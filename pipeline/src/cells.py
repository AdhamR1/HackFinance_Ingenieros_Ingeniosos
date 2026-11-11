"""Cell ids and paths shared by the whole pipeline.

The grid is the ELT one (ELT/dclake/grid.py): 3.5 x 3.5 km cells in the equal-area projection of
the country (ELT/config.yaml > country_profiles: EPSG:3035 for Spain, a Lambert azimuthal centred
on Japan for Japan).
    site_id = <ISO>_{floor(x / 3500)}_{floor(y / 3500)}   (x, y in metres, lower-left corner)
Nobody builds another grid: every point is mapped to a cell with `site_id_from_lonlat`.

Country: environment variable DC_COUNTRY (ESP by default), e.g. in PowerShell
    $env:DC_COUNTRY = "JPN"; python src/features.py
Spain keeps its files where they always were (data/processed/*_es_3500.parquet); any other country
writes to data/processed/<ISO>/ with its own tag (*_jp_3500.parquet), so nothing gets mixed.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

CELL_M = 3500
TAGS = {"ESP": "es", "JPN": "jp", "USA": "us"}  # file name tag of each country
ISO = os.environ.get("DC_COUNTRY", "ESP").strip().upper() or "ESP"
if ISO not in TAGS:
    raise ValueError(f"DC_COUNTRY={ISO}: los países con modelo son {', '.join(TAGS)}")
TAG = TAGS[ISO]

PIPELINE = Path(__file__).resolve().parents[1]
REPO = PIPELINE.parent
ELT_DATASET = REPO / "ELT" / "dataset"
RAW = PIPELINE / "data" / "raw"
PROCESSED = PIPELINE / "data" / "processed" / ("" if ISO == "ESP" else ISO)


def _country_crs(iso: str) -> str:
    """Equal-area projection of the ELT grid of the country (ELT/config.yaml)."""
    with open(REPO / "ELT" / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["country_profiles"][iso]["crs_equal_area"]


CRS = _country_crs(ISO)


def out_file(stem: str, ext: str = "parquet") -> Path:
    """Per-country output in PROCESSED, e.g. out_file('features') -> features_jp_3500.parquet."""
    return PROCESSED / f"{stem}_{TAG}_3500.{ext}"


def site_id_from_xy(x, y) -> np.ndarray:
    i = np.floor(np.asarray(x, dtype=float) / CELL_M).astype(np.int64)
    j = np.floor(np.asarray(y, dtype=float) / CELL_M).astype(np.int64)
    return np.array([f"{ISO}_{a}_{b}" for a, b in zip(i, j)])


def site_id_from_lonlat(lon, lat) -> np.ndarray:
    from pyproj import Transformer

    x, y = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform(
        np.asarray(lon), np.asarray(lat)
    )
    return site_id_from_xy(x, y)


def cell_index(site_id: pd.Series) -> pd.DataFrame:
    """Grid indices (i, j) and the cell centre in metres (x_m, y_m) from the site_id."""
    parts = site_id.str.split("_", expand=True)
    i, j = parts[1].astype(int), parts[2].astype(int)
    return pd.DataFrame(
        {"i": i, "j": j, "x_m": (i + 0.5) * CELL_M, "y_m": (j + 0.5) * CELL_M}, index=site_id.index
    )


def read_elt(table: str, columns=None) -> pd.DataFrame:
    """One ELT table of the country (all parts), e.g. read_elt('sites_static')."""
    files = sorted((ELT_DATASET / table).glob(f"{ISO}-p*.parquet"))
    if not files:
        raise FileNotFoundError(f"No hay archivos {ISO}-p*.parquet en {ELT_DATASET / table}")
    return pd.concat([pd.read_parquet(f, columns=columns) for f in files], ignore_index=True)


def read_grid() -> pd.DataFrame:
    """The ELT grid: site_id, lon, lat (cell centre), admin1, admin2 + grid indices."""
    g = read_elt("sites_static", columns=["site_id", "lon", "lat", "admin1", "admin2"])
    return pd.concat([g, cell_index(g["site_id"])], axis=1)
