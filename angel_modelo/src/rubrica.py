"""Paso 2 · RÚBRICA: decide el estado de cada celda. Configurable (config/rubrica.yaml) y vectorizada.

Uso:  angel_modelo/.venv/bin/python angel_modelo/src/actualizar.py rubrica      (o: sensibilidad)
Lee <salida>/celdas.parquet y escribe <salida>/rubrica.parquet, rubrica_capas.json (+ sensibilidad.csv).

Robustez ante cambios en los datos (regla 12):
  * Una capa (exclusión, condicionante o criterio) solo se ACTIVA si su columna existe y tiene datos en al
    menos `cobertura_minima_capa` de las celdas. Si no, se omite con aviso.
  * Los pesos de los criterios activos se renormalizan para sumar 100, pero la COBERTURA de cada celda se
    mide sobre el peso total configurado: si falta una capa entera, baja la confianza de todas.
  * Una columna nueva que no esté registrada aquí no cambia nada.

Por celda: excluida, exclusiones, penalizacion, score (nota absoluta 0-100), score_pct (percentil de
ordenación entre las celdas no excluidas: NO es una probabilidad), cobertura (parte del peso con dato
real), confianza (alta/media/baja), estado, motivos (hasta 3 códigos), capas_faltan y sub_<criterio>.

Estados (regla conservadora: ante la duda, no viable):
  No evaluable  cobertura < cobertura_minima
  No viable     excluida, o nota < umbral - margen
  Candidata     nota >= umbral (+ margen si la confianza es baja) y sin datos de exclusión que falten
  Dudosa        el resto (cerca del umbral o con datos incompletos)
Códigos de motivo: "E:<id>" exclusión, "C:<id>" condicionante, "-:<id>" criterio que más resta,
"+:<id>" criterio que más suma (solo en Candidatas), "F:datos" faltan datos.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from configuracion import CONFIG as CONFIG_DIR
from configuracion import SEMILLA, salida

CONFIG = CONFIG_DIR / "rubrica.yaml"
OPS = {">=": np.greater_equal, ">": np.greater, "<=": np.less_equal, "<": np.less, "==": np.equal}
ESTADOS = ["Candidata", "Dudosa", "No viable", "No evaluable"]


# ----------------------------------------------------------------------------- configuración
def cargar_config(path=CONFIG) -> dict:
    """Rúbrica común (config/rubrica.yaml) + reglas del perfil del país (config/paises/<pais>.yaml).
    Una regla con `paises: [ISO3, ...]` solo se aplica en esos países."""
    from configuracion import perfil

    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    p = perfil()
    for tipo in ("exclusiones", "condicionantes"):
        extra = (p.get("reglas") or {}).get(tipo) or []
        cfg[tipo] = [r for r in cfg[tipo] + extra if p["pais"] in r.get("paises", [p["pais"]])]
    cfg["_limitaciones"] = p.get("limitaciones_no_modeladas", [])
    validar(cfg)
    return cfg


def validar(cfg: dict):
    w = sum(c["peso"] for c in cfg["criterios"])
    if abs(w - 100) > 1e-6:
        raise ValueError(f"Los pesos de los criterios deben sumar 100 (suman {w})")
    ids = [r["id"] for r in cfg["exclusiones"] + cfg["condicionantes"] + cfg["criterios"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay ids repetidos en la rúbrica")
    for c in cfg["criterios"]:
        xs = [p[0] for p in c["puntos"]]
        if xs != sorted(xs):
            raise ValueError(f"Criterio {c['id']}: los tramos deben ir con x creciente")
        if not all(0 <= p[1] <= 100 for p in c["puntos"]) or not 0 <= c["si_falta"] <= 100:
            raise ValueError(f"Criterio {c['id']}: notas fuera de 0-100")
    for r in cfg["exclusiones"] + cfg["condicionantes"]:
        if r["op"] not in OPS:
            raise ValueError(f"Operador no válido en {r['id']}: {r['op']}")


# ----------------------------------------------------------------------------- utilidades
def columna(df: pd.DataFrame, name: str) -> np.ndarray:
    """Columna como float (NaN si no existe); booleanos -> 0/1."""
    if name not in df:
        return np.full(len(df), np.nan)
    s = df[name]
    if s.dtype == "boolean" or s.dtype == bool:
        s = s.astype("Float64")
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype=float, na_value=np.nan)


def cumple_regla(df, r):
    """(cumple, hay_dato). Sin dato nunca cumple."""
    v = columna(df, r["columna"])
    has = ~np.isnan(v)
    with np.errstate(invalid="ignore"):
        return OPS[r["op"]](v, r["valor"]) & has, has


# ----------------------------------------------------------------------------- rúbrica
def capas_activas(df: pd.DataFrame, cfg: dict) -> dict:
    """Qué capas se usan con estos datos: {id: {"columna", "cobertura", "activa", "tipo"}}."""
    umbral = cfg["salida"].get("cobertura_minima_capa", 0.0)
    out = {}
    for tipo in ("exclusiones", "condicionantes", "criterios"):
        for r in cfg[tipo]:
            cob = float(df[r["columna"]].notna().mean()) if r["columna"] in df.columns and len(df) else 0.0
            out[r["id"]] = {"tipo": tipo, "columna": r["columna"], "cobertura": round(cob, 4),
                            "activa": cob >= umbral and cob > 0}
    return out


def config_efectiva(df: pd.DataFrame, cfg: dict) -> tuple[dict, dict]:
    """Copia de la rúbrica solo con las capas activas; pesos de criterios renormalizados a 100."""
    act = capas_activas(df, cfg)
    c2 = copy.deepcopy(cfg)
    for tipo in ("exclusiones", "condicionantes"):
        c2[tipo] = [r for r in cfg[tipo] if act[r["id"]]["activa"]]
    activos = [c for c in cfg["criterios"] if act[c["id"]]["activa"]]
    total_cfg = sum(c["peso"] for c in cfg["criterios"])
    total_act = sum(c["peso"] for c in activos)
    c2["criterios"] = [dict(c, peso=c["peso"] * 100 / total_act) for c in activos] if total_act else []
    c2["_fraccion_peso_activo"] = total_act / total_cfg if total_cfg else 0.0
    c2["_criterios_inactivos"] = [c["id"] for c in cfg["criterios"] if not act[c["id"]]["activa"]]
    # reglas obligatorias sin capa (p. ej. militar): «no verificadas», bajan la confianza de todas las celdas
    sin = [r for t in ("exclusiones", "condicionantes") for r in cfg[t] if r.get("obligatoria") and not act[r["id"]]["activa"]]
    c2["_no_verificadas"] = sorted({r["id"] for r in sin})
    c2["_penalizacion_no_verificadas"] = sum(r.get("penalizacion_confianza", 0) for r in sin)
    return c2, act


def aplicar(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Aplica la rúbrica. Si `cfg` no viene de config_efectiva, se hace aquí (capas activas y renormalización)."""
    if "_fraccion_peso_activo" not in cfg:
        cfg, _ = config_efectiva(df, cfg)
    n = len(df)
    out = pd.DataFrame(index=df.index)
    if "site_id" in df:
        out["site_id"] = df["site_id"].to_numpy()
    impact, codes = [], []          # matriz de impacto para elegir los motivos

    # 1) exclusiones
    excl = np.zeros(n, bool)
    excl_missing = np.zeros(n, bool)
    ex_names = np.full(n, "", dtype=object)
    for r in cfg["exclusiones"]:
        hit, has = cumple_regla(df, r)
        excl |= hit
        excl_missing |= ~has
        ex_names = np.where(hit, ex_names + np.where(ex_names == "", "", ",") + r["id"], ex_names)
        impact.append(np.where(hit, 1000.0, 0.0))
        codes.append(f"E:{r['id']}")

    # 2) criterios
    total_w = sum(c["peso"] for c in cfg["criterios"]) or 1.0
    frac_activo = cfg["_fraccion_peso_activo"]
    score = np.zeros(n)
    cov = np.zeros(n)
    missing = np.full(n, "", dtype=object)
    losses, gains = [], []
    for c in cfg["criterios"]:
        v = columna(df, c["columna"])
        has = ~np.isnan(v)
        xs, ys = zip(*c["puntos"])
        sub = np.where(has, np.interp(v, xs, ys), c["si_falta"])
        out[f"sub_{c['id']}"] = sub.round(1)
        score += c["peso"] * sub / total_w
        cov += c["peso"] * has / total_w
        missing = np.where(has, missing, missing + np.where(missing == "", "", ",") + c["id"])
        losses.append(np.where(has, c["peso"] * (100 - sub) / total_w, 0.0))
        gains.append(np.where(has, c["peso"] * sub / total_w, 0.0))
    out["score_bruto"] = score.round(2)

    # 3) condicionantes (natura alta y parcial no se suman: cuenta la mayor)
    pen = np.zeros(n)
    hits = {}
    bloquea = np.zeros(n, bool)
    for r in cfg["condicionantes"]:
        hits[r["id"]], has_c = cumple_regla(df, r)
        if r.get("bloquea_candidata"):
            bloquea |= hits[r["id"]]
        if r.get("obligatoria"):
            excl_missing |= ~has_c        # celda sin dato en una regla obligatoria: no puede ser Candidata
    if "natura2000_alta" in hits and "natura2000_parcial" in hits:
        hits["natura2000_parcial"] = hits["natura2000_parcial"] & ~hits["natura2000_alta"]
    for r in cfg["condicionantes"]:
        h = hits[r["id"]]
        pen += h * r["penalizacion"]
        impact.append(np.where(h, 100.0 + r["penalizacion"], 0.0))   # por delante de los criterios
        codes.append(f"C:{r['id']}")
    out["penalizacion"] = pen
    final = np.clip(score - pen, 0, 100)
    out["score"] = final.round(2)
    cov = cov * frac_activo                     # sobre el peso total configurado (capas omitidas cuentan)
    cov = np.clip(cov - cfg.get("_penalizacion_no_verificadas", 0.0), 0, 1)
    out["cobertura"] = cov.round(3)

    # 4) confianza y estado
    s = cfg["salida"]
    thr, margin = s["umbral_candidata"], s["margen_duda"]
    conf = np.where(cov >= s["confianza"]["alta"], "alta", np.where(cov >= s["confianza"]["media"], "media", "baja"))
    evaluable = cov >= s["cobertura_minima"]
    need = np.where(conf == "baja", thr + margin, thr)
    conf_min = s.get("cobertura_minima_candidata", 0.0)
    candidata = ~excl & evaluable & ~excl_missing & ~bloquea & (cov >= conf_min) & (final >= need)
    noviable = excl | (evaluable & (final < thr - margin))
    estado = np.select([~evaluable & ~excl, noviable, candidata], ["No evaluable", "No viable", "Candidata"], "Dudosa")
    out["excluida"] = excl
    out["exclusiones"] = ex_names
    out["confianza"] = conf
    out["estado"] = estado
    out["viable"] = estado == "Candidata"

    # percentil de ordenación entre las no excluidas (0 = peor, 100 = mejor)
    pct = pd.Series(np.where(excl, np.nan, final)).rank(pct=True, method="average") * 100
    out["score_pct"] = pct.round(1).to_numpy()

    # 5) motivos: hasta 3 códigos por celda, del mayor impacto al menor
    is_cand = estado == "Candidata"
    for c, lo, ga in zip(cfg["criterios"], losses, gains):
        impact.append(np.where(is_cand, 0.0, lo))
        codes.append(f"-:{c['id']}")
        impact.append(np.where(is_cand, ga, 0.0))
        codes.append(f"+:{c['id']}")
    impact.append(np.where((~evaluable | excl_missing) & ~excl, 500.0, 0.0))
    codes.append("F:datos")
    M = np.vstack(impact).T
    order = np.argsort(-M, axis=1, kind="stable")[:, :3]
    top_val = np.take_along_axis(M, order, axis=1)
    codes = np.array(codes, dtype=object)
    out["motivos"] = ["|".join(codes[o][v > 0.05]) for o, v in zip(order, top_val)]
    inactivos = ",".join(cfg["_criterios_inactivos"] + [f"{x}(no verificada)" for x in cfg.get("_no_verificadas", [])])
    if inactivos:
        missing = np.where(missing == "", inactivos, missing + "," + inactivos)
    out["capas_faltan"] = missing
    return out


