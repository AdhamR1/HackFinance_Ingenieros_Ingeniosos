"""Expert criteria from the audio citations -> constraints of the model (no downloads)."""

import pandas as pd
import priors_voz
import pytest


def _evidence(rows) -> pd.DataFrame:
    base = {
        "evidence_confidence": 0.6,
        "quote": "cita",
        "source_publisher": "Programa",
        "source_title": "Episodio",
        "t_start_s": 10.0,
        "audio_url": "https://example.org/a.mp3",
    }
    return pd.DataFrame(
        [{**base, "source_id": s, "target_field": t, "value": v} for s, t, v in rows]
    )


def test_a_criterion_needs_three_recordings_and_no_real_dissent():
    ev = _evidence(
        [
            ("a", "criterion:grid_access", 1),
            ("a", "criterion:grid_access", 1),  # the same recording twice counts once
            ("b", "criterion:grid_access", 1),
            ("c", "criterion:grid_access", 1),
            ("c", "criterion:grid_access", 0),  # a nuance is neither for nor against
            ("a", "criterion:airport_access", 1),
            ("b", "criterion:airport_access", 1),
            ("a", "criterion:demand_proximity", 1),
            ("b", "criterion:demand_proximity", 1),
            ("c", "criterion:demand_proximity", 1),
            ("d", "criterion:demand_proximity", -1),  # 1 of 4 against: no constraint
            ("a", "moratorium_flag", 1),  # not a criterion
        ]
    )
    table = priors_voz.criteria_table(ev).set_index("criterion")
    assert table.loc["grid_access", ["n_sources_for", "n_sources_against"]].tolist() == [3, 0]
    assert table["applied"].to_dict() == {
        "grid_access": True,
        "airport_access": False,
        "demand_proximity": False,
    }
    pri = priors_voz.priors(table.reset_index())
    assert dict(zip(pri["feature"], pri["monotone"])) == priors_voz.CRITERIA["grid_access"]
    assert pri["quote"].eq("cita").all() and pri["audio_url"].str.startswith("https").all()


def test_monotone_params_follow_the_model_columns(tmp_path):
    pytest.importorskip("lightgbm")
    pytest.importorskip("shap")
    import train

    path = tmp_path / "priors.csv"
    pd.DataFrame(
        {
            "feature": ["dist_substation_km", "industrial_pct", "not_in_model"],
            "monotone": [-1, 1, 1],
        }
    ).to_csv(path, index=False)
    got = train.monotone_params(path, ["slope_pct", "industrial_pct", "dist_substation_km"])
    assert got["monotone_constraints"] == [0, 1, -1]
    assert train.monotone_params(None, ["slope_pct"]) == {}
    assert train.monotone_params(path, ["slope_pct"]) == {}  # nothing to constrain
