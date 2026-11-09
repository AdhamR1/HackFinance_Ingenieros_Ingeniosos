# Can I Build Here?

Mapa que estima si un terreno es viable para construir un **data center**.
El país se divide en cuadrados de 12 km² (3,46 × 3,46 km) y cada uno se pinta verde, amarillo o rojo según su puntuación.

Dominio previsto: **canibuildhere.online** (alojado en Cloudflare Pages).

> ⚠️ Ahora mismo los datos de España son **inventados** (ver `DATA_FORMAT.md` para sustituirlos por los reales).

## Cómo abrir la web en tu ordenador

La web necesita un pequeño servidor local (si abres `index.html` con doble clic, el navegador
no deja cargar los archivos de datos y el mapa sale vacío).

1. Abre una terminal **dentro de esta carpeta** (`pagina`).
   En Windows: abre la carpeta en el Explorador, haz clic en la barra de direcciones, escribe `cmd` y pulsa Enter.
2. Escribe:
   ```
   python -m http.server 8000
   ```
3. Abre en el navegador: **http://localhost:8000**
4. Para pararlo, vuelve a la terminal y pulsa `Ctrl + C`.

Truco: `http://localhost:8000/#ES` abre directamente España.

Si cambias algo y no lo ves, recarga forzando con `Ctrl + F5`.

## Qué archivo tocar para cada cosa

| Quiero cambiar…                                  | Archivo |
|--------------------------------------------------|---------|
| Pesos, colores, umbrales, descartes, opciones    | `config.js` |
| Textos de la web (español / inglés)              | `i18n/es.json`, `i18n/en.json` |
| Los datos de un país                             | `data/ES.json` (formato en `DATA_FORMAT.md`) |
| Qué países tienen datos                          | `data/paises.json` |
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
- Contornos de países: [Natural Earth](https://www.naturalearthdata.com/) (dominio público).
