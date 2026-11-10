"""Cell ids and paths shared by the whole pipeline.

The grid is the ELT one (ELT/dclake/grid.py): EPSG:3035, 3.5 x 3.5 km cells.
    site_id = ESP_{floor(x / 3500)}_{floor(y / 3500)}   (x, y in metres, lower-left corner)
Nobody builds another grid: every point is mapped to a cell with `site_id_from_lonlat`.
"""

from pathlib import Path

import numpy as np
import pandas as pd

CELL_M = 3500
CRS = "EPSG:3035"
ISO = "ESP"

PIPELINE = Path(__file__).resolve().parents[1]
REPO = PIPELINE.parent
ELT_DATASET = REPO / "ELT" / "dataset"
RAW = PIPELINE / "data" / "raw"
PROCESSED = PIPELINE / "data" / "processed"


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
    """One ELT table for Spain (all parts), e.g. read_elt('sites_static')."""
    files = sorted((ELT_DATASET / table).glob(f"{ISO}-p*.parquet"))
    if not files:
        raise FileNotFoundError(f"No hay archivos {ISO}-p*.parquet en {ELT_DATASET / table}")
    return pd.concat([pd.read_parquet(f, columns=columns) for f in files], ignore_index=True)


def read_grid() -> pd.DataFrame:
    """The ELT grid: site_id, lon, lat (cell centre), admin1, admin2 + grid indices."""
    g = read_elt("sites_static", columns=["site_id", "lon", "lat", "admin1", "admin2"])
    return pd.concat([g, cell_index(g["site_id"])], axis=1)
