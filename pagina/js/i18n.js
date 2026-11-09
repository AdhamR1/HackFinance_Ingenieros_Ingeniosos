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

export async function ponerIdioma(nuevo) {
  const res = await fetch(`i18n/${nuevo}.json`);
  textos = await res.json();
  idiomaActual = nuevo;
  try { localStorage.setItem(CLAVE_GUARDADA, nuevo); } catch { /* sin almacenamiento */ }
  document.documentElement.lang = nuevo;
  document.title = t('titulo_pagina');
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll('[data-i18n-aria]').forEach(el => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  avisos.forEach(fn => fn(nuevo));
}

export function iniciarIdioma() { return ponerIdioma(idiomaInicial()); }
