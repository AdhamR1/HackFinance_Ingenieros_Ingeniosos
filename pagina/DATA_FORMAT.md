# Formato de los datos — qué lee la web

Este documento describe **qué archivo espera la web y qué significa cada campo**. No dice cómo
hay que preparar los datos: da igual de dónde salgan (data lake, Azure, Python, una base de datos…),
siempre que al final se entregue un archivo con esta forma. Basta con sustituir el archivo
(por ejemplo `data/ES.json`) y recargar la web; no hace falta tocar el código.

---

## 1. La idea

- El país está dividido en **cuadrados de 12 km²** (3,46 × 3,46 km). En España hay **43.213**.
- Cada cuadrado tiene un **identificador** (`id`), su **forma** (coordenadas) y una serie de **datos**:
  la nota final, las 6 variables, los permisos que le afectan y, si se quiere, los motivos principales.
- Con eso la web pinta cada cuadrado **verde, amarillo o rojo** y, al pulsarlo, enseña el detalle.

Los cuadrados ya están dibujados en `data/ES.json` (ahora con datos inventados). Cada uno lleva
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
    "puntuacion": 64,
    "descartado": false,
    "motivo_descarte": null,
    "energia": 85,
    "agua": 60,
    "clima": 70,
    "riesgos": 88,
    "conectividad": null,
    "suelo": 45,
    "permisos": ["zona_inundable"],
    "motivos_a_favor": ["Subestación eléctrica a menos de 5 km", "Clima fresco todo el año"],
    "motivos_en_contra": ["Parte del terreno es zona inundable"],
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
| `motivo_descarte` | no | texto o `null` | Por qué se descarta (se enseña en el panel). |

\* Si `puntuacion` viene vacía (`null`), la web calcula una nota provisional por su cuenta (ver punto 5).

### 3.3. Variables (el desglose que se ve en el panel)

Son los factores que explican la nota. **Todas van de 0 a 100, y 100 es siempre lo mejor.**

| Campo | Qué representa |
|---|---|
| `energia` | Electricidad: disponibilidad, cercanía a la red, precio. |
| `agua` | Agua disponible para la refrigeración. |
| `clima` | Clima favorable (más fresco = refrigerar cuesta menos). |
| `riesgos` | Riesgos naturales (sísmico, inundación…). **100 = POCO riesgo** (al revés de lo intuitivo). |
| `conectividad` | Fibra óptica y cercanía a puntos de intercambio de internet. |
| `suelo` | Terreno apto para construir (pendiente, estabilidad, disponibilidad…). |

Reglas de los valores:

- **0 a 100, y 100 = mejor**, también en los riesgos. Un dato del tipo "cuanto más, peor" tiene que
  darse la vuelta (`100 − valor`) antes de llegar a la web.
- **`null` = "no tenemos el dato".** La web enseña "Sin datos". No es lo mismo que `0`, que significa "malísimo".
- `null` se escribe **sin comillas** (`"null"` con comillas sería un texto, y estaría mal).
- Los números van **sin comillas** y con **punto** decimal: `72.5`, no `"72,5"`.
- **Si cualquiera de las variables baja de 20, la web descarta el cuadrado** (ver punto 5).
- Los campos que empiezan por `_` (guion bajo) los usa la web internamente: no deben venir en el archivo.

### 3.4. Permisos

`permisos` es la **lista de permisos que afectan al cuadrado**. Lista vacía `[]` = no le afecta ninguno.
En el panel solo aparecen los que le afectan.

| Valor | Se muestra como | ¿Descarta el cuadrado? |
|---|---|---|
| `"natura_2000"` | Red Natura 2000 | **Sí** (sale rojo) |
| `"parque_nacional"` | Parque Nacional | **Sí** (sale rojo) |
| `"suelo_urbano"` | Suelo urbano | No, solo se informa |
| `"flujo_preferente"` | Zona de flujo preferente | No, solo se informa |
| `"zona_inundable"` | Zona inundable | No, solo se informa |

