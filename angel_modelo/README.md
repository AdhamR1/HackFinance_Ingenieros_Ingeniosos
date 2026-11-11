# Mapa de cribado de emplazamientos para data centers (España y Japón)

Mapa web interactivo que clasifica cada celda de 3,5 × 3,5 km de **España y Japón** (un perfil por país en `config/paises/`) en **Candidata / Dudosa / No viable / No evaluable** para construir un data center. Para cada celda muestra los motivos de la decisión, la confianza (parte del peso con datos) y un percentil de ordenación. Está enlazado desde la web del equipo («Cribado detallado» → `Web/mapa/`) y también funciona por separado. Selector de país con carga perezosa (solo se descarga el país elegido); el percentil se calcula **dentro** de cada país.

> **Cribado inicial.** No es un estudio geotécnico ni una clasificación urbanística. La puntuación es una ordenación, no una probabilidad.

- **Quién decide:** una rúbrica transparente (`config/rubrica.yaml`) con exclusiones, condicionantes y criterios ponderados.
- **Qué se ha medido:** con validación espacial por provincias, un modelo entrenado (réplica del LightGBM del equipo) **no** supera a una regresión de 2 variables. Por eso **no alimenta el mapa** (panel «Sobre el modelo»).
- **Dinámico:** si cambian los datos, basta con un comando para regenerar el mapa, sin tocar código (ver «Qué pasa cuando cambian los datos»).

## Requisitos
- Python ≥ 3.11 (probado con 3.15). No necesita LightGBM ni `libomp`.
- Un navegador moderno. Opcional: Node ≥ 22 y Google Chrome para las pruebas del navegador.

## Instalación (una vez, desde la raíz del repositorio)
macOS / Linux:
```bash
python3 -m venv angel_modelo/.venv
angel_modelo/.venv/bin/pip install -r angel_modelo/requirements.txt
```
Windows (PowerShell):
```powershell
py -3 -m venv angel_modelo\.venv
angel_modelo\.venv\Scripts\pip install -r angel_modelo\requirements.txt
```

## Regenerar el mapa (un comando)
```bash
make -C angel_modelo actualizar                        # macOS/Linux, unos 4 min
angel_modelo/.venv/bin/python angel_modelo/src/actualizar.py   # igual, sin make (Windows: angel_modelo\.venv\Scripts\python ...)
```
Pasos sueltos: `actualizar.py carga | rubrica | sensibilidad | evaluacion | exportacion | test`. Con `actualizar.py rapido`, unos 40 s, se hace todo menos reentrenar.

| Paso | Archivo | Qué hace |
|---|---|---|
| militar | `src/militar.py` | Instalaciones militares (OSM) por celda: `militar_pct`, `distancia_militar_km`, `en_franja` |
| carga | `src/carga.py` | Lee `ETL/dataset` con `read_elt` del equipo y las capas de `Modelo/data/processed`; resuelve alias; deduplica; agrega por año; filtra rangos; unifica las listas de data centers; calcula la huella |
| rubrica | `src/rubrica.py` + `config/rubrica.yaml` | Activa las capas con datos y asigna estado, nota, percentil, confianza y motivos |
| evaluacion | `src/evaluacion.py` | Compara rúbrica, logística de 2 variables y réplica del modelo con validación por provincias; escribe `metricas.json` |
| exportacion | `src/exportacion.py` | Genera la salida por celda, `informe_datos.md` y los datos del mapa por país, y copia el mapa a `Web/mapa/` |
| sentido | `src/sentido.py` | Suite de sentido común por país → `docs/SENTIDO_RESULTADOS.md` |

Cada paso corre para cada país (`MAPA_PAISES=es` limita); un país con perfil pero sin datos del ETL se salta con aviso. Los intermedios van a `angel_modelo/salida/<pais>/` (no se versionan). Lo que necesita el mapa (`web_mapa/data/<pais>/` y `Web/mapa/`) sí se versiona, para que funcione nada más clonar.

## Qué pasa cuando cambian los datos
Ejecuta `make -C angel_modelo actualizar` y revisa `angel_modelo/salida/informe_datos.md` (también se publica en `web_mapa/data/`).
- **Columnas nuevas:** se clasifican y se listan. **No cambian el mapa** hasta que las registres en `config/rubrica.yaml`. Si pasan los filtros automáticos (no son identificador, no son constantes, tienen ≥ 60 % de datos y no hay fuga), entran en el experimento del modelo y se listan para que alguien decida.
- **Una capa vacía que se rellena** (por ejemplo `water_stress`): se activa sola cuando su cobertura llega al 60 % (`cobertura_minima_capa`). Sube la confianza y se aplican sus reglas.
- **Columnas que desaparecen, se renombran o llegan vacías:**
  - el criterio se omite con aviso, los pesos se reparten entre los demás y baja la confianza;
  - los nombres alternativos se declaran en `config/columnas.yaml` (`alias`);
  - solo es **error fatal** que falten el identificador, las coordenadas o la carpeta de datos.
- **Filas:** sin límites fijos. Los duplicados (misma celda y fecha) se resuelven quedándose con la última fila; los valores imposibles pasan a «sin dato».
- **Otra rejilla:** si los ids no siguen el patrón configurado o el centroide no cuadra con el tamaño de celda, el mapa dibuja cuadrados desde el centroide.
- **El mapa avisa** («Los datos han cambiado») y muestra en el pie la fecha y la huella de los datos. Con los mismos datos, dos ejecuciones dan archivos idénticos.

