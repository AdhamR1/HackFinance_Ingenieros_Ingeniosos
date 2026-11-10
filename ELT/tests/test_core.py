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
    amount = np.full(len(hours), 0.001)  # 1 mm every hour
    key = (hours - pd.Timedelta(hours=1)).normalize()
    acc = pd.Series(amount, index=hours).groupby(key).cumsum()
    d = daily_total(acc) * 1000
    assert np.allclose(d.values, 24)
    plain = daily_total(pd.Series(amount, index=hours)) * 1000
    assert np.isclose(plain.loc["2024-01-02"], 24)


def test_psychrometrics():
    assert np.isclose(rh_from_dewpoint(20.0, 20.0), 100)
    assert abs(wetbulb_stull(20.0, 50.0) - 13.7) < 0.3  # reference value from Stull (2011)


def test_omie_parser():
    txt = "MARGINALPDBC;\n2024;01;01;1;63.33;63.33;\n2024;01;01;2;50.10;50.10;\n*\n"
    assert parse_omie_marginal(txt) == [63.33, 50.10]


def test_weekly_aggregation():
    from dclake.weekly import aggregate, iso_year, weekly_rules

    spec = load_schemas(DICT)["sites_weekly"]
    rules = weekly_rules(spec)
    days = pd.date_range("2025-12-22", "2026-01-04", freq="D")  # two ISO weeks, across New Year
    d = pd.DataFrame(
        {
            "site_id": "a",
            "date": days,
            "t2m_mean_c": np.arange(14.0),
            "precip_mm": 1.0,
            "frost_flag": pd.array([True] * 3 + [False] * 11, dtype="boolean"),
            "ssrd_kwh_m2": np.nan,
        }
    )
    w = aggregate(d, rules)
    assert list(w["week_start"].dt.strftime("%Y-%m-%d")) == ["2025-12-22", "2025-12-29"]
    assert list(iso_year(w["week_start"])) == [2025, 2026]  # 29 Dec 2025 belongs to ISO 2026
    assert list(w["n_days_week"]) == [7, 7] and list(w["precip_mm"]) == [7.0, 7.0]
    assert w.loc[0, "t2m_mean_c"] == 3.0 and list(w["frost_days"]) == [3, 0]
    assert w["ssrd_kwh_m2"].isna().all()  # no data -> null, not 0


def test_schema_covers_dictionary():
    specs = load_schemas(DICT)
    dic = pd.read_excel(DICT, sheet_name="Diccionario")

    n_fields = sum(len([f for f in s.fields if f not in s.keys]) for s in specs.values())
    assert n_fields >= len(dic) - 1
    assert "hv_f0_hz" in specs["signal_features"].fields
    assert "t2m_max_c" in specs["sites_daily"].fields
    df = conform(
        pd.DataFrame({"site_id": ["a"], "elevation_m": ["12.5"], "extra": [1]}),
        specs["sites_static"],
    )
    assert df.loc[0, "elevation_m"] == 12.5 and "extra" not in df


def test_country_profiles_and_parts():
    from dclake.collectors.gridclimate import NASAPowerCollector
    from dclake.config import load_config
    from dclake.geo import bbox_union
    from dclake.grid import assign_parts, in_region, norm

    root = Path(__file__).resolve().parents[1]
    usa = load_config(root / "config.yaml", overrides={"project.country_iso3": "usa"})
    assert usa.iso == "USA" and usa["project"]["crs_equal_area"] == "EPSG:5070"
    assert usa.lake.name == "USA" and "conus" in usa["bboxes"]
    assert bbox_union(usa, 1)[0] == pytest.approx(-125.9)

    # earthquake counts: one threshold for every country, above the floor of the cached download
    from dclake.collectors.hazards import count_min_magnitude

    for iso in ("esp", "jpn", "usa"):
        c = load_config(root / "config.yaml", overrides={"project.country_iso3": iso})
        assert count_min_magnitude(c) == 2.0

    g = pd.DataFrame({"x": np.random.default_rng(0).uniform(0, 1e6, 1001)})
    parts = assign_parts(g, 250)
    assert parts.max() == 4 and np.bincount(parts).max() <= 250
    assert (pd.Series(parts).groupby(pd.cut(g["x"], 5)).nunique() <= 2).all()  # strips by x
    assert (assign_parts(g, 5000) == 0).all()

    assert in_region("Comunidad de Madrid", norm("madrid"))
    assert in_region("Virginia", norm("=virginia")) and not in_region(
        "West Virginia", norm("=virginia")
    )

    boxes = NASAPowerCollector.boxes(np.array([123.1, 139.7, 141.3]), np.array([24.3, 35.7, 43.1]))
    assert boxes == [(123.0, 24.0), (133.0, 34.0)]  # only boxes with cells; each cell in one box


def test_daily_counts_matches_brute_force():
    from dclake import geo
    from dclake.collectors.hazards import daily_counts

    rng = np.random.default_rng(1)
    geo.set_equal_area("EPSG:3035")
    sites = pd.DataFrame(
        {
            "site_id": [f"c{i}" for i in range(60)],
            "lon": rng.uniform(-4, -2, 60),
            "lat": rng.uniform(39, 41, 60),
        }
    )
    xy = geo.xy(geo.points_from_lonlat(sites))
    sites["x"], sites["y"] = xy[:, 0], xy[:, 1]
    days = pd.date_range("2025-01-01", "2025-01-10")
    ev = pd.DataFrame(
        {
            "lon": rng.uniform(-4, -2, 40),
            "lat": rng.uniform(39, 41, 40),
            "date": rng.choice(days, 40),
            "mag": rng.uniform(1.5, 4, 40),
        }
    )
    d = daily_counts(sites, ev, 50, days, "mag", "n", "mx", "max").set_index(["site_id", "date"])
    exy = geo.xy(geo.points_from_lonlat(ev))
    for i in (0, 17, 59):
        near = np.hypot(exy[:, 0] - xy[i, 0], exy[:, 1] - xy[i, 1]) <= 50_000
        for day in days[:4]:
            sel = near & (ev["date"].values == day)
            got = d.loc[(f"c{i}", day)]
            assert got["n"] == sel.sum()
            expected = ev["mag"].values[sel].max() if sel.any() else np.nan
            assert np.isclose(got["mx"], expected, equal_nan=True)


def test_collectors_declare_fields_in_their_dictionary_table(tmp_path):
    """A field staged in the wrong table is dropped silently by conform: catch it here."""
    from dclake.collectors import REGISTRY
    from dclake.config import load_config
    from dclake.lake import Lake

    cfg = load_config(Path(__file__).resolve().parents[1] / "config.yaml")
    specs = load_schemas(cfg.dictionary_path)
    lake = Lake(tmp_path, tmp_path / "tables")
    wrong = [
        (cls.name, table, field)
        for cls in REGISTRY
        for table, fields in cls(lake, cfg).declared_fields().items()
        for field in fields
        if table not in specs or field not in specs[table].fields
    ]
    assert not wrong, wrong
