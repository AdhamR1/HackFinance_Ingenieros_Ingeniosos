> **HISTÓRICO (9-nov-2026).** Análisis hecho con los datos de entonces, cuando muchas capas estaban vacías. Con los datos del 10-nov algunas conclusiones han cambiado: ver `CAMBIOS.md` y `metricas.json`. Los scripts citados aquí (`analisis.py`, `auditoria.py`) se han sustituido.

# INFORME — modelo y rúbrica (Ángel)

Rama `angel/modelo`, creada a partir de `origin/main` @ `83c32ce` (9-nov-2026). Todo lo mío está en `angel_modelo/`. No he modificado ningún archivo existente, ni he hecho commit ni push.

Leyenda: **[visto]** = lo he leído en el código o en los datos · **[deduzco]** = inferencia mía · **[no lo sé]** = sin verificar.

---

## Fase 1 · Mapa del proyecto

### 0. Aviso previo: tu `main` local estaba desfasado
Tu `main` local estaba en `9279309` (8-nov): solo había un `dc_datalake.zip`, dos diccionarios xlsx y **ningún Parquet**. Al hacer `git fetch` aparecieron 15 commits nuevos en `origin/main` (9-nov) con el ELT descomprimido, el dataset en Parquet y un **pipeline de modelo ya hecho por Cristóbal**. He creado `angel/modelo` sobre `origin/main` (tu `main` local queda intacto). → **Supuesto S1.** Haz `git pull` en `main` cuando puedas.

### 1. Árbol (origin/main, sin los Parquet)
```
README.md                 índice: ELT/ y pipeline/
registros.py              vacío (0 bytes)
ELT/                      data lake (Adham + Dani)
  config.yaml, .env.example, requirements.txt, CLAUDE.md, README.md
  data_dictionary/        build_dict.py -> diccionario_datos_datacenters.xlsx
  dclake/                 grid, assemble, weekly, upload (Azure), hv (H/V sísmico)
    collectors/           osm, eobs, gridclimate, openmeteo, rasters, hazards, seismic,
                          electricity, country, peeringdb, transport, derived, pending
  dataset/                27 Parquet, 58 MB (ESP y JPN; USA excluido por .gitignore)
  tests/                  test_core.py, test_upload.py
pipeline/                 target + features + modelo (Cristóbal)
  src/  cells.py labels.py features.py feat_suelo.py train.py
  data/raw/dc_sites_es.csv          103 emplazamientos de datacentermap.com
  data/processed/                   labels, features, exclusions, feat_suelo, scores (+ informes)
```

### 2. Tabla de componentes
| Ruta | Qué hace | Entradas | Salidas | Dependencias | Estado |
|---|---|---|---|---|---|
| `ELT/dclake/grid.py` | Rejilla 3,5 km EPSG:3035 + `sample_type` | geoBoundaries, lista DC | celdas | geopandas, pyproj | completo [visto README] |
| `ELT/dclake/collectors/*` | Una fuente por archivo | APIs públicas | `.cache/` staging | requests, rasterio, obspy… | parcial (`pending.py` lista lo que falta) |
| `ELT/dclake/assemble.py`, `weekly.py` | Une por diccionario; diario→semana ISO (`weekly.py:30-45`) | staging | `ELT/dataset/*` | pandas, pyarrow | completo [visto] |
| `ELT/dclake/upload.py` | Sube `dataset/` a Azure ADLS Gen2 | `.env` AZURE_* | Azure | azure-* | completo, claves por `.env` [visto `upload.py:31-35`] |
| `pipeline/src/labels.py` | Target: celda con DC existente o anunciado | `dc_sites_es.csv` | `labels_es_3500.parquet` | scipy, pyproj | completo |
| `pipeline/src/features.py` | Variables numéricas, quita fuga/vacías/constantes | ELT static+yearly, `feat_*.parquet` | `features_es_3500.parquet` | pandas | completo |
| `pipeline/src/feat_suelo.py` | % Natura 2000, urbano, industrial, agua (CORINE) y exclusiones | EEA ArcGIS REST | `feat_suelo`, `exclusions_es_3500` | shapely 2, requests | completo; solo excluye “agua ≥ 90 %” (`feat_suelo.py:40`) |
| `pipeline/src/train.py` | LightGBM PU + CV espacial 70 km + SHAP | labels, features, exclusions | `scores_es_3500.parquet` (lo pinta la web) | lightgbm, shap | completo |
| `registros.py` | — | — | — | — | vacío |
| Web (Cloudflare) | — | `scores_es_3500.parquet` | — | — | **no está en el repo** |

### 3. Flujo de datos extremo a extremo
APIs públicas → `ELT/dclake collect` (caché `.cache/`) → `assemble` → `ELT/dataset/` (Parquet: `sites_static`, `sites_yearly`, `sites_weekly`…) → (`upload` → Azure) → `pipeline/labels.py` + `features.py` + `feat_suelo.py` → `train.py` → `scores_es_3500.parquet` (nota en percentil, banda, 3 razones SHAP) → web.

### 4. Instalación y ejecución [visto]
- ELT: `ELT/requirements.txt` (Python ≥ 3.11; venv + `pip install -r`), luego `python -m dclake grid|collect|assemble|upload` desde `ELT/`.
- Pipeline: desde `pipeline/`, `python src/labels.py && python src/features.py && python src/train.py [--exclusions …]`. **No hay `requirements.txt` del pipeline**: solo una lista en `pipeline/README.md` (lightgbm, shap…).

