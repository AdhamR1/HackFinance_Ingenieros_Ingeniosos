"""FINANCE layer per cell: what it costs to build and run a data center there.

This is NOT a model input (the file is not called feat_*): the model says WHERE a data center
fits; this layer says HOW MUCH it costs. Mixing them would let land price act as a proxy for
"near Madrid" (where the existing data centers are).

Sources (public, no registration):
  * Electricity: OMIE day-ahead price, Spain, mean of 2025 (already in ELT/dataset/country_daily).
    Same price in the whole country: the islands are also billed at the peninsular price.
  * PUE: est_pue from the ELT (depends on the climate of the cell).
  * Land: Ministerio de Transportes, Estadística de Precios de Suelo, per province:
    value / surface of all land transactions in the last 4 quarters published (tables 2.x / 3.x).
  * Labour: INE, Encuesta Trimestral de Coste Laboral (table 6061), per autonomous community,
    total labour cost per worker and month, mean of the last 4 quarters.
  * Grid connection (only if data/processed/feat_infra.parquet exists): distance to the nearest
    220 kV+ substation x cost per km of a 220 kV line (ASSUMPTION, see LINE_220KV_MEUR_KM).

Reference project for the totals: 10 MW of IT on 10 ha (100,000 m2).

Output: data/processed/finanzas_es_3500.parquet
"""
import json
import unicodedata

import numpy as np
import pandas as pd
import requests

from cells import ELT_DATASET, PIPELINE, PROCESSED, read_elt, read_grid

CACHE = PIPELINE / "data" / "cache" / "finanzas"
HEADERS = {"User-Agent": "hackfinance-dc-siting/0.1 (hackathon research)"}
MITMA = "https://apps.fomento.gob.es/BoletinOnline2/sedal/{}.XLS"
LAND_VALUE = ["36201000", "36201500"]      # tables 2.1 / 2.2: value (thousand EUR), natural / legal persons
LAND_AREA = ["36301000", "36301500"]       # tables 3.1 / 3.2: surface (thousand m2)
INE_LABOUR = "https://servicios.ine.es/wstempus/js/es/DATOS_TABLA/6061?nult=4"

IT_MW = 10                  # reference project
LAND_M2 = 100_000           # 10 ha
HOURS = 8760
LINE_220KV_MEUR_KM = 0.4    # ASSUMPTION: order of magnitude of a 220 kV overhead line in Spain
# Building + M&E: Turner & Townsend, Data Centre Construction Cost Index 2025-2026, Madrid = 10.0 USD/W
# (air-cooled, 30-50 MW; excludes land, utility works, site works, IT equipment, fees).
BUILD_MADRID_USD_W = 10.0
LABOUR_SHARE = 0.35         # ASSUMPTION: share of the build cost that is labour (scaled by INE regional cost)
YEARS = 10                  # horizon for the cost including electricity


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace("(", " ").replace(")", " ").replace(",", " ").split())


# grid name -> name used by the source, when they do not match after norm()
PROV_ALIAS = {"alava": "alava", "bizkaia": "vizcaya", "gipuzkoa": "guipuzcoa", "coruna": "coruna a",
              "rioja la": "rioja la", "palmas las": "palmas las", "balears illes": "balears illes",
              # single-province communities appear under the community name
              "asturias": "asturias principado de", "madrid": "madrid comunidad de",
              "murcia": "murcia region de", "navarra": "navarra comunidad foral de"}
CCAA_ALIAS = {"cataluna/catalunya": "cataluna", "pais vasco/euskadi": "pais vasco",
              "comunidad foral de navarra": "navarra comunidad foral de", "comunidad de madrid": "madrid comunidad de",
              "region de murcia": "murcia region de", "principado de asturias": "asturias principado de",
              "castilla-la mancha": "castilla - la mancha", "illes balears": "balears illes", "la rioja": "rioja la"}


def download(url, name):
    dest = CACHE / name
    if not dest.exists():
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
    return dest


def mitma_last4(code) -> pd.Series:
    """Province -> sum of the last 4 quarters of one MITMA land table."""
    t = pd.read_excel(download(MITMA.format(code), f"{code}.xls"), header=None)
    quarters = [c for c in t.columns if pd.to_numeric(t[c].iloc[14:70], errors="coerce").notna().sum() > 30]
    quarters = [c for c in quarters if "aci" not in str(t[c].iloc[11])]   # drop the "variación" columns
    rows = t.iloc[14:].dropna(subset=[1])
    vals = rows[quarters[-4:]].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    return pd.Series(vals.values, index=[norm(n) for n in rows[1]])


def land_price() -> pd.Series:
    value = sum(mitma_last4(c) for c in LAND_VALUE)
    area = sum(mitma_last4(c) for c in LAND_AREA)
    return (value / area).replace([np.inf], np.nan)          # thousand EUR / thousand m2 = EUR/m2


