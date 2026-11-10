"""Hourly ERA5-Land through the Open-Meteo historical API (no key) -> same daily variables as
era5land.

Used when there is no CDS key. It comes after ERA5LandCollector in the registry, so data
downloaded directly from the CDS wins when both exist.
Open-Meteo: free for non-commercial use, data under CC BY 4.0 (attribution required).
"""

from __future__ import annotations

import time

import pandas as pd

from .base import Collector
from .climate import hourly_to_daily

URL = "https://archive-api.open-meteo.com/v1/archive"
# 'era5_land' alone only serves temperature, dew point and soil moisture (wind, rain and
# radiation come back null); 'era5_seamless' fills those from ERA5 (0.25 deg).
MODEL = "era5_seamless"
HOURLY = [
    "temperature_2m",
    "dew_point_2m",
    "wind_speed_10m",
    "precipitation",
    "snowfall",
    "shortwave_radiation",
    "soil_moisture_0_to_7cm",
]


def to_era5_hourly(js: dict) -> pd.DataFrame:
    """Open-Meteo JSON -> frame with ERA5 short names/units expected by hourly_to_daily."""
    h = js["hourly"]
    t = pd.to_datetime(h["time"])
    ws = pd.Series(h["wind_speed_10m"], index=t, dtype=float)  # m/s (wind_speed_unit=ms)
    return pd.DataFrame(
        {
            "t2m": pd.Series(h["temperature_2m"], index=t, dtype=float) + 273.15,
            "d2m": pd.Series(h["dew_point_2m"], index=t, dtype=float) + 273.15,
            "u10": ws,
            "v10": 0.0,  # hypot(u, 0) = speed
            "tp": pd.Series(h["precipitation"], index=t, dtype=float)
            / 1000,  # mm -> m (hourly amounts)
            "sf": pd.Series(h["snowfall"], index=t, dtype=float)
            / 7
            / 1000,  # cm snow -> m water eq. (1/7, Open-Meteo)
            "ssrd": pd.Series(h["shortwave_radiation"], index=t, dtype=float)
            * 3600,  # W/m2 hourly mean -> J/m2
            "swvl1": pd.Series(
                h["soil_moisture_0_to_7cm"], index=t, dtype=float
            ),  # m3/m3, ERA5-Land layer 1 (0-7 cm)
        }
    )


class OpenMeteoCollector(Collector):
    name = "openmeteo"
    description = "Clima horario ERA5-Land vía Open-Meteo (sin clave) -> variables diarias"
    source = "Open-Meteo Historical Weather API (modelo era5_seamless: ERA5-Land + ERA5)"
    source_url = "https://open-meteo.com/en/docs/historical-weather-api"
    license = "CC BY 4.0 (Open-Meteo); API gratuita solo para uso no comercial"
    spatial_resolution_m = 9000
    confidence = 0.8
    run_by_default = False  # one request per cell: only for small tests (--only openmeteo)
    fields = {
        "sites_daily": [
            "t2m_mean_c",
            "t2m_max_c",
            "t2m_min_c",
            "td2m_mean_c",
            "rh_mean_pct",
            "wetbulb_max_c",
            "wind10m_mean_ms",
            "wind10m_max_ms",
            "precip_mm",
            "snowfall_mm_we",
            "ssrd_kwh_m2",
            "soil_moisture_l1",
            "cdd_18",
            "hdd_18",
            "free_cooling_hours",
            "adiabatic_cooling_hours",
            "heatwave_flag",
            "tropical_night_flag",
            "frost_flag",
            "extreme_cold_flag",
        ]
    }

    def run(self, sites):
        import math

        from tqdm import tqdm

        p = self.cfg["period"]
        raw = self.lake.raw / "openmeteo" / MODEL / self.cfg.period_tag
        # Free tier: 600 calls/min, 5000/hour, 10000/day; one request counts ceil(days/14) calls.
        n_days = (pd.Timestamp(p["end"]) - pd.Timestamp(p["start"])).days + 1
        weight = math.ceil(n_days / 14) * math.ceil(len(HOURLY) / 10)
        pause = weight * 3600 / 4500
        todo = [
            (s, lo, la)
            for s, lo, la in zip(sites["site_id"], sites["lon"], sites["lat"])
            if not (raw / f"{s}.json").exists()
        ]
        self.log.info(
            "  %d celdas por descargar (~%d llamadas cada una, %.0f s entre peticiones, %.1f h); "
            "límite gratuito ~%d celdas/día",
            len(todo),
            weight,
            pause,
            len(todo) * pause / 3600,
            10000 // weight,
        )
        daily, failures = [], 0
        for sid, lon, lat in tqdm(
            list(zip(sites["site_id"], sites["lon"], sites["lat"])), desc="Open-Meteo"
        ):
            dest = raw / f"{sid}.json"
            fresh = not dest.exists()
            if failures >= 3:
                break
            js = None
            for attempt in range(4):
                try:
                    js = self.lake.get_json(
                        URL,
                        dest,
                        params={
                            "latitude": round(float(lat), 4),
                            "longitude": round(float(lon), 4),
                            "start_date": p["start"],
                            "end_date": p["end"],
                            "hourly": ",".join(HOURLY),
                            "models": MODEL,
                            "wind_speed_unit": "ms",
                            "timezone": "GMT",
                        },
                        timeout=120,
                        sleep=0.5,
                        retry=False,
                    )
                    break
                except Exception as e:  # 429 = per-minute limit: wait and retry
                    self.log.warning("  %s: Open-Meteo %s; reintento", sid, str(e)[:120])
                    time.sleep(30 * (attempt + 1))
            if fresh:
                time.sleep(pause)
            if not js or "hourly" not in js:
                failures += 1
                if failures >= 3:
                    self.log.error(
                        "  Open-Meteo rechaza peticiones (¿límite diario?). Lo descargado se "
                        "conserva: "
                        "vuelve a ejecutar más tarde y continuará donde lo dejó."
                    )
                continue
            failures = 0
            d = hourly_to_daily(to_era5_hourly(js), self.cfg["climate"])
            d.insert(0, "site_id", sid)
            daily.append(d)
        self.lake.catalog("openmeteo_era5land", self.source, self.source_url, self.license)
        if not daily:
            return
        df = pd.concat(daily, ignore_index=True)
        for y, g in df.groupby(pd.to_datetime(df["date"]).dt.year):
            self.stage("sites_daily", g, year=int(y))

    def write_lineage(self, **kw):
        super().write_lineage(
            per_field={
                "snowfall_mm_we": {
                    "notes": "Open-Meteo da nieve en cm; agua equivalente = cm / 7 (convención de "
                    "Open-Meteo)"
                },
                "wind10m_mean_ms": {
                    "notes": "Velocidad a 10 m de ERA5-Land servida por Open-Meteo"
                },
            }
        )