### 5. Lo que tú sabías frente a lo que hay
| Lo que sabías | Lo que hay | Fuente |
|---|---|---|
| Celdas de unos 12 km² (3,5 × 3,5) | ✔ 12,25 km², 41.296 celdas en España | `ELT/README.md`, `pipeline/src/cells.py:12` |
| Histórico semanal | ✔ `sites_weekly` (semana ISO), pero en git solo 2025-2026; además `sites_yearly` | `ELT/README.md`, `weekly.py` |
| Unos 100 parámetros finales | ✘ El diccionario tiene cientos de campos; al modelo entran **~28 variables** tras filtrar (`scores_es_3500_importance.csv`) | ver fase 2 |
| Parquet en Azure | ✔ `upload.py`; y además **todo ESP/JPN está en git** (58 MB) | `.gitignore` |
| Solo España | ✔ en pipeline; el ELT ya tiene Japón y EEUU | `ELT/README.md` |
| Muestra pequeña para experimentar | ✘ no es una muestra: es España entera (41.296 celdas) | fase 2 |
| Salida viable / no viable | ✘ hoy la salida es una **ordenación** (percentil + banda alta/media/baja/excluida), no binaria | `train.py:112-114` |
| XGBoost | ✘ el equipo usa **LightGBM** (misma familia) | `train.py:28` |
| Tú: modelo y rúbrica | ⚠ el modelo ya lo ha montado **Cristóbal** (commits `691f2cc`, `86b74e1`, `99a4b30`) | `git log` |
| Roles | Adham: ELT y datos (commits de datos). Dani (`dmar1400`): config, Azure upload, fixes. Cristóbal: pipeline y modelo. **Desi no aparece en git**. Web de Cloudflare: no está en el repo | `git log` |

### 6. README: qué dice y qué falta
Dice: estructura `ELT/` y `pipeline/`, cómo ejecutar, reglas anti-fuga. Falta: requirements del pipeline, enlace a la web, qué significa la nota para el usuario final (es un percentil, no una probabilidad), una sección de rúbrica y limitaciones del target, y la lista de 8 países debería decir que el MVP es solo España.

### 7. Riesgos
- **Claves:** no he encontrado ninguna versionada. `.env` está en `.gitignore`; `.env.example` tiene las variables vacías. ✔
- **Datos pesados en git:** 58 MB de Parquet versionados y regenerables; con 20 años España serían ~0,8 GB (`ELT/README.md`). Recomiendo dejar en git solo una muestra y el resto en Azure.
- **Rutas absolutas:** ninguna. ✔
- **Target débil:** validación espacial AUC 0,585 (frente a 0,834 aleatoria) → el modelo apenas generaliza fuera de las zonas de los DC conocidos (`scores_es_3500_cv_report.csv`).
- **Variables clave ausentes del modelo:** potencia o red eléctrica (`dist_substation_km`), fibra o latencia (quitadas por fuga), inundación oficial. El top de importancia es aeropuerto, pendiente y clima → ver fases 2 y 5.
- **Pipeline sin dependencias fijadas** (`lightgbm`, `shap`) y sin tests.

### 8. Diez líneas para el equipo
1. El repo tiene dos partes: `ELT/` (datos) y `pipeline/` (target, modelo, puntuación para la web).
2. Rejilla única 3,5 × 3,5 km (12,25 km²), 41.296 celdas en España, clave `site_id`.
3. El dataset está en Parquet en `ELT/dataset/` (58 MB en git) y se sube a Azure con `dclake upload`.
4. Hay tres tablas por celda: estática, anual y semanal (2025-2026 en git).
5. Target actual: 103 data centers reales (datacentermap) → aprendizaje PU (positivos frente a no etiquetados).
6. El modelo actual es LightGBM con validación espacial; la honesta da AUC 0,585: flojo.
7. Hoy solo se excluye “agua ≥ 90 %”; Natura 2000 y urbano son avisos.
8. Faltan en el modelo las variables que más deciden un DC: potencia de red, fibra e inundación.
9. Sin claves en el repo; sin rutas absolutas; el pipeline no tiene requirements.
10. Mi propuesta: rúbrica transparente + modelo PU como segunda opinión, decidida con exclusiones objetivas.

---

## Fase 2 · Auditoría de datos

Script: `angel_modelo/auditoria.py` (37 s). Esquemas completos (columna, tipo, unidad del diccionario, % nulos, únicos, min/p50/max) en `out/esquema_<tabla>.csv`; resumen en `out/resumen_auditoria.txt`; pares correlados en `out/correlaciones_altas.csv`.

**No es una “muestra pequeña”:** es España entera (41.296 celdas) y pesa poco (< 60 MB), así que no he muestreado. **[visto]**

### 1. Tablas (solo ESP)
| Tabla | Filas | Columnas | Con datos y variables | 100 % vacías | Constantes |
|---|---|---|---|---|---|
| `sites_static` | 41.296 (1 por celda, 0 duplicados) | 256 | **40** | 214 | 2 (`country_iso3`, `n_submarine_cables_country`) |
| `sites_yearly` | 41.296 (**solo 2025**) | 64 | 21 (todo clima) | 33 | 10 (precio, mix, PIB, paro…: valores de país repetidos) |
| `sites_weekly` | 2.188.688 (53 semanas, 30-dic-2024 → 29-dic-2025) | 31 | 24 | 6 | 1 (`extreme_cold_days`) |
| `feat_suelo` / `exclusions` (pipeline) | 41.296 | 8 | 4 % (Natura, urbano, industrial, agua) | 0 | — |
| `stations`, `signal_features` | **0 filas** | — | — | — | → **no hay H/V sísmico** |

Cobertura geográfica: lon −18,15…4,30, lat 27,65…43,76 (incluye Canarias y Baleares), 19 comunidades/ciudades autónomas, 52 provincias. Temporal: un solo año (2025). **[visto]**

