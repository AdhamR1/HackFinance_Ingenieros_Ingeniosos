# CAMBIOS

Rama de trabajo `angel/mapa-web` (local) → rama publicada `angel/mapa-viabilidad`, ambas a partir de `origin/pipeline` @ `d04c225` (10-nov-2026 23:28), que contiene todo `origin/main` @ `9ad03cf`.

## 0. Reinicio seguro (10-nov-2026, 23:28)

**Estado inicial:**
- Árbol limpio, sin stash y sin `.env` en el repositorio.
- 9 commits locales sin publicar en la antigua `angel/mapa-web` (sesión anterior).
- `main` local estaba 58 commits por detrás de `origin/main`.
- `angel_modelo/` ocupaba 579 MB, de los que 492 MB eran `.venv`, 31 MB `out/` y 30 MB `node_modules`.

**Copia de seguridad (verificada)** en `/Users/gallego/hack/copia_seguridad_hackathon_2026-11-10_2328/`:
- `angel_modelo/`: 92 archivos, sin `.venv` ni `node_modules`.
- `repo.bundle`: 550 MB, todas las ramas; `git bundle verify` → *okay*.
- No había `.env` que copiar.
- Restaurar todo: `git clone /Users/gallego/hack/copia_seguridad_hackathon_2026-11-10_2328/repo.bundle restaurado`.
- Restaurar una rama: `git fetch <ruta>/repo.bundle angel/mapa-web:angel/mapa-web-restaurada`.

**Reinicio:**
1. `git fetch --all --prune`.
2. Borrado de `angel_modelo/` local, incluidos `.venv`, cachés y salidas.
3. `main` y `angel/modelo` avanzadas solo por fast-forward hasta `origin/main`.
4. La antigua `angel/mapa-web` se renombró en local a `angel/mapa-web-sesion-anterior`: sus commits no estaban en origin y además están en el bundle. No se ha borrado.
5. Nueva rama local `pipeline` siguiendo `origin/pipeline`; `git status` limpio.
6. `angel/mapa-web` creada desde ahí.
- Ningún cambio de otras personas sin guardar (no hizo falta `git stash`).

**Rescate** (desde la copia, adaptado):
- `rubrica.yaml` → `config/rubrica.yaml` y `rubrica.py` → `src/rubrica.py`.
- `evaluar.py` → `src/evaluacion.py`; `exportar.py` → `src/exportacion.py`.
- `datos.py` → reescrito como `src/carga.py`.
- `web_mapa/`, `tests/test_rubrica.py`, `tests/test_salida.py`, `tests/verificar_web.mjs` e `INFORME.md` (→ `docs/`).
- **`analisis.py`, `pasos_siguientes.py`, `entrenar.sh` y `columnas_mantener_eliminar.csv` no existían** en la copia: `analisis.py` se sustituyó por `evaluar.py` en la sesión anterior, y los otros tres nunca se crearon. Lo que hacían `unificar_listas` y `backtest_rubrica` está en `src/carga.py` y `src/evaluacion.py`.

## 1. Reconocimiento (quién ha hecho qué, según `git log origin/pipeline`)
1. **dani99992 (Dani), 29 commits**: la web `pagina/`.
   - Tecnología: MapLibre GL, buscador Photon, ES|EN, datos de prueba con `herramientas/generar_datos_prueba.mjs`.
   - Publicación: Worker de Cloudflare con `wrangler.jsonc` (`canibuildhere.online`).
2. **AdhamR1 / Adham El Amrani, 19 commits**: el ELT (`ELT/dclake`, colectores, rejilla 3,5 km EPSG:3035), los datos `ELT/dataset` (ESP 2010-2025, JPN), los riesgos (SNCZI, PGA del IGN), las restricciones de expertos (ElevenLabs) y `scores` para la web.
3. **Cristobal (Cristóbal), 12 commits**: `pipeline/`: target (`labels.py`), suelo y exclusiones (`feat_suelo.py`), red eléctrica (`feat_infra.py`), riesgos, finanzas, `train.py` (LightGBM PU, bloques de 70 km, SHAP) y gráficas.
4. **dmar1400, 9 commits**: `ELT/dclake/upload.py` (Azure Data Lake), configuración, CI con ruff y `pipeline/requirements.txt`. *Deduzco* que es Desi (el reparto le asigna el data lake); no lo sé seguro.
5. **Angel-522414 (tú), 1 commit en `main`**, más este trabajo.

