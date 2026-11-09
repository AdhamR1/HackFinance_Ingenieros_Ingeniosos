"""LAND features and EXCLUSION rules per cell: protected areas, urban fabric, water, industrial land.

Sources (no registration, EEA ArcGIS REST services):
  * Natura 2000 (end-2023 release), Spanish sites (MS = 'ES'), Habitats + Birds directives.
  * CORINE Land Cover 2018 vector (minimum mapping unit 25 ha).
For each cell we compute the % of its area covered by each group of classes.

Outputs:
  data/processed/feat_suelo.parquet          site_id + pct columns (model features)
  data/processed/exclusions_es_3500.parquet  site_id + pct columns + excluded (bool)

Rules (layer 1 of the model): a cell is EXCLUDED when at least THRESHOLD_PCT of it is
Natura 2000, residential urban fabric or water / wetland. Industrial and commercial land
(CORINE 121) is NOT excluded: it is where data centers get built.
train.py warns if an existing data center falls in an excluded cell (rule too strict).
"""
import json
import time

import numpy as np
import pandas as pd
import requests
import shapely

from cells import CELL_M, PIPELINE, PROCESSED, read_grid

CACHE = PIPELINE / "data" / "cache" / "eea"
HEADERS = {"User-Agent": "hackfinance-dc-siting/0.1 (hackathon research)"}
NATURA = "https://bio.discomap.eea.europa.eu/arcgis/rest/services/ProtectedSites/Natura2000Sites/MapServer/2"
CORINE = "https://image.discomap.eea.europa.eu/arcgis/rest/services/Corine/CLC2018_WM/MapServer/0"
GROUPS = {   # CORINE 2018 codes
    "urbano": ["111", "112", "124", "141", "142"],      # urban fabric, airports, urban green, sport/leisure
    "industrial": ["121"],                               # industrial or commercial units
    "agua": ["411", "412", "421", "422", "423", "511", "512", "521", "522", "523"],  # wetlands + water
}
# PROVISIONAL, under review: at 50 % it excludes 35 of the 100 cells with a data center.
# Proposal: hard exclusion only for what is forbidden (water, national parks, preferential flood
# flow zones); Natura 2000 and urban land become warnings (permits), not exclusions.
THRESHOLD_PCT = {"natura2000": 50, "urbano": 50, "agua": 50}
TILE_DEG = 1
SIMPLIFY_M = 50


def get(url, params, cache_name):
    dest = CACHE / cache_name
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))
    for attempt in range(5):
        try:
            r = requests.post(url + "/query", data={**params, "f": "json"}, headers=HEADERS, timeout=180)
            d = r.json()
            if "error" not in d:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(d), encoding="utf-8")
                return d
            why = d["error"].get("message")
        except (requests.RequestException, ValueError) as ex:
            why = type(ex).__name__
        wait = 10 * 2 ** attempt
        print(f"    {cache_name}: falló ({why}), reintento en {wait} s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"No se pudo descargar {cache_name}")


def esri_to_shapely(geom):
    """Esri JSON polygon -> shapely (outer rings are clockwise, holes counter-clockwise)."""
    outer, holes = [], []
    for ring in geom.get("rings", []):
        if len(ring) < 4:
            continue
        p = shapely.Polygon(ring)
        (holes if shapely.is_ccw(p.exterior) else outer).append(shapely.make_valid(p))
    if not outer:
        return None
    g = shapely.union_all(outer)
    return g.difference(shapely.union_all(holes)) if holes else g


def features(url, where, envelope, tag):
    """All polygons matching `where` inside the lon/lat envelope, in EPSG:3035."""
    w, s, e, n = envelope
    base = {"where": where, "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}
    ids = get(url, {**base, "returnIdsOnly": "true"}, f"{tag}_ids.json").get("objectIds") or []
    out = []
    for k in range(0, len(ids), 100):
        chunk = sorted(ids)[k:k + 100]
        d = get(url, {"objectIds": ",".join(map(str, chunk)), "outFields": "*", "returnGeometry": "true",
                      "outSR": 3035, "maxAllowableOffset": SIMPLIFY_M}, f"{tag}_{k:05d}.json")
        for f in d.get("features", []):
            g = esri_to_shapely(f.get("geometry") or {})
            if g is not None and not g.is_empty:
                out.append((g, f["attributes"]))
    return out


def cover_pct(boxes, polys):
    """% of each cell box covered by the union of `polys`."""
    pct = np.zeros(len(boxes))
    if not polys:
        return pct
    polys = np.array(polys, dtype=object)
    cell_ix, poly_ix = shapely.STRtree(polys).query(boxes, predicate="intersects")
    parts = shapely.intersection(boxes[cell_ix], polys[poly_ix])
    df = pd.DataFrame({"cell": cell_ix, "geom": parts})
    for c, grp in df.groupby("cell"):
        pct[c] = shapely.union_all(grp["geom"].values).area
    return 100 * pct / (CELL_M * CELL_M)


def tiles(grid):
    keys = set(zip(np.floor(grid.lon / TILE_DEG).astype(int), np.floor(grid.lat / TILE_DEG).astype(int)))
    return sorted((a, b, a + TILE_DEG, b + TILE_DEG) for a, b in keys)


def main():
    grid = read_grid()
    boxes = shapely.box(grid.i * CELL_M, grid.j * CELL_M, (grid.i + 1) * CELL_M, (grid.j + 1) * CELL_M)
    tl = tiles(grid)

    natura = {}
    for t in tl:
        for g, a in features(NATURA, "MS='ES'", t, f"natura_{t[0]}_{t[1]}"):
            natura.setdefault(a["SITECODE"], g)                 # a site can cross several tiles
    print(f"Natura 2000: {len(natura):,} espacios", flush=True)

    codes = sorted(c for v in GROUPS.values() for c in v)
    where = "Code_18 IN (" + ",".join(f"'{c}'" for c in codes) + ")"
    corine = {}
    for i, t in enumerate(tl, 1):
        for g, a in features(CORINE, where, t, f"corine_{t[0]}_{t[1]}"):
            corine.setdefault(a["OBJECTID"], (a["Code_18"], g))
        if i % 10 == 0 or i == len(tl):
            print(f"  CORINE: {i}/{len(tl)} teselas, {len(corine):,} polígonos", flush=True)

    out = pd.DataFrame({"site_id": grid["site_id"]})
    out["natura2000_pct"] = cover_pct(boxes, list(natura.values()))
    for name, cl in GROUPS.items():
        out[f"{name}_pct"] = cover_pct(boxes, [g for c, g in corine.values() if c in cl])
    out = out.round(1)

    ex = out.copy()
    ex["excluded"] = False
    for name, thr in THRESHOLD_PCT.items():
        hit = ex[f"{name}_pct"] >= thr
        ex["excluded"] |= hit
        print(f"  excluidas por {name} (>= {thr} %): {hit.sum():,}")
    print(f"Excluidas en total: {ex.excluded.sum():,} de {len(ex):,} ({ex.excluded.mean():.1%})")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROCESSED / "feat_suelo.parquet", index=False)
    ex.to_parquet(PROCESSED / "exclusions_es_3500.parquet", index=False)
    print(f"-> {PROCESSED / 'feat_suelo.parquet'}\n-> {PROCESSED / 'exclusions_es_3500.parquet'}")


if __name__ == "__main__":
    main()
