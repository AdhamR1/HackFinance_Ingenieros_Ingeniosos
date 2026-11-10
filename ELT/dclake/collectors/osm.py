"""OpenStreetMap layers via Overpass (whole of Spain once, then distances per cell)."""
from __future__ import annotations

import json
import re
import time

import numpy as np
import pandas as pd

from .. import geo
from .base import Collector

# Overpass admits queries according to the resources they declare: huge claims
# ([timeout:1200][maxsize:4e9]) are rejected with 504 when the server is busy.
# So we ask for modest limits and, if the whole-country query fails, split it in tiles.
HEADER = "[out:json][timeout:{timeout}][maxsize:{maxsize}];"
AREA = 'area["ISO3166-1"="{iso2}"][admin_level=2]->.a;'
AREA_LIMITS = (600, 1024 ** 3)          # whole Spain: 10 min, 1 GiB
TILE_LIMITS = (300, 512 * 1024 ** 2)    # each tile: 5 min, 512 MiB
TILE_DEG = 4.0
KEEP_TAGS = ["name", "voltage", "plant:source", "plant:output:electricity", "usage", "highway",
             "military", "aeroway", "amenity", "historic"]

# name, overpass body, output mode
LAYERS = [
    ("substations", 'nwr["power"="substation"](area.a);', "center"),
    ("power_lines", 'way["power"="line"](area.a);', "geom"),
    ("power_plants", 'nwr["power"="plant"](area.a);', "center"),
    ("roads_main", 'way["highway"~"^(motorway|trunk)$"](area.a);', "geom"),
    ("roads_primary", 'way["highway"="primary"](area.a);', "geom"),
    ("junctions", 'node["highway"="motorway_junction"](area.a);', "center"),
    ("railways", 'way["railway"="rail"](area.a);', "geom"),
    ("quarries", 'nwr["landuse"="quarry"](area.a);', "center"),
    ("military", 'nwr["landuse"="military"](area.a);', "center"),
    ("military_airfields", 'nwr["military"="airfield"](area.a);nwr["aeroway"="aerodrome"]["military"](area.a);', "center"),
    ("fire_stations", 'nwr["amenity"="fire_station"](area.a);', "center"),
    ("receptors", 'nwr["amenity"~"^(school|hospital|nursing_home)$"](area.a);', "center"),
    ("residential", 'nwr["landuse"="residential"](area.a);', "center"),
    ("helipads", 'nwr["aeroway"~"^(heliport|helipad)$"](area.a);', "center"),
    ("heritage", 'nwr["historic"~"^(archaeological_site|castle|monument|ruins)$"](area.a);', "center"),
]

RENEWABLE = {"solar", "wind", "hydro", "biomass", "geothermal", "biogas", "biofuel", "tidal", "wave"}


def _parse_mw(v) -> float:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    m = re.search(r"([\d.,]+)\s*(gw|mw|kw|w)?", str(v).lower())
    if not m:
        return np.nan
    x = float(m.group(1).replace(",", "."))
    unit = m.group(2) or "mw"
    return x * {"gw": 1000, "mw": 1, "kw": 1e-3, "w": 1e-6}[unit]


def _parse_kv(v) -> float:
    vals = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(v or ""))]
    vals = [x / 1000 if x > 1000 else x for x in vals]
    return max(vals) if vals else np.nan


def overpass_complete(content: bytes) -> bool:
    """False for error pages and for truncated answers (HTTP 200 + 'runtime error' remark)."""
    if not content.lstrip()[:1] == b"{":
        return False
    tail = content[-3000:]
    return b"runtime error" not in tail and b"runtime remark" not in tail


def _tiles(cfg) -> list[tuple[float, float, float, float]]:
    """(south, west, north, east) tiles of TILE_DEG covering the Spanish bounding boxes."""
    out = []
    for w, s, e, n in cfg["bboxes"].values():
        for x in np.arange(w, e, TILE_DEG):
            for y in np.arange(s, n, TILE_DEG):
                out.append((round(y, 3), round(x, 3), round(min(y + TILE_DEG, n), 3), round(min(x + TILE_DEG, e), 3)))
    return out


