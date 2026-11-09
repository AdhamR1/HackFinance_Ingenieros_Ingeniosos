# ELT: data lake de viabilidad de data centers

Descarga datos públicos en una rejilla de **3,5 × 3,5 km** (12,25 km² por celda) para España, Japón y EEUU continental, y los deja en tablas Parquet **con exactamente las columnas del diccionario** (`data_dictionary/diccionario_datos_datacenters.xlsx`). De aquí sale el dataset para entrenar el modelo.

| País | Celdas | Proyección (igual área) | Clima diario (sin clave) |
|---|---|---|---|
| España (`ESP`) | 41.296 | EPSG:3035 (LAEA Europa) | E-OBS 0,1° (observaciones) |
| Japón (`JPN`) | 30.779 | LAEA centrada en Japón | NASA POWER 0,5° (reanálisis MERRA-2) |
| EEUU (`USA`, 48 estados + DC) | ~640.000 | EPSG:5070 (Conus Albers) | gridMET 4 km |

- Cada país se procesa por separado (`--country`) con su perfil en `config.yaml` (`country_profiles`). Los países grandes van por **partes** (franjas de ≤25.000 celdas) para no agotar la memoria.
- `sample_type` marca las celdas con data center conocido (`positivo_dc`), las de las regiones foco (`foco_region`: Madrid y Aragón; Tokio y Osaka; Virginia, Texas y Arizona) y el `resto`.
- Periodo configurable: ahora 2025; después, 20 años (nov 2006 – oct 2026).
- Las fuentes se descargan **por rejilla, por país o por tesela, nunca por celda**: el coste apenas crece con el número de celdas.

La tabla grande es `sites_weekly`:

| | 1 año | 20 años |
|---|---|---|
| España | 2,2 M filas (~50 MB) | ~43 M (~1 GB) |
| Japón | 1,6 M (~35 MB) | ~32 M (~0,7 GB) |
| EEUU | ~34 M (~0,75 GB) | ~670 M (~15 GB) |

Los tres países con 20 años ocupan unos 17 GB: caben de sobra en un data lake de 2 TB.

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

En `.env` puedes poner `DCLAKE_START` y `DCLAKE_END` para limitar el periodo y `DCLAKE_COUNTRY` para el país por defecto. Las claves son opcionales: el colector que no tenga la suya se salta.

| Clave | Para qué | Dónde se pide |
|---|---|---|
| `CDSAPI_KEY` | ERA5-Land horario: añade nieve, humedad del suelo y viento máximo | cds.climate.copernicus.eu (acepta la licencia del dataset *ERA5-Land hourly time-series*) |
| `FIRMS_MAP_KEY` | Incendios del año en curso (los años cerrados se descargan sin clave) | firms.modaps.eosdis.nasa.gov/api/map_key |

## Uso

Siempre desde `ELT/` y con el entorno activado:

```
python -m dclake grid --country JPN          # rejilla del país (ESP si no se indica)
python -m dclake collect --country JPN       # todos los colectores, parte a parte (reanudable)
python -m dclake assemble --country JPN      # escribe el país en ELT/dataset/
python -m dclake upload                      # sube ELT/dataset/ a Azure Data Lake (AZURE_* en .env)
python -m dclake status --country JPN        # claves y capas manuales que faltan
python -m dclake collect --country ESP --only eobs --limit-sites 3   # probar un colector con 3 celdas
```

`--part N` procesa solo una parte del país. Las descargas e intermedios se guardan en `ELT/.cache/<país>/` (no se versiona): si algo se corta, se vuelve a lanzar el mismo comando y continúa donde lo dejó.

## El dataset (`ELT/dataset/`)

Una carpeta por tabla y un archivo por país (y parte): los países se suman sin tocar nada.

| Tabla | Archivos | Una fila por | Se une por |
|---|---|---|---|
| `sites_static/` | `ESP-p00.parquet`, `JPN-p00.parquet`… | celda | `site_id` |
| `sites_yearly/` | igual | celda × año | `site_id`, `year` |
| `sites_weekly/year=AAAA/` | `ESP-p00-2025.parquet`… | celda × semana ISO (año ISO de la semana) | `site_id`, `week_start` |
| `country_daily/` | `ESP.parquet` | país × día: precio OMIE, mix REE, EUR/USD (solo España) | `country_iso3`, `date` |
| `country_context.parquet` | uno | país × año (8 países) | `country_iso3`, `year` |
| `stations/`, `signal_features/` | `ESP.parquet` | estación sísmica / grabación analizada | `station_id` |
| `field_lineage/` | `ESP-p00.parquet` | campo: fuente, licencia, cobertura, si es modelo o proxy | `table`, `field` |

`site_id` empieza por el país (`ESP_…`, `JPN_…`, `USA_…`). Para leer una tabla entera: `pd.read_parquet("dataset/sites_static")`, o en DuckDB `read_parquet('dataset/sites_weekly/*/*.parquet', hive_partitioning = true)`.

## Código

- `dclake/collectors/`: un archivo por fuente. Cada colector declara qué campos del diccionario rellena y, si solo vale para algunos países, `countries` o `climate_key`.
- `dclake/grid.py`: rejilla y etiquetas. `assemble.py`: une todo según el diccionario. `hv.py`: método H/V sísmico.
- Para añadir un país: un perfil más en `country_profiles` (proyección, cajas, fuente de clima, vecinos).
- Para añadir campos se edita `data_dictionary/build_dict.py` y se regenera el xlsx (`python build_dict.py` dentro de esa carpeta).

## Limitaciones

- El clima de Japón viene de un reanálisis de 0,5° (~50 km): es regional, no local. España (11 km) y EEUU (4 km) van con más detalle.
- EEUU es solo el territorio continental (48 estados + DC): Alaska, Hawái y los territorios se pueden añadir en `adm1_exclude`.
- OSM (red eléctrica, carreteras, etc.) y el mercado eléctrico diario solo están para España; en Japón y EEUU esos campos quedan vacíos de momento.
- La pendiente y la rugosidad salen del DEM Copernicus leído a ~60 m, igual en todos los países.
- El conteo semanal de terremotos (`eq_count_100km`) depende de lo que el catálogo EMSC recoge en cada país: España desde M1,5, EEUU desde ~M2 y Japón desde ~M3. No es comparable entre países sin un umbral común; los campos históricos M≥4 de USGS sí lo son.
- El H/V de cada celda viene de la estación sísmica más cercana: es un indicador regional, no una medida de la parcela.
- PUE, WUE e intensidad de carbono salen de modelos simplificados; lo indica `field_lineage`.
- GEM y UICN tienen licencia no comercial: valen para el hackathon, no para un producto. E-OBS también es de uso no comercial.
