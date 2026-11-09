"""Airports (OurAirports), submarine cables (TeleGeography) and coastline (Natural Earth)."""
from __future__ import annotations

import re
from datetime import date

import numpy as np
import pandas as pd

from .. import geo
from .base import Collector

OA = "https://davidmegginson.github.io/ourairports-data/{f}"
CABLE = "https://www.submarinecablemap.com/api/v3/{p}"
NE_COAST = "https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip"


class AirportsCollector(Collector):
    name = "ourairports"
    description = "Aeropuertos, pistas y conos de aproximación (OurAirports)"
    source = "OurAirports"
    source_url = "https://ourairports.com/data/"
    license = "Dominio público"
    confidence = 0.8
    fields = {"sites_static": ["dist_airport_km", "dist_airport_runway_km", "in_flight_path_flag"]}

    def run(self, sites):
        import geopandas as gpd
        from shapely.geometry import Polygon
        ap = pd.read_csv(self.lake.cached_get(OA.format(f="airports.csv"), self.lake.raw / "ourairports" / "airports.csv"))
        rw = pd.read_csv(self.lake.cached_get(OA.format(f="runways.csv"), self.lake.raw / "ourairports" / "runways.csv"))
        self.lake.catalog("ourairports", self.source, self.source_url, self.license)
        ap = ap[ap["iso_country"].isin(["ES", "PT", "FR", "AD", "GI", "MA"])]
        comm = ap[ap["type"].isin(["large_airport", "medium_airport"]) & (ap["scheduled_service"] == "yes")]
        pts = geo.site_points(sites)
        df = pd.DataFrame({"site_id": sites["site_id"].values})
        apg = geo.points_from_lonlat(comm.rename(columns={"longitude_deg": "lon", "latitude_deg": "lat"}))
        df["dist_airport_km"] = geo.nearest(pts, apg)["dist_km"].values

        rw = rw[rw["airport_ref"].isin(comm["id"]) & (rw["closed"] == 0)].dropna(
            subset=["le_latitude_deg", "le_longitude_deg", "he_latitude_deg", "he_longitude_deg"])
        if len(rw) == 0:
            self.stage("sites_static", df)
            return
        le = geo.points_from_lonlat(rw.rename(columns={"le_longitude_deg": "lon", "le_latitude_deg": "lat"}))
        he = geo.points_from_lonlat(rw.rename(columns={"he_longitude_deg": "lon", "he_latitude_deg": "lat"}))
        from shapely.geometry import LineString
        segs, funnels = [], []
        for a, b in zip(le.geometry, he.geometry):
            segs.append(LineString([a, b]))
            v = np.array([b.x - a.x, b.y - a.y])
            n = np.linalg.norm(v)
            if n == 0:
                continue
            u = v / n
            perp = np.array([-u[1], u[0]])
            for thr, out in ((np.array([a.x, a.y]), -u), (np.array([b.x, b.y]), u)):
                far = thr + out * 15000
                funnels.append(Polygon([thr + perp * 150, far + perp * 2400, far - perp * 2400, thr - perp * 150]))
        segs = gpd.GeoDataFrame(geometry=segs, crs=geo.EQUAL_AREA)
        df["dist_airport_runway_km"] = geo.nearest(pts, segs)["dist_km"].values
        fun = gpd.GeoDataFrame(geometry=funnels, crs=geo.EQUAL_AREA)
        cells = sites[["geometry"]].reset_index(drop=True).assign(_i=lambda x: np.arange(len(x)))
        j = gpd.sjoin(cells, fun, predicate="intersects")
        flag = np.zeros(len(cells), dtype=bool)
        flag[j["_i"].unique()] = True
        df["in_flight_path_flag"] = flag
        self.stage("sites_static", df)

    def write_lineage(self, **kw):
        super().write_lineage(per_field={"in_flight_path_flag": {
            "imputation_method": "modelo", "confidence": 0.5,
            "notes": "Embudo simplificado: 15 km desde el umbral, 150 m de semiancho que se abre un 15 % por lado"}})


