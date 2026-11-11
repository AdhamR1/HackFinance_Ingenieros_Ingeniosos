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

// NOMBRES DE LUGARES Y FRONTERAS: texto de verdad (no imágenes), nítido a cualquier zoom.
// Vienen de OpenFreeMap (gratis, sin clave, datos de OpenStreetMap).
const NOMBRES = { type: 'vector', url: 'https://tiles.openfreemap.org/planet' };
const FUENTES_TEXTO = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf';
const TEXTO_BLANCO = { 'text-color': '#ffffff', 'text-halo-color': 'rgba(0, 0, 0, 0.8)', 'text-halo-width': 1.5, 'text-halo-blur': 0.5 };
const nombreEn = idioma => ['coalesce', ['get', 'name:' + idioma], ['get', 'name']];

// Capas de nombres (de menos a más importantes: las últimas se dibujan encima).
function capasNombres(idioma, visible) {
  const v = { visibility: visible ? 'visible' : 'none' };
  const clase = lista => ['in', ['get', 'class'], ['literal', lista]];
  return [
    { id: 'fronteras', type: 'line', source: 'nombres', 'source-layer': 'boundary', minzoom: 4,
      filter: ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1]],
      layout: v, paint: { 'line-color': '#ffffff', 'line-opacity': 0.55, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.6, 10, 1.6] } },
    { id: 'nombres-barrios', type: 'symbol', source: 'nombres', 'source-layer': 'place', minzoom: 12,
      filter: clase(['suburb', 'neighbourhood', 'quarter', 'hamlet']),
      layout: { ...v, 'text-field': nombreEn(idioma), 'text-font': ['Noto Sans Regular'], 'text-size': 12 }, paint: TEXTO_BLANCO },
    { id: 'nombres-pueblos', type: 'symbol', source: 'nombres', 'source-layer': 'place', minzoom: 9,
      filter: clase(['village']),
      layout: { ...v, 'text-field': nombreEn(idioma), 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 9, 11, 14, 14] }, paint: TEXTO_BLANCO },
    { id: 'nombres-municipios', type: 'symbol', source: 'nombres', 'source-layer': 'place', minzoom: 7,
      filter: clase(['town']),
      layout: { ...v, 'text-field': nombreEn(idioma), 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 7, 11, 14, 16] }, paint: TEXTO_BLANCO },
    { id: 'nombres-ciudades', type: 'symbol', source: 'nombres', 'source-layer': 'place', minzoom: 4,
      filter: clase(['city']),
      layout: { ...v, 'text-field': nombreEn(idioma), 'text-font': ['Noto Sans Bold'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 4, 11, 8, 15, 12, 19] }, paint: TEXTO_BLANCO },
    { id: 'nombres-paises', type: 'symbol', source: 'nombres', 'source-layer': 'place', maxzoom: 7,
      filter: clase(['country']),
      layout: { ...v, 'text-field': nombreEn(idioma), 'text-font': ['Noto Sans Bold'], 'text-transform': 'uppercase',
        'text-letter-spacing': 0.12, 'text-size': ['interpolate', ['linear'], ['zoom'], 1, 10, 5, 14] },
      paint: { ...TEXTO_BLANCO, 'text-color': 'rgba(255, 255, 255, 0.85)' } },
  ];
}
const CAPAS_NOMBRES = ['fronteras', 'nombres-barrios', 'nombres-pueblos', 'nombres-municipios', 'nombres-ciudades', 'nombres-paises'];
// Todas nuestras capas (países, cuadrícula, bordes) se insertan justo debajo de los nombres.
const ENCIMA = 'fronteras';
let conNombres = true;

// creditos = { busqueda, limites, paises }: textos ya traducidos para la línea de créditos.
export function crearMapa(idContenedor, capaInicial, { nombres = true, idioma = 'es', creditos } = {}) {
  conNombres = nombres;
  const map = new maplibregl.Map({
    container: idContenedor,
    style: {
      version: 8,
      glyphs: FUENTES_TEXTO,
      sources: { satelite: CAPAS_BASE.satelite, mapa: CAPAS_BASE.mapa, nombres: NOMBRES },
      layers: [
        { id: 'fondo', type: 'background', paint: { 'background-color': '#05070a' } },
        { id: 'base-satelite', type: 'raster', source: 'satelite',
          layout: { visibility: capaInicial === 'satelite' ? 'visible' : 'none' } },
        { id: 'base-mapa', type: 'raster', source: 'mapa',
          layout: { visibility: capaInicial === 'mapa' ? 'visible' : 'none' } },
        // El mapa normal (OpenStreetMap) ya trae nombres; los nuestros solo hacen falta sobre el satélite.
        ...capasNombres(idioma, nombres && capaInicial === 'satelite'),
      ],
    },
    center: [10, 30],
    zoom: 1.6,
    minZoom: 1,
    maxZoom: 19,
    attributionControl: false, // se pone abajo, en ponerCreditos(), para poder traducirlo
    renderWorldCopies: false,
    dragRotate: false,
    pitchWithRotate: false,
  });
  map.touchZoomRotate.disableRotation();
  ponerCreditos(map, creditos);
  return map;
}

