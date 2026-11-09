"""FEATURES: one row per cell, built from the ELT dataset (ELT/dataset/, Spain only).

  sites_static  -> used as is (one row per cell)
  sites_yearly  -> averaged over the years available (one row per cell)

Kept: numeric columns with data. Dropped, and printed so everyone sees it:
  * LEAKAGE: columns that tell the model where the data centers already are. With them the
    score looks great and means nothing. See LEAKAGE below and the reason for each one.
  * empty columns (the ELT has not filled them yet) and constant columns (country-level values).

Output: data/processed/features_es_3500.parquet  (site_id + numeric columns)
When the ELT gets new columns (power grid, flood, seismic...), just run this again.
"""
import pandas as pd

from cells import PROCESSED, read_elt

# column -> why it is not allowed as a feature
LEAKAGE = {
    # the target itself, or distances / counts of data centers
    "is_datacenter": "es la target",
    "sample_type": "marca las celdas con data center",
    "dist_existing_dc_km": "distancia a data centers",
    "n_existing_dc_50km": "número de data centers cercanos",
    "dc_capacity_50km_mw": "capacidad de data centers cercanos",
    "dc_status": "estado del data center", "dc_cancelled_flag": "data center cancelado",
    "capacity_mw": "capacidad del data center", "operator_type": "operador del data center",
    "year_commissioned": "año del data center",
    # PeeringDB facilities ARE data centers (colocation); IXPs live inside them
    "dist_ixp_km": "los IXP están dentro de data centers",
    "n_ixp_100km": "los IXP están dentro de data centers",
    "n_networks_at_ixp": "los IXP están dentro de data centers",
    "n_colo_facilities_100km": "las colocation son data centers",
    "n_networks_100km": "redes presentes en data centers cercanos",
    "n_carriers_nearest_colo": "operadores del data center más cercano",
    # pure geography: distance to fixed cities = latitude/longitude in disguise
    "lat": "coordenada", "lon": "coordenada", "h3_cell_r7": "identificador de celda",
    "dist_major_hub_km": "distancia a Madrid (coordenada encubierta)",
    "latency_to_hub_ms": "distancia a Madrid (coordenada encubierta)",
    "latency_frankfurt_ms": "distancia a un punto fijo (coordenada encubierta)",
    "latency_ashburn_ms": "distancia a un punto fijo (coordenada encubierta)",
    "latency_singapore_ms": "distancia a un punto fijo (coordenada encubierta)",
    "latency_tokyo_ms": "distancia a un punto fijo (coordenada encubierta)",
    # grid artefacts: only say whether the cell is cut by the coast or the border
    "area_ha": "artefacto de la rejilla", "parcel_compactness": "artefacto de la rejilla",
    # outputs of a model, not inputs
    "viability_score": "es una salida", "capex_per_mw_usd": "es una salida",
    "foundation_overcost_pct": "es una salida", "opex_per_mw_year_usd": "es una salida",
    "time_to_power_months": "es una salida",
}


def numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s) or pd.api.types.is_numeric_dtype(s):
            out[c] = pd.to_numeric(s, errors="coerce").astype("float64")
    return pd.DataFrame(out, index=df.index)


def main():
    static = read_elt("sites_static").set_index("site_id")
    yearly = read_elt("sites_yearly")
    yearly = numeric(yearly.drop(columns=["year"]).set_index("site_id")).groupby(level=0).mean()

    feats = numeric(static).join(yearly, how="left")
    leak = [c for c in feats.columns if c in LEAKAGE]
    feats = feats.drop(columns=leak)
    empty = [c for c in feats.columns if feats[c].isna().all()]
    feats = feats.drop(columns=empty)
    constant = [c for c in feats.columns if feats[c].nunique(dropna=True) <= 1]
    feats = feats.drop(columns=constant)

    print(f"Quitadas por fuga de la target ({len(leak)}):")
    for c in leak:
        print(f"  - {c}: {LEAKAGE[c]}")
    print(f"Quitadas por vacías ({len(empty)}) y por constantes ({len(constant)}): {', '.join(constant)}")
    print(f"\nVariables que entran al modelo ({feats.shape[1]}), con su cobertura:")
    print(feats.notna().mean().mul(100).round(0).astype(int).astype(str).add(" %").to_string())

    PROCESSED.mkdir(parents=True, exist_ok=True)
    feats.reset_index().to_parquet(PROCESSED / "features_es_3500.parquet", index=False)
    print(f"\n-> {PROCESSED / 'features_es_3500.parquet'}  ({len(feats):,} celdas)")


if __name__ == "__main__":
    main()
