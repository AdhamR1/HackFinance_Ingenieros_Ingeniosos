"""Known data centers of a country WITHOUT a hand-made list (Japan): data/raw/dc_sites_<tag>.csv.

Spain's dc_sites_es.csv was built by hand from datacentermap.com. For other countries the list is
put together from two public sources, both with exact coordinates:
  * PeeringDB facilities (colocation data centers), already downloaded by the ETL
    (ETL/.cache/<ISO>/processed/grid/known_datacenters.parquet, `python -m dclake grid`)
  * OpenStreetMap: telecom=data_center or building=data_center, through the ohsome API (centre
    of the bounding box of each element, same snapshot as feat_infra.py). OSM adds the big
    campuses that are not colocation (hyperscalers, telecom operators' own buildings).
Points of the two sources closer than DEDUP_M are the same building and count once (PeeringDB
name kept). Every site counts as `operational` (both sources map existing buildings).

Same columns as dc_sites_es.csv, so labels.py reads it unchanged.
Usage (from Modelo/):  $env:DC_COUNTRY = "JPN"; python src/dc_sites.py; python src/labels.py
"""

import json
import time

import numpy as np
import pandas as pd
import requests
from feat_infra import tiles
from pyproj import Transformer
from scipy.spatial import cKDTree

from cells import CRS, ISO, PIPELINE, RAW, REPO, TAG, read_grid

try:  # corporate networks that inspect TLS: use the Windows certificate store
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

URL = "https://api.ohsome.org/v1/elements/bbox"  # /centroid answers 403; the box centre is enough
SNAPSHOT = "2026-07-27"  # the one of feat_infra.py
HEADERS = {"User-Agent": "hackfinance-dc-siting/0.1 (hackathon research)"}
CACHE = PIPELINE / "data" / "cache" / "ohsome" / "datacenter"  # one file per 2-degree tile
FILTER = "telecom=data_center or building=data_center"
DEDUP_M = 300
COLUMNS = [
    "site", "operators", "municipio", "prov", "status", "n_buildings", "precision", "lat",
    "lon", "metro_page", "geocode_source",
]  # fmt: skip


def fetch_tile(s, w, n, e) -> list:
    """OSM data centers of one tile (cached): a single box for the whole country is too slow."""
    dest = CACHE / f"{s}_{w}_{n}_{e}.json"
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))["features"]
    params = {
        "bboxes": f"{w},{s},{e},{n}",
        "filter": FILTER,
        "time": SNAPSHOT,
        "properties": "tags",
    }
    for attempt in range(5):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=600)
            if r.status_code == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(r.text, encoding="utf-8")
                return r.json()["features"]
            why = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as ex:
            why = type(ex).__name__
        wait = 15 * 2**attempt
        print(f"  OSM {s},{w}: falló ({why}), reintento en {wait} s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"No se pudieron bajar los data centers de OSM en {s},{w},{n},{e}")


def osm_datacenters(grid: pd.DataFrame) -> pd.DataFrame:
    feats, seen = [], set()
    tl = tiles(grid)
    for k, t in enumerate(tl, 1):
        got = fetch_tile(*t)
        feats += [f for f in got if f["properties"]["@osmId"] not in seen]
        seen |= {f["properties"]["@osmId"] for f in got}
        print(f"  [{k}/{len(tl)}] OSM lat {t[0]} lon {t[1]}: {len(got)}", flush=True)
    rows = []
    for f in feats:
        p = f["properties"]
        name = p.get("name:en") or p.get("name") or p.get("operator") or "data center (OSM)"
        geom = f["geometry"]
        ring = np.array(
            geom["coordinates"][0] if geom["type"] == "Polygon" else [geom["coordinates"]]
        )
        lon, lat = ring[:, 0].mean(), ring[:, 1].mean()
        rows.append((name, p.get("operator", ""), lon, lat, p["@osmId"]))
    return pd.DataFrame(rows, columns=["site", "operators", "lon", "lat", "osm_id"])


def main():
    grid = read_grid()
    pdb = pd.read_parquet(
        REPO / "ETL" / ".cache" / ISO / "processed" / "grid" / "known_datacenters.parquet",
        columns=["source", "name", "lon", "lat"],
    ).dropna(subset=["lon", "lat"])
    pdb = pdb.rename(columns={"name": "site"}).assign(
        operators=lambda d: d.site, precision="exact", geocode_source=pdb["source"]
    )
    osm = osm_datacenters(grid).assign(precision="exact", geocode_source="OSM")
    print(f"PeeringDB: {len(pdb)}  OpenStreetMap: {len(osm)}")

    to_m = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    xy_p = np.column_stack(to_m.transform(pdb.lon.values, pdb.lat.values))
    xy_o = np.column_stack(to_m.transform(osm.lon.values, osm.lat.values))
    dup = np.zeros(len(osm), bool)
    if len(pdb) and len(osm):
        dup = cKDTree(xy_p).query(xy_o)[0] < DEDUP_M
    # several OSM elements of one campus (buildings + site polygon) also count once
    keep, taken = [], cKDTree(xy_o) if len(osm) else None
    seen = np.zeros(len(osm), bool)
    for k in range(len(osm)):
        if dup[k] or seen[k]:
            continue
        keep.append(k)
        seen[taken.query_ball_point(xy_o[k], DEDUP_M)] = True
    osm = osm.iloc[keep]
    print(f"  OSM ya en PeeringDB o del mismo campus (< {DEDUP_M} m): {len(dup) - len(osm)}")

    s = pd.concat([pdb, osm], ignore_index=True)
    s = s.assign(status="operational", n_buildings=1, municipio="", prov="", metro_page="")
    s = s.drop_duplicates(subset=["lon", "lat"])[COLUMNS]
    dest = RAW / f"dc_sites_{TAG}.csv"
    s.to_csv(dest, index=False, encoding="utf-8")
    print(f"-> {dest}  ({len(s)} emplazamientos)")


if __name__ == "__main__":
    main()
