// Arranque de la web y flujo principal: mundo → elegir país → cuadrícula.
import { CONFIG } from '../config.js';
import { t, idioma, iniciarIdioma, alCambiarIdioma } from './i18n.js';
import { crearMapa, anadirPaises, marcarPaisSeleccionado } from './mapa.js';

const $ = id => document.getElementById(id);

const estado = {
  paises: {},        // contenido de data/paises.json (países con datos)
  mundo: null,       // siluetas de todos los países
  paisAbierto: null, // código del país que se está viendo, p. ej. 'ES'
};

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

let temporizadorAviso;
function mostrarAviso(texto) {
  const aviso = $('aviso');
  aviso.textContent = texto;
  aviso.hidden = false;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => { aviso.hidden = true; }, 4000);
}

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
function abrirPais(map, iso) {
  if (!tieneDatos(iso)) return;
  const info = estado.paises[iso];
  estado.paisAbierto = iso;
  ocultarTooltip();
  marcarPaisSeleccionado(map, iso);
  // Encuadra el país (limites = [[oeste, sur], [este, norte]]) dejando sitio a los controles.
  const estrecho = window.innerWidth <= 640;
  map.fitBounds(info.limites, {
    padding: estrecho ? { top: 120, bottom: 40, left: 10, right: 10 } : { top: 90, bottom: 50, left: 40, right: 40 },
    speed: 1.4, essential: true,
  });
  $('selector-pais').value = iso;
  $('boton-mundo').hidden = false;
  history.replaceState(null, '', `#${iso}`);
  // Paso 3: aquí se cargará la cuadrícula del país (info.archivo).
}

function volverAlMundo(map) {
  estado.paisAbierto = null;
  marcarPaisSeleccionado(map, null);
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

  map.on('mousemove', 'paises-relleno', e => {
    const f = e.features[0];
    const iso = f.properties.iso;
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
    if (iso === estado.paisAbierto) return;
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
    mostrarAviso(t('error_carga', { pais: '—' }));
    return;
  }

  const map = crearMapa('mapa', CONFIG.capa_inicial);
  window.__mapa = map; // útil para depurar desde la consola del navegador

  map.on('load', () => {
    anadirPaises(map, estado.mundo, Object.keys(estado.paises), CONFIG.paises_proximamente);
    activarInteraccionPaises(map);
    rellenarSelector();

    // Si la dirección termina en #ES, se abre España directamente.
    const desdeEnlace = location.hash.slice(1).toUpperCase();
    if (tieneDatos(desdeEnlace)) abrirPais(map, desdeEnlace);
    window.__listo = true; // señal para las pruebas automáticas
  });

  $('selector-pais').addEventListener('change', e => {
    if (e.target.value) abrirPais(map, e.target.value);
    else volverAlMundo(map);
  });
  $('boton-mundo').addEventListener('click', () => volverAlMundo(map));

  alCambiarIdioma(() => { if (estado.mundo) rellenarSelector(); });
}

iniciar();