## Restricción militar
- **Capa:** huella de instalaciones de OpenStreetMap (`datos/militar/<iso>.geojson`). Para actualizarla: `MAPA_PAIS=es python angel_modelo/src/militar.py descargar`.
- **Reglas** (`config/paises/<pais>.yaml`):
  - ≥ 50 % de la celda militar → **excluida**;
  - cualquier solape o franja (500 m en España, Ley 8/1975; 1.000 m en Japón como proxy de área vigilada, Ley 84/2021) → **condicionante** que impide ser Candidata;
  - sin capa → «restricción militar no verificada» y −5 % de confianza.
- Umbrales y franjas son SUPUESTOS; la huella física no es el perímetro legal. Auditoría en `docs/AUDITORIA_BASES_MILITARES.md`.

## Añadir un tercer país (sin tocar código)
1. Que el ETL del equipo tenga el país: un perfil en `ETL/config.yaml` (`country_profiles`) y sus `ETL/dataset/*/<ISO>-p*.parquet`.
2. Crear `config/paises/<xx>.yaml` copiando `jp.yaml`:
   - `pais`, `iso2`, `nombre`, `etiqueta_division`, `admin`, `alias` de columnas con otro nombre, `tablas`/`subcarpeta_procesados` y `atribucion`;
   - `militar.buffer_m` y las `reglas` legales propias, cada una con su motivo y base normativa.
3. `MAPA_PAIS=xx python angel_modelo/src/militar.py descargar` (capa militar de OSM).
4. `make -C angel_modelo actualizar`: el país aparece en el selector del mapa.
   - Las capas que no tenga se omiten con aviso;
   - si la confianza queda baja, el mapa muestra la ordenación provisional.

## Ver la web con el mapa en local
```bash
make -C angel_modelo servir-web       # = cd Web && python -m http.server 8000
```
Abre `http://localhost:8000/#ES` y pulsa **«Cribado detallado»** (arriba a la derecha), o ve directamente a `http://localhost:8000/mapa/` (Japón: `http://localhost:8000/mapa/#pais=jp`). Solo el mapa: `make -C angel_modelo servir` → `http://localhost:8001`.

## Probar
```bash
angel_modelo/.venv/bin/python -m pytest -q angel_modelo/tests      # rúbrica, contrato, salida, militar y sentido común (~15 s)
angel_modelo/.venv/bin/python angel_modelo/tests/aceptacion.py     # 9 escenarios sobre copias temporales (~30 min)
node angel_modelo/tests/verificar_web.mjs http://localhost:8001/   # el mapa en Chrome headless
MODO=pagina EXIGE_ENLACE=1 node angel_modelo/tests/verificar_web.mjs http://localhost:8000/#ES   # web del equipo + enlace + mapa
```
Escenarios de aceptación:
1. Datos actuales.
2. Columnas nuevas y una capa vacía rellena (sintética).
3. Columna que falta, tipo cambiado, duplicados e imposibles.
4. Dos ejecuciones idénticas.
5. Sin capa militar.
6. Capa militar vacía.
7. Solo España.
8. Japón con capas parciales y un CSV en CP932.
9. La huella de España coincide con la publicada.

## Desplegar
- **Dentro de la web del equipo (lo previsto):** el mapa ya está en `Web/mapa/`. Dani lo publica como siempre: `cd Web && npx wrangler deploy`. Allí el botón «Explicar esta celda» usa la plantilla sin IA, porque el Worker solo sirve archivos.
- **Por separado, en Cloudflare Pages, con la explicación por Claude:**
  1. Root directory `angel_modelo/web_mapa`, build command `npm install`, output `.`.
  2. Secreto `ANTHROPIC_API_KEY` y, opcionalmente, `CLAUDE_MODEL` (por defecto `claude-sonnet-5-5`).
  3. Recomendado: una regla de Rate Limiting en `/api/*`.
- **Mapa base:** teselas estándar de OpenStreetMap, con atribución. Si hay mucho tráfico, define `window.TILE_URL` con otro proveedor.

## Estructura
```
angel_modelo/
  README.md  Makefile  requirements.txt  .env.example  .gitignore
  config/    columnas.yaml (rutas, alias, rangos, rejilla) · rubrica.yaml (reglas y pesos)
  config/paises/  es.yaml · jp.yaml (perfil y reglas legales de cada país)
  datos/     militar/<iso>.geojson (capa OSM con fuente y fecha)
  src/       actualizar.py · configuracion.py · militar.py · carga.py · rubrica.py · evaluacion.py · exportacion.py · sentido.py
  tests/     test_rubrica.py · test_contrato.py · test_salida.py · test_militar.py · test_sentido.py · aceptacion.py · verificar_web.mjs
  web_mapa/  index.html · style.css · app.js · vendor/leaflet · data/ · functions/api/explicar.js
  docs/      EXPLICACION_CODIGO.md · INTEGRACION.md · CAMBIOS.md · CAMBIOS_DATOS.md · AUDITORIA_BASES_MILITARES.md ·
             MEJORAS_MODELO.md · SENTIDO_RESULTADOS.md · FUENTES.md · LIMPIEZA.md · INFORME.md (histórico)
```

## Fuentes y licencias
OpenStreetMap (ODbL), CORINE Land Cover 2018 y Natura 2000 (Copernicus / EEA), SNCZI (MITECO), PGA a 475 años (IGN), E-OBS, Copernicus DEM, datacentermap.com y PeeringDB. Leaflet 1.9.4 (BSD-2, `web_mapa/vendor/leaflet/LICENSE`). E-OBS, GEM y UICN tienen licencias no comerciales: valen para el hackathon, no para un producto.