Otras comprobaciones:
6. **Ramas:** `origin/main` @ `9ad03cf` ⊂ `origin/pipeline` @ `d04c225`. La base es `pipeline`.
7. **Datos:** `ELT/dataset/` y `pipeline/data/processed/` son Parquet reales (sin LFS); el mayor tiene 18 MB.
8. **Entrenamiento del equipo:** `pipeline/src/train.py`; el orden de ejecución está en `pipeline/README.md`.
9. **Web:** `pagina/` (HTML, CSS y JS). En local: `cd pagina && python -m http.server 8000` → `/#ES`. Una sola página (`index.html`: vista del mundo, España, panel y buscador). Hoy pinta `data/ES.json` **inventado**, con otra rejilla (43.213 cuadrados UTM).
10. **Tests existentes:**
    - `pipeline/tests`: 7 aprobados, 1 omitido.
    - `ELT/tests`: 29 aprobados, 2 omitidos. Necesitan `shapely`, `geopandas` y `openpyxl`, instalados solo en `angel_modelo/.venv` para ejecutarlos.
    - CI: `.github/workflows/ci.yml` (ruff + tests, con checkout parcial que no incluye `angel_modelo/`).
11. **Pruebas de la web de Dani:** `pagina/herramientas/pruebas/probar.mjs` tiene escrita a mano la ruta de Chrome en Windows (`C:/Program Files/...`) y no corre en macOS. **No lo he modificado**: verifico su web con `tests/verificar_web.mjs` (`MODO=pagina`).
12. Los datos desmienten «el cuello de botella son los datos»: red eléctrica, PGA, inundación, espacios protegidos y autovías ya están. Siguen faltando fibra, estrés hídrico y capacidad de red por nudo.
13. Se confirma con los datos de hoy: la logística de 2 variables (PR-AUC 0,29) supera a la réplica del modelo del equipo (0,17), validando por provincias.
14. Las listas de DC no coinciden (100 frente a 63 celdas, 21 en común): se unifican por celda (142).
15. **Secretos:** ninguno en el árbol ni en el historial de ninguna rama (búsqueda de patrones de claves de Anthropic, AWS, Azure y tokens).

## 2. Cambios en archivos de otras personas (todos en commits «INTEGRACIÓN:»)
| Archivo | Antes | Después | Motivo | Revisa |
|---|---|---|---|---|
| `pagina/index.html` | Cabecera: selector de país e idiomas | + 1 línea: `<a href="mapa/" class="boton boton-secundario" data-i18n="ver_cribado" …>Cribado detallado</a>` | Acceso al mapa desde la página principal con su estilo y su sistema de traducción | Dani |
| `pagina/i18n/es.json`, `en.json` | — | + `ver_cribado`, `ver_cribado_ayuda` (ES y EN) | Texto del enlace en los dos idiomas | Dani |
| `pagina/mapa/` (**nuevo**) | — | Copia generada del mapa (`src/exportacion.py`) | Que se despliegue con su Worker sin cambiar su configuración. No modifica nada existente | Dani |

- Comprobado antes y después con `MODO=pagina node angel_modelo/tests/verificar_web.mjs`: 0 errores de consola. Después, el enlace lleva a `/mapa/`, que dibuja 40.691 celdas.
- Los tests de `pipeline/` y `ELT/` dan el mismo resultado antes y después: no toco esos archivos.
- **Propuesta no aplicada (decide el equipo):** adaptador que escriba `pagina/data/ES.json` con la nota de la rúbrica en el formato `DATA_FORMAT.md`. Requiere cruzar las dos rejillas (UTM de 43.213 cuadrados frente a EPSG:3035 de 41.296) por el centroide. Hoy el `pipeline/README.md` del equipo prevé que esa nota salga del modelo de Cristóbal.

## 3. Qué se ha añadido, cambiado y eliminado en `angel_modelo/`
Detalle de lo que se mantiene, fusiona, elimina y renombra: `docs/LIMPIEZA.md`. Novedades de esta sesión:
- **Robustez ante cambios de datos:**
  - `config/columnas.yaml`: rutas, alias, rangos plausibles, rejilla, agregación temporal y filtros del experimento.
  - Activación de capas por cobertura y renormalización de pesos.
  - `informe_datos.md`, huella de datos, aviso «los datos han cambiado» y geometría por centroide si cambia la rejilla.
  - Salidas sin marcas de tiempo, para que dos ejecuciones iguales den archivos idénticos.
- **Lectura con el código del equipo:** `read_elt` y `LEAKAGE`.
- **Capa `water_stress` registrada**, con peso 4 (se resta 2 de `latencia` y 2 del proxy de precipitación). Hoy está vacía: se omite con aviso y se activará sola.
- **Tests:** `test_contrato.py`, `aceptacion.py` (4 escenarios) y modo `pagina` en `verificar_web.mjs`.
- **Integración en la web de Dani** (sección 2).

