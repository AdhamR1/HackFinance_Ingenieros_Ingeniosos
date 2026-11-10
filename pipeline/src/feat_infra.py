"""INFRASTRUCTURE features per cell from OpenStreetMap: power grid and motorways.

A data center needs a grid connection (tens to hundreds of MW): the farther the substation /
high-voltage line, the more expensive and slower the connection. Motorways = construction
access and fibre corridors.

Source: OpenStreetMap (ODbL) through the ohsome API (HeiGIT, Heidelberg University), snapshot of
2026-07-27. The public Overpass servers were down (502/504) when this was built, and ohsome only
serves the bounding box of each element, so we use elements that are points or short pieces:
  * substations (with their voltage tag)      -> exact position
  * power towers (pylons)                      -> exact position; pylons carry high-voltage lines
  * motorway / trunk road segments             -> centre of each segment (segments are short)
  * motorway exits                             -> exact position
Distances only count elements inside Spain and in the cell's own electrical system (peninsula,
Balearics, Canaries, Ceuta, Melilla): NaN = that system has none (e.g. no 400 kV in the islands).
Spain is fetched in 2-degree tiles, cached in data/cache/ohsome/: re-running continues where it stopped.

Output: data/processed/feat_infra.parquet
  site_id, dist_substation_km, dist_substation_220kv_km, dist_substation_400kv_km,
  n_substations_20km, dist_hv_line_km, n_towers_5km, dist_motorway_km, dist_motorway_junction_km
"""
import json
import time

import numpy as np
import pandas as pd
import requests
from pyproj import Transformer
from scipy.spatial import cKDTree

from cells import PIPELINE, PROCESSED, read_grid, site_id_from_xy

CACHE = PIPELINE / "data" / "cache" / "ohsome"
URL = "https://api.ohsome.org/v1/elements/bbox"
SNAPSHOT = "2026-07-27"
HEADERS = {"User-Agent": "hackfinance-dc-siting/0.1 (hackathon research)"}
TILE_DEG = 2
LAYERS = {   # name -> (ohsome filter, keep tags)
    "substation": ("power=substation", True),
    "tower": ("power=tower and type:node", False),
    "motorway": ("highway in (motorway, trunk) and type:way", False),
    "junction": ("highway=motorway_junction and type:node", False),
}
TO_M = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
# separate electrical systems: an island cell cannot connect to a substation across the sea
ISLANDS = ["Canarias", "Illes Balears", "Ciudad Autónoma de Ceuta", "Ciudad Autónoma de Melilla"]


