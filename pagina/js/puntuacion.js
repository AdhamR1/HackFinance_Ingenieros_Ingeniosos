// Cálculo de la puntuación, descartes y color de cada cuadrado.
// Todas las reglas (umbrales, permisos que descartan, límite de las variables) están en config.js.
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
//   motivo      → p. ej. 'parque_nacional', 'variable_baja', o lo que traiga el archivo (o null)
//   motivoDatos → para 'variable_baja': { variable, valor }
//   categoria   → 'verde' | 'amarillo' | 'rojo' | 'sin_datos'
//   color       → color de esa categoría
export function evaluar(p) {
  // 1) Descartes, por orden: lo que diga el archivo, un permiso que descarta, una variable muy baja.
  let descartado = p.descartado === true;
  let motivo = descartado ? (p.motivo_descarte || 'otro') : null;
  let motivoDatos = null;
  if (!descartado) {
    const permisos = permisosDe(p);
    const permiso = CONFIG.permisos.find(x => x.descarta && permisos.includes(x.clave));
    if (permiso) { descartado = true; motivo = permiso.clave; }
  }
  const limite = CONFIG.descarte_si_variable_menor_que;
  if (!descartado && tieneValor(limite)) {
    let peor = null;
    for (const { clave } of CONFIG.variables) {
      const v = p[clave];
      if (tieneValor(v) && v < limite && (peor === null || v < peor.valor)) peor = { variable: clave, valor: v };
    }
    if (peor) { descartado = true; motivo = 'variable_baja'; motivoDatos = peor; }
  }

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

  return { nota, origen, descartado, motivo, motivoDatos, categoria, color: CONFIG.colores[categoria] };
}
