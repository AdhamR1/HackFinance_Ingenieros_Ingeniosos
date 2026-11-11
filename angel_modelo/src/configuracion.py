"""Rutas y configuración compartidas por todos los pasos. Multipaís sin «if país == ...».

La configuración efectiva = config/columnas.yaml (común) + config/paises/<pais>.yaml (perfil del país),
fusionadas en profundidad (el perfil gana). El país se elige con la variable de entorno MAPA_PAIS
(código de 2 letras en minúsculas, por defecto «es»). Las rutas se pueden sobrescribir con MAPA_<CLAVE>
(MAPA_ELT_DATASET, MAPA_PIPELINE_PROCESSED, MAPA_PIPELINE_RAW, MAPA_SALIDA, MAPA_WEB, MAPA_WEB_INTEGRADA,
MAPA_DATOS_PROPIOS) para probar con copias de los datos sin tocar el repositorio.
Añadir un país = añadir config/paises/<xx>.yaml (ver README).
"""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path

import yaml

RAIZ_MODULO = Path(__file__).resolve().parents[1]          # angel_modelo/
REPO = RAIZ_MODULO.parent
CONFIG = RAIZ_MODULO / "config"
SEMILLA = 42


class ErrorFatal(SystemExit):
    """Error que impide generar el mapa (falta identificador, coordenadas o una ruta de entrada)."""

    def __init__(self, mensaje: str):
        super().__init__(f"\nERROR FATAL: {mensaje}\n")


def _fusionar(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _fusionar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def pais() -> str:
    return os.environ.get("MAPA_PAIS", "es").strip().lower() or "es"


def paises_disponibles() -> list[str]:
    return sorted(p.stem for p in (CONFIG / "paises").glob("*.yaml"))


@lru_cache(maxsize=None)
def _cargar(p: str) -> dict:
    base = yaml.safe_load((CONFIG / "columnas.yaml").read_text(encoding="utf-8"))
    f = CONFIG / "paises" / f"{p}.yaml"
    if not f.exists():
        raise ErrorFatal(f"no hay perfil de país config/paises/{p}.yaml (disponibles: {paises_disponibles()})")
    return _fusionar(base, yaml.safe_load(f.read_text(encoding="utf-8")))


def columnas() -> dict:
    """Configuración efectiva del país actual (común + perfil). Fija DC_COUNTRY para el código del equipo
    (Modelo/src/cells.py elige país, proyección y carpeta con esa variable)."""
    c = _cargar(pais())
    os.environ["DC_COUNTRY"] = c["pais"]
    return c


perfil = columnas


def ruta(clave: str) -> Path:
    """Ruta configurada (relativa a la raíz del repo) o la de la variable de entorno MAPA_<CLAVE>."""
    env = os.environ.get("MAPA_" + clave.upper())
    valor = env if env is not None else columnas()["rutas"].get(clave, "")
    if valor == "":
        return Path()
    p = Path(valor)
    p = p if p.is_absolute() else REPO / p
    sub = columnas().get("subcarpeta_procesados") if clave == "pipeline_processed" else None
    return p / sub if sub else p


def salida() -> Path:
    """Intermedios del país: <salida>/<pais>/ (ignorado por git)."""
    p = ruta("salida") / pais()
    p.mkdir(parents=True, exist_ok=True)
    return p


def web_datos() -> Path:
    """Datos del mapa del país: <web>/data/<pais>/."""
    return ruta("web") / "data" / pais()


def crs_rejilla() -> str:
    """Proyección métrica de igual área de la rejilla: la del ETL del equipo (ETL/config.yaml) salvo que el
    perfil la fije en rejilla.crs."""
    r = columnas()["rejilla"]
    if r.get("crs") and r["crs"] != "desde_etl":
        return r["crs"]
    etl = yaml.safe_load((REPO / "ETL" / "config.yaml").read_text(encoding="utf-8"))
    return etl["country_profiles"][columnas()["pais"]]["crs_equal_area"]


def pais_tiene_datos(p: str) -> bool:
    """¿Hay tabla estática del ETL para el país p? (si no, el orquestador lo salta con aviso)."""
    c = _cargar(p)
    env = os.environ.get("MAPA_ELT_DATASET")
    base = Path(env) if env else REPO / c["rutas"]["elt_dataset"]
    return any((base / c["tablas"]["estatica"]).glob(f"{c['pais']}-p*.parquet"))