// Créditos (abajo a la derecha) y botones + / −.
// Los créditos son NUESTROS (no los de MapLibre): el de MapLibre se abre y se cierra solo
// (al cargar, al cambiar el tamaño, al arrastrar) y peleaba con nuestro código, dejando una
// barra negra vacía que ya no respondía. Este es un botón ⓘ sencillo que hace solo lo que pide
// el visitante. El texto es fijo (todas las fuentes que usa la web), así no cambia de tamaño al
// pasar de Satélite a Mapa.
const ESTRECHA = window.matchMedia('(max-width: 640px)');
let creditos = null; // { caja, boton, texto } una vez creados
// ¿Quiere el visitante los créditos abiertos? null = aún no ha tocado nada (entonces: abiertos en
// pantalla grande, plegados en móvil). Se recuerda al cambiar de idioma.
let creditosAbiertos = null;

function abrirCreditos(abrir) {
  creditos.caja.classList.toggle('abiertos', abrir);
  creditos.boton.setAttribute('aria-expanded', String(abrir));
  creditos.texto.hidden = !abrir;
}

class ControlCreditos {
  onAdd() {
    const caja = document.createElement('div');
    caja.className = 'maplibregl-ctrl creditos';
    caja.innerHTML = `
      <div class="creditos-texto" id="creditos-texto"></div>
      <button type="button" class="creditos-boton" aria-controls="creditos-texto">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9.2"/><path d="M12 11v6"/><circle cx="12" cy="7.6" r="0.6" fill="currentColor"/></svg>
      </button>`;
    creditos = { caja, boton: caja.querySelector('button'), texto: caja.querySelector('.creditos-texto') };
    creditos.boton.addEventListener('click', () => {
      creditosAbiertos = !caja.classList.contains('abiertos');
      abrirCreditos(creditosAbiertos);
    });
    return caja;
  }
  onRemove() {}
}

export function ponerCreditos(map, { busqueda = 'Búsqueda', limites = 'Límites administrativos', paises = 'Países',
  boton = 'Créditos del mapa', satelite = 'Satélite', mapa = 'Mapa', nombres = 'Nombres' } = {}) {
  if (!creditos) {
    // Orden de MapLibre: lo último que se añade abajo queda ENCIMA; así los créditos van debajo de + / −.
    map.addControl(new ControlCreditos(), 'bottom-right');
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    // En el móvil, los créditos abiertos tapan mapa: se pliegan al arrastrar (como hacía MapLibre).
    map.on('dragstart', () => {
      if (ESTRECHA.matches && creditos.caja.classList.contains('abiertos')) { creditosAbiertos = false; abrirCreditos(false); }
    });
    // Si el visitante no ha tocado nada y cambia el ancho de la ventana: abiertos en grande, plegados en móvil.
    ESTRECHA.addEventListener('change', () => { if (creditosAbiertos === null) abrirCreditos(!ESTRECHA.matches); });
    abrirCreditos(creditosAbiertos ?? !ESTRECHA.matches);
  }
  const enlace = (url, txt) => `<a href="${url}" target="_blank" rel="noopener">${txt}</a>`;
  creditos.texto.innerHTML =
      `${satelite}: Esri, Maxar, Earthstar Geographics, GIS User Community`
    + ` · ${mapa}: © ${enlace('https://www.openstreetmap.org/copyright', 'OpenStreetMap')}`
    + ` · ${nombres}: ${enlace('https://openfreemap.org', 'OpenFreeMap')}, © ${enlace('https://www.openmaptiles.org/', 'OpenMapTiles')}`
    + ` · ${busqueda}: ${enlace('https://photon.komoot.io', 'Photon')}`
    + ` · ${limites}: ${enlace('https://www.geoboundaries.org', 'geoBoundaries')} (CC BY 4.0)`
    + ` · ${paises}: Natural Earth`;
  creditos.boton.setAttribute('aria-label', boton);
  creditos.boton.title = boton;
}

