// Todo lo que tiene que ver con MapLibre (el mapa): capas base y países.
// maplibregl viene del <script> del index.html (variable global).

const COLOR_ACENTO = '#f5b301';   // ámbar (igual que en estilos.css)
const COLOR_GRIS   = '#9ca3af';   // países "próximamente"
const COLOR_OSCURO = '#1f2937';   // países sin planes ("no disponible")

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

// Capa transparente de Esri con nombres de ciudades, regiones y fronteras
// (como la vista "híbrida" de Google Maps). Va siempre ENCIMA de todo.
const ETIQUETAS = {
  type: 'raster',
  tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'],
  tileSize: 256,
  maxzoom: 19,
};
// Todas nuestras capas se insertan justo debajo de los nombres.
const ENCIMA = 'etiquetas';
let conNombres = true;

export function crearMapa(idContenedor, capaInicial, { nombres = true } = {}) {
  conNombres = nombres;
  const map = new maplibregl.Map({
    container: idContenedor,
    style: {
      version: 8,
      sources: { satelite: CAPAS_BASE.satelite, mapa: CAPAS_BASE.mapa, etiquetas: ETIQUETAS },
      layers: [
        { id: 'fondo', type: 'background', paint: { 'background-color': '#05070a' } },
        { id: 'base-satelite', type: 'raster', source: 'satelite',
          layout: { visibility: capaInicial === 'satelite' ? 'visible' : 'none' } },
        { id: 'base-mapa', type: 'raster', source: 'mapa',
          layout: { visibility: capaInicial === 'mapa' ? 'visible' : 'none' } },
        // El mapa normal (OpenStreetMap) ya trae nombres; los de Esri solo hacen falta sobre el satélite.
        { id: ENCIMA, type: 'raster', source: 'etiquetas',
          layout: { visibility: nombres && capaInicial === 'satelite' ? 'visible' : 'none' } },
      ],
    },
    center: [10, 30],
    zoom: 1.6,
    minZoom: 1,
    maxZoom: 19,
    attributionControl: {
      compact: true,
      customAttribution: 'Búsqueda: <a href="https://photon.komoot.io" target="_blank" rel="noopener">Photon</a> · datos &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> · Límites: Natural Earth',
    },
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
  map.setLayoutProperty(ENCIMA, 'visibility', conNombres && capa === 'satelite' ? 'visible' : 'none');
}

// Añade las siluetas de los países:
//   - con datos ("disponibles", p. ej. ['ES'])  → ámbar
//   - "próximamente" (lista de config.js)       → gris claro
//   - el resto ("no disponible")                → gris oscuro
let paisesDisponibles = [];
let paisesProximamente = [];

// Opacidad del relleno de cada país. El país abierto ("seleccionado") se deja
// transparente para ver bien su cuadrícula.
function opacidadPaises(seleccionado) {
  const esDisponible = ['in', ['get', 'iso'], ['literal', paisesDisponibles]];
  const enHover = ['boolean', ['feature-state', 'hover'], false];
  return ['case',
    ['==', ['get', 'iso'], seleccionado || ''], 0,
    esDisponible, ['case', enHover, 0.45, 0.25],
    ['in', ['get', 'iso'], ['literal', paisesProximamente]], ['case', enHover, 0.55, 0.4],
    ['case', enHover, 0.5, 0.4]];
}

export function anadirPaises(map, mundo, disponibles, proximamente) {
  paisesDisponibles = disponibles;
  paisesProximamente = proximamente;
  const esDisponible = ['in', ['get', 'iso'], ['literal', disponibles]];
  const esProximamente = ['in', ['get', 'iso'], ['literal', proximamente]];

  map.addSource('paises', { type: 'geojson', data: mundo, generateId: true });
  map.addLayer({
    id: 'paises-relleno',
    type: 'fill',
    source: 'paises',
    paint: {
      'fill-color': ['case', esDisponible, COLOR_ACENTO, esProximamente, COLOR_GRIS, COLOR_OSCURO],
      'fill-opacity': opacidadPaises(null),
    },
  }, ENCIMA);
  map.addLayer({
    id: 'paises-borde',
    type: 'line',
    source: 'paises',
    paint: {
      'line-color': ['case', esDisponible, COLOR_ACENTO, '#ffffff'],
      'line-opacity': ['case', esDisponible, 0.9, 0.35],
      'line-width': ['case', esDisponible, 1.5, 0.6],
    },
  }, ENCIMA);
}

// Marca un país como "abierto" (o ninguno, con null).
export function marcarPaisSeleccionado(map, iso) {
  map.setPaintProperty('paises-relleno', 'fill-opacity', opacidadPaises(iso));
  // El borde simplificado del país abierto se oculta: su cuadrícula ya dibuja la forma.
  const esDisponible = ['in', ['get', 'iso'], ['literal', paisesDisponibles]];
  map.setPaintProperty('paises-borde', 'line-opacity',
    ['case', ['==', ['get', 'iso'], iso || ''], 0, esDisponible, 0.9, 0.35]);
}

// ---------------------------------------------------------------------
// CUADRÍCULA DE UN PAÍS
// ---------------------------------------------------------------------
// Opacidad del relleno: la elegida por el usuario, pero bajando al acercarse
// para que se vea bien el satélite (árboles, edificios...) dentro del cuadrado.
function opacidadCuadricula(opacidad) {
  return ['interpolate', ['linear'], ['zoom'],
    5, opacidad,
    9, opacidad * 0.8,
    12, opacidad * 0.55,
    15, opacidad * 0.4];
}

// "datos" es el GeoJSON del país, con _color ya calculado en cada cuadrado.
export function ponerCuadricula(map, datos, opacidad) {
  const fuente = map.getSource('cuadricula');
  if (fuente) {
    fuente.setData(datos);
  } else {
    map.addSource('cuadricula', { type: 'geojson', data: datos, promoteId: 'id' });
    map.addLayer({
      id: 'cuadricula-relleno', type: 'fill', source: 'cuadricula',
      // fill-antialias false: evita una malla de rayitas finas entre cuadrados vecinos.
      paint: { 'fill-color': ['get', '_color'], 'fill-opacity': opacidadCuadricula(opacidad), 'fill-antialias': false },
    }, ENCIMA);
    map.addLayer({
      id: 'cuadricula-borde', type: 'line', source: 'cuadricula',
      paint: {
        'line-color': '#000000',
        // De lejos no se dibujan (con miles de cuadrados oscurecerían el mapa); aparecen al acercarse.
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 6.5, 0, 8, 0.3, 11, 0.5],
        'line-width': ['interpolate', ['linear'], ['zoom'], 7, 0.3, 10, 0.8, 13, 1.4],
      },
    }, ENCIMA);
    // Resalte del cuadrado bajo el ratón o seleccionado (se activa con feature-state).
    map.addLayer({
      id: 'cuadricula-resalte', type: 'line', source: 'cuadricula',
      paint: {
        'line-color': ['case', ['boolean', ['feature-state', 'seleccionado'], false], '#f5b301', '#ffffff'],
        'line-width': ['case', ['boolean', ['feature-state', 'seleccionado'], false], 3, 2],
        'line-opacity': ['case',
          ['boolean', ['feature-state', 'seleccionado'], false], 1,
          ['boolean', ['feature-state', 'hover'], false], 0.95, 0],
      },
    }, ENCIMA);
  }
  mostrarCuadricula(map, true);
}

export function mostrarCuadricula(map, visible) {
  for (const capa of ['cuadricula-relleno', 'cuadricula-borde', 'cuadricula-resalte'])
    if (map.getLayer(capa)) map.setLayoutProperty(capa, 'visibility', visible ? 'visible' : 'none');
}

export function ponerOpacidadCuadricula(map, opacidad) {
  if (map.getLayer('cuadricula-relleno'))
    map.setPaintProperty('cuadricula-relleno', 'fill-opacity', opacidadCuadricula(opacidad));
}

// ---------------------------------------------------------------------
// COMUNIDADES Y PROVINCIAS (bordes para orientarse)
// ---------------------------------------------------------------------
export function ponerRegiones(map, datos) {
  if (map.getSource('regiones')) { map.getSource('regiones').setData(datos); mostrarRegiones(map, true); return; }
  map.addSource('regiones', { type: 'geojson', data: datos });
  // Provincias: línea fina discontinua, solo al acercarse un poco.
  map.addLayer({
    id: 'provincias-borde', type: 'line', source: 'regiones', minzoom: 6,
    filter: ['==', ['get', 'tipo'], 'provincia'],
    paint: {
      'line-color': '#ffffff',
      'line-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.35, 9, 0.6],
      'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.6, 10, 1.2],
      'line-dasharray': [3, 2],
    },
  }, ENCIMA);
  // Comunidades autónomas: línea blanca continua, con un halo oscuro para verse sobre cualquier color.
  map.addLayer({
    id: 'comunidades-halo', type: 'line', source: 'regiones',
    filter: ['==', ['get', 'tipo'], 'comunidad'],
    paint: { 'line-color': '#000000', 'line-opacity': 0.35,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 2.5, 10, 4.5] },
  }, ENCIMA);
  map.addLayer({
    id: 'comunidades-borde', type: 'line', source: 'regiones',
    filter: ['==', ['get', 'tipo'], 'comunidad'],
    paint: { 'line-color': '#ffffff', 'line-opacity': 0.9,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1, 10, 2] },
  }, ENCIMA);
  // Resalte de la región elegida en el buscador: ámbar con un contorno oscuro para que destaque.
  map.addLayer({
    id: 'region-resalte-halo', type: 'line', source: 'regiones',
    filter: ['==', ['get', 'tipo'], '__ninguna__'],
    paint: { 'line-color': '#000000', 'line-opacity': 0.6, 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 6, 10, 8] },
  }, ENCIMA);
  map.addLayer({
    id: 'region-resalte', type: 'line', source: 'regiones',
    filter: ['==', ['get', 'tipo'], '__ninguna__'],
    paint: { 'line-color': '#f5b301', 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 3, 10, 4.5] },
  }, ENCIMA);
}