### 2. Lo que hay de verdad (40 + 21 + 4 columnas útiles)
- **Terreno:** `elevation_m`, `slope_pct`, `aspect_deg`, `terrain_ruggedness`.
- **Sismicidad (catálogo):** `n_eq_m4_100km_50y`, `max_mag_100km_hist` (14,5 % nulos = sin sismo M≥4 en 100 km → debería ser 0 o “sin dato”, no NaN), `dist_m5_epicenter_km`.
- **Costa y cables:** `dist_coast_km`, `in_low_elevation_coastal_zone`, `dist_cable_landing_km`, `n_cables_nearest_landing`, `newest_cable_year`, `planned_cables_flag`.
- **Conectividad (con fuga, ver abajo):** `dist_ixp_km`, `n_ixp_100km`, `n_networks_at_ixp`, `n_colo_facilities_100km`, `n_networks_100km`, `n_carriers_nearest_colo`, latencias.
- **Aeropuerto:** `dist_airport_km`, `dist_airport_runway_km`, `in_flight_path_flag`.
- **Clima 2025 (yearly):** temperatura media y percentiles, grados-día, bulbo húmedo p99, punto de rocío, humedad, horas de free cooling y adiabático, `est_pue`, `est_wue_l_kwh`, olas de calor, noches tropicales, heladas, precipitación, viento, radiación.
- **Suelo (pipeline, CORINE 2018 + Natura 2000):** `natura2000_pct`, `urbano_pct`, `industrial_pct`, `agua_pct`.

### 3. Lo que falta y más importa (100 % vacío en `sites_static`) **[visto]**
Energía: `dist_substation_km`, `substation_voltage_kv`, `n_substations_20km`, `grid_capacity_available_mw`, `dist_power_plant_km`, `grid_congestion_flag`. · Riesgo: `pga_475y_g`, `dist_active_fault_km`, todas las `flood_*`, `in_official_flood_zone`, `water_stress*`. · Fibra: `dist_fiber_backbone_km`, `n_fiber_routes_20km`. · Accesos: `dist_highway_km`, `dist_primary_road_km`, `dist_railway_km`. · Regulación: `in_protected_area`, `dist_protected_area_km`, `zoning_class`. · Entorno: `n_buildings_1km`.
El `ELT/README.md` dice que WDPA, GEM (PGA) y JRC (inundación) se “descargan solos”, pero en el dataset versionado están vacíos. **[deduzco]** que la ejecución subida es anterior o que esos colectores fallaron; el commit `09f018b` “Completar datos 1/2” apunta a que falta la segunda parte. **Es el cuello de botella nº 1 del proyecto.**

### 4. Redundancias (|ρ Spearman| > 0,9): 29 pares
Los más claros (ρ ≈ 1): `free_cooling_hours`↔`est_pue`, `cooling_degree_days`↔`est_wue_l_kwh` (el PUE/WUE son **fórmulas** de esas variables, no datos nuevos), `dist_airport_km`↔`dist_airport_runway_km`, `slope_pct`↔`terrain_ruggedness` (0,999), `dist_major_hub_km`↔`latency_to_hub_ms`. Bloque térmico muy correlado entre sí: `mean_temp_c`, `heating_degree_days`, `free_cooling_hours`, `tropical_nights_year`, `frost_days_year` (0,90–0,98). `lat`↔`solar_ghi_kwh_m2` 0,945. `train.py:45-48` ya quita las de |ρ| > 0,95.

### 5. Valores imposibles
Ninguno físicamente imposible. Mi regla genérica marcó falsos positivos (años de cable, latencias en ms, horas) que he revisado a mano. Detalles plausibles: `elevation_m` mínimo −3,7 m (costa), `area_ha` 613–1.225 (celdas recortadas por costa o frontera). **[visto `out/valores_imposibles.csv`]**

### 6. Identificadores y coordenadas que NO deben entrar como variables
`site_id`, `h3_cell_r7`, `lat`, `lon`, `admin1`, `admin2`, `country_iso3`, `sample_type`, `is_datacenter`, `year`, `week_start`, y todas las distancias a puntos fijos (hub de Madrid, latencias a Frankfurt, Ashburn, Singapur o Tokio, que son coordenadas encubiertas). `pipeline/src/features.py:20-51` (`LEAKAGE`) ya las quita. ✔

### 7. Variable objetivo
- **Sí existe** y no es circular respecto a las variables: `pipeline/src/labels.py` marca `y=1` en las celdas con data center existente o anunciado según `data/raw/dc_sites_es.csv` (103 emplazamientos de datacentermap.com geocodificados a mano). Resultado: **100 celdas positivas (0,24 %)**, 77 operativas. **[visto]**
- En el ELT hay **otra** marca: `is_datacenter` / `sample_type = positivo_dc` en **63 celdas**. **Solo 21 celdas coinciden con `y`**: 42 celdas “positivo_dc” del ELT no tienen DC según el pipeline, y 79 del pipeline no lo están en el ELT. **[visto, cruce en `resumen_auditoria.txt`]** Hay que decidir cuál es la lista oficial (la del pipeline está documentada con precisión por punto, así que propongo esa) y avisar a Adham.
- `viability_score`, `dc_status`, `capacity_mw`: 100 % vacíos (no hay etiqueta “viable” en el dataset).

### 8. Conclusión de la fase 2
Con el dataset actual, el modelo solo puede aprender **terreno + clima + aeropuerto + costa**. Lo que decide de verdad dónde va un data center (potencia de red, fibra, suelo industrial, riesgos) no está o está como fuga. Por eso el AUC espacial es 0,585.

---

## Fase 3 · Target

