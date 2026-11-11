"""LAND features and EXCLUSION rules per cell OUTSIDE Europe (Japan), from GHSL built-up surface.

feat_suelo.py uses CORINE Land Cover and Natura 2000, which only cover Europe. Here the land
columns come from the JRC Global Human Settlement Layer, built-up surface 2025, 1 km
(GHS-BUILT-S R2023A, CC BY 4.0), which comes in two maps: all buildings and NON-residential
buildings (industry, commerce, services). Per cell:
  industrial_pct   % of the cell covered by non-residential buildings   (CORINE 121's role)
  urbano_pct       % of the cell covered by residential buildings       (CORINE 111/112's role)
They measure building footprints, not land-use zones, so they are smaller than CORINE's
percentages and NOT comparable with Spain's; each country has its own model, so they do not need
to be. Each cell takes the mean of 7 x 7 points 500 m apart inside it (each point reads the 1 km
pixel it falls in).

The world maps (153 + 34 MB) are downloaded to a temporary folder and only the crop of the
country is kept in data/cache/ghsl/. Natura 2000 does not exist outside the EU. The exclusions and
warnings reuse feat_suelo.exclusions with the columns that exist (national parks come from
feat_riesgos.py: run it first).

Usage (from pipeline/):  $env:DC_COUNTRY = "JPN"; python src/feat_suelo_ghsl.py
Output: data/processed/<ISO>/feat_suelo.parquet and exclusions_<tag>_3500.parquet
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from pyproj import Transformer

from cells import CELL_M, CRS, ISO, PIPELINE, PROCESSED, read_grid
from feat_suelo import exclusions

try:  # corporate networks that inspect TLS: use the Windows certificate store
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

BASE = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A/"
MAPS = {  # name -> product (1 km, Mollweide ESRI:54009, m2 of building per pixel)
    "total": "GHS_BUILT_S_E2025_GLOBE_R2023A_54009_1000",
    "nres": "GHS_BUILT_S_NRES_E2025_GLOBE_R2023A_54009_1000",
}
MOLLWEIDE = "ESRI:54009"
CACHE = PIPELINE / "data" / "cache" / "ghsl"
HEADERS = {"User-Agent": "hackfinance-dc-siting/0.1 (hackathon research)"}
SUB = 7  # sample points per cell side
MARGIN_M = 20_000  # crop margin around the country


def crop(name: str, grid: pd.DataFrame) -> Path:
    """Crop of the world map around the country (GeoTIFF in data/cache/ghsl/), made once."""
    import rasterio
    from rasterio.windows import from_bounds

    dest = CACHE / f"{MAPS[name]}_{ISO}.tif"
    if dest.exists():
        return dest
    prod = MAPS[name]
    url = f"{BASE}{prod}/V1-0/{prod}_V1_0.zip"
    to_m = Transformer.from_crs("EPSG:4326", MOLLWEIDE, always_xy=True)
    x, y = to_m.transform(grid.lon.to_numpy(), grid.lat.to_numpy())
    bounds = (x.min() - MARGIN_M, y.min() - MARGIN_M, x.max() + MARGIN_M, y.max() + MARGIN_M)
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / f"{prod}.zip"
        print(f"  descargando {prod} (temporal)...", flush=True)
        with requests.get(url, headers=HEADERS, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(zpath, "wb") as f:
                for block in r.iter_content(1 << 20):
                    f.write(block)
        with rasterio.open(f"/vsizip/{zpath.as_posix()}/{prod}_V1_0.tif") as src:
            win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
            data = src.read(1, window=win)
            meta = src.meta | {
                "driver": "GTiff",
                "height": data.shape[0],
                "width": data.shape[1],
                "transform": src.window_transform(win),
                "compress": "deflate",
            }
        CACHE.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dest, "w", **meta) as out:
            out.write(data, 1)
    print(f"  recorte -> {dest}")
    return dest


def built_pct(path: Path, grid: pd.DataFrame) -> np.ndarray:
    """% of each cell covered by buildings: mean of SUB x SUB points read from the 1 km map."""
    import rasterio

    off = (np.arange(SUB) + 0.5) / SUB * CELL_M
    ox, oy = np.meshgrid(off, off)
    xs = (grid["i"].to_numpy()[:, None] * CELL_M + ox.ravel()).ravel()
    ys = (grid["j"].to_numpy()[:, None] * CELL_M + oy.ravel()).ravel()
    mx, my = Transformer.from_crs(CRS, MOLLWEIDE, always_xy=True).transform(xs, ys)
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        if src.nodata is not None:
            arr[arr == src.nodata] = 0
        rows, cols = rasterio.transform.rowcol(src.transform, mx, my)
        pix_m2 = abs(src.transform.a * src.transform.e)
    rows, cols = np.asarray(rows), np.asarray(cols)
    ok = (rows >= 0) & (rows < arr.shape[0]) & (cols >= 0) & (cols < arr.shape[1])
    v = np.zeros(len(xs))
    v[ok] = arr[rows[ok], cols[ok]] / pix_m2
    return 100 * v.reshape(len(grid), SUB * SUB).mean(axis=1)


def main():
    grid = read_grid()
    total = built_pct(crop("total", grid), grid)
    nres = built_pct(crop("nres", grid), grid)
    out = pd.DataFrame(
        {
            "site_id": grid["site_id"],
            "industrial_pct": nres,
            "urbano_pct": np.clip(total - nres, 0, None),
        }
    ).round(2)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROCESSED / "feat_suelo.parquet", index=False)
    print(out.describe().T[["mean", "50%", "max"]].round(2).to_string())
    print(f"-> {PROCESSED / 'feat_suelo.parquet'}")
    exclusions(out)


if __name__ == "__main__":
    main()
