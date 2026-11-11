# Pipeline: del dataset al mapa de viabilidad

Coge el dataset del ELT (`ELT/dataset/`) y produce un archivo con **una fila por celda de 3,5 km de España**: su nota, su banda (alta / media / baja / excluida) y las 3 razones que la explican. Ese archivo es el que pinta la web.

## Las 3 capas

1. **Reglas (exclusiones):** fuera lo imposible por ley o por física: celdas casi enteras de agua (≥ 90 %) o al menos la mitad en un parque nacional o en zona de flujo preferente del SNCZI (≥ 50 %). Estas celdas no se puntúan. Lo que se puede hacer con permisos (Natura 2000, suelo urbano, parte de la celda en zona inundable de 100 años, en un parque nacional o en zona de flujo preferente) se puntúa y lleva un aviso. Umbrales en `EXCLUDE_PCT` y `WARN_PCT` de `src/feat_suelo.py`.
2. **Modelo:** LightGBM entrenado con las celdas donde ya hay o se ha anunciado un data center (positivas) frente al resto (sin etiquetar). Ordena las celdas según cuánto se parecen a donde ya se ha invertido. Es una ordenación, no una probabilidad.
3. **Explicación:** SHAP da las 3 variables que más pesan en la nota de cada celda.

## Cómo se ejecuta

Desde `pipeline/`, con el entorno del ELT más lo del modelo (`python -m pip install -r requirements.txt`):

```
python src/labels.py      # target: celdas con data center (datacentermap)
python src/feat_suelo.py  # % de suelo por celda (Natura 2000, CORINE) y exclusiones
python src/feat_riesgos.py   # zonas inundables oficiales (SNCZI), parques nacionales y PGA del IGN
python src/feat_riesgos.py --solo-pga   # solo la PGA del IGN, sobre el parquet existente
python src/feat_infra.py  # red eléctrica y autovías (OpenStreetMap vía ohsome)
python src/feat_suelo.py --solo-exclusiones   # rehace las exclusiones con feat_riesgos (sin descargas)
python src/features.py    # variables desde ELT/dataset + feat_*.parquet, sin las que hacen trampa
python src/priors_voz.py  # criterios de expertos (citas de audio del ELT) -> sentido obligado por variable
python src/train.py --exclusions data/processed/exclusions_es_3500.parquet   # modelo -> scores
python src/train.py --exclusions data/processed/exclusions_es_3500.parquet --priors data/processed/priors_voz.csv
python src/finanzas.py    # capa financiera (no entra al modelo)
python src/agua.py        # riesgo hídrico WRI Aqueduct 4.0 (indicador y aviso, no entra al modelo)
```

Cualquier `data/processed/feat_*.parquet` (`site_id` + columnas numéricas) entra solo al modelo al ejecutar `features.py`.

`feat_riesgos.py` necesita los zips de datos del SNCZI (MITECO pide una verificación en el navegador, así que se
descargan a mano) en cualquier carpeta de `data/raw/`: `laminas-zfp-PB.zip`, `laminas-zfp-can.zip`,
`laminasPB-q100.zip`, `laminasCanarias-q100.zip`, `laminasPB-q500.zip` y `laminasCanarias-q500.zip`. Los de estilo
(`lyr-...zip`) no sirven: solo traen la simbología.

`--priors` hace que el modelo respete lo que dicen quienes eligen emplazamientos en 81 grabaciones públicas
(`ELT/dataset/audio_evidence.parquet`): estar más cerca de una subestación, de una línea de alta tensión o de
un corredor de fibra, o tener más suelo industrial o más generación cerca, nunca puede bajar la nota. Un
criterio se aplica si lo sostienen al menos 3 grabaciones distintas y menos del 20 % dice lo contrario
(12 variables hoy; `priors_voz.py` imprime cuáles y por qué no las demás).

Opciones de `train.py`: `--exclusions <parquet>` (columnas `site_id, excluded`) y `--target y_operational` (entrenar solo con data centers operativos, sin los anunciados).

Cuando el ELT tenga columnas nuevas, basta con volver a ejecutar `features.py` y `train.py`: las variables nuevas entran solas.

### Japón (y cualquier otro país del ELT)

El país se elige con la variable de entorno `DC_COUNTRY` (por defecto `ESP`, así que España no cambia). Los
archivos de otro país van a `data/processed/<ISO>/` con su etiqueta (`*_jp_3500.parquet`): nada se mezcla.

