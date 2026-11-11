# LIMPIEZA

**Red de seguridad:** la etiqueta local `backup/pre-limpieza` (no se sube) apunta al último commit de `angel/mapa-web` antes de la limpieza.
- Recuperar un archivo: `git checkout backup/pre-limpieza -- <ruta>`.
- Todo lo de sesiones anteriores está además en la copia `/Users/gallego/hack/copia_seguridad_hackathon_2026-11-10_2328/` (carpeta `angel_modelo/` y `repo.bundle`).

## Criterio
- Un archivo se mantiene si lo usa el pipeline, los tests, la web o el README, o si es un entregable.
- Antes de eliminar o renombrar, se buscó en todo el repositorio que nada lo importara ni lo citara (`git grep`).
- Solo se ha actuado dentro de `angel_modelo/`.

## Se mantiene (inventario final)
| Ruta | Por qué |
|---|---|
| `README.md`, `Makefile`, `requirements.txt`, `.env.example`, `.gitignore` | Instalación, ejecución y secretos |
| `config/columnas.yaml`, `config/rubrica.yaml` | Toda la configuración (nada fijo en el código) |
| `src/actualizar.py`, `configuracion.py`, `carga.py`, `rubrica.py`, `evaluacion.py`, `exportacion.py` | Un módulo por responsabilidad, en orden de ejecución |
| `tests/test_rubrica.py`, `test_contrato.py`, `test_salida.py`, `aceptacion.py`, `verificar_web.mjs` | Pruebas |
| `web_mapa/index.html`, `style.css`, `app.js`, `vendor/leaflet/*`, `functions/api/explicar.js`, `package.json` | Mapa autocontenido (más la función de Claude para Cloudflare Pages) |
| `web_mapa/data/*` (~21 MB) | Resultados finales que el mapa necesita para funcionar nada más clonar; `esquema.json` es además la referencia para detectar cambios en los datos |
| `docs/EXPLICACION_CODIGO.md`, `INTEGRACION.md`, `CAMBIOS.md`, `LIMPIEZA.md` | Entregables |
| `docs/INFORME.md` | Análisis del 9-nov, marcado como **histórico** (algunas conclusiones las han superado los datos, ver `CAMBIOS.md`) |

## Fusionado o sustituido (respecto a la sesión anterior, que está en la copia)
| Antes | Ahora | Motivo |
|---|---|---|
| `datos.py` | `src/carga.py` | Reescrito: alias, deduplicado, rangos, tipos, huella y lectura con `read_elt` del equipo |
| `regenerar.py` | `src/actualizar.py` | Mismo papel; pasos con nombres en español |
| `evaluar.py` | `src/evaluacion.py` | Variables con filtros automáticos; huella; menos réplicas configurables |
| `exportar.py` | `src/exportacion.py` | Informe de datos, esquema publicado, salidas sin marcas de tiempo, geometría por centroide, copia a `pagina/mapa/` |
| `rubrica.py`, `rubrica.yaml` | `src/rubrica.py`, `config/rubrica.yaml` | Activación de capas por cobertura y renormalización |
| `CAMBIOS.md`, `EXPLICACION_CODIGO.md`, `INFORME.md` | `docs/` | Documentación agrupada; reescrita para la estructura nueva |
| `tests/verificar_web.mjs` | igual, más el modo `pagina` | Verifica también la web de Dani y su enlace |

## Eliminado
| Qué | Motivo |
|---|---|
| `.venv/` (492 MB), `web_mapa/node_modules/` (30 MB), `web_mapa/package-lock.json`, `__pycache__/` | Regenerables; ignorados por git |
| `out/` (31 MB) | Intermedios regenerables; ahora `salida/`, ignorada |
| `analisis.py`, `auditoria.py` | Ya se eliminaron en la sesión anterior (sustituidos por la evaluación) |
| `pasos_siguientes.py`, `entrenar.sh`, `columnas_mantener_eliminar.csv` | **No existían** (nunca se crearon); sus funciones están en `carga.py` y `evaluacion.py` |

## Renombrado (un solo idioma)
- Funciones de `src/rubrica.py`: `load_config` → `cargar_config`, `validate` → `validar`, `col` → `columna`, `rule_hit` → `cumple_regla`, `apply` → `aplicar`.
- Funciones de `src/evaluacion.py`: `recall_top` → `recall_superior`, `drop_redundant` → `quitar_redundantes`, `oof` → `predecir_fuera_de_pliegue`, `boot` → `bootstrap_provincias`, `ci` → `intervalo95`, `calib` → `calibracion`.
- Las funciones de `web_mapa/app.js` (`init`, `draw`, …) siguen en inglés: es la convención del código JavaScript y de Leaflet, y no se exportan.
- La rama se reconstruyó desde `origin/pipeline`, así que los cambios de carpeta (`*.py` → `src/`, `*.yaml` → `config/`, `*.md` → `docs/`) aparecen como archivos nuevos y no como `git mv`. La correspondencia está en la tabla «Fusionado o sustituido».

## Comprobación tras la limpieza
Ver `CAMBIOS.md`, sección 5: tests y prueba de aceptación repetidos después de la limpieza.

## Limpieza del 11-nov-2026
- **Eliminado** (generado y sustituido): `web_mapa/data/{celdas.json, dc.json, esquema.json, informe_datos.md, metricas.json, prov/}` en la raíz de `data/`. Ahora va por país en `web_mapa/data/<pais>/` más `data/paises.json`. El esquema y las métricas publicados se movieron a `data/es/` antes de borrar, para conservar la comparación.
- **Movido:** `pagina/mapa/` → `Web/mapa/` (reorganización del equipo; commit «INTEGRACIÓN:»).
- **Nuevo:**
  - `config/paises/{es,jp}.yaml`, `src/militar.py`, `src/sentido.py`, `datos/militar/{esp,jpn}.geojson`;
  - `tests/test_militar.py`, `tests/test_sentido.py`;
  - `docs/{CAMBIOS_DATOS, AUDITORIA_BASES_MILITARES, MEJORAS_MODELO, SENTIDO_RESULTADOS, FUENTES}.md`.
- **Nombres:** sin sufijos (`_v2`, `_final`, …), en minúsculas y snake_case. Los `.geojson` militares se nombran por ISO3 en minúsculas (`esp`, `jpn`), igual que los archivos del ETL.
- **Restos borrados fuera de la carpeta, generados por mí:** `ELT/` y `pipeline/` con solo `__pycache__`, sin versionar.
