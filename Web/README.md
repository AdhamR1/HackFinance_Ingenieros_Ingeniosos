# Can I Build Here?

Mapa que estima si un terreno es viable para construir un **data center**.
El país se divide en cuadrados de 12 km² (3,46 × 3,46 km) y cada uno se pinta verde, amarillo o rojo según su puntuación.

Publicada en **https://canibuildhere.online** (alojada en Cloudflare).

Países con datos reales del modelo: **España** y **Japón** (`Modelo/src/exportar_web.py` genera sus archivos; el formato está en `DATA_FORMAT.md`).

## Cómo abrir la web en tu ordenador

La web necesita un pequeño servidor local (si abres `index.html` con doble clic, el navegador
no deja cargar los archivos de datos y el mapa sale vacío).

1. Abre una terminal **dentro de esta carpeta** (`Web`).
   En Windows: abre la carpeta en el Explorador, haz clic en la barra de direcciones, escribe `cmd` y pulsa Enter.
2. Escribe:
   ```
   python -m http.server 8000
   ```
3. Abre en el navegador: **http://localhost:8000**
4. Para pararlo, vuelve a la terminal y pulsa `Ctrl + C`.

Truco: `http://localhost:8000/#ES` abre directamente España (`#JP`, Japón).

Si cambias algo y no lo ves, recarga forzando con `Ctrl + F5`.

## Qué archivo tocar para cada cosa

| Quiero cambiar…                                  | Archivo |
|--------------------------------------------------|---------|
| Colores, umbrales, descartes, variables, opciones | `config.js` |
| Textos de la web (español / inglés)              | `i18n/es.json`, `i18n/en.json` |
| Los datos de un país                             | `data/ES.json`, `data/JP.json` (formato en `DATA_FORMAT.md`) |
| Qué países tienen datos                          | `data/paises.json` |
| Comunidades y provincias (bordes y buscador)     | `data/ES_regiones.json` (se crea con `herramientas/preparar_regiones.mjs`, que también actualiza el contorno usado por la cuadrícula); `data/JP_regiones.json` (prefecturas, lo crea `exportar_web.py`) |
| Colores y aspecto                                | `css/estilos.css` |

## Estructura

```
index.html        página principal
config.js         configuración (comentada en español)
css/              estilos
js/               código (app, mapa, puntuación, panel, idiomas)
i18n/             textos en cada idioma
data/             datos: mundo, lista de países y un archivo por país
herramientas/     scripts para generar datos (no forman parte de la web)
```

## Créditos

- Mapa: [MapLibre GL JS](https://maplibre.org/) (licencia BSD).
- Satélite: Esri World Imagery. Mapa: © colaboradores de OpenStreetMap.
- Contornos de países (vista del mundo): [Natural Earth](https://www.naturalearthdata.com/) (dominio público).
- Límites de España, comunidades y provincias: [geoBoundaries](https://www.geoboundaries.org) (datos del INE, CC BY 4.0).
- Límites de Japón y prefecturas: [geoBoundaries](https://www.geoboundaries.org) (CC BY 4.0).
- Nombres de lugares y fronteras: [OpenFreeMap](https://openfreemap.org) / OpenMapTiles, datos de OpenStreetMap.
- Buscador de pueblos y ciudades: [Photon](https://photon.komoot.io) (komoot), con datos de OpenStreetMap.