class CablesCollector(Collector):
    name = "submarine_cables"
    description = "Estaciones de amarre de cables submarinos (TeleGeography)"
    source = "TeleGeography Submarine Cable Map"
    source_url = "https://www.submarinecablemap.com"
    license = "CC BY-SA 4.0"
    confidence = 0.8
    fields = {"sites_static": ["dist_cable_landing_km", "n_cables_nearest_landing", "newest_cable_year",
                               "planned_cables_flag", "n_submarine_cables_country"]}

    def run(self, sites):
        raw = self.lake.raw / "cables"
        lp = self.lake.get_json(CABLE.format(p="landing-point/landing-point-geo.json"), raw / "landing-points.json")
        rows = [{"id": f["properties"]["id"], "name": f["properties"].get("name", ""),
                 "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
                for f in lp["features"]]
        lp = pd.DataFrame(rows)
        lp = lp[lp["lon"].between(-20, 10) & lp["lat"].between(25, 48)].reset_index(drop=True)
        info, year_cache = [], {}
        this_year = date.today().year
        for _, r in lp.iterrows():
            d = self.lake.get_json(CABLE.format(p=f"landing-point/{r['id']}.json"), raw / f"lp_{r['id']}.json", sleep=0.3)
            cables = (d or {}).get("cables", [])
            years = []
            for c in cables:
                cid = c.get("id")
                if cid not in year_cache:
                    cd = self.lake.get_json(CABLE.format(p=f"cable/{cid}.json"), raw / f"cable_{cid}.json", sleep=0.3) or {}
                    m = re.search(r"(19|20)\d{2}", str(cd.get("rfs_year") or cd.get("rfs") or ""))
                    year_cache[cid] = int(m.group(0)) if m else np.nan
                years.append(year_cache[cid])
            yrs = [y for y in years if not np.isnan(y)]
            info.append({"n_cables": len(cables), "newest": max(yrs) if yrs else np.nan,
                         "planned": any(y > this_year for y in yrs), "cable_ids": [c.get("id") for c in cables]})
        lp = pd.concat([lp, pd.DataFrame(info)], axis=1)
        self.lake.catalog("telegeography_cables", self.source, self.source_url, self.license)
        lpg = geo.points_from_lonlat(lp)
        pts = geo.site_points(sites)
        nn = geo.nearest(pts, lpg, ["n_cables", "newest", "planned"])
        es = lp[lp["name"].str.contains("Spain", case=False, na=False)]
        n_country = len({c for ids in es["cable_ids"] for c in ids})
        df = pd.DataFrame({"site_id": sites["site_id"].values,
                           "dist_cable_landing_km": nn["dist_km"].values,
                           "n_cables_nearest_landing": nn["n_cables"].values,
                           "newest_cable_year": nn["newest"].values,
                           "planned_cables_flag": nn["planned"].values,
                           "n_submarine_cables_country": n_country})
        self.stage("sites_static", df)


class CoastCollector(Collector):
    name = "coastline"
    description = "Distancia a la costa (Natural Earth 1:10m)"
    source = "Natural Earth 10m coastline"
    source_url = "https://www.naturalearthdata.com"
    license = "Dominio público"
    confidence = 0.8
    spatial_resolution_m = 1000
    fields = {"sites_static": ["dist_coast_km"]}

    def run(self, sites):
        import geopandas as gpd
        p = self.lake.cached_get(NE_COAST, self.lake.raw / "naturalearth" / "ne_10m_coastline.zip")
        coast = gpd.read_file(f"zip://{p}").cx[-25:10, 20:50].to_crs(geo.EQUAL_AREA)
        coast.to_parquet(self.lake.processed / "coastline.parquet")
        self.lake.catalog("naturalearth_coastline", self.source, NE_COAST, self.license)
        nn = geo.nearest(geo.site_points(sites), coast)
        self.stage("sites_static", pd.DataFrame({"site_id": sites["site_id"].values, "dist_coast_km": nn["dist_km"].values}))