### Evidencia [visto, consulta sobre `labels_es_3500` + `exclusions_es_3500` + `sites_static`]
- 103 emplazamientos → 100 celdas positivas en 37 provincias; Madrid 22, Barcelona 14, Zaragoza 14, Valencia 5, Baleares 4. 78 operativos y 25 planificados.
- Precisión del punto (`dc_sites_es.csv`): `district_approx` 21, `municipio` 50, `metro` 32 → **~80 % puede caer en la celda equivocada** (la celda mide 3,5 km y el centro de un municipio puede estar a varios km del DC).
- Perfil (mediana con DC frente a sin DC): pendiente 5,9 % frente a 11,6 %; altitud 252 frente a 680 m; **urbano 34 % frente a 0 %**; **industrial 9,7 % frente a 0 %**; aeropuerto 19 frente a 61 km.
- Prueba de las reglas: Natura ≥ 25 % → 13 de 100 DC quedarían fuera (33,5 % de España); urbano ≥ 50 % → 30 DC; pendiente ≥ 30 % → 1 DC (y el 13 % de España); agua ≥ 90 % → 0 DC.

### Opciones
| Opción | Qué es | Circularidad | Fuga | Sesgos | Veredicto |
|---|---|---|---|---|---|
| **A** etiqueta presente | `y` (pipeline) o `is_datacenter` (ELT) | No: viene de una fuente externa, no de la rúbrica | Sí, si entran IXP, colocation o distancias a hubs (ya filtrado en `features.py:20-51`) | Las dos listas no coinciden (solo 21 de 100 en común) | Es la misma que C; usar la del pipeline |
| **B** exclusiones objetivas | agua, pendiente, protegido, inundable | No | No | Solo da negativos; hoy solo hay agua, Natura (que no es veto legal), urbano y pendiente: **faltan inundación y espacios protegidos** | Verdad parcial para “no viable” |
| **C** positivos reales | DC existentes o anunciados (PU) | No | Controlada | **Supervivencia y aglomeración** (se construye donde ya hay DC, fibra y clientes: Madrid, Barcelona, Aragón); **autocorrelación espacial** (positivos agrupados); **ruido de etiqueta** por geolocalización; “sin DC” ≠ “no viable” | Válida **como ordenación** (“se parece a donde se ha invertido”), no como “viable” |

### Decisión
**C + B**, con la rúbrica como salida principal:
1. **No existe un target “viable / no viable” verdadero.** Un DC ausente no demuestra inviabilidad. No entreno nada con etiquetas generadas por la rúbrica (solo aprendería la rúbrica).
2. La **rúbrica** decide viable / no viable (transparente, configurable, defendible ante el jurado).
3. Los **DC reales (C)** sirven para **validar** la rúbrica y para entrenar un modelo PU como **segunda opinión** (“parecido a donde se invierte”), evaluado con bloques espaciales (provincias).
4. Las **exclusiones (B)** son la verdad parcial de “no viable”: ninguna celda excluida puede salir viable, y ninguna regla dura debe dejar fuera DC reales (si lo hace, la regla está mal calibrada).

**Qué target falta** para un clasificador de “viable” de verdad: (a) solicitudes de acceso a red y **denegaciones** de REE o distribuidoras por nudo (negativos reales); (b) proyectos de DC **cancelados o rechazados** con su motivo (agua, red, urbanismo); (c) **suelo industrial disponible** (polígonos con parcelas libres ≥ 5-10 ha); (d) geolocalización a nivel de parcela de los 103 DC (catastro).

---

## Fase 4 · Rúbrica

Archivos: `rubrica.yaml` (configuración: cada umbral y peso con su columna, valor y justificación o “SUPUESTO”), `rubrica.py` (aplicación vectorizada: 41.296 celdas en 1,6 s), `tests/test_rubrica.py` (**12 tests, todos pasan**). Salida: `out/rubrica_es_3500.parquet`; sensibilidad en `out/sensibilidad.csv` (60 variantes + 200 sorteos Monte Carlo).
Ejecutar: `angel_modelo/.venv/bin/python angel_modelo/rubrica.py [--sensibilidad]` y `… -m pytest -q angel_modelo/tests`.

### Estructura
1. **Exclusiones duras (veto):** agua ≥ 90 % (regla del equipo); pendiente media ≥ 40 % (supuesto: la celda con DC más empinada tiene 37,4 %); espacio protegido y zona inundable oficial (**columnas vacías**: listas para cuando lleguen).
2. **Condicionantes (restan puntos y dan un aviso):** Natura ≥ 50 % −15 / ≥ 25 % −5 (no se suman); urbano ≥ 50 % −5; trayectoria de aproximación −5; costa baja −10 (proxy de inundación); altitud ≥ 1.500 m −10.
3. **Criterios (pesos = 100, curva por tramos):** energía 25 (`dist_substation_km`, **vacía**), conectividad 15 (`latency_to_hub_ms`), suelo industrial 10, pendiente 10, free cooling 10, bulbo húmedo 5, agua 5 (proxy: precipitación), sismicidad por catálogo 5, PGA 5 (**vacía**), inundación 5 (**vacía**), aeropuerto 5.
4. **Regla conservadora:** un dato que falta puntúa 40/100 (pesimista) y baja la **cobertura**. Confianza **alta** si cobertura ≥ 0,85 y |nota − umbral| ≥ 10; **media** si ≥ 0,70 y ≥ 5; si no, **baja**. Viable = no excluida, cobertura ≥ 0,60 y nota ≥ 60 (**≥ 65 si la confianza es baja**). Motivo principal: exclusión, condicionante, “duda” o el criterio con dato que más resta (o que más suma, si es viable).