```
$env:DC_COUNTRY = "JPN"          # PowerShell (bash: export DC_COUNTRY=JPN)
python src/feat_riesgos.py       # parques nacionales (WDPA); SNCZI y PGA del IGN solo existen en España
python src/feat_suelo_ghsl.py    # suelo industrial y urbano (GHSL) y exclusiones: CORINE solo cubre Europa
python src/feat_infra.py         # red eléctrica y autopistas (OSM vía ohsome); Okinawa es su propio sistema
python src/dc_sites.py           # data centers conocidos: PeeringDB (del ELT) + OSM -> data/raw/dc_sites_jp.csv
python src/labels.py
python src/features.py
python src/train.py --exclusions data/processed/JPN/exclusions_jp_3500.parquet --priors data/processed/priors_voz.csv
```

Diferencias con España, por falta de fuentes equivalentes:
- Etiquetas de PeeringDB + OpenStreetMap, no de datacentermap.com.
- `industrial_pct` y `urbano_pct` miden superficie edificada de GHSL (no residencial / residencial), no zonas de CORINE: no son comparables entre países.
- Sin Natura 2000, zonas inundables oficiales ni PGA del IGN: quedan la inundación del JRC y la sismicidad de GEM del ELT.
- El ELT de Japón no tiene sísmica H/V ni las capas de OSM de Overpass, así que esas variables no entran al modelo.

## Archivos

| Archivo | Qué es |
|---|---|
| `data/raw/dc_sites_es.csv` | 103 emplazamientos de datacentermap.com (9-nov-2026) con coordenadas. `precision`: `district_approx` (~1–2 km), `municipio` (centro del pueblo), `metro` (centro de la ciudad, a mejorar) |
| `data/processed/labels_es_3500.parquet` | `site_id, y, y_operational, n_sites, n_buildings, sites` |
| `data/processed/feat_suelo.parquet` | `site_id` + % de la celda en Natura 2000, suelo urbano, industrial y agua |
| `data/processed/feat_riesgos.parquet` | `site_id` + % en zona de flujo preferente, zona inundable de 100 y 500 años y parque nacional, distancia al parque nacional más cercano y `pga475_ign_g` (PGA a 475 años del IGN, en g, interpolada entre las isolíneas de 0,01 g de su visor de terremotos) |
| `data/processed/feat_infra.parquet` | Distancias a subestación (todas, 220 kV, 400 kV), torres de alta tensión y autovías. Solo cuenta la red de España y del mismo sistema eléctrico (las islas no cruzan el mar) |
| `data/processed/priors_voz.csv` | `feature, monotone (+1 sube / -1 baja), criterion, n_sources_for, n_sources_against` + la cita más clara con su segundo y enlace |
| `data/processed/exclusions_es_3500.parquet` | `site_id, excluded, motivo_descarte, avisos` + los % que deciden la regla |
| `data/processed/features_es_3500.parquet` | `site_id` + variables numéricas |
| `data/processed/finanzas_es_3500.parquet` | Para un data center de 10 MW en 10 ha: luz al año (OMIE 2025 × PUE), suelo (Mº Transportes, por provincia), coste laboral (INE, por comunidad), construcción (Turner & Townsend: Madrid 10 $/W), conexión (distancia a 220 kV × 0,4 M€/km, supuesto), `inversion_eur_m2` y `coste_10_anos_eur_m2` |
| `data/processed/agua_es_3500.parquet` | Riesgo hídrico de WRI Aqueduct 4.0 (0–5) por celda: estrés hídrico actual, 2030 y 2050, agotamiento, riesgo de sequía y variabilidad. No entra al modelo (solo subía el AUC de 0,893 a 0,899 y por geografía encubierta): es indicador y aviso para la web |
| `data/processed/scores_es_3500.parquet` | **Para la web:** `site_id, lon, lat, admin1, admin2, y, y_operational, sites, excluded, score_pct, oof_spatial_pct, band, reasons` |
| `data/processed/scores_es_3500_cv_report.csv` | Validación aleatoria frente a espacial (la que se presenta es la espacial) |
| `data/processed/scores_es_3500_importance.csv` | Importancia de cada variable (media de \|SHAP\|) |

## Reglas para todos

- **Una sola rejilla, la del ELT.** La clave es `site_id = ESP_<x/3500>_<y/3500>` (EPSG:3035). Para asignar un punto a su celda: `cells.site_id_from_lonlat(lon, lat)`. Nadie crea otra rejilla.
- **Nada de variables que digan dónde están los data centers.** Ni coordenadas ni distancias a data centers, puntos de interconexión o ciudades fijas. La lista, con el motivo de cada una, está en `LEAKAGE` de `src/features.py`.
- Lo que falta se deja vacío (NaN), nunca a 0.
- La métrica que se presenta es la **validación espacial** (bloques de 70 km). La aleatoria sale inflada porque el test ve a los vecinos.
