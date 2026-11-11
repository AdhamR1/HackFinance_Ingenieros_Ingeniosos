"""Daily -> weekly (ISO weeks, Monday start) following the 'Variables semanales' sheet of the
dictionary."""

from __future__ import annotations

import pandas as pd

AGG = {"media": "mean", "máximo": "max", "mínimo": "min", "suma": "sum", "días": "sum"}


def weekly_rules(spec) -> list[tuple[str, str, str]]:
    """(weekly field, daily field, pandas aggregation) from the dictionary rows of sites_weekly."""
    out = []
    for f, m in spec.meta.items():
        agg = AGG.get(str(m.get("Agregación", "")).strip())
        src = str(m.get("Desde (campo diario)", "")).strip()
        if agg and src:
            out.append((f, src, agg))
    return out


def week_start(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates).dt.normalize()
    return d - pd.to_timedelta(d.dt.day_of_week, unit="D")


def iso_year(ws: pd.Series) -> pd.Series:
    """ISO year of a week = calendar year of its Thursday."""
    return (ws + pd.Timedelta(days=3)).dt.year


def aggregate(daily: pd.DataFrame, rules) -> pd.DataFrame:
    """One row per site_id and ISO week. Sums of a week with no data stay null (not zero)."""
    d = daily.copy()
    d["week_start"] = week_start(d["date"])
    d["site_id"] = d["site_id"].astype("category")
    g = d.groupby(["site_id", "week_start"], observed=True, sort=True)
    out = {"n_days_week": g.size()}
    for wf, src, how in rules:
        if src not in d:
            continue
        col = pd.to_numeric(
            d[src].astype("Float64") if d[src].dtype == "boolean" else d[src], errors="coerce"
        )
        gc = col.groupby([d["site_id"], d["week_start"]], observed=True, sort=True)
        val = gc.agg(how)
        if how == "sum":
            val = val.where(gc.count() > 0)
        out[wf] = val
    w = pd.DataFrame(out).reset_index()
    w["site_id"] = w["site_id"].astype(str)
    return w
