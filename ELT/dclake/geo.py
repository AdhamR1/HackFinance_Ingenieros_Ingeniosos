"""Geospatial helpers. All distance work happens in the equal-area CRS (metres)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EQUAL_AREA = "EPSG:3035"


def site_points(sites, crs: str = EQUAL_AREA):
    """Centroids of the sample cells as a point GeoDataFrame (index = site_id order)."""
    import geopandas as gpd
    pts = gpd.GeoDataFrame({"site_id": sites["site_id"].values},
                           geometry=gpd.points_from_xy(sites["x"], sites["y"]), crs=crs)
    return pts


def points_from_lonlat(df: pd.DataFrame, lon="lon", lat="lat", crs: str = EQUAL_AREA):
    import geopandas as gpd
    df = df.dropna(subset=[lon, lat])
    g = gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df[lon], df[lat]), crs="EPSG:4326")
    return g.to_crs(crs)


def nearest(left, right, attrs: list[str] | None = None) -> pd.DataFrame:
    """Distance (km) from each left geometry to the nearest right geometry, plus its attributes.

    Returns a DataFrame aligned with `left` (same order) with column dist_km and attrs.
    """
    import geopandas as gpd
    attrs = attrs or []
    if right is None or len(right) == 0:
        out = pd.DataFrame({"dist_km": np.nan}, index=range(len(left)))
        for a in attrs:
            out[a] = pd.NA
        return out
    lft = left[["geometry"]].reset_index(drop=True).copy()
    lft["_i"] = np.arange(len(lft))
    rgt = right[[*attrs, "geometry"]].reset_index(drop=True)
    j = gpd.sjoin_nearest(lft, rgt, how="left", distance_col="_d")
    j = j.sort_values("_d").drop_duplicates("_i").sort_values("_i")
    out = pd.DataFrame({"dist_km": j["_d"].values / 1000.0})
    for a in attrs:
        out[a] = j[a].values
    return out


def count_within(left_xy: np.ndarray, right_xy: np.ndarray, radius_km: float,
                 weights: np.ndarray | None = None) -> np.ndarray:
    """Count (or sum of weights) of right points within radius of each left point."""
    if right_xy is None or len(right_xy) == 0:
        return np.zeros(len(left_xy))
    tree = cKDTree(right_xy)
    idx = tree.query_ball_point(left_xy, r=radius_km * 1000.0)
    if weights is None:
        return np.array([len(i) for i in idx], dtype=float)
    w = np.nan_to_num(np.asarray(weights, dtype=float))
    return np.array([w[i].sum() if i else 0.0 for i in idx])


def neighbours_within(left_xy: np.ndarray, right_xy: np.ndarray, radius_km: float) -> list[list[int]]:
    if right_xy is None or len(right_xy) == 0:
        return [[] for _ in range(len(left_xy))]
    return cKDTree(right_xy).query_ball_point(left_xy, r=radius_km * 1000.0)


def xy(gdf) -> np.ndarray:
    g = gdf.geometry
    if not (g.geom_type == "Point").all():
        g = g.representative_point()
    return np.column_stack([g.x.values, g.y.values])


def contains(left_pts, polys) -> np.ndarray:
    import geopandas as gpd
    if polys is None or len(polys) == 0:
        return np.zeros(len(left_pts), dtype=bool)
    lft = left_pts[["geometry"]].reset_index(drop=True).copy()
    lft["_i"] = np.arange(len(lft))
    j = gpd.sjoin(lft, polys[["geometry"]], how="inner", predicate="within")
    res = np.zeros(len(lft), dtype=bool)
    res[j["_i"].unique()] = True
    return res


def point_attr(left_pts, polys, attr: str) -> np.ndarray:
    import geopandas as gpd
    lft = left_pts[["geometry"]].reset_index(drop=True).copy()
    lft["_i"] = np.arange(len(lft))
    j = gpd.sjoin(lft, polys[[attr, "geometry"]], how="left", predicate="within")
    j = j.drop_duplicates("_i").sort_values("_i")
    return j[attr].values


def length_within(left_pts, lines, radius_km: float) -> np.ndarray:
    """Total line length (km) inside a circle around each point."""
    if lines is None or len(lines) == 0:
        return np.zeros(len(left_pts))
    import geopandas as gpd
    buf = gpd.GeoDataFrame({"_i": np.arange(len(left_pts))},
                           geometry=left_pts.geometry.buffer(radius_km * 1000.0).values, crs=left_pts.crs)
    inter = gpd.overlay(gpd.GeoDataFrame(geometry=lines.geometry.values, crs=lines.crs), buf,
                        how="intersection", keep_geom_type=True)
    s = inter.assign(L=inter.length / 1000.0).groupby("_i")["L"].sum()
    out = np.zeros(len(left_pts))
    out[s.index.values] = s.values
    return out


def latency_ms(dist_km, route_factor=1.4, ms_per_km_rtt=0.01, fixed_ms=1.0):
    return np.asarray(dist_km, dtype=float) * route_factor * ms_per_km_rtt + fixed_ms


def haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))
