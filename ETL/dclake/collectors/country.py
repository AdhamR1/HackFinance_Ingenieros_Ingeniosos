"""Country-level yearly indicators (World Bank API) for the 8 countries + reference facts."""

from __future__ import annotations

import pandas as pd

from .base import Collector

WB = "https://api.worldbank.org/v2/country/{codes}/indicator/{ind}"

COUNTRY_FIELDS = {  # field -> (indicator, source id) ; source 3 = Worldwide Governance Indicators
    # Since the 2024 WGI revision the API codes are GOV_WGI_<X>.EST (estimate, approx. -2.5..2.5,
    # the unit of the dictionary) and GOV_WGI_<X>.SC (0-100 score). The old <X>.EST codes are
    # rejected.
    "political_stability_wgi": ("GOV_WGI_PV.EST", 3),
    "government_effectiveness_wgi": ("GOV_WGI_GE.EST", 3),
    "regulatory_quality_wgi": ("GOV_WGI_RQ.EST", 3),
    "rule_of_law_wgi": ("GOV_WGI_RL.EST", 3),
    "control_of_corruption_wgi": ("GOV_WGI_CC.EST", 3),
    "voice_accountability_wgi": ("GOV_WGI_VA.EST", 3),
    "internet_users_pct": ("IT.NET.USER.ZS", 2),
    "trade_openness_pct": ("NE.TRD.GNFS.ZS", 2),
    "usd_fx_rate": ("PA.NUS.FCRF", 2),
}
SITE_YEARLY_FIELDS = {  # national value used as proxy for every Spanish cell
    "inflation_pct": ("FP.CPI.TOTL.ZG", 2),
    "gdp_per_capita_ppp": ("NY.GDP.PCAP.PP.CD", 2),
    "unemployment_rate_pct": ("SL.UEM.TOTL.ZS", 2),
    "ppp_factor": ("PA.NUS.PPP", 2),
    "interest_rate_pct": ("FR.INR.LEND", 2),
}
REFERENCE = {  # stable facts, not indicators
    "ESP": {
        "currency": "EUR",
        "business_language": "es",
        "time_zone_utc_offset": 1,
        "seismic_code": "NCSE-02 / Eurocódigo 8",
    },
    "USA": {
        "currency": "USD",
        "business_language": "en",
        "time_zone_utc_offset": -5,
        "seismic_code": "ASCE 7",
    },
    "MYS": {
        "currency": "MYR",
        "business_language": "ms/en",
        "time_zone_utc_offset": 8,
        "seismic_code": "MS EN 1998-1",
    },
    "IND": {
        "currency": "INR",
        "business_language": "en/hi",
        "time_zone_utc_offset": 5.5,
        "seismic_code": "IS 1893",
    },
    "AUS": {
        "currency": "AUD",
        "business_language": "en",
        "time_zone_utc_offset": 10,
        "seismic_code": "AS 1170.4",
    },
    "CHN": {
        "currency": "CNY",
        "business_language": "zh",
        "time_zone_utc_offset": 8,
        "seismic_code": "GB 50011",
    },
    "JPN": {
        "currency": "JPY",
        "business_language": "ja",
        "time_zone_utc_offset": 9,
        "seismic_code": "Building Standard Law",
    },
    "GBR": {
        "currency": "GBP",
        "business_language": "en",
        "time_zone_utc_offset": 0,
        "seismic_code": "BS EN 1998",
    },
}


def fetch_indicator(
    lake, codes: list[str], ind: str, source: int, y0: int, y1: int
) -> pd.DataFrame:
    url = WB.format(codes=";".join(codes), ind=ind)
    js = lake.get_json(
        url,
        lake.raw / "worldbank" / f"{ind}_{source}_{y0}_{y1}.json",
        params={"source": source, "format": "json", "date": f"{y0}:{y1}", "per_page": 20000},
        sleep=0.5,
    )
    if not js or len(js) < 2 or js[1] is None:
        return pd.DataFrame(columns=["country_iso3", "year", "value"])
    return pd.DataFrame(
        [
            {
                "country_iso3": r.get("countryiso3code") or r["country"]["id"],
                "year": int(r["date"]),
                "value": r["value"],
            }
            for r in js[1]
        ]
    )


class WorldBankCollector(Collector):
    name = "worldbank"
    description = "Indicadores anuales por país (Banco Mundial: WGI y WDI)"
    source = "World Bank API (WGI, WDI)"
    source_url = "https://api.worldbank.org/v2"
    license = "CC BY 4.0"
    confidence = 0.9
    fields = {
        "country_context": [
            *list(COUNTRY_FIELDS),
            "currency",
            "business_language",
            "time_zone_utc_offset",
            "seismic_code",
        ],
        "sites_yearly": list(SITE_YEARLY_FIELDS),
    }

    def run(self, sites):
        countries = self.cfg["countries"]
        y0 = pd.Timestamp(self.cfg["period"]["start"]).year
        y1 = pd.Timestamp(self.cfg["period"]["end"]).year
        base = pd.MultiIndex.from_product(
            [countries, range(y0, y1 + 1)], names=["country_iso3", "year"]
        ).to_frame(index=False)
        allf = {**COUNTRY_FIELDS, **SITE_YEARLY_FIELDS}
        for field, (ind, src) in allf.items():
            try:
                v = fetch_indicator(self.lake, countries, ind, src, y0, y1).rename(
                    columns={"value": field}
                )
                base = base.merge(v, on=["country_iso3", "year"], how="left")
            except Exception as e:
                self.log.warning("  %s (%s) no disponible: %s", field, ind, e)
        for k in ("currency", "business_language", "time_zone_utc_offset", "seismic_code"):
            base[k] = base["country_iso3"].map(lambda c, k=k: REFERENCE.get(c, {}).get(k))
        self.lake.catalog("worldbank_api", self.source, self.source_url, self.license)
        self.stage(
            "country_context", base.drop(columns=[f for f in SITE_YEARLY_FIELDS if f in base])
        )

        es = base[base["country_iso3"] == self.cfg["project"]["country_iso3"]]
        cols = [c for c in SITE_YEARLY_FIELDS if c in es]
        sy = sites[["site_id"]].merge(es[["year", *cols]], how="cross")
        self.stage("sites_yearly", sy)

    def write_lineage(self, **kw):
        per = {
            f: {"imputation_method": "valor nacional como proxy", "confidence": 0.5}
            for f in SITE_YEARLY_FIELDS
        }
        per.update(
            {
                f: {
                    "source": "Referencia fija en el código (collectors/country.py)",
                    "license": "-",
                }
                for f in ("currency", "business_language", "time_zone_utc_offset", "seismic_code")
            }
        )
        super().write_lineage(per_field=per)
