# Cómo funciona el código, explicado desde cero

Para quien nunca ha entrenado un modelo. Los archivos aparecen en el orden en que se ejecutan, incluidos los del equipo que se usan. Cada término técnico se define la primera vez que aparece, con un ejemplo de este proyecto. Las rutas son relativas a la raíz del repositorio y las líneas citadas son las de la rama publicada.

## Mapa de una página

```
 TRABAJO DEL EQUIPO (base, no se duplica)          angel_modelo/ (Ángel)                                 WEB DEL EQUIPO
 ─────────────────────────────────────          ─────────────────────────                              ──────────────
 ELT/dataset/sites_static, sites_yearly ──┐      config/columnas.yaml (rutas, alias, rangos, rejilla)
   (Adham)                                │                  │
 pipeline/src/cells.py: read_elt  ────────┼──► 1 src/carga.py ──► salida/celdas.parquet + informe_carga.json (huella, cambios)
 pipeline/data/processed/feat_*.parquet ──┤                  │
   exclusions, finanzas, labels, scores   │      config/rubrica.yaml (reglas, pesos)
   (Cristóbal, Adham)                     │                  ▼
 pipeline/data/raw/dc_sites_es.csv ───────┘    2 src/rubrica.py ──► salida/rubrica.parquet (estado, nota, motivos)
 pipeline/src/features.py: LEAKAGE ────────► 3 src/evaluacion.py ──► salida/metricas.json (rúbrica vs 2 variables vs modelo)
 pipeline/data/processed/priors_voz.csv ───┘                 ▼
                                               4 src/exportacion.py ──► web_mapa/data/*.json + informe_datos.md
                                                             │                 │
                                                             │                 └── copia ──► pagina/mapa/  ◄── enlace «Cribado detallado»
                                                             ▼                                                  en pagina/index.html (Dani)
                                               salida/salida_celdas.csv
 Orquestador: src/actualizar.py (make actualizar) · Pruebas: tests/ · Explicación con Claude: web_mapa/functions/api/explicar.js
```

**En una frase:** cada celda pasa por unas reglas escritas a mano (la rúbrica), que deciden su estado. Un modelo entrenado se mide aparte y solo entraría en el mapa si demostrara ser mejor que alternativas sencillas; hoy no lo es.

---

## 0. Piezas del equipo que se usan

**`pipeline/src/cells.py` → `read_elt()` (Cristóbal).** Lee todas las partes `ESP-p*.parquet` de una tabla del ELT y las junta.
- *Parquet*: formato de tabla por columnas, comprimido y rápido de leer.
- Se usa **tal cual**: `src/carga.py` solo le cambia la carpeta en memoria (`cells.ELT_DATASET = ...`), sin tocar el archivo.

**`pipeline/src/labels.py` (Cristóbal).** Marca qué celdas tienen un data center según `dc_sites_es.csv` (103 emplazamientos de datacentermap.com).
- *Target* (variable objetivo): lo que un modelo intenta predecir. Aquí, `y = 1` si la celda tiene un data center.

**`pipeline/src/features.py` → `LEAKAGE` (Cristóbal).** Lista de columnas que «hacen trampa».
- *Fuga de datos* (*leakage*): una variable que contiene la respuesta disfrazada. Ejemplo: `dist_ixp_km`, porque los puntos de intercambio de Internet están dentro de data centers.
- `src/evaluacion.py` importa esta lista para que el experimento no las use.

**`pipeline/src/train.py` (Cristóbal).** Modelo LightGBM del equipo.
- *Modelo entrenado*: un programa que aprende reglas a partir de ejemplos. *LightGBM* combina cientos de árboles de decisión pequeños (*gradient boosting*).
- Usa *aprendizaje PU* (positivos frente a no etiquetados): sabemos dónde **hay** data centers, pero no dónde es imposible ponerlos. Una celda sin data center no es «no viable».
- Las *restricciones monotónicas* salen de `priors_voz.py`, que extrae criterios de expertos de grabaciones públicas. Ejemplo: estar más cerca de una subestación nunca puede bajar la nota.

**`pagina/` (Dani).** Web estática con MapLibre, servida por un Worker de Cloudflare. Solo se le ha añadido un enlace y la carpeta `pagina/mapa/` (ver `docs/INTEGRACION.md`).