def _overpass_fetch(lake, cfg, q: str, dest, timeout: int, label: str) -> bool:
    """POST one query to the configured endpoints (2 attempts each, with a pause). True if saved."""
    for ep in cfg["overpass_endpoints"]:
        for attempt in range(2):
            try:
                lake.log.info("  Overpass %s (%s)…", label, ep.split("/")[2])
                if lake.cached_get(ep, dest, method="POST", data={"data": q}, timeout=timeout + 60,
                                   validate=overpass_complete, retry=False):
                    time.sleep(2)
                    return True
                lake.log.warning("  Overpass %s: respuesta incompleta en %s", label, ep)
            except Exception as e:
                lake.log.warning("  Overpass %s falló en %s: %s", label, ep, str(e)[:200])
            time.sleep(15 * (attempt + 1))
    return False


def overpass_elements(lake, cfg, name: str, body: str, out: str) -> list[dict]:
    """Elements of one layer: whole-Spain area query, or bbox tiles if that fails."""
    tail = "out center tags;" if out == "center" else "out tags geom;"
    raw = lake.raw / "osm" / f"{name}.json"
    if not raw.exists() and not (lake.raw / "osm" / name).is_dir():   # already being fetched in tiles: go on
        t, m = AREA_LIMITS
        _overpass_fetch(lake, cfg, HEADER.format(timeout=t, maxsize=m) + AREA.format(iso2=cfg["project"].get("iso2", "ES")) + "(" + body + ");" + tail, raw, t, name)
    if raw.exists():
        return json.loads(raw.read_text(encoding="utf-8")).get("elements", [])

    lake.log.info("  Overpass %s: divido la consulta en teselas de %.0f°", name, TILE_DEG)
    t, m = TILE_LIMITS
    seen, elements, missing = set(), [], 0
    for i, (s, w, n, e) in enumerate(_tiles(cfg)):
        dest = lake.raw / "osm" / name / f"tile_{i:02d}.json"
        q = HEADER.format(timeout=t, maxsize=m) + "(" + body.replace("(area.a)", f"({s},{w},{n},{e})") + ");" + tail
        if not dest.exists() and not _overpass_fetch(lake, cfg, q, dest, t, f"{name} tesela {i}"):
            missing += 1
            continue
        for el in json.loads(dest.read_text(encoding="utf-8")).get("elements", []):
            k = (el["type"], el["id"])
            if k not in seen:
                seen.add(k)
                elements.append(el)
    if missing:
        raise RuntimeError(f"{missing} teselas de {name} sin descargar; vuelve a ejecutar para reintentarlas")
    return elements


