# Pipeline: del dataset al mapa de viabilidad

Coge el dataset del ELT (`ELT/dataset/`) y produce un archivo con **una fila por celda de 3,5 km de España**: su nota, su banda (alta / media / baja / excluida) y las 3 razones que la explican. Ese archivo es el que pinta la web.

## Las 3 capas

1. **Reglas (exclusiones):** en rojo solo lo prohibido o imposible (hoy: celda casi toda agua; pendiente: parques nacionales y zonas de flujo preferente). Lo que se puede hacer con permisos (Natura 2000, suelo urbano) se puntúa y lleva un aviso. Ver `src/feat_suelo.py`.
2. **Modelo:** LightGBM entrenado con las celdas donde ya hay o se ha anunciado un data center (positivas) frente al resto (sin etiquetar). Ordena las celdas según cuánto se parecen a donde ya se ha invertido. Es una ordenación, no una probabilidad.
3. **Explicación:** SHAP da las 3 variables que más pesan en la nota de cada celda.

## Cómo se ejecuta

Desde `pipeline/`, con un entorno de Python que tenga `pandas pyarrow numpy scipy scikit-learn lightgbm shap pyproj`:

```
python src/labels.py      # target: celdas con data center (datacentermap)
python src/feat_suelo.py  # Natura 2000 y CORINE -> feat_suelo + exclusiones
python src/feat_infra.py  # red eléctrica y autovías (OpenStreetMap vía ohsome)
python src/features.py    # variables desde ELT/dataset, sin las que hacen trampa
python src/train.py --exclusions data/processed/exclusions_es_3500.parquet
python src/finanzas.py    # capa financiera (no entra al modelo)
```

Cualquier `data/processed/feat_*.parquet` (`site_id` + columnas numéricas) entra solo al modelo al ejecutar `features.py`.

Opciones de `train.py`: `--exclusions <parquet>` (columnas `site_id, excluded`) y `--target y_operational` (entrenar solo con data centers operativos, sin los anunciados).

Cuando el ELT tenga columnas nuevas, basta con volver a ejecutar `features.py` y `train.py`: las variables nuevas entran solas.

## Archivos

| Archivo | Qué es |
|---|---|
| `data/raw/dc_sites_es.csv` | 103 emplazamientos de datacentermap.com (9-nov-2026) con coordenadas. `precision`: `district_approx` (~1–2 km), `municipio` (centro del pueblo), `metro` (centro de la ciudad, a mejorar) |
| `data/processed/labels_es_3500.parquet` | `site_id, y, y_operational, n_sites, n_buildings, sites` |
| `data/processed/feat_suelo.parquet` / `exclusions_es_3500.parquet` | % de la celda en Natura 2000, urbano, industrial y agua; exclusiones y avisos |
| `data/processed/feat_infra.parquet` | Distancias a subestación (todas, 220 kV, 400 kV), torres de alta tensión y autovías. Solo cuenta la red de España y del mismo sistema eléctrico (las islas no cruzan el mar) |
| `data/processed/features_es_3500.parquet` | `site_id` + variables numéricas (se regenera, no editar a mano) |
| `data/processed/finanzas_es_3500.parquet` | Para un data center de 10 MW en 10 ha: luz al año (OMIE 2025 × PUE), suelo (Mº Transportes, por provincia), coste laboral (INE, por comunidad), construcción (Turner & Townsend: Madrid 10 $/W), conexión (distancia a 220 kV × 0,4 M€/km, supuesto), `inversion_eur_m2` y `coste_10_anos_eur_m2` |
| `data/processed/scores_es_3500.parquet` | **Para la web:** `site_id, lon, lat, admin1, admin2, y, y_operational, sites, excluded, score_pct, oof_spatial_pct, band, reasons` |
| `data/processed/scores_es_3500_cv_report.csv` | Validación aleatoria frente a espacial (la que se presenta es la espacial) |
| `data/processed/scores_es_3500_importance.csv` | Importancia de cada variable (media de \|SHAP\|) |

## Reglas para todos

- **Una sola rejilla, la del ELT.** La clave es `site_id = ESP_<x/3500>_<y/3500>` (EPSG:3035). Para asignar un punto a su celda: `cells.site_id_from_lonlat(lon, lat)`. Nadie crea otra rejilla.
- **Nada de variables que digan dónde están los data centers.** Ni coordenadas ni distancias a data centers, puntos de interconexión o ciudades fijas. La lista, con el motivo de cada una, está en `LEAKAGE` de `src/features.py`.
- Lo que falta se deja vacío (NaN), nunca a 0.
- La métrica que se presenta es la **validación espacial** (bloques de 70 km). La aleatoria sale inflada porque el test ve a los vecinos.
