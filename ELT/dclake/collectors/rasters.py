"""Raster and vector layers: Copernicus DEM, remote COG/VRT rasters and manually downloaded layers."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .. import geo
from .base import Collector

DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
           "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")

GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff,.vrt",
                GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="TRUE")


def _os_ca_bundle() -> str | None:
    """PEM with the OS trusted roots (incl. corporate TLS-inspection CAs) + certifi, for GDAL/curl."""
    import ssl
    import tempfile
    from pathlib import Path
    p = Path(tempfile.gettempdir()) / "dclake_ca_bundle.pem"
    if p.exists():
        return str(p)
    try:
        ctx = ssl.create_default_context()
        ctx.load_default_certs()
        pems = [ssl.DER_cert_to_PEM_cert(der) for der in ctx.get_ca_certs(binary_form=True)]
        try:
            import certifi
            pems.append(Path(certifi.where()).read_text(encoding="utf-8"))
        except Exception:
            pass
        p.write_text("\n".join(pems), encoding="utf-8")
        return str(p)
    except Exception:
        return None


_ca = _os_ca_bundle()
if _ca:
    GDAL_ENV.update(GDAL_CURL_CA_BUNDLE=_ca, CURL_CA_BUNDLE=_ca)


def dem_tile_url(lat: int, lon: int) -> str:
    return DEM_URL.format(ns="N" if lat >= 0 else "S", lat=abs(lat), ew="E" if lon >= 0 else "W", lon=abs(lon))


def terrain_stats(z: np.ndarray, dx: float, dy: float) -> dict:
    """Mean elevation, slope (%), circular-mean aspect (deg) and Terrain Ruggedness Index."""
    z = np.where(np.isfinite(z), z, np.nan)
    if np.isnan(z).all():
        return {}
    gy, gx = np.gradient(z, dy, dx)
    slope = np.hypot(gx, gy) * 100
    aspect = (np.degrees(np.arctan2(-gx, gy)) + 360) % 360
    ok = np.isfinite(aspect) & (slope > 1)
    asp = (np.degrees(np.arctan2(np.nanmean(np.sin(np.radians(aspect[ok]))),
                                 np.nanmean(np.cos(np.radians(aspect[ok]))))) % 360) if ok.any() else np.nan
    pad = np.pad(z, 1, mode="edge")
    tri = np.zeros_like(z)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di or dj:
                tri += (pad[1 + di:pad.shape[0] - 1 + di, 1 + dj:pad.shape[1] - 1 + dj] - z) ** 2
    return {"elevation_m": float(np.nanmean(z)), "slope_pct": float(np.nanmean(slope)),
            "aspect_deg": float(asp), "terrain_ruggedness": float(np.nanmean(np.sqrt(tri)))}


def dem_stats_bounds(lon0, lat0, lon1, lat1, target_px: int = 100) -> dict:
    """Read Copernicus GLO-30 over a lon/lat box (reduced resolution) and compute terrain stats."""
    import rasterio
    from rasterio.windows import from_bounds
    arrays = []
    with rasterio.Env(**GDAL_ENV):
        for la in range(math.floor(lat0), math.floor(lat1) + 1):
            for lo in range(math.floor(lon0), math.floor(lon1) + 1):
                url = "/vsicurl/" + dem_tile_url(la, lo)
                try:
                    with rasterio.open(url) as ds:
                        b = (max(lon0, lo), max(lat0, la), min(lon1, lo + 1), min(lat1, la + 1))
                        w = from_bounds(*b, transform=ds.transform)
                        frac = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]) / ((lon1 - lon0) * (lat1 - lat0)))
                        n = max(8, int(target_px * math.sqrt(frac)))
                        z = ds.read(1, window=w, out_shape=(n, n), boundless=True, fill_value=np.nan,
                                    resampling=rasterio.enums.Resampling.average).astype(float)
                        arrays.append((z, b))
                except rasterio.errors.RasterioIOError:
                    continue  # ocean tile, does not exist
    if not arrays:
        return {}
    stats = []
    for z, b in arrays:
        latm = (b[1] + b[3]) / 2
        dx = (b[2] - b[0]) * 111320 * math.cos(math.radians(latm)) / z.shape[1]
        dy = (b[3] - b[1]) * 110540 / z.shape[0]
        s = terrain_stats(z, dx, dy)
        if s:
            stats.append((s, np.isfinite(z).sum()))
    if not stats:
        return {}
    w = np.array([n for _, n in stats], dtype=float)
    return {k: float(np.average([s[k] for s, _ in stats], weights=w)) for k in stats[0][0]}


class DEMCollector(Collector):
    name = "copernicus_dem"
    description = "Altitud, pendiente, orientación y rugosidad (Copernicus DEM GLO-30)"
    source = "Copernicus DEM GLO-30 (AWS Open Data)"
    source_url = "https://registry.opendata.aws/copernicus-dem/"
    license = "Copernicus DEM licence (uso libre con atribución)"
    spatial_resolution_m = 50
    confidence = 0.9
    fields = {"sites_static": ["elevation_m", "slope_pct", "aspect_deg", "terrain_ruggedness"]}

    def run(self, sites):
        from concurrent.futures import ThreadPoolExecutor

        import geopandas as gpd
        from tqdm import tqdm
        b84 = gpd.GeoSeries(sites.geometry.values, crs=geo.EQUAL_AREA).to_crs(4326).bounds
        cache = self.lake.processed / "dem_stats.parquet"      # per-cell results survive interruptions
        done = pd.read_parquet(cache) if cache.exists() else pd.DataFrame(columns=["site_id"])
        todo = [(sid, r) for sid, (_, r) in zip(sites["site_id"], b84.iterrows()) if sid not in set(done["site_id"])]

        def one(item):
            sid, r = item
            try:
                return {"site_id": sid, **dem_stats_bounds(r.minx, r.miny, r.maxx, r.maxy)}
            except Exception as e:
                self.log.debug("  DEM %s: %s", sid, e)
                return {"site_id": sid}

        rows = []
        with ThreadPoolExecutor(max_workers=8) as ex:   # GDAL releases the GIL while reading over HTTP
            for i, row in enumerate(tqdm(ex.map(one, todo), total=len(todo), desc="DEM")):
                rows.append(row)
                if (i + 1) % 1000 == 0 or i + 1 == len(todo):
                    done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
                    done.to_parquet(cache, index=False)
                    rows = []
        self.lake.catalog("copernicus_dem_glo30", self.source, self.source_url, self.license)
        self.stage("sites_static", done[done["site_id"].isin(sites["site_id"])])


def _sample_raster(path_or_url: str, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    import rasterio
    from rasterio.warp import transform
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(path_or_url) as ds:
            xs, ys = transform("EPSG:4326", ds.crs, list(lon), list(lat))
            vals = np.array([v[0] for v in ds.sample(zip(xs, ys))], dtype=float)
            if ds.nodata is not None:
                vals[vals == ds.nodata] = np.nan
    return vals


def _zonal_sum(path: str, lon, lat, radius_km: float) -> np.ndarray:
    import rasterio
    from rasterio.warp import transform
    out = []
    with rasterio.open(path) as ds:
        xs, ys = transform("EPSG:4326", ds.crs, list(lon), list(lat))
        geographic = ds.crs.is_geographic
        px = abs(ds.transform.a)
        for x, y, la in zip(xs, ys, lat):
            r = radius_km * 1000 if not geographic else radius_km / (111.32 * math.cos(math.radians(la)))
            win = rasterio.windows.from_bounds(x - r, y - r, x + r, y + r, transform=ds.transform)
            a = ds.read(1, window=win, boundless=True, fill_value=0).astype(float)
            if ds.nodata is not None:
                a[a == ds.nodata] = 0
            n = a.shape[0]
            yy, xx = np.mgrid[:n, :a.shape[1]]
            c = (n - 1) / 2
            mask = ((yy - c) ** 2 + (xx - (a.shape[1] - 1) / 2) ** 2) * px ** 2 <= r ** 2
            out.append(float(np.nansum(np.where(mask, a, 0))))
    return np.array(out)


class RemoteRastersCollector(Collector):
    name = "remote_rasters"
    description = "Rásteres remotos (SoilGrids…) leídos por HTTP en los centroides"
    confidence = 0.6
    spatial_resolution_m = 250

    def declared_fields(self):
        return {"sites_static": [r["field"] for r in self.cfg.get("remote_rasters", [])]}

    def run(self, sites):
        df = pd.DataFrame({"site_id": sites["site_id"].values})
        for r in self.cfg.get("remote_rasters", []):
            try:
                v = _sample_raster("/vsicurl/" + r["url"], sites["lon"].values, sites["lat"].values)
                v = v * r.get("scale", 1)
                df[r["field"]] = [f"WRB_{int(x)}" if np.isfinite(x) else pd.NA for x in v] if r.get("categorical") else v
                self.lake.catalog(f"raster_{r['field']}", r.get("source", ""), r["url"], r.get("license", ""))
            except Exception as e:
                self.log.warning("  %s no disponible: %s", r["field"], e)
        self.stage("sites_static", df)

    def write_lineage(self, **kw):
        info = {}
        for r in self.cfg.get("remote_rasters", []):
            info[f"sites_static.{r['field']}"] = {"source": r.get("source", ""), "source_url": r["url"],
                                                  "license": r.get("license", ""), "is_synthetic": False,
                                                  "imputation_method": "ninguno", "spatial_resolution_m": 250,
                                                  "pipeline_version": self.cfg["project"]["pipeline_version"]}
        self.lake.write_lineage(self.name, info)


class ManualLayersCollector(Collector):
    """Layers that need a manual download (registration, forms). Missing files are skipped."""
    name = "manual_layers"
    description = "Capas descargadas a mano en data_lake/raw/manual/"

    def declared_fields(self):
        f = []
        for layer in self.cfg.get("manual_layers", []):
            f += [op["field"] for op in layer["ops"]]
        return {"sites_static": f}

    def run(self, sites):
        import geopandas as gpd
        from shapely.geometry import box
        pts = geo.site_points(sites)
        df = pd.DataFrame({"site_id": sites["site_id"].values})
        self._done = []
        bb = self.cfg["bboxes"]
        area = gpd.GeoSeries([box(*bb["peninsula_baleares"]).buffer(1), box(*bb["canarias"]).buffer(1)], crs=4326)
        for layer in self.cfg.get("manual_layers", []):
            path = self.lake.manual / layer["file"]
            if not path.exists():
                self.log.warning("  [%s] falta %s (descarga: %s)", layer["name"], path, layer.get("download", "?"))
                continue
            try:
                if layer["kind"] == "vector":
                    g = gpd.read_file(path, mask=area.to_crs(gpd.read_file(path, rows=1).crs))
                    if layer.get("filter"):
                        g = g.query(layer["filter"])
                    g = g.to_crs(geo.EQUAL_AREA)
                    for op in layer["ops"]:
                        f = op["field"]
                        if op["op"] == "distance_km":
                            df[f] = geo.nearest(pts, g)["dist_km"].values
                        elif op["op"] == "contains":
                            df[f] = geo.contains(pts, g)
                        elif op["op"] == "nearest_attr":
                            df[f] = geo.nearest(pts, g, [op["attr"]])[op["attr"]].values
                        elif op["op"] == "point_attr":
                            df[f] = geo.point_attr(pts, g, op["attr"])
                        elif op["op"] == "count_within_km":
                            df[f] = geo.count_within(geo.xy(pts), geo.xy(g), op["radius_km"])
                else:
                    for op in layer["ops"]:
                        f = op["field"]
                        if op["op"] == "sample":
                            v = _sample_raster(str(path), sites["lon"].values, sites["lat"].values)
                            if "nodata_as" in op:
                                v = np.where(np.isnan(v), op["nodata_as"], v)
                            df[f] = v * op.get("scale", 1)
                        elif op["op"] == "zonal_sum_km":
                            df[f] = _zonal_sum(str(path), sites["lon"].values, sites["lat"].values, op["radius_km"])
                self._done.append(layer)
                self.lake.catalog(f"manual_{layer['name']}", layer["name"], layer.get("download", ""), layer.get("license", ""))
                self.log.info("  [%s] ok", layer["name"])
            except Exception as e:
                self.log.error("  [%s] error: %s", layer["name"], e)
        self.stage("sites_static", df)

    def write_lineage(self, **kw):
        info = {}
        for layer in getattr(self, "_done", []):
            for op in layer["ops"]:
                info[f"sites_static.{op['field']}"] = {
                    "source": layer["name"], "source_url": layer.get("download", ""), "license": layer.get("license", ""),
                    "is_synthetic": False, "imputation_method": "ninguno",
                    "pipeline_version": self.cfg["project"]["pipeline_version"]}
        self.lake.write_lineage(self.name, info)