# ----------------------------------------------------------------------------- sensibilidad
def sensibilidad(df: pd.DataFrame, cfg: dict, seed: int = SEMILLA, n_mc: int = 100) -> pd.DataFrame:
    """Cuántas celdas cambian de estado Candidata/no al mover pesos (x0,5 y x1,5, renormalizando),
    tramos (±20 %), umbrales (±20 %), el umbral de candidata (±5) y pesos aleatorios (Dirichlet)."""
    base = aplicar(df, cfg)["viable"].to_numpy()
    rows = []

    def run(name, c2):
        v = aplicar(df, c2)["viable"].to_numpy()
        rows.append({"cambio": name, "candidatas": int(v.sum()), "entran": int((v & ~base).sum()),
                     "salen": int((~v & base).sum()), "cambian_pct": round(100 * (v != base).mean(), 3)})

    for i, c in enumerate(cfg["criterios"]):
        for f in (0.5, 1.5):
            c2 = copy.deepcopy(cfg)
            c2["criterios"][i]["peso"] *= f
            tot = sum(x["peso"] for x in c2["criterios"])
            for x in c2["criterios"]:
                x["peso"] *= 100 / tot
            run(f"peso {c['id']} x{f}", c2)
        for f in (0.8, 1.2):
            c2 = copy.deepcopy(cfg)
            c2["criterios"][i]["puntos"] = [[x * f, y] for x, y in c["puntos"]]
            run(f"tramos {c['id']} x{f}", c2)
    for key in ("exclusiones", "condicionantes"):
        for i, r in enumerate(cfg[key]):
            if r["op"] == "==":
                continue
            for f in (0.8, 1.2):
                c2 = copy.deepcopy(cfg)
                c2[key][i]["valor"] = r["valor"] * f
                run(f"umbral {r['id']} x{f}", c2)
    for d in (-5, 5):
        c2 = copy.deepcopy(cfg)
        c2["salida"]["umbral_candidata"] += d
        run(f"umbral_candidata {d:+d}", c2)

    rng = np.random.default_rng(seed)
    w0 = np.array([c["peso"] for c in cfg["criterios"]], float)
    labels = []
    for _ in range(n_mc):
        c2 = copy.deepcopy(cfg)
        for x, wi in zip(c2["criterios"], rng.dirichlet(w0 / 100 * 50) * 100):
            x["peso"] = wi
        labels.append(aplicar(df, c2)["viable"].to_numpy())
    L = np.array(labels)
    stab = (L == base).mean(0)
    rows.append({"cambio": f"Monte Carlo pesos (n={n_mc}): media", "candidatas": int(L.sum(1).mean()),
                 "entran": None, "salen": None, "cambian_pct": round(100 * (L != base).mean(), 3)})
    rows.append({"cambio": "Monte Carlo: candidatas estables en >= 90 % de sorteos",
                 "candidatas": int(((stab >= 0.9) & base).sum()), "entran": None, "salen": None,
                 "cambian_pct": round(100 * (stab < 0.9).mean(), 3)})
    return pd.DataFrame(rows)