También se acepta la forma de objeto: `"permisos": { "natura_2000": true, "zona_inundable": false, ... }`.
Qué permisos descartan se cambia en `config.js` (`permisos`, `descarta: true/false`).

### 3.5. Motivos principales (opcional)

`motivos_a_favor` y `motivos_en_contra`: listas de frases cortas que explican la nota. La web enseña
**hasta 3** de cada:

- **verde** → "Por qué se acepta" (a favor)
- **rojo** (o descartado) → "Por qué se rechaza" (en contra)
- **amarillo** → los dos

Cada frase puede ser un texto o un objeto con los dos idiomas, para que salga traducida:

```json
"motivos_a_favor": [ { "es": "Clima fresco todo el año", "en": "Cool climate all year round" } ]
```

**Si no vienen, la web los saca de los datos**: a favor, las variables con mejor valor; en contra,
el motivo de descarte, los permisos que le afectan y las variables con peor valor.

### 3.6. Motivos de descarte (`motivo_descarte`)

| Valor | Se muestra como |
|---|---|
| `"suelo_protegido"` | Suelo protegido |
| `"natura_2000"` | Dentro de la Red Natura 2000 |
| `"parque_nacional"` | Dentro de un Parque Nacional |

Cualquier otro texto (por ejemplo `"zona militar"`) se muestra tal cual. Para que salga traducido
a los dos idiomas, se añade en `i18n/es.json` y `i18n/en.json` como `"motivo_<valor>"`.

---

## 4. La geometría

- Coordenadas en grados, sistema **WGS84** (el del GPS), en orden **[longitud, latitud]** y con
  4 decimales (≈ 10 m). Ojo: primero la longitud, que en casi toda España es negativa.
- `"Polygon"` para los cuadrados normales y `"MultiPolygon"` para los de costa que quedan partidos en varios trozos.
- Los cuadrados de costa y frontera están **recortados** con los límites oficiales del INE: solo cubren tierra española.
- Si solo cambian los datos, **la geometría no hace falta tocarla**: basta con unir los datos por el `id`.

---

## 5. Cómo decide la web el color

1. **Rojo ("Descartado")**, sea cual sea su nota, si se cumple cualquiera de estas cosas:
   - el archivo trae `"descartado": true`;
   - le afecta un permiso que descarta (Red Natura 2000 o Parque Nacional);
   - **alguna de las 6 variables vale menos de 20** (una variable sin dato no cuenta).
     El límite se cambia en `config.js` (`descarte_si_variable_menor_que`).
2. Si no está descartado y trae `puntuacion` → se usa esa nota.
3. Si no la trae → la web calcula una **nota provisional** con los valores de las variables. Sirve
   solo para probar con datos inventados: con los datos reales, lo previsto es que la nota venga ya
   calculada en `puntuacion`, para que **el modelo (cómo se combinan las variables) no esté en la web**.
4. Color según la nota: **verde** ≥ 70 · **amarillo** 40-69 · **rojo** < 40 · **gris** sin ningún dato.
   Estos límites se cambian en `config.js` (`umbrales`).

---

## 6. Añadir o quitar una variable

Si el equipo cambia la lista de variables, en la web hay que tocar:

1. `config.js` → `variables` (orden y color del icono).
2. `i18n/es.json` y `i18n/en.json` → el nombre visible, `"var_<clave>"`.
3. `js/iconos.js` → su dibujo (si no tiene, sale un círculo).

Y en el archivo de datos, un campo nuevo en `properties` con ese mismo nombre (`<clave>`), de 0 a 100.
Para un permiso nuevo: `config.js` → `permisos` y su nombre en los dos idiomas (`"permiso_<clave>"`).

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

Con 43.000 cuadrados el archivo ocupa unos 19 MB, pero la web lo descarga comprimido (~1,8 MB).
Cada campo se repite 43.000 veces, así que conviene no añadir campos que la web no use
(y que los motivos escritos sean frases cortas).
