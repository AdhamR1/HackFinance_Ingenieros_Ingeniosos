"""Collector registry. Order matters: when two collectors fill the same field, the earlier one wins."""
from .base import Collector, PendingCollector
from .climate import ERA5LandCollector
from .country import WorldBankCollector
from .derived import DerivedCollector
from .electricity import ElectricityESCollector
from .eobs import EOBSCollector
from .gridclimate import GridMETCollector, NASAPowerCollector
from .hazards import EarthquakesCollector, FIRMSCollector
from .openmeteo import OpenMeteoCollector
from .osm import OSMCollector
from .peeringdb import HubsCollector, PeeringDBCollector
from .pending import PENDING
from .rasters import DEMCollector, ManualLayersCollector, RemoteRastersCollector
from .seismic import SeismicCollector
from .transport import AirportsCollector, CablesCollector, CoastCollector

REGISTRY = [
    OSMCollector, PeeringDBCollector, HubsCollector, AirportsCollector, CablesCollector, CoastCollector,
    DEMCollector, RemoteRastersCollector, ManualLayersCollector,
    EarthquakesCollector, FIRMSCollector, ERA5LandCollector, EOBSCollector, GridMETCollector, NASAPowerCollector, OpenMeteoCollector, ElectricityESCollector,
    WorldBankCollector,
    SeismicCollector, *PENDING,
    DerivedCollector,  # always last
]
BY_NAME = {c.name: c for c in REGISTRY}