def labour_cost() -> pd.Series:
    d = json.loads(download(INE_LABOUR, "ine_6061.json").read_text(encoding="utf-8"))
    out = {}
    for s in d:
        name = s["Nombre"]
        if "Coste laboral total" in name and "Industria, construcci" in name:
            out[norm(name.split(".")[0])] = np.mean([p["Valor"] for p in s["Data"]])
    return pd.Series(out)


def match(names: pd.Series, table: pd.Series, alias: dict, fallback: float) -> pd.Series:
    def find(n):
        k = alias.get(norm(n), norm(n))
        hits = [v for key, v in table.items() if key == k or key.split("/")[0].strip() == k]
        return hits[0] if hits else np.nan
    m = {n: find(n) for n in names.unique()}
    missing = [n for n, v in m.items() if pd.isna(v)]
    if missing:
        print(f"    sin dato propio, uso la media nacional: {', '.join(missing)}")
    return names.map(m).fillna(fallback)


def main():
    grid = read_grid()
    out = grid[["site_id", "admin1", "admin2"]].copy()

    omie = pd.read_parquet(ELT_DATASET / "country_daily" / "ESP.parquet")["omie_price_mean_eur_mwh"].mean()
    pue = read_elt("sites_yearly", ["site_id", "est_pue"]).groupby("site_id").est_pue.mean()
    out["est_pue"] = out.site_id.map(pue).fillna(pue.median())
    out["precio_luz_eur_mwh"] = round(omie, 2)
    out["coste_energia_meur_ano"] = IT_MW * out.est_pue * HOURS * omie / 1e6
    print(f"Luz: OMIE 2025 = {omie:.2f} EUR/MWh; PUE de {out.est_pue.min():.2f} a {out.est_pue.max():.2f}")

    land = land_price()
    print("Suelo (EUR/m2, últimos 4 trimestres):")
    out["precio_suelo_eur_m2"] = match(out.admin2, land, PROV_ALIAS, land.get("total nacional"))
    out["coste_suelo_meur"] = out.precio_suelo_eur_m2 * LAND_M2 / 1e6

    lab = labour_cost()
    print("Coste laboral (EUR/trabajador/mes, últimos 4 trimestres):")
    out["coste_laboral_eur_mes"] = match(out.admin1, lab, CCAA_ALIAS, lab.get("total nacional"))

    eur_usd = pd.read_parquet(ELT_DATASET / "country_daily" / "ESP.parquet")["eur_usd"].mean()
    madrid = lab.get("madrid comunidad de")
    base = BUILD_MADRID_USD_W * IT_MW / eur_usd                       # M EUR for IT_MW in Madrid
    out["coste_construccion_meur"] = base * (1 - LABOUR_SHARE + LABOUR_SHARE * out.coste_laboral_eur_mes / madrid)
    print(f"Construcción: {BUILD_MADRID_USD_W} USD/W en Madrid = {base:.1f} M EUR para {IT_MW} MW "
          f"(EUR/USD {eur_usd:.3f}), mano de obra {LABOUR_SHARE:.0%} ajustada por comunidad")

    infra = PROCESSED / "feat_infra.parquet"
    if infra.exists():
        d = pd.read_parquet(infra).set_index("site_id")["dist_substation_220kv_km"]
        out["coste_conexion_meur"] = out.site_id.map(d) * LINE_220KV_MEUR_KM
        print(f"Conexión: {LINE_220KV_MEUR_KM} M EUR/km hasta la subestación de 220 kV más cercana (supuesto)")
    else:
        out["coste_conexion_meur"] = np.nan
        print("Conexión: falta feat_infra.parquet (red eléctrica); la inversión total sale SIN conexión hasta entonces")

    # what Adham asked for: total cost per m2 of plot, and the same including YEARS of electricity
    out["inversion_meur"] = out.coste_suelo_meur + out.coste_construccion_meur + out.coste_conexion_meur.fillna(0)
    out["inversion_eur_m2"] = out.inversion_meur * 1e6 / LAND_M2
    out[f"coste_{YEARS}_anos_meur"] = out.inversion_meur + YEARS * out.coste_energia_meur_ano
    out[f"coste_{YEARS}_anos_eur_m2"] = out[f"coste_{YEARS}_anos_meur"] * 1e6 / LAND_M2

    out = out.drop(columns=["admin1", "admin2"]).round(3)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROCESSED / "finanzas_es_3500.parquet", index=False)
    print(out.describe().T[["min", "50%", "max"]].round(2).to_string())
    print(f"-> {PROCESSED / 'finanzas_es_3500.parquet'}")


if __name__ == "__main__":
    main()
