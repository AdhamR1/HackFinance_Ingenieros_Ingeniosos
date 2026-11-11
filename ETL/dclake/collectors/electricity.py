"""Spanish electricity: OMIE day-ahead prices, REE generation mix, ECB EUR/USD rate (all daily, no
API key)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Collector

OMIE_URL = "https://www.omie.es/es/file-download"
REE_URL = "https://apidatos.ree.es/es/datos/generacion/estructura-generacion"
ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"


def parse_omie_marginal(text: str, es_index: int = 5) -> list[float]:
    """Spanish marginal prices (one per hour or quarter-hour) from a marginalpdbc file."""
    prices = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        vals = [p for p in parts if p != ""]
        try:
            idx = es_index if len(vals) > es_index else len(vals) - 1
            prices.append(float(vals[idx].replace(",", ".")))
        except ValueError:
            continue
    return prices


class ElectricityESCollector(Collector):
    countries = {"ESP"}
    name = "electricity_es"
    description = "Precio diario OMIE, mix de generación REE y tipo de cambio BCE"
    source = "OMIE / REE REData / BCE"
    source_url = (
        "https://www.omie.es ; https://www.ree.es/es/apidatos ; https://data.ecb.europa.eu"
    )
    license = "Condiciones de uso de OMIE, REE (reutilización con atribución) y BCE"
    confidence = 0.9
    fields = {
        "country_daily": [
            "omie_price_mean_eur_mwh",
            "omie_price_max_eur_mwh",
            "omie_price_min_eur_mwh",
            "eur_usd",
            "omie_price_mean_usd_mwh",
            "gen_total_gwh",
            "renewable_share_pct",
            "carbon_intensity_gco2_kwh",
        ]
    }

    def run(self, sites):
        p = self.cfg["period"]
        days = pd.date_range(p["start"], p["end"], freq="D")
        df = pd.DataFrame({"country_iso3": "ESP", "date": days})
        for step in (self._omie, self._ree, self._ecb):
            try:
                part = step(days)
                if part is not None and len(part):
                    df = df.merge(part, on="date", how="left")
            except Exception as e:
                self.log.error("  %s falló: %s", step.__name__, e)
        if {"omie_price_mean_eur_mwh", "eur_usd"} <= set(df.columns):
            df["omie_price_mean_usd_mwh"] = df["omie_price_mean_eur_mwh"] * df["eur_usd"]
        self.stage("country_daily", df)

    # ------------------------------------------------------------------ OMIE
    def _omie(self, days):
        import re
        import zipfile

        from tqdm import tqdm

        idx = self.cfg["electricity"]["omie_es_field_index"]
        # closed years come in one zip per year (365 files): 16 requests instead of ~5,800
        texts = {}
        for y in sorted(set(days.year)):
            if y >= pd.Timestamp.today().year:
                continue
            try:
                z = self.lake.cached_get(
                    OMIE_URL,
                    self.lake.raw / "omie" / f"marginalpdbc_{y}.zip",
                    params={"parents": "marginalpdbc", "filename": f"marginalpdbc_{y}.zip"},
                    timeout=300,
                    min_bytes=1000,
                    sleep=0.5,
                    validate=lambda b: b[:2] == b"PK",
                )
            except Exception as e:
                self.log.warning("  OMIE %d (zip anual): %s; se descarga día a día", y, e)
                z = None
            if z is not None:
                with zipfile.ZipFile(z) as zf:
                    for n in sorted(
                        zf.namelist(), reverse=True
                    ):  # version .1 is read last, so it wins
                        m = re.search(r"marginalpdbc_(\d{8})\.\d", n)
                        if m:
                            texts[m.group(1)] = zf.read(n).decode("latin-1", errors="ignore")
        rows, misses, dead = [], {}, set()
        for d in tqdm(days, desc="OMIE"):
            ds = d.strftime("%Y%m%d")
            text = texts.get(ds)
            if text is None and d.year in dead:
                continue
            for version in () if text else (1, 2, 3):
                dest = self.lake.raw / "omie" / f"marginalpdbc_{ds}.{version}"
                try:
                    # 'parents[0]=' answers with an HTML redirect page (HTTP 200): use 'parents='
                    path = self.lake.cached_get(
                        OMIE_URL,
                        dest,
                        params={
                            "parents": "marginalpdbc",
                            "filename": f"marginalpdbc_{ds}.{version}",
                        },
                        timeout=60,
                        min_bytes=50,
                        sleep=0.2,
                        validate=lambda b: b.lstrip()[:12].upper() == b"MARGINALPDBC",
                    )
                except Exception as e:
                    self.log.debug("  OMIE %s.%d: %s", ds, version, e)
                    path = None
                if path is not None:
                    text = path.read_bytes().decode("latin-1", errors="ignore")
                    break
            if (
                text is None
            ):  # OMIE publishes files from 2018 on: a year whose first week fails is skipped
                misses[d.year] = misses.get(d.year, 0) + 1
                if misses[d.year] >= 7 and not any(r["date"].year == d.year for r in rows[-7:]):
                    dead.add(d.year)
                    self.log.warning(
                        "  OMIE %d: sin archivos diarios publicados; el año queda vacío", d.year
                    )
            prices = parse_omie_marginal(text, idx) if text else []
            if prices:
                rows.append(
                    {
                        "date": d,
                        "omie_price_mean_eur_mwh": float(np.mean(prices)),
                        "omie_price_max_eur_mwh": float(np.max(prices)),
                        "omie_price_min_eur_mwh": float(np.min(prices)),
                    }
                )
        self.lake.catalog("omie_marginalpdbc", "OMIE", OMIE_URL, "Condiciones de uso de OMIE")
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ REE
    def _ree(self, days):
        ecfg = self.cfg["electricity"]
        factors = ecfg["emission_factors"]
        renewable_titles = set(ecfg["renewable_titles"])
        series = {}
        for year in sorted(set(days.year)):
            start = max(days.min(), pd.Timestamp(f"{year}-01-01"))
            end = min(days.max(), pd.Timestamp(f"{year}-12-31"))
            try:  # REE has daily data from 2011: a year it does not have must not drop the others
                js = self.lake.get_json(
                    REE_URL,
                    self.lake.raw
                    / "ree"
                    / f"estructura_generacion_{start:%Y%m%d}_{end:%Y%m%d}.json",
                    params={
                        "start_date": start.strftime("%Y-%m-%dT00:00"),
                        "end_date": end.strftime("%Y-%m-%dT23:59"),
                        "time_trunc": "day",
                    },
                    sleep=1,
                )
            except Exception as e:
                self.log.warning("  REE %d: sin datos (%s)", year, str(e)[:100])
                continue
            for item in (js or {}).get("included", []):
                a = item.get("attributes", {})
                title = a.get("title") or item.get("type")
                for v in a.get("values", []):
                    dt = (
                        pd.to_datetime(v["datetime"], utc=True)
                        .tz_convert("Europe/Madrid")
                        .tz_localize(None)
                        .normalize()
                    )
                    series.setdefault(title, {})[dt] = v.get("value")
                if a.get("type") and str(a["type"]).lower().startswith("renov"):
                    renewable_titles.add(title)
        self.lake.catalog(
            "ree_estructura_generacion", "REE REData", REE_URL, "REE: reutilización con atribución"
        )
        if not series:
            return None
        gen = pd.DataFrame(series)  # MWh per technology
        total = gen["Generación total"] if "Generación total" in gen else gen.sum(axis=1)
        ren = gen[[c for c in gen.columns if c in renewable_titles]].sum(axis=1)
        co2 = sum(gen[c].fillna(0) * f for c, f in factors.items() if c in gen)  # tCO2
        out = pd.DataFrame(
            {
                "date": gen.index,
                "gen_total_gwh": total.values / 1000,
                "renewable_share_pct": (100 * ren / total).values,
                "carbon_intensity_gco2_kwh": (1000 * co2 / total).values
                if not isinstance(co2, int)
                else np.nan,
            }
        )
        return out

    # ------------------------------------------------------------------ ECB
    def _ecb(self, days):
        p = self.lake.cached_get(
            ECB_URL,
            self.lake.raw / "ecb" / f"eur_usd_{days.min():%Y%m%d}_{days.max():%Y%m%d}.csv",
            params={
                "format": "csvdata",
                "startPeriod": days.min().strftime("%Y-%m-%d"),
                "endPeriod": days.max().strftime("%Y-%m-%d"),
            },
        )
        fx = pd.read_csv(p)[["TIME_PERIOD", "OBS_VALUE"]]
        fx.columns = ["date", "eur_usd"]
        fx["date"] = pd.to_datetime(fx["date"])
        fx = fx.set_index("date").reindex(days).ffill().bfill().rename_axis("date").reset_index()
        self.lake.catalog("ecb_eurusd", "BCE", ECB_URL, "Reutilización libre con atribución (BCE)")
        return fx

    def write_lineage(self, **kw):
        super().write_lineage(
            per_field={
                "carbon_intensity_gco2_kwh": {
                    "imputation_method": "modelo",
                    "confidence": 0.6,
                    "notes": "Generación diaria REE x factores de emisión de config.yaml "
                    "(supuesto)",
                },
                "gen_total_gwh": {"notes": "Sistema nacional (incluye islas)"},
                "renewable_share_pct": {"notes": "Sistema nacional (incluye islas)"},
            }
        )
