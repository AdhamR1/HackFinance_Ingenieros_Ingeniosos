// Todo lo que tiene que ver con MapLibre (el mapa): capas base y países.
// maplibregl viene del <script> del index.html (variable global).

const COLOR_ACENTO = '#f5b301';   // ámbar (igual que en estilos.css)
const COLOR_GRIS   = '#9ca3af';

// Capas base gratuitas, sin clave. Las atribuciones son obligatorias.
const CAPAS_BASE = {
  satelite: {
    type: 'raster',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    tileSize: 256,
    maxzoom: 19,
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
  },
  mapa: {
    type: 'raster',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    tileSize: 256,
    maxzoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
  },
};

export function crearMapa(idContenedor, capaInicial) {
  const map = new maplibregl.Map({
    container: idContenedor,
    style: {
      version: 8,
      sources: { satelite: CAPAS_BASE.satelite, mapa: CAPAS_BASE.mapa },
      layers: [
        { id: 'fondo', type: 'background', paint: { 'background-color': '#05070a' } },
        { id: 'base-satelite', type: 'raster', source: 'satelite',
          layout: { visibility: capaInicial === 'satelite' ? 'visible' : 'none' } },
        { id: 'base-mapa', type: 'raster', source: 'mapa',
          layout: { visibility: capaInicial === 'mapa' ? 'visible' : 'none' } },
      ],
    },
    center: [10, 30],
    zoom: 1.6,
    minZoom: 1,
    maxZoom: 19,
    attributionControl: { compact: true },
    renderWorldCopies: false,
    dragRotate: false,
    pitchWithRotate: false,
  });
  map.touchZoomRotate.disableRotation();
  // En pantallas pequeñas, los créditos empiezan plegados (botón ⓘ) para no tapar el mapa.
  if (window.matchMedia('(max-width: 640px)').matches) {
    map.once('load', () => document.querySelector('.maplibregl-ctrl-attrib')
      ?.classList.remove('maplibregl-compact-show'));
  }
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  return map;
}

// Cambia entre 'satelite' y 'mapa'.
export function ponerCapaBase(map, capa) {
  map.setLayoutProperty('base-satelite', 'visibility', capa === 'satelite' ? 'visible' : 'none');
  map.setLayoutProperty('base-mapa', 'visibility', capa === 'mapa' ? 'visible' : 'none');
}

// Añade las siluetas de los países. Los que tienen datos se pintan en ámbar
// y el resto en gris. "disponibles" es una lista de códigos, p. ej. ['ES'].
let paisesDisponibles = [];

// Opacidad del relleno de cada país. El país abierto ("seleccionado") se deja
// transparente para ver bien su cuadrícula.
function opacidadPaises(seleccionado) {
  const esDisponible = ['in', ['get', 'iso'], ['literal', paisesDisponibles]];
  const enHover = ['boolean', ['feature-state', 'hover'], false];
  return ['case',
    ['==', ['get', 'iso'], seleccionado || ''], 0,
    esDisponible, ['case', enHover, 0.45, 0.25],
    ['case', enHover, 0.55, 0.4]];
}

export function anadirPaises(map, mundo, disponibles) {
  paisesDisponibles = disponibles;
  const esDisponible = ['in', ['get', 'iso'], ['literal', disponibles]];

  map.addSource('paises', { type: 'geojson', data: mundo, generateId: true });
  map.addLayer({
    id: 'paises-relleno',
    type: 'fill',
    source: 'paises',
    paint: {
      'fill-color': ['case', esDisponible, COLOR_ACENTO, COLOR_GRIS],
      'fill-opacity': opacidadPaises(null),
    },
  });
  map.addLayer({
    id: 'paises-borde',
    type: 'line',
    source: 'paises',
    paint: {
      'line-color': ['case', esDisponible, COLOR_ACENTO, '#ffffff'],
      'line-opacity': ['case', esDisponible, 0.9, 0.35],
      'line-width': ['case', esDisponible, 1.5, 0.6],
    },
  });
}

// Marca un país como "abierto" (o ninguno, con null).
export function marcarPaisSeleccionado(map, iso) {
  map.setPaintProperty('paises-relleno', 'fill-opacity', opacidadPaises(iso));
}
