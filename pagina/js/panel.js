// Panel lateral (datos de un cuadrado), leyenda y texto del tooltip.
// Todo el texto sale de i18n/*.json; los colores y umbrales, de config.js.
import { CONFIG } from '../config.js';
import { t, idioma } from './i18n.js';
import { evaluar, tieneValor } from './puntuacion.js';

const $ = id => document.getElementById(id);
const escaparHtml = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const numero = (n, decimales = 0) => n.toLocaleString(idioma() === 'en' ? 'en-GB' : 'es-ES',
  { minimumFractionDigits: decimales, maximumFractionDigits: decimales });

// Nombre de la categoría: "Viable", "Con condiciones"...
export const textoCategoria = categoria => t(`categoria_${categoria}`);

// Motivo de descarte: los conocidos se traducen; si no, se muestra tal cual venga en los datos.
export function textoMotivo(motivo) {
  const clave = `motivo_${motivo}`;
  const traducido = t(clave);
  return traducido === clave ? String(motivo) : traducido;
}

// Color de una barra según su valor (mismos umbrales que la puntuación).
function colorValor(v) {
  if (v >= CONFIG.umbrales.verde) return CONFIG.colores.verde;
  if (v >= CONFIG.umbrales.amarillo) return CONFIG.colores.amarillo;
  return CONFIG.colores.rojo;
}

// Texto corto del tooltip al pasar el ratón.
export function textoTooltip(p) {
  const r = evaluar(p);
  let linea;
  if (r.descartado) linea = `${t('descartado')} · ${textoMotivo(r.motivo)}`;
  else if (r.nota === null) linea = t('sin_datos');
  else linea = `${r.nota}/100 · ${textoCategoria(r.categoria)}`;
  return `<span class="mono">${escaparHtml(p.id)}</span><div class="tooltip-nota" style="color:${r.color}">${escaparHtml(linea)}</div>`;
}

