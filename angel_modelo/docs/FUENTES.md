# Fuentes de datos por país

Regla: solo información pública y abierta, respetando licencias y límites. Todo en UTF-8 (lo que llegue en Shift_JIS/CP932 se convierte; `carga.leer_csv` y `militar.leer_capa` lo hacen con aviso). Sin datos personales. Unidades canónicas iguales en los dos países.

## Comunes (trabajo del equipo, se usan tal cual)
| Capa | Fuente | Licencia / términos | Dónde |
|---|---|---|---|
| Rejilla 3,5 km, clima, terreno, sismicidad, OSM | ETL del equipo (`ETL/dclake`, ver `ETL/README.md`) | La de cada fuente (OSM ODbL; E-OBS y GEM no comerciales) | `ETL/dataset/*/{ESP,JPN}-p*.parquet` |
| Suelo, riesgos, red eléctrica, etiquetas | `Modelo/src/*.py` del equipo | Ídem | `Modelo/data/processed/` (España) y `.../JPN/` |

## Instalaciones militares (este módulo)
| País | Fuente | URL | Licencia y atribución | Descarga | CRS de trabajo | Unidades |
|---|---|---|---|---|---|---|
| España | OpenStreetMap: `landuse=military` y `military=base\|airfield\|naval_base\|barracks\|range\|training_area\|ammunition` | https://overpass-api.de (consulta en el `meta` del GeoJSON) | ODbL 1.0 · «© colaboradores de OpenStreetMap» | 11-nov-2026, 1.236 polígonos, 0,9 MB | EPSG:3035 (igual área, métrica: misma rejilla del ETL; vale para Península, Baleares y Canarias) | `militar_pct` %, `distancia_militar_km` km, `en_franja` 0/1 |
| Japón | Ídem | Ídem | Ídem | 11-nov-2026, 670 polígonos, 0,7 MB | LAEA centrada en Japón (`+proj=laea +lat_0=36 +lon_0=137`, ETL; métrica, válida para Okinawa e islas remotas) | Ídem |

Limitaciones: la huella física **no es el perímetro legal**; OSM puede estar incompleto; no se deduce ninguna instalación que no figure en fuentes públicas.

## Sismicidad (unidades comparables)
- **España:** `pga475_ign_g`, PGA a 475 años del IGN, en **g** (equipo, `feat_riesgos.py`).
- **Japón:** `pga_475y_g`, GEM, en **g** (ETL). Se lee como `pga475_ign_g` por alias (`config/paises/jp.yaml`).
- Conversión documentada: 1 gal = 1 cm/s² y 1 g = 980,665 gal, así que g = gal / 980,665. La intensidad (escala JMA) no se convierte a g: no es una aceleración.
- **Alternativa oficial PENDIENTE: J-SHIS** (NIED). Sus términos permiten el uso con atribución, pero no se ha descargado (sin tiempo para verificar el formato). Vs30 de J-SHIS, también pendiente.

## Japón: capas PENDIENTES (reglas ya escritas en `config/paises/jp.yaml`; se activarán solas al rellenarse)
| Capa | Fuente oficial | Estado | Cómo obtenerla |
|---|---|---|---|
| Área de control de urbanización (市街化調整区域) | MLIT 国土数値情報 A29 (用途地域) / 都市地域 | **PENDIENTE** | https://nlftp.mlit.go.jp/ksj/ → descarga por prefectura (shapefile, atributos en **CP932**, JGD2011). Términos de uso de 国土数値情報 (uso con atribución; comprobar la licencia del conjunto). Calcular `control_urbanizacion_pct` por celda |
| Zonas de alerta especial por sedimentos (土砂災害特別警戒区域) | MLIT 国土数値情報 A33 | **PENDIENTE** | Ídem, A33 → `sedimentos_especial_pct` |
| Tsunami e inundación | MLIT A40 y A31 | **PENDIENTE** (opcional) | Ídem |
| Fallas activas | AIST (活断層データベース) | **PENDIENTE** (opcional) | Comprobar los términos de AIST |
| K-NET / KiK-net (NIED) | — | **NO se descarga** (registro obligatorio) | Solo con cuenta de NIED |
| Fibra y corredores de infraestructura | — | **No disponible** en el ETL de Japón (`dist_infra_corridor_km` al 0 %) | — |

Atribución exigida en el mapa: OpenStreetMap (ODbL); las capas de MLIT, cuando se añadan, con «出典：国土交通省 国土数値情報».
