"""5x5 km equal-area grid over Spain and the stratified sample of 500 cells."""
from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd

from . import geo

GB_API = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/{level}/"
GB_MIRROR = ("https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/main/releaseData/gbOpen/"
             "{iso}/{level}/geoBoundaries-{iso}-{level}_simplified.geojson")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.lower().strip()


def fetch_boundaries(lake, iso="ESP"):
    """ADM0/ADM1/ADM2 from geoBoundaries (simplified geometries, CC BY 4.0)."""
    import geopandas as gpd
    out = {}
    for level in ("ADM0", "ADM1", "ADM2"):
        dest = lake.raw / "geoboundaries" / f"{iso}_{level}.geojson"
        if not dest.exists():
            try:
                meta = lake.get_json(GB_API.format(iso=iso, level=level),
                                     lake.raw / "geoboundaries" / f"{iso}_{level}_meta.json")
                url = meta.get("simplifiedGeometryGeoJSON") or meta["gjDownloadURL"]
            except Exception as e:
                lake.log.warning("API de geoBoundaries no disponible (%s); uso el espejo de GitHub", e)
                url = GB_MIRROR.format(iso=iso, level=level)
            lake.cached_get(url, dest)
        out[level] = gpd.read_file(dest).to_crs(geo.EQUAL_AREA)
    lake.catalog("geoboundaries_ESP", "geoBoundaries", GB_API.format(iso=iso, level="ADM*"), "CC BY 4.0")
    return out


def build_grid(adm0, cell_m: int = 5000, min_land: float = 0.5, iso: str = "ESP"):
    import geopandas as gpd
    import shapely

    land = shapely.union_all(adm0.geometry.values)
    shapely.prepare(land)
    parts = list(getattr(land, "geoms", [land]))
    cells = []
    for part in parts:
        minx, miny, maxx, maxy = part.bounds
        xs = np.arange(np.floor(minx / cell_m) * cell_m, maxx, cell_m)
        ys = np.arange(np.floor(miny / cell_m) * cell_m, maxy, cell_m)
        if len(xs) == 0 or len(ys) == 0:
            continue
        X, Y = np.meshgrid(xs, ys)
        cells.append(np.column_stack([X.ravel(), Y.ravel()]))
    ll = np.unique(np.vstack(cells), axis=0)
    boxes = shapely.box(ll[:, 0], ll[:, 1], ll[:, 0] + cell_m, ll[:, 1] + cell_m)

    tree = shapely.STRtree(boxes)
    cand = np.unique(tree.query(land, predicate="intersects"))
    boxes, ll = boxes[cand], ll[cand]
    inside = shapely.contains(land, boxes)
    frac = np.ones(len(boxes))
    edge = ~inside
    inter = shapely.intersection(boxes[edge], land)
    frac[edge] = shapely.area(inter) / (cell_m * cell_m)
    clipped = boxes.copy()
    clipped[edge] = inter
    keep = frac >= min_land

    g = gpd.GeoDataFrame({
        "site_id": [f"{iso}_{int(x // cell_m)}_{int(y // cell_m)}" for x, y in ll[keep]],
        "land_fraction": frac[keep],
    }, geometry=boxes[keep], crs=geo.EQUAL_AREA)
    clip = clipped[keep]
    g["area_ha"] = shapely.area(clip) / 1e4
    perim = shapely.length(clip)
    g["parcel_compactness"] = 4 * np.pi * shapely.area(clip) / np.where(perim > 0, perim ** 2, np.nan)
    c = g.geometry.centroid
    g["x"], g["y"] = c.x.values, c.y.values
    ll84 = gpd.GeoSeries(c, crs=geo.EQUAL_AREA).to_crs("EPSG:4326")
    g["lon"], g["lat"] = ll84.x.values, ll84.y.values
    g["country_iso3"] = iso
    return g.reset_index(drop=True)


def attach_admin(grid, adm1, adm2):
    import geopandas as gpd
    pts = geo.site_points(grid)
    for col, adm in (("admin1", adm1), ("admin2", adm2)):
        name_col = "shapeName" if "shapeName" in adm.columns else adm.columns[0]
        j = gpd.sjoin_nearest(pts[["geometry"]].assign(_i=np.arange(len(pts))),
                              adm[[name_col, "geometry"]], how="left")
        j = j.drop_duplicates("_i").sort_values("_i")
        grid[col] = j[name_col].values
    return grid


def attach_h3(grid, res: int = 7):
    try:
        import h3
        f = h3.latlng_to_cell if hasattr(h3, "latlng_to_cell") else h3.geo_to_h3
        grid["h3_cell_r7"] = [f(la, lo, res) for la, lo in zip(grid["lat"], grid["lon"])]
    except ImportError:
        grid["h3_cell_r7"] = pd.NA
    return grid


