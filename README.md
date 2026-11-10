# HackFinance_Ingenieros_Ingeniosos

Sistema que mide la viabilidad de construir un data center en un terreno a partir de datos
estructurados (energía, clima, riesgos, conectividad, suelo, economía) y no estructurados.

Países de contexto (indicadores por país): EEUU, Malasia, India, Australia, China, Reino Unido,
Japón y España. Con rejilla de celdas de 3,5 × 3,5 km: **España, Japón y EEUU continental**.

## Estructura

```
ELT/                  datos: descarga, limpieza y dataset por celda (paquete dclake)
  dclake/             código: un colector por fuente en collectors/
  data_dictionary/    diccionario de datos (manda sobre las columnas del dataset)
  dataset/            el dataset final, en Parquet (una carpeta por tabla)
  tests/              pruebas sin red
pipeline/             modelo: target, variables, exclusiones, puntuación por celda (lo que pinta la web)
  src/                un script por paso (labels, features, feat_*, train)
  data/               entradas (raw), intermedios (cache, no se versiona) y salidas (processed)
  tests/              pruebas sin red
pyproject.toml        configuración de calidad de código (ruff) y de pytest
.github/workflows/    integración continua: formato, lint y pruebas en cada push
```

Cómo ejecutar cada parte: [ELT/README.md](ELT/README.md) y [pipeline/README.md](pipeline/README.md).

## Calidad de código

El código sigue PEP 8 con líneas de hasta 99 caracteres (lo que PEP 8 admite cuando el equipo lo
acuerda). Antes de subir cambios, desde la raíz del repositorio:

```
python -m ruff format .        # formato
python -m ruff check . --fix   # PEP 8, orden de imports, errores frecuentes
python -m pytest               # pruebas de ELT y pipeline (sin red, ~5 s)
```

Lo mismo se comprueba en GitHub en cada push y pull request (`.github/workflows/ci.yml`).
Instalación del entorno: ver [ELT/README.md](ELT/README.md#instalación-una-vez) (`pip install ruff` aparte).

## Reglas del equipo

- **Una sola rejilla**: la del ELT (`site_id = <ISO>_<x/3500>_<y/3500>`, EPSG:3035 en España).
- **El diccionario manda**: las columnas del dataset son las de `ELT/data_dictionary`.
- **Lo que falta es NaN, nunca 0**, y cada campo lleva su fuente y licencia en `field_lineage`.
- **Datos grandes fuera de git**: el dataset de EEUU y las descargas (cachés, zips del SNCZI) se
  comparten por el data lake (`python -m dclake upload`), no por el repositorio.