> Por qué la conectividad sí entra en la rúbrica y no en el modelo: para una regla escrita a mano, la latencia al hub es un criterio legítimo (los clientes la exigen). En un modelo entrenado con DC actúa como coordenada encubierta. Al validar la rúbrica contra los DC reales, esa parte está algo inflada: lo mido en la fase 5.

### Resultado actual [visto]
- 2.267 excluidas (2.235 por pendiente, 32 por agua) · **729 viables (1,8 %)** · confianza **baja en todas las no excluidas**, porque la cobertura es 0,65 (falta el 35 % del peso: energía, PGA e inundación).
- Viables sobre todo en la meseta norte y Madrid (Salamanca 128, Ávila 108, Madrid 103, Valladolid 61): clima fresco + llano + cerca del hub.
- Frente a los DC reales (sin entrenar con ellos): **0 de 100 excluidos** ✔, percentil mediano de nota 76, 12 de 100 viables; tasa de DC entre viables 1,65 % frente a 0,24 % de base (**×7**). Los DC que salen “no viables” fallan sobre todo por free cooling (34: Madrid, Barcelona y Valencia son cálidos) → en la realidad la demanda y la red pesan más que el clima.

### Sensibilidad (`out/sensibilidad.csv`) [visto]
| Cambio | Viables (base 729) | % celdas que cambian |
|---|---|---|
| umbral_viable −5 | 5.527 | 11,6 |
| peso energía ×0,5 | 3.385 | 6,4 |
| peso energía ×1,5 | **0** | 1,8 |
| umbral_viable +5 | 83 | 1,6 |
| peso suelo industrial ×0,5 | 2.037 | 3,6 |
| tramos de free cooling ×0,8 | 1.961 | 3,0 |
| Monte Carlo de pesos (media) | 1.641 | 3,6 |
| Mediana de las 60 variantes | — | 0,44 |
- **Ninguna de las 729 celdas viables sigue siendo viable en ≥ 95 % de los sorteos de pesos.** Las viables están todas cerca del umbral.
- **Conclusión:** la frontera “viable” la manda hoy la **ausencia de datos de red eléctrica** (su peso con valor pesimista). La ordenación por nota es razonablemente estable (la mediana de variantes cambia el 0,4 % de celdas), pero la línea binaria no lo es. Para la demo: enseñar la **nota + confianza + motivo** y presentar el binario como “viable con confianza X”. En cuanto el ELT tenga `dist_substation_km`, la cobertura sube a 0,90 y la confianza puede llegar a “alta”.
- Columnas importantes que faltan para la rúbrica: `dist_substation_km` / `grid_capacity_available_mw`, `in_protected_area`, `in_official_flood_zone` / `flood_depth_rp100_m`, `pga_475y_g`, `water_stress`, `dist_fiber_backbone_km`, `dist_highway_km`, y precio del suelo.

---

## Fase 5 · Comparativas y modelo

Script: `analisis.py` (semilla 42, ~2,5 min). Salidas: `out/comparativa.csv`, `out/calibracion.csv`, `out/importancia_permutacion.csv`, `out/columnas_mantener_eliminar.csv`, `out/analisis.txt`.
- **Target:** `y` del pipeline (100 celdas con DC, aprendizaje PU). Se evalúan las 39.029 celdas no excluidas por la rúbrica.
- **Validación:** **espacial por provincias** (`StratifiedGroupKFold`, 5 pliegues, grupos = `admin2`; positivos por pliegue 17/22/27/17/17). Nunca aleatoria (solo como control).
- **Variables:** las 36 de `features_es_3500.parquet` (ya sin fuga) + 4 de `feat_suelo` = 40.
- **XGBoost → `HistGradientBoostingClassifier`** (mismo tipo de modelo; XGBoost y LightGBM no cargan en este Mac sin `libomp` de sistema). Supuesto S3.
- “Viable” para comparar a igual tasa = el **1,87 %** superior de cada puntuación (la tasa de viables de la rúbrica) y el 5 %.

### Resultados (validación por provincias) [visto, `out/comparativa.csv`]
| Puntuación | PR-AUC | PR-AUC por pliegue | ROC-AUC | Precisión @1,9 % | Recall @1,9 % | Recall @5 % |
|---|---|---|---|---|---|---|
| Aleatorio | 0,003 | 0,003±0,001 | 0,51 | 0,003 | 0,02 | 0,05 |
| Línea base: −distancia a aeropuerto | 0,020 | 0,025±0,012 | 0,85 | 0,034 | 0,25 | 0,45 |
| **Línea base: % urbano (una variable)** | **0,210** | 0,224±0,103 | **0,97** | 0,089 | 0,65 | 0,79 |
| Rúbrica (sin entrenar) | 0,008 | 0,014±0,016 | 0,67 | 0,016 | 0,12 | 0,20 |
| Rúbrica sin conectividad | 0,008 | 0,012±0,009 | 0,72 | 0,010 | 0,07 | 0,26 |
| Regresión logística | 0,132 | 0,219±0,150 | 0,94 | 0,081 | 0,59 | 0,77 |
| Regresión logística + PCA | 0,199 | 0,221±0,116 | 0,95 | 0,086 | 0,63 | 0,77 |
| Gradient boosting (≈XGBoost) | 0,138 | 0,170±0,071 | 0,96 | 0,081 | 0,59 | 0,82 |
| Gradient boosting + PCA | 0,167 | 0,176±0,078 | 0,96 | 0,089 | 0,65 | 0,77 |
| Control: GB con CV aleatoria | 0,154 | 0,161±0,065 | 0,95 | 0,086 | 0,63 | 0,78 |
| Control: GB + variables con fuga | 0,135 | 0,154±0,060 | 0,95 | 0,082 | 0,60 | 0,82 |
| **Control: GB SIN urbano ni industrial** | **0,019** | 0,028±0,019 | 0,85 | 0,023 | 0,17 | 0,45 |
| **Control: logística SOLO urbano + industrial** | **0,252** | 0,270±0,142 | **0,97** | **0,095** | **0,69** | 0,80 |

