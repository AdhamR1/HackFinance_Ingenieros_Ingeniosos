# CLAUDE.md: contexto de ETL para Claude Code

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
- **Todo dentro del repo y sin archivos basura.** La única salida es el dataset en `ETL/dataset/`. Descargas, staging, logs, informes y demo van en `ETL/.cache/` (ignorada en git). Nunca escribir fuera del repo ni generar Excel o informes que no se hayan pedido. Los archivos grandes intermedios (E-OBS de toda Europa) se descargan en temporal y solo se guarda el recorte de España.
- Código y comentarios en inglés; documentación, logs y mensajes al usuario en español.
- **PEP 8 con ruff** (configuración en `pyproject.toml` de la raíz, líneas de 99): antes de dar algo por
  terminado, `python -m ruff format .`, `python -m ruff check .` y `python -m pytest` desde la raíz. La CI de
  GitHub (`.github/workflows/ci.yml`) comprueba lo mismo. `build_dict.py` no se formatea (es una tabla).

## Comandos (desde ETL/, con `%USERPROFILE%\.venvs\dclake` activado)
```
python -m pytest -q tests
python -m dclake demo                       # offline, datos sintéticos
python -m dclake grid --country ESP|JPN|USA
python -m dclake collect --country JPN --only <nombre> --limit-sites 3   (o --sites id1,id2)
python -m dclake collect --country JPN [--skip a,b] [--part N] [--start AAAA-MM-DD --end AAAA-MM-DD]
python -m dclake assemble --country JPN     # dataset en ETL/dataset/ (+ .cache/JPN/reports/coverage.csv)
python -m dclake export --sites a,b,c --out x.xlsx   # solo si lo piden
python -m dclake qc --country JPN           # control de calidad -> .cache/JPN/reports/qc.csv
python -m dclake assemble --country JPN --static-only   # sin rehacer la tabla semanal
python -m dclake transcribe | excerpts --only <id> | cite   # audio público -> citas verificadas
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

## Estado (11 nov 2026): estructura ETL / Modelo / Web, Azure y Japón
- El repositorio tiene tres carpetas: `ETL/` (esta, antes `ELT/`), `Modelo/` (antes `pipeline/`) y `Web/` (antes `pagina/`).
- Data lake en Azure: `python -m dclake azure-setup` (login en el navegador; guarda cuenta, contenedor y un token SAS
  en `.env` sin mostrarlos) y `python -m dclake upload` (incremental; sube `dataset/` y `azure.extra_dirs`,
  hoy `../Modelo/data/processed`). Cuenta `stdclake`, contenedor `dclake`, región Spain Central.
- El modelo y la web cubren España y Japón: en `Modelo/` el país se elige con `DC_COUNTRY` (ver su README).

## Estado (10 nov 2026, noche): datos no estructurados (audio)
- `speech.py` + `collectors/speech.py`: 89 grabaciones públicas (39 h) transcritas con ElevenLabs Scribe v2 por
  `source_url` (ElevenLabs lee la URL; si el servidor del audio lo rechaza, p. ej. iVoox, se envía el archivo
  y no se guarda copia). Transcripciones en `.cache/audio/transcripts/` (no van a git).
- `audio/claims.csv` (245 citas) lo escribe Claude leyendo `python -m dclake excerpts`; **toda cita debe ser
  literal**: `python -m dclake cite` la busca palabra por palabra (sin tildes ni puntuación, pero con las
  muletillas «eh») y calcula segundo y hablante. `tests/test_speech.py` falla si hay una cita sin verificar.
- Tabla nueva del diccionario `audio_evidence` (aprobada por el usuario): un solo archivo, igual desde
  cualquier país; un ensamblado sin citas no lo vacía.
- Los campos que rellena (regulación, oposición, red) son dispersos y por zona: en `Modelo/src/features.py`
  están en `LEAKAGE` a propósito. No sacarlos de ahí sin revisar la fuga de la target.
- `assemble --static-only`: rehace todo menos `sites_weekly` (España 10 s en vez de 40 min) y conserva el
  linaje semanal del dataset. Usarlo siempre que el cambio no toque datos diarios.
- El SDK de ElevenLabs lee la clave al importarse: `.env` se carga después, por eso `speech._client` se la pasa.
- No abrir ni imprimir `ETL/.env`; `elevenlabs onboard check` comprueba la clave.
- Heredocs largos en bash se corrompen aquí (pierden `\n`): los parches se escriben con Write y se ejecutan.

## Estado (9 nov 2026, noche)
- España con datos semanales 2010–2025 (34,5 M filas, ~600 MB). Capas automáticas (`auto` en `manual_layers` de
  config.yaml, código en `autolayers.py`): WDPA y Natura 2000, GEM (PGA 475 años y fallas), JRC (calado 10/100/500
  años), GHSL (población 1/10/50 km, recorte de 1 km del mapa mundial). Suelos de SoilGrids por su WCS
  (`soilgrids_tiles` en `rasters.py`): el `/vsicurl` de GDAL falla con la inspección TLS, `requests` no.
- OMIE solo publica desde 2018 (zips anuales 2018–2022, diarios desde 2023); REE desde 2011.
- `assemble` escribe en `.cache/<ISO>/assemble_tmp` y solo al final sustituye los archivos del país en el dataset:
  si se corta (sesión cerrada, suspensión), el dataset conserva la versión anterior en vez de quedar a medias.
- Una capa de `manual_layers` con `table: sites_yearly` (y `year`) va a la tabla anual: la población (GHSL 2025)
  está en `sites_yearly` en el diccionario. `test_collectors_declare_fields_in_their_dictionary_table` impide que un
  campo se declare en otra tabla (conform lo descartaría sin avisar).
- `python -m dclake qc --country X`: control de calidad (claves, rangos, coherencia) en `.cache/X/reports/qc.csv`.
- Cobertura (10 nov): España 114 campos MVP, EEUU 98, Japón 67. QC sin fallos salvo ~0,05 % de celdas donde el
  calado JRC no crece con el periodo de retorno (viene así en los mapas del JRC).
- H/V sísmico funcionando (España 94 % de las celdas con f0; EEUU 82 %, 2.328 estaciones). Tres causas arregladas:
  (1) el cliente de enrutado de EIDA de obspy solo acepta argumentos con nombre y el fallo quedaba oculto en
  debug (ahora es un aviso por estación); (2) se asignaban estaciones ya cerradas (ahora solo las que registran en
  el periodo); (3) la red ES del IGN no llega por EIDA: `seismic.waveform_clients` la pide directa al IGN.
  Cada celda toma la estación más cercana que sí dio H/V (hasta `max_station_km`). Estaciones en paralelo (6).
- Población (GHSL): `_zonal_sum` hace una convolución de disco con FFT (segundos para 640.000 celdas).
- Japón: temperaturas de NASA POWER corregidas por altitud (-6,5 °C/km frente a la altitud del modelo, deducida
  de su presión en superficie); el sesgo en ciudades baja de ~2 °C a ~0,5 °C.
- Zonas inundables oficiales (SNCZI) y parques nacionales están en `Modelo/src/feat_riesgos.py` (zips del SNCZI
  bajados a mano: MITECO pide verificación en el navegador; no automatizarla).

## Estado (9 nov 2026, tarde)
- Rejilla pasada a 3,5 km y tres países: España (41.296 celdas), Japón (30.779) y EEUU continental (~640.000). Clima: E-OBS / NASA POWER / gridMET, con los mismos campos calculados por `eobs.daily_fields`.
- DEM por tesela de 1° leída a ~60 m (`DEM_FACTOR = 2`): cuadra con el método anterior celda a celda (elevación r = 1,00; pendiente r = 0,998). Una tesela solo se da por mar si el servidor dice que no existe (HEAD 403/404); un fallo de red no se cachea.
- EMSC no es igual de completo en todos los países (ESP desde M1,5; USA ~M2; JPN ~M3). Desde el 10 nov el conteo
  usa un umbral común M≥2 (`earthquakes.count_min_magnitude`; la descarga sigue desde M1,5); en Japón sigue
  infravalorado y el linaje lo anota.
- PGA del IGN (475 años): `Modelo/src/feat_riesgos.py` interpola las isolíneas públicas del visor de terremotos del
  IGN (`pga475_ign_g`, r = 0,91 con la PGA de GEM).
- Dataset de 2025: ESP 45 MB, JPN 12 MB, USA 1,25 GB. ESP y JPN están en git; los archivos de EEUU se ignoran en `.gitignore` (van al data lake).

## Estado (9 nov 2026, mañana)
- Validados con datos reales de 2025: rejilla, PeeringDB, hubs, OurAirports, cables, costa, DEM, terremotos, OMIE/REE/BCE, Banco Mundial (códigos WGI nuevos `GOV_WGI_*.EST`), Open-Meteo, E-OBS (cuadra con ERA5: lluvia 1.325 frente a 1.324 mm en San Sebastián) y FIRMS por país.
- E-OBS: el archivo anual provisional trae la radiación (qq) con meses de retraso; si una variable cubre menos del 90 % del año se usa el bloque consolidado o se deja vacía.
- Pendiente: OSM (Overpass lento; descarga por teselas), sísmica H/V con estaciones reales, SoilGrids (certificado en GDAL), confirmar columna España/Portugal de OMIE, colector ERA5-Land por rejilla (cuando haya clave CDS), colectores de `collectors/pending.py` y control de calidad.
