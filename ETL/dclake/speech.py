"""Unstructured audio -> text: public recordings transcribed with ElevenLabs Scribe v2.

Catalogue: ETL/audio/sources.csv, one public recording per row with the URL of its audio.
Transcripts: <cache>/audio/transcripts/<source_id>.json (third-party content: never in git).
ElevenLabs reads the audio from its URL (`source_url`), so nothing is downloaded here.

Citations: ETL/audio/claims.csv holds literal quotes taken from the transcripts. `locate_quote`
finds each quote in the word timestamps, so the minute and the speaker of a citation are computed,
never typed by hand; a quote that is not in the transcript is rejected.

    python -m dclake transcribe [--only id1,id2] [--workers 4]
    python -m dclake excerpts --only id1 [--terms "agua|red"]    # passages to read before citing
    python -m dclake cite                                         # check quotes, fill the minutes
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import pairwise
from pathlib import Path

import pandas as pd

MODEL = "scribe_v2"
REQUEST_TIMEOUT_S = 3600
# Words that mark a passage worth reading (Spanish, English): siting drivers and local response
TERMS = (
    r"megav|\bmw\b|gigav|\bgw\b|kilovolt|\bkv\b|subestaci|substation|nudo|conexi|interconnect"
    r"|capacidad|capacity|red el|grid|transmis|transporte|distribu|potencia|power"
    r"|agua|water|sequ|drought|refriger|cooling|latenc|fibra|fiber|fibre|cable"
    r"|suelo|terreno|land|acre|hect|parcel|zoning|rezon|urban|licen|permis|permit|tramit"
    r"|plazo|meses|months|años|years|moratori|vecin|oposici|opposition|protest|rechaz|resident"
    r"|incentiv|fiscal|tax|impuest|sism|seismic|inunda|flood|riesgo|risk|aeropuert|airport"
    r"|site selection|ubicaci|emplazamiento|criteri|renovable|renewable|precio|price"
)


def audio_dir(cfg) -> Path:
    return cfg.root / "audio"


def transcripts_dir(cfg) -> Path:
    return cfg.root / cfg["paths"]["lake_dir"] / "audio" / "transcripts"


def load_sources(cfg) -> pd.DataFrame:
    df = pd.read_csv(audio_dir(cfg) / "sources.csv", dtype=str).fillna("")
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
    return df


def load_transcript(cfg, source_id: str) -> dict | None:
    p = transcripts_dir(cfg) / f"{source_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _client():
    """ElevenLabs client. The key comes from ELEVENLABS_API_KEY (.env), never from the code."""
    key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("Falta ELEVENLABS_API_KEY en .env (python -m dclake status)")
    from elevenlabs import ElevenLabs

    # the SDK reads the variable when it is imported; .env is loaded later, so pass it on
    return ElevenLabs(api_key=key)


def _error_text(e: Exception) -> str:
    """Short reason of an API error (the SDK puts the response headers first)."""
    body = getattr(e, "body", None)
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("status") or detail
    code = getattr(e, "status_code", None)
    return f"{type(e).__name__} {code or ''}: {str(detail if detail is not None else e)[:300]}"


def _fetch_audio(url: str, dest: Path) -> Path:
    """Download a public audio file to the cache (only when ElevenLabs cannot read its URL)."""
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(
        url, stream=True, timeout=300, headers={"User-Agent": "dclake/podcast"}
    ) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest


def transcribe_one(client, row: dict, dest: Path) -> dict:
    """One recording -> transcript with word timestamps, speakers and audio events."""
    kw = {"language_code": row["language"]} if row.get("language") else {}
    opts = {
        "model_id": MODEL,
        "diarize": True,
        "timestamps_granularity": "word",
        "tag_audio_events": True,
        "request_options": {"timeout_in_seconds": REQUEST_TIMEOUT_S},
        **kw,
    }
    try:
        res = client.speech_to_text.convert(source_url=row["audio_url"], **opts)
    except Exception as e:
        if getattr(e, "status_code", None) in (401, 402, 403, 429):  # key, quota or rate limit
            raise
        # some hosts refuse the fetch from ElevenLabs: send the file ourselves, keep no copy
        tmp = _fetch_audio(row["audio_url"], dest.with_suffix(".audio"))
        try:
            with open(tmp, "rb") as f:
                res = client.speech_to_text.convert(file=f, **opts)
        finally:
            tmp.unlink(missing_ok=True)
    d = res.model_dump() if hasattr(res, "model_dump") else dict(res)
    out = {
        "source_id": row["source_id"],
        "model": MODEL,
        "transcribed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "language_code": d.get("language_code"),
        "language_probability": d.get("language_probability"),
        "audio_duration_secs": d.get("audio_duration_secs"),
        "text": d.get("text") or "",
        "words": [
            {k: w.get(k) for k in ("text", "start", "end", "type", "speaker_id")}
            for w in (d.get("words") or [])
        ],
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    tmp.replace(dest)
    return out


def transcribe_sources(cfg, log, only: set | None = None, workers: int = 4) -> dict:
    """Transcribe the recordings of the catalogue that are not in the cache yet."""
    src = load_sources(cfg)
    if only:
        src = src[src["source_id"].isin(only)]
    out = transcripts_dir(cfg)
    todo = [r for r in src.to_dict("records") if not (out / f"{r['source_id']}.json").exists()]
    budget_h = float((cfg.get("speech") or {}).get("max_hours_per_run", 60))
    hours = sum(r["minutes"] for r in todo) / 60
    log.info(
        "Transcripción: %d grabaciones en el catálogo, %d por hacer (%.1f h de audio)",
        len(src),
        len(todo),
        hours,
    )
    if hours > budget_h:
        raise RuntimeError(
            f"{hours:.1f} h de audio superan speech.max_hours_per_run ({budget_h:.0f} h): "
            f"usa --only o sube el límite en config.yaml"
        )
    done, failed = [], {}
    if not todo:
        return {"done": done, "failed": failed}
    client = _client()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {
            ex.submit(transcribe_one, client, r, out / f"{r['source_id']}.json"): r for r in todo
        }
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                t = fut.result()
            except Exception as e:  # one failing recording must not stop the rest
                failed[r["source_id"]] = _error_text(e)
                log.warning(
                    "  FALLO %s (%s): %s", r["source_id"], r["title"][:50], failed[r["source_id"]]
                )
            else:
                done.append(r["source_id"])
                log.info(
                    "  %s: %.0f min, idioma %s, %d palabras",
                    r["source_id"],
                    (t["audio_duration_secs"] or 0) / 60,
                    t["language_code"],
                    sum(w["type"] == "word" for w in t["words"]),
                )
    log.info("Transcripción: %d hechas, %d fallidas", len(done), len(failed))
    return {"done": done, "failed": failed}


def fold(text: str) -> str:
    """Lower case, no accents, no punctuation: how quotes are compared with the transcript."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w]+", " ", t, flags=re.UNICODE).strip()


