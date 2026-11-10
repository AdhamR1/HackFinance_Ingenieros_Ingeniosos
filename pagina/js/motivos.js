// Motivos principales de un cuadrado: "Por qué se acepta" y "Por qué se rechaza".
//
// 1) Si el archivo de datos los trae ("motivos_a_favor" / "motivos_en_contra"), se usan esos.
//    Cada motivo puede ser un texto o { "es": "...", "en": "..." } (para que salga traducido).
// 2) Si no los trae, la web los saca de los datos del cuadrado:
//    - a favor: las variables con mejor valor (desde la nota "amarilla" hacia arriba);
//    - en contra: primero el motivo de descarte del archivo y los permisos que le afectan,
//      después las variables con peor valor (por debajo de la nota "verde").
// Qué se enseña depende del color: verde → a favor · rojo → en contra · amarillo → los dos.
import { CONFIG } from '../config.js';
import { t, idioma } from './i18n.js';
import { tieneValor, permisosDe } from './puntuacion.js';

// Texto de un motivo escrito en el archivo, en el idioma de la web.
function textoDelArchivo(m) {
  if (typeof m === 'string') return m;
  if (m && typeof m === 'object') return m[idioma()] ?? m.es ?? m.en ?? Object.values(m).find(x => typeof x === 'string') ?? null;
  return null;
}
const listaDelArchivo = lista => Array.isArray(lista) ? lista.map(textoDelArchivo).filter(Boolean) : null;

const textoVariable = (clave, v) => `${t(`var_${clave}`)} · ${Math.round(v)}/100`;

// r = resultado de evaluar(p). Devuelve { aFavor, enContra } (listas de textos, ya recortadas)
// con solo lo que toca enseñar según el color (lista vacía = no se enseña ese bloque).
export function motivosDe(p, r) {
  const max = CONFIG.motivos_maximos ?? 3;
  const ensenaFavor = r.categoria === 'verde' || r.categoria === 'amarillo';
  const ensenaContra = r.categoria === 'rojo' || r.categoria === 'amarillo';

  // Variables con dato, de mejor a peor.
  const vars = CONFIG.variables.map(({ clave }) => ({ clave, v: p[clave] }))
    .filter(x => tieneValor(x.v)).sort((a, b) => b.v - a.v);

  let aFavor = listaDelArchivo(p.motivos_a_favor);
  if (!aFavor) aFavor = vars.filter(x => x.v >= CONFIG.umbrales.amarillo).map(x => textoVariable(x.clave, x.v));

  let enContra = listaDelArchivo(p.motivos_en_contra);
  if (!enContra) {
    enContra = [];
    const permisos = permisosDe(p);
    // Primero el motivo de descarte (si lo hay), luego los permisos, luego las peores variables.
    if (r.descartado) enContra.push(textoMotivoSuelto(r.motivo));
    for (const clave of CONFIG.permisos)   // (si el descarte ya es por ese permiso, no se repite)
      if (permisos.includes(clave) && r.motivo !== clave) enContra.push(t('motivo_permiso_requiere', { permiso: t(`permiso_${clave}`) }));
    for (const x of [...vars].reverse())
      if (x.v < CONFIG.umbrales.verde) enContra.push(textoVariable(x.clave, x.v));
  }

  return {
    aFavor: ensenaFavor ? aFavor.slice(0, max) : [],
    enContra: ensenaContra ? enContra.slice(0, max) : [],
  };
}

// Motivo de descarte que viene del archivo: una clave conocida ("natura_2000"), cualquier texto
// ("zona militar") o { "es": "...", "en": "..." }.
export function textoMotivoSuelto(motivo) {
  if (motivo && typeof motivo === 'object') return textoDelArchivo(motivo) ?? t('motivo_otro');
  const clave = `motivo_${motivo}`;
  const traducido = t(clave);
  return traducido === clave ? String(motivo) : traducido;
}
