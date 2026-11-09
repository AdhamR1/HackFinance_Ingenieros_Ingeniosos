// Arranque de la web y flujo principal: mundo → elegir país → cuadrícula.
import { CONFIG } from '../config.js';
import { t, idioma, iniciarIdioma, alCambiarIdioma, ponerIdioma } from './i18n.js';
import {
  crearMapa, anadirPaises, marcarPaisSeleccionado, ponerCuadricula, mostrarCuadricula,
  ponerRegiones, mostrarRegiones, ponerMarcador, ponerIdiomaNombres,
  ponerCapaBase, ponerOpacidadCuadricula, ponerCreditos,
} from './mapa.js';
import { pintarPanel, ponerLugar, pintarLeyenda, textoTooltip } from './panel.js';
import { evaluar } from './puntuacion.js';
import { crearBuscador } from './buscador.js';

const $ = id => document.getElementById(id);

const estado = {
  paises: {},        // contenido de data/paises.json (países con datos)
  mundo: null,       // siluetas de todos los países
  paisAbierto: null, // código del país que se está viendo, p. ej. 'ES'
  datosPais: {},     // cuadrículas ya descargadas, por país
  regiones: {},      // comunidades/provincias ya descargadas, por país
  opacidad: leerPreferencia('cibh_opacidad', CONFIG.opacidad_inicial, Number),
  capa: leerPreferencia('cibh_capa', CONFIG.capa_inicial, String),
  porId: {},         // por país: id del cuadrado → cuadrado (para abrir el panel)
  seleccionado: null,// id del cuadrado abierto en el panel
};

// Preferencias de cada visitante (opacidad, capa). Si el navegador no deja guardar, no pasa nada.
function leerPreferencia(clave, porDefecto, tipo) {
  try { const v = localStorage.getItem(clave); return v === null ? porDefecto : tipo(v); } catch { return porDefecto; }
}
function guardarPreferencia(clave, valor) { try { localStorage.setItem(clave, String(valor)); } catch { /* nada */ } }

// ---------- Utilidades ----------
function nombrePais(iso) {
  const f = estado.mundo.features.find(x => x.properties.iso === iso);
  if (!f) return iso;
  return idioma() === 'es' ? f.properties.nombre_es : f.properties.nombre_en;
}

const tieneDatos = iso => Object.hasOwn(estado.paises, iso);
const esProximamente = iso => !tieneDatos(iso) && CONFIG.paises_proximamente.includes(iso);
// Texto pequeño bajo el nombre del país: nada si tiene datos.
const notaPais = iso => tieneDatos(iso) ? '' : t(esProximamente(iso) ? 'proximamente' : 'no_disponible');

function mostrarTooltip(x, y, html) {
  const tip = $('tooltip');
  tip.innerHTML = html;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
  tip.hidden = false;
}
const ocultarTooltip = () => { $('tooltip').hidden = true; };

// El aviso recibe una función que da el texto, para poder repetirla si cambia el idioma.
let temporizadorAviso;
let textoAviso = () => '';
function mostrarAviso(texto, duracionMs = 4000) {
  const aviso = $('aviso');
  textoAviso = texto;
  aviso.textContent = texto();
  aviso.hidden = false;
  clearTimeout(temporizadorAviso);
  if (duracionMs) temporizadorAviso = setTimeout(() => { aviso.hidden = true; }, duracionMs);
}
const ocultarAviso = () => { $('aviso').hidden = true; };

const escaparHtml = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---------- Selector de país ----------
function rellenarSelector() {
  const sel = $('selector-pais');
  const ordenar = lista => lista.sort((a, b) => a.nombre.localeCompare(b.nombre, idioma()));
  const conDatos = ordenar(Object.keys(estado.paises).map(iso => ({ iso, nombre: nombrePais(iso) })));
  const proximos = ordenar(CONFIG.paises_proximamente.filter(esProximamente)
    .map(iso => ({ iso, nombre: nombrePais(iso) })));

  const opcion = (p, desactivada) =>
    `<option value="${p.iso}"${desactivada ? ' disabled' : ''}>${escaparHtml(p.nombre)}</option>`;

  sel.innerHTML =
    `<option value="">${escaparHtml(t('elige_pais'))}</option>` +
    `<optgroup label="${escaparHtml(t('paises_disponibles'))}">${conDatos.map(p => opcion(p, false)).join('')}</optgroup>` +
    `<optgroup label="${escaparHtml(t('paises_proximamente'))}">${proximos.map(p => opcion(p, true)).join('')}</optgroup>`;
  sel.value = estado.paisAbierto || '';
}

