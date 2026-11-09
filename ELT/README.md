# ELT: data lake de viabilidad de data centers

Descarga datos públicos de España en una rejilla de 5×5 km y los deja en tablas Parquet **con exactamente las columnas del diccionario** (`data_dictionary/diccionario_datos_datacenters.xlsx`). De aquí sale el dataset para entrenar el modelo.

- Rejilla de **20.236 celdas** (EPSG:3035), todas por defecto. `sample_type` marca las 58 con data center conocido (`positivo_dc`), las de Madrid y Aragón (`foco_region`) y el `resto`. Con `DCLAKE_N_CELLS=500` se vuelve a la muestra estratificada.
- Periodo configurable: empezamos con 2025 y luego ampliamos a 20 años (nov 2006 – oct 2026).
- Las fuentes diarias se descargan **por rejilla o por país, no por celda**: el coste no crece con el número de celdas. El clima viene de E-OBS (observaciones, 0,1°) y los incendios de los archivos anuales de FIRMS, sin clave en ambos casos.

| Tabla | Filas con 2025 | Filas con 20 años |
|---|---|---|
| `sites_static` | 20.236 | 20.236 |
| `sites_yearly` | 20.236 | ~425.000 |
| `sites_weekly` | ~1,07 millones (23 MB) | ~21 millones (~0,5 GB) |

Las variables diarias (clima, terremotos, incendios) se calculan por día y se cargan **agregadas por semana ISO**. La regla de cada campo está en la hoja *Variables semanales* del diccionario: media, máximo, suma o número de días.

## Instalación (una vez)

Desde esta carpeta (`ELT/`), en Windows:

```
py -3 -m venv %USERPROFILE%\.venvs\dclake
%USERPROFILE%\.venvs\dclake\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
python -m pytest -q tests
```

En `.env` puedes poner `DCLAKE_START` y `DCLAKE_END` para limitar el periodo. Las claves son opcionales: el colector que no tenga la suya se salta.

| Clave | Para qué | Dónde se pide |
|---|---|---|
| `CDSAPI_KEY` | ERA5-Land horario: añade nieve, humedad del suelo y viento máximo, que E-OBS no trae | cds.climate.copernicus.eu (acepta la licencia del dataset *ERA5-Land hourly time-series*) |
| `FIRMS_MAP_KEY` | Incendios del año en curso (los años cerrados se descargan sin clave) | firms.modaps.eosdis.nasa.gov/api/map_key |

`openmeteo` (ERA5 celda a celda, sin clave) solo se ejecuta si se pide con `--only openmeteo`: sirve para pruebas con pocas celdas, porque su plan gratuito da para ~380 celdas-año al día.

## Uso

Siempre desde `ELT/` y con el entorno activado:

```
python -m dclake grid                                  # rejilla y muestra de 500 celdas
python -m dclake collect --only openmeteo --limit-sites 3   # probar un colector con 3 celdas
python -m dclake collect                               # todos los colectores (reanudable)
python -m dclake assemble                              # escribe el dataset en ELT/dataset/
python -m dclake upload                                # lo sube a Azure Data Lake (AZURE_* en .env)
python -m dclake status                                # claves y capas manuales que faltan
```

Las descargas e intermedios se guardan en `ELT/.cache/` (no se versiona): si algo se corta, se vuelve a lanzar el mismo comando y continúa donde lo dejó.

## El dataset (`ELT/dataset/`)

| Tabla | Una fila por | Se une por |
|---|---|---|
| `sites_static.parquet` | celda | `site_id` |
| `sites_yearly.parquet` | celda × año | `site_id`, `year` |
| `sites_weekly/year=AAAA/` | celda × semana ISO (año ISO de la semana) | `site_id`, `week_start` |
| `country_daily.parquet` | país × día (precio OMIE, mix REE, EUR/USD) | `country_iso3`, `date` |
| `country_context.parquet` | país × año (8 países) | `country_iso3`, `year` |
| `stations.parquet` / `signal_features.parquet` | estación sísmica / grabación analizada | `station_id`; `nearest_station_id` en `sites_static` |
| `field_lineage.parquet` | campo: fuente, licencia, si es modelo o proxy | `table`, `field` |

`field_lineage` incluye el porcentaje de cobertura de cada campo.

## Código

- `dclake/collectors/`: un archivo por fuente. Cada colector declara qué campos del diccionario rellena.
- `dclake/grid.py`: rejilla y muestra. `assemble.py`: une todo según el diccionario. `hv.py`: método H/V sísmico.
- Para añadir campos se edita `data_dictionary/build_dict.py` y se regenera el xlsx (`python build_dict.py` dentro de esa carpeta).

## Limitaciones

- El H/V de cada celda viene de la estación sísmica más cercana: es un indicador regional, no una medida de la parcela.
- PUE, WUE e intensidad de carbono salen de modelos simplificados; lo indica `field_lineage`.
- GEM y UICN tienen licencia no comercial: valen para el hackathon, no para un producto.
