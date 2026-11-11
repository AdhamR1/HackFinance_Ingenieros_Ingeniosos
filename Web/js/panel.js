// Panel lateral (datos de un cuadrado), leyenda y texto del tooltip.
// Todo el texto sale de i18n/*.json; los colores y umbrales, de config.js.
import { CONFIG } from '../config.js';
import { t, idioma } from './i18n.js';
import { evaluar, tieneValor, permisosDe } from './puntuacion.js';
import { motivosDe, textoMotivoSuelto } from './motivos.js';
import { icono as dibujarIcono } from './iconos.js';

const $ = id => document.getElementById(id);
const escaparHtml = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const numero = (n, decimales = 0) => n.toLocaleString(idioma() === 'en' ? 'en-GB' : 'es-ES',
  { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
// Con los decimales que tenga, hasta 2 (12 → "12", 12,25 → "12,25").
const numeroLibre = n => n.toLocaleString(idioma() === 'en' ? 'en-GB' : 'es-ES', { maximumFractionDigits: 2 });

// Nombre de la categoría: "Viable", "Con condiciones"...
export const textoCategoria = categoria => t(`categoria_${categoria}`);

// Motivo de descarte (r = resultado de evaluar). Los conocidos se traducen; si no, se muestra
// tal cual venga en los datos.
export const textoMotivo = r => textoMotivoSuelto(r.motivo);

// Iconos pequeños de las listas de motivos (✓ a favor, ✗ en contra).
const MARCA = {
  favor: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  contra: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>',
};
const listaMotivos = (tipo, titulo, motivos) => motivos.length ? `
    <section class="motivos motivos-${tipo}">
      <h3 class="panel-subtitulo">${escaparHtml(titulo)}</h3>
      <ul>${motivos.map(m => `<li>${MARCA[tipo]}<span>${escaparHtml(m)}</span></li>`).join('')}</ul>
    </section>` : '';

// Permisos que afectan al cuadrado (solo esos).
function bloquePermisos(p) {
  const afectan = permisosDe(p);
  let cuerpo;
  if (p.permisos === undefined || p.permisos === null) cuerpo = `<p class="panel-mini">${escaparHtml(t('sin_datos'))}</p>`;
  else if (!afectan.length) cuerpo = `<p class="panel-mini">${escaparHtml(t('permisos_ninguno'))}</p>`;
  else {
    const orden = [...CONFIG.permisos.filter(k => afectan.includes(k)), ...afectan.filter(k => !CONFIG.permisos.includes(k))];
    cuerpo = `<ul class="permisos">${orden.map(clave => {
      const nombre = t(`permiso_${clave}`) === `permiso_${clave}` ? clave : t(`permiso_${clave}`);
      return `<li class="permiso">${escaparHtml(nombre)}</li>`;
    }).join('')}</ul>`;
  }
  return `
    <section class="permisos-bloque">
      <h3 class="panel-subtitulo">${escaparHtml(t('permisos_titulo'))}</h3>
      ${cuerpo}
    </section>`;
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
  if (r.descartado) linea = `${t('descartado')} · ${textoMotivo(r)}`;
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
  const area = meta?.area_cuadrado_km2 ?? CONFIG.area_cuadrado_km2;
  const lado = meta?.lado_cuadrado_km ?? Math.sqrt(area);
  const c = feature.geometry ? centro(feature.geometry) : null;

  const nota = r.nota === null ? '—' : r.nota;
  const motivos = motivosDe(p, r);
  const origen = r.origen === 'archivo' ? `<p class="panel-mini">${escaparHtml(t('puntuacion_del_archivo'))}</p>` : '';
  // Si está descartado, la nota se enseña (es información útil) pero se aclara que no cuenta.
  const notaDescartada = r.descartado && r.nota !== null
    ? `<p class="panel-mini">${escaparHtml(t('nota_no_cuenta'))}</p>` : '';

  const aviso = r.descartado ? `
    <div class="panel-aviso" role="alert">
      <span aria-hidden="true">⛔</span>
      <div><strong>${escaparHtml(t('descartado'))}</strong><br>${escaparHtml(textoMotivo(r))}</div>
    </div>` : '';

  // Los pesos NO se muestran (no son fijos y no queremos que se copie el modelo).
  const filas = CONFIG.variables.map(({ clave, color, ayuda: conAyuda }) => {
    const v = p[clave];
    const hay = tieneValor(v);
    const ayuda = conAyuda ? ` <span class="panel-mini">(${escaparHtml(t('ayuda_riesgo'))})</span>` : '';
    return `
      <li class="variable${hay ? '' : ' sin-dato'}">
        <div class="variable-cabecera">
          <span class="variable-icono">${dibujarIcono(clave, color)}</span>
          <span class="variable-nombre">${escaparHtml(t(`var_${clave}`))}${ayuda}</span>
          <span class="variable-valor mono">${hay ? numero(v) : escaparHtml(t('sin_datos'))}</span>
        </div>
        <div class="barra" role="meter" aria-valuemin="0" aria-valuemax="100" ${hay ? `aria-valuenow="${v}"` : ''} aria-label="${escaparHtml(t(`var_${clave}`))}">
          ${hay ? `<span style="width:${Math.max(0, Math.min(100, v))}%;background:${colorValor(v)}"></span>` : ''}
        </div>
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
    ${listaMotivos('favor', t('motivos_a_favor'), motivos.aFavor)}
    ${listaMotivos('contra', t('motivos_en_contra'), motivos.enContra)}
    ${bloquePermisos(p)}

    <h3 class="panel-subtitulo">${escaparHtml(t('desglose'))}</h3>
    <ul class="variables">${filas}</ul>

    <dl class="panel-datos">
      ${c ? `<div><dt>${escaparHtml(t('coordenadas'))}</dt><dd class="mono">${coordenadas(c)}</dd></div>` : ''}
      ${tierra}
    </dl>
    <p class="panel-nota-area">${escaparHtml(t('nota_area', { area: numeroLibre(area), lado: numero(lado, 2) }))}</p>
  `;
  return c;
}

// ---------- Data centers que ya existen ----------
const nombreDc = p => p.nombre || t('dc_sin_nombre');

// Texto corto del tooltip de un data center.
export function textoTooltipDc(p) {
  const estado = t(`dc_estado_${p.estado}`);
  const edificios = p.edificios > 1 ? ` · ${t('dc_edificios_n', { n: p.edificios })}` : '';
  return `<strong>${escaparHtml(nombreDc(p))}</strong><div class="tooltip-nota">${escaparHtml(estado + edificios)}</div>`;
}

// Ficha de un data center (en el mismo panel que los cuadrados).
export function pintarPanelDatacenter(feature) {
  const p = feature.properties;
  const [lon, lat] = feature.geometry.coordinates;
  const operadores = p.operadores?.length ? `
    <h3 class="panel-subtitulo">${escaparHtml(t('dc_operadores'))}</h3>
    <ul class="dc-operadores">${p.operadores.map(o => `<li>${escaparHtml(o)}</li>`).join('')}</ul>` : '';
  const exacta = p.precision === 'exacta';
  const fuente = { datacentermap: 'datacentermap.com', peeringdb: 'PeeringDB', osm: 'OpenStreetMap' }[p.fuente] ?? p.fuente;
  // El municipio debajo del nombre, salvo que sea lo mismo ("Paterna" / "Paterna").
  const sinAcentos = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const municipio = p.municipio && sinAcentos(p.municipio) !== sinAcentos(nombreDc(p)) ? p.municipio : '';

  $('panel-contenido').innerHTML = `
    <header class="panel-cabecera">
      <p class="panel-etiqueta">${escaparHtml(t('dc_etiqueta'))}</p>
      <h2 id="panel-id">${escaparHtml(nombreDc(p))}</h2>
      <p id="panel-lugar" class="panel-lugar"${municipio ? '' : ' hidden'}>${escaparHtml(municipio)}</p>
    </header>
    <ul class="permisos dc-chips">
      <li class="dc-chip dc-chip-${p.estado}">${escaparHtml(t(`dc_estado_${p.estado}`))}</li>
      <li class="dc-chip">${escaparHtml(t('dc_edificios_n', { n: p.edificios }))}</li>
    </ul>
    ${operadores}
    <dl class="panel-datos">
      <div><dt>${escaparHtml(t('dc_coordenadas'))}</dt><dd class="mono">${coordenadas([lon, lat])}</dd></div>
      <div><dt>${escaparHtml(t('dc_ubicacion'))}</dt><dd>${escaparHtml(t(`dc_precision_${p.precision}`))}</dd></div>
      <div><dt>${escaparHtml(t('dc_fuente'))}</dt><dd>${escaparHtml(fuente)}</dd></div>
    </dl>
    ${exacta ? '' : `<p class="panel-nota-area">${escaparHtml(t('dc_nota_aproximada'))}</p>`}
  `;
  return { lonLat: [lon, lat], conLugar: !p.municipio };
}

// Leyenda de los puntos (debajo de la de colores).
export function pintarLeyendaDc() {
  $('leyenda-dc').innerHTML = ['operativo', 'planeado'].map(estado => `
    <li><span class="muestra-dc muestra-dc-${estado}"></span><span>${escaparHtml(t(`dc_estado_${estado}`))}</span></li>`).join('');
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
