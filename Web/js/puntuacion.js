// Cálculo de la puntuación, descartes y color de cada cuadrado.
// Los umbrales de color están en config.js. Los descartes vienen en el archivo de datos.
import { CONFIG } from '../config.js';

// ¿Es un número válido? (null, undefined, "", NaN → no)
export const tieneValor = v => typeof v === 'number' && Number.isFinite(v);

// Permisos que afectan al cuadrado, como lista de claves (['natura_2000', ...]).
// Acepta una lista (["natura_2000"]) o un objeto ({ "natura_2000": true, ... }).
export function permisosDe(p) {
  const v = p.permisos;
  if (Array.isArray(v)) return v.filter(x => typeof x === 'string');
  if (v && typeof v === 'object') return Object.keys(v).filter(k => v[k] === true);
  return [];
}

// Devuelve:
//   nota        → 0-100, o null si no hay ningún dato
//   origen      → 'archivo' (venía en el archivo) o 'calculada'
//   descartado  → true/false
//   motivo      → el "motivo_descarte" del archivo (o null)
//   categoria   → 'verde' | 'amarillo' | 'rojo' | 'sin_datos'
//   color       → color de esa categoría
export function evaluar(p) {
  // 1) Descarte: solo el que diga el archivo (la web no descarta nada por su cuenta).
  const descartado = p.descartado === true;
  const motivo = descartado ? (p.motivo_descarte || 'otro') : null;

  // 2) Nota: la del archivo (si se permite y viene) o una media provisional (solo datos de prueba).
  let nota = null, origen = 'calculada';
  if (CONFIG.usar_puntuacion_del_archivo && tieneValor(p.puntuacion)) {
    nota = p.puntuacion;
    origen = 'archivo';
  } else {
    let suma = 0, pesoTotal = 0;
    for (const [variable, peso] of Object.entries(CONFIG.pesos)) {
      if (peso > 0 && tieneValor(p[variable])) { suma += p[variable] * peso; pesoTotal += peso; }
    }
    if (pesoTotal > 0) nota = suma / pesoTotal; // el peso de las variables sin dato se reparte
  }
  if (nota !== null) nota = Math.round(Math.max(0, Math.min(100, nota)));

  // 3) Categoría y color.
  let categoria;
  if (descartado) categoria = 'rojo';
  else if (nota === null) categoria = 'sin_datos';
  else if (nota >= CONFIG.umbrales.verde) categoria = 'verde';
  else if (nota >= CONFIG.umbrales.amarillo) categoria = 'amarillo';
  else categoria = 'rojo';

  return { nota, origen, descartado, motivo, categoria, color: CONFIG.colores[categoria] };
}
