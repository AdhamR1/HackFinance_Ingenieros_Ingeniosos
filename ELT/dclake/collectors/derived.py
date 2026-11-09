"""Fields computed from other collectors' outputs (runs last)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import geo
from ..assemble import merge_staged
from ..grid import norm
from ..schema import load_schemas
from .base import Collector

def complete_sum(s: pd.Series, min_frac: float = 0.9) -> float:
    """Annual total only when at least 90 % of the days have data (missing days are not zeros)."""
    return s.sum() if s.notna().sum() >= min_frac * len(s) else np.nan


CLIMATE_YEARLY = {
    "mean_temp_c": ("t2m_mean_c", "mean"),
    "max_temp_p99_c": ("t2m_max_c", lambda s: s.quantile(0.99)),
    "min_temp_p01_c": ("t2m_min_c", lambda s: s.quantile(0.01)),
    "cooling_degree_days": ("cdd_18", complete_sum),
    "heating_degree_days": ("hdd_18", complete_sum),
    "wetbulb_p99_c": ("wetbulb_max_c", lambda s: s.quantile(0.99)),
    "dewpoint_mean_c": ("td2m_mean_c", "mean"),
    "rel_humidity_mean_pct": ("rh_mean_pct", "mean"),
    "free_cooling_hours": ("free_cooling_hours", complete_sum),
    "adiabatic_cooling_hours": ("adiabatic_cooling_hours", complete_sum),
    "heatwave_days_year": ("heatwave_flag", complete_sum),
    "tropical_nights_year": ("tropical_night_flag", complete_sum),
    "frost_days_year": ("frost_flag", complete_sum),
    "extreme_cold_days_year": ("extreme_cold_flag", complete_sum),
    "annual_precip_mm": ("precip_mm", complete_sum),
    "max_daily_precip_p99_mm": ("precip_mm", lambda s: s.quantile(0.99)),
    "wind_speed_mean_ms": ("wind10m_mean_ms", "mean"),
    "solar_ghi_kwh_m2": ("ssrd_kwh_m2", complete_sum),
}
MIN_DAYS_PER_YEAR = 330   # incomplete years (first/last of the period) are not aggregated


def soil_class_from_vs30(v):
    if v is None or not np.isfinite(v):
        return pd.NA
    return "A" if v > 800 else "B" if v > 360 else "C" if v > 180 else "D"


class DerivedCollector(Collector):
    name = "derived"
    description = "Campos calculados a partir de otros colectores"
    source = "Cálculo propio a partir de otras fuentes del data lake"
    imputation_method = "derivado"
    fields = {
        "sites_yearly": list(CLIMATE_YEARLY) + ["diurnal_range_c", "est_pue", "est_wue_l_kwh",
                                                "wholesale_price_mean_usd_mwh", "electricity_price_volatility",
                                                "renewable_share_pct", "grid_carbon_intensity_gco2_kwh"],
        "sites_static": ["soil_class", "in_low_elevation_coastal_zone"],
        "stations": ["country_iso3", "h3_cell_r7", "dist_nearest_other_station_km", "dist_station_road_m",
                     "dist_station_coast_km", "spatial_cv_fold", "data_split", "is_label_station"],
    }

    def _others(self):
        return [c for c in self.lake.staged_collectors() if c != self.name]

    def run(self, sites):
        specs = load_schemas(self.cfg.dictionary_path)
        others = self._others()
        self._yearly(sites, specs, others)
        self._static(specs, others)
        self._stations(specs, others)

    # ------------------------------------------------------------ yearly
    def _yearly(self, sites, specs, others):
        c = self.cfg["climate"]
        p = self.cfg["period"]
        frames = []
        for y in range(pd.Timestamp(p["start"]).year, pd.Timestamp(p["end"]).year + 1):
            d = merge_staged(self.lake, self.cfg, specs["sites_daily"], others, year=y)
            if "t2m_mean_c" not in d or d["t2m_mean_c"].notna().sum() == 0:
                continue
            num = [c for c in d.columns if c not in ("site_id", "date")]
            d[num] = d[num].apply(pd.to_numeric, errors="coerce")
            d = d[d["t2m_mean_c"].notna()]
            n = d.groupby("site_id").size()
            g = d.groupby("site_id")
            out = pd.DataFrame(index=g.size().index)
            for f, (col, how) in CLIMATE_YEARLY.items():
                if col in d:
                    out[f] = g[col].agg(how) if isinstance(how, str) else g[col].apply(how)
            out["diurnal_range_c"] = (d["t2m_max_c"] - d["t2m_min_c"]).groupby(d["site_id"]).mean()
            out = out[n.reindex(out.index) >= MIN_DAYS_PER_YEAR]
            hours = 24 * n.reindex(out.index)
            out["est_pue"] = c["pue_base"] + c["pue_mech_penalty"] * (1 - out["free_cooling_hours"] / hours)
            out["est_wue_l_kwh"] = c["wue_base_l_kwh"] + c["wue_cdd_coef"] * out["cooling_degree_days"]
            out["year"] = y
            frames.append(out.reset_index())
        yearly = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["site_id", "year"])

        cd = merge_staged(self.lake, self.cfg, specs["country_daily"], others)
        if "omie_price_mean_eur_mwh" in cd and cd["omie_price_mean_eur_mwh"].notna().any():
            cd["year"] = pd.to_datetime(cd["date"]).dt.year
            for col in ("omie_price_mean_usd_mwh", "omie_price_mean_eur_mwh", "renewable_share_pct",
                        "carbon_intensity_gco2_kwh", "gen_total_gwh"):
                cd[col] = pd.to_numeric(cd.get(col), errors="coerce")
            w = cd["gen_total_gwh"]
            g = cd.groupby("year")
            el = pd.DataFrame({
                "wholesale_price_mean_usd_mwh": g["omie_price_mean_usd_mwh"].mean(),
                "electricity_price_volatility": g["omie_price_mean_eur_mwh"].std(),
                "renewable_share_pct": (cd["renewable_share_pct"] * w).groupby(cd["year"]).sum() / w.groupby(cd["year"]).sum(),
                "grid_carbon_intensity_gco2_kwh": (cd["carbon_intensity_gco2_kwh"] * w).groupby(cd["year"]).sum() / w.groupby(cd["year"]).sum(),
            }).reset_index()
            islands = [norm(x) for x in self.cfg["electricity"]["island_admin1"]]
            mainland = sites[~sites["admin1"].map(lambda a: any(i in norm(a) for i in islands))][["site_id"]]
            el_sites = mainland.merge(el, how="cross")
            yearly = el_sites.merge(yearly, on=["site_id", "year"], how="outer") if len(yearly) else el_sites
        self.stage("sites_yearly", yearly)

    # ------------------------------------------------------------ static
    def _static(self, specs, others):
        s = merge_staged(self.lake, self.cfg, specs["sites_static"], others)
        out = s[["site_id"]].copy()
        if "vs30_ms" in s:
            out["soil_class"] = [soil_class_from_vs30(v) for v in pd.to_numeric(s["vs30_ms"], errors="coerce")]
        if {"elevation_m", "dist_coast_km"} <= set(s.columns):
            e = pd.to_numeric(s["elevation_m"], errors="coerce")
            dc = pd.to_numeric(s["dist_coast_km"], errors="coerce")
            out["in_low_elevation_coastal_zone"] = ((e < 10) & (dc < 25)).where(e.notna() & dc.notna())
        self.stage("sites_static", out)

    # ------------------------------------------------------------ stations
    def _stations(self, specs, others):
        import geopandas as gpd
        st = merge_staged(self.lake, self.cfg, specs["stations"], others)
        if st.empty or "lat" not in st:
            return
        st = st.dropna(subset=["lat", "lon"]).reset_index(drop=True)
        st["lat"] = pd.to_numeric(st["lat"]); st["lon"] = pd.to_numeric(st["lon"])
        g = geo.points_from_lonlat(st)
        out = pd.DataFrame({"station_id": st["station_id"].values})
        adm0 = self.lake.raw / "geoboundaries" / f"{self.cfg['project']['country_iso3']}_ADM0.geojson"
        if adm0.exists():
            land = gpd.read_file(adm0).to_crs(geo.EQUAL_AREA)
            out["country_iso3"] = np.where(geo.contains(g, land), self.cfg["project"]["country_iso3"], "OTRO")
        try:
            from ..grid import attach_h3
            out["h3_cell_r7"] = attach_h3(st[["lat", "lon"]].copy())["h3_cell_r7"].values
        except Exception:
            pass
        xy = geo.xy(g)
        if len(xy) > 1:
            from scipy.spatial import cKDTree
            d, _ = cKDTree(xy).query(xy, k=2)
            out["dist_nearest_other_station_km"] = d[:, 1] / 1000
        roads = [self.lake.processed / "osm" / f"{n}.parquet" for n in ("roads_main", "roads_primary")]
        roads = [gpd.read_parquet(p) for p in roads if p.exists()]
        if roads:
            r = gpd.GeoDataFrame(pd.concat(roads, ignore_index=True), crs=geo.EQUAL_AREA)
            out["dist_station_road_m"] = geo.nearest(g, r)["dist_km"].values * 1000
        coast = self.lake.processed / "coastline.parquet"
        if coast.exists():
            out["dist_station_coast_km"] = geo.nearest(g, gpd.read_parquet(coast))["dist_km"].values
        # spatial cross-validation: 100 km blocks -> 5 folds, so nearby stations share a fold
        bx, by = (xy[:, 0] // 100_000).astype(int), (xy[:, 1] // 100_000).astype(int)
        out["spatial_cv_fold"] = (bx * 7 + by * 13) % 5
        out["data_split"] = out["spatial_cv_fold"].map({0: "test", 1: "val"}).fillna("train")
        label_cols = [c for c in ("vs30_measured", "f0_published_hz") if c in st]
        out["is_label_station"] = st[label_cols].notna().any(axis=1).values if label_cols else False
        self.stage("stations", out)

    def write_lineage(self, **kw):
        super().write_lineage(per_field={
            "est_pue": {"imputation_method": "modelo", "confidence": 0.4,
                        "notes": "PUE = pue_base + pue_mech_penalty x (1 - horas free cooling / horas del año). Supuesto."},
            "est_wue_l_kwh": {"imputation_method": "modelo", "confidence": 0.3, "notes": "WUE = base + coef x CDD. Supuesto."},
            "wholesale_price_mean_usd_mwh": {"notes": "Media anual del precio OMIE en USD; NaN en Baleares y Canarias"},
            "in_low_elevation_coastal_zone": {"imputation_method": "proxy", "notes": "altitud < 10 m y a menos de 25 km de la costa"},
            "soil_class": {"notes": "Clases del Eurocódigo 8 a partir de Vs30 (la clase E no se puede deducir solo de Vs30)"},
        })
