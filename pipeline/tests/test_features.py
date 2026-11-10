"""Offline tests of the pipeline feature blocks (no downloads)."""

import zipfile

import numpy as np
import pandas as pd
import pytest
import shapely

import feat_riesgos
import feat_suelo
from cells import CELL_M, cell_index, site_id_from_xy


def test_site_id_round_trip():
    ids = site_id_from_xy([3500.0, -1.0, 7001.0], [0.0, 3499.9, -3500.0])
    assert list(ids) == ["ESP_1_0", "ESP_-1_0", "ESP_2_-1"]
    idx = cell_index(pd.Series(ids))
    assert idx["x_m"].tolist() == [1.5 * CELL_M, -0.5 * CELL_M, 2.5 * CELL_M]


def test_cover_pct_tiled_matches_direct_intersection():
    cells = pd.DataFrame({"i": [0, 1, 2, 11, 12], "j": [0, 0, 0, 0, 0]})  # 11 and 12: next tile
    boxes = shapely.box(cells.i * CELL_M, 0, (cells.i + 1) * CELL_M, CELL_M)
    river = shapely.box(0.5 * CELL_M, 0.25 * CELL_M, 11.5 * CELL_M, 0.75 * CELL_M)  # crosses tiles
    pond = shapely.Point(2.5 * CELL_M, 0.5 * CELL_M).buffer(1000)  # overlaps river
    parts = np.array([river, pond], dtype=object)
    got = feat_riesgos.cover_pct_tiled(cells, parts)
    union = shapely.union_all(parts)
    expected = [100 * shapely.area(shapely.intersection(b, union)) / CELL_M**2 for b in boxes]
    assert got == pytest.approx(expected, abs=0.01)
    assert got[4] == 0  # cell 12 is outside the river


def test_snczi_zips_skips_style_files(tmp_path, monkeypatch):
    def make(name, members):
        with zipfile.ZipFile(tmp_path / name, "w") as z:
            for m in members:
                z.writestr(m, b"x")

    make("lyr-zonadeflujopreferente.zip", ["Zona de flujo preferente.lyr"])
    make("laminas-zfp-PB.zip", ["ZFP_PenBal.shp", "ZFP_PenBal.prj"])
    make("laminasCanarias-q100.zip", ["Q100_Canarias.shp"])
    make("otra_cosa.zip", ["datos.shp"])
    monkeypatch.setattr(feat_riesgos, "RAW", tmp_path)
    found = feat_riesgos.snczi_zips()
    assert [f.name for f in found["zfp_pct"]] == ["laminas-zfp-PB.zip"]
    assert [f.name for f in found["zi_t100_pct"]] == ["laminasCanarias-q100.zip"]
    assert found["zi_t500_pct"] == []


def test_exclusions_use_risk_layers(tmp_path, monkeypatch):
    out = pd.DataFrame(
        {
            "site_id": ["a", "b", "c", "d"],
            "natura2000_pct": [0.0, 30.0, 0.0, 0.0],
            "urbano_pct": [0.0, 0.0, 0.0, 0.0],
            "industrial_pct": [0.0, 0.0, 0.0, 0.0],
            "agua_pct": [95.0, 0.0, 0.0, 0.0],
        }
    )
    risks = pd.DataFrame(
        {
            "site_id": ["a", "b", "c", "d"],
            "parque_nacional_pct": [0.0, 60.0, 15.0, 0.0],
            "zfp_pct": [0.0, 0.0, 0.0, 55.0],
            "zi_t100_pct": [0.0, 0.0, 30.0, 0.0],
        }
    )
    risks.to_parquet(tmp_path / "feat_riesgos.parquet", index=False)
    monkeypatch.setattr(feat_suelo, "PROCESSED", tmp_path)
    ex = feat_suelo.exclusions(out).set_index("site_id")
    assert ex.loc["a", "motivo_descarte"] == "agua"
    assert ex.loc["b", "motivo_descarte"] == "parque nacional"
    assert ex.loc["d", "motivo_descarte"] == "zona de flujo preferente"
    assert not ex.loc["c", "excluded"]
    assert "Parque nacional en el 15 %" in ex.loc["c", "avisos"]
    assert "Zona inundable de 100 años" in ex.loc["c", "avisos"]
    assert "Natura 2000" in ex.loc["b", "avisos"]