// ---------- Abrir / cerrar país ----------
// Margen para que los controles flotantes no tapen lo que se encuadra.
const margenEncuadre = () => window.innerWidth <= 640
  ? { top: 170, bottom: 40, left: 10, right: 10 }
  : { top: 90, bottom: 50, left: 40, right: 40 };

// encuadrar: false cuando luego se va a hacer zoom a otro sitio (p. ej. desde el buscador).
function abrirPais(map, iso, { encuadrar = true } = {}) {
  if (!tieneDatos(iso)) return;
  const info = estado.paises[iso];
  const yaAbierto = estado.paisAbierto === iso;
  estado.paisAbierto = iso;
  ocultarTooltip();
  marcarPaisSeleccionado(map, iso);
  // Encuadra el país (limites = [[oeste, sur], [este, norte]]).
  if (encuadrar) map.fitBounds(info.limites, { padding: margenEncuadre(), speed: 1.4, essential: true });
  if (yaAbierto) return;
  $('selector-pais').value = iso;
  $('boton-mundo').hidden = false;
  history.replaceState(null, '', `#${iso}`);
  // Primero la cuadrícula (lo importante); los bordes de comunidades, después.
  cargarCuadricula(map, iso).finally(() =>
    cargarRegiones(iso).then(datos => { if (datos && estado.paisAbierto === iso) ponerRegiones(map, datos); }));
}

// Comunidades y provincias del país (si el país las tiene en data/paises.json).
async function cargarRegiones(iso) {
  const archivo = estado.paises[iso]?.regiones;
  if (!archivo) return null;
  estado.regiones[iso] ??= fetch(archivo).then(r => r.json()).catch(err => { console.error(err); delete estado.regiones[iso]; return null; });
  return estado.regiones[iso];
}

// Descarga del archivo de datos de un país. Se guarda la promesa para no descargarlo dos veces
// (puede empezar antes, en segundo plano, mientras el visitante mira el mapa del mundo).
const descargas = {};
function descargarDatos(iso) {
  descargas[iso] ??= fetch(estado.paises[iso].archivo).then(res => {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  });
  descargas[iso].catch(() => { delete descargas[iso]; }); // si falla, se podrá reintentar
  return descargas[iso];
}

// Descarga (solo la primera vez) la cuadrícula del país y la pinta.
// Solo se cargan los cuadrados del país abierto.
async function cargarCuadricula(map, iso) {
  let datos = estado.datosPais[iso];
  if (!datos) {
    mostrarAviso(() => t('cargando'), 0);
    try {
      datos = await descargarDatos(iso);
    } catch (err) {
      console.error(err);
      mostrarAviso(() => t('error_carga', { pais: nombrePais(iso) }));
      return;
    }
    if (estado.datosPais[iso]) datos = estado.datosPais[iso]; // ya preparado por otra llamada
    // Se calcula una vez la nota y el color de cada cuadrado (reglas de config.js).
    for (const f of datos.features) {
      const r = evaluar(f.properties);
      f.properties._color = r.color;
      f.properties._categoria = r.categoria;
      f.properties._nota = r.nota ?? -1;
    }
    estado.datosPais[iso] = datos;
    estado.porId[iso] = new Map(datos.features.map(f => [f.properties.id, f]));
    ocultarAviso();
  }
  if (estado.paisAbierto !== iso) return; // el usuario se fue a otro sitio mientras cargaba
  ponerCuadricula(map, datos, estado.opacidad);
  activarInteraccionCuadricula(map);
  $('bloque-cuadricula').hidden = false;
}

function volverAlMundo(map) {
  estado.paisAbierto = null;
  marcarPaisSeleccionado(map, null);
  mostrarCuadricula(map, false);
  mostrarRegiones(map, false);
  ponerMarcador(map, null);
  cerrarPanel(map);
  $('bloque-cuadricula').hidden = true;
  buscador?.limpiar();
  map.flyTo({ center: [10, 30], zoom: 1.6, speed: 1.4, essential: true });
  $('selector-pais').value = '';
  $('boton-mundo').hidden = true;
  history.replaceState(null, '', location.pathname);
}