def fetch(layer, s, w, n, e):
    dest = CACHE / layer / f"{s}_{w}_{n}_{e}.json"
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))["features"]
    filt, tags = LAYERS[layer]
    params = {"bboxes": f"{w},{s},{e},{n}", "filter": filt, "time": SNAPSHOT,
              "properties": "tags" if tags else None}
    for attempt in range(5):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=300)
            if r.status_code == 200:
                d = r.json()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(d), encoding="utf-8")
                return d["features"]
            why = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as ex:
            why = type(ex).__name__
        wait = 15 * 2 ** attempt
        print(f"    {layer} {s},{w}: falló ({why}), reintento en {wait} s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"No se pudo descargar {layer} en {s},{w},{n},{e}")


def tiles(grid):
    """2-degree tiles that contain at least one cell centre."""
    keys = set(zip(np.floor(grid.lat / TILE_DEG).astype(int), np.floor(grid.lon / TILE_DEG).astype(int)))
    return sorted((a * TILE_DEG, b * TILE_DEG, (a + 1) * TILE_DEG, (b + 1) * TILE_DEG) for a, b in keys)


def kv(tags: dict) -> float:
    """Highest voltage in kV (voltage tags can be '400000;220000')."""
    vals = []
    for v in str(tags.get("voltage", "")).replace(",", ";").split(";"):
        try:
            vals.append(float(v.strip()) / 1000)
        except ValueError:
            pass
    return max(vals) if vals else np.nan


def points(features):
    """Centre of each bounding box in EPSG:3035 + voltage (NaN if untagged). Deduplicated by OSM id."""
    seen, rows = set(), []
    for f in features:
        p = f["properties"]
        if p["@osmId"] in seen:          # an element crossing two tiles comes twice
            continue
        seen.add(p["@osmId"])
        ring = np.array(f["geometry"]["coordinates"][0] if f["geometry"]["type"] == "Polygon"
                        else [f["geometry"]["coordinates"]])
        rows.append((ring[:, 0].mean(), ring[:, 1].mean(), kv(p)))
    a = np.array(rows, dtype=float).reshape(-1, 3)
    x, y = TO_M.transform(a[:, 0], a[:, 1])
    return np.column_stack([x, y]), a[:, 2]


def system_of(admin1: pd.Series) -> np.ndarray:
    return np.where(admin1.isin(ISLANDS), admin1, "peninsula")


def nearest_km(cells, pts):
    """Distance from each cell to the nearest point of the SAME electrical system (NaN if none).
    `cells` / `pts` are (xy, system) tuples."""
    (cxy, csys), (pxy, psys) = cells, pts
    out = np.full(len(cxy), np.nan)
    for s in np.unique(csys):
        c, p = csys == s, psys == s
        if p.any():
            out[c] = cKDTree(pxy[p]).query(cxy[c])[0] / 1000
    return out


def count_within(cells, pts, radius_m):
    (cxy, csys), (pxy, psys) = cells, pts
    out = np.zeros(len(cxy), dtype=int)
    for s in np.unique(csys):
        c, p = csys == s, psys == s
        if p.any():
            out[c] = [len(ix) for ix in cKDTree(pxy[p]).query_ball_point(cxy[c], radius_m)]
    return out


def main():
    grid = read_grid()
    tl = tiles(grid)
    feats = {k: [] for k in LAYERS}
    for i, (s, w, n, e) in enumerate(tl, 1):
        for layer in LAYERS:
            t0 = time.time()
            got = fetch(layer, s, w, n, e)
            feats[layer] += got
            print(f"  [{i}/{len(tl)}] {layer} lat {s}..{n} lon {w}..{e}: {len(got):,} ({time.time() - t0:.0f} s)", flush=True)

    cell_sys = dict(zip(grid.site_id, system_of(grid.admin1)))
    cells = (grid[["x_m", "y_m"]].values, system_of(grid.admin1))

    def layer(name, min_kv=None):
        """Points of a layer that fall inside a Spanish cell (drops Portugal, France, Morocco)."""
        xy, v = pts[name]
        sys = pd.Series(site_id_from_xy(xy[:, 0], xy[:, 1])).map(cell_sys).values
        keep = pd.notna(sys)
        if min_kv is not None:
            keep &= v >= min_kv
        return xy[keep], sys[keep].astype(str)

    pts = {k: points(v) for k, v in feats.items()}
    sub = layer("substation")
    print(f"En España: subestaciones={len(sub[0]):,} (220 kV+: {len(layer('substation', 220)[0]):,}, "
          f"400 kV: {len(layer('substation', 380)[0]):,})  torres={len(layer('tower')[0]):,}  "
          f"tramos de autovía={len(layer('motorway')[0]):,}  salidas={len(layer('junction')[0]):,}")

    out = pd.DataFrame({"site_id": grid["site_id"]})
    out["dist_substation_km"] = nearest_km(cells, sub)
    out["dist_substation_220kv_km"] = nearest_km(cells, layer("substation", 220))
    out["dist_substation_400kv_km"] = nearest_km(cells, layer("substation", 380))
    out["n_substations_20km"] = count_within(cells, sub, 20_000)
    towers = layer("tower")
    out["dist_hv_line_km"] = nearest_km(cells, towers)
    out["n_towers_5km"] = count_within(cells, towers, 5_000)
    out["dist_motorway_km"] = nearest_km(cells, layer("motorway"))
    out["dist_motorway_junction_km"] = nearest_km(cells, layer("junction"))

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROCESSED / "feat_infra.parquet", index=False)
    print(out.describe().T[["mean", "50%", "max"]].round(1).to_string())
    print(f"-> {PROCESSED / 'feat_infra.parquet'}")


if __name__ == "__main__":
    main()