Calibración (`out/calibracion.csv`): **ningún modelo está calibrado**. En su decil superior el GB predice 0,48 de media y la tasa real es 0,024 (unas 20 veces de más; Brier 0,031). Es consecuencia de `class_weight="balanced"` y del PU: **la salida es una ordenación, nunca una probabilidad de “viable”**.

### Lectura honesta
1. **El modelo no mejora a la rúbrica ni la imita; responde a otra pregunta.** Correlación de Spearman GB–rúbrica = 0,13; solape del top 5 % = 18 %. La rúbrica mide “¿se puede construir bien aquí?” (llano, fresco, sin riesgos); el modelo mide “¿se parece a donde se ha invertido?”.
2. **Lo que aprende el modelo es “ciudad o polígono industrial”.** Una logística con `urbano_pct` + `industrial_pct` (2 variables) gana a todo. Sin ellas, las otras 38 variables del ELT (clima, terreno, sismicidad, cables, aeropuerto) dan PR-AUC 0,019: **prácticamente ruido** frente a la línea base del aeropuerto (0,020). Es el sesgo de aglomeración de la fase 3: los DC están donde hay demanda, fibra y red, y el suelo urbano es su proxy.
3. **El AUC 0,585 del equipo** (`scores_es_3500_cv_report.csv`) se calculó **antes** de añadir `feat_suelo` (su lista de importancia no tiene variables de suelo). Si Cristóbal vuelve a ejecutar `features.py` + `train.py`, deberían salir cifras parecidas a estas (≈0,95). **[deduzco]** Hay que contarlo bien: no es que el modelo “haya aprendido viabilidad”, es que ha encontrado las ciudades.
4. **PCA:** sube un poco la logística (0,13 → 0,20) porque agrupa el bloque térmico redundante, pero quita explicabilidad. **No lo recomiendo** para la versión que se presenta: mejor quitar las redundantes a mano (lista abajo).
5. **Controles:** la CV aleatoria apenas infla aquí (0,154 frente a 0,138) y las variables con fuga tampoco (0,135), porque `urbano_pct` ya captura esa información. Con la validación por bloques de 70 km del equipo la diferencia era mayor (0,834 frente a 0,585).
6. **Red neuronal:** descartada. Con 100 positivos se sobreajusta, y ni siquiera el boosting supera a 2 variables lineales.
7. **La rúbrica casi no detecta los DC** (PR-AUC 0,008, ×3 sobre el azar) **porque penaliza justo lo que los atrae**: calor urbano (free cooling) y suelo urbano. No es un fallo si el producto es “dónde construir uno nuevo” (los nuevos campus a gran escala sí buscan suelo barato, fresco y llano), pero hay que decidir conscientemente qué pregunta responde la web.

### Columnas: mantener / eliminar (para Adham y Cristóbal) [visto, `out/columnas_mantener_eliminar.csv`]
Criterio: importancia por permutación en el pliegue de test (ΔPR-AUC, GB), estable si es > 0,002 en ≥ 3 de 5 pliegues; redundantes con ρ ≥ 0,95 → se queda la más útil.
- **Mantener (11):** `urbano_pct`, `industrial_pct`, `dist_airport_runway_km`, `elevation_m`, `newest_cable_year`, `wetbulb_p99_c`, `dist_m5_epicenter_km`, `terrain_ruggedness`, `n_eq_m4_100km_50y`, `dist_coast_km`, `aspect_deg`*.
  *`aspect_deg` (orientación 0–360°) es circular: 1° y 359° son casi iguales. Su “aporte” es casi seguro espurio → **eliminar** o convertir en seno y coseno. `newest_cable_year` [deduzco] actúa como proxy de “ciudad costera con cable” (Barcelona, Bilbao, Valencia).
- **Revisar (10, aporte pequeño o inestable):** `free_cooling_hours`, `solar_ghi_kwh_m2`, `max_daily_precip_p99_mm`, `dist_cable_landing_km`, `agua_pct`, `heating_degree_days`, `rel_humidity_mean_pct`, `annual_precip_mm`, `max_mag_100km_hist`, `min_temp_p01_c`.
- **Eliminar del modelo (19):**
  - Redundantes (ρ ≥ 0,95): `dist_airport_km` (=`dist_airport_runway_km`), `est_pue` (fórmula de `free_cooling_hours`), `est_wue_l_kwh` / `cooling_degree_days` (ρ = 1 entre sí), `mean_temp_c`, `max_temp_p99_c`, `frost_days_year`, `slope_pct`/`terrain_ruggedness` (ρ = 0,999: **quedarse con `slope_pct`** por ser más explicable, aunque el script eligiera la otra).
  - Ruido (sin aporte fuera de muestra): `planned_cables_flag`, `in_low_elevation_coastal_zone`, `n_cables_nearest_landing`, `wind_speed_mean_ms`, `natura2000_pct`, `heatwave_days_year`, `in_flight_path_flag`, `dewpoint_mean_c`, `tropical_nights_year`, `diurnal_range_c`, `adiabatic_cooling_hours`.
  - **Ojo:** “ruido para el modelo” ≠ “inútil”. `natura2000_pct`, `in_flight_path_flag`, `in_low_elevation_coastal_zone` y `slope_pct` **siguen en la rúbrica** como reglas: son restricciones reales aunque no expliquen dónde hay DC hoy.
