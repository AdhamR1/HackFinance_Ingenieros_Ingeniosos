"""Sources identified but not implemented yet. They document the gap in the coverage report.

To implement one: subclass Collector (see base.py), keep the same `fields`, and replace it
in collectors/__init__.py.
"""

from __future__ import annotations

from .base import PendingCollector


class GloFASPending(PendingCollector):
    name = "glofas"
    reason = (
        "Caudal diario GloFAS (Early Warning Data Store de ECMWF, misma cuenta que CDS, "
        "dataset cems-glofas-historical)"
    )
    fields = {"sites_daily": ["river_discharge_m3s"]}


class CAMSPending(PendingCollector):
    name = "cams"
    reason = "Calidad del aire diaria CAMS EAC4 (Atmosphere Data Store, misma cuenta ECMWF)"
    fields = {
        "sites_daily": ["pm25_ug_m3", "dust_aod"],
        "sites_yearly": ["pm25_ug_m3", "dust_aod", "so2_ug_m3"],
    }


class BuildingsPending(PendingCollector):
    name = "buildings"
    reason = "Huellas de edificios: Catastro INSPIRE (ESP) o Microsoft/Google Open Buildings"
    fields = {
        "sites_static": [
            "dist_nearest_dwelling_m",
            "n_buildings_1km",
            "n_dwellings_1km",
            "housing_density_km2",
        ]
    }


class TrafficPending(PendingCollector):
    name = "traffic"
    reason = (
        "Aforos del Mapa de Tráfico (MITMA), movimientos de AENA y sobrevuelos de OpenSky Network"
    )
    fields = {
        "sites_yearly": ["aadt_nearest_road", "airport_annual_movements", "overflights_per_day"],
        "sites_static": [
            "heavy_vehicle_pct",
            "road_noise_lden_db",
            "aircraft_noise_lden_db",
            "in_aero_easement_flag",
        ],
    }


class LandPricePending(PendingCollector):
    name = "land_prices"
    reason = (
        "Valor del suelo: estadística de valor tasado (MITMA) o Catastro; requiere scraping "
        "o descarga manual"
    )
    fields = {"sites_yearly": ["land_price_usd_m2", "land_price_trend_5y_pct"]}


class BiodiversityPending(PendingCollector):
    name = "biodiversity_species"
    reason = (
        "Rangos de la Lista Roja UICN (registro, licencia NC), GBIF API y KBA/IBAT (solicitud)"
    )
    fields = {
        "sites_static": [
            "n_threatened_species_10km",
            "n_cr_en_species_10km",
            "n_threatened_mammals",
            "n_threatened_birds",
            "n_threatened_amphibians_reptiles",
            "n_threatened_plants",
            "n_endemic_species",
            "species_richness",
            "n_gbif_threatened_occ_5km",
            "in_kba",
            "in_iba",
        ]
    }


class GridCapacityPending(PendingCollector):
    name = "grid_capacity"
    reason = "Capacidad de acceso por nudo publicada por REE (PDF/Excel por nudo); requiere parseo"
    fields = {"sites_static": ["grid_capacity_available_mw", "grid_congestion_flag"]}


PENDING = [
    GloFASPending,
    CAMSPending,
    BuildingsPending,
    TrafficPending,
    LandPricePending,
    BiodiversityPending,
    GridCapacityPending,
]
