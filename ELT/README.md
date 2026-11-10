# ELT: data lake de viabilidad de data centers

Descarga datos públicos en una rejilla de **3,5 × 3,5 km** (12,25 km² por celda) para España, Japón y EEUU continental, y los deja en tablas Parquet **con exactamente las columnas del diccionario** (`data_dictionary/diccionario_datos_datacenters.xlsx`). De aquí sale el dataset para entrenar el modelo.

| País | Celdas | Proyección (igual área) | Clima diario (sin clave) |
|---|---|---|---|
| España (`ESP`) | 41.296 | EPSG:3035 (LAEA Europa) | E-OBS 0,1° (observaciones) |
| Japón (`JPN`) | 30.779 | LAEA centrada en Japón | NASA POWER 0,5° (reanálisis MERRA-2) |
| EEUU (`USA`, 48 estados + DC) | 636.890 | EPSG:5070 (Conus Albers) | gridMET 4 km |

- Cada país se procesa por separado (`--country`) con su perfil en `config.yaml` (`country_profiles`). Los países grandes van por **partes** (franjas de ≤25.000 celdas) para no agotar la memoria.
- `sample_type` marca las celdas con data center conocido (`positivo_dc`), las de las regiones foco (`foco_region`: Madrid y Aragón; Tokio y Osaka; Virginia, Texas y Arizona) y el `resto`.
- Periodo por país (`period` en su perfil): **España 2010–2025**; Japón y EEUU, 2025 de momento.
- Capas de referencia que se descargan solas (`auto` en `manual_layers`): espacios protegidos y Red Natura 2000 (WDPA), peligrosidad sísmica (GEM, PGA de 475 años), fallas activas (GEM), calado de inundación de 10, 100 y 500 años (JRC), población a 1, 10 y 50 km (GHSL, 1 km). Los suelos (arcilla, arena, densidad, tipo WRB) salen del servicio WCS de SoilGrids. Red eléctrica y carreteras salen de OpenStreetMap.
- Las fuentes se descargan **por rejilla, por país o por tesela, nunca por celda**: el coste apenas crece con el número de celdas.

Tamaño medido con 2025 (la tabla grande es `sites_weekly`) y estimado para 20 años:

| | Filas semanales (1 año) | Disco (1 año) | Disco (20 años) |
|---|---|---|---|
| España | 2,2 M | 45 MB | ~0,8 GB |
| Japón | 1,6 M | 12 MB | ~0,2 GB |
| EEUU | 33,8 M | 1,25 GB | ~22 GB |

España ya está con 2010–2025: 34,5 M filas semanales (~600 MB). Los tres países con 20 años ocupan unos 23 GB: caben de sobra en un data lake de 2 TB. EEUU es demasiado grande para git: se comparte por el data lake (`python -m dclake upload`).

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
python -m dclake qc --country JPN            # control de calidad: claves, rangos y coherencia
python -m dclake collect --country ESP --only eobs --limit-sites 3   # probar un colector con 3 celdas
python -m dclake assemble --country ESP --static-only   # todo menos la tabla semanal (segundos, no 40 min)
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
| `audio_evidence.parquet` | uno | cita literal de una grabación pública, con su segundo, hablante y enlace | `evidence_id` |
| `field_lineage/` | `ESP-p00.parquet` | campo: fuente, licencia, cobertura, si es modelo o proxy | `table`, `field` |

`site_id` empieza por el país (`ESP_…`, `JPN_…`, `USA_…`). Para leer una tabla entera: `pd.read_parquet("dataset/sites_static")`, o en DuckDB `read_parquet('dataset/sites_weekly/*/*.parquet', hive_partitioning = true)`.

## Datos no estructurados: audio público

Lo que no está en ninguna base de datos (moratorias, oposición vecinal, plazos de permisos, saturación de
la red, criterios de quien elige emplazamientos) se dice en pódcast, radios y sesiones públicas.

```
python -m dclake transcribe                  # audio del catálogo -> texto (ElevenLabs Scribe v2), a la caché
python -m dclake excerpts --only <id>        # pasajes de una transcripción para leer antes de citar
python -m dclake cite                        # comprueba cada cita contra su transcripción
python -m dclake collect --country ESP --only speech
python -m dclake assemble --country ESP --static-only
```

