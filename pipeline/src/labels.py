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

A few sites fall in coastal cells that the ELT grid drops (< 50 % land). Their location is
approximate anyway, so they are moved to the nearest ELT cell (reported, max MAX_SNAP_CELLS away).
"""

import pandas as pd
from scipy.spatial import cKDTree

from cells import PROCESSED, RAW, cell_index, read_grid, site_id_from_lonlat

MAX_SNAP_CELLS = 2


def main():
    grid = read_grid()
    s = pd.read_csv(RAW / "dc_sites_es.csv").dropna(subset=["lat", "lon"])
    s["site_id"] = site_id_from_lonlat(s["lon"].values, s["lat"].values)

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
    lab.to_parquet(PROCESSED / "labels_es_3500.parquet", index=False)
    print(
        f"emplazamientos={len(s)}  edificios={s.n_buildings.sum()}  celdas "
        f"positivas={lab.y.sum()} "
        f""
        f"(operativas {lab.y_operational.sum()}) de {len(lab):,} ({lab.y.mean():.2%})"
    )


if __name__ == "__main__":
    main()
