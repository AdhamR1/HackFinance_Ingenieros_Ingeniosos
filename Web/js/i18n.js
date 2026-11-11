// Idiomas: carga los textos de i18n/<idioma>.json y los pone en la página.
// En el HTML, un elemento con data-i18n="clave" recibe el texto de esa clave.
import { CONFIG } from '../config.js';

const CLAVE_GUARDADA = 'cibh_idioma';
let textos = {};
let idiomaActual = null;
const avisos = []; // funciones a las que avisar cuando cambia el idioma

// Idioma inicial: el que eligió el usuario la última vez; si no, el del navegador.
function idiomaInicial() {
  try {
    const guardado = localStorage.getItem(CLAVE_GUARDADA);
    if (CONFIG.idiomas.includes(guardado)) return guardado;
  } catch { /* navegación privada: no pasa nada */ }
  for (const l of navigator.languages || [navigator.language || '']) {
    const corto = l.slice(0, 2).toLowerCase();
    if (CONFIG.idiomas.includes(corto)) return corto;
  }
  return CONFIG.idioma_por_defecto;
}

// Devuelve el texto de una clave. t('error_carga', { pais: 'España' })
export function t(clave, variables = {}) {
  let texto = textos[clave] ?? clave;
  for (const [k, v] of Object.entries(variables)) texto = texto.replaceAll(`{${k}}`, v);
  return texto;
}

export const idioma = () => idiomaActual;

export function alCambiarIdioma(fn) { avisos.push(fn); }

// Cada idioma se descarga una sola vez; después el cambio es instantáneo.
const descargados = {};
const descargar = l => descargados[l] ??= fetch(`i18n/${l}.json`).then(res => res.json())
  .catch(err => { delete descargados[l]; throw err; });
let ultimoPedido = null; // si se pulsa ES y EN muy seguido, manda el último pulsado

export async function ponerIdioma(nuevo) {
  if (nuevo === idiomaActual && nuevo === ultimoPedido) return; // ya está puesto
  ultimoPedido = nuevo;
  const datos = await descargar(nuevo);
  if (nuevo !== ultimoPedido) return; // mientras llegaba, el visitante eligió otro idioma
  textos = datos;
  idiomaActual = nuevo;
  try { localStorage.setItem(CLAVE_GUARDADA, nuevo); } catch { /* sin almacenamiento */ }
  document.documentElement.lang = nuevo;
  document.title = t('titulo_pagina');
  document.querySelector('meta[name="description"]')?.setAttribute('content', t('descripcion_pagina'));
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.querySelectorAll('[data-i18n-aria]').forEach(el => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  avisos.forEach(fn => fn(nuevo));
}

export async function iniciarIdioma() {
  await ponerIdioma(idiomaInicial());
  // Los otros idiomas se descargan ya (pesan muy poco): así el primer cambio es instantáneo,
  // aunque el navegador esté ocupado preparando la cuadrícula.
  CONFIG.idiomas.forEach(l => descargar(l).catch(() => {}));
}
