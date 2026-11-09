"""Seismic stations (FDSN) and ambient-noise features on sampled days (ObsPy)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import geo, hv
from .base import Collector

STATION_FIELDS = ["station_id", "network_code", "lat", "lon", "elevation_m", "depth_m", "datacenter_fdsn",
                  "operational_start", "operational_end", "is_active", "location_code", "station_name",
                  "network_type", "open_data_flag", "sensor_model", "digitizer_model", "n_components",
                  "has_broadband_flag", "has_accelerometer_flag", "max_sampling_rate_hz", "response_available_flag",
                  "sensor_corner_period_s", "median_psd_vs_nlnm_db", "noise_seasonal_range_db", "n_days_downloaded",
                  "n_sites_assigned"]


def _clients(names):
    from obspy.clients.fdsn import Client, RoutingClient
    out = {}
    for n in names:
        try:
            out[n] = RoutingClient(n) if "routing" in n or "federator" in n else Client(n, timeout=120)
        except Exception:
            pass
    return out


def sample_dates(start, end, per_year: int) -> list[pd.Timestamp]:
    """Evenly spread dates (mid-month) per year inside [start, end]."""
    out = []
    for y in range(start.year, end.year + 1):
        months = np.linspace(1, 12, per_year, endpoint=False).round().astype(int) + 0
        for mth in months:
            d = pd.Timestamp(year=y, month=int(np.clip(mth, 1, 12)), day=15)
            if start <= d <= end:
                out.append(d)
    return out


class SeismicCollector(Collector):
    name = "seismic"
    description = "Estaciones sísmicas y features de ruido ambiental (H/V, PSD) en días muestreados"
    source = "FDSN (EIDA, EarthScope/IRIS) vía ObsPy"
    source_url = "https://www.orfeus-eu.org/data/eida/ ; https://ds.iris.edu"
    license = "Licencias por red sísmica (ver DOI de cada red)"
    confidence = 0.6
    fields = {
        "stations": STATION_FIELDS,
        "signal_features": ["record_id", "station_id", "channel_codes", "sampling_rate_hz", "sensor_type",
                            "record_start_utc", "record_hours", "n_windows_valid", "data_completeness_pct",
                            "hv_f0_hz", "hv_a0", "hv_f0_std", "hv_sesame_reliable", "hv_sesame_clear_peak",
                            "hv_second_peak_hz", "hv_curve", "psd_p50_db_0_1_1hz", "psd_p50_db_1_10hz",
                            "psd_p50_db_10_30hz", "psd_vs_nlnm_db", "day_night_ratio", "weekday_weekend_ratio",
                            "dominant_freq_hz", "spectral_centroid_hz", "spectral_bandwidth_hz",
                            "spectral_rolloff_hz", "rms_velocity", "kurtosis", "n_transients_hour",
                            "noise_source_class"],
        "sites_static": ["nearest_station_id", "dist_station_km", "hv_f0_hz", "hv_a0", "ambient_vibration_db",
                         "hv_confidence"],
    }

    # ----------------------------------------------------------- stations
    def _inventory(self, clients):
        from obspy import UTCDateTime
        p = self.cfg["period"]
        s = self.cfg["seismic"]
        rows = []
        for cname, cl in clients.items():
            for bb in self.cfg["bboxes"].values():
                m = 1.0  # ~100 km margin
                try:
                    inv = cl.get_stations(minlongitude=bb[0] - m, minlatitude=bb[1] - m, maxlongitude=bb[2] + m,
                                          maxlatitude=bb[3] + m, channel=s["channels"], level="channel",
                                          starttime=UTCDateTime(p["start"]), endtime=UTCDateTime(p["end"]))
                except Exception as e:
                    self.log.warning("  get_stations %s: %s", cname, e)
                    continue
                for net in inv:
                    for sta in net:
                        chans = list(sta.channels)
                        codes = sorted({c.code for c in chans})
                        bands = {c[:2] for c in codes}
                        rows.append({
                            "station_id": f"{net.code}.{sta.code}", "network_code": net.code,
                            "lat": sta.latitude, "lon": sta.longitude, "elevation_m": sta.elevation,
                            "depth_m": float(np.nanmax([c.depth or 0 for c in chans])) if chans else np.nan,
                            "datacenter_fdsn": cname,
                            "operational_start": pd.Timestamp(str(sta.start_date)).tz_localize(None) if sta.start_date else pd.NaT,
                            "operational_end": pd.Timestamp(str(sta.end_date)).tz_localize(None) if sta.end_date else pd.NaT,
                            "location_code": ",".join(sorted({c.location_code for c in chans})),
                            "station_name": sta.site.name if sta.site else None,
                            "network_type": "temporal" if net.code[:1].isdigit() or net.code[:1] in "XYZ" else "permanente",
                            "open_data_flag": (net.restricted_status or "open") == "open",
                            "sensor_model": next((c.sensor.description for c in chans if c.sensor and c.sensor.description), None),
                            "digitizer_model": next((c.data_logger.description for c in chans if c.data_logger and c.data_logger.description), None),
                            "n_components": max((sum(1 for c in codes if c[:2] == b) for b in bands), default=0),
                            "has_broadband_flag": any(b in ("HH", "BH") for b in bands),
                            "has_accelerometer_flag": any(b[1] == "N" for b in bands),
                            "max_sampling_rate_hz": max((c.sample_rate or 0) for c in chans) if chans else np.nan,
                            "_codes": codes,
                        })
        st = pd.DataFrame(rows)
        if st.empty:
            return st
        st = st.drop_duplicates("station_id").reset_index(drop=True)
        now = pd.Timestamp.utcnow().tz_localize(None)
        st["is_active"] = st["operational_end"].isna() | (st["operational_end"] > now)
        return st

    # ----------------------------------------------------------- features
    def _record(self, cl, inv, sid, band, t0, minutes):
        from obspy import UTCDateTime
        net, sta = sid.split(".")
        s = self.cfg["seismic"]
        raw = self.lake.raw / "seismic" / sid / f"{t0:%Y%m%d_%H%M}.mseed"
        raw.parent.mkdir(parents=True, exist_ok=True)
        from obspy import read
        if raw.exists():
            st = read(str(raw))
        else:
            st = cl.get_waveforms(net, sta, "*", f"{band}?", UTCDateTime(t0), UTCDateTime(t0) + minutes * 60)
            if not s["keep_raw_waveforms"]:
                pass
            else:
                st.write(str(raw), format="MSEED")
        st.merge(method=1, fill_value=0)
        comps = {}
        for tr in st:
            c = tr.stats.channel[-1]
            key = {"Z": "Z", "N": "N", "1": "N", "E": "E", "2": "E"}.get(c)
            if key and key not in comps:
                comps[key] = tr
        if len(comps) < 3:
            return None
        fs = comps["Z"].stats.sampling_rate
        expected = minutes * 60 * fs
        completeness = 100 * min(len(t.data) for t in comps.values()) / expected
        vel = False
        if inv is not None:
            try:
                for tr in comps.values():
                    tr.remove_response(inventory=inv, output="VEL",
                                       pre_filt=(0.05, 0.08, 0.4 * fs, 0.45 * fs), water_level=60)
                vel = True
            except Exception:
                vel = False
        z, n, e = comps["Z"].data, comps["N"].data, comps["E"].data
        r = hv.hv_ratio(z, n, e, fs, s["hv_window_s"], s["hv_fmin"], s["hv_fmax"], s["konno_ohmachi_b"])
        sf = hv.spectral_features(z, fs, vel_units=vel)
        f_, pacc = sf.pop("_f", None), sf.pop("_pacc", None)
        rec = {"station_id": sid, "channel_codes": ",".join(sorted(t.stats.channel for t in comps.values())),
               "sampling_rate_hz": fs, "sensor_type": "acelerometro" if band[1] == "N" else "banda_ancha",
               "record_start_utc": t0, "record_hours": minutes / 60, "data_completeness_pct": completeness,
               **{k: v for k, v in r.items() if k != "hv_freqs"}, **sf}
        rec["psd_vs_nlnm_db"] = hv.psd_vs_nlnm(f_, pacc) if f_ is not None else np.nan
        try:
            rec["n_transients_hour"] = hv.count_transients(z, fs) / (minutes / 60)
        except Exception:
            rec["n_transients_hour"] = np.nan
        return rec

    def run(self, sites):
        from tqdm import tqdm
        s = self.cfg["seismic"]
        clients = _clients(s["networks_clients"])
        if not clients:
            raise RuntimeError("No se pudo crear ningún cliente FDSN")
        st = self._inventory(clients)
        if st.empty:
            self.log.error("  sin estaciones")
            return
        # 3-component broadband stations only for H/V
        st["_band"] = st["_codes"].map(lambda cs: next((b for b in ("HH", "BH") if sum(c[:2] == b for c in cs) >= 3), None))
        usable = st[st["_band"].notna()].reset_index(drop=True)
        stg = geo.points_from_lonlat(usable)
        pts = geo.site_points(sites)
        nn = geo.nearest(pts, stg, ["station_id"])
        assign = pd.DataFrame({"site_id": sites["site_id"].values, "nearest_station_id": nn["station_id"].values,
                               "dist_station_km": nn["dist_km"].values})
        assign.loc[assign["dist_station_km"] > s["max_station_km"], "nearest_station_id"] = pd.NA
        needed = usable[usable["station_id"].isin(assign["nearest_station_id"].dropna())]
        self.log.info("  %d estaciones en total, %d usadas por la muestra", len(st), len(needed))

        p = self.cfg["period"]
        dates = sample_dates(pd.Timestamp(p["start"]), pd.Timestamp(p["end"]), s["days_per_year"])
        recs = []
        for _, row in needed.iterrows():
            cl = clients[row["datacenter_fdsn"]]
            sid = row["station_id"]
            net, sta = sid.split(".")
            inv = None
            try:
                from obspy import read_inventory
                xml = self.lake.raw / "seismic" / sid / "response.xml"
                xml.parent.mkdir(parents=True, exist_ok=True)
                if xml.exists():
                    inv = read_inventory(str(xml))
                else:
                    inv = cl.get_stations(network=net, station=sta, channel=f"{row['_band']}?", level="response")
                    inv.write(str(xml), format="STATIONXML")
            except Exception as e:
                self.log.warning("  %s sin respuesta instrumental (%s); PSD no calibrada", sid, e)
            st.loc[st["station_id"] == sid, "response_available_flag"] = inv is not None
            for d in tqdm(dates, desc=sid, leave=False):
                if d < row["operational_start"] or (pd.notna(row["operational_end"]) and d > row["operational_end"]):
                    continue
                for w in s["windows_utc"]:
                    t0 = pd.Timestamp(f"{d:%Y-%m-%d} {w}")
                    try:
                        r = self._record(cl, inv, sid, row["_band"], t0, s["window_minutes"])
                    except Exception as e:
                        self.log.debug("  %s %s: %s", sid, t0, e)
                        r = None
                    if r:
                        r["record_id"] = f"{sid}_{t0:%Y%m%d_%H%M}"
                        recs.append(r)
        sf = pd.DataFrame(recs)
        if not sf.empty:
            sf["date"] = pd.to_datetime(sf["record_start_utc"]).dt.normalize()
            # day/night ratio on the same date
            sf["_hour"] = pd.to_datetime(sf["record_start_utc"]).dt.hour
            night = sf[sf["_hour"] < 6].set_index(["station_id", "date"])["rms_velocity"]
            key = list(zip(sf["station_id"], sf["date"]))
            sf["day_night_ratio"] = [r / night.get(k, np.nan) if h >= 6 else np.nan
                                     for r, k, h in zip(sf["rms_velocity"], key, sf["_hour"])]
            wk = pd.to_datetime(sf["date"]).dt.day_of_week < 5
            ratio = sf[wk].groupby("station_id")["rms_velocity"].mean() / sf[~wk].groupby("station_id")["rms_velocity"].mean()
            sf["weekday_weekend_ratio"] = sf["station_id"].map(ratio)
            sf["noise_source_class"] = [hv.classify_noise(a, b, c) for a, b, c in
                                        zip(sf.get("psd_p50_db_1_10hz", np.nan), sf.get("psd_p50_db_10_30hz", np.nan),
                                            sf["day_night_ratio"].fillna(np.nan))]
            # station aggregates
            agg = sf.groupby("station_id").agg(median_psd_vs_nlnm_db=("psd_vs_nlnm_db", "median"),
                                               n_days_downloaded=("date", "nunique"))
            month = pd.to_datetime(sf["date"]).dt.month
            mon = sf.assign(m=month).groupby(["station_id", "m"])["psd_p50_db_1_10hz"].median().groupby("station_id")
            agg["noise_seasonal_range_db"] = mon.max() - mon.min()
            st = st.drop(columns=[c for c in agg.columns if c in st], errors="ignore").merge(
                agg.reset_index(), on="station_id", how="left")
            self.stage("signal_features", sf.drop(columns=["date", "_hour"]))

            # per-site aggregates from the assigned station (reliable windows preferred)
            good = sf[sf["hv_sesame_reliable"] == True]  # noqa: E712
            src = good if len(good) else sf
            sagg = src.groupby("station_id").agg(hv_f0_hz=("hv_f0_hz", "median"), hv_a0=("hv_a0", "median"))
            rel = sf.groupby("station_id")["hv_sesame_reliable"].mean()
            amb = sf.groupby("station_id")["psd_p50_db_1_10hz"].median() if "psd_p50_db_1_10hz" in sf else pd.Series(dtype=float)
            assign = assign.merge(sagg.reset_index().rename(columns={"station_id": "nearest_station_id"}),
                                  on="nearest_station_id", how="left")
            assign["ambient_vibration_db"] = assign["nearest_station_id"].map(amb)
            dist_term = (1 - assign["dist_station_km"] / s["max_station_km"]).clip(0, 1)
            assign["hv_confidence"] = dist_term * (0.5 + 0.5 * assign["nearest_station_id"].map(rel).fillna(0))
        st["n_sites_assigned"] = st["station_id"].map(assign["nearest_station_id"].value_counts()).fillna(0)
        self.stage("stations", st.drop(columns=["_codes", "_band"], errors="ignore"))
        self.stage("sites_static", assign)
        self.lake.catalog("fdsn_stations_waveforms", self.source, self.source_url, self.license)

    def write_lineage(self, **kw):
        super().write_lineage(per_field={
            "hv_confidence": {"imputation_method": "modelo", "notes": "(1 - dist/max_dist) x (0.5 + 0.5 x fracción de registros fiables SESAME)"},
            "noise_source_class": {"imputation_method": "reglas", "confidence": 0.3, "notes": "Reglas sobre PSD y ratio día/noche"},
            "hv_f0_hz": {"notes": "Heredado de la estación más cercana: indicador regional, no de la parcela"},
        })
