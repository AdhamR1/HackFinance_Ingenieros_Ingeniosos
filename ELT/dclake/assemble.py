"""Merge staged collector outputs into the final tables defined by the dictionary.

Dataset layout: one folder per table and one file per country (and part, for the per-cell tables),
so the countries add up in the same tables:
  sites_static/ESP-p00.parquet   sites_yearly/ESP-p00.parquet   field_lineage/ESP-p00.parquet
  sites_weekly/year=2025/ESP-p00-2025.parquet    (ISO year of the week; -2025 = calendar year
  processed)
  country_daily/ESP.parquet   stations/ESP.parquet   signal_features/ESP.parquet
  country_context.parquet     (the same 8 countries whatever the run)
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from .schema import TableSpec, conform, load_schemas


def _base_keys(lake, cfg, table: str, year: int | None = None) -> pd.DataFrame | None:
    sites = lake.sites()
    p = cfg["period"]
    y0, y1 = pd.Timestamp(p["start"]).year, pd.Timestamp(p["end"]).year
    if table == "sites_static":
        return sites[["site_id"]].copy()
    if table == "sites_yearly":
        return sites[["site_id"]].merge(pd.DataFrame({"year": range(y0, y1 + 1)}), how="cross")
    if table == "country_context":
        return pd.MultiIndex.from_product(
            [cfg["countries"], range(y0, y1 + 1)], names=["country_iso3", "year"]
        ).to_frame(index=False)
    if table == "sites_daily":
        days = pd.date_range(p["start"], p["end"], freq="D")
        days = days[days.year == year]
        return pd.MultiIndex.from_product(
            [sites["site_id"].values, days], names=["site_id", "date"]
        ).to_frame(index=False)
    if table == "country_daily":
        return pd.DataFrame(
            {
                "country_iso3": cfg["project"]["country_iso3"],
                "date": pd.date_range(p["start"], p["end"], freq="D"),
            }
        )
    return None  # stations, signal_features: union of staged keys


def _norm_keys(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    df = df.copy()
    for k in keys:
        if k == "date":
            df[k] = pd.to_datetime(df[k]).dt.normalize()
        elif k == "year":
            df[k] = pd.to_numeric(df[k]).astype(int)
        else:
            df[k] = df[k].astype(str)
    return df


def merge_staged(
    lake,
    cfg,
    spec: TableSpec,
    collectors: list[str],
    year: int | None = None,
    provenance: dict | None = None,
) -> pd.DataFrame:
    """Combine all staged frames for one table. Earlier collectors win on conflicts."""
    keys = spec.keys
    frames = []
    for c in collectors:
        df = lake.read_stage(c, spec.name, year if spec.partition_by_year else None)
        if df is not None and len(df):
            frames.append((c, _norm_keys(df, keys)))
    base = _base_keys(lake, cfg, spec.name, year)
    if base is None:
        if not frames:
            return pd.DataFrame(columns=spec.columns)
        idx = pd.concat([f[keys] for _, f in frames]).drop_duplicates()
        base = idx
    base = _norm_keys(base, keys).drop_duplicates(keys).set_index(keys)
    for c, df in frames:
        d = df.drop_duplicates(keys, keep="last").set_index(keys)
        cols = [col for col in d.columns if col in spec.fields]
        d = d[cols].reindex(base.index)  # one alignment per collector, not per column
        for col in cols:
            new = d[col]
            if col in base.columns:
                before = base[col].notna().sum()
                if before < len(base):  # earlier collectors win; only fill their gaps
                    base[col] = base[col].where(base[col].notna(), new)
                gained = base[col].notna().sum() - before
            else:
                base[col] = new
                gained = new.notna().sum()
            if provenance is not None and gained > 0:
                provenance.setdefault(col, [])
                if c not in provenance[col]:
                    provenance[col].append(c)
    return base.reset_index()


def clear_outputs(lake) -> int:
    """Remove this country's per-cell files from the dataset (before rebuilding all its parts)."""
    files = list(lake.tables.glob(f"*/{lake.iso}-p*.parquet")) + list(
        lake.tables.glob(f"sites_weekly/year=*/{lake.iso}-p*.parquet")
    )
    # per-country files of an older layout (stations and signals are now per part as well)
    files += [lake.tables / t / f"{lake.iso}.parquet" for t in ("stations", "signal_features")]
    files = [f for f in files if f.exists()]
    for f in files:
        f.unlink()
    return len(files)


def _out_path(lake, name: str):
    if name == "country_context":
        return lake.tables / "country_context.parquet"
    d = lake.tables / name
    d.mkdir(parents=True, exist_ok=True)
    per_part = name in (
        "sites_static",
        "sites_yearly",
        "field_lineage",
        "stations",
        "signal_features",
    )
    return d / f"{lake.out_name if per_part else lake.iso}.parquet"