---

## 1. `src/actualizar.py` — el botón de «hazlo todo»
- **Qué hace.** `main()` (línea 33) ejecuta en orden carga → rúbrica → evaluación → exportación → test, o un solo paso. Si un paso falla, se detiene y dice cuál.
- **Qué tiene en cuenta.** Cada paso corre en un proceso aparte, así que un error no deja datos a medias en memoria. Usa el mismo Python con el que se lanza, por lo que sirve en Windows sin `make`.
- **Alternativa descartada.** Un `Makefile` solo, que no funciona en los Windows del equipo; queda como atajo.
- **Qué podría fallar.** Lanzarlo con un Python sin las dependencias: usa el de `angel_modelo/.venv`.

## 2. `src/configuracion.py` — de dónde salen rutas y parámetros
- `columnas()` (línea 29) lee `config/columnas.yaml`.
- `ruta()` (línea 33) devuelve la ruta configurada o, si existe, la de la variable de entorno `MAPA_<CLAVE>`. Así las pruebas trabajan con **copias** de los datos sin tocar el repositorio.
- `ErrorFatal` (línea 21) es el único tipo de error que para el programa, con un mensaje claro.
- **Por qué.** Regla de oro: nada escrito a mano en el código. Ni nombres de columnas ni «40.000 celdas».

## 3. `src/carga.py` — una fila por celda, aunque los datos cambien
- **`cargar()` (línea 167)**, el orden de trabajo:
  1. **Lee** con `read_elt` del equipo (`_lector_equipo`, línea 39). Si no se puede importar, usa un lector equivalente y lo avisa.
  2. **Comprueba punteros de Git LFS** (`_comprobar_lfs`, línea 61): archivos diminutos que solo dicen dónde está el archivo real. Si los hay, error fatal con el comando `git lfs pull`.
  3. **Resuelve alias** (`_renombrar_alias`, línea 68). Si una columna llega como `longitude`, se lee como `lon`.
  4. **Errores fatales:** solo la falta de identificador (`site_id`), de coordenadas (`lon`, `lat`) o de la carpeta de datos. Todo lo demás es un aviso.
  5. **Convierte texto numérico** (`_a_numero`, línea 86): si `slope_pct` llega como texto «12.5», se convierte a número y se anota como «tipo cambiado».
  6. **Deduplica** (`_dedup`, línea 112): misma celda (y año si existe), y se queda con la última fila.
  7. **Agrega lo anual** a una fila por celda (media de los 16 años, configurable).
  8. **Une las capas del pipeline** `feat_*.parquet`; cualquier archivo nuevo con ese nombre entra solo.
  9. **Unifica las dos listas de data centers.** datacentermap (100 celdas) y OSM/PeeringDB (63) solo coinciden en 21. `dc_real` es la unión (142) y `dc_fuente` dice de dónde viene cada una. Se usa la unión porque con 21 celdas no se puede validar nada.
  10. **Rangos plausibles** (`_rango`, línea 125): un valor imposible (altitud de 99.999 m, distancia negativa) pasa a *NaN* («sin dato») y se cuenta. **Nunca se rellena con 0**: un 0 en una distancia significaría «está aquí mismo».
  11. **Clasifica** cada columna (`_clasificar`, línea 135) como identificador, coordenada, numérica, booleana, categórica, fecha o constante.
  12. **Huella** (`_huella`, línea 158): un *hash* (código corto que cambia si cambia un solo bit) del esquema y de los valores. Con los mismos datos sale la misma huella.
- **`comparar()` (línea 315).** Compara el esquema con el publicado (`web_mapa/data/esquema.json`): columnas nuevas, desaparecidas, con otro tipo, con otro rango o con otra cobertura, y número de filas.
- **Qué podría fallar.** Si cambia el significado de una columna sin cambiar su nombre (por ejemplo, metros en vez de kilómetros), el filtro de rangos solo lo detecta si el valor sale del rango plausible.

