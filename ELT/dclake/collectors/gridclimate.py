"""Daily climate outside Europe for every cell at once, without keys.

- gridMET (contiguous US, 1/24 deg ~4 km): one file per variable and year for the whole country,
  kept in the cache because every part (strip of cells) of the country reads it.
- NASA POWER (any country; MERRA-2 0.5 x 0.625 deg, radiation CERES 1 deg): regional API in boxes
  of 10 x 10 deg, one parameter per request.

Both are converted to the E-OBS variables (tg, tx, tn, rr, hu, fg, qq) and go through the same
daily_fields as E-OBS, so every country gets the same dictionary fields computed the same way.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .base import Collector
from .eobs import MIN_YEAR_COVERAGE, EOBSCollector, stage_daily_climate

GRIDMET = "https://www.northwestknowledge.net/metdata/data/{var}_{year}.nc"
GRIDMET_VARS = {"tmmx": "tx", "tmmn": "tn", "pr": "rr", "rmax": "rmax", "rmin": "rmin", "vs": "fg", "srad": "qq"}
POWER = "https://power.larc.nasa.gov/api/temporal/daily/regional"
POWER_PARAMS = {"T2M": "tg", "T2M_MAX": "tx", "T2M_MIN": "tn", "PRECTOTCORR": "rr", "RH2M": "hu",
                "WS10M": "fg", "ALLSKY_SFC_SW_DWN": "qq"}
POWER_BOX_DEG = 10          # API limit per request, in latitude and in longitude
MODEL_NOTES = {
    "free_cooling_hours": "Ciclo diario coseno entre tn y tx (máximo a las 15 h)",
    "adiabatic_cooling_hours": "Ciclo diario coseno y punto de rocío constante en el día",
    "wetbulb_max_c": "Stull (2011) con tx y la humedad relativa a la hora de tx",
}


def nearest_valid(lon_px, lat_px, valid, lon, lat, max_deg):
    """(iy, ix, ok): nearest pixel with data for each cell; ok=False if it is farther than max_deg."""
    n = len(lon)
    iy, ix = np.nonzero(valid)
    if len(iy) == 0 or n == 0:
        return np.zeros(n, int), np.zeros(n, int), np.zeros(n, bool)
    LON, LAT = np.meshgrid(lon_px, lat_px)
    k = np.cos(np.radians(float(np.mean(lat))))
    d, j = cKDTree(np.column_stack([LON[iy, ix] * k, LAT[iy, ix]])).query(np.column_stack([lon * k, lat]))
    return iy[j], ix[j], d <= max_deg


def _coverage_ok(a: np.ndarray) -> bool:
    """A year with data on fewer than MIN_YEAR_COVERAGE of its days is left empty (it would bias annual sums)."""
    return bool(np.isfinite(a).any(axis=1).mean() >= MIN_YEAR_COVERAGE)


class GridMETCollector(Collector):
    name = "gridmet"
    climate_key = "gridmet"
    description = "Clima diario gridMET (EEUU continental, 4 km, sin clave) para todas las celdas"
    source = "gridMET (Abatzoglou 2013, Climatology Lab / Northwest Knowledge Network)"
    source_url = "https://www.climatologylab.org/gridmet.html"
    license = "Dominio público (CC0)"
    spatial_resolution_m = 4000
    confidence = 0.85
    fields = EOBSCollector.fields

    def _file(self, var: str, year: int):
        dest = self.lake.raw / "gridmet" / f"{var}_{year}.nc"
        if not dest.exists():
            self.log.info("  gridMET %s %d: descarga (~150 MB)…", var, year)
        return self.lake.download_file(GRIDMET.format(var=var, year=year), dest, timeout=3600)

    @staticmethod
    def _values(path, dy, lon, lat) -> np.ndarray:
        """(days x cells) of one variable, reading only the window around these cells."""
        import xarray as xr
        out = np.full((len(dy), len(lon)), np.nan, dtype="float32")
        with xr.open_dataset(path) as ds:
            da = ds[[v for v in ds.data_vars if v != "crs"][0]]
            tdim, ydim, xdim = da.dims
            la, lo = ds[ydim].values, ds[xdim].values
            yi = np.nonzero((la >= lat.min() - 0.2) & (la <= lat.max() + 0.2))[0]
            xi = np.nonzero((lo >= lon.min() - 0.2) & (lo <= lon.max() + 0.2))[0]
            if len(yi) == 0 or len(xi) == 0:
                return out
            win = da.isel({ydim: slice(yi.min(), yi.max() + 1), xdim: slice(xi.min(), xi.max() + 1)})
            v = win.values.astype("float32")
            iy, ix, ok = nearest_valid(win[xdim].values, win[ydim].values, np.isfinite(v).mean(axis=0) > 0.5,
                                       lon, lat, 0.1)
            a = np.full((v.shape[0], len(lon)), np.nan, dtype="float32")
            a[:, ok] = v[:, iy[ok], ix[ok]]
            t = pd.DatetimeIndex(win[tdim].values).normalize()
        return pd.DataFrame(a, index=t).reindex(dy).to_numpy(dtype="float32")

    def run(self, sites):
        p = self.cfg["period"]
        days = pd.date_range(p["start"], p["end"], freq="D")
        lon, lat = sites["lon"].to_numpy(float), sites["lat"].to_numpy(float)
        ids = sites["site_id"].astype(str).to_numpy()
        for y in sorted(set(days.year)):
            dy = days[days.year == y]
            raw = {}
            for var, key in GRIDMET_VARS.items():
                f = self._file(var, y)
                a = self._values(f, dy, lon, lat) if f is not None else np.full((len(dy), len(ids)), np.nan, "float32")
                if f is None or not _coverage_ok(a):
                    self.log.warning("  gridMET %s %d: sin datos suficientes; se deja vacío", var, y)
                    a[:] = np.nan
                raw[key] = a
            for k in ("tx", "tn"):
                if np.isfinite(raw[k]).any() and np.nanmedian(raw[k]) > 150:     # Kelvin
                    raw[k] = raw[k] - np.float32(273.15)
            vals = {"tg": np.full_like(raw["tx"], np.nan), "tx": raw["tx"], "tn": raw["tn"], "rr": raw["rr"],
                    "hu": (raw["rmax"] + raw["rmin"]) / 2, "fg": raw["fg"], "qq": raw["qq"]}
            stage_daily_climate(self, ids, dy, vals)
            self.log.info("  gridMET %d: %d celdas x %d días; celdas con píxel válido: %.0f %%", y, len(ids), len(dy),
                          100 * np.isfinite(vals["tx"]).any(axis=0).mean())
        self.lake.catalog("gridmet", self.source, self.source_url, self.license)

    def write_lineage(self, **kw):
        model = {"imputation_method": "modelo", "confidence": 0.6}
        super().write_lineage(per_field={
            **{f: {**model, "notes": n} for f, n in MODEL_NOTES.items()},
            "t2m_mean_c": {"imputation_method": "derivado", "notes": "(tmmx + tmmn) / 2"},
            "rh_mean_pct": {"imputation_method": "derivado", "notes": "(rmax + rmin) / 2"},
            "td2m_mean_c": {"imputation_method": "derivado", "notes": "Magnus a partir de la temperatura y humedad medias"},
            "ssrd_kwh_m2": {"notes": "gridMET srad (media diaria W/m2) x 24 h / 1000"},
        })


class NASAPowerCollector(Collector):
    name = "nasapower"
    climate_key = "nasapower"
    description = "Clima diario NASA POWER (MERRA-2 0,5°, global, sin clave) para todas las celdas"
    source = "NASA POWER daily regional API (MERRA-2; radiación CERES SYN1deg)"
    source_url = "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"
    license = "NASA Earth Science data: uso libre con atribución"
    spatial_resolution_m = 55000
    confidence = 0.7
    fields = EOBSCollector.fields

    @staticmethod
    def boxes(lon, lat) -> list[tuple[float, float]]:
        """(west, south) of the 10 x 10 deg boxes (API limit), aligned to whole degrees, that contain cells."""
        out = []
        for s in np.arange(np.floor(lat.min()), lat.max() + 1e-9, POWER_BOX_DEG):
            for w in np.arange(np.floor(lon.min()), lon.max() + 1e-9, POWER_BOX_DEG):
                if ((lon >= w) & (lon < w + POWER_BOX_DEG) & (lat >= s) & (lat < s + POWER_BOX_DEG)).any():
                    out.append((float(w), float(s)))
        return out

    def _box(self, param: str, w: float, s: float, start, end):
        import xarray as xr
        dest = self.lake.raw / "nasapower" / f"{param}_{start:%Y%m%d}_{end:%Y%m%d}_{w:+.0f}_{s:+.0f}.nc"
        pth = self.lake.cached_get(POWER, dest, params={
            "latitude-min": s, "latitude-max": s + POWER_BOX_DEG, "longitude-min": w, "longitude-max": w + POWER_BOX_DEG,
            "parameters": param, "community": "RE", "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}",
            "format": "netcdf"}, timeout=600, sleep=0.5, validate=lambda b: b[:3] == b"CDF" or b[:4] == b"\x89HDF")
        if pth is None:
            return None
        with xr.open_dataset(pth) as ds:
            da = ds[param].load()
        da = da.where(da > -990)
        if param == "ALLSKY_SFC_SW_DWN":       # daily energy -> mean irradiance in W/m2 (E-OBS qq units)
            da = da * (1e6 / 86400 if "MJ" in str(da.attrs.get("units", "")) else 1000 / 24)
        return da.transpose("time", "lat", "lon")

    def run(self, sites):
        p = self.cfg["period"]
        days = pd.date_range(p["start"], p["end"], freq="D")
        lon, lat = sites["lon"].to_numpy(float), sites["lat"].to_numpy(float)
        ids = sites["site_id"].astype(str).to_numpy()
        boxes = self.boxes(lon, lat)
        self.log.info("  NASA POWER: %d cajas de %d° x %d parámetros", len(boxes), POWER_BOX_DEG, len(POWER_PARAMS))
        for y in sorted(set(days.year)):
            dy = days[days.year == y]
            vals = {k: np.full((len(dy), len(ids)), np.nan, dtype="float32") for k in POWER_PARAMS.values()}
            for w, s in boxes:
                inside = (lon >= w) & (lon < w + POWER_BOX_DEG) & (lat >= s) & (lat < s + POWER_BOX_DEG)
                for param, key in POWER_PARAMS.items():
                    try:
                        da = self._box(param, w, s, dy[0], dy[-1])
                    except Exception as e:
                        self.log.error("  NASA POWER %s %d caja (%g, %g): %s", param, y, w, s, e)
                        continue
                    if da is None:
                        continue
                    v = da.values.astype("float32")
                    iy, ix, ok = nearest_valid(da["lon"].values, da["lat"].values, np.isfinite(v).mean(axis=0) > 0.5,
                                               lon[inside], lat[inside], 1.0)
                    a = np.full((v.shape[0], int(inside.sum())), np.nan, dtype="float32")
                    a[:, ok] = v[:, iy[ok], ix[ok]]
                    t = pd.DatetimeIndex(da["time"].values).normalize()
                    vals[key][:, inside] = pd.DataFrame(a, index=t).reindex(dy).to_numpy(dtype="float32")
            for key, a in vals.items():
                if not _coverage_ok(a):
                    self.log.warning("  NASA POWER %s %d: sin datos suficientes; se deja vacío", key, y)
                    a[:] = np.nan
            stage_daily_climate(self, ids, dy, vals)
            self.log.info("  NASA POWER %d: %d celdas x %d días; celdas con dato: %.0f %%", y, len(ids), len(dy),
                          100 * np.isfinite(vals["tx"]).any(axis=0).mean())
        self.lake.catalog("nasa_power", self.source, self.source_url, self.license)

    def write_lineage(self, **kw):
        model = {"imputation_method": "modelo", "confidence": 0.5}
        super().write_lineage(per_field={
            **{f: {**model, "notes": n} for f, n in MODEL_NOTES.items()},
            "td2m_mean_c": {"imputation_method": "derivado", "notes": "Magnus a partir de T2M y RH2M"},
            "ssrd_kwh_m2": {"notes": "ALLSKY_SFC_SW_DWN (CERES, 1°)"},
            "precip_mm": {"notes": "PRECTOTCORR (MERRA-2 corregida con observaciones)"},
        })