def stratified_sample(grid, dcs, cfg):
    """Positives (cells with a known data center) + focus regions + uniform random."""
    rng = np.random.default_rng(cfg["project"]["seed"])
    s = cfg["sampling"]
    n_total = s["n_cells"]
    grid = grid.copy()
    grid["n_known_dc"] = 0
    if dcs is not None and len(dcs):
        import geopandas as gpd
        j = gpd.sjoin(dcs[["geometry"]], grid[["site_id", "geometry"]], predicate="within")
        cnt = j.groupby("site_id").size()
        grid["n_known_dc"] = grid["site_id"].map(cnt).fillna(0).astype(int)

    focus = [norm(r) for r in s.get("focus_regions", [])]
    if str(n_total).lower() in ("all", "todas", "0") or int(n_total) >= len(grid):
        # whole grid: every cell, labelled with the stratum it would belong to
        out = grid.copy()
        in_focus = out["admin1"].map(lambda a: any(f in norm(a) for f in focus))
        out["sample_type"] = np.where(out["n_known_dc"] > 0, "positivo_dc", np.where(in_focus, "foco_region", "resto"))
        return out.sort_values("site_id").reset_index(drop=True)
    n_total = int(n_total)

    chosen, kind = [], {}
    pos = grid.index[grid["n_known_dc"] > 0].to_numpy()
    if len(pos) > s["n_positive_max"]:
        pos = rng.choice(pos, s["n_positive_max"], replace=False)
    for i in pos:
        chosen.append(i); kind[i] = "positivo_dc"

    per_region = s["n_focus"] // max(len(focus), 1)      # same number of cells in each focus region
    for f in focus:
        in_f = grid["admin1"].map(lambda a: f in norm(a)).to_numpy()
        pool = np.setdiff1d(np.flatnonzero(in_f), chosen)
        k = min(per_region, len(pool), n_total - len(chosen))
        for i in rng.choice(pool, k, replace=False) if k > 0 else []:
            chosen.append(i); kind[i] = "foco_region"

    pool = np.setdiff1d(np.arange(len(grid)), chosen)
    k = min(n_total - len(chosen), len(pool))
    for i in rng.choice(pool, k, replace=False) if k > 0 else []:
        chosen.append(i); kind[i] = "aleatoria"

    out = grid.loc[chosen].copy()
    out["sample_type"] = [kind[i] for i in chosen]
    return out.sort_values("site_id").reset_index(drop=True)


def known_datacenters(lake, cfg):
    """Data centers from OSM and PeeringDB (Spain), used for positives and labels."""
    import geopandas as gpd
    from .collectors.osm import overpass_layer
    from .collectors.peeringdb import fetch_pdb

    frames = []
    try:
        osm = overpass_layer(lake, cfg, "datacenters",
                             'nwr["telecom"="data_center"](area.a);nwr["building"="data_center"](area.a);', "center")
        if osm is not None and len(osm):
            frames.append(pd.DataFrame({"source": "OSM", "name": osm.get("name"),
                                        "lon": osm.geometry.to_crs(4326).x, "lat": osm.geometry.to_crs(4326).y}))
    except Exception as e:
        lake.log.warning("Overpass (data centers) falló: %s", e)
    try:
        fac = fetch_pdb(lake, "fac", country="ES")
        if fac is not None and len(fac):
            frames.append(pd.DataFrame({"source": "PeeringDB", "name": fac["name"],
                                        "lon": fac["longitude"], "lat": fac["latitude"]}))
    except Exception as e:
        lake.log.warning("PeeringDB (facilities) falló: %s", e)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True).dropna(subset=["lon", "lat"])
    g = geo.points_from_lonlat(df)
    (lake.processed / "grid").mkdir(parents=True, exist_ok=True)
    g.to_parquet(lake.processed / "grid" / "known_datacenters.parquet")
    return g


def run_grid(lake, cfg, adm=None, dcs="fetch"):
    """Build the full grid, attach admin units and H3, draw the sample, stage static fields."""
    import geopandas as gpd
    adm = adm or fetch_boundaries(lake, cfg["project"]["country_iso3"])
    grid = build_grid(adm["ADM0"], cfg["project"]["cell_size_m"], cfg["project"]["min_land_fraction"],
                      cfg["project"]["country_iso3"])
    grid = attach_admin(grid, adm["ADM1"], adm["ADM2"])
    grid = attach_h3(grid)
    d = lake.processed / "grid"
    d.mkdir(parents=True, exist_ok=True)
    grid.to_parquet(d / "spain_grid_5km.parquet")
    lake.log.info("Rejilla: %d celdas de %d m", len(grid), cfg["project"]["cell_size_m"])

    if isinstance(dcs, str):
        dcs = known_datacenters(lake, cfg)
    sample = stratified_sample(grid, dcs, cfg)
    sample.to_parquet(d / "sample_cells.parquet")
    lake.log.info("Muestra: %s", sample["sample_type"].value_counts().to_dict())

    # static fields that come straight from the grid
    pts = geo.site_points(sample)
    static = sample[["site_id", "country_iso3", "admin1", "admin2", "lat", "lon", "h3_cell_r7",
                     "area_ha", "parcel_compactness", "sample_type"]].copy()
    static["is_datacenter"] = sample["n_known_dc"] > 0
    if dcs is not None and len(dcs):
        nn = geo.nearest(pts, dcs)
        static["dist_existing_dc_km"] = nn["dist_km"].values
        static["n_existing_dc_50km"] = geo.count_within(geo.xy(pts), geo.xy(dcs), 50)
    lake.write_stage("grid", "sites_static", static)
    src = {"source": "Rejilla propia sobre geoBoundaries", "license": "CC BY 4.0", "crs": cfg["project"]["crs_equal_area"],
           "spatial_resolution_m": cfg["project"]["cell_size_m"], "is_synthetic": False, "imputation_method": "ninguno"}
    dc_src = {"source": "OpenStreetMap + PeeringDB", "license": "ODbL / PeeringDB AUP", "is_synthetic": False,
              "imputation_method": "ninguno", "confidence": 0.6}
    lake.write_lineage("grid", {
        **{f"sites_static.{f}": src for f in ["country_iso3", "admin1", "admin2", "lat", "lon", "h3_cell_r7",
                                               "area_ha", "parcel_compactness", "sample_type"]},
        **{f"sites_static.{f}": dc_src for f in ["is_datacenter", "dist_existing_dc_km", "n_existing_dc_50km"]},
    })
    return sample
