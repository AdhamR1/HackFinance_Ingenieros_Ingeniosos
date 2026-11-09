"""Earthquake catalogues (EMSC, USGS) and active fires (NASA FIRMS) -> daily counts per cell."""
from __future__ import annotations


import numpy as np
import pandas as pd

from .. import geo
from .base import Collector

EMSC = "https://www.seismicportal.eu/fdsnws/event/1/query"
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
FIRMS = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/10/{date}"
FIRMS_START = {"MODIS_SP": "2000-11-01", "VIIRS_SNPP_SP": "2012-01-20", "VIIRS_NOAA20_SP": "2018-04-01"}
EQ_BBOX = dict(minlatitude=26.0, maxlatitude=45.5, minlongitude=-20.0, maxlongitude=6.0)


def daily_counts(sites, events: pd.DataFrame, radius_km: float, days: pd.DatetimeIndex,
                 value_col: str | None, count_name: str, agg_name: str, agg: str) -> pd.DataFrame:
    """Full site x day frame: number of events within radius and max/sum of value_col."""
    sxy = np.column_stack([sites["x"].values, sites["y"].values])
    base = pd.MultiIndex.from_product([sites["site_id"].values, days], names=["site_id", "date"])
    out = pd.DataFrame(index=base)
    out[count_name] = 0
    out[agg_name] = 0.0 if agg == "sum" else np.nan
    if events is None or events.empty:
        return out.reset_index()
    eg = geo.points_from_lonlat(events)
    nb = geo.neighbours_within(sxy, geo.xy(eg), radius_km)
    rows = []
    dates = eg["date"].values
    vals = eg[value_col].values if value_col else np.ones(len(eg))
    for sid, idx in zip(sites["site_id"].values, nb):
        for i in idx:
            rows.append((sid, dates[i], vals[i]))
    if rows:
        r = pd.DataFrame(rows, columns=["site_id", "date", "v"])
        g = r.groupby(["site_id", "date"])["v"].agg(["count", agg])
        g = g[g.index.get_level_values("date").isin(days)]
        out.loc[g.index, count_name] = g["count"].values
        out.loc[g.index, agg_name] = g[agg].values
    return out.reset_index()


class EarthquakesCollector(Collector):
    name = "earthquakes"
    description = "Terremotos: conteo diario (EMSC) y estadísticas históricas M>=4 (USGS)"
    source = "EMSC FDSN event service / USGS ComCat"
    source_url = "https://www.seismicportal.eu ; https://earthquake.usgs.gov/fdsnws/event/1/"
    license = "EMSC: CC BY 4.0 ; USGS: dominio público"
    confidence = 0.8
    fields = {"sites_daily": ["eq_count_100km", "eq_max_mag_100km"],
              "sites_static": ["n_eq_m4_100km_50y", "max_mag_100km_hist", "dist_m5_epicenter_km"]}

    def _emsc_year(self, y0, y1):
        c = self.cfg["earthquakes"]
        dest = self.lake.raw / "earthquakes" / f"emsc_{y0:%Y%m%d}_{y1:%Y%m%d}.txt"
        p = self.lake.cached_get(EMSC, dest, params={
            "start": f"{y0:%Y-%m-%d}", "end": f"{y1:%Y-%m-%d}", "minmag": c["daily_min_magnitude"],
            "minlat": EQ_BBOX["minlatitude"], "maxlat": EQ_BBOX["maxlatitude"],
            "minlon": EQ_BBOX["minlongitude"], "maxlon": EQ_BBOX["maxlongitude"],
            "format": "text", "limit": 20000}, timeout=300, sleep=1, min_bytes=0)
        if p is None or p.stat().st_size == 0:
            return pd.DataFrame()
        df = pd.read_csv(p, sep="|")
        df.columns = [c.strip().lstrip("#") for c in df.columns]
        return pd.DataFrame({"time": pd.to_datetime(df["Time"], utc=True, errors="coerce").dt.tz_localize(None),
                             "lat": df["Latitude"], "lon": df["Longitude"], "mag": df["Magnitude"]})

    def run(self, sites):
        c = self.cfg["earthquakes"]
        p = self.cfg["period"]
        days = pd.date_range(p["start"], p["end"], freq="D")
        frames = []
        for y in sorted(set(days.year)):
            y0 = max(days.min(), pd.Timestamp(f"{y}-01-01"))
            y1 = min(days.max() + pd.Timedelta(days=1), pd.Timestamp(f"{y + 1}-01-01"))
            try:
                frames.append(self._emsc_year(y0, y1))
            except Exception as e:
                self.log.error("  EMSC %s: %s", y, e)
        ev = pd.concat(frames, ignore_index=True).dropna(subset=["lat", "lon"]) if frames else pd.DataFrame()
        if len(ev):
            ev["date"] = ev["time"].dt.normalize()
        self.lake.catalog("emsc_catalog", "EMSC", EMSC, "CC BY 4.0")
        for y in sorted(set(days.year)):
            dy = days[days.year == y]
            sub = ev[ev["date"].dt.year == y] if len(ev) else ev
            d = daily_counts(sites, sub, c["daily_radius_km"], dy, "mag", "eq_count_100km", "eq_max_mag_100km", "max")
            self.stage("sites_daily", d, year=int(y))

        # historical statistics (USGS M>=4 since static_start)
        dest = self.lake.raw / "earthquakes" / f"usgs_m4_{c['static_start']}_{p['end']}.csv"
        pth = self.lake.cached_get(USGS, dest, params={
            "format": "csv", "starttime": c["static_start"], "endtime": p["end"], "minmagnitude": 4, **EQ_BBOX},
            timeout=300, min_bytes=0)
        us = pd.read_csv(pth).rename(columns={"latitude": "lat", "longitude": "lon"}) if pth else pd.DataFrame()
        self.lake.catalog("usgs_comcat_m4", "USGS ComCat", USGS, "Dominio público")
        st = pd.DataFrame({"site_id": sites["site_id"].values})
        if len(us):
            ug = geo.points_from_lonlat(us)
            sxy = np.column_stack([sites["x"].values, sites["y"].values])
            nb = geo.neighbours_within(sxy, geo.xy(ug), 100)
            st["n_eq_m4_100km_50y"] = [len(i) for i in nb]
            st["max_mag_100km_hist"] = [float(ug["mag"].values[i].max()) if i else np.nan for i in nb]
            m5 = ug[ug["mag"] >= 5]
            st["dist_m5_epicenter_km"] = geo.nearest(geo.site_points(sites), m5)["dist_km"].values
        self.stage("sites_static", st)

    def write_lineage(self, **kw):
        super().write_lineage(per_field={
            "n_eq_m4_100km_50y": {"notes": "USGS ComCat desde config.earthquakes.static_start (no son exactamente 50 años)"}})