## 4. `config/rubrica.yaml` + `src/rubrica.py` — el motor de decisión
- *Rúbrica*: reglas y pesos escritos a mano, como la plantilla de corrección de un examen. Están en un archivo de texto para que cualquiera los cambie sin programar.
- Tres capas:
  1. **Exclusiones** (veto): agua ≥ 90 %, parque nacional ≥ 50 %, zona de flujo preferente ≥ 50 % (las tres del equipo) y pendiente media ≥ 40 %.
  2. **Condicionantes** (restan puntos y avisan): Natura 2000, espacio protegido, zona inundable de 100 años, suelo urbano, servidumbre aeronáutica, costa baja y altitud.
  3. **Criterios ponderados** (pesos que suman 100) con *curva por tramos*: pares (valor, nota). Ejemplo, subestación de 220 kV: a 0-3 km, 100; a 10 km, 70; a 25 km, 30; a 50 km, 0. Entre tramos se interpola en línea recta.
- **`capas_activas()` (línea 88) y `config_efectiva()` (línea 100).** Una capa solo se usa si su columna tiene datos en al menos el 60 % de las celdas.
  - Hoy `water_stress` está vacía: se omite con aviso y su peso (4) se reparte entre los demás criterios.
  - La **confianza** se mide sobre el peso total configurado, así que baja: hoy, cobertura de 0,96.
  - Cuando el equipo rellene la capa, se activa sola.
- **`validar()` (línea 50)** comprueba que los pesos sumen 100, que no haya ids repetidos y que los tramos vayan en orden.
- **`aplicar()` (línea 115)**, el corazón:
  - Es *vectorizada*: opera sobre columnas enteras a la vez (41.296 celdas en ~1 s).
  - Nota = Σ peso × subnota / 100 − penalizaciones.
  - Si a una celda le falta un dato, ese criterio puntúa 40/100 (pesimista: «ante la duda, no viable»).
  - **Estados:**
    - **No evaluable**: cobertura < 70 %.
    - **No viable**: excluida, o nota < 75 − 6.
    - **Candidata**: nota ≥ 75 (≥ 81 si la confianza es baja).
    - **Dudosa**: el resto.
  - `score_pct` es el *percentil de ordenación*: P90 significa «mejor que el 90 % de las celdas no excluidas». **No es una probabilidad.**
  - Los **motivos** son las 3 reglas o criterios de más impacto en la celda.
- **`sensibilidad()` (línea 216).** Mueve pesos, tramos y umbrales y cuenta cuántas celdas cambian de estado. También hace 100 sorteos de pesos al azar (*Dirichlet*: un sorteo de pesos que suman 100, centrado en los pesos base).
- **Por qué una rúbrica.** No existe un dato fiable de «viable / no viable», y un modelo entrenado con los data centers responde a otra pregunta: «¿se parece a donde ya se ha invertido?».
- **Alternativa descartada:** entrenar con etiquetas generadas por la propia rúbrica. Es *circularidad*: el modelo solo copiaría las reglas.
- **Qué podría fallar.** Los pesos son supuestos razonados con percentiles, no normativa; conviene validarlos con alguien del sector.

## 5. `src/evaluacion.py` — ¿aporta algo un modelo?
- **`variables_experimento()` (línea 47).** Elige las variables con filtros automáticos: fuera identificadores, coordenadas, constantes, columnas con menos del 60 % de datos y las de la lista `LEAKAGE` del equipo o con patrones de fuga. Una columna nueva entra sola **al experimento**, nunca al mapa, y queda listada en el informe.
- **`main()` (línea 131)** compara cuatro puntuaciones:
  1. la **rúbrica**;
  2. una **regresión logística** con `urbano_pct` + `industrial_pct`, el modelo más simple (suma ponderada pasada por una curva en S);
  3. una **réplica del modelo del equipo**: `HistGradientBoostingClassifier`, mismo tipo de modelo que LightGBM, con las mismas restricciones de expertos. LightGBM no carga en el Mac de desarrollo porque le falta `libomp` (comando: `brew install libomp`, no ejecutado);
  4. el **azar**.
