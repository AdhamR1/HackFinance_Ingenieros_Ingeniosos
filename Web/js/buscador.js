// Buscador de lugares (estilo Google Maps).
//  - Comunidades autónomas y provincias: se buscan al instante, sin internet
//    (vienen de data/XX_regiones.json).
//  - Pueblos y ciudades: con Photon (https://photon.komoot.io), gratuito y sin clave,
//    basado en OpenStreetMap. Solo se le pregunta cuando se escriben 3 letras o más
//    y se para de escribir un momento, para no abusar del servicio.
import { CONFIG } from '../config.js';
import { t, idioma } from './i18n.js';

const ESPERA_MS = 350;
const MAX_LOCALES = 6;
const MAX_REMOTOS = 6;

// "Ávila" → "avila": sin tildes ni mayúsculas, para comparar.
const normalizar = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const escaparHtml = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// opciones:
//   input, lista              → elementos del HTML
//   cargarRegiones()          → promesa con [{ pais, features }] de los países con datos
//   paisesConDatos()          → ['ES', ...]
//   paisActual()              → país abierto ('ES', 'JP'…) o null en la vista del mundo:
//                               con un país abierto solo se sugieren lugares de ese país
//   alElegir(resultado)       → qué hacer al elegir: { nombre, pais, caja?, punto?, region? }
export function crearBuscador({ input, lista, cargarRegiones, paisesConDatos, paisActual = () => null, alElegir }) {
  let indice = null;       // lugares locales (comunidades y provincias)
  let cajas = {};          // rectángulo que cubre cada país con datos (para Photon)
  let resultados = [];
  let activo = -1;
  let temporizador = null;
  let peticion = null;     // para cancelar la búsqueda anterior en Photon
  let elegido = null;      // último resultado elegido (para traducir su nombre en la caja)

  async function prepararIndice() {
    if (indice) return;
    const porPais = await cargarRegiones();
    indice = [];
    for (const { pais, features } of porPais) {
      let [o, s, e, n] = [180, 90, -180, -90];
      // Nombre en inglés de cada comunidad, para el "Provincia · Comunidad" de las provincias.
      const comunidadEn = new Map(features.filter(f => f.properties.tipo === 'comunidad')
        .map(f => [f.properties.nombre_es, f.properties.nombre_en]));
      for (const f of features) {
        const p = f.properties;
        if (p.tipo !== 'comunidad' && p.tipo !== 'provincia') continue; // las líneas de borde no tienen nombre
        const nombres = [p.nombre_es, p.nombre_en, ...(p.alias || [])];
        indice.push({
          tipo: p.tipo, pais, caja: p.caja, comunidad: p.comunidad, comunidad_en: comunidadEn.get(p.comunidad) ?? p.comunidad,
          nombre_es: p.nombre_es, nombre_en: p.nombre_en,
          claves: [...new Set(nombres.map(normalizar))],
        });
        o = Math.min(o, p.caja[0]); s = Math.min(s, p.caja[1]); e = Math.max(e, p.caja[2]); n = Math.max(n, p.caja[3]);
      }
      if (o <= e) cajas[pais] = [o, s, e, n];
    }
  }

  const nombreLocal = l => (idioma() === 'en' ? l.nombre_en : l.nombre_es);
  // Con un país abierto, solo sus lugares; en la vista del mundo, los de todos los países con datos.
  const delPais = l => !paisActual() || l.pais === paisActual();
  // En Japón las regiones grandes son prefecturas (en los datos vienen como tipo "comunidad").
  const tipoRegion = l => (l.pais === 'JP' ? t('tipo_prefectura') : t('tipo_comunidad'));
  const aResultadoLocal = l => ({
    nombre: nombreLocal(l),
    detalle: l.tipo === 'comunidad' ? tipoRegion(l) : `${t('tipo_provincia')} · ${idioma() === 'en' ? l.comunidad_en : l.comunidad}`,
    pais: l.pais, caja: l.caja, region: { tipo: l.tipo, nombre: l.nombre_es }, icono: l.tipo === 'comunidad' ? '◇' : '▫',
    local: l,
  });

  function buscarLocal(texto) {
    const q = normalizar(texto);
    const puntos = l => {
      if (l.claves.some(k => k.startsWith(q))) return 0;                       // empieza igual
      if (l.claves.some(k => k.split(/[\s/-]+/).some(w => w.startsWith(q)))) return 1; // alguna palabra empieza igual
      return null;
    };
    return indice.filter(delPais).map(l => ({ l, p: puntos(l) })).filter(x => x.p !== null)
      .sort((a, b) => a.p - b.p
        || (a.l.tipo === 'comunidad' ? 0 : 1) - (b.l.tipo === 'comunidad' ? 0 : 1)   // comunidades primero
        || nombreLocal(a.l).localeCompare(nombreLocal(b.l), idioma()))
      .slice(0, MAX_LOCALES).map(x => aResultadoLocal(x.l));
  }

  async function buscarPhoton(texto) {
    if (!CONFIG.buscar_con_photon || normalizar(texto).length < 3) return [];
    peticion?.abort();
    peticion = new AbortController();
    const url = new URL('https://photon.komoot.io/api/');
    url.searchParams.set('q', texto);
    url.searchParams.set('limit', '15');
    if (idioma() === 'en') url.searchParams.set('lang', 'en'); // nombres en inglés si los hay (Seville, Corunna…)
    // Rectángulo del país abierto o, en la vista del mundo, el que cubre todos los países con datos.
    const pais = paisActual();
    const lista_ = pais ? [cajas[pais]].filter(Boolean) : Object.values(cajas);
    if (lista_.length) url.searchParams.set('bbox', [Math.min(...lista_.map(c => c[0])), Math.min(...lista_.map(c => c[1])),
      Math.max(...lista_.map(c => c[2])), Math.max(...lista_.map(c => c[3]))].join(','));
    const res = await fetch(url, { signal: peticion.signal });
    if (!res.ok) throw new Error(`Photon ${res.status}`);
    const datos = await res.json();
    const conDatos = pais ? [pais] : paisesConDatos();
    const vistos = new Set();
    const TIPOS = { city: 'tipo_ciudad', town: 'tipo_municipio', village: 'tipo_pueblo', hamlet: 'tipo_aldea',
      suburb: 'tipo_barrio', neighbourhood: 'tipo_barrio', quarter: 'tipo_barrio', municipality: 'tipo_municipio',
      island: 'tipo_isla', islet: 'tipo_isla' };
    const salida = [];
    for (const f of datos.features) {
      const p = f.properties;
      if (!conDatos.includes(p.countrycode)) continue;          // solo países con datos
      if (p.osm_key !== 'place') continue;                   // solo poblaciones (no calles, estaciones, tiendas…)
      // Comunidades, provincias y comarcas ya las da el índice local (evita duplicados).
      if (['state', 'country'].includes(p.type) || ['state', 'province', 'region', 'county'].includes(p.osm_value)) continue;
      const detalle = [t(TIPOS[p.osm_value] || 'tipo_lugar'), p.county || p.state].filter(Boolean).join(' · ');
      const clave = normalizar(`${p.name}|${detalle}`);
      if (!p.name || vistos.has(clave)) continue;
      vistos.add(clave);
      const ext = p.extent; // [oeste, norte, este, sur]
      salida.push({
        nombre: p.name, detalle, pais: p.countrycode, icono: '•',
        punto: f.geometry.coordinates,
        caja: ext ? [ext[0], ext[3], ext[2], ext[1]] : null,
      });
      if (salida.length >= MAX_REMOTOS) break;
    }
    return salida;
  }

  // ---------- Lista de resultados ----------
  function pintar(lista_, { cargando = false, sinResultados = false } = {}) {
    resultados = lista_;
    activo = resultados.length ? 0 : -1;
    let html = resultados.map((r, i) =>
      `<li role="option" id="busca-op-${i}" class="busca-op${i === activo ? ' activo' : ''}" data-i="${i}">` +
      `<span class="busca-icono" aria-hidden="true">${r.icono}</span>` +
      `<span class="busca-textos"><span class="busca-nombre">${escaparHtml(r.nombre)}</span>` +
      `<span class="busca-detalle">${escaparHtml(r.detalle)}</span></span></li>`).join('');
    if (cargando) html += `<li class="busca-nota">${escaparHtml(t('buscando'))}</li>`;
    else if (sinResultados) html += `<li class="busca-nota">${escaparHtml(t('sin_resultados'))}</li>`;
    lista.innerHTML = html;
    lista.hidden = !html;
    input.setAttribute('aria-expanded', String(!lista.hidden));
    input.setAttribute('aria-activedescendant', activo >= 0 ? `busca-op-${activo}` : '');
  }
  function marcarActivo(i) {
    if (!resultados.length) return;
    activo = (i + resultados.length) % resultados.length;
    lista.querySelectorAll('.busca-op').forEach(li => li.classList.toggle('activo', Number(li.dataset.i) === activo));
    input.setAttribute('aria-activedescendant', `busca-op-${activo}`);
    lista.querySelector('.activo')?.scrollIntoView({ block: 'nearest' });
  }
  function cerrar() { lista.hidden = true; input.setAttribute('aria-expanded', 'false'); }
  function elegir(i) {
    const r = resultados[i];
    if (!r) return;
    input.value = r.nombre;
    elegido = r;
    cerrar();
    input.blur();
    alElegir(r);
  }

  // Al escribir: primero lo local (al instante) y luego Photon.
  async function alEscribir() {
    const texto = input.value;
    await prepararIndice();
    if (!normalizar(texto)) { pintar(listaComunidades()); return; }
    const locales = buscarLocal(texto);
    const irARemoto = CONFIG.buscar_con_photon && normalizar(texto).length >= 3;
    pintar(locales, { cargando: irARemoto, sinResultados: !irARemoto && !locales.length });
    if (!irARemoto) return;
    clearTimeout(temporizador);
    temporizador = setTimeout(async () => {
      try {
        const remotos = await buscarPhoton(texto);
        if (input.value !== texto) return; // el usuario ya ha escrito otra cosa
        const todos = [...locales, ...remotos];
        pintar(todos, { sinResultados: !todos.length });
      } catch (err) {
        if (err.name === 'AbortError') return;
        console.warn('Búsqueda de lugares no disponible:', err);
        pintar(locales, { sinResultados: !locales.length });
      }
    }, ESPERA_MS);
  }

  // Con la caja vacía: lista de comunidades para elegir directamente.
  const listaComunidades = () => indice.filter(l => l.tipo === 'comunidad' && delPais(l))
    .sort((a, b) => nombreLocal(a).localeCompare(nombreLocal(b), idioma())).map(aResultadoLocal);

  input.addEventListener('input', alEscribir);
  input.addEventListener('focus', () => { input.select(); alEscribir(); });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); if (lista.hidden) alEscribir(); else marcarActivo(activo + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); marcarActivo(activo - 1); }
    else if (e.key === 'Enter') { e.preventDefault(); elegir(activo); }
    else if (e.key === 'Escape') { cerrar(); input.blur(); }
  });
  // pointerdown (no click) para que funcione antes de que el input pierda el foco.
  lista.addEventListener('pointerdown', e => {
    const li = e.target.closest('.busca-op');
    if (li) { e.preventDefault(); elegir(Number(li.dataset.i)); }
  });
  document.addEventListener('pointerdown', e => {
    if (!lista.hidden && !lista.contains(e.target) && e.target !== input) cerrar();
  });

  return {
    limpiar() { input.value = ''; elegido = null; cerrar(); },
    // Al cambiar de idioma: traduce el nombre elegido (comunidades y provincias) y la lista abierta.
    refrescar() {
      if (elegido?.local && input.value === elegido.nombre) input.value = elegido.nombre = nombreLocal(elegido.local);
      if (!lista.hidden) alEscribir();
    },
  };
}