def overpass_layer(lake, cfg, name: str, body: str, out: str):
    """Run (or load from cache) one Overpass layer and return a GeoDataFrame in EPSG:3035."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point

    cache = lake.processed / "osm" / f"{name}.parquet"
    if cache.exists():
        return gpd.read_parquet(cache)
    elements = overpass_elements(lake, cfg, name, body, out)
    rows, geoms = [], []
    for el in elements:
        tags = el.get("tags", {})
        g = None
        if out == "center":
            if "lat" in el:
                g = Point(el["lon"], el["lat"])
            elif "center" in el:
                g = Point(el["center"]["lon"], el["center"]["lat"])
        else:
            pts = [(p["lon"], p["lat"]) for p in el.get("geometry", []) if p]
            if len(pts) >= 2:
                g = LineString(pts)
        if g is None:
            continue
        rows.append({k: tags.get(k) for k in KEEP_TAGS} | {"osm_id": f'{el["type"][0]}{el["id"]}'})
        geoms.append(g)
    cols = KEEP_TAGS + ["osm_id"]
    gdf = gpd.GeoDataFrame(pd.DataFrame(rows, columns=cols), geometry=gpd.GeoSeries(geoms, crs="EPSG:4326"),
                           crs="EPSG:4326").to_crs(geo.EQUAL_AREA)
    cache.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(cache)
    lake.catalog(f"osm_{name}", "OpenStreetMap (Overpass)", cfg["overpass_endpoints"][0], "ODbL 1.0")
    return gdf


class OSMCollector(Collector):
    name = "osm"
    description = "Infraestructura, transporte y entorno desde OpenStreetMap"
    source = "OpenStreetMap (Overpass API)"
    source_url = "https://www.openstreetmap.org"
    license = "ODbL 1.0"
    confidence = 0.7
    fields = {"sites_static": [
        "dist_substation_km", "substation_voltage_kv", "n_substations_20km", "dist_hv_line_km",
        "dist_400kv_line_km", "dist_power_plant_km", "nearest_plant_type", "gen_capacity_50km_mw",
        "renewable_capacity_50km_mw", "dist_nuclear_plant_km", "dist_highway_km", "dist_primary_road_km",
        "dist_motorway_junction_km", "road_density_km_km2", "dist_railway_km", "dist_freight_rail_km",
        "dist_infra_corridor_km", "dist_mine_quarry_km", "dist_military_km", "dist_military_airbase_km",
        "dist_fire_station_km", "n_sensitive_receptors_2km", "dist_residential_km", "dist_heliport_km",
        "dist_heritage_site_km"]}

    def run(self, sites):
        L = {}
        wanted = (self.cfg.get("osm") or {}).get("layers")       # DCLAKE_OSM_LAYERS=a,b: only these layers
        wanted = {s.strip() for s in str(wanted).split(",") if s.strip()} if wanted else None
        for name, body, out in LAYERS:
            if wanted and name not in wanted:
                L[name] = None
                continue
            try:
                L[name] = overpass_layer(self.lake, self.cfg, name, body, out)
            except Exception as e:
                self.log.error("  capa %s no disponible: %s", name, e)
                L[name] = None
        pts = geo.site_points(sites)
        sxy = geo.xy(pts)
        df = pd.DataFrame({"site_id": sites["site_id"].values})

        def dist(layer, col, attrs=None, filt=None):
            g = L.get(layer)
            if g is not None and filt is not None:
                g = g[filt(g)]
            nn = geo.nearest(pts, g, attrs)
            df[col] = nn["dist_km"].values
            return nn

        nn = dist("substations", "dist_substation_km", ["voltage"])
        df["substation_voltage_kv"] = [_parse_kv(v) for v in nn["voltage"]]
        if L.get("substations") is not None:
            df["n_substations_20km"] = geo.count_within(sxy, geo.xy(L["substations"]), 20)
        dist("power_lines", "dist_hv_line_km")
        dist("power_lines", "dist_400kv_line_km", filt=lambda g: g["voltage"].map(_parse_kv) >= 345)

        pp = L.get("power_plants")
        if pp is not None and len(pp):
            pp = pp.assign(mw=pp["plant:output:electricity"].map(_parse_mw),
                           src=pp["plant:source"].fillna("desconocida").str.lower())
            nn = geo.nearest(pts, pp, ["src"])
            df["dist_power_plant_km"] = nn["dist_km"].values
            df["nearest_plant_type"] = nn["src"].values
            pxy = geo.xy(pp)
            df["gen_capacity_50km_mw"] = geo.count_within(sxy, pxy, 50, pp["mw"].values)
            ren = pp["src"].map(lambda s: any(r in s for r in RENEWABLE)).values
            df["renewable_capacity_50km_mw"] = geo.count_within(sxy, pxy[ren], 50, pp["mw"].values[ren])
            nuc = pp[pp["src"].str.contains("nuclear")]
            df["dist_nuclear_plant_km"] = geo.nearest(pts, nuc)["dist_km"].values

        dist("roads_main", "dist_highway_km")
        dist("roads_primary", "dist_primary_road_km")
        dist("junctions", "dist_motorway_junction_km")
        roads = [g for g in (L.get("roads_main"), L.get("roads_primary")) if g is not None]
        if roads:
            import geopandas as gpd
            allr = gpd.GeoDataFrame(pd.concat(roads, ignore_index=True), crs=geo.EQUAL_AREA)
            df["road_density_km_km2"] = geo.length_within(pts, allr, 2) / (np.pi * 2 ** 2)
        dist("railways", "dist_railway_km")
        dist("railways", "dist_freight_rail_km", filt=lambda g: g["usage"].fillna("").str.contains("freight"))
        df["dist_infra_corridor_km"] = df[["dist_highway_km", "dist_railway_km"]].min(axis=1)
        dist("quarries", "dist_mine_quarry_km")
        dist("military", "dist_military_km")
        dist("military_airfields", "dist_military_airbase_km")
        dist("fire_stations", "dist_fire_station_km")
        if L.get("receptors") is not None:
            df["n_sensitive_receptors_2km"] = geo.count_within(sxy, geo.xy(L["receptors"]), 2)
        dist("residential", "dist_residential_km")
        dist("helipads", "dist_heliport_km")
        dist("heritage", "dist_heritage_site_km")
        self.stage("sites_static", df)

    def write_lineage(self, **kw):
        super().write_lineage(per_field={
            "dist_residential_km": {"notes": "Distancia al centroide del polígono residencial (aproximada)", "confidence": 0.5},
            "gen_capacity_50km_mw": {"notes": "Suma de plant:output:electricity; centrales sin etiqueta cuentan 0", "confidence": 0.4},
            "renewable_capacity_50km_mw": {"confidence": 0.4},
        })
