# Qué ha cambiado en los datos (11-nov-2026)

## Lo que ha traído el equipo (`git merge --no-ff origin/main` en `angel/mapa-viabilidad`, sin conflictos)
| Commit | Autor | Qué |
|---|---|---|
| `9b6e914` | Cristóbal | Datos reales en la web: `ES.json` desde el modelo (nota, descartes, permisos, motivos e indicadores) |
| `4ea1ca4` | Cristóbal | Mejoras en las ubicaciones de los data centers y en la nota de la web |
| `31211bb` | Adham | Configuración final de subida al data lake (Azure) |
| `002de80` | Adham | Japón en el modelo (`DC_COUNTRY`), data lake en Azure, subida de `pipeline/data/processed` |
| `3bc665f`, `32e888d` | Adham | **Reorganización `ELT/` → `ETL/`, `pipeline/` → `Modelo/`, `pagina/` → `Web/`**; Japón en el modelo y en la web |

- La base era `origin/main`, que contiene `origin/pipeline`. Las carpetas del equipo, no la rama «Pipeline», eran las que había que leer.
- Datos de **Japón ya subidos por el equipo**: `ETL/dataset/*/JPN-p*.parquet` (30.779 celdas, 256 columnas) y `Modelo/data/processed/JPN/` (suelo, parques, infraestructura eléctrica, exclusiones y 138 data centers en `Modelo/data/raw/dc_sites_jp.csv`). **Se usan como base; no se duplican.**
- **Adaptación solo de configuración:**
  - rutas nuevas en `config/columnas.yaml`;
  - perfiles `config/paises/{es,jp}.yaml`;
  - la proyección de cada país se lee de `ETL/config.yaml`;
  - la subcarpeta `JPN/` (convención del equipo) va en el perfil.
- **Mi integración se ha movido** de `pagina/mapa/` a `Web/mapa/` (commit `INTEGRACIÓN:`). El enlace «Cribado detallado» se conservó solo en `Web/index.html` y en `Web/i18n/`, por la detección de renombres de git.

## España: esquema y estados
- **Esquema:** sin columnas desaparecidas ni cambios de tipo, rango o cobertura respecto a lo publicado. Columnas nuevas: `militar_pct`, `distancia_militar_km` y `en_franja` (las de la capa militar, ver abajo).
- **Data centers:** datacentermap 100 celdas, OSM/PeeringDB 63, en la misma celda 20 (antes 21, por las mejoras de ubicación de Cristóbal). **Lista maestra por distancia: 131 celdas.** Hay 12 celdas OSM/PeeringDB a menos de 3,5 km de un punto de datacentermap: son el mismo centro, contado dos veces en la unión por celdas.
- **Cambios de estado** (descomposición con la misma rúbrica, paso a paso):

| Paso | Candidata | Dudosa | No viable | No evaluable | Celdas que cambian |
|---|---|---|---|---|---|
| Antes (rama publicada, `3585f83`) | 3.393 | 4.092 | 33.810 | 1 | — |
| + datos nuevos del equipo | 3.393 | 4.092 | 33.810 | 1 | **0** (sus cambios no tocan las entradas de la rúbrica) |
| + regla militar | 3.140 | 4.086 | 34.069 | 1 | **423**: 164 Candidata→Dudosa, 89 Candidata→No viable, 170 Dudosa→No viable |
| + centro urbano denso (≥ 80 %) | 3.138 | 4.088 | 34.069 | 1 | 2 Candidata→Dudosa |
| + confianza mínima para Candidata | 3.138 | 4.088 | 34.069 | 1 | 0 |
| + agua dominante (≥ 50 %, suite de sentido común) | **3.136** | **4.090** | **34.069** | **1** | 2 Candidata→Dudosa (embalses en Palencia y Zaragoza) |

Huella de España **antes**: `salida_celdas.csv` = `d0d8fa52d92c8305`. Después cambia **solo** por las filas de esta tabla. Añadir Japón no altera ni un resultado de España: lo comprueba el escenario 9 de la prueba de aceptación.

## Japón (primera ejecución)
- 30.779 celdas y 47 prefecturas.
- Resultado: 0 Candidatas, 621 Dudosas, 30.041 No viables, 117 No evaluables. Ver `docs/MEJORAS_MODELO.md` y `docs/SENTIDO_RESULTADOS.md`.
- Capas omitidas por falta de datos (cobertura 0): `agua`, `corredor_fibra`, `estres_hidrico`, `inundacion`, `control_urbanizacion` y `sedimentos` (las dos últimas, PENDIENTES de MLIT).
- La cobertura de todas las celdas queda en 0,82 < 0,85: **ninguna celda puede ser Candidata** y el mapa arranca en «Ordenación provisional (datos incompletos)».

### Ajuste de la regla militar (opción 2, decidida con el usuario el 11-nov-2026)
- Solo las instalaciones con entidad generan franja y bloqueo; la exclusión pasa a ≥ 90 %. Detalle en `AUDITORIA_BASES_MILITARES.md`.
- **Estado final de España:** **3.219 Candidatas**, 4.125 Dudosas, 33.951 No viables, 1 No evaluable. Frente a la tabla anterior: +83 Candidatas que la versión primera bloqueaba solo por recintos menores.
- **Japón:** 0 Candidatas, 624 Dudosas, 30.032 No viables, 123 No evaluables.
