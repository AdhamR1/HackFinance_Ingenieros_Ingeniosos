"""Speech data, offline: quotes are found in transcripts and citations reach the right cells."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dclake import geo, speech
from dclake.collectors.speech import cells_of_claim, evidence_table, usable_claims
from dclake.config import Config


def _transcript() -> dict:
    words, t = [], 0.0

    def say(text, speaker):
        nonlocal t
        for w in text.split():
            words.append(
                {"text": w, "start": t, "end": t + 0.4, "type": "word", "speaker_id": speaker}
            )
            words.append(
                {
                    "text": " ",
                    "start": t + 0.4,
                    "end": t + 0.5,
                    "type": "spacing",
                    "speaker_id": None,
                }
            )
            t += 0.5

    say("Bienvenidos al pleno.", "speaker_0")
    words.append({"text": "(aplausos)", "start": t, "end": t + 1, "type": "audio_event"})
    say("El suelo, si no tiene potencia, no me vale.", "speaker_1")
    say("Se tramitó en nueve meses.", "speaker_0")
    return {"audio_duration_secs": 60.0, "language_code": "spa", "words": words}


def test_locate_quote_gives_the_second_and_the_speaker():
    t = _transcript()
    loc = speech.locate_quote(t, "el suelo si no tiene POTENCIA, no me vale")  # case, commas
    assert loc == {"t_start_s": 1.5, "t_end_s": pytest.approx(5.9), "speaker_id": "speaker_1"}
    assert speech.locate_quote(t, "tramitó en nueve meses")["speaker_id"] == "speaker_0"
    # a paraphrase is not a quote: it must not get a minute
    assert speech.locate_quote(t, "el suelo sin potencia no vale") is None
    assert speech.locate_quote(t, "") is None


def test_audio_stats_and_excerpts():
    t = _transcript()
    st = speech.audio_stats(t)
    assert st["n_speakers"] == 2 and st["n_applause"] == 1
    assert st["turns_per_min"] == pytest.approx(2.0)  # two changes of speaker in one minute
    text = speech.excerpts(t, "potencia", window=2)
    assert text.startswith("[00:0") and "potencia" in text and "Bienvenidos" not in text


def test_cite_rejects_quotes_that_are_not_in_the_transcript(tmp_path):
    import json
    import logging

    cfg = Config({"_root": str(tmp_path), "paths": {"lake_dir": ".cache"}})
    out = speech.transcripts_dir(cfg)
    out.mkdir(parents=True)
    (out / "pleno1.json").write_text(json.dumps(_transcript()), encoding="utf-8")
    speech.audio_dir(cfg).mkdir()
    pd.DataFrame(
        {
            "source_id": ["pleno1", "pleno1", "otra"],
            "quote": [
                "Se tramitó en nueve meses",
                "se tramitó en seis meses",
                "sin transcripción",
            ],
            "country_iso3": "ESP",
            "scope": "country",
            "t_start_s": [None, None, 12.0],  # the third was verified where its transcript is
        }
    ).to_csv(speech.audio_dir(cfg) / "claims.csv", index=False)
    speech.cite(cfg, logging.getLogger("test"))
    ok = speech.load_claims(cfg)
    assert ok["quote"].tolist() == ["Se tramitó en nueve meses", "sin transcripción"]
    assert ok["t_start_s"].tolist() == [6.0, 12.0] and ok["speaker_id"].iat[0] == "speaker_0"
    assert len(speech.load_claims(cfg, verified_only=False)) == 3


def _claims(rows) -> pd.DataFrame:
    base = {
        "country_iso3": "ESP",
        "scope": "point",
        "place_name": "",
        "lat": np.nan,
        "lon": np.nan,
        "radius_km": np.nan,
        "topic": "",
        "target_field": "grid_congestion_flag",
        "value": 1.0,
        "confidence": 0.5,
        "t_start_s": 1.0,
        "t_end_s": 2.0,
        "speaker_id": "speaker_0",
        "quote": "cita",
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def test_usable_claims_asks_two_recordings_for_a_whole_region():
    c = _claims(
        [
            {"source_id": "a", "scope": "admin1", "place_name": "Aragón"},
            {"source_id": "b", "scope": "admin1", "place_name": "Aragón"},
            {"source_id": "a", "scope": "admin1", "place_name": "Galicia"},  # one recording
            {"source_id": "c", "scope": "admin1", "place_name": "Texas", "confidence": 0.8},
            {"source_id": "d", "scope": "point", "place_name": "Zaragoza"},
            {"source_id": "d", "scope": "point", "place_name": "Teruel", "confidence": 0.3},
            {"source_id": "e", "scope": "point", "place_name": "Memphis", "country_iso3": "USA"},
        ]
    )
    got = usable_claims(c, "ESP", {"min_confidence": 0.4})
    assert got["place_name"].tolist() == ["Aragón", "Aragón", "Texas", "Zaragoza"]


def test_cells_of_claim_by_radius_and_by_region(monkeypatch):
    from scipy.spatial import cKDTree

    monkeypatch.setattr(geo, "EQUAL_AREA", "EPSG:3035")
    sites = pd.DataFrame(
        {
            "site_id": ["zgz", "calatorao", "madrid", "wv"],
            "lon": [-0.887, -1.346, -3.703, -3.0],
            "lat": [41.649, 41.523, 40.417, 40.0],
            "admin1": ["Aragón", "Aragón", "Comunidad de Madrid", "West Virginia"],
        }
    )
    xy = geo.xy(geo.points_from_lonlat(sites))
    sites["x"], sites["y"] = xy[:, 0], xy[:, 1]
    tree = cKDTree(xy)
    point = _claims([{"scope": "point", "lat": 41.65, "lon": -0.89, "radius_km": 10}]).iloc[0]
    assert cells_of_claim(point, sites, tree).tolist() == [0]
    wide = _claims([{"scope": "point", "lat": 41.65, "lon": -0.89, "radius_km": 60}]).iloc[0]
    assert sorted(cells_of_claim(wide, sites, tree).tolist()) == [0, 1]
    region = _claims([{"scope": "admin1", "place_name": "aragon"}]).iloc[0]  # no accent
    assert cells_of_claim(region, sites, tree).tolist() == [0, 1]
    short = _claims([{"scope": "admin1", "place_name": "Comunidad"}]).iloc[0]
    assert cells_of_claim(short, sites, tree).tolist() == [2]  # "Comunidad de Madrid"
    virginia = _claims([{"scope": "admin1", "place_name": "Virginia"}]).iloc[0]
    assert cells_of_claim(virginia, sites, tree).tolist() == []  # not West Virginia
    country = _claims([{"scope": "country"}]).iloc[0]
    assert cells_of_claim(country, sites, tree).tolist() == []


def test_evidence_table_numbers_citations_in_order_of_appearance():
    claims = _claims(
        [
            {"source_id": "s1", "t_start_s": 90.0, "quote": "segunda"},
            {"source_id": "s1", "t_start_s": 10.0, "quote": "primera"},
        ]
    )
    sources = pd.DataFrame(
        {
            "source_id": ["s1"],
            "title": ["Pleno"],
            "publisher": ["Ayuntamiento"],
            "date": ["2026-01-13"],
            "language": ["spa"],
            "audio_url": ["https://example.org/a.mp3"],
            "page_url": [""],
        }
    )
    ev = evidence_table(claims, sources, {"s1": "spa"})
    assert ev["evidence_id"].tolist() == ["s1#01", "s1#02"]
    assert ev["quote"].tolist() == ["primera", "segunda"]
    assert ev["source_date"].iat[0] == pd.Timestamp("2026-01-13")
    assert ev["audio_url"].iat[0].endswith("a.mp3") and ev["quote_language"].iat[0] == "spa"


def test_every_citation_in_the_repo_is_verified_and_has_its_recording():
    """claims.csv is what reaches the dataset: no unverified quote, no unknown recording."""
    root = Path(__file__).resolve().parents[1]
    cfg = Config({"_root": str(root), "paths": {"lake_dir": ".cache"}})
    every = speech.load_claims(cfg, verified_only=False)
    if every.empty:
        pytest.skip("no citations yet")
    assert every["t_start_s"].notna().all(), "run: python -m dclake cite"
    assert set(every["source_id"]) <= set(speech.load_sources(cfg)["source_id"])
    assert every["scope"].isin(["point", "admin1", "admin2", "country", "general"]).all()
    pts = every[every["scope"] == "point"]
    assert pts[["lat", "lon"]].notna().all().all()
    assert every["confidence"].between(0, 1).all()
