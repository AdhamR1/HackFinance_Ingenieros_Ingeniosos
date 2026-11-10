"""Quality control of one country's dataset: keys, physical ranges and consistency between fields.

Writes <cache>/<ISO>/reports/qc.csv (one row per check) and logs a summary. A failing check does
not stop anything: it points at a source or a step to review.

    python -m dclake qc --country ESP
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Plausible ranges: (min, max) by exact field name, then by suffix. NaN never fails a range.
RANGES = {
    "lat": (-90, 90),
    "lon": (-180, 180),
    "elevation_m": (-450, 5000),
    "slope_pct": (0, 300),
    "aspect_deg": (0, 360),
    "pga_475y_g": (0, 3),
    "t2m_mean_c": (-50, 45),
    "t2m_max_c": (-45, 55),
    "t2m_min_c": (-60, 40),
    "rh_mean_pct": (0, 100),
    "wind10m_mean_ms": (0, 60),
    "precip_mm": (0, 2000),  # weekly sum
    "n_days_week": (1, 7),
    "free_cooling_hours": (0, 168),
    "adiabatic_cooling_hours": (0, 168),
    "renewable_share_pct": (0, 100),
    "omie_price_mean_eur_mwh": (-500, 4000),
}
SUFFIX_RANGES = {
    "_pct": (0, 100),
    "_km": (0, 20_000),
    "_mw": (0, 1e6),
    "_depth_rp10_m": (0, 100),
    "_depth_rp100_m": (0, 100),
    "_depth_rp500_m": (0, 100),
}
# (table, lower field, upper field): lower <= upper wherever both are known
ORDER = [
    ("sites_weekly", "t2m_min_c", "t2m_mean_c"),
    ("sites_weekly", "t2m_mean_c", "t2m_max_c"),
    ("sites_static", "flood_depth_rp10_m", "flood_depth_rp100_m"),
    ("sites_static", "flood_depth_rp100_m", "flood_depth_rp500_m"),
    ("sites_static", "dist_hv_line_km", "dist_400kv_line_km"),
    ("sites_static", "population_1km", "population_10km"),
    ("sites_static", "population_10km", "population_50km"),
]
KEYS = {
    "sites_static": ["site_id"],
    "sites_yearly": ["site_id", "year"],
    "sites_weekly": ["site_id", "week_start"],
}
TOL = 1e-6
RATE_WORDS = ("inflation", "interest", "trend", "growth", "change", "balance")
# Fields whose range depends on the table (weekly vs yearly sums)
TABLE_RANGES = {
    ("sites_yearly", "free_cooling_hours"): (0, 8784),
    ("sites_yearly", "adiabatic_cooling_hours"): (0, 8784),
}


def _range(field: str, table: str = ""):
    if (table, field) in TABLE_RANGES:
        return TABLE_RANGES[(table, field)]
    if field in RANGES:
        return RANGES[field]
    if field.startswith(("population_", "n_")):
        return (0, np.inf)
    if field.endswith("_pct") and any(k in field for k in RATE_WORDS):
        return (-100, 10_000)  # rates of change can be negative (deflation, negative rates)
    return next((r for suf, r in SUFFIX_RANGES.items() if field.endswith(suf)), None)


def check_frame(table: str, df: pd.DataFrame) -> list[dict]:
    """Checks of one table (or one file of it): keys, ranges and order between fields."""
    rows = []

    def add(check, field, fail, example=None):
        rows.append(
            {
                "table": table,
                "check": check,
                "field": field,
                "n_rows": len(df),
                "n_fail": int(fail),
                "example": example,
            }
        )

    keys = [k for k in KEYS.get(table, []) if k in df]
    if keys:
        dup = df.duplicated(keys)
        add(
            "clave duplicada",
            "+".join(keys),
            dup.sum(),
            df.loc[dup, keys[0]].iloc[0] if dup.any() else None,
        )
    for col in df.columns:
        r = _range(col, table)
        if r is None or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        v = pd.to_numeric(df[col], errors="coerce")
        bad = (v < r[0] - TOL) | (v > r[1] + TOL)
        ex = None
        if bad.any() and "site_id" in df:
            ex = f"{df.loc[bad, 'site_id'].iloc[0]}={v[bad].iloc[0]:.4g}"
        add(f"rango [{r[0]}, {r[1]}]", col, bad.sum(), ex)
    for t, lo, hi in ORDER:
        if t == table and lo in df and hi in df:
            a, b = pd.to_numeric(df[lo], errors="coerce"), pd.to_numeric(df[hi], errors="coerce")
            bad = (a > b + TOL) & a.notna() & b.notna()
            ex = df.loc[bad, "site_id"].iloc[0] if bad.any() and "site_id" in df else None
            add(f"{lo} <= {hi}", f"{lo},{hi}", bad.sum(), ex)
    return rows


def run_qc(lake) -> pd.DataFrame:
    """All checks for the country of `lake`, file by file (the weekly table does not fit at
    once)."""
    rows = []
    for table in ("sites_static", "sites_yearly"):
        df = lake.read_table(table)
        if df is not None:
            rows += check_frame(table, df)
    weekly = sorted((lake.tables / "sites_weekly").glob(f"year=*/{lake.iso}-p*.parquet"))
    for f in weekly:
        rows += check_frame("sites_weekly", pd.read_parquet(f))
    rep = pd.DataFrame(rows)
    if rep.empty:
        lake.log.warning("QC: no hay tablas de %s en %s", lake.iso, lake.tables)
        return rep
    rep = rep.groupby(["table", "check", "field"], as_index=False).agg(
        n_rows=("n_rows", "sum"), n_fail=("n_fail", "sum"), example=("example", "first")
    )
    rep["pct_fail"] = (100 * rep["n_fail"] / rep["n_rows"].clip(lower=1)).round(3)
    rep = rep.sort_values(["n_fail", "table", "field"], ascending=[False, True, True])
    lake.reports.mkdir(parents=True, exist_ok=True)
    rep.to_csv(lake.reports / "qc.csv", index=False, encoding="utf-8-sig")
    bad = rep[rep["n_fail"] > 0]
    lake.log.info("QC %s: %d comprobaciones, %d con fallos", lake.iso, len(rep), len(bad))
    for r in bad.head(15).itertuples():
        lake.log.info(
            "  %-14s %-34s %-32s %9d (%.2f %%) p. ej. %s",
            r.table,
            r.check[:34],
            r.field[:32],
            r.n_fail,
            r.pct_fail,
            r.example,
        )
    lake.log.info("Informe: %s", lake.reports / "qc.csv")
    return rep
