"""TARGET: which cells host an existing or announced data center.

Why this target (and not 18 hand-made `viabilidad_<bloque>` labels):
  * A data center that exists or has been announced is a REVEALED decision: an investor
    did the due diligence (power, water, permits, seismic, latency) and said "yes".
  * We do NOT have true negatives: a cell without a DC is "unlabeled", not "not viable".
    -> Positive-Unlabeled (PU) learning. Hard "no" comes only from exclusion rules.

Input : data/raw/dc_sites_es.csv  (103 sites from datacentermap.com, 9-Nov-2026, already geocoded;
        `precision` says how exact the point is: district_approx ~1-2 km, municipio, metro = city
        centre)
Output: data/processed/labels_es_3500.parquet
        (site_id, y, y_operational, n_sites, n_buildings, sites)

A few sites fall in coastal cells that the ETL grid drops (< 50 % land). Their location is
approximate anyway, so they are moved to the nearest ETL cell (reported, max MAX_SNAP_CELLS away).

Sites placed at a CITY CENTRE (precision `metro`, operator unknown, and the RELOCATE
list) would teach
"the historic centre is a good place". They are moved to the cell with most industrial land within
RELOCATE_CELLS (~7 km), where city data centers usually are (needs exclusions_es_3500.parquet from
feat_suelo.py, so run labels.py after it).
Tested on 11-Nov-2026 on the 67 sites that are NOT moved: spatial AUC 0.927 -> 0.937, i.e. the gain
is not just "moved to where industrial_pct is high". Dropping these sites instead gave 0.888.
"""

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from cells import PROCESSED, RAW, TAG, cell_index, out_file, read_grid, site_id_from_lonlat

MAX_SNAP_CELLS = 2
RELOCATE_CELLS = 2
RELOCATE = {"Zaragoza - ciudad"}  # municipio rows that are really "somewhere in a big city"


def relocate_city_centres(s: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    suelo = out_file("exclusions")
    if not suelo.exists():
        print(
            f"  falta {suelo.name} (feat_suelo.py): los de centro de ciudad se quedan en el centro"
        )
        return s
    ex = pd.read_parquet(suelo).set_index("site_id")
    g = grid[["site_id", "i", "j"]].assign(
        industrial_pct=lambda d: d.site_id.map(ex.industrial_pct).fillna(0)
    )
    g = g[~g.site_id.map(ex.excluded).fillna(False).astype(bool)]  # never into a forbidden cell
    for k in s.index[(s.precision == "metro") | s.site.isin(RELOCATE)]:
        c = cell_index(pd.Series([s.at[k, "site_id"]])).iloc[0]
        near = g[(g.i - c.i).abs().le(RELOCATE_CELLS) & (g.j - c.j).abs().le(RELOCATE_CELLS)]
        near = near.assign(dist=np.hypot(near.i - c.i, near.j - c.j))
        best = near.sort_values(["industrial_pct", "dist"], ascending=[False, True]).iloc[0]
        if best.industrial_pct > 0 and best.site_id != s.at[k, "site_id"]:
            print(
                f"  centro de ciudad -> zona industrial: {s.at[k, 'site']} "
                f"({best.dist * 3.5:.1f} km, "
                f"{best.industrial_pct:.0f} % industrial)"
            )
            s.at[k, "site_id"] = best.site_id
    return s


def main():
    grid = read_grid()
    s = pd.read_csv(RAW / f"dc_sites_{TAG}.csv").dropna(subset=["lat", "lon"])
    s["site_id"] = site_id_from_lonlat(s["lon"].values, s["lat"].values)
    s = relocate_city_centres(s, grid)

    outside = ~s["site_id"].isin(grid["site_id"])
    if outside.any():
        tree = cKDTree(grid[["i", "j"]].values)
        ij = cell_index(s.loc[outside, "site_id"])[["i", "j"]].values
        dist, idx = tree.query(ij)
        for (k, row), d, n in zip(s[outside].iterrows(), dist, idx):
            new = grid["site_id"].iat[n]
            flag = "" if d <= MAX_SNAP_CELLS else "  <-- LEJOS, revisar coordenadas"
            print(
                f"  movido a la celda más cercana ({d:.1f} celdas): {row['site']} "
                f"{row['site_id']} "
                f"-> {new}{flag}"
            )
            if d <= MAX_SNAP_CELLS:
                s.at[k, "site_id"] = new
        s = s[s["site_id"].isin(grid["site_id"])]

    agg = s.groupby("site_id").agg(
        n_sites=("site", "size"),
        n_buildings=("n_buildings", "sum"),
        y_operational=("status", lambda x: int((x == "operational").any())),
        sites=("site", lambda x: " | ".join(x)),
    )
    lab = grid[["site_id"]].merge(agg, on="site_id", how="left")
    lab["y"] = lab["n_sites"].notna().astype(int)
    lab[["n_sites", "n_buildings", "y_operational"]] = (
        lab[["n_sites", "n_buildings", "y_operational"]].fillna(0).astype(int)
    )
    lab["sites"] = lab["sites"].fillna("")
    lab = lab[["site_id", "y", "y_operational", "n_sites", "n_buildings", "sites"]]

    PROCESSED.mkdir(parents=True, exist_ok=True)
    lab.to_parquet(out_file("labels"), index=False)
    print(
        f"emplazamientos={len(s)}  edificios={s.n_buildings.sum()}  celdas "
        f"positivas={lab.y.sum()} "
        f""
        f"(operativas {lab.y_operational.sum()}) de {len(lab):,} ({lab.y.mean():.2%})"
    )


if __name__ == "__main__":
    main()
