# Formato de los datos — guía para rellenar el archivo real

Esta guía explica cómo es el archivo con los datos de un país (por ejemplo `data/ES.json`)
para que podáis sustituir los datos inventados por los reales. **No hace falta tocar el código**:
basta con cambiar el archivo y recargar la web.

---

## 1. La idea en una frase

El país está dividido en **cuadrados de 12 km²** (3,46 × 3,46 km; en España salen unos 43.000).
Para cada cuadrado ponemos una nota
de 0 a 100 en cada variable (energía, agua…). La web calcula la puntuación final y lo pinta
verde, amarillo o rojo.

## 2. La forma más fácil de hacerlo (recomendada)

Los cuadrados **ya están dibujados** en `data/ES.json`. Lo más sencillo es:

1. **No tocar la geometría** (las coordenadas de cada cuadrado).
2. Buscar cada cuadrado por su `id` (por ejemplo `ES-01234`) o por sus columnas `utm_huso`, `utm_x`, `utm_y`
   (esquina suroeste del cuadrado en metros, en la proyección UTM que usa el Instituto Geográfico Nacional).
3. **Cambiar solo los números** de las variables (`energia`, `agua`, etc.).

Si queréis empezar de una plantilla con todo vacío (todas las variables a `null`):

```
cd herramientas
npm install                                   (solo la primera vez)
node generar_datos_prueba.mjs --solo-geometria --salida ../data/ES_plantilla.json
```

> **Consejo:** si trabajáis en Excel o Python, sacad una tabla con columnas
> `id, energia, agua, clima, conectividad, carreteras, sismico, inundacion, descartado, motivo_descarte`
> y luego se mezcla con la geometría por el `id`. Pedídmelo y preparo un script que lo haga.

---

## 3. Estructura del archivo

Es un archivo **GeoJSON** (el formato estándar para mapas; lo abren QGIS, Python/geopandas,
geojson.io, etc.). Por fuera tiene esta forma:

```json
{
  "type": "FeatureCollection",
  "meta": { ...información del archivo... },
  "features": [
    { ...cuadrado 1... },
    { ...cuadrado 2... }
  ]
}
```

### 3.1. `meta` — información del archivo

| Campo | Obligatorio | Qué es | Ejemplo |
|---|---|---|---|
| `pais` | sí | Código del país (2 letras) | `"ES"` |
| `area_cuadrado_km2` | sí | Superficie de cada cuadrado en km². Se muestra en el panel | `12` |
| `lado_cuadrado_km` | no | Lado del cuadrado en km | `3.464` |
| `datos_de_prueba` | no | `true` si son datos inventados | `false` |
| `fuente` | no | De dónde salen los datos | `"Equipo datos, REE + AEMET"` |
| `fecha` | no | Fecha de los datos (AAAA-MM-DD) | `"2026-12-01"` |