- **Además, en el preprocesado del ELT:** quitar las 10 constantes de `sites_yearly` (valores de país) y `n_submarine_cables_country`; `max_mag_100km_hist` NaN → “sin sismo M≥4” (0 o indicador), no nulo; y no versionar en git `sites_weekly` (el modelo estático no lo usa).
- **Lo que de verdad falta (más valioso que cualquier algoritmo):** `dist_substation_km`, `grid_capacity_available_mw`, `dist_fiber_backbone_km`, `in_protected_area`, `in_official_flood_zone`, `pga_475y_g`, `water_stress`, precio del suelo y suelo industrial disponible.

---

## Fase 6 · Entregables

### 1. El proyecto parte por parte (para ti)
1. **Rejilla** (`ELT/dclake/grid.py`): España partida en 41.296 cuadrados de 3,5 km en una proyección de igual área (EPSG:3035). Cada celda tiene un `site_id` = su columna y su fila. Todo se une por esa clave.
2. **Colectores** (`ELT/dclake/collectors/`): cada archivo baja una fuente pública (OSM, E-OBS, Copernicus DEM, USGS, PeeringDB, OMIE…) para toda España de una vez y calcula un valor por celda.
3. **Ensamblado** (`assemble.py`, `weekly.py`): mete todo en tablas con exactamente las columnas del diccionario (lo que no hay queda vacío) y agrega lo diario por semanas.
4. **Dataset** (`ELT/dataset/`): Parquet por tabla y por país; se sube a Azure con `dclake upload`.
5. **Target** (`pipeline/src/labels.py`): marca las 100 celdas donde hay o se ha anunciado un data center.
6. **Variables** (`pipeline/src/features.py`, `feat_suelo.py`): quita lo que haría trampa (fuga) y añade el % de suelo urbano, industrial, agua y Natura 2000.
7. **Modelo del equipo** (`pipeline/src/train.py`): LightGBM que ordena las celdas por parecido a donde ya se ha invertido + 3 razones SHAP por celda → `scores_es_3500.parquet` → web.
8. **Mi parte** (`angel_modelo/`): rúbrica transparente (`rubrica.yaml` + `rubrica.py`) que decide viable / no viable con confianza y motivo; `analisis.py`, que compara rúbrica, líneas base y modelos con validación por provincias.
9. **Web (Dani, Cloudflare)**: pinta el mapa con nota, banda, razones y avisos. No está en el repo.

### 2. Glosario (12 términos)
- **Target (variable objetivo):** lo que el modelo intenta predecir. *Aquí: `y` = la celda tiene un data center existente o anunciado.*
- **Aprendizaje PU (positivos / sin etiquetar):** solo sabemos qué es “sí”; el resto es “no sabemos”, no “no”. *Una celda sin DC puede ser perfecta y simplemente nadie ha construido aún.*
- **Fuga de datos (leakage):** una variable que contiene la respuesta de forma disfrazada. *`dist_ixp_km`: los puntos de intercambio están dentro de data centers.*
- **Circularidad:** entrenar con etiquetas que salen de tus propias reglas; el modelo solo copia las reglas. *Entrenar con “viable según la rúbrica” no aporta nada.*
- **Validación espacial:** separar entrenamiento y prueba por zonas (provincias) y no al azar. *Si Madrid está en la prueba, el modelo no ha visto celdas de Madrid al entrenar.*
- **Autocorrelación espacial:** las celdas vecinas se parecen. *Dos celdas contiguas de San Blas tienen casi el mismo clima y suelo; si una está en entrenamiento y otra en prueba, se “copia”.*
- **Overfitting (sobreajuste):** el modelo memoriza el entrenamiento y falla con lo nuevo. *Con 100 positivos, una red neuronal se aprendería las 100 celdas de memoria.*
- **Precisión y recall de “viable”:** precisión = de las que digo viables, cuántas lo son; recall = de las viables de verdad, cuántas encuentro. *Priorizamos la precisión: mandar a un inversor a una celda mala es peor.*
- **PR-AUC:** resumen de la curva precisión-recall; útil cuando los positivos son raros. *Base aleatoria = 0,003 (100 de 39.029 celdas).*
- **Calibración:** si el modelo dice 30 %, ¿ocurre el 30 % de las veces? *El GB dice 48 % en su decil alto y la tasa real es 2,4 %: no calibrado.*
- **Importancia por permutación:** se baraja una columna y se mide cuánto empeora el modelo en datos no vistos. *Si barajar `mean_temp_c` no empeora nada, es ruido.*
- **Sesgo de supervivencia / aglomeración:** solo vemos dónde se construyó, no dónde se descartó; y se construye donde ya hay otros DC. *El modelo aprende “cerca de una ciudad”, no “buen sitio”.*