FIRMS_COUNTRY = "https://firms.modaps.eosdis.nasa.gov/data/country/{prod}/{year}/{prod}_{year}_Spain.csv"
FIRMS_COUNTRY_PRODUCT = {"MODIS_SP": "modis", "VIIRS_SNPP_SP": "viirs-snpp", "VIIRS_NOAA20_SP": "viirs-noaa20"}


class FIRMSCollector(Collector):
    name = "firms"
    description = "Focos de incendio diarios (NASA FIRMS: archivo anual por país sin clave, o API con clave)"
    source = "NASA FIRMS (MODIS/VIIRS Standard Processing)"
    source_url = "https://firms.modaps.eosdis.nasa.gov/country/"
    license = "NASA Earth Science data: uso libre con atribución"
    spatial_resolution_m = 1000
    confidence = 0.8
    fields = {"sites_daily": ["fire_detections_10km", "fire_frp_sum_10km"]}

    def _country_archive(self, days) -> list[pd.DataFrame]:
        """Yearly country CSVs (no key). Only completed years exist; Spain only (border fires abroad are missed)."""
        frames = []
        for src in self.cfg["fires"]["sources"]:
            prod = FIRMS_COUNTRY_PRODUCT.get(src)
            if not prod:
                continue
            for y in sorted(set(days.year)):
                url = FIRMS_COUNTRY.format(prod=prod, year=y)
                try:
                    pth = self.lake.cached_get(url, self.lake.raw / "firms" / "country" / f"{prod}_{y}_Spain.csv",
                                               timeout=300, sleep=1,
                                               validate=lambda b: b.lstrip()[:8] == b"latitude")
                except Exception as e:
                    self.log.error("  FIRMS %s %d: %s", prod, y, e)
                    continue
                if pth is None:
                    self.log.warning("  FIRMS %s %d: sin archivo anual (año en curso: hace falta FIRMS_MAP_KEY)", prod, y)
                    continue
                df = pd.read_csv(pth)
                if "type" in df:
                    df = df[df["type"] == 0]          # 0 = vegetation fire (drop static industrial sources, offshore)
                frames.append(df[["latitude", "longitude", "acq_date", "frp"]])
        return frames

    def run(self, sites):
        from tqdm import tqdm
        key = self.cfg.secret("FIRMS_MAP_KEY")
        p = self.cfg["period"]
        days = pd.date_range(p["start"], p["end"], freq="D")
        frames = [] if key else self._country_archive(days)
        for src in (self.cfg["fires"]["sources"] if key else []):
            start = max(days.min(), pd.Timestamp(FIRMS_START.get(src, "2000-11-01")))
            windows = pd.date_range(start, days.max(), freq="10D")
            for name, bb in self.cfg["bboxes"].items():
                bbox = ",".join(str(v) for v in bb)
                for w in tqdm(windows, desc=f"FIRMS {src} {name}"):
                    dest = self.lake.raw / "firms" / src / name / f"{w:%Y%m%d}.csv"
                    url = FIRMS.format(key=key, source=src, bbox=bbox, date=f"{w:%Y-%m-%d}")
                    try:
                        pth = self.lake.cached_get(url, dest, timeout=120, sleep=0.3, min_bytes=0)
                    except Exception as e:
                        self.log.error("  FIRMS %s %s: %s", src, w.date(), e)
                        continue
                    if pth is None or pth.stat().st_size == 0:
                        continue
                    try:
                        df = pd.read_csv(pth)
                    except pd.errors.EmptyDataError:
                        continue
                    if "latitude" in df:
                        frames.append(df[["latitude", "longitude", "acq_date", "frp"]])
        self.lake.catalog("nasa_firms", self.source, self.source_url, self.license)
        ev = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["latitude", "longitude", "acq_date", "frp"])
        ev = ev.rename(columns={"latitude": "lat", "longitude": "lon"})
        ev["date"] = pd.to_datetime(ev["acq_date"])
        for y in sorted(set(days.year)):
            dy = days[days.year == y]
            d = daily_counts(sites, ev[ev["date"].dt.year == y], self.cfg["fires"]["radius_km"], dy,
                             "frp", "fire_detections_10km", "fire_frp_sum_10km", "sum")
            self.stage("sites_daily", d, year=int(y))

    def write_lineage(self, **kw):
        note = ("Solo incendios de vegetación (type=0). Sin clave: archivo anual de España, sin focos al otro lado "
                "de la frontera ni año en curso")
        super().write_lineage(per_field={f: {"notes": note} for f in self.fields["sites_daily"]})
