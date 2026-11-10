"""Automatic download of reference layers that used to need a manual download.

A manual layer in config.yaml with an `auto` key is fetched the first time it is needed:
  wdpa        protected areas of the country (UNEP-WCMC WDPA feature service) + Natura 2000 subset
  download    plain file (e.g. GEM active faults GeoJSON)
  zip_member  one file out of a zip (e.g. GEM seismic hazard raster from Zenodo)
  jrc_flood   river flood depth tiles of the JRC global flood hazard maps (10 x 10 deg, ~90 m)
"""
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

WDPA_FS = ("https://data-gis.unep-wcmc.org/server/rest/services/ProtectedSites/"
           "The_World_Database_of_Protected_Areas/FeatureServer")
JRC_FLOOD = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/"
NATURA2000 = ("Habitats Directive", "Birds Directive")
PAGE = 1000
# WDPA schema since 2025 (lowercase) -> names used in config.yaml
WDPA_FIELDS = {"site_id": "WDPAID", "name_eng": "NAME", "desig_eng": "DESIG_ENG", "iucn_cat": "IUCN_CAT",
               "status": "STATUS", "realm": "REALM", "rep_area": "REP_AREA"}


def layer_path(lake, cfg, layer) -> Path:
    p = cfg["project"]
    return lake.manual / layer["file"].format(iso3=p["country_iso3"], iso2=p.get("iso2", ""))


def ensure_layer(lake, cfg, layer) -> Path | None:
    """Local path of the layer, downloading it first when config.yaml says how (`auto`)."""
    path = layer_path(lake, cfg, layer)
    if path.exists():
        return path
    kind = layer.get("auto")
    if not kind:
        return None
    lake.log.info("  [%s] descarga automática (%s)…", layer["name"], kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "wdpa":
        fetch_wdpa(lake, cfg)
    elif kind == "download":
        lake.download_file(layer["url"], path, timeout=1800)
    elif kind == "zip_member":
        with tempfile.TemporaryDirectory(prefix="dclake_zip_", ignore_cleanup_errors=True) as td:
            z = lake.download_file(layer["url"], Path(td) / "src.zip", timeout=1800)
            with zipfile.ZipFile(z) as zf:
                member = next(n for n in zf.namelist() if n.lower().endswith(layer.get("member", ".tif")))
                tmp = path.with_suffix(path.suffix + ".part")
                tmp.write_bytes(zf.read(member))
                tmp.replace(path)
    elif kind == "jrc_flood":
        fetch_jrc_flood(lake, cfg, int(layer["rp"]), path)
    return path if path.exists() else None


def fetch_wdpa(lake, cfg) -> None:
    """Protected areas of the country (~100 m generalised) and their Natura 2000 subset.

    Areas reported only as points get a circle of their reported area. Marine-only areas are left out:
    they do not constrain a site on land.
    """
    import geopandas as gpd

    from . import geo
    iso3 = cfg["project"]["country_iso3"]
    frames = []
    for lyr in (1, 0):                       # 1 = polygons, 0 = points
        offset = 0
        while True:
            dest = lake.raw / "wdpa" / f"{iso3}_v2025_layer{lyr}_{offset:05d}.geojson"
            js = lake.get_json(f"{WDPA_FS}/{lyr}/query", dest, params={
                "where": f"iso3='{iso3}'", "outFields": ",".join(WDPA_FIELDS),
                "outSR": 4326, "f": "geojson", "resultOffset": offset, "resultRecordCount": PAGE,
                "maxAllowableOffset": 0.001, "geometryPrecision": 5}, timeout=900, sleep=1,
                validate=lambda b: b.lstrip()[:1] == b"{" and b'"error"' not in b[:300])   # errors are not cached
            if js and "error" in js:
                raise RuntimeError(f"WDPA: {js['error'].get('message')}")
            feats = (js or {}).get("features", [])
            if feats:
                frames.append(gpd.GeoDataFrame.from_features(feats, crs=4326))
            if len(feats) < PAGE:
                break
            offset += PAGE
    if not frames:
        raise RuntimeError(f"WDPA: el servicio no devolvió espacios para {iso3}")
    g = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=4326)
    g = g.rename(columns=WDPA_FIELDS)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    g = g[(g["REALM"].astype(str) != "Marine") & ~g["STATUS"].isin(["Proposed", "Not Reported"])]
    pts = g.geom_type == "Point"
    if pts.any():                            # point-only sites: circle with the reported area
        r_m = np.sqrt(pd.to_numeric(g.loc[pts, "REP_AREA"], errors="coerce").fillna(0.01) * 1e6 / np.pi)
        circles = g.loc[pts].to_crs(geo.EQUAL_AREA).buffer(r_m.values).to_crs(4326)
        g.loc[pts, "geometry"] = circles.values
    out = lake.manual / "wdpa" / f"WDPA_{iso3}.gpkg"
    out.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(out, driver="GPKG")
    n2k = g[g["DESIG_ENG"].fillna("").str.contains("|".join(NATURA2000))]
    if len(n2k):
        o2 = lake.manual / "natura2000" / f"Natura2000_{iso3}.gpkg"
        o2.parent.mkdir(parents=True, exist_ok=True)
        n2k.to_file(o2, driver="GPKG")
    lake.catalog(f"wdpa_{iso3}", "WDPA (UNEP-WCMC)", WDPA_FS, "Términos de uso WDPA (no comercial)")
    lake.log.info("  WDPA %s: %d espacios protegidos (%d de la Red Natura 2000)", iso3, len(g), len(n2k))


def fetch_jrc_flood(lake, cfg, rp: int, folder: Path) -> None:
    """Depth tiles of the JRC global river flood hazard maps (v2.1) that cover the country's boxes."""
    from shapely.geometry import box, shape
    ext = lake.get_json(JRC_FLOOD + "tile_extents.geojson", lake.raw / "jrc_flood" / "tile_extents.geojson")
    boxes = [box(*b) for b in cfg["bboxes"].values()]
    tmp = folder.with_name(folder.name + "_part")
    tmp.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in ext["features"]:
        if any(shape(f["geometry"]).intersects(b) for b in boxes):
            p = f["properties"]
            name = f"ID{p['id']}_{p['name']}_RP{rp}_depth.tif"
            if lake.download_file(f"{JRC_FLOOD}RP{rp}/{name}", tmp / name, timeout=1800) is not None:
                n += 1
    tmp.replace(folder)                      # the folder only appears once its tiles are there
    lake.catalog(f"jrc_flood_rp{rp}", "JRC Global river flood hazard maps v2.1", JRC_FLOOD, "CC BY 4.0")
    lake.log.info("  JRC inundación RP%d: %d teselas", rp, n)