### 3.2. Cada cuadrado (`feature`)

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[-3.6677,40.4593], [-3.6268,40.4595], [-3.6271,40.4907], [-3.668,40.4905], [-3.6677,40.4593]]]
  },
  "properties": {
    "id": "ES-21404",
    "puntuacion": null,
    "descartado": false,
    "motivo_descarte": null,
    "energia": 85,
    "agua": 60,
    "clima": 70,
    "conectividad": null,
    "carreteras": 90,
    "sismico": 95,
    "inundacion": 80,
    "area_km2": 12,
    "utm_huso": 30,
    "utm_x": 443392,
    "utm_y": 4478952
  }
}
```

### 3.3. Campos de `properties`, uno a uno

| Campo | Obligatorio | Valores | Qué significa |
|---|---|---|---|
| `id` | **sí** | texto, `"ES-00001"`… | Identificador único del cuadrado. No repetir. |
| `energia` | sí* | 0-100 o `null` | Disponibilidad/precio de electricidad. **100 = mejor.** |
| `agua` | sí* | 0-100 o `null` | Agua disponible para refrigeración. **100 = mejor.** |
| `clima` | sí* | 0-100 o `null` | Clima favorable (fresco = refrigerar cuesta menos). **100 = mejor.** |
| `conectividad` | sí* | 0-100 o `null` | Fibra, cercanía a puntos de intercambio. **100 = mejor.** |
| `carreteras` | sí* | 0-100 o `null` | Acceso por carretera. **100 = mejor.** |
| `sismico` | sí* | 0-100 o `null` | Riesgo sísmico. **100 = POCO riesgo** (¡ojo, al revés de lo intuitivo!). |
| `inundacion` | sí* | 0-100 o `null` | Riesgo de inundación. **100 = POCO riesgo.** |
| `descartado` | no | `true` / `false` | `true` = el cuadrado no vale (sale rojo directamente). |
| `motivo_descarte` | no | texto o `null` | Por qué se descarta. Valores conocidos abajo. |
| `puntuacion` | no | 0-100 o `null` | Nota final ya calculada (p. ej. por vuestro modelo). Si es `null`, la calcula la web. |
| `area_km2` | no | número | Superficie de tierra del cuadrado (los de costa y frontera son menores de 12). |
| `utm_huso`, `utm_x`, `utm_y` | no | números | Esquina suroeste del cuadrado en metros (UTM huso 30; huso 28 en Canarias). Útil para cruzar con datos en QGIS. |

\* "sí" = el campo debe existir, pero puede valer `null`.

**Reglas importantes:**

- **Todas las variables van de 0 a 100 y 100 es siempre lo mejor.** Si vuestro dato original es
  "cuanto más, peor" (por ejemplo, riesgo sísmico), hay que darle la vuelta: `100 - valor`.
- **`null` significa "no tenemos el dato".** La web pondrá "Sin datos" y **no** lo usará para la
  media (su peso se reparte entre las demás). **No pongáis 0 cuando falte el dato**: 0 significa "malísimo".
- `null` se escribe tal cual, **sin comillas**. `"null"` (con comillas) estaría mal.
- Los números van **sin comillas** y con **punto** decimal: `72.5`, no `"72,5"`.
- Los campos que empiezan por `_` (guion bajo) los usa la web internamente: no los pongáis.

**Motivos de descarte conocidos** (la web los traduce):

| Valor | Se muestra como |
|---|---|
| `"suelo_protegido"` | Suelo protegido |
| `"inundacion"` | Riesgo de inundación alto |
| `"sismico"` | Riesgo sísmico extremo |

Si ponéis otro texto (por ejemplo `"zona militar"`), la web lo muestra tal cual.

**Descartes automáticos:** aunque `descartado` sea `false`, la web descarta el cuadrado si
`inundacion` < 20 o `sismico` < 10. Estos límites se cambian en `config.js` (`reglas_descarte`).

### 3.4. La geometría

- Coordenadas en grados, sistema **WGS84** (el de GPS), en orden **[longitud, latitud]**, con 4 decimales (≈ 10 m)
  (¡primero la longitud! En España la longitud es negativa en casi toda la península).
- Tipo `"Polygon"` para cuadrados normales y `"MultiPolygon"` para los de costa que quedan partidos
  en varios trozos (islotes).
- Los cuadrados de la costa y de la frontera están **recortados**: solo cubren tierra española.

---

> **Sobre el tamaño del archivo:** con 43.000 cuadrados ocupa ~18 MB, pero al publicarlo en
> Cloudflare se descarga comprimido (~1 MB). No añadáis campos extra innecesarios: cada campo se repite
> 43.000 veces.

## 4. Cómo se calcula la puntuación (para que sepáis qué afecta a qué)

1. Si el cuadrado trae `puntuacion` y en `config.js` está `usar_puntuacion_del_archivo: true`,
   se usa esa nota.
2. Si no, se hace la **media ponderada** de las variables que tienen dato, con estos pesos
   (se cambian en `config.js`):

   | Variable | Peso |
   |---|---|
   | energía | 0.25 |
   | agua | 0.25 |
   | clima | 0.15 |
   | conectividad | 0.15 |
   | carreteras | 0.10 |
   | sísmico | 0.10 |
   | inundación | 0 (solo descarta) |

3. Color: **verde** ≥ 70 · **amarillo** 40-69 · **rojo** < 40 o descartado · **gris** sin ningún dato.

---

## 5. Comprobar que el archivo está bien

1. Abrid el archivo en QGIS (Capa → Añadir capa vectorial): si se ven los cuadrados sobre España,
   la geometría está bien. (El archivo pesa unos 18 MB: webs como geojson.io pueden ir muy lentas.)
2. Si el archivo tiene un error de formato, la web mostrará "No se han podido cargar los datos".
   Pegad el contenido en <https://jsonlint.com> y os dirá en qué línea está el fallo
   (lo típico: una coma de más al final de una lista, o comillas que faltan).
3. Cuando sean los datos reales, cambiad en `meta` → `"datos_de_prueba": false` y en
   `config.js` → `mostrar_etiqueta_datos_prueba: false`.

## 6. Añadir otro país

1. Crear `data/FR.json` con este mismo formato (`id` tipo `"FR-00001"`).
2. Añadir una línea en `data/paises.json`:
   ```json
   "FR": { "archivo": "data/FR.json", "limites": [[-5.2, 42.3], [8.3, 51.1]] }
   ```
   (`limites` = esquina suroeste y noreste [longitud, latitud] para encuadrar el país).
3. Listo: el país pasa a salir en dorado y se puede abrir.