## 4. Supuestos
- **S1.** Base `origin/pipeline` (no «Pipeline»): contiene `main`, los datos, el pipeline y la web.
- **S2.** No sustituyo `pagina/data/ES.json` (otra rejilla; decisión del equipo). El mapa se integra como página propia en `pagina/mapa/`.
- **S3.** Target de validación = unión de las dos listas de DC (142 celdas).
- **S4.** `umbral_candidata = 75` (cribado selectivo, ~8 % de España). Todos los pesos y tramos marcados como SUPUESTO en `config/rubrica.yaml` son criterio propio razonado con percentiles: por validar con alguien del sector.
- **S5.** Una capa se activa con ≥ 60 % de cobertura (`cobertura_minima_capa`). Un dato que falta en una celda puntúa 40/100 (pesimista, nunca 0).
- **S6.** LightGBM no carga en este Mac (falta `libomp`; comando: `brew install libomp`, **no ejecutado**). El modelo del equipo se replica con `HistGradientBoostingClassifier` de scikit-learn.
- **S7.** Regla de decisión del modelo, fijada antes de ver resultados: debe superar a la rúbrica y a la logística de 2 variables en ≥ 90 % de las réplicas bootstrap. Hoy no lo hace.
- **S8.** Explicación con Claude: modelo por defecto `claude-sonnet-5-5` (vigente según la referencia de la API, noviembre de 2026), configurable con `CLAUDE_MODEL`. Usa el SDK oficial, esfuerzo `low` y reintento automático ante rechazos (`fallbacks: "default"`). En la web de Dani (un Worker de solo archivos) se usa la plantilla sin IA.
- **S9.** No se ha descargado ninguna capa nueva: fibra, estrés hídrico y capacidad por nudo no tienen una fuente abierta lista para esta rejilla. Quedan como «no disponibles» o como capas que se activarán solas.
- **S10.** La prueba de aceptación usa 100 réplicas bootstrap, en vez de 300, para tardar menos.
- **S11.** `dmar1400` = Desi (deducido por el reparto del data lake).
- **S12.** Los datos del mapa se versionan dos veces (`angel_modelo/web_mapa/data/` y `pagina/mapa/data/`, ~21 MB cada una), para que el mapa funcione solo y dentro de la web nada más clonar.

## 5. Prueba de aceptación (`tests/aceptacion.py`, sobre copias temporales)
**Antes de la limpieza: 23/23 comprobaciones OK** en 584 s.

| Escenario | Resultado |
|---|---|
| E1 · datos actuales | termina · mapa sin errores de consola (40.691 celdas dibujadas en ~0,5 s) · sin cambios de esquema · `water_stress` omitida con aviso |
| E2 · columnas nuevas y capa rellena (sintético, solo en la copia temporal) | termina · el informe lista las columnas nuevas · la capa `water_stress` se activa sola · el mapa avisa «los datos han cambiado» |
| E3 · columna desaparecida, tipo cambiado, duplicados e imposibles | termina · `free_cooling_hours` desaparecida y criterio `refrigeracion` omitido con aviso · tipo cambiado de `slope_pct` · 25 duplicados descartados · valores imposibles a «sin dato» |
| E4 · dos ejecuciones con los mismos datos | resultados idénticos byte a byte · mapa sin errores |

**Después de la limpieza (11-nov-2026):**
- Tests: 31/31.
- Aceptación en el árbol de trabajo: **23/23** (577 s).
- **Verificación final en un clon limpio de solo `angel/mapa-viabilidad`**, siguiendo el README:
  - venv + `pip install` → tests (27 aprobados y 4 omitidos porque aún no hay salida);
  - `make -C angel_modelo actualizar` termina y después pasan 31/31;
  - `git status` limpio tras regenerar: los mismos datos dan los mismos archivos;
  - aceptación **23/23** (427 s);
  - ningún archivo supera 50 MB (el mayor: 2,5 MB);
  - ningún secreto en el árbol ni en el historial de la rama;
  - `.gitignore` excluye `.venv/`, `salida/` y `__pycache__/`.

---

# Actualización del 11-nov-2026 (misma rama `angel/mapa-viabilidad`)

## 0. Rama y copia de seguridad
- Estaba en `angel/mapa-web`.
  - La rama de trabajo es `angel/mapa-viabilidad`, que tenía ocupada el *worktree* temporal de la publicación anterior (limpio). Retiré el worktree y cambié de rama sin perder nada.
  - Las dos ramas tenían el mismo árbol: `angel/mapa-viabilidad` (publicada) es la más reciente; `angel/mapa-web` queda solo en local.
- **Copia:**
  - etiqueta local `backup/pre-actualizacion-2026-11-11`;
  - `/Users/gallego/hack/copia_seguridad_2026-11-11/repo.bundle` (`git bundle verify` → okay);
  - resultados de España por celda antes del cambio: `es_resultados_antes.csv`.
