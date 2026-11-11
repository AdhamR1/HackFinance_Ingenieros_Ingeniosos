"""Earthquake catalogues (EMSC, USGS) and active fires (NASA FIRMS) -> daily counts per cell."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import geo
from .base import Collector

EMSC = "https://www.seismicportal.eu/fdsnws/event/1/query"
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
FIRMS = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/10/{date}"
FIRMS_START = {
    "MODIS_SP": "2000-11-01",
    "VIIRS_SNPP_SP": "2012-01-20",
    "VIIRS_NOAA20_SP": "2018-04-01",
}
EMSC_LIMIT = 20000


def eq_bbox(cfg, margin: float = 1.5) -> dict:
    """Earthquake search box: the country's boxes plus ~150 km (cells count events within 100
    km)."""
    w, s, e, n = geo.bbox_union(cfg, margin)
    return {"minlatitude": s, "maxlatitude": n, "minlongitude": w, "maxlongitude": e}


def count_min_magnitude(cfg) -> float:
    """Common magnitude threshold of the daily counts (never below what was downloaded)."""
    c = cfg["earthquakes"]
    return max(float(c.get("count_min_magnitude", 0)), float(c["daily_min_magnitude"]))


def daily_counts(
    sites,
    events: pd.DataFrame,
    radius_km: float,
    days: pd.DatetimeIndex,
    value_col: str | None,
    count_name: str,
    agg_name: str,
    agg: str,
) -> pd.DataFrame:
    """Full site x day frame: number of events within radius and max/sum of value_col.

    Day by day with numpy: with 3.5 km cells one event reaches ~2,500 cells within 100 km, so a
    site x event list would have tens of millions of rows in Japan or California.
    """
    from scipy.spatial import cKDTree

    n, nd = len(sites), len(days)
    cnt = np.zeros((n, nd), dtype=np.int32)
    acc = np.zeros((n, nd)) if agg == "sum" else np.full((n, nd), np.nan)
    if events is not None and not events.empty:
        eg = geo.points_from_lonlat(events)
        exy = geo.xy(eg)
        tree = cKDTree(np.column_stack([sites["x"].to_numpy(float), sites["y"].to_numpy(float)]))
        day = pd.DatetimeIndex(days).get_indexer(
            pd.DatetimeIndex(pd.to_datetime(eg["date"].values)).normalize()
        )
        vals = eg[value_col].to_numpy(float) if value_col else np.ones(len(eg))
        vals = np.nan_to_num(vals) if agg == "sum" else np.where(np.isfinite(vals), vals, -np.inf)
        for j in np.unique(day[day >= 0]):
            m = day == j
            near = tree.query_ball_point(exy[m], r=radius_km * 1000.0)
            lens = np.fromiter((len(x) for x in near), dtype=np.int64, count=len(near))
            if lens.sum() == 0:
                continue
            si = np.concatenate([np.asarray(x, dtype=np.int64) for x in near if len(x)])
            v = np.repeat(vals[m], lens)
            cnt[:, j] = np.bincount(si, minlength=n)
            if agg == "sum":
                acc[:, j] = np.bincount(si, weights=v, minlength=n)
            else:
                col = np.full(n, -np.inf)
                np.maximum.at(col, si, v)
                acc[:, j] = np.where(np.isfinite(col), col, np.nan)
    return pd.DataFrame(
        {
            "site_id": np.repeat(sites["site_id"].to_numpy(), nd),
            "date": np.tile(days.values, n),
            count_name: cnt.ravel(),
            agg_name: acc.ravel(),
        }
    )


class EarthquakesCollector(Collector):
    name = "earthquakes"
    description = "Terremotos: conteo diario (EMSC) y estadísticas históricas M>=4 (USGS)"
    source = "EMSC FDSN event service / USGS ComCat"
    source_url = "https://www.seismicportal.eu ; https://earthquake.usgs.gov/fdsnws/event/1/"
    license = "EMSC: CC BY 4.0 ; USGS: dominio público"
    confidence = 0.8
    fields = {
        "sites_daily": ["eq_count_100km", "eq_max_mag_100km"],
        "sites_static": ["n_eq_m4_100km_50y", "max_mag_100km_hist", "dist_m5_epicenter_km"],
    }

    def _emsc_year(self, y0, y1):
        c = self.cfg["earthquakes"]
        bb = eq_bbox(self.cfg)
        dest = self.lake.raw / "earthquakes" / f"emsc_{y0:%Y%m%d}_{y1:%Y%m%d}.txt"
        p = self.lake.cached_get(
            EMSC,
            dest,
            params={
                "start": f"{y0:%Y-%m-%d}",
                "end": f"{y1:%Y-%m-%d}",
                "minmag": c["daily_min_magnitude"],
                "minlat": bb["minlatitude"],
                "maxlat": bb["maxlatitude"],
                "minlon": bb["minlongitude"],
                "maxlon": bb["maxlongitude"],
                "format": "text",
                "limit": EMSC_LIMIT,
            },
            timeout=300,
            sleep=1,
            min_bytes=0,
        )
        if p is None or p.stat().st_size == 0:
            return pd.DataFrame()
        df = pd.read_csv(p, sep="|")
        if len(df) >= EMSC_LIMIT and y1 - y0 > pd.Timedelta(
            days=2
        ):  # truncated answer: split the period
            mid = (y0 + (y1 - y0) / 2).normalize()
            return pd.concat(
                [self._emsc_year(y0, mid), self._emsc_year(mid, y1)], ignore_index=True
            )
        df.columns = [c.strip().lstrip("#") for c in df.columns]
        return pd.DataFrame(
            {
                "time": pd.to_datetime(df["Time"], utc=True, errors="coerce").dt.tz_localize(None),
                "lat": df["Latitude"],
                "lon": df["Longitude"],
                "mag": df["Magnitude"],
            }
        )

    def _usgs(self, t0, t1, bb) -> list[pd.DataFrame]:
        """USGS M>=4 catalogue; a query over its 20,000-event limit (HTTP 400) is split in two."""
        import requests

        dest = self.lake.raw / "earthquakes" / f"usgs_m4_{t0:%Y-%m-%d}_{t1:%Y-%m-%d}.csv"
        try:
            pth = self.lake.cached_get(
                USGS,
                dest,
                params={
                    "format": "csv",
                    "starttime": f"{t0:%Y-%m-%d}",
                    "endtime": f"{t1:%Y-%m-%d}",
                    "minmagnitude": 4,
                    **bb,
                },
                timeout=300,
                min_bytes=0,
            )
        except requests.HTTPError as e:
            if (
                e.response is not None
                and e.response.status_code == 400
                and t1 - t0 > pd.Timedelta(days=60)
            ):
                mid = (t0 + (t1 - t0) / 2).normalize()
                return self._usgs(t0, mid, bb) + self._usgs(mid, t1, bb)
            raise
        return [pd.read_csv(pth)] if pth is not None and pth.stat().st_size > 0 else []

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
        ev = (
            pd.concat(frames, ignore_index=True).dropna(subset=["lat", "lon"])
            if frames
            else pd.DataFrame()
        )
        if len(ev):
            ev["date"] = ev["time"].dt.normalize()
        self.lake.catalog("emsc_catalog", "EMSC", EMSC, "CC BY 4.0")
        # what EMSC really lists varies by country (Spain from M1.5, US ~M2, Japan ~M3): measured
        # on the whole download and kept in the lineage
        self._mc = float(ev["mag"].quantile(0.1)) if len(ev) else None
        if len(ev):  # one threshold for every country, so that the counts can be compared
            ev = ev[ev["mag"] >= count_min_magnitude(self.cfg)]
        for y in sorted(set(days.year)):
            dy = days[days.year == y]
            sub = ev[ev["date"].dt.year == y] if len(ev) else ev
            d = daily_counts(
                sites,
                sub,
                c["daily_radius_km"],
                dy,
                "mag",
                "eq_count_100km",
                "eq_max_mag_100km",
                "max",
            )
            self.stage("sites_daily", d, year=int(y))

        # historical statistics (USGS M>=4 since static_start)
        frames = self._usgs(
            pd.Timestamp(c["static_start"]), pd.Timestamp(p["end"]), eq_bbox(self.cfg)
        )
        us = (
            pd.concat(frames, ignore_index=True).rename(
                columns={"latitude": "lat", "longitude": "lon"}
            )
            if frames
            else pd.DataFrame()
        )
        self.lake.catalog("usgs_comcat_m4", "USGS ComCat", USGS, "Dominio público")
        st = pd.DataFrame({"site_id": sites["site_id"].values})
        if len(us):
            ug = geo.points_from_lonlat(us)
            sxy = np.column_stack([sites["x"].values, sites["y"].values])
            nb = geo.neighbours_within(sxy, geo.xy(ug), 100)
            st["n_eq_m4_100km_50y"] = [len(i) for i in nb]
            st["max_mag_100km_hist"] = [
                float(ug["mag"].values[i].max()) if i else np.nan for i in nb
            ]
            m5 = ug[ug["mag"] >= 5]
            st["dist_m5_epicenter_km"] = geo.nearest(geo.site_points(sites), m5)["dist_km"].values
        self.stage("sites_static", st)

    def write_lineage(self, **kw):
        mc = getattr(self, "_mc", None)
        mmin = count_min_magnitude(self.cfg)
        note = f"EMSC, solo eventos M>={mmin:.1f} (umbral común a todos los países)"
        if mc is not None and mc > mmin + 0.25:
            iso = self.cfg["project"]["country_iso3"]
            note += (
                f"; en {iso} EMSC solo es completo desde M{mc:.1f} aprox. (percentil 10): "
                f"el conteo está infravalorado frente a otros países"
            )
        daily = {"notes": note}
        super().write_lineage(
            per_field={
                "n_eq_m4_100km_50y": {
                    "notes": "USGS ComCat desde config.earthquakes.static_start (no son "
                    "exactamente 50 años)"
                },
                **({"eq_count_100km": daily, "eq_max_mag_100km": daily} if mc is not None else {}),
            }
        )


FIRMS_COUNTRY = (
    "https://firms.modaps.eosdis.nasa.gov/data/country/{prod}/{year}/{prod}_{year}_{country}.csv"
)
FIRMS_COUNTRY_PRODUCT = {
    "MODIS_SP": "modis",
    "VIIRS_SNPP_SP": "viirs-snpp",
    "VIIRS_NOAA20_SP": "viirs-noaa20",
}


class FIRMSCollector(Collector):
    name = "firms"
    description = (
        "Focos de incendio diarios (NASA FIRMS: archivo anual por país sin clave, o API con clave)"
    )
    source = "NASA FIRMS (MODIS/VIIRS Standard Processing)"
    source_url = "https://firms.modaps.eosdis.nasa.gov/country/"
    license = "NASA Earth Science data: uso libre con atribución"
    spatial_resolution_m = 1000
    confidence = 0.8
    fields = {"sites_daily": ["fire_detections_10km", "fire_frp_sum_10km"]}

    def _country_archive(self, days) -> list[pd.DataFrame]:
        """Yearly country CSVs (no key). Only completed years exist; Spain only (border fires
        abroad are missed)."""
        frames = []
        country = self.cfg["project"].get("firms_name") or self.cfg["project"].get("name", "Spain")
        for src in self.cfg["fires"]["sources"]:
            prod = FIRMS_COUNTRY_PRODUCT.get(src)
            if not prod:
                continue
            for y in sorted(set(days.year)):
                url = FIRMS_COUNTRY.format(prod=prod, year=y, country=country)
                try:
                    pth = self.lake.cached_get(
                        url,
                        self.lake.raw / "firms" / "country" / f"{prod}_{y}_{country}.csv",
                        timeout=300,
                        sleep=1,
                        validate=lambda b: b.lstrip()[:8] == b"latitude",
                    )
                except Exception as e:
                    self.log.error("  FIRMS %s %d: %s", prod, y, e)
                    continue
                if pth is None:
                    self.log.warning(
                        "  FIRMS %s %d: sin archivo anual (año en curso: hace falta "
                        "FIRMS_MAP_KEY)",
                        prod,
                        y,
                    )
                    continue
                df = pd.read_csv(pth)
                if "type" in df:
                    df = df[
                        df["type"] == 0
                    ]  # 0 = vegetation fire (drop static industrial sources, offshore)
                frames.append(df[["latitude", "longitude", "acq_date", "frp"]])
        return frames

    def run(self, sites):
        from tqdm import tqdm

        key = self.cfg.secret("FIRMS_MAP_KEY")
        p = self.cfg["period"]
        days = pd.date_range(p["start"], p["end"], freq="D")
        frames = [] if key else self._country_archive(days)
        for src in self.cfg["fires"]["sources"] if key else []:
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
        ev = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=["latitude", "longitude", "acq_date", "frp"])
        )
        ev = ev.rename(columns={"latitude": "lat", "longitude": "lon"})
        ev["date"] = pd.to_datetime(ev["acq_date"])
        for y in sorted(set(days.year)):
            dy = days[days.year == y]
            d = daily_counts(
                sites,
                ev[ev["date"].dt.year == y],
                self.cfg["fires"]["radius_km"],
                dy,
                "frp",
                "fire_detections_10km",
                "fire_frp_sum_10km",
                "sum",
            )
            self.stage("sites_daily", d, year=int(y))

    def write_lineage(self, **kw):
        note = (
            "Solo incendios de vegetación (type=0). Sin clave: archivo anual de España, sin "
            "focos "
            "al otro lado "
            "de la frontera ni año en curso"
        )
        super().write_lineage(per_field={f: {"notes": note} for f in self.fields["sites_daily"]})
