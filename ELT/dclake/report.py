"""Coverage report: which dictionary fields have data, which are pending and why."""
from __future__ import annotations

import pandas as pd

from .schema import _read, load_schemas


def coverage_report(lake, cfg, registry) -> pd.DataFrame:
    specs = load_schemas(cfg.dictionary_path)
    lin_p = lake.tables / "field_lineage.parquet"
    lin = pd.read_parquet(lin_p) if lin_p.exists() else pd.DataFrame(columns=["table", "field", "coverage_pct", "collector"])
    lin = lin.set_index(["table", "field"])
    dic, daily = _read(str(cfg.dictionary_path))

    declared = {}
    for cls in registry:
        c = cls(lake, cfg)
        for t, fl in c.declared_fields().items():
            for f in fl:
                declared.setdefault((t, f), []).append(c)

    meta = {}
    for _, r in dic.iterrows():
        tables = {"sites": ("sites_static" if r["Temporalidad"] == "Estático" else "sites_yearly"),
                  "country_context": "country_context", "stations": "stations",
                  "signal_features": "signal_features"}
        t = tables.get(r["Tabla"])
        if t:
            meta[(t, r["Campo"])] = (r["Bloque"], r["Prioridad"])
    for _, r in daily.iterrows():
        meta[(r["Tabla"], r["Campo"])] = ("Variables diarias", "MVP")
    wsrc = {f: str(m.get("Desde (campo diario)", "")) for f, m in specs["sites_weekly"].meta.items()}
    for f in wsrc:
        meta[("sites_weekly", f)] = ("Variables semanales", "MVP")

    rows = []
    for t, spec in specs.items():
        if t in ("field_lineage", "sites_daily"):   # the daily layer is internal; the lake gets sites_weekly
            continue
        for f in spec.fields:
            if f in spec.keys:
                continue
            cov = float(lin.loc[(t, f), "coverage_pct"]) if (t, f) in lin.index else 0.0
            cs = declared.get(("sites_daily", wsrc.get(f, f)) if t == "sites_weekly" else (t, f), [])
            impl = [c for c in cs if c.status != "pendiente"]
            pend = [c for c in cs if c.status == "pendiente"]
            if cov > 0:
                status = "con datos"
            elif impl:
                status = "sin datos (revisar clave, archivo manual o log)"
            elif pend:
                status = "pendiente"
            else:
                status = "sin colector"
            bloque, prio = meta.get((t, f), ("", ""))
            rows.append({"table": t, "field": f, "bloque": bloque, "prioridad": prio, "coverage_pct": round(cov, 1),
                         "status": status, "collectors": ",".join(c.name for c in impl),
                         "pending_reason": "; ".join(getattr(c, "reason", "") for c in pend)})
    rep = pd.DataFrame(rows).sort_values(["table", "bloque", "field"])
    lake.reports.mkdir(parents=True, exist_ok=True)       # inside the cache, not in the dataset
    rep.to_csv(lake.reports / "coverage.csv", index=False, encoding="utf-8-sig")

    log = lake.log
    log.info("Cobertura del diccionario (%d campos):", len(rep))
    for s, n in rep["status"].value_counts().items():
        log.info("  %-48s %4d", s, n)
    mvp = rep[rep["prioridad"] == "MVP"]
    if len(mvp):
        log.info("  Campos MVP con datos: %d de %d", (mvp["status"] == "con datos").sum(), len(mvp))
    log.info("Informe completo: %s", lake.reports / "coverage.csv")
    return rep