- Conceptos:
  - *Validación cruzada*: se divide España en 5 trozos, se entrena con 4 y se mide con el que el modelo no ha visto (`predecir_fuera_de_pliegue()`, línea 90).
  - *Validación espacial por provincias*: los trozos son provincias enteras. Así se evita la *autocorrelación espacial* (dos celdas vecinas son casi iguales y el modelo «se copiaría» del vecino).
  - *Semilla fija* (42): los sorteos salen siempre igual, así que el resultado es reproducible.
  - *Desbalance de clases*: 142 positivos entre ~39.000 celdas. `class_weight="balanced"` da más peso a cada positivo.
  - *PR-AUC*: resume lo bien que se ponen arriba los positivos cuando son muy raros; el azar saca ~0,004.
    - *Precisión*: de las celdas que señalo, cuántas tienen data center.
    - *Recall*: de las celdas con data center, cuántas encuentro.
  - *AUC*: probabilidad de que una celda con data center puntúe más que una sin él (0,5 = azar).
  - *Recall en el 5 % superior* (`recall_superior`, línea 78): qué parte de los data centers cae en el 5 % de celdas mejor puntuadas.
  - *Intervalo por bootstrap de provincias* (`bootstrap_provincias`, línea 98): se remuestrean provincias enteras con reemplazo y se recalcula la métrica cada vez.
  - *Calibración* (`calibracion`, línea 123): si el modelo dice 30 %, ¿ocurre el 30 % de las veces? No: dice ~33 % en su 10 % superior y la tasa real es ~3 %. Por eso nada se presenta como probabilidad.
- **Regla de decisión, fijada antes de mirar los resultados.** El modelo entra al mapa solo si supera a la rúbrica **y** a la logística de 2 variables en ≥ 90 % de las réplicas.
- **Resultado:** la logística obtiene PR-AUC 0,29 y el modelo 0,17; P(modelo mejor que ambos) = 0. **No entra.** El modelo aprende «ciudad o polígono industrial».
- Las métricas se guardan con la **huella de los datos**. Si los datos cambian y no se reevalúa, el informe y el panel lo avisan.

## 6. `src/exportacion.py` — de tablas a archivos ligeros para la web
- **`main()` (línea 128)** escribe:
  - la salida por celda (`salida/salida_celdas.csv`);
  - `informe_datos.md` (`_informe`, línea 88);
  - los datos del mapa: `celdas.json` (~2,4 MB, por columnas, con enteros) y `prov/<n>.json` (detalle por provincia, solo al hacer clic);
  - una copia del mapa en `pagina/mapa/`.
- **`_geometria()` (línea 48).**
  - Si los ids siguen el patrón de la rejilla y cuadran con el centroide, guarda una sola vez los *nodos* (esquinas compartidas) de la rejilla en la *proyección* EPSG:3035 (igual área: todas las celdas miden 12,25 km²), pasados a longitud y latitud.
  - Si no cuadran (el equipo ha cambiado de rejilla), reconstruye cuadrados desde el centroide y el tamaño configurado.
- **Sin marcas de tiempo.** La fecha es la de los datos (`_fecha_datos`, línea 82), así que dos ejecuciones iguales dan archivos idénticos (escenario 4 de la prueba de aceptación).
- **Alternativas descartadas.** GeoJSON con polígonos (~40 MB, lento) y sustituir `pagina/data/ES.json` de Dani (otra rejilla, y la decisión es del equipo).

## 7. `web_mapa/app.js` — el mapa
- **`init()` (línea 37).** Crea el mapa *Leaflet* (librería de mapas web, incluida en `vendor/`) sobre teselas de OpenStreetMap.
- **`buildGeometry()` (línea 69) y `buildCentroides()` (línea 95).** Reconstruyen las esquinas de cada celda.
- **`draw()` (línea 191).** Pinta todas las celdas en **un único `<canvas>`** (lienzo de dibujo).
  - Alejado, usa rectángulos (`rectOf`, línea 241), porque rellenar un trazado con 40.000 cuadriláteros tardaba 4,4 s en Chrome sin tarjeta gráfica.
  - De cerca, polígonos exactos.
- **`avisosDatos()` (línea 113).** Muestra «Los datos han cambiado» y las capas omitidas. El pie enseña la fecha y la huella.
- **Accesibilidad:**
  - paleta Okabe-Ito, apta para daltonismo, y **patrones** además del color (puntos en Dudosa, rayas en No viable);
  - teclado: Intro selecciona la celda del centro, y hay una lista de mejores celdas y botones de celdas vecinas;
  - la ficha se anuncia a los lectores de pantalla (`aria-live`).
