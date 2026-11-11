"""Offline tests of the multi-country grid helpers and the reference layers (no downloads)."""

import geopandas as gpd
import numpy as np
import pytest
import shapely

from dclake import geo
from dclake.autolayers import layer_path
from dclake.collectors.rasters import _sample_raster
from dclake.grid import build_grid, country_land, polygons_only


def test_polygons_only_drops_lines_and_points():
    mixed = shapely.GeometryCollection(
        [
            shapely.box(0, 0, 1, 1),
            shapely.LineString([(2, 2), (3, 3)]),
            shapely.Point(5, 5),
        ]
    )
    out = polygons_only(mixed)
    assert out.geom_type in ("Polygon", "MultiPolygon")
    assert out.area == pytest.approx(1.0)


def test_country_land_excludes_regions():
    adm1 = gpd.GeoDataFrame(
        {"shapeName": ["Mainland", "Alaska"]},
        geometry=[shapely.box(0, 0, 10, 10), shapely.box(20, 0, 30, 10)],
        crs="EPSG:3035",
    )
    adm0 = gpd.GeoDataFrame(geometry=[shapely.union_all(adm1.geometry.values)], crs="EPSG:3035")
    land, adm = country_land({"ADM0": adm0, "ADM1": adm1, "ADM2": adm1}, ["alaska"])
    assert land.geometry.iloc[0].area == pytest.approx(100.0)
    assert list(adm["ADM1"]["shapeName"]) == ["Mainland"]


def test_build_grid_keeps_land_cells():
    geo.set_equal_area("EPSG:3035")
    land = gpd.GeoDataFrame(
        geometry=[shapely.box(2_999_500, 2_002_000, 3_010_000, 2_009_000)], crs="EPSG:3035"
    )
    g = build_grid(land, cell_m=3500, min_land=0.5, iso="ESP")
    assert len(g) == 6  # 3 x 2 cells of 3.5 km
    assert g["site_id"].str.startswith("ESP_").all()
    assert g["land_fraction"].min() == pytest.approx(1.0)


def test_sample_raster_reads_a_folder_of_tiles(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    folder = tmp_path / "tiles"
    folder.mkdir()
    for k, (west, value) in enumerate(((0.0, 1.0), (10.0, 2.0))):  # two 10 x 10 deg tiles
        data = np.full((10, 10), value, dtype="float32")
        with rasterio.open(
            folder / f"t{k}.tif",
            "w",
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            nodata=-9999,
            transform=from_origin(west, 50.0, 1.0, 1.0),
        ) as ds:
            ds.write(data, 1)
    v = _sample_raster(str(folder), np.array([5.0, 15.0, 25.0]), np.array([45.0, 45.0, 45.0]))
    assert v[:2].tolist() == [1.0, 2.0]
    assert np.isnan(v[2])  # outside every tile


def test_layer_path_formats_the_country():
    class FakeLake:
        manual = __import__("pathlib").Path("manual")

    cfg = {"project": {"country_iso3": "JPN", "iso2": "JP"}}
    p = layer_path(FakeLake(), cfg, {"file": "wdpa/WDPA_{iso3}.gpkg"})
    assert p.as_posix() == "manual/wdpa/WDPA_JPN.gpkg"


def test_zonal_sum_counts_the_disk(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    from dclake.collectors.rasters import _zonal_sum

    path = tmp_path / "pop.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=200,
        width=200,
        count=1,
        dtype="float32",
        crs="EPSG:3035",
        transform=from_origin(4_255_000, 3_310_000, 1000, 1000),
    ) as ds:
        ds.write(np.ones((200, 200), dtype="float32"), 1)  # 1 person per km2
    lon, lat = 10.5, 52.0  # a point near the raster centre, in lon/lat
    import pyproj

    x, y = pyproj.Transformer.from_crs(4326, 3035, always_xy=True).transform(lon, lat)
    assert 4_255_000 < x < 4_455_000 and 3_110_000 < y < 3_310_000
    total = _zonal_sum(str(path), np.array([lon]), np.array([lat]), 10)[0]
    assert total == pytest.approx(np.pi * 10**2, rel=0.05)
    outside = _zonal_sum(str(path), np.array([-30.0]), np.array([10.0]), 10)[0]
    assert np.isnan(outside)
