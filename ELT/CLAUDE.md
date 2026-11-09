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
python -m dclake grid
python -m dclake collect --only <nombre> --limit-sites 3   (o --sites id1,id2)
python -m dclake collect [--skip a,b] [--start AAAA-MM-DD --end AAAA-MM-DD]
python -m dclake assemble                   # dataset en ELT/dataset/ (+ .cache/reports/coverage.csv)
python -m dclake export --sites a,b,c --out x.xlsx   # solo si lo piden
```

## Arquitectura
- `grid.py`: rejilla 5x5 km en EPSG:3035 sobre geoBoundaries y muestra estratificada (`site_id = ESP_<x/5000>_<y/5000>`).
- `collectors/*.py`: cada uno escribe en `<lake>/staging/<colector>/<tabla>.parquet` (las diarias por año). Orden en `collectors/__init__.py`: si dos colectores rellenan el mismo campo, gana el primero (`era5land` antes que `openmeteo`). `derived` va siempre el último.
- `assemble.py` combina el staging en `<lake>/tables/` con el esquema del diccionario y escribe `field_lineage`; `report.py` da la cobertura; `export.py` el Excel de ejemplo.
- `hv.py`: H/V con Konno-Ohmachi y criterios SESAME, PSD frente a Peterson. Probado con señales sintéticas.

## Escala
- Por defecto se usan **todas las celdas** (`sampling.n_cells: all`). Las fuentes diarias se descargan por rejilla o por país (E-OBS, FIRMS por país, EMSC, OMIE/REE), nunca por celda, para que el coste no dependa del número de celdas.
- Colectores celda a celda solo con `run_by_default = False` (p. ej. `openmeteo`).
- `assemble` trabaja con ~7,4 millones de filas por año en `sites_daily`: evitar `astype(object)` y operaciones columna a columna sobre el índice completo.

## Estado (9 nov 2026)
- Validados con datos reales de 2025: rejilla, PeeringDB, hubs, OurAirports, cables, costa, DEM, terremotos, OMIE/REE/BCE, Banco Mundial (códigos WGI nuevos `GOV_WGI_*.EST`), Open-Meteo, E-OBS (cuadra con ERA5: lluvia 1.325 frente a 1.324 mm en San Sebastián) y FIRMS por país.
- E-OBS: el archivo anual provisional trae la radiación (qq) con meses de retraso; si una variable cubre menos del 90 % del año se usa el bloque consolidado o se deja vacía.
- Pendiente: OSM (Overpass lento; descarga por teselas), sísmica H/V con estaciones reales, SoilGrids (certificado en GDAL), confirmar columna España/Portugal de OMIE, colector ERA5-Land por rejilla (cuando haya clave CDS), colectores de `collectors/pending.py` y control de calidad.
