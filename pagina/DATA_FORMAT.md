# Formato de los datos — qué lee la web

Este documento describe **qué archivo espera la web y qué significa cada campo**. No dice cómo
hay que preparar los datos: da igual de dónde salgan (data lake, Azure, Python, una base de datos…),
siempre que al final se entregue un archivo con esta forma. Basta con sustituir el archivo
(por ejemplo `data/ES.json`) y recargar la web; no hace falta tocar el código.

---

## 1. La idea

- El país está dividido en **cuadrados de 12 km²** (3,46 × 3,46 km). En España hay **43.213**.
- Cada cuadrado tiene un **identificador** (`id`), su **forma** (coordenadas) y una serie de **valores**.
- Con esos valores la web pinta cada cuadrado **verde, amarillo o rojo** y, al pulsarlo, enseña el detalle.

Los cuadrados ya están dibujados en `data/ES.json` (ahora con valores inventados). Cada uno lleva
también su posición en coordenadas UTM (`utm_huso`, `utm_x`, `utm_y`), que puede servir para
cruzarlos con otros datos geográficos.

---

## 2. Estructura del archivo

Es un archivo **GeoJSON** (formato estándar de mapas: lo leen QGIS, Python/geopandas, PostGIS, etc.):

```json
{
  "type": "FeatureCollection",
  "meta": { ...información sobre el archivo... },
  "features": [
    { ...cuadrado 1... },
    { ...cuadrado 2... }
  ]
}
```

### 2.1. `meta` — información sobre el archivo

| Campo | Obligatorio | Qué es | Ejemplo |
|---|---|---|---|
| `pais` | sí | Código del país (2 letras) | `"ES"` |
| `area_cuadrado_km2` | sí | Superficie de cada cuadrado en km² (se muestra en el panel) | `12` |
| `lado_cuadrado_km` | no | Lado del cuadrado en km | `3.464` |
| `datos_de_prueba` | no | `true` si los datos son inventados | `false` |
| `fuente` | no | De dónde salen los datos | `"Equipo de datos"` |
| `fecha` | no | Fecha de los datos (AAAA-MM-DD) | `"2026-12-01"` |

