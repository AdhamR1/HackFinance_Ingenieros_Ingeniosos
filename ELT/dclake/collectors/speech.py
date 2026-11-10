"""Unstructured data: what is said in public recordings -> citations and regulation fields.

Input: ELT/audio/claims.csv, literal quotes taken from transcripts of public recordings
(ElevenLabs Scribe v2, see dclake/speech.py). Only quotes found in their transcript are used.

Output
  audio_evidence   one row per citation (quote, second, speaker, link): every country and the
                   general siting criteria, so the file is the same whatever the country run
  sites_yearly     moratorium_flag, local_opposition_index      (year of the recording)
  sites_static     permitting_months, grid_congestion_flag, grid_connection_wait_months,
                   water_restriction_flag, dc_tax_incentive_flag
  country_context  dc_pipeline_mw, dc_market_size_mw            (figures stated for the country)

A citation reaches the cells of its place: a radius around a point, or a whole province or
region. Cells without a citation stay null: no evidence is not the same as "no opposition".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import geo, speech
from .base import Collector

# field -> (table, how citations that reach the same cell are combined)
CELL_FIELDS = {
    "moratorium_flag": ("sites_yearly", "max"),
    "local_opposition_index": ("sites_yearly", "max"),
    "permitting_months": ("sites_static", "median"),
    "grid_congestion_flag": ("sites_static", "max"),
    "grid_connection_wait_months": ("sites_static", "median"),
    "water_restriction_flag": ("sites_static", "max"),
    "dc_tax_incentive_flag": ("sites_static", "max"),
}
COUNTRY_FIELDS = ("dc_pipeline_mw", "dc_market_size_mw")
EVIDENCE_FIELDS = [
    "evidence_id",
    "source_id",
    "country_iso3",
    "place_name",
    "lat",
    "lon",
    "topic",
    "target_field",
    "value",
    "quote",
    "quote_language",
    "t_start_s",
    "t_end_s",
    "speaker_id",
    "source_title",
    "source_publisher",
    "source_date",
    "audio_url",
    "page_url",
    "extraction_method",
    "evidence_confidence",
]
METHOD = "lectura por LLM (Claude) de la transcripción; cita literal verificada"


def evidence_table(claims: pd.DataFrame, sources: pd.DataFrame, languages: dict) -> pd.DataFrame:
    """Citations joined with their recording, one id per citation in order of appearance."""
    if claims.empty:
        return pd.DataFrame(columns=EVIDENCE_FIELDS)
    c = claims.sort_values(["source_id", "t_start_s"]).copy()
    c["evidence_id"] = (
        c["source_id"] + "#" + (c.groupby("source_id").cumcount() + 1).map("{:02d}".format)
    )
    s = sources.set_index("source_id")
    c["source_title"] = c["source_id"].map(s["title"])
    c["source_publisher"] = c["source_id"].map(s["publisher"])
    c["source_date"] = pd.to_datetime(c["source_id"].map(s["date"]), errors="coerce")
    c["audio_url"] = c["source_id"].map(s["audio_url"])
    c["page_url"] = c["source_id"].map(s["page_url"])
    c["quote_language"] = c["source_id"].map(languages).fillna(c["source_id"].map(s["language"]))
    c["extraction_method"] = METHOD
    c["evidence_confidence"] = c["confidence"]
    return c[EVIDENCE_FIELDS].reset_index(drop=True)


def cells_of_claim(row, sites: pd.DataFrame, tree) -> np.ndarray:
    """Positions (in `sites`) of the cells a citation applies to."""
    scope = row["scope"]
    if scope in ("admin1", "admin2") and scope in sites:
        want = speech.fold(row["place_name"])
        names = sites[scope].fillna("").map(speech.fold)
        # "Cataluña" matches "Cataluña/Catalunya" and "Aichi" matches "Aichi Prefecture", but
        # "Virginia" must not match "West Virginia"
        hit = (names == want) | names.str.startswith(want + " ")
        return np.flatnonzero(hit.to_numpy() & bool(want))
    if scope == "point" and np.isfinite(row["lat"]) and np.isfinite(row["lon"]):
        p = geo.xy(
            geo.points_from_lonlat(pd.DataFrame({"lon": [row["lon"]], "lat": [row["lat"]]}))
        )
        r_km = row["radius_km"] if np.isfinite(row["radius_km"]) else 15.0
        return np.asarray(tree.query_ball_point(p[0], r=r_km * 1000.0), dtype=int)
    return np.empty(0, dtype=int)


def usable_claims(claims: pd.DataFrame, iso: str, rules: dict) -> pd.DataFrame:
    """Citations of one country that may fill fields (all of them are kept as evidence).

    A citation needs a minimum confidence. One that covers a whole region (province, state)
    also needs a second recording saying the same about that place, or to be very clear.
    """
    min_conf = float(rules.get("min_confidence", 0.4))
    need = int(rules.get("min_sources_region", 2))
    solo = float(rules.get("solo_confidence", 0.7))
    c = claims[(claims["country_iso3"] == iso) & (claims["confidence"].fillna(0) >= min_conf)]
    regional = c["scope"].isin(["admin1", "admin2"])
    n_src = c.groupby(["scope", "place_name", "target_field"])["source_id"].transform("nunique")
    return c[~regional | (n_src >= need) | (c["confidence"] >= solo)]


class SpeechCollector(Collector):
    name = "speech"
    description = "Citas de grabaciones públicas (ElevenLabs Scribe): evidencia y regulación"
    source = "Grabaciones públicas (ELT/audio/sources.csv) transcritas con ElevenLabs Scribe v2"
    source_url = "https://elevenlabs.io/docs/overview/capabilities/speech-to-text"
    license = (
        "Citas breves con atribución; el audio y la transcripción completa no se redistribuyen"
    )
    confidence = 0.5
    imputation_method = "lectura por LLM de citas literales"
    fields = {
        "audio_evidence": [f for f in EVIDENCE_FIELDS if f != "evidence_id"],
        "sites_yearly": [f for f, (t, _) in CELL_FIELDS.items() if t == "sites_yearly"],
        "sites_static": [f for f, (t, _) in CELL_FIELDS.items() if t == "sites_static"],
        "country_context": list(COUNTRY_FIELDS),
    }

    def run(self, sites):
        from scipy.spatial import cKDTree

        for old in self.lake.stage_dir(self.name).glob("*.parquet"):
            old.unlink()  # a citation that is withdrawn must not survive in the staging
        claims = speech.load_claims(self.cfg)
        src = speech.load_sources(self.cfg)
        claims = claims[claims["source_id"].isin(src["source_id"])]
        langs = {}
        for sid in claims["source_id"].unique():
            t = speech.load_transcript(self.cfg, sid)
            if t and t.get("language_code"):
                langs[sid] = t["language_code"]
        ev = evidence_table(claims, src, langs)
        self.stage("audio_evidence", ev)
        iso = self.cfg.iso
        mine = usable_claims(claims, iso, self.cfg.get("speech") or {})
        self.log.info(
            "  %d citas verificadas (%d de %s) de %d grabaciones",
            len(claims),
            len(mine),
            iso,
            claims["source_id"].nunique(),
        )
        p = self.cfg["period"]
        y0, y1 = pd.Timestamp(p["start"]).year, pd.Timestamp(p["end"]).year
        year_of = pd.to_datetime(
            mine["source_id"].map(src.set_index("source_id")["date"]), errors="coerce"
        ).dt.year
        tree = cKDTree(np.column_stack([sites["x"].to_numpy(float), sites["y"].to_numpy(float)]))
        long = []  # (cell position, field, year, value)
        for (_, r), yr in zip(mine.iterrows(), year_of):
            f = r["target_field"]
            if f not in CELL_FIELDS or not np.isfinite(r["value"]):
                continue
            pos = cells_of_claim(r, sites, tree)
            # the yearly tables end with the period: a later recording counts for its last year
            year = int(min(max(yr if np.isfinite(yr) else y1, y0), y1))
            long += [(i, f, year, float(r["value"])) for i in pos]
        self.n_cells = {}
        if long:
            d = pd.DataFrame(long, columns=["pos", "field", "year", "value"])
            d["site_id"] = sites["site_id"].to_numpy()[d["pos"].to_numpy()]
            for table in ("sites_static", "sites_yearly"):
                keys = ["site_id"] + (["year"] if table == "sites_yearly" else [])
                out = None
                for f, (t, how) in CELL_FIELDS.items():
                    sub = d[d["field"] == f]
                    if t != table or sub.empty:
                        continue
                    col = sub.groupby(keys)["value"].agg(how).rename(f).reset_index()
                    self.n_cells[f] = col["site_id"].nunique()
                    out = col if out is None else out.merge(col, on=keys, how="outer")
                if out is not None:
                    self.stage(table, out)
        # country figures: what the recordings state for the whole country, by year
        cc = mine[mine["target_field"].isin(COUNTRY_FIELDS) & (mine["scope"] == "country")].copy()
        if len(cc):
            cc["year"] = year_of[cc.index].clip(y0, y1).astype(int)
            wide = cc.pivot_table(
                index="year", columns="target_field", values="value", aggfunc="median"
            )
            wide = wide.reset_index()
            wide.insert(0, "country_iso3", iso)
            self.stage("country_context", wide)
        if self.n_cells:
            self.log.info("  celdas con dato: %s", self.n_cells)

    def write_lineage(self, **kw):
        note = (
            "Dato no estructurado: citas literales de grabaciones públicas (audio a texto con "
            "ElevenLabs Scribe v2), leídas por Claude y verificadas contra la transcripción; "
            "evidencia en audio_evidence. Solo las celdas del lugar citado; el resto queda nulo"
        )
        per = {f: {"notes": note} for f in list(CELL_FIELDS) + list(COUNTRY_FIELDS)}
        per["local_opposition_index"] = {
            "notes": note + ". 0 = apoyo o sin oposición declarada, 0,5 = preocupación vecinal o "
            "política, 1 = oposición organizada, recurso o rechazo; máximo de las citas del lugar"
        }
        per["moratorium_flag"] = {
            "notes": note + ". 1 = moratoria o restricción aprobada o en trámite en ese lugar; el "
            "año es el de la grabación, acotado al último año del periodo"
        }
        super().write_lineage(per_field=per)
