# HackFinance_Ingenieros_Ingeniosos

Sistema que mide la viabilidad de construir un data center en un terreno a partir de datos
estructurados (energía, clima, riesgos, conectividad, suelo, economía) y no estructurados.

Países de contexto (indicadores por país): EEUU, Malasia, India, Australia, China, Reino Unido,
Japón y España. Con rejilla de celdas de 3,5 × 3,5 km: **España, Japón y EEUU continental**.
Modelo y web: **España y Japón**.

## Estructura

```
ETL/                  datos: descarga, limpieza y dataset por celda (paquete dclake)
  dclake/             código: un colector por fuente en collectors/
  data_dictionary/    diccionario de datos (manda sobre las columnas del dataset)
  dataset/            el dataset final, en Parquet (una carpeta por tabla)
  tests/              pruebas sin red
Modelo/               modelo: target, variables, exclusiones, puntuación por celda (lo que pinta la web)
  src/                un script por paso (labels, features, feat_*, train, exportar_web)
  data/               entradas (raw), intermedios (cache, no se versiona) y salidas (processed;
                      España en processed/, Japón en processed/JPN/)
  tests/              pruebas sin red
Web/                  la web "Can I Build Here?" (HTML + JS, sin compilar; se publica en Cloudflare)
  data/               ES.json, JP.json y sus regiones, generados por Modelo/src/exportar_web.py
pyproject.toml        configuración de calidad de código (ruff) y de pytest
.github/workflows/    integración continua: formato, lint y pruebas en cada push
```

Cómo ejecutar cada parte: [ETL/README.md](ETL/README.md), [Modelo/README.md](Modelo/README.md) y
[Web/README.md](Web/README.md).

El data lake de Azure (`abfss://dclake@stdclake.dfs.core.windows.net/`) tiene el dataset de los
tres países (`dataset/`) y las salidas del modelo (`processed/`): `python -m dclake azure-setup`
lo crea o renueva el acceso, y `python -m dclake upload` sube lo nuevo (desde `ETL/`).

## Calidad de código

El código sigue PEP 8 con líneas de hasta 99 caracteres (lo que PEP 8 admite cuando el equipo lo
acuerda). Antes de subir cambios, desde la raíz del repositorio:

```
python -m ruff format .        # formato
python -m ruff check . --fix   # PEP 8, orden de imports, errores frecuentes
python -m pytest               # pruebas de ETL y Modelo (sin red, ~10 s)
```

Lo mismo se comprueba en GitHub en cada push y pull request (`.github/workflows/ci.yml`).
Instalación del entorno: ver [ETL/README.md](ETL/README.md#instalación-una-vez) (`pip install ruff` aparte).

## Reglas del equipo

- **Una sola rejilla**: la del ETL (`site_id = <ISO>_<x/3500>_<y/3500>`, en la proyección de igual
  área de cada país: EPSG:3035 en España, Lambert azimutal centrada en Japón).
- **El diccionario manda**: las columnas del dataset son las de `ETL/data_dictionary`.
- **Lo que falta es NaN, nunca 0**, y cada campo lleva su fuente y licencia en `field_lineage`.
- **Datos grandes fuera de git**: el dataset de EEUU y las descargas (cachés, zips del SNCZI) se
  comparten por el data lake (`python -m dclake upload`), no por el repositorio.
