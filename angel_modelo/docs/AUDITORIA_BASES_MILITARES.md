# Auditoría: ¿tienen las bases e instalaciones militares un control y una restricción EXPLÍCITOS?

Fecha: 11-nov-2026. Búsqueda en todo el repositorio (código, configuración, web, tests, documentación y esquemas de los Parquet) de `militar, military, defensa, defence, cuartel, base aérea, base naval, polvorín, campo de tiro, zona de seguridad, servidumbre, 8/1975, 689/1978, landuse=military, military=, 自衛隊, 米軍, 防衛, 注視区域, 特別注視区域`.

## ANTES (rama tras traer lo nuevo del equipo, `b2352e3`)

| Criterio | España | Japón |
|---|---|---|
| (a) DATO | **PARCIAL**: `dist_military_km` y `dist_military_airbase_km` (ETL, OSM `landuse=military` medido al **centro** de cada polígono, `ETL/dclake/collectors/osm.py:46,344`), cobertura 100 %. Ni huella ni % de la celda | **NO**: las mismas columnas existen con **cobertura 0 %** |
| (b) REGLA | **NO**: ninguna exclusión ni condicionante. Solo es variable del modelo y texto de motivo en la web del equipo (`Modelo/src/exportar_web.py:158`) | **NO** |
| (c) EFECTO | **NO** (ningún test) | **NO** |
| (d) TRANSPARENCIA | **NO** en el mapa de cribado; en la web principal, solo «Zona militar a X km» como motivo | **NO** |
| (e) CONTROL | **NO** (sin alerta si la capa falta o cae) | **NO** |
| **Global** | **PARCIAL (dato sin regla)** | **NO** |

## DESPUÉS (esta rama)

| Criterio | España | Japón | Evidencia |
|---|---|---|---|
| (a) DATO | **SÍ**: 1.236 polígonos OSM (huella), descargados el 11-nov-2026; 913 km²; 722 celdas con instalación, 1.098 en la franja de 500 m | **SÍ**: 670 polígonos OSM; 617 celdas con instalación, 1.044 en la franja de 1.000 m | `src/militar.py`, `datos/militar/{esp,jpn}.geojson`, `docs/FUENTES.md` |
| (b) REGLA | **SÍ**: exclusión `militar_pct ≥ 50 %` y condicionante «Requiere autorización del Ministerio de Defensa (Ley 8/1975)» que impide ser Candidata | **SÍ**: exclusión `militar_pct ≥ 50 %` y condicionante «Posible área vigilada (Ley 84/2021)…» con proxy de 1.000 m | `config/paises/es.yaml`, `config/paises/jp.yaml` |
| (c) EFECTO | **SÍ**: tests dentro, parcial, franja, lejos y capa ausente (y aceptación sin capa y con capa vacía) | **SÍ**: mismos tests (se aplican con el perfil del país) | `tests/test_rubrica.py::test_militar_*`, `tests/test_militar.py`, `tests/aceptacion.py` (E5, E6) |
| (d) TRANSPARENCIA | **SÍ**: capa opcional «Instalaciones militares», leyenda, ficha «Excluida / Condicionada / Sin efecto / No verificado», fuente y fecha, y aviso de que la huella no es el perímetro legal | **SÍ** (igual, con «designación no verificada») | `web_mapa/app.js` (drawMil, ficha), `meta.militar` |
| (e) CONTROL | **SÍ**: `informe_datos.md` con nº de polígonos, área y celdas; alerta si llega vacía o cae > 20 % (configurable); sin capa → «no verificada» y −5 % de confianza | **SÍ** | `src/exportacion.py`, `config/paises/*.yaml: militar.caida_alerta_pct` |
| **Global** | **SÍ** | **SÍ (con proxy; designaciones oficiales no verificadas)** | |

Comprobación con un caso real: ver `docs/CAMBIOS_DATOS.md` (423 celdas de España cambian de estado por la regla; ningún data center real queda excluido en España).