def main():
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--sensibilidad", action="store_true")
    a = ap.parse_args()
    cfg = cargar_config(a.config)
    out = salida()
    df = pd.read_parquet(out / "celdas.parquet")
    efectiva, act = config_efectiva(df, cfg)
    for k, v in act.items():
        if not v["activa"]:
            print(f"  AVISO: capa '{k}' ({v['columna']}) omitida: cobertura {v['cobertura']:.0%}")
    res = aplicar(df, efectiva)
    res.to_parquet(out / "rubrica.parquet", index=False)
    (out / "rubrica_capas.json").write_text(json.dumps(
        {"capas": act, "fraccion_peso_activo": round(efectiva["_fraccion_peso_activo"], 4)},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"celdas={len(res):,}  estados={res.estado.value_counts().to_dict()}")
    print("confianza:", res.confianza.value_counts().to_dict(), " cobertura media:", round(float(res.cobertura.mean()), 3))
    if "dc_real" in df:
        dc = df["dc_real"].to_numpy()
        print("celdas con DC real por estado:", res[dc].estado.value_counts().to_dict(),
              " excluidas con DC:", int(res[dc].excluida.sum()))
    if a.sensibilidad:
        s = sensibilidad(df, efectiva)
        s.to_csv(out / "sensibilidad.csv", index=False)
        print(s.sort_values("cambian_pct", ascending=False).head(12).to_string(index=False))


if __name__ == "__main__":
    main()
