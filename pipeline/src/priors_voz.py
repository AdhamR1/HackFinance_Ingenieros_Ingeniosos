"""Expert siting criteria said in public recordings -> monotone constraints for the model.

The model learns from ~100 positive cells, so it can pick up accidents of that small sample. What
developers, brokers, utilities and analysts say in public talks is independent knowledge: "land
without power is worth nothing", "you want the high-voltage lines". Here that knowledge becomes a
direction per variable that the model must respect (a cell closer to a substation can never score
lower because of it).

Input : ELT/dataset/audio_evidence.parquet, the citations of the ELT (speech -> text with
        ElevenLabs Scribe). A citation with target_field = criterion:<name> has value +1 (the
        criterion matters in its natural sense), -1 (the speaker says it does not) or 0 (nuance).
Output: data/processed/priors_voz.csv  one row per constrained variable, with its evidence

A criterion becomes a constraint when at least MIN_SOURCES different recordings support it and
fewer than MAX_AGAINST of the recordings that mention it say the opposite.

    python src/priors_voz.py
    python src/train.py --priors data/processed/priors_voz.csv
"""

import pandas as pd

from cells import ELT_DATASET, PROCESSED

MIN_SOURCES = 3
MAX_AGAINST = 0.20
# criterion -> {model variable: +1 the score may only rise with it, -1 it may only fall}
CRITERIA = {
    "grid_access": {"dist_substation_km": -1, "dist_hv_line_km": -1, "n_substations_20km": 1},
    "hv_transmission": {"dist_400kv_line_km": -1, "substation_voltage_kv": 1},
    "generation_nearby": {
        "gen_capacity_50km_mw": 1,
        "renewable_capacity_50km_mw": 1,
        "dist_power_plant_km": -1,
    },
    "fiber": {"dist_infra_corridor_km": -1},
    "cable_landing": {"dist_cable_landing_km": -1},
    "road_access": {"dist_highway_km": -1, "dist_motorway_junction_km": -1},
    "airport_access": {"dist_airport_km": -1},
    "demand_proximity": {"population_50km": 1},
    "industrial_land": {"industrial_pct": 1},
    "flat_land": {"slope_pct": -1, "terrain_ruggedness": -1},
    "cool_climate": {"free_cooling_hours": 1, "mean_temp_c": -1, "cooling_degree_days": -1},
    "seismic": {"pga_475y_g": -1, "pga475_ign_g": -1},
    "protected_land": {"in_protected_area": -1, "natura2000_pct": -1},
}


def criteria_table(ev: pd.DataFrame) -> pd.DataFrame:
    """Recordings for and against each criterion, and whether it becomes a constraint."""
    c = ev[ev["target_field"].str.startswith("criterion:", na=False)].copy()
    c["criterion"] = c["target_field"].str.split(":", n=1).str[1]
    rows = []
    for name, g in c.groupby("criterion"):
        n_for = g.loc[g["value"] > 0, "source_id"].nunique()
        n_against = g.loc[g["value"] < 0, "source_id"].nunique()
        share = n_against / max(n_for + n_against, 1)
        best = g[g["value"] > 0].sort_values("evidence_confidence", ascending=False).head(1)
        rows.append(
            {
                "criterion": name,
                "n_sources_for": n_for,
                "n_sources_against": n_against,
                "applied": bool(n_for >= MIN_SOURCES and share < MAX_AGAINST and name in CRITERIA),
                "quote": best["quote"].iat[0] if len(best) else "",
                "source": f"{best['source_publisher'].iat[0]}: {best['source_title'].iat[0]}"
                if len(best)
                else "",
                "t_start_s": best["t_start_s"].iat[0] if len(best) else None,
                "audio_url": best["audio_url"].iat[0] if len(best) else "",
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values(["applied", "n_sources_for"], ascending=False).reset_index(drop=True)


def priors(table: pd.DataFrame) -> pd.DataFrame:
    """One row per constrained model variable."""
    rows = [
        {"feature": f, "monotone": sign, **r}
        for r in table[table["applied"]].to_dict("records")
        for f, sign in CRITERIA[r["criterion"]].items()
    ]
    cols = ["feature", "monotone", "criterion", "n_sources_for", "n_sources_against", "quote",
            "source", "t_start_s", "audio_url"]  # fmt: skip
    return pd.DataFrame(rows, columns=cols)


def main():
    path = ELT_DATASET / "audio_evidence.parquet"
    if not path.exists():
        raise SystemExit(f"Falta {path}: ejecuta en ELT/  python -m dclake collect --only speech")
    ev = pd.read_parquet(path)
    table = criteria_table(ev)
    print(f"Criterios citados en {ev['source_id'].nunique()} grabaciones:")
    for r in table.itertuples():
        why = "restricción" if r.applied else f"sin restricción (pide >= {MIN_SOURCES} a favor)"
        if not r.applied and r.n_sources_for >= MIN_SOURCES:
            why = "sin restricción (hay voces en contra)"
        print(f"  {r.criterion:18s} a favor {r.n_sources_for:2d}  en contra {r.n_sources_against}"
              f"  -> {why}")  # fmt: skip
    out = priors(table)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROCESSED / "priors_voz.csv", index=False, encoding="utf-8")
    print(f"\n{len(out)} variables con sentido obligado:")
    for r in out.itertuples():
        print(f"  {r.feature:28s} {'sube' if r.monotone > 0 else 'baja'}  ({r.criterion})")
    print(f"-> {PROCESSED / 'priors_voz.csv'}  (python src/train.py --priors ...)")


if __name__ == "__main__":
    main()
