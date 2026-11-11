"""Quality checks: they must catch duplicated keys, impossible values and inconsistent pairs."""

import numpy as np
import pandas as pd

from dclake.qc import check_frame


def _fails(rows):
    return {(r["check"], r["field"]): r["n_fail"] for r in rows if r["n_fail"]}


def test_qc_catches_bad_static_rows():
    df = pd.DataFrame(
        {
            "site_id": ["a", "b", "b"],
            "natura2000_pct": [10.0, 120.0, np.nan],  # 120 % is impossible, NaN is fine
            "dist_coast_km": [5.0, -1.0, 3.0],
            "flood_depth_rp10_m": [0.5, 0.0, 0.0],
            "flood_depth_rp100_m": [0.2, 1.0, 0.0],  # site a: deeper at 10 years than at 100
            "population_10km": [100.0, 50.0, 10.0],
            "population_50km": [1000.0, 40.0, 10.0],  # site b: fewer people within 50 km
        }
    )
    fails = _fails(check_frame("sites_static", df))
    assert fails[("clave duplicada", "site_id")] == 1
    assert fails[("rango [0, 100]", "natura2000_pct")] == 1
    assert fails[("rango [0, 20000]", "dist_coast_km")] == 1
    assert (
        fails[
            ("flood_depth_rp10_m <= flood_depth_rp100_m", "flood_depth_rp10_m,flood_depth_rp100_m")
        ]
        == 1
    )
    assert fails[("population_10km <= population_50km", "population_10km,population_50km")] == 1


def test_qc_uses_table_specific_ranges():
    yearly = pd.DataFrame({"site_id": ["a"], "year": [2025], "free_cooling_hours": [5000.0]})
    weekly = pd.DataFrame(
        {
            "site_id": ["a"],
            "week_start": ["2025-01-06"],
            "free_cooling_hours": [5000.0],
            "t2m_min_c": [5.0],
            "t2m_mean_c": [4.0],
        }
    )
    assert not _fails(check_frame("sites_yearly", yearly))  # an annual sum: fine
    fails = _fails(check_frame("sites_weekly", weekly))
    assert ("rango [0, 168]", "free_cooling_hours") in fails  # more hours than a week has
    assert ("t2m_min_c <= t2m_mean_c", "t2m_min_c,t2m_mean_c") in fails


def test_qc_allows_negative_rates():
    yearly = pd.DataFrame({"site_id": ["a"], "year": [2015], "inflation_pct": [-0.5]})
    assert not _fails(check_frame("sites_yearly", yearly))  # deflation is real