### 2.2. Cada cuadrado (`feature`)

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[-3.6677,40.4593], [-3.6268,40.4595], [-3.6271,40.4907], [-3.668,40.4905], [-3.6677,40.4593]]]
  },
  "properties": {
    "id": "ES-21404",
    "puntuacion": 74,
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

---

## 3. Qué es cada campo de `properties`

### 3.1. Identificación

| Campo | Obligatorio | Valores | Qué es |
|---|---|---|---|
| `id` | **sí** | texto: `"ES-00001"`… | Identificador único del cuadrado. Es la clave para unir cualquier dato con su cuadrado. |
| `utm_huso`, `utm_x`, `utm_y` | no | números | Esquina suroeste del cuadrado, en metros, en coordenadas UTM (huso 30; huso 28 en Canarias). |
| `area_km2` | no | número | Superficie de tierra del cuadrado. Los de costa y frontera son menores de 12 porque están recortados. |

### 3.2. Resultado

| Campo | Obligatorio | Valores | Qué es |
|---|---|---|---|
| `puntuacion` | no* | 0-100 o `null` | **Nota final del cuadrado**, ya calculada por el modelo del equipo. Es lo que decide el color. |
| `descartado` | no | `true` / `false` | `true` = el cuadrado no sirve, sea cual sea su nota (sale en rojo). |
| `motivo_descarte` | no | texto o `null` | Por qué se descarta. Ver la tabla de motivos más abajo. |

\* Si `puntuacion` viene vacía (`null`), la web calcula una nota provisional por su cuenta (ver punto 5).

### 3.3. Variables (el desglose que se ve en el panel)

Son los factores que explican la nota. **Todos van de 0 a 100, y 100 es siempre lo mejor.**

| Campo | Qué representa |
|---|---|
| `energia` | Disponibilidad y precio de la electricidad. |
| `agua` | Agua disponible para la refrigeración. |
| `clima` | Clima favorable (más fresco = refrigerar cuesta menos). |
| `conectividad` | Fibra óptica y cercanía a puntos de intercambio de internet. |
| `carreteras` | Acceso por carretera para la obra y el mantenimiento. |
| `sismico` | Riesgo sísmico. **100 = POCO riesgo** (al revés de lo intuitivo). |
| `inundacion` | Riesgo de inundación. **100 = POCO riesgo.** |

La lista de variables **no es definitiva**: se pueden añadir o quitar (ver punto 6).

### 3.4. Reglas de los valores

- **0 a 100, y 100 = mejor**, también en los riesgos. Un dato del tipo "cuanto más, peor" tiene que
  darse la vuelta (`100 − valor`) antes de llegar a la web.
- **`null` = "no tenemos el dato".** La web enseña "Sin datos". No es lo mismo que `0`, que significa "malísimo".
- `null` se escribe **sin comillas** (`"null"` con comillas sería un texto, y estaría mal).
- Los números van **sin comillas** y con **punto** decimal: `72.5`, no `"72,5"`.
- Los campos que empiezan por `_` (guion bajo) los usa la web internamente: no deben venir en el archivo.

### 3.5. Motivos de descarte

| Valor de `motivo_descarte` | Se muestra como |
|---|---|
| `"suelo_protegido"` | Suelo protegido |
| `"inundacion"` | Riesgo de inundación alto |
| `"sismico"` | Riesgo sísmico extremo |

Cualquier otro texto (por ejemplo `"zona militar"`) se muestra tal cual. Para que salga traducido
a los dos idiomas, se añade en `i18n/es.json` y `i18n/en.json` como `"motivo_<valor>"`.

---

## 4. La geometría

- Coordenadas en grados, sistema **WGS84** (el del GPS), en orden **[longitud, latitud]** y con
  4 decimales (≈ 10 m). Ojo: primero la longitud, que en casi toda España es negativa.
- `"Polygon"` para los cuadrados normales y `"MultiPolygon"` para los de costa que quedan partidos en varios trozos.
- Los cuadrados de costa y frontera están **recortados** con los límites oficiales del INE: solo cubren tierra española.
- Si solo cambian los valores, **la geometría no hace falta tocarla**: basta con unir los datos por el `id`.

---

## 5. Cómo decide la web el color

1. Si el cuadrado está **descartado** → **rojo**, sea cual sea su nota.
2. Si trae `puntuacion` → se usa esa nota.
3. Si no la trae → la web calcula una **nota provisional** con los valores de las variables. Sirve
   solo para probar con datos inventados: con los datos reales, lo previsto es que la nota venga ya
   calculada en `puntuacion`, para que **el modelo (cómo se combinan las variables) no esté en la web**.
4. Color según la nota: **verde** ≥ 70 · **amarillo** 40-69 · **rojo** < 40 · **gris** sin ningún dato.
   Estos límites se cambian en `config.js` (`umbrales`).

La web también puede descartar cuadrados automáticamente con reglas sencillas (ahora: inundación < 20
o sísmico < 10). Están en `config.js` (`reglas_descarte`) y se pueden cambiar o quitar si el
descarte ya viene decidido en los datos.

---

## 6. Añadir o quitar una variable

Si el equipo cambia la lista de variables, en la web hay que tocar:

1. `config.js` → `variables` (orden y color del icono).
2. `i18n/es.json` y `i18n/en.json` → el nombre visible, `"var_<clave>"`.
3. `js/iconos.js` → su dibujo (si no tiene, sale un círculo).

Y en el archivo de datos, un campo nuevo en `properties` con ese mismo nombre (`<clave>`), de 0 a 100.

---

## 7. Otros países

1. Un archivo `data/XX.json` con este mismo formato (`id` del tipo `"FR-00001"`).
2. Una línea en `data/paises.json`:
   ```json
   "FR": { "archivo": "data/FR.json", "limites": [[-5.2, 42.3], [8.3, 51.1]] }
   ```
   (`limites` = esquinas suroeste y noreste, [longitud, latitud], para encuadrar el país).

---

## 8. Tamaño

Con 43.000 cuadrados el archivo ocupa unos 18 MB, pero la web lo descarga comprimido (~1,8 MB).
Cada campo se repite 43.000 veces, así que conviene no añadir campos que la web no use.
