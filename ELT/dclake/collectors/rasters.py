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


DEM_FACTOR = 2          # each 1 deg tile is read at half resolution (~60 m), the same in every country


def dem_tile_exists(lat: int, lon: int) -> bool:
    """False for tiles that do not exist (open sea); raises on network errors, which must not be cached."""
    import requests
    r = requests.head(dem_tile_url(lat, lon), timeout=60)
    if r.status_code in (403, 404):
        return False
    r.raise_for_status()
    return True


def dem_tile_sums(lat: int, lon: int, crs: str, cell_m: float, factor: int = DEM_FACTOR) -> pd.DataFrame:
    """Terrain sums per grid cell (cell indices ix, iy as in the site_id) for one 1 deg Copernicus tile.

    One remote read per tile instead of one per cell: what makes big countries feasible. Empty for sea tiles.
    """
    import rasterio
    from pyproj import Transformer
    from rasterio.enums import Resampling
    cols = ["ix", "iy", "n_z", "z", "n_s", "slope", "n_t", "tri", "n_a", "sin", "cos"]
    with rasterio.Env(**GDAL_ENV):
        try:
            with rasterio.open("/vsicurl/" + dem_tile_url(lat, lon)) as ds:
                h, w = ds.height // factor, ds.width // factor
                z = ds.read(1, out_shape=(h, w), resampling=Resampling.average, masked=True)
                z = z.astype("float32").filled(np.nan)
                t = ds.transform
                a, e = t.a * ds.width / w, t.e * ds.height / h
                c, f = t.c, t.f
        except rasterio.errors.RasterioIOError:
            if not dem_tile_exists(lat, lon):      # sea: there is no tile
                return pd.DataFrame(columns=cols)
            raise                                   # network failure: not cached, retried in the next run
    lons = c + (np.arange(w) + 0.5) * a
    lats = f + (np.arange(h) + 0.5) * e
    gy, gx = np.gradient(z)
    gx /= (abs(a) * 111320.0 * np.cos(np.radians(lats))).astype("float32")[:, None]
    gy /= np.float32(abs(e) * 110540.0)
    slope = np.hypot(gx, gy) * 100
    aspect = np.arctan2(-gx, gy)
    del gx, gy
    pad = np.pad(z, 1, mode="edge")
    tri = np.zeros_like(z)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di or dj:
                tri += (pad[1 + di:pad.shape[0] - 1 + di, 1 + dj:pad.shape[1] - 1 + dj] - z) ** 2
    tri = np.sqrt(tri)
    del pad
    X, Y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(*np.meshgrid(lons, lats))
    ix = np.floor(np.asarray(X).ravel() / cell_m).astype(np.int64)
    iy = np.floor(np.asarray(Y).ravel() / cell_m).astype(np.int64)
    del X, Y
    x0, y0 = ix.min(), iy.min()
    ny = int(iy.max() - y0 + 1)
    uk, inv = np.unique((ix - x0) * ny + (iy - y0), return_inverse=True)
    inv = inv.ravel()

    def sums(v, mask=None):
        v = v.ravel()
        ok = np.isfinite(v) if mask is None else np.isfinite(v) & mask
        return (np.bincount(inv[ok], weights=v[ok].astype(float), minlength=len(uk)),
                np.bincount(inv[ok], minlength=len(uk)))

    zs, zn = sums(z)
    ss, sn = sums(slope)
    ts, tn = sums(tri)
    steep = slope.ravel() > 1
    sin_s, an = sums(np.sin(aspect), steep)
    cos_s, _ = sums(np.cos(aspect), steep)
    out = pd.DataFrame({"ix": uk // ny + x0, "iy": uk % ny + y0, "n_z": zn, "z": zs, "n_s": sn, "slope": ss,
                        "n_t": tn, "tri": ts, "n_a": an, "sin": sin_s, "cos": cos_s})
    return out[out["n_z"] > 0].reset_index(drop=True)


