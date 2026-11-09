"""Daily gridded observations E-OBS (0.1 deg, Europe, no key) -> daily climate for every cell at once.

One file per variable and year (or per multi-year block) covers the whole country, so the cost
does not grow with the number of cells. E-OBS has no snowfall, soil moisture or daily max wind:
those stay for ERA5-Land (CDS key) or Open-Meteo.
License: free for non-commercial research and education, citing Cornes et al. (2018) and ECA&D.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .base import Collector
from .climate import wetbulb_stull

BASE = "https://knmi-ecad-assets-prd.s3.amazonaws.com/ensembles/data"
YEARLY = BASE + "/months/ens/{var}_0.1deg_day_{year}_grid_ensmean.nc"
BLOCK = BASE + "/Grid_0.1deg_reg_ensemble/{var}_ens_mean_0.1deg_reg_{block}_{version}.nc"
BLOCKS = {"1995-2010": (1995, 2010), "2011-2025": (2011, 2025)}
VARS = ["tg", "tx", "tn", "rr", "hu", "fg", "qq"]
BBOX = (-18.5, 27.3, 4.8, 44.1)          # lon0, lat0, lon1, lat1 (peninsula, Baleares, Canarias)
MAX_PIXEL_DEG = 0.25                     # coastal cells take the nearest valid pixel up to ~25 km
HOUR_COS = np.sort(np.cos(2 * np.pi * (np.arange(24) - 15) / 24))   # diurnal cycle, max at 15 h
MIN_YEAR_COVERAGE = 0.9                  # a variable with fewer days than this in a year is left empty


def _day_coverage(da, n_expected: int) -> float:
    """Fraction of the expected days (those of the period in that year) with data anywhere in the subset."""
    if da.sizes.get("time", 0) == 0 or n_expected <= 0:
        return 0.0
    has = np.isfinite(da.values).reshape(da.sizes["time"], -1).any(axis=1)
    return float(min(has.sum(), n_expected) / n_expected)


def _es(t):
    return 6.112 * np.exp(17.62 * t / (243.12 + t))


def dewpoint(t, rh):
    g = np.log(np.clip(rh, 1, 100) / 100) + 17.62 * t / (243.12 + t)
    return 243.12 * g / (17.62 - g)


def hours_below(tn, tx, thr):
    """Hours of the day below thr for a cosine cycle between tn and tx (count, vectorised)."""
    tm, amp = (tx + tn) / 2, (tx - tn) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        c = (thr - tm) / amp
    n = np.searchsorted(HOUR_COS, c, side="left").astype(float)
    n = np.where(amp <= 0, np.where(tm < thr, 24.0, 0.0), n)
    return np.where(np.isfinite(tn) & np.isfinite(tx), n, np.nan)


def wetbulb_hours_below(tn, tx, td, thr, chunk=400_000):
    """Hours with wet-bulb < thr: cosine temperature cycle and constant dew point (absolute humidity)."""
    out = np.full(len(tn), np.nan)
    hours = np.cos(2 * np.pi * (np.arange(24) - 15) / 24)
    for i in range(0, len(tn), chunk):
        a, b, d = tn[i:i + chunk], tx[i:i + chunk], td[i:i + chunk]
        t = (a + b)[:, None] / 2 + (b - a)[:, None] / 2 * hours[None, :]
        rh = np.clip(100 * _es(d)[:, None] / _es(t), 5, 99)
        tw = wetbulb_stull(t, rh)
        cnt = (tw < thr).sum(axis=1).astype(float)
        out[i:i + chunk] = np.where(np.isfinite(a) & np.isfinite(b) & np.isfinite(d), cnt, np.nan)
    return out


def daily_fields(v: dict[str, np.ndarray], ccfg: dict) -> dict[str, np.ndarray]:
    """v: flat arrays (cells x days) of E-OBS variables -> dictionary daily fields."""
    tg, tx, tn, hu = v["tg"], v["tx"], v["tn"], v["hu"]
    tg = np.where(np.isfinite(tg), tg, (tx + tn) / 2)
    td = dewpoint(tg, hu)
    rh_tx = np.clip(100 * _es(td) / _es(tx), 5, 99)          # humidity at the time of tmax
    out = {
        "t2m_mean_c": tg, "t2m_max_c": tx, "t2m_min_c": tn, "td2m_mean_c": td, "rh_mean_pct": hu,
        "wetbulb_max_c": wetbulb_stull(tx, rh_tx), "wind10m_mean_ms": v["fg"], "precip_mm": v["rr"],
        "ssrd_kwh_m2": v["qq"] * 24 / 1000,                    # W/m2 daily mean -> kWh/m2/day
        "cdd_18": np.clip(tg - 18, 0, None), "hdd_18": np.clip(18 - tg, 0, None),
        "free_cooling_hours": hours_below(tn, tx, ccfg["free_cooling_threshold_c"]),
        "adiabatic_cooling_hours": wetbulb_hours_below(tn, tx, td, ccfg["adiabatic_wetbulb_threshold_c"]),
    }
    for name, cond, src in (("heatwave_flag", tx > ccfg["heatwave_threshold_c"], tx),
                            ("tropical_night_flag", tn > ccfg["tropical_night_c"], tn),
                            ("frost_flag", tn < 0, tn), ("extreme_cold_flag", tn < ccfg["extreme_cold_c"], tn)):
        out[name] = np.where(np.isfinite(src), cond, np.nan)
    return out


def stage_daily_climate(collector, ids, dy, vals: dict) -> None:
    """vals: {E-OBS variable: array (days x cells)} for the days dy of one year -> staged sites_daily fields."""
    flat = {k: v.T.reshape(-1).astype(float) for k, v in vals.items()}   # site-major order
    out = daily_fields(flat, collector.cfg["climate"])
    df = pd.DataFrame({"site_id": np.repeat(ids, len(dy)), "date": np.tile(dy.values, len(ids)), **out})
    for c in df.columns:
        if c.endswith("_flag"):
            df[c] = df[c].astype("boolean") if df[c].isna().any() else df[c].astype(bool)
        elif c not in ("site_id", "date"):
            df[c] = df[c].astype("float32")
    collector.stage("sites_daily", df, year=int(dy[0].year))


class EOBSCollector(Collector):
    name = "eobs"
    climate_key = "eobs"
    description = "Clima diario observado E-OBS (rejilla 0,1°, sin clave) para todas las celdas"
    source = "E-OBS ensemble mean 0.1° (Copernicus C3S / ECA&D, KNMI)"
    source_url = "https://surfobs.climate.copernicus.eu/dataaccess/access_eobs.php"
    license = "E-OBS: uso libre no comercial (investigación y educación) citando Cornes et al. (2018) y ECA&D"
    spatial_resolution_m = 11000
    confidence = 0.85
    version = "v33.0e"
    fields = {"sites_daily": ["t2m_mean_c", "t2m_max_c", "t2m_min_c", "td2m_mean_c", "rh_mean_pct", "wetbulb_max_c",
                              "wind10m_mean_ms", "precip_mm", "ssrd_kwh_m2", "cdd_18", "hdd_18",
                              "free_cooling_hours", "adiabatic_cooling_hours", "heatwave_flag",
                              "tropical_night_flag", "frost_flag", "extreme_cold_flag"]}

    # ------------------------------------------------------------ download + Spain subset
    def _cache(self, var: str, year: int):
        return self.lake.processed / "eobs" / f"{var}_{year}_{self.version}.nc"

    def _cached_coverage(self, var: str, year: int) -> float:
        import xarray as xr
        p = self._cache(var, year)
        if not p.exists():
            return -1.0
        with xr.open_dataset(p) as ds:
            return _day_coverage(ds[var], self._expected_days[year])

    def _extract(self, url: str, var: str, years: list[int], label: str) -> None:
        """Download a Europe-wide file to a temporary folder, keep only the Spain subset of `years`.

        The Europe file (0.2-1 GB) is transient: it is never kept, only the Spain cut (~20 MB/year).
        """
        import tempfile
        import xarray as xr
        if url in self._tried:          # each source file is downloaded at most once per run
            return
        self._tried.add(url)
        with tempfile.TemporaryDirectory(prefix="dclake_eobs_", ignore_cleanup_errors=True) as td:
            self.log.info("  E-OBS %s %s: descarga temporal…", var, label)
            src = self.lake.download_file(url, Path(td) / "src.nc", timeout=3600)
            if src is None:
                return
            for y in years:
                sub = self._subset(src, var, y)
                if _day_coverage(sub, self._expected_days[y]) > self._cached_coverage(var, y):
                    out = self._cache(var, y)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    sub.to_dataset(name=var).to_netcdf(out)
            xr.backends.file_manager.FILE_CACHE.clear()   # release the handle before the temp folder goes

    def _ensure_subsets(self, var: str, years: list[int]) -> None:
        """Make sure processed/eobs has a complete Spain subset of `var` for every year (when the source has it)."""
        todo = [y for y in years if self._cached_coverage(var, y) < MIN_YEAR_COVERAGE]
        for block, (a, z) in BLOCKS.items():
            ys = [y for y in todo if a <= y <= z]
            if ys and self._use_blocks[block]:
                self._extract(BLOCK.format(var=var, block=block, version=self.version), var, ys, f"bloque {block}")
        for y in [y for y in years if self._cached_coverage(var, y) < MIN_YEAR_COVERAGE]:
            self._extract(YEARLY.format(var=var, year=y), var, [y], str(y))
            block = next((b for b, (a, z) in BLOCKS.items() if a <= y <= z), None)
            if block and self._cached_coverage(var, y) < MIN_YEAR_COVERAGE:
                # provisional yearly files lag for some variables (radiation): the consolidated block has more
                self._extract(BLOCK.format(var=var, block=block, version=self.version), var,
                              [b for b in years if self._cached_coverage(var, b) < MIN_YEAR_COVERAGE
                               and BLOCKS[block][0] <= b <= BLOCKS[block][1]], f"bloque {block}")

    @staticmethod
    def _subset(src, var: str, year: int):
        import xarray as xr
        with xr.open_dataset(src) as ds:
            lon0, lat0, lon1, lat1 = BBOX
            sub = ds[var].sel(longitude=slice(lon0, lon1), latitude=slice(lat0, lat1))
            return sub.sel(time=sub["time"].dt.year == year).load()

    # ------------------------------------------------------------ pixel assignment
    @staticmethod
    def _pixel_index(da, lon, lat):
        """Nearest pixel with data (>50 % of days) for each cell; -1 if none within MAX_PIXEL_DEG."""
        valid = np.isfinite(da.values).mean(axis=0) > 0.5
        LON, LAT = np.meshgrid(da["longitude"].values, da["latitude"].values)
        iy, ix = np.nonzero(valid)
        if len(iy) == 0:
            return None, None, np.zeros(len(lon), bool)
        k = np.cos(np.radians(40))
        tree = cKDTree(np.column_stack([LON[iy, ix] * k, LAT[iy, ix]]))
        d, j = tree.query(np.column_stack([np.asarray(lon) * k, np.asarray(lat)]))
        ok = d <= MAX_PIXEL_DEG
        return iy[j], ix[j], ok

    def run(self, sites):
        import xarray as xr
        p = self.cfg["period"]
        days = pd.date_range(p["start"], p["end"], freq="D")
        years = sorted(set(days.year))
        # whole blocks only when most of their years are needed (otherwise yearly files are smaller)
        self._use_blocks = {b: sum(a <= y <= z for y in years) > 3 for b, (a, z) in BLOCKS.items()}
        self._expected_days = {y: int((days.year == y).sum()) for y in years}
        lon, lat = sites["lon"].values, sites["lat"].values
        ids = sites["site_id"].astype(str).values
        self._coverage, self._tried = {}, set()
        for var in VARS:
            self._ensure_subsets(var, years)
        for y in years:
            dy = days[days.year == y]
            vals = {}
            for var in VARS:
                f = self._cache(var, y)
                if not f.exists():
                    vals[var] = np.full((len(dy), len(ids)), np.nan, dtype="float32")
                    continue
                with xr.open_dataset(f) as ds:
                    da = ds[var].sel(time=slice(dy[0], dy[-1] + pd.Timedelta(hours=23)))
                    iy, ix, ok = self._pixel_index(da, lon, lat)
                    arr = np.full((da.sizes["time"], len(ids)), np.nan, dtype="float32")
                    if iy is not None:
                        arr[:, ok] = da.values[:, iy[ok], ix[ok]]
                    t = pd.DatetimeIndex(da["time"].values).normalize()
                    vals[var] = pd.DataFrame(arr, index=t).reindex(dy).to_numpy(dtype="float32")
                    self._coverage[var] = float(ok.mean())
                    cov = _day_coverage(da, len(dy))
                    if cov < MIN_YEAR_COVERAGE:   # partial years would bias annual sums: leave it empty
                        self.log.warning("  E-OBS %s %d: solo %.0f %% de los días; se deja vacío ese año", var, y, 100 * cov)
                        vals[var][:] = np.nan
                        self._coverage[var] = 0.0
            stage_daily_climate(self, ids, dy, vals)
            self.log.info("  E-OBS %d: %d celdas x %d días; celdas con píxel válido: %s", y, len(ids), len(dy),
                          {k: f"{v:.0%}" for k, v in self._coverage.items()})
        self.lake.catalog("eobs_" + self.version, self.source, self.source_url, self.license)

    def write_lineage(self, **kw):
        model = {"imputation_method": "modelo", "confidence": 0.6}
        super().write_lineage(per_field={
            "free_cooling_hours": {**model, "notes": "Ciclo diario coseno entre tn y tx (máximo a las 15 h)"},
            "adiabatic_cooling_hours": {**model, "notes": "Ciclo diario coseno y punto de rocío constante en el día"},
            "wetbulb_max_c": {**model, "notes": "Stull (2011) con tx y la humedad relativa a la hora de tx"},
            "td2m_mean_c": {"imputation_method": "derivado", "notes": "Magnus a partir de tg y hu"},
            "ssrd_kwh_m2": {"notes": "E-OBS qq (media diaria W/m2) x 24 h / 1000; cobertura limitada a zonas con estaciones"},
            "wind10m_mean_ms": {"notes": "E-OBS fg; cobertura limitada a zonas con estaciones"},
        })
