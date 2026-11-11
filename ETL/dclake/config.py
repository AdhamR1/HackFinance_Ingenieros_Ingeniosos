"""Load config.yaml and secrets from .env / environment variables."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # optional
    load_dotenv = None


class Config(dict):
    """dict with attribute access and resolved paths."""

    def __getattr__(self, k):
        try:
            v = self[k]
        except KeyError as e:
            raise AttributeError(k) from e
        return Config(v) if isinstance(v, dict) and not isinstance(v, Config) else v

    @property
    def root(self) -> Path:
        return Path(self["_root"])

    @property
    def iso(self) -> str:
        return self["project"]["country_iso3"]

    @property
    def lake(self) -> Path:
        """Cache of one country (downloads and intermediates): <lake_dir>/<ISO3>."""
        return self.root / self["paths"]["lake_dir"] / self.iso

    @property
    def dataset(self) -> Path:
        return self.root / self["paths"].get("dataset_dir", "dataset")

    @property
    def dictionary_path(self) -> Path:
        return self.root / self["paths"]["dictionary"]

    def secret(self, name: str) -> str | None:
        v = os.environ.get(name)
        return v.strip() if v and v.strip() else None

    @property
    def period_tag(self) -> str:
        """Short tag of the period, used in cache file names (e.g. 20250101_20251231)."""
        p = self["period"]
        return f"{str(p['start']).replace('-', '')}_{str(p['end']).replace('-', '')}"


# Environment variables (or .env) that override config.yaml without editing it.
# Precedence: explicit overrides (CLI, demo) > environment > config.yaml
ENV_OVERRIDES = {
    "DCLAKE_COUNTRY": "project.country_iso3",  # country of the run (its profile is in config.yaml)
    "DCLAKE_LAKE_DIR": "paths.lake_dir",  # cache of downloads and intermediates
    "DCLAKE_DATASET_DIR": "paths.dataset_dir",
    "DCLAKE_START": "period.start",
    "DCLAKE_END": "period.end",
    "DCLAKE_N_CELLS": "sampling.n_cells",
    "DCLAKE_OSM_LAYERS": "osm.layers",  # only these OpenStreetMap layers (comma separated)
}


# ELT/config.yaml, located from the package so the CLI works from any working directory
# (python -m dclake from ELT/, or python -m ELT.dclake from the repo root).
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Config:
    path = Path(path).resolve() if path else DEFAULT_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"No se encuentra el archivo de configuración: {path}")
    if load_dotenv is not None:
        load_dotenv(path.parent / ".env")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["_root"] = str(path.parent)
    merged = {}
    for env, key in ENV_OVERRIDES.items():
        v = os.environ.get(env, "").strip()
        if v:
            merged[key] = int(v) if key == "sampling.n_cells" and v.isdigit() else v
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})
    for k, v in merged.items():
        sec, _, key = k.partition(".")
        data.setdefault(sec, {})[key] = v
    apply_country_profile(data, explicit=set(merged))
    return Config(data)


def apply_country_profile(data: dict, explicit=()) -> None:
    """Overlay country_profiles[<country_iso3>] on project, bboxes, sampling.focus_regions and
    period.

    A period given on the command line or in the environment (explicit) wins over the profile's.
    """
    iso = str(data["project"]["country_iso3"]).upper()
    data["project"]["country_iso3"] = iso
    profiles = data.get("country_profiles") or {}
    if profiles and iso not in profiles:
        raise ValueError(
            f"No hay perfil para {iso} en config.yaml (country_profiles: {', '.join(profiles)})"
        )
    for k, v in (profiles.get(iso) or {}).items():
        if k == "bboxes":
            data["bboxes"] = v
        elif k == "focus_regions":
            data.setdefault("sampling", {})["focus_regions"] = v
        elif k == "period":
            for pk, pv in v.items():
                if f"period.{pk}" not in explicit:
                    data.setdefault("period", {})[pk] = pv
        else:
            data["project"][k] = v
