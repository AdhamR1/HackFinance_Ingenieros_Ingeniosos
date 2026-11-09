"""Read the data dictionary (xlsx) and turn it into table schemas.

The dictionary is the single source of truth: every field it lists becomes a
column of the right table, even if no collector fills it yet (it stays null and
shows up in the coverage report).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

# Columns of field_lineage (block "15 Control y linaje" + bookkeeping)
LINEAGE_EXTRA = ["table", "field", "collector", "coverage_pct", "n_rows", "notes"]


@dataclass
class TableSpec:
    name: str
    keys: list[str]
    fields: dict[str, str]                      # field -> dictionary type
    meta: dict[str, dict] = field(default_factory=dict)  # field -> dictionary row
    partition_by_year: bool = False

    @property
    def columns(self) -> list[str]:
        cols = list(self.keys)
        cols += [f for f in self.fields if f not in cols]
        return cols


PANDAS_DTYPES = {
    "float": "float64",
    "int": "Int64",
    "bool": "boolean",
    "string": "string",
    "category": "string",
    "date": "datetime64[ns]",
    "datetime": "datetime64[ns]",
    "array": "object",
}


@lru_cache(maxsize=4)
def _read(path: str):
    dic = pd.read_excel(path, sheet_name="Diccionario")
    daily = pd.read_excel(path, sheet_name="Variables diarias")
    return dic, daily


@lru_cache(maxsize=4)
def _read_weekly(path: str) -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name="Variables semanales").fillna("")
    except ValueError:  # older dictionary without the weekly sheet
        return pd.DataFrame(columns=["Tabla", "Campo", "Tipo", "Desde (campo diario)", "Agregación"])


def load_schemas(dictionary_path: str | Path) -> dict[str, TableSpec]:
    dic, daily = _read(str(dictionary_path))
    dic = dic.fillna("")

    def spec(name, keys, rows, year_part=False):
        fields = {}
        meta = {}
        for _, r in rows.iterrows():
            fields[r["Campo"]] = r["Tipo"]
            meta[r["Campo"]] = r.to_dict()
        for k in keys:  # keys not in the dictionary (year, date)
            fields.setdefault(k, {"year": "int", "date": "date"}.get(k, "string"))
        return TableSpec(name, keys, fields, meta, year_part)

    sites = dic[dic["Tabla"] == "sites"]
    specs = {
        "sites_static": spec("sites_static", ["site_id"], sites[sites["Temporalidad"] == "Estático"]),
        "sites_yearly": spec("sites_yearly", ["site_id", "year"], sites[sites["Temporalidad"] == "Anual"]),
        "country_context": spec("country_context", ["country_iso3", "year"], dic[dic["Tabla"] == "country_context"]),
        "stations": spec("stations", ["station_id"], dic[dic["Tabla"] == "stations"]),
        "signal_features": spec("signal_features", ["record_id"], dic[dic["Tabla"] == "signal_features"]),
    }
    d = daily.fillna("")
    d = d.rename(columns={"Tabla": "Tabla", "Campo": "Campo", "Tipo": "Tipo"})
    specs["sites_daily"] = spec("sites_daily", ["site_id", "date"], d[d["Tabla"] == "sites_daily"], year_part=True)
    specs["country_daily"] = spec("country_daily", ["country_iso3", "date"], d[d["Tabla"] == "country_daily"])
    w = _read_weekly(str(dictionary_path))
    specs["sites_weekly"] = spec("sites_weekly", ["site_id", "week_start"], w[w["Tabla"] == "sites_weekly"],
                                 year_part=True)

    lineage_fields = {r["Campo"]: r["Tipo"] for _, r in dic[dic["Tabla"] == "todas"].iterrows()}
    lf = {k: "string" for k in LINEAGE_EXTRA}
    lf["coverage_pct"] = "float"
    lf["n_rows"] = "int"
    lf.update(lineage_fields)
    specs["field_lineage"] = TableSpec("field_lineage", ["table", "field"], lf)
    return specs


def field_index(specs: dict[str, TableSpec]) -> dict[str, list[str]]:
    """field -> tables where it lives (a field name can repeat across tables)."""
    idx: dict[str, list[str]] = {}
    for t, s in specs.items():
        for f in s.fields:
            idx.setdefault(f, []).append(t)
    return idx


def conform(df: pd.DataFrame, spec: TableSpec, logger=None, strict: bool = True) -> pd.DataFrame:
    """Reorder/cast columns to the spec; add missing ones as null; drop unknown ones."""
    unknown = [c for c in df.columns if c not in spec.fields]
    if unknown and logger:
        logger.warning("%s: columnas fuera del diccionario descartadas: %s", spec.name, unknown)
    out = {}
    for col in spec.columns:
        typ = spec.fields[col]
        dtype = PANDAS_DTYPES.get(typ, "object")
        if col in df.columns:
            s = df[col]
        else:
            s = pd.Series([pd.NA] * len(df), index=df.index)
        try:
            if dtype.startswith("datetime"):
                s = pd.to_datetime(s, errors="coerce")
            elif dtype == "boolean":
                s = s.map(lambda v: pd.NA if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA else bool(v)).astype("boolean")
            elif dtype == "Int64":
                s = pd.to_numeric(s, errors="coerce").round().astype("Int64")
            elif dtype == "float64":
                s = pd.to_numeric(s, errors="coerce").astype("float64")
            elif dtype == "string":
                s = s.astype("string")
        except Exception as e:  # keep going, report it
            if strict:
                raise
            if logger:
                logger.warning("%s.%s: no se pudo convertir a %s (%s)", spec.name, col, dtype, e)
        out[col] = s
    return pd.DataFrame(out, index=df.index).reset_index(drop=True)