// Centro aproximado de la forma (para mostrar coordenadas).
function centro(geometria) {
  const pts = geometria.type === 'Polygon' ? geometria.coordinates[0] : geometria.coordinates.flatMap(p => p[0]);
  const xs = pts.map(c => c[0]), ys = pts.map(c => c[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
}
const coordenadas = ([lon, lat]) =>
  `${numero(Math.abs(lat), 4)}° ${lat >= 0 ? 'N' : 'S'}, ${numero(Math.abs(lon), 4)}° ${lon >= 0 ? 'E' : t('oeste_abrev')}`;

// Pinta el panel de un cuadrado. "meta" es la cabecera del archivo de datos.
export function pintarPanel(feature, meta) {
  const p = feature.properties;
  const r = evaluar(p);
  const pesoTotal = Object.values(CONFIG.pesos).reduce((a, b) => a + b, 0) || 1;
  const area = meta?.area_cuadrado_km2 ?? CONFIG.area_cuadrado_km2;
  const lado = meta?.lado_cuadrado_km ?? Math.sqrt(area);
  const c = feature.geometry ? centro(feature.geometry) : null;

  const nota = r.nota === null ? '—' : r.nota;
  const origen = r.origen === 'archivo' ? `<p class="panel-mini">${escaparHtml(t('puntuacion_del_archivo'))}</p>` : '';
  // Si está descartado, la nota se enseña (es información útil) pero se aclara que no cuenta.
  const notaDescartada = r.descartado && r.nota !== null
    ? `<p class="panel-mini">${escaparHtml(t('nota_no_cuenta'))}</p>` : '';

  const aviso = r.descartado ? `
    <div class="panel-aviso" role="alert">
      <span aria-hidden="true">⛔</span>
      <div><strong>${escaparHtml(t('descartado'))}</strong><br>${escaparHtml(textoMotivo(r.motivo))}</div>
    </div>` : '';

  const filas = CONFIG.variables.map(({ clave, icono }) => {
    const v = p[clave];
    const hay = tieneValor(v);
    const peso = CONFIG.pesos[clave] ?? 0;
    const pesoTxt = peso > 0 ? t('peso', { n: Math.round(peso / pesoTotal * 100) }) : t('solo_descarta');
    const ayuda = (clave === 'sismico' || clave === 'inundacion') ? ` <span class="panel-mini">(${escaparHtml(t('ayuda_riesgo'))})</span>` : '';
    return `
      <li class="variable${hay ? '' : ' sin-dato'}">
        <div class="variable-cabecera">
          <span class="variable-icono" aria-hidden="true">${icono}</span>
          <span class="variable-nombre">${escaparHtml(t(`var_${clave}`))}${ayuda}</span>
          <span class="variable-valor mono">${hay ? numero(v) : escaparHtml(t('sin_datos'))}</span>
        </div>
        <div class="barra" role="meter" aria-valuemin="0" aria-valuemax="100" ${hay ? `aria-valuenow="${v}"` : ''} aria-label="${escaparHtml(t(`var_${clave}`))}">
          ${hay ? `<span style="width:${Math.max(0, Math.min(100, v))}%;background:${colorValor(v)}"></span>` : ''}
        </div>
        <div class="variable-peso">${escaparHtml(pesoTxt)}</div>
      </li>`;
  }).join('');

  const tierra = tieneValor(p.area_km2) && p.area_km2 < area * 0.995
    ? `<div><dt>${escaparHtml(t('superficie_tierra'))}</dt><dd class="mono">${numero(p.area_km2, 1)} km²</dd></div>` : '';

  $('panel-contenido').innerHTML = `
    <header class="panel-cabecera">
      <p class="panel-etiqueta">${escaparHtml(t('cuadrado'))}</p>
      <h2 id="panel-id" class="mono">${escaparHtml(p.id)}</h2>
      <p id="panel-lugar" class="panel-lugar" hidden></p>
    </header>

    <div class="panel-nota${r.descartado ? ' descartada' : ''}" style="--color:${r.color}">
      <div class="nota-circulo"><span class="nota-numero">${nota}</span><span class="nota-max">/100</span></div>
      <div>
        <p class="nota-categoria" style="color:${r.color}">${escaparHtml(textoCategoria(r.categoria))}</p>
        <p class="panel-mini">${escaparHtml(t('puntuacion_total'))}</p>
        ${notaDescartada}
        ${origen}
      </div>
    </div>
    ${aviso}

    <h3 class="panel-subtitulo">${escaparHtml(t('desglose'))}</h3>
    <ul class="variables">${filas}</ul>

    <dl class="panel-datos">
      ${c ? `<div><dt>${escaparHtml(t('coordenadas'))}</dt><dd class="mono">${coordenadas(c)}</dd></div>` : ''}
      ${tierra}
    </dl>
    <p class="panel-nota-area">${escaparHtml(t('nota_area', { area: numero(area), lado: numero(lado, 2) }))}</p>
  `;
  return c;
}

// Añade "Cerca de: Calatayud · Zaragoza" cuando llega la respuesta (puede tardar o fallar).
export function ponerLugar(texto) {
  const el = document.getElementById('panel-lugar');
  if (!el) return;
  el.textContent = texto ? t('cerca_de', { lugar: texto }) : '';
  el.hidden = !texto;
}

// Leyenda con los umbrales de config.js.
export function pintarLeyenda() {
  const u = CONFIG.umbrales;
  const filas = [
    ['verde', `≥ ${u.verde}`],
    ['amarillo', `${u.amarillo}–${u.verde - 1}`],
    ['rojo', t('leyenda_rojo', { n: u.amarillo })],
    ['sin_datos', ''],
  ];
  $('leyenda').innerHTML = filas.map(([cat, rango]) => `
    <li><span class="muestra" style="background:${CONFIG.colores[cat]}"></span>
      <span>${escaparHtml(textoCategoria(cat))}</span><span class="leyenda-rango mono">${escaparHtml(rango)}</span></li>`).join('');
}