## Base normativa y lo que NO se afirma
- **España.** Ley 8/1975, de 12 de marzo, de zonas e instalaciones de interés para la Defensa Nacional, y Reglamento (RD 689/1978):
  - zonas de interés para la Defensa Nacional;
  - zonas de seguridad (próxima y lejana), que Defensa delimita **instalación a instalación** por orden publicada en el BOE;
  - zonas de acceso restringido a la propiedad por parte de extranjeros.

  Las obras en zonas de seguridad requieren autorización de Defensa. El **artículo exacto está POR VERIFICAR** en el BOE antes de citarlo; no se cita número. Las delimitaciones del BOE no están en un formato geográfico abierto: se usa la huella OSM + 500 m (SUPUESTO).
- **Japón.** Ley n.º 84 de 2021 (重要施設周辺及び国境離島等における土地等の利用状況の調査及び利用の規制等に関する法律):
  - áreas vigiladas (注視区域, ~1.000 m) y especialmente vigiladas (特別注視区域), designadas **una a una por anuncio oficial**, así que no todo el entorno de toda instalación está designado;
  - aquí se usa un **proxy de 1.000 m** y la ficha dice «designación no verificada»;
  - **proyecto de ley de autorización previa** (aprobado por el Gobierno en octubre de 2026): **estado legislativo NO verificado** a 11-nov-2026, **no se modela**.
- **La huella física de OSM NO es el perímetro legal.** OSM puede estar incompleto y algunas instalaciones sensibles pueden no figurar; no se deduce ninguna instalación que no aparezca en fuentes públicas.
- **No modelado:** zonas de acceso restringido a la propiedad por parte de extranjeros (España). Relevante para inversores extranjeros; vigencia por verificar.

## Conclusión
1. Antes, la restricción militar no era explícita en ningún país: España tenía solo una distancia al centro de las zonas, sin regla ni efecto.
2. Ahora es explícita y configurable por país: excluye si la instalación ocupa ≥ 50 % de la celda y condiciona cualquier solape o cercanía (sin poder ser Candidata).
3. Sin capa, la restricción queda «no verificada» y baja la confianza; nunca se trata como «sin restricción».
4. Los umbrales (50 %, 500 m y 1.000 m) son SUPUESTOS que deben sustituirse por las delimitaciones oficiales (BOE y kokuji) cuando estén disponibles.
5. Ningún data center real queda excluido en España. En Japón queda 1 excluido (`JPN_-257_-289`), probablemente un caso legítimo o un error de la capa, que hay que revisar a mano.

## Ajuste decidido el 11-nov-2026 (opción 2: criterio legal y físico, no ajustado a los data centers)
Primera versión: cualquier recinto OSM (o su franja) condicionaba, y la exclusión se aplicaba desde el 50 %. Así quedaban condicionados 41 de los 131 data centers reales de España, casi todos junto a cuarteles urbanos pequeños.

**Cambio.** La franja y el bloqueo de la etiqueta Candidata solo cuentan para **instalaciones con entidad**: `military=base|airfield|naval_base|range|training_area|ammunition`, o recintos sin tipo de **5 ha o más** (SUPUESTO). Los recintos menores solo generan un **aviso** (`militar_menor`). La exclusión pasa a **≥ 90 %** de la celda, como la regla de agua del equipo.

| | España antes → después | Japón antes → después |
|---|---|---|
| Polígonos con entidad / total | — / 1.236 → 433 / 1.236 | — / 670 → 398 / 670 |
| Celdas excluidas | 45 → 13 | 47 → 10 |
| Celdas condicionadas (no pueden ser Candidata) | 1.053 → 608 | 997 → 954 |
| Celdas con solo aviso | — → 477 | — → 80 |
| Data centers reales excluidos | 0 → 0 | 1 → 0 (Ginoza/Nago, Okinawa: ahora condicionado) |
| Data centers reales condicionados | 41 → 29 (+12 con aviso) | 14 → 14 (+1 con aviso) |

- **España:** los 29 condicionados están junto a instalaciones con entidad (bases aéreas de Getafe y Torrejón, Cádiz, Ceuta, Mahón…): es plausible que requieran una consulta a Defensa.
- **Japón:** muchos data centers de Tokio quedan a menos de 1.000 m de instalaciones de las Fuerzas de Autodefensa o de EE. UU. La franja es un proxy de 注視区域 y la ficha dice «designación no verificada».
- Los umbrales (5 ha, 90 %, 500 m y 1.000 m) siguen siendo SUPUESTOS hasta disponer de las delimitaciones oficiales.