def spoken_words(transcript: dict) -> list[dict]:
    """Spoken words (no spacing, no audio events) with their folded text."""
    out = []
    for w in transcript.get("words") or []:
        if w.get("type") != "word":
            continue
        for tok in fold(w.get("text") or "").split():
            out.append(
                {
                    "tok": tok,
                    "start": w.get("start"),
                    "end": w.get("end"),
                    "speaker": w.get("speaker_id"),
                    "text": w.get("text"),
                }
            )
    return out


def locate_quote(transcript: dict, quote: str, words: list[dict] | None = None) -> dict | None:
    """Where a literal quote is said: start, end (seconds) and speaker. None if it is not there."""
    q = fold(quote).split()
    words = spoken_words(transcript) if words is None else words
    if not q or len(q) > len(words):
        return None
    toks = [w["tok"] for w in words]
    first = q[0]
    for i in range(len(toks) - len(q) + 1):
        if toks[i] == first and toks[i : i + len(q)] == q:
            seg = words[i : i + len(q)]
            speakers = [w["speaker"] for w in seg if w["speaker"]]
            return {
                "t_start_s": float(seg[0]["start"] or 0.0),
                "t_end_s": float(seg[-1]["end"] or 0.0),
                "speaker_id": max(set(speakers), key=speakers.count) if speakers else None,
            }
    return None


CLAIM_COLUMNS = [
    "source_id",
    "quote",
    "country_iso3",
    "scope",  # point | admin2 | admin1 | country | general
    "place_name",
    "lat",
    "lon",
    "radius_km",
    "topic",
    "target_field",
    "value",
    "confidence",
    "t_start_s",  # computed by `cite`: where the quote is said
    "t_end_s",
    "speaker_id",
]