// Cambia el idioma de los nombres de lugares ('es' o 'en').
export function ponerIdiomaNombres(map, idioma) {
  for (const id of CAPAS_NOMBRES)
    if (map.getLayer(id) && map.getLayer(id).type === 'symbol') map.setLayoutProperty(id, 'text-field', nombreEn(idioma));
}

// Cambia entre 'satelite' y 'mapa'.
export function ponerCapaBase(map, capa) {
  map.setLayoutProperty('base-satelite', 'visibility', capa === 'satelite' ? 'visible' : 'none');
  map.setLayoutProperty('base-mapa', 'visibility', capa === 'mapa' ? 'visible' : 'none');
  for (const id of CAPAS_NOMBRES)
    map.setLayoutProperty(id, 'visibility', conNombres && capa === 'satelite' ? 'visible' : 'none');
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
  const segunPais = ['case',
    ['==', ['get', 'iso'], seleccionado || ''], 0,
    esDisponible, ['case', enHover, 0.45, 0.25],
    ['in', ['get', 'iso'], ['literal', paisesProximamente]], ['case', enHover, 0.55, 0.4],
    ['case', enHover, 0.5, 0.4]];
  // Al acercarse, el gris de los países se desvanece: sus siluetas son aproximadas
  // y taparían el terreno. De cerca mandan las fronteras precisas (capa "fronteras").
  return ['interpolate', ['linear'], ['zoom'], 4.5, segunPais, 6.5, 0];
}

// Bordes aproximados de los países (solo para la vista del mundo; se desvanecen al acercarse).
function opacidadBordesPaises(seleccionado) {
  const esDisponible = ['in', ['get', 'iso'], ['literal', paisesDisponibles]];
  return ['interpolate', ['linear'], ['zoom'], 3.5,
    ['case', ['==', ['get', 'iso'], seleccionado || ''], 0, esDisponible, 0.9, 0.35], 5, 0];
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
      'line-opacity': opacidadBordesPaises(null),
      'line-width': ['case', esDisponible, 1.5, 0.6],
    },
  }, ENCIMA);
}

// Marca un país como "abierto" (o ninguno, con null).
export function marcarPaisSeleccionado(map, iso) {
  map.setPaintProperty('paises-relleno', 'fill-opacity', opacidadPaises(iso));
  // El borde simplificado del país abierto se oculta: su cuadrícula ya dibuja la forma.
  map.setPaintProperty('paises-borde', 'line-opacity', opacidadBordesPaises(iso));
}

// ---------------------------------------------------------------------
// CUADRÍCULA DE UN PAÍS
// ---------------------------------------------------------------------
// Opacidad del relleno: exactamente la elegida por el usuario, igual en todos
// los niveles de zoom (antes bajaba sola al acercarse y confundía).
function opacidadCuadricula(opacidad) {
  return opacidad;
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
// Los bordes vienen de la misma fuente que el contorno con el que se recorta
// la cuadrícula, así que coinciden con los cuadrados.
export function ponerRegiones(map, datos) {
  if (map.getSource('regiones')) { map.getSource('regiones').setData(datos); mostrarRegiones(map, true); return; }
  map.addSource('regiones', { type: 'geojson', data: datos });
  // Provincias: línea fina discontinua, solo al acercarse un poco.
  map.addLayer({
    id: 'provincias-borde', type: 'line', source: 'regiones', minzoom: 6,
    filter: ['==', ['get', 'tipo'], 'linea_provincia'],
    paint: {
      'line-color': '#ffffff',
      'line-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.25, 9, 0.45],
      'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.6, 10, 1.2],
      'line-dasharray': [3, 2],
    },
  }, ENCIMA);
  // Comunidades autónomas: línea blanca continua, discreta.
  map.addLayer({
    id: 'comunidades-borde', type: 'line', source: 'regiones',
    filter: ['==', ['get', 'tipo'], 'linea_comunidad'],
    paint: { 'line-color': '#ffffff', 'line-opacity': 0.5,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.9, 10, 1.8] },
  }, ENCIMA);
}

export function mostrarRegiones(map, visible) {
  for (const capa of ['provincias-borde', 'comunidades-borde'])
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
