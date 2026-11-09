"""ERA5-Land hourly point time series (Copernicus CDS) -> daily climate variables."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .base import Collector

DATASET = "reanalysis-era5-land-timeseries"
VARIABLES = {  # CDS name -> short name in the output
    "2m_temperature": "t2m",
    "2m_dewpoint_temperature": "d2m",
    "10m_u_component_of_wind": "u10",
    "10m_v_component_of_wind": "v10",
    "total_precipitation": "tp",
    "snowfall": "sf",
    "surface_solar_radiation_downwards": "ssrd",
    "volumetric_soil_water_layer_1": "swvl1",
}
ACCUMULATED = ("tp", "sf", "ssrd")


# ---------------------------------------------------------------- physics
def rh_from_dewpoint(t_c, td_c):
    es = lambda t: 6.112 * np.exp(17.62 * t / (243.12 + t))
    return np.clip(100 * es(td_c) / es(t_c), 0, 100)


def wetbulb_stull(t_c, rh):
    """Stull (2011) wet-bulb approximation, valid for RH 5-99 % and T -20..50 °C."""
    return (t_c * np.arctan(0.151977 * np.sqrt(rh + 8.313659)) + np.arctan(t_c + rh) - np.arctan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh) - 4.686035)


def daily_total(series: pd.Series) -> pd.Series:
    """Daily total of an ERA5-Land flux that may be accumulated since 00 UTC.

    ERA5-Land stores precipitation/radiation as accumulations that reset every day,
    so the daily total is the value at 00 UTC of the next day. If the series is
    already de-accumulated (hourly amounts), the daily total is a plain sum.
    """
    s = series.dropna()
    if s.empty:
        return s
    d = s.diff()
    neg = d < -1e-9
    accumulated = neg.mean() > 0.02 and (s.index[neg].hour == 1).mean() > 0.8
    if accumulated:
        nxt = s[s.index.hour == 0]
        out = pd.Series(nxt.values, index=(nxt.index - pd.Timedelta(days=1)).normalize())
        return out
    return s.clip(lower=0).resample("1D").sum()


def hourly_to_daily(h: pd.DataFrame, ccfg: dict) -> pd.DataFrame:
    """h: hourly frame indexed by UTC time with columns t2m (K), d2m (K), u10, v10, tp (m), sf (m), ssrd (J/m2), swvl1."""
    h = h.sort_index()
    t = h["t2m"] - 273.15
    td = h["d2m"] - 273.15
    rh = rh_from_dewpoint(t, td)
    tw = wetbulb_stull(t, rh)
    ws = np.hypot(h["u10"], h["v10"])
    hd = pd.DataFrame({"t": t, "td": td, "rh": rh, "tw": tw, "ws": ws, "swvl1": h.get("swvl1")})
    g = hd.resample("1D")
    d = pd.DataFrame({
        "t2m_mean_c": g["t"].mean(), "t2m_max_c": g["t"].max(), "t2m_min_c": g["t"].min(),
        "td2m_mean_c": g["td"].mean(), "rh_mean_pct": g["rh"].mean(), "wetbulb_max_c": g["tw"].max(),
        "wind10m_mean_ms": g["ws"].mean(), "wind10m_max_ms": g["ws"].max(),
        "soil_moisture_l1": g["swvl1"].mean(),
        "free_cooling_hours": (hd["t"] < ccfg["free_cooling_threshold_c"]).resample("1D").sum(),
        "adiabatic_cooling_hours": (hd["tw"] < ccfg["adiabatic_wetbulb_threshold_c"]).resample("1D").sum(),
        "n_hours": g["t"].count(),
    })
    for col, short, factor in (("precip_mm", "tp", 1000), ("snowfall_mm_we", "sf", 1000), ("ssrd_kwh_m2", "ssrd", 1 / 3.6e6)):
        if short in h:
            d[col] = daily_total(h[short]).reindex(d.index) * factor
    d = d[d["n_hours"] >= 20].drop(columns="n_hours")   # incomplete days are dropped
    d["cdd_18"] = (d["t2m_mean_c"] - 18).clip(lower=0)
    d["hdd_18"] = (18 - d["t2m_mean_c"]).clip(lower=0)
    d["heatwave_flag"] = d["t2m_max_c"] > ccfg["heatwave_threshold_c"]
    d["tropical_night_flag"] = d["t2m_min_c"] > ccfg["tropical_night_c"]
    d["frost_flag"] = d["t2m_min_c"] < 0
    d["extreme_cold_flag"] = d["t2m_min_c"] < ccfg["extreme_cold_c"]
    d.index.name = "date"
    return d.reset_index()


def read_cds_output(path: Path) -> pd.DataFrame:
    """Parse the CDS time-series download (CSV or zip of CSVs, or NetCDF) into an hourly frame."""
    frames = []

    def from_csv(buf):
        df = pd.read_csv(buf, comment="#")
        tcol = next(c for c in df.columns if c.lower() in ("valid_time", "time", "date"))
        df[tcol] = pd.to_datetime(df[tcol], utc=True).dt.tz_localize(None)
        keep = [c for c in df.columns if c in VARIABLES.values()]
        return df.set_index(tcol)[keep]

    raw = Path(path).read_bytes()
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for n in z.namelist():
                if n.endswith(".csv"):
                    frames.append(from_csv(io.BytesIO(z.read(n))))
                elif n.endswith(".nc"):
                    frames.append(_from_nc(z.read(n)))
    elif raw[:4] in (b"\x89HDF", b"CDF\x01", b"CDF\x02"):
        frames.append(_from_nc(raw))
    else:
        frames.append(from_csv(io.BytesIO(raw)))
    out = pd.concat(frames, axis=1)
    return out.loc[:, ~out.columns.duplicated()]


def _from_nc(raw: bytes) -> pd.DataFrame:
    import tempfile
    import xarray as xr
    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as f:
        f.write(raw)
        name = f.name
    ds = xr.open_dataset(name)
    tname = "valid_time" if "valid_time" in ds.coords else "time"
    df = ds.to_dataframe().reset_index().set_index(tname)
    ds.close()
    return df[[c for c in df.columns if c in VARIABLES.values()]]


class ERA5LandCollector(Collector):
    name = "era5land"
    description = "Clima horario ERA5-Land por celda (CDS time-series) -> variables diarias"
    source = "ERA5-Land hourly time-series (Copernicus Climate Data Store)"
    source_url = "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries"
    license = "Licence to use Copernicus Products"
    spatial_resolution_m = 9000
    confidence = 0.85
    fields = {"sites_daily": ["t2m_mean_c", "t2m_max_c", "t2m_min_c", "td2m_mean_c", "rh_mean_pct", "wetbulb_max_c",
                              "wind10m_mean_ms", "wind10m_max_ms", "precip_mm", "snowfall_mm_we", "ssrd_kwh_m2",
                              "soil_moisture_l1", "cdd_18", "hdd_18", "free_cooling_hours", "adiabatic_cooling_hours",
                              "heatwave_flag", "tropical_night_flag", "frost_flag", "extreme_cold_flag"]}

    def missing_requirements(self):
        has_env = self.cfg.secret("CDSAPI_KEY") is not None
        has_rc = (Path.home() / ".cdsapirc").exists()
        return [] if (has_env or has_rc) else ["CDSAPI_KEY (o archivo ~/.cdsapirc)"]

    def run(self, sites):
        import cdsapi
        from tqdm import tqdm
        import os
        if self.cfg.secret("CDSAPI_KEY") and not os.environ.get("CDSAPI_URL"):
            os.environ["CDSAPI_URL"] = "https://cds.climate.copernicus.eu/api"
        client = cdsapi.Client(quiet=True, progress=False)
        p = self.cfg["period"]
        raw_dir = self.lake.raw / "era5land" / self.cfg.period_tag   # one request per site and period
        day_dir = raw_dir / "daily"
        day_dir.mkdir(parents=True, exist_ok=True)
        for sid, lon, lat in tqdm(list(zip(sites["site_id"], sites["lon"], sites["lat"])), desc="ERA5-Land"):
            out = day_dir / f"{sid}.parquet"
            if out.exists():
                continue
            target = raw_dir / "hourly" / f"{sid}.download"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                try:
                    client.retrieve(DATASET, {
                        "variable": list(VARIABLES),
                        "location": {"longitude": round(float(lon), 3), "latitude": round(float(lat), 3)},
                        "date": [f"{p['start']}/{p['end']}"],
                        "data_format": "csv",
                    }, str(target))
                except Exception as e:
                    self.log.error("  %s: petición CDS fallida (%s)", sid, e)
                    continue
            try:
                h = read_cds_output(target)
                d = hourly_to_daily(h, self.cfg["climate"])
            except Exception as e:
                self.log.error("  %s: no se pudo leer la descarga (%s)", sid, e)
                continue
            d.insert(0, "site_id", sid)
            d["year"] = pd.to_datetime(d["date"]).dt.year
            d.to_parquet(out, index=False)
        self.lake.catalog("era5land_timeseries", self.source, self.source_url, self.license)
        self._stage_by_year(day_dir)

    def _stage_by_year(self, day_dir: Path):
        import pyarrow.compute as pc
        import pyarrow.dataset as ds
        files = [str(f) for f in day_dir.glob("*.parquet")]
        if not files:
            return
        dset = ds.dataset(files, format="parquet")
        years = sorted(set(pc.unique(dset.to_table(columns=["year"])["year"]).to_pylist()))
        for y in years:  # one year at a time keeps memory low
            g = dset.to_table(filter=pc.field("year") == y).to_pandas()
            self.stage("sites_daily", g.drop(columns="year"), year=int(y))
