"""RISK features per cell, a separate block that features.py joins on its own (feat_*.parquet).

Sources
  * SNCZI (MITECO), 1:25,000 shapefiles: Zona de Flujo Preferente (ZFP) and flood zones for
    T=100 and T=500 years. MITECO protects the download with an anti-bot check, so the zips are
    downloaded by hand (browser) anywhere under data/raw/ and read as they are (no need to unzip):
      laminas-zfp-PB.zip, laminas-zfp-can.zip          (zona de flujo preferente)
      laminasPB-q100.zip, laminasCanarias-q100.zip     (T = 100 años)
      laminasPB-q500.zip, laminasCanarias-q500.zip     (T = 500 años)
    https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/agua/zi-lamina.html
    https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/agua/laminas-zona-flujo-preferente
    .html
  * National parks: WDPA (UNEP-WCMC feature service, no registration), designation "Parque
  Nacional".
  * IGN PGA, 475 years (mapa de peligrosidad sísmica 2012/2015): there is no seismic product in
    the CNIG download centre, but the IGN earthquake viewer (https://visualizadores.ign.es/tproximos)
    draws the PGA isolines (0.01 g apart) from a public GeoJSON: it is downloaded once to
    data/raw/ign/ and interpolated between isolines at every cell centre. Any other IGN file put in
    data/raw/ign/ (GeoTIFF, zones, or a mesh of points as shapefile/GPKG/CSV with lon/lat; g or
    cm/s2) is also read. The ETL has pga_475y_g as well (GEM, same for the three countries).

Output: data/processed/feat_riesgos.parquet  (site_id + the columns below; NaN = layer not
available)
  zfp_pct, zi_t100_pct, zi_t500_pct    % of the cell inside the zone (Peninsula+Baleares and
  Canarias
                                       come in separate files: a region without its file stays NaN)
  parque_nacional_pct                  % of the cell inside a national park
  dist_parque_nacional_km              distance from the cell centre to the nearest national park
  pga475_ign_g                         IGN PGA (475 years, g, rock) at the cell centre

    python src/feat_riesgos.py              # everything
    python src/feat_riesgos.py --solo-pga   # only pga475_ign_g, on the existing parquet
"""

import json
import zipfile

import numpy as np
import pandas as pd
import requests
import shapely

from cells import CELL_M, CRS, ISO, PIPELINE, PROCESSED, RAW, read_grid
from feat_suelo import HEADERS, cover_pct

try:  # corporate networks that inspect TLS: use the Windows certificate store
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

CACHE = PIPELINE / "data" / "cache"
SNCZI = RAW / "snczi"
IGN = RAW / "ign"
# column -> words in the MITECO file names (data zips: laminasPB-q100.zip...; their style zips are
# lyr-...)
SNCZI_LAYERS = {
    "zfp_pct": ("zfp", "flujopreferente"),
    "zi_t100_pct": ("q100", "mediauocasional"),
    "zi_t500_pct": ("q500", "bajaoexcepcional"),
}
WDPA = (
    "https://data-gis.unep-wcmc.org/server/rest/services/ProtectedSites/"
    "The_World_Database_of_Protected_Areas/FeatureServer/1/query"
)
SIMPLIFY_M = 10  # 1:25,000 outlines: 10 m changes nothing at the scale of a 12 km2 cell


def read_zip_shapes(path) -> np.ndarray:
    """Every shapefile inside a zip: geometry only, in EPSG:3035, simplified and split into single
    parts."""
    import pyogrio

    with zipfile.ZipFile(path) as z:
        members = [n for n in z.namelist() if n.lower().endswith(".shp")]
    out = []
    for m in members:
        g = pyogrio.read_dataframe(f"/vsizip/{path.as_posix()}/{m}", columns=[])
        if g.crs is None:
            print(f"    {path.name}/{m}: sin sistema de referencia, se omite")
            continue
        geoms = g[g.geometry.notna()].to_crs(CRS).geometry.values
        del g
        geoms = shapely.simplify(
            np.asarray(geoms, dtype=object), SIMPLIFY_M, preserve_topology=True
        )
        parts = shapely.get_parts(geoms)
        out.append(parts[~shapely.is_empty(parts)])
    return np.concatenate(out) if out else np.array([], dtype=object)


