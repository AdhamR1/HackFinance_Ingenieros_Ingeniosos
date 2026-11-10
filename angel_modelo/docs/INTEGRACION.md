# Contrato de integración

Qué uso del trabajo del equipo, qué espero de cada pieza y qué pasa si cambia. Los nombres de columnas,
alias, rutas, rangos plausibles y tamaño de celda están en `config/columnas.yaml`, no en el código.
Los tests de este contrato están en `tests/test_contrato.py`. Usan un recorte real de 300 celdas copiado a un
directorio temporal y nunca tocan los datos del repositorio.

## Errores fatales y avisos

| Situación | Tipo | Mensaje / efecto |
|---|---|---|
| No existe la carpeta `ELT/dataset` (o la de `MAPA_ELT_DATASET`) | **FATAL** | `ERROR FATAL: no existe la carpeta de datos del ELT` |
| Falta la tabla `sites_static` | **FATAL** | `no hay tabla 'sites_static'` |
| Falta el identificador `site_id` (y sus alias) | **FATAL** | `la tabla estática no tiene identificador de celda` |
| Faltan `lon`/`lat` (y sus alias) | **FATAL** | `la tabla estática no tiene coordenadas` |
| Un Parquet es un puntero de Git LFS | **FATAL** | `es un puntero de Git LFS. Ejecuta: git lfs install && git lfs pull` |
| Una columna llega con otro nombre registrado como alias | aviso | se renombra al nombre canónico |
| Falta `sites_yearly`, `finanzas`, `exclusions`, `labels`, `scores` o `dc_sites_es.csv` | aviso | lo que depende de ella queda «no disponible» |
| Falta `admin1`/`admin2` | aviso | «Sin provincia» / «Sin comunidad» |
| Filas duplicadas (misma celda y fecha) | aviso | se queda la última; se cuentan en el informe |
| Columna numérica que llega como texto | aviso | se convierte a número si ≥ 90 % lo es |
| Valor fuera de rango plausible | aviso | pasa a «sin dato» y se cuenta |
| Capa de la rúbrica vacía o con cobertura < 60 % | aviso | la capa se omite, sus pesos se reparten y baja la confianza |
| Columna nueva | informe | se clasifica y se lista; **no cambia el mapa** hasta registrarla en `config/rubrica.yaml` |
| Ids que no siguen el patrón de la rejilla, o centroides que no cuadran | aviso | el mapa dibuja cuadrados desde el centroide |
| Menos de 10 celdas con data center o menos de 5 provincias | aviso | la evaluación del modelo se marca como no evaluable |

## Componentes del equipo que uso

### ELT (Adham; Dani en la configuración) — `ELT/dataset/`
- **Cómo se genera:** `cd ELT && python -m dclake grid|collect|assemble` (ver `ELT/README.md`). No lo ejecuto: solo leo su salida.
- **`sites_static/ESP-p*.parquet`**: una fila por celda.
  - `site_id` (texto, `ESP_<x/3500>_<y/3500>` en EPSG:3035), `lon`, `lat` (decimales, centro de la celda) y `admin1`, `admin2` (texto).
  - Unas 250 columnas más; uso las numéricas y booleanas.
  - `is_datacenter` (booleano): lista OSM + PeeringDB.
- **`sites_yearly/ESP-p*.parquet`**: `site_id` y `year` (entero), más variables climáticas. Agrego por celda con la media (configurable: `agregacion_temporal`).
- **Supuesto:** una celda por `site_id`; si se repite, me quedo con la última.

### Pipeline (Cristóbal; datos de Adham) — `pipeline/`
- **Código importado:**
  - `pipeline/src/cells.py: read_elt()` para leer el ELT (le cambio la carpeta en tiempo de ejecución, sin modificar el archivo).
  - `pipeline/src/features.py: LEAKAGE`, para excluir del experimento las columnas con fuga.
- **`data/processed/feat_*.parquet`** (`feat_suelo`, `feat_riesgos`, `feat_infra` y cualquiera nuevo): `site_id` y columnas numéricas. Ganan al ELT si una columna está en ambos.
- **`exclusions_es_3500.parquet`**: `site_id`, `excluded` (booleano), `motivo_descarte` y `avisos` (texto). Los avisos se muestran en la ficha.
- **`finanzas_es_3500.parquet`**: `site_id`, `inversion_eur_m2` (decimal). Se muestra en la ficha.
- **`labels_es_3500.parquet`**: `site_id`, `y` (0/1, datacentermap), `sites` (texto).
- **`scores_es_3500.parquet`**: `site_id`, `score_pct`, `oof_spatial_pct`. Solo para comparar en el panel «Sobre el modelo».
- **`priors_voz.csv`**: `feature` y `monotone` (+1/−1). Restricciones de expertos para la réplica del modelo.
- **`data/raw/dc_sites_es.csv`**: `site, operators, municipio, status, precision, lat, lon`. Puntos de los data centers en el mapa.
- **Cómo se ejecuta su parte:** `pipeline/README.md` (`labels.py`, `feat_*.py`, `features.py`, `train.py`).

### Web (Dani) — `pagina/`
- **Tecnología:** sitio estático (HTML, CSS y JS con MapLibre GL) servido por un *Worker* de Cloudflare con `assets.directory = "."` (`pagina/wrangler.jsonc`). Publicado en `canibuildhere.online`; se sube con `npx wrangler deploy` desde `pagina/`.
- **En local:** `cd pagina && python -m http.server 8000` → `http://localhost:8000/#ES`.
- **Páginas:** `index.html` (vista del mundo, `#ES` España, buscador, panel lateral, ES|EN). Lee `data/ES.json` (GeoJSON propio, `DATA_FORMAT.md`), que **hoy son datos inventados**.
- **Integración (commits `INTEGRACIÓN:`):**
  1. Un enlace «Cribado detallado» en la cabecera (`index.html`) con las clases `boton boton-secundario`, y las claves `ver_cribado` y `ver_cribado_ayuda` en `i18n/es.json` y `i18n/en.json`.
  2. Carpeta nueva `pagina/mapa/`: copia del mapa que genera `src/exportacion.py`. Se despliega con su Worker sin cambiar nada más.
- **Supuesto:** no sustituyo `pagina/data/ES.json`. Usa otra rejilla (43.213 cuadrados UTM con id `ES-xxxxx`, frente a la del ELT), y el `pipeline/README.md` del equipo dice que la nota de la web saldrá del modelo de Cristóbal. Lo decide el equipo; dejo propuesto un adaptador en `CAMBIOS.md`.

## Lo que produce el mapa (para quien quiera usarlo)
- `angel_modelo/salida/salida_celdas.csv` (regenerable, no versionado). Una fila por celda:
  - `site_id, lon, lat, comunidad, provincia, estado` (Candidata / Dudosa / No viable / No evaluable);
  - `score_pct` (percentil de ordenación, vacío si está excluida), `nota_rubrica` (0-100), `cobertura` (0-1), `confianza`;
  - `motivos` (hasta 3 códigos `E:`, `C:`, `-:`, `+:`, `F:`), `exclusiones`, `capas_faltan`;
  - `dc_real, dc_fuente, dc_nombres`.
- `angel_modelo/web_mapa/data/` y `pagina/mapa/data/`: `celdas.json`, `prov/<n>.json`, `dc.json`, `metricas.json`, `esquema.json` e `informe_datos.md`.
