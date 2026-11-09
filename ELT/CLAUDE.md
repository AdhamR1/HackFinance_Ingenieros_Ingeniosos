# CLAUDE.md: contexto de ELT para Claude Code

## Qué es
Hackathon de finanzas (equipo de 5, 4 días). Herramienta de **cribado de viabilidad de parcelas para data centers**: ruido sísmico ambiental (H/V) + energía, agua, clima, riesgos, conectividad, economía, regulación y biodiversidad → puntuación, coste por MW e informe generado por Claude. Es un cribado inicial, no un estudio geotécnico.

Esta carpeta es la parte de **datos**: construye el data lake del que se entrena el modelo. Responde siempre en español.

## Reglas
- **El diccionario manda.** `data_dictionary/diccionario_datos_datacenters.xlsx` define tablas, campos, tipos, temporalidad y prioridad. `schema.conform` descarta columnas que no estén en él. Para cambiar campos: editar `data_dictionary/build_dict.py`, regenerar el xlsx y luego el código. **Preguntar antes** de cambiar la estructura del diccionario o borrar datos descargados.
- **No inventar datos.** Si una fuente no está, el campo queda nulo y sale en el informe de cobertura. Lo que sea modelo, proxy o sintético se marca en el linaje (`is_synthetic`, `imputation_method`, `notes`).
- **Linaje siempre.** Cada colector declara `fields`, `source`, `license`.
- **Windows y red corporativa.** `pathlib`, nada de `:` en nombres de archivo. Conda está bloqueado (anaconda.org): se usa venv + pip. Hay inspección TLS: `dclake/__init__.py` activa `truststore` para requests y `rasters.py` pasa a GDAL un bundle con los certificados de Windows.
- **Reanudable e idempotente.** Toda descarga pasa por `lake.cached_get` (caché en `<lake>/raw/`, con `validate` para no guardar páginas de error). Las cachés que dependen del periodo llevan el periodo en el nombre. Un colector que falla no para a los demás.
- **Educado con las APIs.** Pausas, reintentos con backoff, límites (Overpass, Open-Meteo), términos de uso.
- **Todo dentro del repo y sin archivos basura.** La única salida es el dataset en `ELT/dataset/`. Descargas, staging, logs, informes y demo van en `ELT/.cache/` (ignorada en git). Nunca escribir fuera del repo ni generar Excel o informes que no se hayan pedido. Los archivos grandes intermedios (E-OBS de toda Europa) se descargan en temporal y solo se guarda el recorte de España.
- Código y comentarios en inglés; documentación, logs y mensajes al usuario en español.

## Comandos (desde ELT/, con `%USERPROFILE%\.venvs\dclake` activado)
```
python -m pytest -q tests
python -m dclake demo                       # offline, datos sintéticos
python -m dclake grid --country ESP|JPN|USA
python -m dclake collect --country JPN --only <nombre> --limit-sites 3   (o --sites id1,id2)
python -m dclake collect --country JPN [--skip a,b] [--part N] [--start AAAA-MM-DD --end AAAA-MM-DD]
python -m dclake assemble --country JPN     # dataset en ELT/dataset/ (+ .cache/JPN/reports/coverage.csv)
python -m dclake export --sites a,b,c --out x.xlsx   # solo si lo piden
```

## Arquitectura
- **Varios países.** `config.yaml > country_profiles` define por país la proyección de igual área, las cajas, la fuente de clima (`climate`), los vecinos (`neighbours_iso2`), las regiones foco y los colectores que se saltan. `--country` o `DCLAKE_COUNTRY` elige el país; `config.apply_country_profile` lo aplica y `geo.set_equal_area` fija la proyección. Caché por país en `.cache/<ISO>/`.
- `grid.py`: rejilla de 3,5 km sobre geoBoundaries (`site_id = <ISO>_<x/3500>_<y/3500>`), etiquetas de muestra y **partes**: franjas por x de ≤ `max_cells_per_part` celdas (EEUU ~26). `lake.with_part(k)` limita `sites()` y el staging a una parte.
- `collectors/*.py`: cada uno escribe en `<lake>/staging/part-NN/<colector>/<tabla>.parquet` (las diarias por año). `countries` / `climate_key` limitan dónde corre (E-OBS en Europa, gridMET en EEUU, NASA POWER en Japón, OMIE/REE en España). Orden en `collectors/__init__.py`: si dos colectores rellenan el mismo campo, gana el primero. `derived` va siempre el último.
- `assemble.py` combina el staging de cada parte con el esquema del diccionario en `dataset/<tabla>/<ISO>-pNN.parquet` (semanal: `dataset/sites_weekly/year=AAAA/<ISO>-pNN-<año>.parquet`); `report.py` da la cobertura; `export.py` el Excel de ejemplo.
- `hv.py`: H/V con Konno-Ohmachi y criterios SESAME, PSD frente a Peterson. Probado con señales sintéticas.

## Escala
- Por defecto se usan **todas las celdas** (`sampling.n_cells: all`). Las fuentes se descargan por rejilla, por país o por tesela (E-OBS, gridMET, NASA POWER, FIRMS por país, EMSC, DEM por tesela de 1°), nunca por celda, para que el coste no dependa del número de celdas.
- Colectores celda a celda solo con `run_by_default = False` (p. ej. `openmeteo`).
- Una parte de 25.000 celdas son ~9 millones de filas diarias por año en `assemble`: evitar `astype(object)` y operaciones columna a columna sobre el índice completo. Más celdas por parte puede agotar los 32 GB del portátil.
- Overpass no puede con EEUU entero ni va fino con Japón: OSM está en `skip_collectors` de esos países (se lanza aparte con `--only osm`).

## Estado (9 nov 2026, tarde)
- Rejilla pasada a 3,5 km y tres países: España (41.296 celdas), Japón (30.779) y EEUU continental (~640.000). Clima: E-OBS / NASA POWER / gridMET, con los mismos campos calculados por `eobs.daily_fields`.
- DEM por tesela de 1° leída a ~60 m (`DEM_FACTOR = 2`): cuadra con el método anterior celda a celda (elevación r = 1,00; pendiente r = 0,998).

## Estado (9 nov 2026, mañana)
- Validados con datos reales de 2025: rejilla, PeeringDB, hubs, OurAirports, cables, costa, DEM, terremotos, OMIE/REE/BCE, Banco Mundial (códigos WGI nuevos `GOV_WGI_*.EST`), Open-Meteo, E-OBS (cuadra con ERA5: lluvia 1.325 frente a 1.324 mm en San Sebastián) y FIRMS por país.
- E-OBS: el archivo anual provisional trae la radiación (qq) con meses de retraso; si una variable cubre menos del 90 % del año se usa el bloque consolidado o se deja vacía.
- Pendiente: OSM (Overpass lento; descarga por teselas), sísmica H/V con estaciones reales, SoilGrids (certificado en GDAL), confirmar columna España/Portugal de OMIE, colector ERA5-Land por rejilla (cuando haya clave CDS), colectores de `collectors/pending.py` y control de calidad.
