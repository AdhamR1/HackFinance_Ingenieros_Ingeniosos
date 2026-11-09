"""Offline tests: run with  python -m pytest -q"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dclake import hv
from dclake.collectors.climate import daily_total, rh_from_dewpoint, wetbulb_stull
from dclake.collectors.electricity import parse_omie_marginal
from dclake.demo import synthetic_noise
from dclake.schema import conform, load_schemas

ROOT = Path(__file__).resolve().parents[1]
DICT = ROOT / "data_dictionary" / "diccionario_datos_datacenters.xlsx"


@pytest.mark.parametrize("f0", [1.0, 2.5, 8.0])
def test_hv_recovers_resonance(f0):
    z, n, e = synthetic_noise(f0, minutes=20, seed=3)
    r = hv.hv_ratio(z, n, e, 100.0)
    assert abs(np.log(r["hv_f0_hz"] / f0)) < 0.1
    assert r["hv_a0"] > 2


def test_daily_total_accumulated_and_plain():
    hours = pd.date_range("2024-01-01 01:00", "2024-01-04 00:00", freq="h")
    amount = np.full(len(hours), 0.001)                     # 1 mm every hour
    key = (hours - pd.Timedelta(hours=1)).normalize()
    acc = pd.Series(amount, index=hours).groupby(key).cumsum()
    d = daily_total(acc) * 1000
    assert np.allclose(d.values, 24)
    plain = daily_total(pd.Series(amount, index=hours)) * 1000
    assert np.isclose(plain.loc["2024-01-02"], 24)


def test_psychrometrics():
    assert np.isclose(rh_from_dewpoint(20.0, 20.0), 100)
    assert abs(wetbulb_stull(20.0, 50.0) - 13.7) < 0.3      # reference value from Stull (2011)


def test_omie_parser():
    txt = "MARGINALPDBC;\n2024;01;01;1;63.33;63.33;\n2024;01;01;2;50.10;50.10;\n*\n"
    assert parse_omie_marginal(txt) == [63.33, 50.10]


def test_weekly_aggregation():
    from dclake.weekly import aggregate, iso_year, weekly_rules
    spec = load_schemas(DICT)["sites_weekly"]
    rules = weekly_rules(spec)
    days = pd.date_range("2025-12-22", "2026-01-04", freq="D")          # two ISO weeks, across New Year
    d = pd.DataFrame({"site_id": "a", "date": days, "t2m_mean_c": np.arange(14.0), "precip_mm": 1.0,
                      "frost_flag": pd.array([True] * 3 + [False] * 11, dtype="boolean"),
                      "ssrd_kwh_m2": np.nan})
    w = aggregate(d, rules)
    assert list(w["week_start"].dt.strftime("%Y-%m-%d")) == ["2025-12-22", "2025-12-29"]
    assert list(iso_year(w["week_start"])) == [2025, 2026]                 # 29 Dec 2025 belongs to ISO 2026
    assert list(w["n_days_week"]) == [7, 7] and list(w["precip_mm"]) == [7.0, 7.0]
    assert w.loc[0, "t2m_mean_c"] == 3.0 and list(w["frost_days"]) == [3, 0]
    assert w["ssrd_kwh_m2"].isna().all()                                   # no data -> null, not 0


def test_schema_covers_dictionary():
    specs = load_schemas(DICT)
    dic = pd.read_excel(DICT, sheet_name="Diccionario")

    n_fields = sum(len([f for f in s.fields if f not in s.keys]) for s in specs.values())
    assert n_fields >= len(dic) - 1
    assert "hv_f0_hz" in specs["signal_features"].fields
    assert "t2m_max_c" in specs["sites_daily"].fields
    df = conform(pd.DataFrame({"site_id": ["a"], "elevation_m": ["12.5"], "extra": [1]}), specs["sites_static"])
    assert df.loc[0, "elevation_m"] == 12.5 and "extra" not in df