### 3. Supuestos
- **S1.** `angel/modelo` sale de `origin/main` @ `83c32ce`, no de tu `main` local (estaba 15 commits por detrás y sin datos).
- **S2.** He descomprimido `dc_datalake.zip` en `angel_modelo/_ref/` para leerlo y lo he borrado al ver que `ELT/` es su versión nueva (todo dentro de mi carpeta).
- **S3.** XGBoost y LightGBM no cargan en este Mac (falta `libomp`, que es de sistema y no he instalado). He usado `HistGradientBoostingClassifier` de scikit-learn. En los portátiles del equipo con `lightgbm` funcionará `train.py` tal cual.
- **S4.** Solo había Python 3.15 en el sistema; el venv está en `angel_modelo/.venv` (ignorado por git con la regla `.venv*/` del `.gitignore`). PyYAML se compiló desde el código fuente.
- **S5.** No he muestreado: el dataset de España pesa < 60 MB (el límite era 500 MB).
- **S6.** Lista oficial de DC = la del pipeline (`dc_sites_es.csv`, 100 celdas), no `is_datacenter` del ELT (63 celdas): está documentada punto a punto.
- **S7.** Todos los pesos, tramos y penalizaciones de `rubrica.yaml` marcados como SUPUESTO son criterio mío, razonado con los datos (percentiles de España y de las celdas con DC), **no con fuente técnica**. Por verificar con alguien del sector: tramos de distancia a subestación, umbral de bulbo húmedo (ASHRAE) y NCSE-02.
- **S8.** La pendiente es la **media de la celda** (12 km²): una celda con 40 % puede tener una parcela llana. Por eso la exclusión es alta (40 %).
- **S9.** “Viable” para comparar los modelos = el 1,87 % superior (tasa de la rúbrica). Es una elección de punto de operación, no un dato.
- **S10.** Fecha de entrega: miércoles 11-nov-2026 (por confirmar, según tu mensaje). Hoy es lunes 9.
- **S11.** Roles deducidos de `git log`: `dmar1400` = Dani; Desi no tiene commits.

### 4. Plan de trabajo en bloques de 2 h (lunes 9 por la tarde → miércoles 11)
| Bloque | Quién | Qué |
|---|---|---|
| Lun 16–18 | Ángel | Enviar el mensaje al grupo; acordar la lista oficial de DC; pasar a Adham la lista de columnas vacías prioritarias |
| Lun 16–20 | Adham | ELT: subestaciones y líneas (OSM), WDPA, inundación JRC, PGA GEM → `sites_static` (desbloquea energía y riesgos) |
| Lun 18–20 | Ángel + Cristóbal | Decidir qué responde la web: **rúbrica = viable sí/no** + **modelo = atractivo de mercado** (ranking). Llevar `rubrica.py` al pipeline (`pipeline/src/`) con salida `score, confianza, motivo, avisos` |
| Mar 9–11 | Ángel | Volver a ejecutar `rubrica.py --sensibilidad` y `analisis.py` con las columnas nuevas; reajustar tramos de energía; actualizar el informe |
| Mar 11–13 | Cristóbal | `features.py` con la lista mantener/eliminar; reentrenar; cifras finales con validación espacial; modelo de 2 variables como línea base en la diapositiva |
| Mar 11–13 | Dani | Web: capa “viable / confianza / motivo / avisos” + ranking del modelo; deslizadores de pesos (usa `rubrica.yaml`) → UX + innovación |
| Mar 15–17 | Ángel + Desi | **IA frontera:** informe por celda generado por Claude a partir de las subnotas, avisos y motivo (sin inventar datos: solo lo que hay en la fila) |
| Mar 17–19 | Todos | Prueba de punta a punta en un portátil limpio; `requirements.txt` del pipeline; tests |
| Mar 19–21 | Cristóbal + Ángel | Diapositivas: problema, datos, rúbrica, validación honesta (azar 0,003 → 2 variables 0,25), limitaciones, siguiente paso |
| Mié 9–11 | Todos | Congelar código, README final, ensayo de la demo (3 celdas: una viable, una excluida y una dudosa) |
| Mié 11–13 | Todos | Margen de imprevistos y entrega |

### 5. Mensaje corto para el grupo
> He revisado datos y modelo (rama `angel/modelo`, carpeta `angel_modelo/`, sin tocar nada vuestro). Resumen:
> 1) **El cuello de botella son los datos, no el algoritmo:** energía (subestaciones, capacidad), inundación, espacios protegidos, PGA, fibra y carreteras están 100 % vacíos en `ELT/dataset`. Adham, ¿podemos priorizarlos hoy?
> 2) Con validación por provincias, **una logística con solo % urbano + % industrial (PR-AUC 0,25) gana al LightGBM/XGBoost con 40 variables (0,14–0,17)**. Sin esas dos, el resto da 0,02 ≈ ruido. El modelo aprende “ciudad/polígono”, no “viable”.
> 3) Hay **dos listas de DC que no coinciden** (ELT 63 celdas, pipeline 100; solo 21 en común). Propongo que la oficial sea la del pipeline.
> 4) Propuesta: **rúbrica transparente** (`rubrica.yaml`: exclusiones, condicionantes, pesos) para viable / no viable con **confianza y motivo**, y el modelo como “atractivo de mercado”. Sin PCA ni red neuronal.
> 5) Lista de columnas a mantener o eliminar en `angel_modelo/out/columnas_mantener_eliminar.csv`. Informe completo en `angel_modelo/INFORME.md`.

### 6. Párrafo para el README (modelo y rúbrica)
> **Modelo y rúbrica.** La viabilidad de cada celda de 3,5 km la decide una **rúbrica transparente** (`angel_modelo/rubrica.yaml`): exclusiones duras (agua, pendiente extrema, espacio protegido, zona inundable), condicionantes que restan puntos y generan avisos (Natura 2000, suelo urbano, servidumbres aeronáuticas, costa baja, altitud) y criterios ponderados con curvas por tramos (energía, conectividad, suelo industrial, pendiente, refrigeración, agua, sismicidad, inundación y accesos; los pesos suman 100). Ante la duda, no viable: un dato que falta puntúa de forma pesimista y baja la confianza, y con confianza baja se exige más nota. Cada celda sale con nota 0-100, viable / no viable, confianza (alta, media, baja), motivo principal y avisos. Aparte, un modelo de aprendizaje PU entrenado con los 103 data centers reales de España ordena las celdas por **parecido a donde ya se ha invertido**; se valida por bloques espaciales (provincias), no al azar, y su salida es un ranking, no una probabilidad. No es un estudio geotécnico ni una clasificación urbanística legal: es un cribado inicial.