- `git fetch --all --prune`; `origin/angel/mapa-viabilidad` ya estaba al día.
- La base con los datos es **`origin/main`**, que contiene `origin/pipeline`. Se fusionó con `git merge --no-ff --no-edit origin/main` (commit `b2352e3`), **sin conflictos**. No hizo falta `git lfs` (no hay punteros).
- Restos sin versionar `ELT/` y `pipeline/` (solo cachés `__pycache__` de mis ejecuciones de tests): borrados.

## Cambios en archivos de otras personas (commits «INTEGRACIÓN:»)
| Archivo | Antes | Después | Motivo | Revisa |
|---|---|---|---|---|
| `pagina/mapa/` → `Web/mapa/` | Mi carpeta generada, en la ruta antigua | Misma carpeta en `Web/mapa/` (regenerada con España y Japón) | La reorganización movió la web a `Web/` y git no movió una carpeta nueva solo mía | Dani |
| `Web/index.html`, `Web/i18n/{es,en}.json` | — | Sin cambios nuevos: el enlace «Cribado detallado» ya llegó con la fusión | — | Dani |

No he tocado nada de `ETL/` ni de `Modelo/`. Tests del equipo: `Modelo/tests` y `ETL/tests` dan lo mismo antes y después de la fusión (ver sección de verificación).

## Supuestos nuevos
- **S13.** La base es `origin/main` (reorganizada por Adham). «Pipeline» era una carpeta, no la rama a seguir.
- **S14.** Para el área de las instalaciones se usa la proyección de igual área de la rejilla del ETL (EPSG:3035 en España y LAEA de Japón), en vez de EPSG:25830 por región. Es métrica, la misma con la que se definen las celdas, y vale igual para Canarias, Baleares, Okinawa e islas remotas (lo prueban los tests).
- **S15.** Capa militar: OSM (`landuse=military` y `military=base|airfield|naval_base|barracks|range|training_area|ammunition`). No existe una capa oficial abierta de Defensa ni de las zonas de seguridad del BOE en formato geográfico (búsqueda en el IDEE/CNIG y datos.gob.es **por verificar**).
- **S16.** Umbrales militares (tras la opción 2): exclusión al **90 %** de la celda; franja de 500 m (España) y de 1.000 m (Japón, proxy de 注視区域), **solo alrededor de instalaciones con entidad** (tipos base, aeródromo, base naval, campo de tiro, maniobras o polvorín, o ≥ 5 ha). Los recintos menores solo avisan. Son SUPUESTOS que deben sustituirse por las delimitaciones oficiales.
- **S17.** Reglas de sentido común nuevas (criterio de cribado, no legal): `urbano_centro` (≥ 80 % urbano) y `agua_dominante` (≥ 50 % agua) impiden ser Candidata; `cobertura_minima_candidata` = 0,85.
- **S18.** Ninguna variante de pesos se adopta (ver `MEJORAS_MODELO.md`).
- **S19.** Japón: la PGA del ETL (GEM) se usa como `pga475_ign_g` por alias, en g. J-SHIS y las capas de MLIT (A29, A33) quedan **PENDIENTES** (ver `FUENTES.md`).
- **S20.** El artículo exacto de la Ley 8/1975 o del RD 689/1978 sobre autorización de obras **no se cita** (por verificar en el BOE). El proyecto de ley japonés de autorización previa **no se modela**: estado no verificado a 11-nov-2026.

## Coherencia de extremo a extremo (tarea 6)
- Los pesos suman 100 y `validar()` lo comprueba al cargar. Cada criterio apunta a una columna; si no existe en un país, se omite con aviso y queda en el informe de ese país. No hay criterios huérfanos.
- **Percentiles:** se calculan **dentro** de cada país y se rotulan así en la ficha y en el panel. Para comparar países se usa la nota absoluta 0-100.
- **Unidades:** PGA en g en los dos países; clima en las unidades del ETL (iguales en los dos).
- **«Sobre el modelo»:** lee las métricas de cada país (`data/<pais>/metricas.json`), con la huella de los datos.
- **Web del equipo:** sigue enlazando al mapa (comprobado en Chrome headless).
- **Contradicciones encontradas y resueltas:**
  - el subtítulo, la etiqueta sísmica («IGN») y la atribución del pie decían España en Japón: ahora salen del perfil;
  - el verificador tenía escritos a mano `ESP_` y «30.000 celdas»: generalizado;
  - el aviso de ordenación provisional se sobrescribía: corregido;
  - los tests de contrato y de salida se saltaban en silencio por las rutas viejas: corregidos.
- **Contradicción abierta (decisión del equipo):** la web principal pinta la nota del modelo de Cristóbal y «Cribado detallado» la de la rúbrica.
