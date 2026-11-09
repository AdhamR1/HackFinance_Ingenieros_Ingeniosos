// Cálculo de la puntuación, descartes y color de cada cuadrado.
// Todas las reglas (pesos, umbrales, descartes) están en config.js.
import { CONFIG } from '../config.js';

// ¿Es un número válido? (null, undefined, "", NaN → no)
export const tieneValor = v => typeof v === 'number' && Number.isFinite(v);

// Devuelve:
//   nota       → 0-100, o null si no hay ningún dato
//   origen     → 'archivo' (venía en el archivo) o 'calculada'
//   descartado → true/false
//   motivo     → p. ej. 'suelo_protegido', 'inundacion', 'sismico' (o null)
//   categoria  → 'verde' | 'amarillo' | 'rojo' | 'sin_datos'
//   color      → color de esa categoría
export function evaluar(p) {
  // 1) Descartes: primero lo que diga el archivo, luego las reglas de config.js.
  let descartado = p.descartado === true;
  let motivo = descartado ? (p.motivo_descarte || 'otro') : null;
  if (!descartado) {
    for (const regla of CONFIG.reglas_descarte) {
      const v = p[regla.variable];
      if (tieneValor(v) && v < regla.menor_que) { descartado = true; motivo = regla.motivo; break; }
    }
  }

  // 2) Nota: la del archivo (si se permite y viene) o la media ponderada.
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
