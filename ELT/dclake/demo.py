"""Offline demo: synthetic inputs run through the real grid, derive, assemble and report code.

It checks the installation and the pipeline plumbing without any network access.
Everything it writes goes to data_lake_demo/ and is flagged is_synthetic.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal


def synthetic_noise(f0: float, fs: float = 100.0, minutes: int = 30, seed: int = 0):
    """Three components where horizontals resonate at f0 -> H/V peak at f0."""
    rng = np.random.default_rng(seed)
    n = int(minutes * 60 * fs)
    b, a = signal.iirpeak(f0, Q=2.5, fs=fs)
    z = rng.standard_normal(n)
    hn = signal.lfilter(b, a, rng.standard_normal(n)) * 6 + rng.standard_normal(n)
    he = signal.lfilter(b, a, rng.standard_normal(n)) * 6 + rng.standard_normal(n)
    return z * 1e-7, hn * 1e-7, he * 1e-7


def run_demo(root: Path):
    import geopandas as gpd
    from shapely.geometry import box

    from . import geo, hv
    from .assemble import assemble
    from .collectors import REGISTRY
    from .collectors.climate import hourly_to_daily
    from .collectors.derived import DerivedCollector
    from .collectors.hazards import daily_counts
    from .config import load_config
    from .grid import run_grid
    from .lake import Lake
    from .report import coverage_report

    cfg = load_config(root / "config.yaml", overrides={   # demo output stays in the (ignored) cache
        "paths.lake_dir": ".cache/demo",
        "period.start": "2024-01-01", "period.end": "2025-12-31",
        "sampling.n_cells": 40, "sampling.n_positive_max": 5, "sampling.n_focus": 10})
    lake = Lake(cfg.lake)
    log = lake.log
    log.info("DEMO OFFLINE con datos sintéticos en %s", lake.root)
    rng = np.random.default_rng(1)

    # --- grid on a fake territory (two regions)
    west = box(-4.6, 39.6, -3.6, 41.0)
    east = box(-3.6, 39.6, -2.6, 41.0)
    adm1 = gpd.GeoDataFrame({"shapeName": ["Comunidad de Madrid", "Castilla-La Mancha"]}, geometry=[west, east], crs=4326)
    adm = {"ADM0": gpd.GeoDataFrame(geometry=[west.union(east)], crs=4326).to_crs(geo.EQUAL_AREA),
           "ADM1": adm1.to_crs(geo.EQUAL_AREA), "ADM2": adm1.to_crs(geo.EQUAL_AREA)}
    dcs = geo.points_from_lonlat(pd.DataFrame({"lon": [-3.60, -3.65, -3.55, -3.70], "lat": [40.45, 40.40, 40.50, 40.35]}))
    sites = run_grid(lake, cfg, adm=adm, dcs=dcs)

    syn = {"is_synthetic": True, "source": "DEMO sintético", "imputation_method": "sintético"}

    # --- climate: synthetic hourly ERA5-like series through the real daily code
    hours = pd.date_range(cfg["period"]["start"], pd.Timestamp(cfg["period"]["end"]) + pd.Timedelta(days=1), freq="h")
    doy, hod = hours.dayofyear.values, hours.hour.values
    era_key = (hours - pd.Timedelta(hours=1)).normalize()   # ERA5-Land: 01 UTC..00 UTC next day

    def era5_accumulate(amounts):
        return pd.Series(amounts, index=hours).groupby(era_key).cumsum().values

    daily_all = []
    for sid, lat in zip(sites["site_id"], sites["lat"]):
        t = 288 + 10 * np.sin(2 * np.pi * (doy - 110) / 365) + 6 * np.sin(2 * np.pi * (hod - 9) / 24) - (lat - 40) * 2
        rain = rng.gamma(0.05, 2e-3, len(hours))                      # m per hour
        sun = np.clip(np.sin(np.pi * (hod - 6) / 12), 0, None) * 2.5e6  # J/m2 per hour
        h = pd.DataFrame({"t2m": t + rng.normal(0, 1, len(hours)), "d2m": t - 6, "u10": rng.normal(2, 1, len(hours)),
                          "v10": rng.normal(1, 1, len(hours)), "tp": era5_accumulate(rain), "sf": 0.0,
                          "ssrd": era5_accumulate(sun), "swvl1": 0.25}, index=hours)
        d = hourly_to_daily(h, cfg["climate"])
        d.insert(0, "site_id", sid)
        daily_all.append(d)
    daily_all = pd.concat(daily_all, ignore_index=True)
    for y, g in daily_all.groupby(pd.to_datetime(daily_all["date"]).dt.year):
        if y <= pd.Timestamp(cfg["period"]["end"]).year:
            lake.write_stage("era5land", "sites_daily", g, year=int(y))
    lake.write_lineage("era5land", {f"sites_daily.{f}": syn for f in ["t2m_mean_c", "t2m_max_c", "precip_mm", "cdd_18"]})

    # --- earthquakes through the real daily_counts
    days = pd.date_range(cfg["period"]["start"], cfg["period"]["end"], freq="D")
    ev = pd.DataFrame({"lon": rng.uniform(-5, -2, 60), "lat": rng.uniform(39, 41.5, 60),
                       "mag": rng.uniform(1.5, 4, 60), "date": rng.choice(days, 60)})
    for y in sorted(set(days.year)):
        dc = daily_counts(sites, ev[ev["date"].dt.year == y], 100, days[days.year == y], "mag",
                          "eq_count_100km", "eq_max_mag_100km", "max")
        lake.write_stage("earthquakes", "sites_daily", dc, year=int(y))

    # --- electricity (country_daily)
    price = 60 + 20 * np.sin(2 * np.pi * days.dayofyear / 365) + rng.normal(0, 8, len(days))
    cd = pd.DataFrame({"country_iso3": "ESP", "date": days, "omie_price_mean_eur_mwh": price,
                       "omie_price_max_eur_mwh": price + 20, "omie_price_min_eur_mwh": price - 20, "eur_usd": 1.08,
                       "gen_total_gwh": 700 + rng.normal(0, 30, len(days)),
                       "renewable_share_pct": 50 + rng.normal(0, 10, len(days)),
                       "carbon_intensity_gco2_kwh": 120 + rng.normal(0, 20, len(days))})
    cd["omie_price_mean_usd_mwh"] = cd["omie_price_mean_eur_mwh"] * cd["eur_usd"]
    lake.write_stage("electricity_es", "country_daily", cd)

    # --- country context
    years = range(2024, 2026)
    cc = pd.MultiIndex.from_product([cfg["countries"], years], names=["country_iso3", "year"]).to_frame(index=False)
    cc["rule_of_law_wgi"] = rng.normal(0.5, 0.8, len(cc))
    cc["internet_users_pct"] = rng.uniform(40, 98, len(cc))
    lake.write_stage("worldbank", "country_context", cc)

    # --- a few static OSM-like fields
    lake.write_stage("osm", "sites_static", pd.DataFrame({
        "site_id": sites["site_id"], "dist_substation_km": rng.gamma(2, 3, len(sites)),
        "dist_highway_km": rng.gamma(2, 4, len(sites)), "dist_railway_km": rng.gamma(2, 5, len(sites))}))
    lake.write_stage("manual_layers", "sites_static", pd.DataFrame({
        "site_id": sites["site_id"], "vs30_ms": rng.uniform(150, 900, len(sites))}))

    # --- seismic: synthetic stations with known f0 through the real H/V code
    true_f0 = {"XX.STA1": 1.5, "XX.STA2": 3.0, "XX.STA3": 6.0}
    st = pd.DataFrame({"station_id": list(true_f0), "network_code": "XX", "lat": [40.0, 40.5, 40.9],
                       "lon": [-4.2, -3.5, -2.9], "max_sampling_rate_hz": 100.0, "n_components": 3})
    recs = []
    for i, (sid, f0) in enumerate(true_f0.items()):
        z, n, e = synthetic_noise(f0, seed=i)
        r = hv.hv_ratio(z, n, e, 100.0)
        sf = hv.spectral_features(z, 100.0, vel_units=True)
        sf.pop("_f"); sf.pop("_pacc")
        recs.append({"record_id": f"{sid}_20240115_0100", "station_id": sid, "record_hours": 0.5,
                     **{k: v for k, v in r.items() if k != "hv_freqs"}, **sf})
        log.info("  H/V sintético %s: f0 real %.2f Hz -> estimada %.2f Hz (A0 %.1f, fiable %s)",
                 sid, f0, r["hv_f0_hz"], r["hv_a0"], r["hv_sesame_reliable"])
    lake.write_stage("seismic", "stations", st)
    lake.write_stage("seismic", "signal_features", pd.DataFrame(recs))
    stg = geo.points_from_lonlat(st)
    nn = geo.nearest(geo.site_points(sites), stg, ["station_id"])
    lake.write_stage("seismic", "sites_static", pd.DataFrame({
        "site_id": sites["site_id"], "nearest_station_id": nn["station_id"], "dist_station_km": nn["dist_km"],
        "hv_f0_hz": nn["station_id"].map(true_f0)}))

    for c in lake.staged_collectors():   # everything in the demo is synthetic
        if c != "grid":
            lake.write_lineage(c, {"*": syn})

    # --- real derive, assemble and report
    DerivedCollector(lake, cfg)(sites)
    assemble(lake, cfg)
    rep = coverage_report(lake, cfg, REGISTRY)
    log.info("DEMO terminada. Tablas en %s", lake.tables)
    return rep