- **`renderFicha()` (línea 402)**: estado, percentil («no es probabilidad»), nota, confianza, media provincial, motivos con su valor, datos usados y que faltan, avisos del equipo y estimación financiera.
- **`search()` (línea 501)**: coordenadas y provincias sin conexión; municipios en OpenStreetMap Nominatim.
- **`openAbout()` (línea 535)**: panel «Sobre el modelo», con lo medido (e intervalos) y lo no medido.
- **Qué podría fallar.**
  - Abrir el `index.html` con doble clic (hay que servirlo con `python -m http.server`).
  - Los límites de uso de las teselas de OpenStreetMap.

## 8. `web_mapa/functions/api/explicar.js` — «Explicar esta celda» con Claude
- Es una *Pages Function*: código que Cloudflare ejecuta en su servidor. **La clave de Anthropic vive solo ahí** (`ANTHROPIC_API_KEY`).
- **`onRequestPost()` (línea 75).**
  - Valida la petición y limita a 20 peticiones por minuto por IP.
  - **Lee los datos de la celda de los archivos publicados, no del navegador**: así nadie puede colar instrucciones (*inyección de prompt*).
  - Llama al modelo `CLAUDE_MODEL` (por defecto `claude-sonnet-5-5`), con esfuerzo bajo, un máximo de 120 palabras y reintento automático ante rechazos.
- **`plantilla()` (línea 64).** Sin clave, ante un rechazo o un error, devuelve una plantilla sin IA. Dentro de la web de Dani (un Worker que solo sirve archivos) siempre se usa la plantilla.
- **No probado:** la llamada con una clave real.

## 9. Pruebas
- `tests/test_rubrica.py` (14): casos límite de reglas, activación de capas, columnas nuevas y renormalización.
- `tests/test_contrato.py` (12): errores fatales frente a avisos, sobre un recorte real de 300 celdas copiado a un directorio temporal.
- `tests/test_salida.py` (6): esquema, rangos, NaN, tamaños y ausencia de claves en el cliente.
- `tests/aceptacion.py`: 4 escenarios de datos sobre copias temporales, con el mapa abierto en Chrome headless.
- `tests/verificar_web.mjs`: el mapa (o la web de Dani con su enlace) sin errores de consola y con carga en menos de 3 s.

---

## 10 preguntas del jurado (con respuesta corta)
1. **¿Por qué una rúbrica y no IA para decidir?** No existe un dato fiable de «viable»; un modelo entrenado con los data centers existentes aprende «parecido a una ciudad», y una regla de 2 variables lo supera. Está medido.
2. **¿Cómo sabéis que el modelo no generaliza?** Validamos por provincias enteras, con intervalos por bootstrap de provincias. La regla para aceptarlo se fijó antes de ver los resultados.
3. **¿Qué significa «P92»?** Mejor que el 92 % de las celdas no excluidas. Es una ordenación, no una probabilidad.
4. **¿De dónde salen los pesos?** Son supuestos razonados con datos (percentiles de España frente a celdas con data center) y con normativa (NCSE-02, SNCZI). Están en un YAML editable y tienen análisis de sensibilidad.
5. **¿Qué pasa si los datos cambian?** Un comando lo regenera todo. Las columnas nuevas no cambian el mapa en silencio, las capas que se rellenan se activan solas, lo que desaparece se omite con aviso y el mapa enseña la huella y avisa del cambio.
6. **¿Qué pasa si falta un dato?** Puntúa de forma pesimista, baja la confianza y se lista en «datos que faltan». Por debajo del 70 % de peso con datos, la celda es «No evaluable».
7. **¿Excluís data centers que ya existen?** No. Hay un test que lo comprueba.
8. **¿Dónde está la IA frontera?** En la explicación de cada celda con Claude, restringida a sus datos y con plantilla de respaldo, y en los criterios de expertos extraídos de audio por el equipo.
9. **¿Es reproducible?** Sí: un comando, semilla fija, huella de datos y una prueba de aceptación que comprueba que dos ejecuciones dan archivos idénticos.
10. **¿Qué haríais con más tiempo?** Capacidad de acceso a red por nudo (REE), suelo industrial disponible por parcela, proyectos cancelados como negativos reales, y validar los pesos con promotores.