// Resalta en ámbar una comunidad o provincia (la elegida en el buscador). null = quitar.
export function resaltarRegion(map, region) {
  if (!map.getLayer('region-resalte')) return;
  const filtro = region
    ? ['all', ['==', ['get', 'tipo'], region.tipo], ['==', ['get', 'nombre_es'], region.nombre]]
    : ['==', ['get', 'tipo'], '__ninguna__'];
  map.setFilter('region-resalte', filtro);
  map.setFilter('region-resalte-halo', filtro);
}

export function mostrarRegiones(map, visible) {
  for (const capa of ['provincias-borde', 'comunidades-halo', 'comunidades-borde', 'region-resalte-halo', 'region-resalte'])
    if (map.getLayer(capa)) map.setLayoutProperty(capa, 'visibility', visible ? 'visible' : 'none');
}

// ---------------------------------------------------------------------
// MARCADOR DEL LUGAR BUSCADO
// ---------------------------------------------------------------------
let marcador = null;
export function ponerMarcador(map, lonLat) {
  if (marcador) { marcador.remove(); marcador = null; }
  if (!lonLat) return;
  const el = document.createElement('div');
  el.className = 'marcador-busqueda';
  marcador = new maplibregl.Marker({ element: el }).setLngLat(lonLat).addTo(map);
}