def cover_pct_tiled(cells, parts, tile_cells: int = 10) -> np.ndarray:
    """% of each cell covered by the union of `parts`, cutting the polygons by tiles of tile_cells
    x
    tile_cells cells first: flood zones are river polygons with millions of vertices, far too slow
    to
    intersect with every cell they touch."""
    pct = np.zeros(len(cells))
    if len(parts) == 0:
        return pct
    tree = shapely.STRtree(parts)
    i, j = cells["i"].to_numpy(), cells["j"].to_numpy()
    t = tile_cells * CELL_M
    groups = (
        pd.Series(np.arange(len(cells)))
        .groupby([i // tile_cells, j // tile_cells])
        .apply(np.asarray)
    )
    for (a, b), rows in groups.items():
        x0, y0 = a * t, b * t
        hit = tree.query(shapely.box(x0, y0, x0 + t, y0 + t), predicate="intersects")
        if len(hit) == 0:
            continue
        pieces = shapely.clip_by_rect(parts[hit], x0, y0, x0 + t, y0 + t)
        pieces = shapely.make_valid(pieces[~shapely.is_empty(pieces)])
        if len(pieces) == 0:
            continue
        cb = shapely.box(
            i[rows] * CELL_M, j[rows] * CELL_M, (i[rows] + 1) * CELL_M, (j[rows] + 1) * CELL_M
        )
        ci, pi = shapely.STRtree(pieces).query(cb, predicate="intersects")
        if len(ci) == 0:
            continue
        inter = pd.DataFrame({"c": ci, "g": shapely.intersection(cb[ci], pieces[pi])})
        for c, grp in inter.groupby("c"):
            pct[rows[c]] = shapely.area(shapely.union_all(grp["g"].values))
    return 100 * pct / (CELL_M * CELL_M)


def snczi_zips() -> dict:
    """Data zips found anywhere under data/raw/, by layer. Zips without a shapefile (the .lyr style
    files MITECO offers next to the data) are skipped."""
    found = {col: [] for col in SNCZI_LAYERS}
    for f in sorted(RAW.rglob("*.zip")):
        name = f.name.lower().replace("-", "").replace("_", "")
        col = next((c for c, keys in SNCZI_LAYERS.items() if any(k in name for k in keys)), None)
        if col is None:
            continue
        with zipfile.ZipFile(f) as z:
            has_shp = any(n.lower().endswith(".shp") for n in z.namelist())
        if not has_shp:
            print(f"  {f.name}: solo trae el estilo (.lyr), sin datos; se omite")
            continue
        found[col].append(f)
    return found


def snczi(grid, boxes, canarias) -> pd.DataFrame:
    out = pd.DataFrame(index=grid.index)
    zips = snczi_zips()
    for col, files in zips.items():
        out[col] = np.nan
        if not files:
            print(f"  {col}: falta el zip de datos (laminas...zip) en {RAW}")
            continue
        for f in files:
            is_can = "can" in f.name.lower()
            cells = canarias if is_can else ~canarias
            parts = read_zip_shapes(f)
            print(
                f"  {col}: {f.name}: {len(parts):,} polígonos; calculando el % de cada celda…",
                flush=True,
            )
            out.loc[cells, col] = cover_pct_tiled(grid[cells.to_numpy()], parts)
            del parts
    return out


PARK_WHERE = {  # WDPA designation of a national park in each country
    "ESP": "iso3='ESP' AND desig LIKE 'Parque Nacional%'",
    "JPN": "iso3='JPN' AND desig_eng = 'National Park'",
}


def national_parks():
    """Polygons of the country's national parks (WDPA), in the grid projection."""
    import geopandas as gpd

    dest = CACHE / "wdpa" / f"parques_nacionales_{ISO.lower()}.geojson"
    if not dest.exists():
        r = requests.get(
            WDPA,
            params={
                "where": PARK_WHERE[ISO],
                "outFields": "site_id,name,desig,status",
                "outSR": 4326,
                "f": "geojson",
            },
            headers=HEADERS,
            timeout=600,
        )
        js = r.json()
        if "error" in js or not js.get("features"):
            raise RuntimeError(f"WDPA no devolvió parques nacionales: {js.get('error')}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(js), encoding="utf-8")
    g = gpd.read_file(dest).to_crs(CRS)
    g = g[g["status"].astype(str) != "Proposed"]
    print(f"  parques nacionales: {len(g)} ({', '.join(sorted(g['name'].astype(str)))[:300]}…)")
    return list(shapely.make_valid(g.geometry.values))


IGN_PGA_URL = "https://www.ign.es/web/resources/sismologia/tproximos/json/pga475.js"
IGN_ISOLINES = "pga475_isolineas_ign.geojson"
IGN_PGA_WORDS = ("pga", "acel", "valor", "value")  # name of the column with the PGA
IGN_POINT_KM = 25  # a grid point of the IGN gives its value to cells up to this distance
IGN_STEP_M = 500  # isolines are densified to one vertex every 500 m before interpolating
CANARIAS_MAX_LAT = 32  # interpolated apart: no triangle may join the Canaries and the Peninsula


def pga_in_g(v) -> pd.Series:
    """PGA in g. The IGN may give it in cm/s2 (gal): no PGA in Spain is above 3 g."""
    v = pd.to_numeric(pd.Series(v), errors="coerce")
    return v / 980.665 if v.median() > 3 else v


def _pga_column(columns) -> str | None:
    return next((c for c in columns if any(k in c.lower() for k in IGN_PGA_WORDS)), None)


def fetch_ign_isolines():
    """PGA isolines of the IGN earthquake viewer: a GeoJSON (CRS84) inside a JavaScript variable,
    saved once as plain GeoJSON in data/raw/ign/."""
    dest = IGN / IGN_ISOLINES
    if dest.exists():
        return dest
    try:
        r = requests.get(IGN_PGA_URL, headers=HEADERS, timeout=120)
        r.raise_for_status()
        js = json.loads(r.text[r.text.index("{") : r.text.rindex("}") + 1])
    except (requests.RequestException, ValueError) as e:
        print(f"  pga475_ign_g: no se pudieron bajar las isolíneas del IGN ({e})")
        return None
    if not js.get("features"):
        return None
    IGN.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(js), encoding="utf-8")
    return dest


def pga_from_isolines(lines, values, x, y, step_m: float = IGN_STEP_M) -> np.ndarray:
    """Value at (x, y) interpolated linearly between isolines (Delaunay triangles over their
    densified vertices). Points outside every triangle take the value of the nearest isoline."""
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

    dense = shapely.segmentize(np.asarray(lines, dtype=object), step_m)
    pts, idx = shapely.get_coordinates(dense, return_index=True)
    z = np.asarray(values, dtype=float)[idx]
    pts, first = np.unique(pts, axis=0, return_index=True)
    z = z[first]
    xy = np.column_stack([x, y])
    v = LinearNDInterpolator(pts, z)(xy)
    out = np.isnan(v)
    if out.any():
        v[out] = NearestNDInterpolator(pts, z)(xy[out])
    return v


def _read_ign_table(f):
    """CSV with longitude/latitude columns (WGS84) -> points."""
    import geopandas as gpd

    t = pd.read_csv(f, sep=None, engine="python", decimal=",")
    low = {c.lower(): c for c in t.columns}
    lon = next((low[k] for k in ("lon", "longitud", "longitude", "x") if k in low), None)
    lat = next((low[k] for k in ("lat", "latitud", "latitude", "y") if k in low), None)
    if lon is None or lat is None:
        return None
    xy = gpd.points_from_xy(pd.to_numeric(t[lon]), pd.to_numeric(t[lat]))
    return gpd.GeoDataFrame(t, geometry=xy, crs=4326)


def ign_pga(grid) -> pd.Series | None:
    """IGN PGA (475 years) at the cell centre from a file in data/raw/ign/.

    Accepted: isolines (downloaded from the IGN viewer when the folder is empty); a GeoTIFF;
    polygons with a PGA column (zones); a mesh of points (shapefile, GPKG or a CSV with lon/lat),
    where each cell takes the nearest point within IGN_POINT_KM. Values in cm/s2 become g.
    """
    files = sorted(
        p
        for p in IGN.glob("*")
        if p.suffix.lower() in (".tif", ".tiff", ".shp", ".gpkg", ".geojson", ".zip", ".csv")
    )
    f = files[0] if files else fetch_ign_isolines()
    if f is None:
        print(
            f"  pga475_ign_g: no hay archivo del IGN en {IGN} (se usa pga_475y_g de GEM del ETL)"
        )
        return None
    x, y = grid["x_m"].to_numpy(), grid["y_m"].to_numpy()
    if f.suffix.lower() in (".tif", ".tiff"):
        import rasterio
        from rasterio.warp import transform

        with rasterio.open(f) as ds:
            xs, ys = transform(CRS, ds.crs, list(x), list(y))
            v = np.array([s[0] for s in ds.sample(zip(xs, ys))], dtype=float)
            if ds.nodata is not None:
                v[v == ds.nodata] = np.nan
        return pga_in_g(v).set_axis(grid.index)
    import geopandas as gpd

    if f.suffix.lower() == ".csv":
        g = _read_ign_table(f)
        if g is None:
            print(f"  pga475_ign_g: {f.name} no tiene columnas de longitud y latitud")
            return None
    else:
        g = gpd.read_file(f"/vsizip/{f.as_posix()}" if f.suffix.lower() == ".zip" else f)
    g = g.to_crs(CRS)
    col = _pga_column([c for c in g.columns if c != "geometry"])
    if col is None:
        print(f"  pga475_ign_g: {f.name} no tiene una columna de PGA ({list(g.columns)})")
        return None
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(x, y), crs=CRS, index=grid.index)
    kinds = set(g.geom_type.dropna())
    if kinds <= {"LineString", "MultiLineString"}:
        z = pd.to_numeric(g[col], errors="coerce").to_numpy()
        line_can = (g.geometry.representative_point().to_crs(4326).y < CANARIAS_MAX_LAT).to_numpy()
        cell_can = (pts.geometry.to_crs(4326).y < CANARIAS_MAX_LAT).to_numpy()
        v = np.full(len(pts), np.nan)
        for lm, cm in ((line_can, cell_can), (~line_can, ~cell_can)):
            if lm.any() and cm.any():
                v[cm] = pga_from_isolines(g.geometry.values[lm], z[lm], x[cm], y[cm])
        v = pga_in_g(v).set_axis(grid.index)
    elif kinds <= {"Point", "MultiPoint"} | {"Polygon", "MultiPolygon"}:
        if kinds <= {"Point", "MultiPoint"}:
            j = gpd.sjoin_nearest(
                pts, g[[col, "geometry"]], how="left", max_distance=IGN_POINT_KM * 1000
            )
        else:
            j = gpd.sjoin(pts, g[[col, "geometry"]], predicate="within", how="left")
        j = j[~j.index.duplicated()]
        v = pga_in_g(j[col]).set_axis(j.index).reindex(grid.index)
    else:
        print(f"  pga475_ign_g: {f.name} mezcla geometrías {sorted(kinds)}")
        return None
    print(
        f"  pga475_ign_g: {f.name} ({col}), {v.notna().mean():.0%} de celdas, "
        f"{v.min():.3f}-{v.max():.3f} g"
    )
    return v.reindex(grid.index)


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Bloque de riesgos por celda (feat_riesgos.parquet)")
    ap.add_argument(
        "--solo-pga", action="store_true", help="solo pga475_ign_g, sobre el parquet existente"
    )
    args = ap.parse_args()
    grid = read_grid()
    if args.solo_pga and (PROCESSED / "feat_riesgos.parquet").exists():
        out = pd.read_parquet(PROCESSED / "feat_riesgos.parquet")
        print("Peligrosidad sísmica IGN:", flush=True)
        pga = ign_pga(grid)
        if pga is not None:
            out["pga475_ign_g"] = out["site_id"].map(pd.Series(pga.values, grid["site_id"]))
        save(out)
        return
    boxes = shapely.box(
        grid.i * CELL_M, grid.j * CELL_M, (grid.i + 1) * CELL_M, (grid.j + 1) * CELL_M
    )
    canarias = grid["admin1"].astype(str).str.contains("Canarias", case=False)
    out = pd.DataFrame({"site_id": grid["site_id"]})

    if ISO == "ESP":  # official Spanish layers; other countries use the ETL's JRC flood and GEM
        print("SNCZI (zonas inundables oficiales):", flush=True)
        out = out.join(snczi(grid, boxes, canarias))

    print("Parques nacionales (WDPA):", flush=True)
    parks = national_parks()
    out["parque_nacional_pct"] = cover_pct(boxes, parks)
    centres = shapely.points(grid["x_m"].to_numpy(), grid["y_m"].to_numpy())
    _, dist = shapely.STRtree(parks).query_nearest(
        centres, return_distance=True, all_matches=False
    )
    out["dist_parque_nacional_km"] = dist / 1000

    if ISO == "ESP":
        print("Peligrosidad sísmica IGN:", flush=True)
        pga = ign_pga(grid)
        if pga is not None:
            out["pga475_ign_g"] = pga.values
    save(out)


def save(out: pd.DataFrame) -> None:
    out = out.round(3)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROCESSED / "feat_riesgos.parquet", index=False)
    print("\nCobertura (celdas con dato) y celdas afectadas:")
    for c in out.columns[1:]:
        hit = (out[c] > 0).sum() if c.endswith("_pct") else None
        print(
            f"  {c:26s} {out[c].notna().mean():6.1%}"
            + (f"   con algo de superficie: {hit:,}" if hit is not None else "")
        )
    print(
        f"-> {PROCESSED / 'feat_riesgos.parquet'}  (python src/features.py lo une a "
        f"features_es_3500.parquet)"
    )


if __name__ == "__main__":
    main()
