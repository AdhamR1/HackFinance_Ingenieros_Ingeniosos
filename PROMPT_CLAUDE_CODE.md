# Prompt para continuar en Claude Code

> Abre Claude Code en la carpeta `dc_datalake/` y pega todo lo que hay debajo de la línea como primer mensaje. `CLAUDE.md` se carga solo y contiene las reglas del proyecto.

---

Hola. Continúo aquí un trabajo que empecé en el chat de Claude. Lee primero `CLAUDE.md`, `README.md` y `config.yaml`, y echa un vistazo a `src/dclake/`. Respóndeme siempre en español.

## Contexto

Estamos en un hackathon de finanzas, equipo de 5 personas, 4 días. El proyecto es una herramienta de **cribado de viabilidad de parcelas para data centers**:

1. El usuario elige una parcela en un mapa.
2. Se estima la respuesta del suelo con ruido sísmico ambiental de estaciones públicas: método **H/V** (cociente espectral horizontal/vertical), frecuencia de resonancia f0 y amplitud A0, más el nivel de vibración ambiental (tráfico, industria).
3. Se combina con capas de energía (subestaciones, precio, mix), agua, clima y refrigeración, riesgos naturales, conectividad, suelo y economía, accesos, tráfico y viviendas cercanas, regulación, biodiversidad y contexto político y cultural del país.
4. Sale una puntuación de viabilidad, un coste estimado por MW y un informe en lenguaje natural generado por Claude.

Es un **cribado inicial**, no un estudio geotécnico: el H/V de la estación más cercana es un indicador regional y así hay que presentarlo.

El reparto del equipo: lectura de datos, data lake, tuning y entrenamiento, interfaz y revisión continua. **Yo me encargo de obtener los datos.** El modelo general se pensó para 8 países (EE. UU., Malasia, India, Australia, China, Japón, Reino Unido y España), pero para el hackathon decidimos:

- **Solo España**, rejilla de **5×5 km**, **500 celdas** de muestra estratificada (celdas con data center conocido, 75 en Madrid, 75 en Aragón y el resto al azar).
- **Temporalidad mixta:** diario 20 años (nov 2006 – oct 2026) solo para lo que cambia a diario (clima, precio eléctrico, mix de generación, terremotos, incendios); anual para agregados e indicadores económicos; estático para el resto.
- **Todos los campos del diccionario** presentes como columnas, aunque muchos queden vacíos de momento.
- La tabla `country_context` sí incluye los 8 países (para el modelo general futuro).
- Se ejecuta en un **portátil con Windows**, con el data lake en **Parquet local**.
- Todavía **no tengo ninguna clave de API** (CDS, FIRMS…); las pediré.

## Qué hay hecho

- `data_dictionary/diccionario_datos_datacenters.xlsx`: diccionario de 494 campos en 17 bloques (identificación, energía, sísmica y geotecnia, riesgos naturales, agua, clima, conectividad, suelo y economía, accesos, tráfico y viviendas, regulación, biodiversidad, señal sísmica, estaciones, contexto país, etiquetas y linaje), con tipo, unidad, fuentes, prioridad (MVP/Ampliado), rol, origen esperado y **temporalidad**, más una hoja de **variables diarias**. Se genera con `build_dict.py`.
- Paquete `src/dclake` con rejilla, muestreo, colectores por fuente, ensamblado según el diccionario, linaje e informe de cobertura. Los colectores implementados son OSM (Overpass), PeeringDB, hubs y latencias, OurAirports, cables submarinos, costa, Copernicus DEM, SoilGrids, capas manuales, terremotos (EMSC/USGS), FIRMS, ERA5-Land (series temporales del CDS), electricidad (OMIE, REE y BCE), Banco Mundial y sísmica (FDSN + H/V). Hay además una lista de pendientes en `collectors/pending.py`.
- Tests offline y `python -m dclake demo`, que pasan. La rejilla real de España (20.236 celdas con geoBoundaries) también se ha probado.

**Importante:** los colectores se escribieron sin poder llamar a las APIs reales (el entorno no tenía acceso a esos dominios). La lógica de cálculo está probada, pero la forma exacta de las respuestas de cada API no.

## Lo que quiero que hagas, por orden

1. **Entorno.** Crea el entorno conda (`environment.yml`), ejecuta los tests y la demo y arregla lo que falle en Windows.
2. **Validar cada colector con 3 celdas.** Ejecuta `python -m dclake grid` y luego `python -m dclake collect --only <colector> --limit-sites 3` uno por uno. Arregla lo que falle y comprueba que los valores tienen sentido (rangos, unidades). Verifica en concreto:
   - **ERA5-Land (CDS):** que el dataset `reanalysis-era5-land-timeseries` acepta la petición tal cual (`location`, `date` como rango, `data_format`) y que `read_cds_output` entiende la salida. Revisa la documentación actual del CDS si hace falta. Comprueba en una celda que la temperatura media anual y la precipitación anual son razonables, y que la lluvia diaria no sale 24 veces mayor de lo que debe (acumulados de ERA5).
   - **OMIE:** que la URL de descarga funciona y qué columna del archivo `marginalpdbc` es el precio de España (`electricity.omie_es_field_index`). Contrasta un día con el precio publicado en la web de OMIE. Ten en cuenta que desde octubre de 2025 hay 96 periodos de 15 minutos por día.
   - **REE REData:** que acepta un año completo con `time_trunc=day` y que la clasificación renovable/no renovable de los títulos es correcta.
   - **Banco Mundial:** que los códigos WGI (`PV.EST`, etc. con `source=3`) siguen funcionando tras la revisión de 2024; si no, encuentra los nuevos.
   - **PeeringDB:** nombres reales de los campos (`net_count`, `carrier_count`) en `fac` e `ix`.
   - **Overpass:** que las consultas de toda España no se cortan por tiempo o tamaño; si se cortan, divídelas por comunidad autónoma o pasa a un extracto `.osm.pbf` de Geofabrik.
   - **Copernicus DEM y SoilGrids** leídos por `/vsicurl/` en Windows.
   - **Sísmica:** qué redes y estaciones salen en España (red `ES` del IGN vía EIDA), y que el H/V da f0 plausibles. Compara alguna con valores publicados si los encuentras.
3. **Ejecución completa.** Corre todo con las 500 celdas. Lo largo (ERA5, OMIE, sísmica) ejecútalo en segundo plano o en partes, y dime cuánto tarda.
4. **Implementar pendientes**, empezando por los campos **MVP** con más peso para el modelo: capacidad de acceso a la red por nudo (REE), huellas de edificios o viviendas (Catastro INSPIRE), aforos de tráfico (MITMA), caudal GloFAS y CAMS (misma cuenta ECMWF), y precio del suelo. Añade lo que falte de `reports/coverage.csv` con estado *sin colector* cuando haya una fuente pública razonable.
5. **Control de calidad.** Revisa el informe de cobertura y valores fuera de rango por campo (por ejemplo, distancias negativas o temperaturas imposibles), y prepara un resumen breve para el resto del equipo: qué tablas hay, qué cubren y cómo se unen.

Antes de cambiar algo que afecte a la estructura del diccionario o borrar datos descargados, pregúntame. Para lo demás, avanza y cuéntame al final qué has hecho y qué ha quedado pendiente.