def load_claims(cfg, verified_only: bool = True) -> pd.DataFrame:
    """Curated citations (ETL/audio/claims.csv). Verified = the quote was found in its
    transcript, so it has a minute and a speaker."""
    p = audio_dir(cfg) / "claims.csv"
    if not p.exists():
        return pd.DataFrame(columns=CLAIM_COLUMNS)
    df = pd.read_csv(p, dtype=str).reindex(columns=CLAIM_COLUMNS)
    numeric = ("lat", "lon", "radius_km", "value", "confidence", "t_start_s", "t_end_s")
    for c in CLAIM_COLUMNS:
        if c in numeric:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:  # text: empty cells are "", also in a column that is missing from the file
            df[c] = df[c].astype(object).where(df[c].notna(), "").astype(str).str.strip()
    return df[df["t_start_s"].notna()].reset_index(drop=True) if verified_only else df


def cite(cfg, log) -> pd.DataFrame:
    """Find every quote of claims.csv in its transcript and write its minute and speaker back.

    A quote that is not literally in the transcript loses its minute, so it never reaches the
    dataset: this is the guard against misquoting.
    """
    p = audio_dir(cfg) / "claims.csv"
    df = load_claims(cfg, verified_only=False)
    cache: dict[str, tuple] = {}
    found = missing = no_transcript = 0
    for i, r in df.iterrows():
        sid = r["source_id"]
        if sid not in cache:
            t = load_transcript(cfg, sid)
            cache[sid] = (t, spoken_words(t) if t else None)
        t, words = cache[sid]
        if t is None:  # transcript not in this machine's cache: keep what is already verified
            no_transcript += 1
            continue
        loc = locate_quote(t, r["quote"], words)
        if loc is None:
            missing += 1
            log.warning("  cita no encontrada en %s: «%s»", sid, r["quote"][:90])
            df.loc[i, ["t_start_s", "t_end_s"]] = [float("nan"), float("nan")]
            df.loc[i, "speaker_id"] = ""
        else:
            found += 1
            df.loc[i, ["t_start_s", "t_end_s"]] = [
                round(loc["t_start_s"], 2),
                round(loc["t_end_s"], 2),
            ]
            df.loc[i, "speaker_id"] = loc["speaker_id"] or ""
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
    log.info(
        "Citas: %d verificadas, %d no encontradas, %d sin transcripción en caché (de %d)",
        found,
        missing,
        no_transcript,
        len(df),
    )
    return df


def audio_stats(transcript: dict) -> dict:
    """Conversation metrics that need no reading: speakers, turns and audience reactions."""
    words = [w for w in transcript.get("words") or [] if w.get("type") == "word"]
    events = [
        fold(w.get("text") or "")
        for w in transcript.get("words") or []
        if w.get("type") == "audio_event"
    ]
    turns = sum(a.get("speaker_id") != b.get("speaker_id") for a, b in pairwise(words))
    minutes = max(float(transcript.get("audio_duration_secs") or 0) / 60, 1e-9)
    return {
        "n_speakers": len({w.get("speaker_id") for w in words if w.get("speaker_id")}),
        "turns_per_min": turns / minutes,
        "n_applause": sum("applau" in e or "aplaus" in e for e in events),
        "n_laughter": sum("laugh" in e or "risa" in e for e in events),
        "words_per_min": len(words) / minutes,
    }


def excerpts(transcript: dict, terms: str = TERMS, window: int = 45, max_words: int = 1500) -> str:
    """Passages around the terms, with [mm:ss speaker] marks: what to read before citing."""
    words = [w for w in transcript.get("words") or [] if w.get("type") == "word"]
    rx = re.compile(terms, re.I)
    hits = [i for i, w in enumerate(words) if rx.search(fold(w.get("text") or ""))]
    spans: list[list[int]] = []
    for i in hits:
        a, b = max(0, i - window), min(len(words), i + window)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = b
        else:
            spans.append([a, b])
    # densest passages first when the transcript is long, then back in time order
    spans.sort(key=lambda s: -sum(s[0] <= i < s[1] for i in hits) / max(s[1] - s[0], 1))
    keep, total = [], 0
    for a, b in spans:
        if total + (b - a) > max_words:
            b = a + max(0, max_words - total)
        if b > a:
            keep.append((a, b))
            total += b - a
        if total >= max_words:
            break
    parts = []
    for a, b in sorted(keep):
        t = float(words[a].get("start") or 0)
        mark = f"[{int(t // 60):02d}:{int(t % 60):02d} {words[a].get('speaker_id') or '?'}]"
        parts.append(mark + " " + " ".join((w.get("text") or "").strip() for w in words[a:b]))
    return "\n".join(parts)
