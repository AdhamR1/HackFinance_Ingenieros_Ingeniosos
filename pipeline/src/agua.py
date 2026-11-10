"""WATER features per cell from WRI Aqueduct 4.0 (water risk per river sub-basin).

A data center cooled with water evaporates millions of litres a year: where water is scarce it
competes with farms and towns, gets restricted in droughts and meets local opposition.

Source: WRI Aqueduct 4.0 (2023), CC BY 4.0, https://www.wri.org/data/aqueduct-global-maps-40-data
Download once (262 MB) into data/cache/aqueduct/ and unzip:
  https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip
Each cell takes the values of the sub-basin that contains its centre. Scores go from 0 (low risk)
to 5 (extremely high); Aqueduct's "no data / arid and low water use" codes become NaN.
(Groundwater decline is left out: Aqueduct has almost no data for Spain.)

NOT a model input (the file is not called feat_*): tested on 10-Nov-2026, spatial AUC only went
0.893 -> 0.899 and the gain came from basin variability, i.e. "which basin" (geography), not from
water scarcity. Used for the "Agua" indicator and warnings in the web, like the finance layer.

Output: data/processed/agua_es_3500.parquet
  site_id, water_stress, water_depletion, drought_risk,
  interannual_variability, seasonal_variability, water_stress_2030, water_stress_2050
"""
import numpy as np
import pandas as pd
import pyogrio
import shapely

from cells import PIPELINE, PROCESSED, read_grid

GDB = (PIPELINE / "data" / "cache" / "aqueduct" / "Aqueduct40_waterrisk_download_Y2023M07D05"
       / "GDB" / "Aq40_Y2023D07M05.gdb")
BBOX = (-18.5, 27.5, 4.5, 44.0)          # Spain incl. Canaries (lon/lat)
BASELINE = {"bws_score": "water_stress", "bwd_score": "water_depletion",
            "drr_score": "drought_risk", "iav_score": "interannual_variability", "sev_score": "seasonal_variability"}
FUTURE = {"bau30_ws_x_s": "water_stress_2030", "bau50_ws_x_s": "water_stress_2050"}   # business as usual


def by_cell(points, layer, cols):
    """Values of the sub-basin polygon that contains each point (NaN if none / no data)."""
    meta, _, geom, fields = pyogrio.raw.read(GDB, layer=layer, columns=list(cols), bbox=BBOX)
    geoms = shapely.from_wkb(geom)
    attrs = pd.DataFrame(dict(zip(meta["fields"], fields)))[list(cols)].to_numpy(dtype=float)
    pt_ix, poly_ix = shapely.STRtree(geoms).query(points, predicate="within")
    first = pd.Series(poly_ix, index=pt_ix).groupby(level=0).first()      # basins do not overlap
    out = np.full((len(points), len(cols)), np.nan)
    out[first.index] = attrs[first.values]
    out = pd.DataFrame(out, columns=list(cols))
    return out.where(out >= 0)                                             # -1 / -9999 = no data


def main():
    grid = read_grid()
    points = shapely.points(grid.lon.values, grid.lat.values)
    base = by_cell(points, "baseline_annual", BASELINE).rename(columns=BASELINE)
    fut = by_cell(points, "future_annual", FUTURE).rename(columns=FUTURE)
    out = pd.concat([grid[["site_id"]].reset_index(drop=True), base, fut], axis=1).round(2)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROCESSED / "agua_es_3500.parquet", index=False)
    print(out.describe().T[["count", "mean", "min", "max"]].round(2).to_string())
    print(f"-> {PROCESSED / 'agua_es_3500.parquet'}")


if __name__ == "__main__":
    main()
