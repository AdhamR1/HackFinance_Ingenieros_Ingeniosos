"""Paso 5 · SENTIDO COMÚN (tarea 4f): comprueba que los resultados de cada país tienen sentido.

Uso:  angel_modelo/.venv/bin/python angel_modelo/src/actualizar.py sentido
Lee <salida>/<pais>/celdas.parquet y rubrica.parquet de cada país; escribe docs/SENTIDO_RESULTADOS.md y
<salida>/<pais>/sentido.json (lo comprueba tests/test_sentido.py). No cambia ningún resultado.

Comprobaciones (fallo = 'NO'):
  1 ninguna Candidata con una exclusión activa;  2 ninguna Candidata en agua dominante (>= 50 %) ni en centro
  urbano denso (>= 80 %);  3 monotonía (empeorar un criterio nunca mejora la nota, se prueba en tests);
  4 sin NaN inesperados;  5 % de Candidatas dentro del rango configurado (si no, aviso);
  6 estabilidad: % de Candidatas que mantienen la etiqueta con pesos ±30 % (40 sorteos uniformes).
Revisión cualitativa: 20 mejores celdas de 5 divisiones, marcando las sospechosas con reglas objetivas.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from configuracion import REPO, SEMILLA, columnas, paises_disponibles, ruta

SOSPECHAS = [  # (columna, condición, texto) – solo con datos existentes
    ("dist_airport_runway_km", lambda v: v < 1.0, "a menos de 1 km de una pista de aeropuerto"),
    ("elevation_m", lambda v: v > 1200, "montaña (> 1.200 m)"),
    ("agua_pct", lambda v: v > 20, "embalse o lámina de agua (> 20 % de la celda)"),
    ("industrial_pct", lambda v: v > 60, "polígono industrial ya ocupado en su mayoría (> 60 %)"),
    ("slope_pct", lambda v: v > 25, "pendiente media > 25 %"),
]


def analizar(pais: str) -> dict:
    os.environ["MAPA_PAIS"] = pais
    import rubrica as R

    out = ruta("salida") / pais
    cel, rub = pd.read_parquet(out / "celdas.parquet"), pd.read_parquet(out / "rubrica.parquet")
    df = pd.concat([cel, rub.drop(columns="site_id")], axis=1)
    cfg = R.cargar_config()
    efectiva, _ = R.config_efectiva(cel, cfg)
    cand = df.estado == "Candidata"
    prov = columnas()["admin"]["provincia"]["columna"]
    r = {"pais": pais, "celdas": len(df), "candidatas": int(cand.sum()),
         "pct_candidatas": round(100 * float(cand.mean()), 2), "estados": df.estado.value_counts().to_dict()}
    r["c1_candidata_con_exclusion"] = int((cand & df.excluida).sum())
    agua = df["agua_pct"] >= 50 if "agua_pct" in df else pd.Series(False, index=df.index)
    urb = df["urbano_pct"] >= 80 if "urbano_pct" in df else pd.Series(False, index=df.index)
    r["c2_candidata_en_agua_o_centro_urbano"] = int((cand & (agua | urb)).sum())
    r["c4_nan_inesperados"] = int(df[["estado", "score", "cobertura", "confianza"]].isna().sum().sum()
                                  + df.loc[~df.excluida, "score_pct"].isna().sum())
    lo, hi = cfg["salida"].get("rango_candidatas_pct", [0, 100])
    r["c5_rango_candidatas"] = [lo, hi]
    r["c5_en_rango"] = bool(lo <= r["pct_candidatas"] <= hi)
    rng = np.random.default_rng(SEMILLA)
    base = cand.to_numpy()
    est = []
    for _ in range(40):
        c2 = copy.deepcopy(efectiva)
        for c in c2["criterios"]:
            c["peso"] *= rng.uniform(0.7, 1.3)
        t = sum(c["peso"] for c in c2["criterios"]) or 1
        for c in c2["criterios"]:
            c["peso"] *= 100 / t
        est.append(R.aplicar(cel, c2)["viable"].to_numpy())
    est = np.array(est)
    r["c6_estabilidad_candidatas_pct"] = round(100 * float((est[:, base].mean(axis=0) >= 0.9).mean()), 1) if base.any() else None
    # revisión cualitativa
    divs = df[~df.excluida].groupby(prov)["score"].max().sort_values(ascending=False).index[:5].tolist()
    filas = []
    for d in divs:
        top = df[(df[prov] == d) & ~df.excluida].nlargest(20, "score")
        for _, t in top.iterrows():
            sos = [txt for col, f, txt in SOSPECHAS if col in t and pd.notna(t[col]) and f(t[col])]
            filas.append({"division": d, "site_id": t["site_id"], "estado": t["estado"], "nota": round(t["score"], 1),
                          "motivos": t["motivos"], "sospecha": "; ".join(sos)})
    top = pd.DataFrame(filas)
    r["top_revisadas"] = len(top)
    r["top_sospechosas"] = int((top.sospecha != "").sum()) if len(top) else 0
    r["sospechas_por_tipo"] = top.sospecha.str.split("; ").explode().loc[lambda s: s != ""].value_counts().to_dict() if len(top) else {}
    top.to_csv(out / "top20_divisiones.csv", index=False)
    (out / "sentido.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r, top


def main():
    paises = [p for p in os.environ.get("MAPA_PAISES", ",".join(paises_disponibles())).split(",") if p]
    L = ["# Sentido de los resultados (generado por src/sentido.py)", "",
         "Comprobaciones automáticas por país (fallos = 0 en 1, 2 y 4). Ejecuta `actualizar.py sentido` para regenerarlo.", ""]
    for p in paises:
        if not (ruta("salida") / p / "rubrica.parquet").exists():
            L.append(f"## {p}: sin resultados (ejecuta el pipeline)")
            continue
        r, top = analizar(p)
        L += [f"## {p.upper()} · {r['celdas']:,} celdas · Candidatas {r['candidatas']} ({r['pct_candidatas']} %)",
              f"- Estados: {r['estados']}",
              f"- (1) Candidatas con exclusión activa: **{r['c1_candidata_con_exclusion']}**",
              f"- (2) Candidatas en agua dominante o centro urbano denso: **{r['c2_candidata_en_agua_o_centro_urbano']}**",
              "- (3) Monotonía: probada en tests/test_sentido.py (empeorar un criterio nunca sube la nota)",
              f"- (4) NaN inesperados: **{r['c4_nan_inesperados']}**",
              f"- (5) % Candidatas en el rango {r['c5_rango_candidatas']}: {'sí' if r['c5_en_rango'] else '**NO (aviso)**'}",
              f"- (6) Estabilidad con pesos ±30 % (Candidatas que lo siguen siendo en ≥ 90 % de 40 sorteos): {r['c6_estabilidad_candidatas_pct']} %",
              f"- Revisión: {r['top_revisadas']} celdas (20 mejores de 5 divisiones); sospechosas: {r['top_sospechosas']} · {r['sospechas_por_tipo']}",
              f"  (lista completa en salida/{p}/top20_divisiones.csv)", ""]
        if len(top):
            ej = top[top.sospecha != ""].head(8)
            if len(ej):
                L += ["| División | Celda | Estado | Nota | Sospecha |", "|---|---|---|---|---|"] + [
                    f"| {t.division} | {t.site_id} | {t.estado} | {t.nota} | {t.sospecha} |" for t in ej.itertuples()] + [""]
    L += ["## Reglas propuestas para las sospechas",
          "- Pista de aeropuerto a < 1 km: ya penaliza `servidumbre_aeronautica` cuando la celda está en la trayectoria; "
          "una distancia < 1 km a la pista sin trayectoria no se ha convertido en regla (sin base normativa verificada).",
          "- Montaña (> 1.200 m): `altitud_alta` penaliza desde 1.500 m; el sobrecoste entre 1.200 y 1.500 m lo recoge la pendiente.",
          "- Embalses: `agua` excluye desde el 90 % de la celda; entre 20 y 90 % la parcela útil se reduce, pero no se veta.",
          "- Polígono lleno (> 60 % industrial): no se puede verificar la disponibilidad real de parcelas con los datos actuales (limitación).",
          ""]
    doc = REPO / "angel_modelo" / "docs" / "SENTIDO_RESULTADOS.md"
    doc.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
