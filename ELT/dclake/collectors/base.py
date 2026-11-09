"""Collector contract.

A collector downloads one source and stages DataFrames whose columns are field
names from the data dictionary. `assemble` later merges all staged outputs into
the final tables, so a collector never has to know about the others.
"""
from __future__ import annotations

import pandas as pd


class Collector:
    name: str = "base"
    description: str = ""
    requires: list[str] = []                 # environment variables (API keys)
    fields: dict[str, list[str]] = {}        # table -> dictionary fields this collector fills
    source: str = ""
    source_url: str = ""
    license: str = ""
    is_synthetic: bool = False
    confidence: float | None = None
    spatial_resolution_m: float | None = None
    imputation_method: str = "ninguno"
    status: str = "implementado"             # or "pendiente"
    run_by_default: bool = True              # False: only runs when named in --only (slow per-cell fallbacks)

    def __init__(self, lake, cfg):
        self.lake = lake
        self.cfg = cfg
        self.log = lake.log

    # -- helpers --------------------------------------------------------
    def missing_requirements(self) -> list[str]:
        return [k for k in self.requires if not self.cfg.secret(k)]

    def declared_fields(self) -> dict[str, list[str]]:
        return self.fields

    def stage(self, table: str, df: pd.DataFrame, year: int | None = None):
        self.lake.write_stage(self.name, table, df, year)

    def write_lineage(self, overrides: dict | None = None, per_field: dict | None = None):
        base = {"source": self.source, "source_url": self.source_url, "license": self.license,
                "is_synthetic": self.is_synthetic, "imputation_method": self.imputation_method,
                "confidence": self.confidence, "spatial_resolution_m": self.spatial_resolution_m,
                "crs": "EPSG:4326 (lat/lon) / EPSG:3035 (distancias)",
                "pipeline_version": self.cfg["project"]["pipeline_version"]}
        base.update(overrides or {})
        info = {}
        for table, fl in self.declared_fields().items():
            for f in fl:
                info[f"{table}.{f}"] = {**base, **(per_field or {}).get(f, {})}
        self.lake.write_lineage(self.name, info)

    # -- to implement ---------------------------------------------------
    def run(self, sites):
        raise NotImplementedError

    def __call__(self, sites):
        miss = self.missing_requirements()
        if miss:
            self.log.warning("[%s] omitido: faltan variables de entorno %s (ver .env.example)", self.name, miss)
            return False
        self.log.info("[%s] %s", self.name, self.description)
        self.run(sites)
        self.write_lineage()
        return True


class PendingCollector(Collector):
    """Placeholder that documents which fields still need a collector."""
    status = "pendiente"
    reason = ""

    def __call__(self, sites):
        self.log.info("[%s] pendiente: %s", self.name, self.reason)
        return False