// ---------- Interacción con los países en el mapa ----------
function activarInteraccionPaises(map) {
  let hoverId = null;
  const quitarHover = () => {
    if (hoverId !== null) map.setFeatureState({ source: 'paises', id: hoverId }, { hover: false });
    hoverId = null;
  };

  // Si hay un cuadrado de la cuadrícula bajo el ratón, manda el cuadrado (no el país de al lado,
  // cuyo borde puede montar un poco sobre la cuadrícula).
  const hayCuadrado = punto => estado.paisAbierto && map.getLayer('cuadricula-relleno') &&
    map.getLayoutProperty('cuadricula-relleno', 'visibility') !== 'none' &&
    map.queryRenderedFeatures(punto, { layers: ['cuadricula-relleno'] }).length > 0;

  map.on('mousemove', 'paises-relleno', e => {
    const f = e.features[0];
    const iso = f.properties.iso;
    if (hayCuadrado(e.point)) { quitarHover(); return; } // de esto se encarga la cuadrícula
    if (iso === estado.paisAbierto) { quitarHover(); ocultarTooltip(); map.getCanvas().style.cursor = ''; return; }
    if (f.id !== hoverId) {
      quitarHover();
      hoverId = f.id;
      map.setFeatureState({ source: 'paises', id: hoverId }, { hover: true });
    }
    map.getCanvas().style.cursor = tieneDatos(iso) ? 'pointer' : 'not-allowed';
    const nota = tieneDatos(iso) ? '' : `<div class="tooltip-nota">${escaparHtml(notaPais(iso))}</div>`;
    mostrarTooltip(e.originalEvent.clientX, e.originalEvent.clientY, `<strong>${escaparHtml(nombrePais(iso))}</strong>${nota}`);
  });
  map.on('mouseleave', 'paises-relleno', () => {
    quitarHover();
    ocultarTooltip();
    map.getCanvas().style.cursor = '';
  });

  map.on('click', 'paises-relleno', e => {
    const iso = e.features[0].properties.iso;
    if (iso === estado.paisAbierto || hayCuadrado(e.point)) return;
    if (tieneDatos(iso)) {
      abrirPais(map, iso);
    } else {
      // En móvil no hay "pasar el ratón": enseñamos el aviso al tocar.
      mostrarTooltip(e.originalEvent.clientX ?? e.point.x, e.originalEvent.clientY ?? e.point.y,
        `<strong>${escaparHtml(nombrePais(iso))}</strong><div class="tooltip-nota">${escaparHtml(notaPais(iso))}</div>`);
      setTimeout(ocultarTooltip, 1800);
    }
  });
}

// ---------- Cuadrícula: pasar el ratón y pulsar ----------
const conRaton = window.matchMedia('(hover: hover)').matches; // en móvil no hay "pasar el ratón"
let interaccionActiva = false;

function activarInteraccionCuadricula(map) {
  if (interaccionActiva) return;
  interaccionActiva = true;
  let hoverId = null;
  const quitarHover = () => {
    if (hoverId !== null) map.setFeatureState({ source: 'cuadricula', id: hoverId }, { hover: false });
    hoverId = null;
  };

  map.on('mousemove', 'cuadricula-relleno', e => {
    const f = e.features[0];
    if (f.id !== hoverId) {
      quitarHover();
      hoverId = f.id;
      map.setFeatureState({ source: 'cuadricula', id: hoverId }, { hover: true });
    }
    map.getCanvas().style.cursor = 'pointer';
    if (!conRaton) return;
    const original = estado.porId[estado.paisAbierto]?.get(f.id);
    if (original) mostrarTooltip(e.originalEvent.clientX, e.originalEvent.clientY, textoTooltip(original.properties));
  });
  map.on('mouseleave', 'cuadricula-relleno', () => {
    quitarHover();
    ocultarTooltip();
    map.getCanvas().style.cursor = '';
  });

  const alPulsar = punto => {
    if (!estado.paisAbierto) return;
    const f = map.queryRenderedFeatures(punto, { layers: ['cuadricula-relleno'] })[0];
    if (f) abrirPanel(map, f.id);
    else cerrarPanel(map); // pulsar fuera de la cuadrícula: se cierra el panel
  };

  // Ratón: el clic de siempre.
  let ultimoToque = 0;
  map.on('click', e => { if (Date.now() - ultimoToque > 600) alPulsar(e.point); });

  // Pantallas táctiles: algunos navegadores no convierten el toque en "clic" sobre el mapa,
  // así que se reconoce aquí un toque corto (menos de 350 ms y casi sin arrastrar).
  let inicio = null;
  map.on('touchstart', e => {
    inicio = e.points.length === 1 ? { x: e.point.x, y: e.point.y, t: Date.now() } : null;
  });
  map.on('touchend', e => {
    if (!inicio || e.points.length > 0 && e.originalEvent.touches.length > 0) { inicio = null; return; }
    const quieto = Math.hypot(e.point.x - inicio.x, e.point.y - inicio.y) < 10;
    if (quieto && Date.now() - inicio.t < 350) { ultimoToque = Date.now(); alPulsar(e.point); }
    inicio = null;
  });
}

