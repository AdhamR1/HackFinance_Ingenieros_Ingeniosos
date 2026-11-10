"""Rutas y configuración compartidas por todos los pasos.

Todo sale de config/columnas.yaml y config/rubrica.yaml. Las rutas de entrada y salida se pueden
sobrescribir con variables de entorno (útil para probar con copias de los datos sin tocar el repositorio):
    MAPA_ELT_DATASET, MAPA_PIPELINE_PROCESSED, MAPA_PIPELINE_RAW, MAPA_SALIDA, MAPA_WEB, MAPA_WEB_INTEGRADA
"""
from __future__ import annotations

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


@lru_cache(maxsize=None)
def columnas() -> dict:
    return yaml.safe_load((CONFIG / "columnas.yaml").read_text(encoding="utf-8"))


def ruta(clave: str) -> Path:
    """Ruta configurada (relativa a la raíz del repo) o la de la variable de entorno MAPA_<CLAVE>."""
    env = os.environ.get("MAPA_" + clave.upper())
    valor = env if env is not None else columnas()["rutas"].get(clave, "")
    if valor == "":
        return Path()
    p = Path(valor)
    return p if p.is_absolute() else REPO / p


def salida() -> Path:
    p = ruta("salida")
    p.mkdir(parents=True, exist_ok=True)
    return p