- `audio/sources.csv`: catálogo de grabaciones (89, 39 h; pódcast y radios con audio público). ElevenLabs lee
  el audio desde su URL; aquí no se guarda audio. Hace falta `ELEVENLABS_API_KEY` en `.env` solo para `transcribe`.
- `audio/claims.csv`: citas literales (245) con lugar, tema, campo al que apoyan y confianza. Las lee una
  persona o un LLM en las transcripciones; `cite` localiza cada cita palabra por palabra y calcula el segundo
  y el hablante. Una cita que no está en la transcripción no entra en el dataset.
- El colector `speech` lleva todas las citas a `audio_evidence.parquet` y, con ellas, rellena
  `moratorium_flag`, `local_opposition_index`, `permitting_months`, `grid_congestion_flag`,
  `grid_connection_wait_months`, `water_restriction_flag`, `dc_tax_incentive_flag` (celdas del lugar citado) y
  `dc_market_size_mw`, `dc_pipeline_mw` (país). Reglas en `config.yaml > speech`: confianza mínima, y dos
  grabaciones (o una cita muy clara) para dar un valor a toda una región.
- Estos campos solo tienen valor donde ya se habla de proyectos: sirven para avisos e informes, **no como
  variables del modelo** (`pipeline/src/features.py` los excluye). Lo que sí va al modelo son los criterios
  de expertos (`pipeline/src/priors_voz.py`).

## Código

- `dclake/collectors/`: un archivo por fuente. Cada colector declara qué campos del diccionario rellena y, si solo vale para algunos países, `countries` o `climate_key`.
- `dclake/speech.py`: audio a texto y verificación de citas. `collectors/speech.py`: citas -> campos.
- `dclake/grid.py`: rejilla y etiquetas. `assemble.py`: une todo según el diccionario. `hv.py`: método H/V sísmico.
- Para añadir un país: un perfil más en `country_profiles` (proyección, cajas, fuente de clima, vecinos).
- Para añadir campos se edita `data_dictionary/build_dict.py` y se regenera el xlsx (`python build_dict.py` dentro de esa carpeta).

## Limitaciones

- El clima de Japón viene de un reanálisis de 0,5° (~50 km): es regional, no local. España (11 km) y EEUU (4 km) van con más detalle.
- EEUU es solo el territorio continental (48 estados + DC): Alaska, Hawái y los territorios se pueden añadir en `adm1_exclude`.
- OSM (red eléctrica, carreteras, etc.) y el mercado eléctrico diario solo están para España; en Japón y EEUU esos campos quedan vacíos de momento. `DCLAKE_OSM_LAYERS=substations,power_lines,…` limita OSM a unas capas.
- Zona inundable oficial (`in_official_flood_zone`, SNCZI): MITECO pide aceptar condiciones en la web, así que hay que bajar a mano `laminasPB-q100.zip` y `laminasCanarias-q100.zip` (miteco.gob.es → Cartografía y SIG → Descargas → Zonas inundables). El calado de inundación de JRC sí se descarga solo.
- Inundación y peligrosidad sísmica se miden en el centro de la celda: indican el riesgo del emplazamiento tipo de la celda, no de toda su superficie.
- La pendiente y la rugosidad salen del DEM Copernicus leído a ~60 m, igual en todos los países.
- El conteo semanal de terremotos (`eq_count_100km`) depende de lo que el catálogo EMSC recoge en cada país: España desde M1,5, EEUU desde ~M2 y Japón desde ~M3. No es comparable entre países sin un umbral común; los campos históricos M≥4 de USGS sí lo son.
- El H/V (frecuencia f0 y amplitud del terreno) se calcula con ruido sísmico real de las estaciones de IGN y EIDA: 2 días x 2 ventanas de 1 h del último año por estación (`seismic` en config.yaml). Cada celda hereda el de su estación más cercana: es un indicador regional, no una medida de la parcela.
- PUE, WUE e intensidad de carbono salen de modelos simplificados; lo indica `field_lineage`.
- GEM y UICN tienen licencia no comercial: valen para el hackathon, no para un producto. E-OBS también es de uso no comercial.
