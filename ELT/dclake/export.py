"""Human-readable Excel sample of the assembled tables for a few cells (for the team to look at)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .schema import _read


def _meta(cfg) -> pd.DataFrame:
    dic, daily = _read(str(cfg.dictionary_path))
    cols = ["Campo", "Bloque", "Unidad", "Descripción", "Prioridad"]
    m = pd.concat([dic[[c for c in cols if c in dic]], daily[[c for c in cols if c in daily]]], ignore_index=True)
    return m.drop_duplicates("Campo").set_index("Campo")


def export_sample(lake, cfg, site_ids: list[str] | None, out: Path, n_default: int = 3) -> Path:
    t = lake.tables
    static = pd.read_parquet(t / "sites_static.parquet")
    if not site_ids:  # cells that have the most data
        site_ids = static.set_index("site_id").notna().sum(axis=1).sort_values(ascending=False).index[:n_default].tolist()
    meta = _meta(cfg)
    lin = pd.read_parquet(t / "field_lineage.parquet")
    src = lin.drop_duplicates("field").set_index("field")["source"]

    def transpose(df: pd.DataFrame, key: str) -> pd.DataFrame:
        tr = df.set_index(key).T
        tr.columns = [str(c) for c in tr.columns]
        tr.insert(0, "bloque", tr.index.map(meta["Bloque"]) if "Bloque" in meta else "")
        tr.insert(1, "unidad", tr.index.map(meta["Unidad"]) if "Unidad" in meta else "")
        tr.insert(2, "descripcion", tr.index.map(meta["Descripción"]) if "Descripción" in meta else "")
        tr.insert(3, "fuente", tr.index.map(src))
        tr["con_datos"] = df.set_index(key).T.notna().any(axis=1)
        return tr.rename_axis("campo").reset_index().sort_values(["con_datos", "bloque", "campo"], ascending=[False, True, True])

    sheets = {}
    st = static[static["site_id"].isin(site_ids)]
    sheets["celdas_estatico"] = transpose(st, "site_id")
    yearly = pd.read_parquet(t / "sites_yearly.parquet")
    y = yearly[yearly["site_id"].isin(site_ids)].copy()
    y["site_id"] = y["site_id"] + " " + y["year"].astype(str)
    y = y[y.drop(columns=["site_id", "year"]).notna().any(axis=1)]
    sheets["celdas_anual"] = transpose(y.drop(columns="year"), "site_id")
    daily = pd.read_parquet(t / "sites_weekly", filters=[("site_id", "in", site_ids)])
    daily = daily.dropna(axis=1, how="all").sort_values(["site_id", "week_start"])
    sheets["celdas_semanal"] = daily
    cd = pd.read_parquet(t / "country_daily.parquet").dropna(axis=1, how="all")
    sheets["pais_diario"] = cd
    cc = pd.read_parquet(t / "country_context.parquet")
    sheets["contexto_paises"] = cc[cc.drop(columns=["country_iso3", "year"]).notna().any(axis=1)].dropna(axis=1, how="all")
    cov = lake.reports / "coverage.csv"
    if cov.exists():
        sheets["cobertura_campos"] = pd.read_csv(cov)

    info = pd.DataFrame({"hoja": list(sheets), "contenido": [
        "Campos estáticos de las celdas de ejemplo (una columna por celda; primero los que tienen datos)",
        "Campos anuales (agregados de clima, precio, macro) por celda y año",
        "Variables semanales por celda (solo columnas con datos)",
        "Variables diarias de España: precio OMIE, mix REE, EUR/USD",
        "Indicadores por país y año (8 países)",
        "Estado de cada campo del diccionario: con datos / sin datos / pendiente / sin colector",
    ][: len(sheets)]})
    info.loc[len(info)] = ["celdas", ", ".join(site_ids)]
    info.loc[len(info)] = ["periodo", f"{cfg['period']['start']} a {cfg['period']['end']}"]

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        info.to_excel(xw, sheet_name="LEEME", index=False)
        for name, df in sheets.items():
            df = df.copy()
            for c in df.columns:  # Excel cannot store tz-aware datetimes or lists
                if pd.api.types.is_datetime64_any_dtype(df[c]) and getattr(df[c].dt, "tz", None) is not None:
                    df[c] = df[c].dt.tz_localize(None)
                elif df[c].dtype == object:
                    df[c] = df[c].map(lambda v: str(v) if isinstance(v, (list, dict)) else v)
            df.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            ws.freeze_panes = "B2"
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    lake.log.info("Ejemplo exportado: %s", out)
    return out