def assemble(lake, cfg, collectors: list[str] | None = None):
    specs = load_schemas(cfg.dictionary_path)
    collectors = collectors or lake.staged_collectors()
    log = lake.log
    lineage_rows = []
    lineage_info = {c: lake.read_lineage(c) for c in collectors}
    now = datetime.now(UTC)

    def add_lineage(spec, df, prov):
        for f in spec.fields:
            if f in spec.keys:
                continue
            cov = float(df[f].notna().mean() * 100) if f in df and len(df) else 0.0
            srcs = prov.get(f, [])
            info = {}
            for c in srcs:
                li = lineage_info.get(c, {})
                info = li.get(f"{spec.name}.{f}") or li.get("*", {})
                if info:
                    break
            lineage_rows.append(
                {
                    "table": spec.name,
                    "field": f,
                    "collector": ",".join(srcs) or None,
                    "coverage_pct": cov,
                    "n_rows": len(df),
                    **info,
                }
            )

    for name in (
        "sites_static",
        "sites_yearly",
        "country_context",
        "country_daily",
        "stations",
        "signal_features",
    ):
        spec = specs[name]
        prov = {}
        df = merge_staged(lake, cfg, spec, collectors, provenance=prov)
        df = conform(df, spec, log, strict=False)
        df.to_parquet(_out_path(lake, name), index=False)
        add_lineage(spec, df, prov)
        log.info("Tabla %-16s %8d filas x %3d columnas", name, len(df), df.shape[1])

    # sites_weekly (what goes to the data lake): built from the merged daily data, one calendar
    # year at a time.
    # The week that straddles New Year is completed with the first days of the next year (carry).
    from .weekly import aggregate, iso_year, week_start, weekly_rules

    dspec, wspec = specs["sites_daily"], specs["sites_weekly"]
    rules = weekly_rules(wspec)
    for old in lake.tables.glob(
        f"sites_weekly/year=*/{lake.out_name}-*.parquet"
    ):  # rebuilt from staging
        old.unlink()
    p = cfg["period"]
    years = list(range(pd.Timestamp(p["start"]).year, pd.Timestamp(p["end"]).year + 1))
    prov, n_total, nn, carry = {}, 0, {}, None
    for y in years:
        df = conform(
            merge_staged(lake, cfg, dspec, collectors, year=y, provenance=prov),
            dspec,
            log,
            strict=False,
        )
        if carry is not None:
            df = pd.concat([carry, df], ignore_index=True)
            carry = None
        ws = week_start(df["date"])
        last = ws.max()
        if y != years[-1] and last + pd.Timedelta(days=6) > pd.Timestamp(f"{y}-12-31"):
            hold = (ws == last).to_numpy()
            carry, df = df[hold], df[~hold]
        w = conform(aggregate(df, rules), wspec, log, strict=False)
        for iy, part in w.groupby(iso_year(w["week_start"])):
            out = lake.tables / "sites_weekly" / f"year={iy}"
            out.mkdir(parents=True, exist_ok=True)
            part.to_parquet(out / f"{lake.out_name}-{y}.parquet", index=False)
        n_total += len(w)
        for f in wspec.fields:
            nn[f] = nn.get(f, 0) + int(w[f].notna().sum())
    src_of = {wf: src for wf, src, _ in rules}
    for f in wspec.fields:
        if f in wspec.keys:
            continue
        srcs = prov.get(src_of.get(f, ""), [])
        info = {}
        for c in srcs:
            li = lineage_info.get(c, {})
            info = dict(li.get(f"sites_daily.{src_of[f]}") or li.get("*", {}))
            if info:
                break
        how = wspec.meta.get(f, {}).get("Agregación", "")
        info["notes"] = "; ".join(
            x for x in (info.get("notes"), f"Semanal ISO: {how} de {src_of.get(f, 'date')}") if x
        )
        lineage_rows.append(
            {
                "table": "sites_weekly",
                "field": f,
                "collector": ",".join(srcs) or None,
                "coverage_pct": 100 * nn.get(f, 0) / max(n_total, 1),
                "n_rows": n_total,
                **info,
            }
        )
    log.info("Tabla %-16s %8d filas (particionada por año ISO)", "sites_weekly", n_total)

    lin = pd.DataFrame(lineage_rows)
    lin["reference_year"] = np.where(
        lin["table"].isin(["sites_weekly", "sites_yearly", "country_context", "country_daily"]),
        np.nan,
        now.year,
    )
    lin = conform(lin, specs["field_lineage"], log, strict=False)
    lin.to_parquet(_out_path(lake, "field_lineage"), index=False)
    return lin


def assemble_safely(lake, cfg, parts: list[int], replace_all: bool = True) -> None:
    """Assemble into a cache folder, and only then replace the country's files in the dataset.

    If the run is interrupted (closed session, sleep, error), the dataset keeps its previous files
    instead of a half-written country.
    """
    import copy
    import os

    work = copy.copy(lake)
    work.tables = lake.root / "assemble_tmp"
    shutil.rmtree(work.tables, ignore_errors=True)
    work.tables.mkdir(parents=True, exist_ok=True)  # OneDrive may keep the empty folders
    for old in work.tables.rglob("*.parquet"):  # never mix in files of an interrupted run
        old.unlink()
    for k in parts:
        assemble(work.with_part(k), cfg)
    if replace_all:
        clear_outputs(lake)
    for f in sorted(work.tables.rglob("*.parquet")):
        dest = lake.tables / f.relative_to(work.tables)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(f, dest)
    shutil.rmtree(work.tables, ignore_errors=True)
    lake.log.info("Dataset de %s actualizado en %s", lake.iso, lake.tables)