class DEMCollector(Collector):
    name = "copernicus_dem"
    description = "Altitud, pendiente, orientación y rugosidad (Copernicus DEM GLO-30)"
    source = "Copernicus DEM GLO-30 (AWS Open Data)"
    source_url = "https://registry.opendata.aws/copernicus-dem/"
    license = "Copernicus DEM licence (uso libre con atribución)"
    spatial_resolution_m = 60       # GLO-30 read at half resolution (DEM_FACTOR)
    confidence = 0.9
    fields = {"sites_static": ["elevation_m", "slope_pct", "aspect_deg", "terrain_ruggedness"]}

    def run(self, sites):
        """Tile by tile: each 1 deg tile is read once and summed into the cells it covers (cached per tile)."""
        from concurrent.futures import ThreadPoolExecutor

        import geopandas as gpd
        from tqdm import tqdm
        pj = self.cfg["project"]
        cell_m = float(pj["cell_size_m"])
        b = gpd.GeoSeries(sites.geometry.values, crs=geo.EQUAL_AREA).to_crs(4326).bounds
        tiles = sorted({(la, lo) for r in b.itertuples()
                        for la in range(math.floor(r.miny), math.floor(r.maxy) + 1)
                        for lo in range(math.floor(r.minx), math.floor(r.maxx) + 1)})
        cache = self.lake.processed / "dem_tiles" / f"{int(cell_m)}m_f{DEM_FACTOR}"
        cache.mkdir(parents=True, exist_ok=True)

        def path(t):
            return cache / f"{t[0]:+03d}_{t[1]:+04d}.parquet"

        def cached_ok(t):
            p = path(t)
            if not p.exists():
                return False
            if len(pd.read_parquet(p, columns=["ix"])):
                return True
            try:        # empty = sea; an older run could have cached a network failure as empty
                return not dem_tile_exists(*t)
            except Exception:
                return False

        todo = [t for t in tiles if not cached_ok(t)]
        self.log.info("  DEM: %d teselas de 1° (%d ya calculadas)", len(tiles), len(tiles) - len(todo))

        def one(t):
            try:
                dem_tile_sums(t[0], t[1], geo.EQUAL_AREA, cell_m).to_parquet(path(t), index=False)  # empty = sea
            except Exception as e:      # retried in the next run
                self.log.warning("  DEM tesela %s: %s", t, e)

        with ThreadPoolExecutor(max_workers=6) as ex:   # GDAL and numpy release the GIL
            list(tqdm(ex.map(one, todo), total=len(todo), desc="DEM teselas"))
        frames = [pd.read_parquet(path(t)) for t in tiles if path(t).exists()]
        frames = [f for f in frames if len(f)]
        self.lake.catalog("copernicus_dem_glo30", self.source, self.source_url, self.license)
        if not frames:
            return
        s = pd.concat(frames, ignore_index=True).groupby(["ix", "iy"], as_index=False).sum()
        s["site_id"] = pj["country_iso3"] + "_" + s["ix"].astype(str) + "_" + s["iy"].astype(str)
        s = s[s["site_id"].isin(set(sites["site_id"]))]
        self.stage("sites_static", pd.DataFrame({
            "site_id": s["site_id"].values,
            "elevation_m": (s["z"] / s["n_z"]).values,
            "slope_pct": (s["slope"] / s["n_s"].where(s["n_s"] > 0)).values,
            "aspect_deg": (np.degrees(np.arctan2(s["sin"], s["cos"])) % 360).where(s["n_a"] > 0).values,
            "terrain_ruggedness": (s["tri"] / s["n_t"].where(s["n_t"] > 0)).values}))

    def run_per_cell(self, sites):
        """Former method (one remote read per cell): kept for comparison on a few cells."""
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
        area = gpd.GeoSeries([box(*b).buffer(1) for b in bb.values()], crs=4326)   # the country's boxes
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
