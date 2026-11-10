"""Paso 3 · EVALUAR: ¿aporta algo un modelo entrenado frente a la rúbrica y a una regla de 2 variables?

Uso:  angel_modelo/.venv/bin/python angel_modelo/evaluar.py
Lee out/celdas.parquet, out/rubrica.parquet y pipeline/data/processed/features_es_3500.parquet (+ priors_voz.csv).
Escribe out/metricas.json (lo lee el panel "Sobre el modelo" del mapa) y out/afinidad.parquet.

Diseño (por qué así, en EXPLICACION_CODIGO.md):
  * Target de validación: celda con data center real (lista unificada, datos.py). Es PU: "sin DC" no es "no viable".
  * Validación ESPACIAL por provincias: StratifiedGroupKFold(5), grupos = provincia, semilla 42. Nunca aleatoria.
  * Intervalos: bootstrap por provincias (se remuestrean provincias enteras, 500 réplicas) sobre las
    predicciones fuera de pliegue.
  * Candidatos:
      - Rúbrica (no se entrena: su nota se evalúa tal cual).
      - Logística con 2 variables: urbano_pct + industrial_pct (la referencia que hay que batir).
      - Réplica del modelo del equipo: gradient boosting con las mismas variables (features_es_3500) y las
        mismas restricciones monotónicas de expertos (priors_voz.csv). LightGBM no carga en este Mac
        (libomp), así que se usa HistGradientBoostingClassifier de scikit-learn, que admite monotonic_cst.
  * Regla de decisión (fijada ANTES de ver los resultados): el modelo entra al mapa como capa de "afinidad"
    solo si su PR-AUC supera a la de la rúbrica y a la de la logística de 2 variables en al menos el 90 %
    de las réplicas bootstrap. Si no, queda como experimento documentado.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from configuracion import SEMILLA as SEED
from configuracion import columnas, ruta, salida

N_BOOT = int(os.environ.get("MAPA_N_BOOT", 300))   # réplicas bootstrap (la prueba de aceptación usa menos)
TOP = 0.05
REDUNDANT_RHO = 0.95       # como pipeline/src/train.py (drop_redundant)


def variables_experimento(df: pd.DataFrame, clases: dict) -> tuple[list, dict]:
    """Columnas candidatas para el modelo, con filtros automáticos. Devuelve (usadas, descartadas{col: motivo})."""
    cfg = columnas()["clasificacion"]
    leak = set()
    try:
        sys.path.insert(0, str(ruta("pipeline_src")))
        from features import LEAKAGE  # noqa: PLC0415  (lista del equipo)

        leak = set(LEAKAGE)
    except Exception:  # noqa: BLE001
        pass
    propias = {"dc_pipeline", "dc_elt", "dc_real", "excl_equipo", "equipo_score_pct", "equipo_oof_pct",
               "inversion_eur_m2"}
    usadas, fuera = [], {}
    for c in df.columns:
        k = clases.get(c, "")
        if k in ("identificador", "coordenada", "categorica", "fecha"):
            continue
        if c in propias:
            continue
        if k == "constante":
            fuera[c] = "constante"
        elif c in leak or any(p in c for p in cfg["fuga_patrones"]):
            fuera[c] = "posible fuga (dice dónde hay data centers)"
        elif df[c].notna().mean() < cfg["cobertura_minima_modelo"]:
            fuera[c] = f"cobertura {df[c].notna().mean():.0%}"
        else:
            usadas.append(c)
    return usadas, fuera


def recall_superior(y, s, frac=TOP):
    k = max(1, int(len(s) * frac))
    return y[np.argsort(-s, kind="stable")[:k]].sum() / max(1, y.sum())


def quitar_redundantes(X: pd.DataFrame, thr=REDUNDANT_RHO) -> list:
    """Misma regla que pipeline/src/train.py: quita una de cada par con |Spearman| > 0,95."""
    c = X.sample(min(len(X), 20000), random_state=SEED).corr(method="spearman").abs()
    up = c.where(np.triu(np.ones(c.shape, dtype=bool), k=1))
    return [col for col in up.columns if (up[col] > thr).any()]


def predecir_fuera_de_pliegue(make, X, y, splits):
    out = np.zeros(len(y))
    for tr, te in splits:
        m = make().fit(X.iloc[tr], y[tr])
        out[te] = m.predict_proba(X.iloc[te])[:, 1]
    return out


def bootstrap_provincias(y, scores: dict, groups, n=N_BOOT, seed=SEED):
    """Bootstrap por provincias: devuelve réplicas de PR-AUC, AUC y recall@5 % por puntuación."""
    rng = np.random.default_rng(seed)
    prov = pd.Series(groups).astype("category")
    codes = prov.cat.codes.to_numpy()
    idx_by = [np.flatnonzero(codes == k) for k in range(len(prov.cat.categories))]
    res = {k: {"pr": [], "auc": [], "rec": []} for k in scores}
    for _ in range(n):
        pick = rng.integers(0, len(idx_by), len(idx_by))
        ix = np.concatenate([idx_by[p] for p in pick])
        yy = y[ix]
        if yy.sum() == 0 or yy.sum() == len(yy):
            continue
        for k, s in scores.items():
            ss = s[ix]
            res[k]["pr"].append(average_precision_score(yy, ss))
            res[k]["auc"].append(roc_auc_score(yy, ss))
            res[k]["rec"].append(recall_superior(yy, ss))
    return {k: {m: np.array(v) for m, v in d.items()} for k, d in res.items()}


def intervalo95(a):
    return [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)]


def calibracion(y, p, bins=10):
    q = pd.qcut(pd.Series(p).rank(method="first"), bins, labels=False)
    t = pd.DataFrame({"q": q, "p": p, "y": y}).groupby("q").mean()
    return {"brier": round(float(brier_score_loss(y, p)), 4),
            "decil_superior_prob_media": round(float(t.p.iloc[-1]), 4),
            "decil_superior_tasa_real": round(float(t.y.iloc[-1]), 4)}


def main():
    out = salida()
    cells = pd.read_parquet(out / "celdas.parquet")
    rub = pd.read_parquet(out / "rubrica.parquet")
    info = json.loads((out / "informe_carga.json").read_text(encoding="utf-8"))
    clases = {c: v["clase"] for c, v in info["esquema"].items()}
    idc = columnas()["identificador"]["columna"]
    provc = columnas()["admin"]["provincia"]["columna"]
    pri_f = ruta("pipeline_processed") / "priors_voz.csv"
    pri = pd.read_csv(pri_f) if pri_f.exists() else pd.DataFrame(columns=["feature", "monotone"])

    keep = ~rub["excluida"].to_numpy()
    df = cells[keep].reset_index(drop=True)
    df["rubrica"] = rub["score"].to_numpy()[keep]
    feat_cols, descartadas = variables_experimento(df, clases)
    X = df[feat_cols].astype(float)
    red = quitar_redundantes(X) if len(feat_cols) > 1 else []
    X = X.drop(columns=red)
    sign = dict(zip(pri["feature"], pri["monotone"]))
    mono = [int(sign.get(c, 0)) for c in X.columns]
    groups = df[provc].to_numpy()
    for c in ("urbano_pct", "industrial_pct"):
        if c not in df.columns:
            df[c] = np.nan

    results = {}
    for target in ("dc_real",):
        y = df[target].astype(int).to_numpy()
        splits = list(StratifiedGroupKFold(5, shuffle=True, random_state=SEED).split(X, y, groups))
        hgb = lambda: HistGradientBoostingClassifier(  # noqa: E731
            max_iter=300, learning_rate=0.03, max_leaf_nodes=15, min_samples_leaf=20, l2_regularization=1.0,
            class_weight="balanced", monotonic_cst=mono, random_state=SEED)
        lr2 = lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),  # noqa: E731
                                    LogisticRegression(class_weight="balanced", max_iter=2000))
        scores = {
            "rubrica": df["rubrica"].to_numpy(),
            "logistica_2_variables": predecir_fuera_de_pliegue(lr2, df[["urbano_pct", "industrial_pct"]], y, splits),
            "modelo_equipo_replica": predecir_fuera_de_pliegue(hgb, X, y, splits),
        }
        rng = np.random.default_rng(SEED)
        scores["aleatorio"] = rng.random(len(y))
        bs = bootstrap_provincias(y, scores, groups)
        if y.sum() < 10 or len(set(groups)) < 5:
            print("  AVISO: menos de 10 celdas con data center o de 5 provincias: no se puede evaluar")
            results[target] = {"positivos": int(y.sum()), "celdas": int(len(y)), "evaluable": False}
            afin = np.full(len(y), np.nan)
            continue
        r = {"positivos": int(y.sum()), "celdas": int(len(y)), "pliegues_positivos": [int(y[te].sum()) for _, te in splits]}
        for k, s in scores.items():
            r[k] = {"pr_auc": round(float(average_precision_score(y, s)), 4), "pr_auc_ic95": intervalo95(bs[k]["pr"]),
                    "auc": round(float(roc_auc_score(y, s)), 4), "auc_ic95": intervalo95(bs[k]["auc"]),
                    "recall_top5": round(float(recall_superior(y, s)), 4), "recall_top5_ic95": intervalo95(bs[k]["rec"])}
        for k in ("logistica_2_variables", "modelo_equipo_replica"):
            r[k]["calibracion"] = calibracion(y, scores[k])
        m, a, b = bs["modelo_equipo_replica"]["pr"], bs["rubrica"]["pr"], bs["logistica_2_variables"]["pr"]
        r["prob_modelo_supera_a_ambos"] = round(float(np.mean((m > a) & (m > b))), 3)
        if "equipo_oof_pct" in df and df["equipo_oof_pct"].notna().all():
            e = df["equipo_oof_pct"].to_numpy()
            yp = df["dc_pipeline"].astype(int).to_numpy()
            r["modelo_equipo_original_bloques70km"] = {
                "nota": "oof_spatial_pct de pipeline/src/train.py (LightGBM, bloques de 70 km, no provincias; target datacentermap)",
                "pr_auc": round(float(average_precision_score(yp, e)), 4), "auc": round(float(roc_auc_score(yp, e)), 4),
                "recall_top5": round(float(recall_superior(yp, e)), 4)}
        results[target] = r
        if target == "dc_real":
            afin = scores["modelo_equipo_replica"]

    main_r = results["dc_real"]
    entra = bool(main_r.get("prob_modelo_supera_a_ambos", 0) >= 0.9)
    met = {
        "huella_datos": info["huella"],
        "validacion": "Espacial por provincias: StratifiedGroupKFold(5, semilla 42), grupos = provincia; "
                      f"intervalos al 95 % por bootstrap de provincias ({N_BOOT} réplicas)",
        "target": "Celda con data center real (lista unificada datacentermap + OSM/PeeringDB). Aprendizaje PU: "
                  "una celda sin data center no es 'no viable'",
        "variables_modelo": int(X.shape[1]), "quitadas_por_redundantes": red,
        "variables_usadas": list(X.columns), "variables_descartadas": descartadas,
        "restricciones_monotonicas": int(sum(1 for v in mono if v)),
        "regla_de_decision": "El modelo entra al mapa como 'afinidad' solo si su PR-AUC supera a la rúbrica y a la "
                             "logística de 2 variables en >= 90 % de las réplicas bootstrap",
        "modelo_entra_al_mapa": bool(entra),
        "resultados": results,
        "lo_que_no_se_ha_medido": [
            "Calibración como probabilidad de 'viable': no existe un target 'viable' verdadero; las notas son ordenaciones",
            "Rendimiento fuera de España",
            "Si una celda Candidata tiene suelo disponible o capacidad de red real (no hay datos de REE por nudo)",
            "Validación con proyectos cancelados o denegados (negativos reales): no hay datos",
        ],
    }
    (out / "metricas.json").write_text(json.dumps(met, ensure_ascii=False, indent=1), encoding="utf-8")
    pd.DataFrame({idc: df[idc], "afinidad_pct": pd.Series(afin).rank(pct=True).mul(100).round(1)}
                 ).to_parquet(out / "afinidad.parquet", index=False)

    for t, r in results.items():
        if not r.get("evaluable", True):
            continue
        print(f"\n== target {t}: {r['positivos']} positivos en {r['celdas']:,} celdas; por pliegue {r['pliegues_positivos']}")
        rows = {k: v for k, v in r.items() if isinstance(v, dict) and "pr_auc" in v}
        print(pd.DataFrame(rows).T[["pr_auc", "pr_auc_ic95", "auc", "auc_ic95", "recall_top5"]].to_string())
        print("P(modelo > rúbrica y > logística 2v) =", r["prob_modelo_supera_a_ambos"])
    print("\ncalibración réplica:", results["dc_real"]["modelo_equipo_replica"]["calibracion"])
    print(f"\nMODELO ENTRA AL MAPA: {entra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
