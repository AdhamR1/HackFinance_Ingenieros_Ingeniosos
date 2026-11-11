"""PeeringDB (IXPs, colocation facilities) and hub distances/latencies."""

from __future__ import annotations

import pandas as pd

from .. import geo
from .base import Collector

PDB = "https://www.peeringdb.com/api/{obj}"
NEIGHBOUR_COUNTRIES = "ES,PT,FR,AD,MA"


def fetch_pdb(lake, obj: str, **params) -> pd.DataFrame | None:
    import os

    key = os.environ.get("PEERINGDB_API_KEY")
    headers = {"Authorization": f"Api-Key {key}"} if key else None
    tag = "_".join(f"{k}-{v}" for k, v in sorted(params.items())).replace(",", "-")
    js = lake.get_json(
        PDB.format(obj=obj),
        lake.raw / "peeringdb" / f"{obj}_{tag}.json",
        params=params,
        headers=headers,
        sleep=3,
    )
    lake.catalog(
        f"peeringdb_{obj}", "PeeringDB", PDB.format(obj=obj), "PeeringDB Acceptable Use Policy"
    )
    return pd.DataFrame(js["data"]) if js else None


class PeeringDBCollector(Collector):
    name = "peeringdb"
    description = "Puntos neutros (IXP) y colocations desde PeeringDB"
    source = "PeeringDB API"
    source_url = "https://www.peeringdb.com/apidocs/"
    license = "PeeringDB Acceptable Use Policy"
    confidence = 0.8
    fields = {
        "sites_static": [
            "dist_ixp_km",
            "n_ixp_100km",
            "n_networks_at_ixp",
            "n_colo_facilities_100km",
            "n_networks_100km",
            "n_carriers_nearest_colo",
        ]
    }

    def run(self, sites):
        cc = ",".join(self.cfg["project"].get("neighbours_iso2") or NEIGHBOUR_COUNTRIES.split(","))
        fac = fetch_pdb(self.lake, "fac", country__in=cc)
        ix = fetch_pdb(self.lake, "ix", country__in=cc)
        ixfac = fetch_pdb(self.lake, "ixfac", country__in=cc)
        pts = geo.site_points(sites)
        sxy = geo.xy(pts)
        df = pd.DataFrame({"site_id": sites["site_id"].values})

        fac = fac.rename(columns={"longitude": "lon", "latitude": "lat"})
        facg = geo.points_from_lonlat(fac)
        nn = geo.nearest(pts, facg, [c for c in ("carrier_count",) if c in facg.columns])
        if "carrier_count" in nn:
            df["n_carriers_nearest_colo"] = nn["carrier_count"].values
        fxy = geo.xy(facg)
        df["n_colo_facilities_100km"] = geo.count_within(sxy, fxy, 100)
        if "net_count" in facg.columns:
            df["n_networks_100km"] = geo.count_within(sxy, fxy, 100, facg["net_count"].values)

        # IXP location = mean position of its facilities
        loc = ixfac.merge(fac[["id", "lon", "lat"]], left_on="fac_id", right_on="id", how="inner")
        loc = loc.groupby("ix_id")[["lon", "lat"]].mean().reset_index()
        ixl = ix.merge(loc, left_on="id", right_on="ix_id", how="inner")
        ixg = geo.points_from_lonlat(ixl)
        attrs = [c for c in ("net_count",) if c in ixg.columns]
        nn = geo.nearest(pts, ixg, attrs)
        df["dist_ixp_km"] = nn["dist_km"].values
        if attrs:
            df["n_networks_at_ixp"] = nn["net_count"].values
        df["n_ixp_100km"] = geo.count_within(sxy, geo.xy(ixg), 100)
        self.stage("sites_static", df)


class HubsCollector(Collector):
    name = "hubs"
    description = "Distancias y latencias estimadas a grandes hubs de interconexión"
    source = "Coordenadas de hubs definidas en config.yaml; latencia por modelo de distancia"
    license = "-"
    imputation_method = "modelo"
    confidence = 0.5
    fields = {
        "sites_static": [
            "dist_major_hub_km",
            "latency_to_hub_ms",
            "latency_frankfurt_ms",
            "latency_ashburn_ms",
            "latency_singapore_ms",
            "latency_tokyo_ms",
        ]
    }

    def run(self, sites):
        h, lat = self.cfg["hubs"], self.cfg["latency"]
        df = pd.DataFrame({"site_id": sites["site_id"].values})

        def d(hub):
            lo, la = h[hub]
            return geo.haversine_km(sites["lon"].values, sites["lat"].values, lo, la)

        kw = {
            "route_factor": lat["route_factor"],
            "ms_per_km_rtt": lat["ms_per_km_rtt"],
            "fixed_ms": lat["fixed_ms"],
        }
        df["dist_major_hub_km"] = d(self.cfg["project"].get("main_hub", "madrid"))
        df["latency_to_hub_ms"] = geo.latency_ms(df["dist_major_hub_km"], **kw)
        for hub in ("frankfurt", "ashburn", "singapore", "tokyo"):
            df[f"latency_{hub}_ms"] = geo.latency_ms(d(hub), **kw)
        self.stage("sites_static", df)