// ---------- Panel lateral ----------
let peticionLugar = null;
const lugaresCache = new Map();

function abrirPanel(map, id) {
  const f = estado.porId[estado.paisAbierto]?.get(id);
  if (!f) return;
  if (estado.seleccionado !== null) map.setFeatureState({ source: 'cuadricula', id: estado.seleccionado }, { seleccionado: false });
  estado.seleccionado = id;
  map.setFeatureState({ source: 'cuadricula', id }, { seleccionado: true });
  ocultarTooltip();
  const centro = pintarPanel(f, estado.datosPais[estado.paisAbierto].meta);
  $('panel').hidden = false;
  $('panel').scrollTop = 0;
  if (centro) buscarLugarCercano(id, centro);
  // En móvil el panel tapa la mitad de abajo: se sube el mapa para que el cuadrado quede a la vista.
  if (centro && window.innerWidth <= 640) {
    const arribaPanel = $('panel').getBoundingClientRect().top;
    const hueco = $('buscador-input').getBoundingClientRect().bottom;
    const yDeseada = (hueco + arribaPanel) / 2;
    const punto = map.project(centro);
    if (punto.y > arribaPanel - 20 || punto.y < hueco + 20)
      map.easeTo({ center: centro, offset: [0, yDeseada - window.innerHeight / 2], duration: 400 });
  }
}

function cerrarPanel(map) {
  if (estado.seleccionado !== null && map.getSource('cuadricula'))
    map.setFeatureState({ source: 'cuadricula', id: estado.seleccionado }, { seleccionado: false });
  estado.seleccionado = null;
  $('panel').hidden = true;
}

// "Cerca de Calatayud · Zaragoza" con Photon (al revés: de coordenadas a nombre).
async function buscarLugarCercano(id, [lon, lat]) {
  const clave = `${id}|${idioma()}`;
  if (lugaresCache.has(clave)) { ponerLugar(lugaresCache.get(clave)); return; }
  if (!CONFIG.buscar_con_photon) return;
  peticionLugar?.abort();
  peticionLugar = new AbortController();
  try {
    const url = `https://photon.komoot.io/reverse?lon=${lon}&lat=${lat}&limit=1&layer=city&radius=15${idioma() === 'en' ? '&lang=en' : ''}`;
    const datos = await (await fetch(url, { signal: peticionLugar.signal })).json();
    const p = datos.features?.[0]?.properties;
    const texto = p ? [p.name, p.county && p.county !== p.name ? p.county : null].filter(Boolean).join(' · ') : '';
    lugaresCache.set(clave, texto);
    if (estado.seleccionado === id) ponerLugar(texto);
  } catch (err) {
    if (err.name !== 'AbortError') console.warn('No se pudo obtener el lugar cercano:', err);
  }
}

// ---------- Controles: capa base, opacidad, leyenda ----------
function activarControles(map) {
  const botonesCapa = document.querySelectorAll('.segmentado button');
  const marcarCapa = () => botonesCapa.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.capa === estado.capa)));
  botonesCapa.forEach(b => b.addEventListener('click', () => {
    estado.capa = b.dataset.capa;
    guardarPreferencia('cibh_capa', estado.capa);
    ponerCapaBase(map, estado.capa);
    marcarCapa();
  }));
  marcarCapa();

  const deslizador = $('opacidad');
  const mostrarValor = () => { $('opacidad-valor').textContent = t('porcentaje', { n: Math.round(estado.opacidad * 100) }); };
  alCambiarIdioma(mostrarValor);
  deslizador.value = Math.round(estado.opacidad * 100);
  mostrarValor();
  deslizador.addEventListener('input', () => {
    estado.opacidad = Number(deslizador.value) / 100;
    ponerOpacidadCuadricula(map, estado.opacidad);
    mostrarValor();
  });
  deslizador.addEventListener('change', () => guardarPreferencia('cibh_opacidad', estado.opacidad));

  // Plegar / desplegar la tarjeta (en móvil empieza plegada para no tapar el mapa).
  const tarjeta = $('controles-mapa'), boton = $('boton-plegar');
  const plegar = plegada => { tarjeta.classList.toggle('plegada', plegada); boton.setAttribute('aria-expanded', String(!plegada)); };
  plegar(window.matchMedia('(max-width: 640px)').matches);
  boton.addEventListener('click', () => plegar(!tarjeta.classList.contains('plegada')));

  pintarLeyenda();

  // Botón "ES | EN": marca el idioma activo y cambia al pulsar el otro.
  const botonesIdioma = document.querySelectorAll('.idiomas button');
  const marcarIdioma = () => botonesIdioma.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.idioma === idioma())));
  botonesIdioma.forEach(b => b.addEventListener('click', () => ponerIdioma(b.dataset.idioma)));
  marcarIdioma();
  alCambiarIdioma(marcarIdioma);

  $('panel-cerrar').addEventListener('click', () => cerrarPanel(map));
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('panel').hidden) cerrarPanel(map); });
}

// ---------- Buscador ----------
let buscador = null;

function irALugar(map, r) {
  if (r.pais && r.pais !== estado.paisAbierto) abrirPais(map, r.pais, { encuadrar: false });
  // Pueblos y ciudades llevan un marcador; comunidades y provincias solo se encuadran.
  ponerMarcador(map, r.region ? null : r.punto);
  // Si el lugar es muy pequeño (un pueblo), se acerca a una vista de unos 15-20 km.
  if (r.caja) {
    map.fitBounds([[r.caja[0], r.caja[1]], [r.caja[2], r.caja[3]]],
      { padding: margenEncuadre(), maxZoom: r.region ? 10 : 12, speed: 1.4, essential: true });
  } else if (r.punto) {
    map.flyTo({ center: r.punto, zoom: 12, speed: 1.4, essential: true });
  }
}

// ---------- Inicio ----------
async function iniciar() {
  await iniciarIdioma();
  $('etiqueta-prueba').hidden = !CONFIG.mostrar_etiqueta_datos_prueba;

  try {
    const [paises, mundo] = await Promise.all([
      fetch('data/paises.json').then(r => r.json()),
      fetch('data/mundo.geojson').then(r => r.json()),
    ]);
    estado.paises = paises;
    estado.mundo = mundo;
  } catch (err) {
    console.error(err);
    mostrarAviso(() => t('error_carga', { pais: '—' }));
    return;
  }

  const creditos = () => ({ busqueda: t('credito_busqueda'), limites: t('credito_limites'), paises: t('credito_paises') });
  const map = crearMapa('mapa', estado.capa, { nombres: CONFIG.mostrar_nombres_lugares, idioma: idioma(), creditos: creditos() });
  window.__mapa = map; // útil para depurar desde la consola del navegador

  map.on('load', () => {
    anadirPaises(map, estado.mundo, Object.keys(estado.paises), CONFIG.paises_proximamente);
    activarInteraccionPaises(map);
    rellenarSelector();

    // Si la dirección termina en #ES, se abre España directamente.
    const desdeEnlace = location.hash.slice(1).toUpperCase();
    if (tieneDatos(desdeEnlace)) abrirPais(map, desdeEnlace);
    window.__listo = true; // señal para las pruebas automáticas

    // Precarga: si solo hay un país con datos, casi seguro que el visitante lo abrirá.
    // Se descarga ya en segundo plano para que al elegirlo aparezca mucho antes.
    const conDatos = Object.keys(estado.paises);
    if (CONFIG.precargar_datos && conDatos.length === 1 && !estado.paisAbierto)
      setTimeout(() => descargarDatos(conDatos[0]).catch(() => {}), 300);
  });

  $('selector-pais').addEventListener('change', e => {
    if (e.target.value) abrirPais(map, e.target.value);
    else volverAlMundo(map);
  });
  $('boton-mundo').addEventListener('click', () => volverAlMundo(map));
  activarControles(map);

  buscador = crearBuscador({
    input: $('buscador-input'),
    lista: $('buscador-lista'),
    paisesConDatos: () => Object.keys(estado.paises),
    cargarRegiones: async () => (await Promise.all(Object.keys(estado.paises).map(async pais =>
      ({ pais, features: (await cargarRegiones(pais))?.features ?? [] })))),
    alElegir: r => irALugar(map, r),
  });

  alCambiarIdioma(nuevo => {
    ocultarTooltip(); // se vuelve a pintar, ya traducido, en cuanto se mueve el ratón
    if (!$('aviso').hidden) $('aviso').textContent = textoAviso();
    buscador?.refrescar();
    if (estado.mundo) rellenarSelector();
    ponerIdiomaNombres(map, nuevo); // (sin esperar a isStyleLoaded: da "no" mientras se cargan imágenes y se saltaba el cambio)
    ponerCreditos(map, creditos());
    pintarLeyenda();
    if (estado.seleccionado !== null) abrirPanel(map, estado.seleccionado); // repinta el panel en el nuevo idioma
  });
}

iniciar();
