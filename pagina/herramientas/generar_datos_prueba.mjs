// =====================================================================
//  GENERADOR DE DATOS DE PRUEBA (INVENTADOS) PARA ESPAÑA
// =====================================================================
//  Crea data/ES.json: una cuadrícula de cuadrados (superficie en config.js →
//  area_cuadrado_km2; 12 km² = 3,46 × 3,46 km) recortada por la costa y la frontera,
//  con valores INVENTADOS que cambian de forma suave por zonas.
//
//  Uso (desde la carpeta pagina):
//      cd herramientas
//      npm install            ← solo la primera vez
//      node generar_datos_prueba.mjs
//
//  Opciones:  --solo-geometria   crea los cuadrados con todas las variables a null
//                                (plantilla para rellenar con datos reales)
//             --salida <ruta>    archivo de salida (por defecto ../data/ES.json)
//             --area <km²>       superficie de cuadrado distinta a la de config.js (para pruebas)
//
//  Cómo se hacen cuadrados de verdad de esa medida:
//  se pasa el contorno de España a una proyección en METROS (UTM, la que usa
//  el Instituto Geográfico Nacional), se dibuja la cuadrícula ahí, se recorta
//  y se vuelve a pasar a longitud/latitud para la web.
//    - Península, Baleares, Ceuta y Melilla → UTM huso 30 (EPSG:25830)
//    - Canarias                            → UTM huso 28 (EPSG:32628)
// =====================================================================
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import polygonClipping from 'polygon-clipping';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const { CONFIG } = await import(new URL('../config.js', import.meta.url));

const args = process.argv.slice(2);
const SOLO_GEOMETRIA = args.includes('--solo-geometria');
const SALIDA = args.includes('--salida') ? args[args.indexOf('--salida') + 1] : path.join(AQUI, '../data/ES.json');
const AREA_KM2 = args.includes('--area') ? Number(args[args.indexOf('--area') + 1]) : CONFIG.area_cuadrado_km2;
const LADO = Math.round(Math.sqrt(AREA_KM2) * 1000); // lado en metros (redondeado al metro)
const LADO_KM = LADO / 1000;
const AREA_REAL_KM2 = LADO_KM * LADO_KM;
const AREA_MINIMA_KM2 = AREA_REAL_KM2 * 0.02;        // trozos de costa < 2 % del cuadrado se descartan (astillas)

// ---------------------------------------------------------------------
// 1. PROYECCIÓN UTM (fórmulas de Snyder, USGS 1987). Elipsoide GRS80.
// ---------------------------------------------------------------------
const a = 6378137, f = 1 / 298.257222101, k0 = 0.9996;
const e2 = f * (2 - f), ep2 = e2 / (1 - e2);
const rad = d => d * Math.PI / 180, grados = r => r * 180 / Math.PI;
const meridiano = huso => rad(huso * 6 - 183);

function aUTM([lon, lat], huso) {
  const φ = rad(lat), λ = rad(lon), λ0 = meridiano(huso);
  const N = a / Math.sqrt(1 - e2 * Math.sin(φ) ** 2);
  const T = Math.tan(φ) ** 2, C = ep2 * Math.cos(φ) ** 2, A = Math.cos(φ) * (λ - λ0);
  const M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * φ
    - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * Math.sin(2 * φ)
    + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * Math.sin(4 * φ)
    - (35 * e2 ** 3 / 3072) * Math.sin(6 * φ));
  const x = k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T * T + 72 * C - 58 * ep2) * A ** 5 / 120) + 500000;
  const y = k0 * (M + N * Math.tan(φ) * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A ** 4 / 24
    + (61 - 58 * T + T * T + 600 * C - 330 * ep2) * A ** 6 / 720));
  return [x, y];
}

function deUTM([x, y], huso) {
  const M = y / k0;
  const mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256));
  const e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));
  const φ1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu)
    + (151 * e1 ** 3 / 96) * Math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * Math.sin(8 * mu);
  const C1 = ep2 * Math.cos(φ1) ** 2, T1 = Math.tan(φ1) ** 2;
  const N1 = a / Math.sqrt(1 - e2 * Math.sin(φ1) ** 2);
  const R1 = a * (1 - e2) / (1 - e2 * Math.sin(φ1) ** 2) ** 1.5;
  const D = (x - 500000) / (N1 * k0);
  const φ = φ1 - (N1 * Math.tan(φ1) / R1) * (D * D / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * ep2) * D ** 4 / 24
    + (61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * ep2 - 3 * C1 * C1) * D ** 6 / 720);
  const λ = meridiano(huso) + (D - (1 + 2 * T1 + C1) * D ** 3 / 6
    + (5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * ep2 + 24 * T1 * T1) * D ** 5 / 120) / Math.cos(φ1);
  return [grados(λ), grados(φ)];
}

// ---------------------------------------------------------------------
// 2. CONTORNO DE ESPAÑA, separado por husos
// ---------------------------------------------------------------------
const contorno = JSON.parse(fs.readFileSync(path.join(AQUI, 'fuentes/espana_contorno.geojson'), 'utf8'));
const partes = contorno.geometry.type === 'Polygon' ? [contorno.geometry.coordinates] : contorno.geometry.coordinates;
const REGIONES = [
  { nombre: 'Península, Baleares, Ceuta y Melilla', huso: 30, partes: [] },
  { nombre: 'Canarias', huso: 28, partes: [] },
];
for (const poli of partes) {
  const lon = poli[0][0][0];
  (lon < -12 ? REGIONES[1] : REGIONES[0]).partes.push(poli);
}

// Área (m²) de un multipolígono en coordenadas proyectadas.
const areaAnillo = an => { let s = 0; for (let i = 0, j = an.length - 1; i < an.length; j = i++) s += (an[j][0] + an[i][0]) * (an[j][1] - an[i][1]); return Math.abs(s / 2); };
const areaMulti = mp => mp.reduce((t, poli) => t + areaAnillo(poli[0]) - poli.slice(1).reduce((h, an) => h + areaAnillo(an), 0), 0);
const rectangulo = (x0, y0, x1, y1) => [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]];

// ---------------------------------------------------------------------
// 3. CUADRÍCULA Y RECORTE
// ---------------------------------------------------------------------
const celdas = [];
for (const region of REGIONES) {
  const tierra = region.partes.map(poli => poli.map(an => an.map(c => aUTM(c, region.huso))));
  const todos = tierra.flat(2);
  const xmin = Math.floor(Math.min(...todos.map(c => c[0])) / LADO) * LADO;
  const ymin = Math.floor(Math.min(...todos.map(c => c[1])) / LADO) * LADO;
  const xmax = Math.ceil(Math.max(...todos.map(c => c[0])) / LADO) * LADO;
  const ymax = Math.ceil(Math.max(...todos.map(c => c[1])) / LADO) * LADO;

  // De norte a sur: primero se recorta una franja (fila) y luego cada cuadrado de esa franja.
  for (let y = ymax - LADO; y >= ymin; y -= LADO) {
    const franja = polygonClipping.intersection(tierra, rectangulo(xmin, y, xmax, y + LADO));
    if (!franja.length) continue;
    for (let x = xmin; x < xmax; x += LADO) {
      const trozo = polygonClipping.intersection(franja, rectangulo(x, y, x + LADO, y + LADO))
        .filter(poli => areaAnillo(poli[0]) >= 1e4); // quita islotes de menos de 0,01 km²
      if (!trozo.length) continue;
      const area = areaMulti(trozo) / 1e6;
      if (area < AREA_MINIMA_KM2) continue;
      const entero = area > AREA_REAL_KM2 * 0.999;
      const geoTrozo = entero
        ? [rectangulo(x, y, x + LADO, y + LADO)[0]].map(an => [an])  // cuadrado completo: 5 puntos exactos
        : trozo;
      // 4 decimales ≈ 10 m: de sobra para cuadrados de varios km y el archivo pesa mucho menos.
      const aGrados = mp => mp.map(poli => poli.map(an => an.map(c => deUTM(c, region.huso).map(v => Math.round(v * 1e4) / 1e4))));
      const coords = aGrados(geoTrozo);
      celdas.push({
        huso: region.huso, x, y, area: Math.round(area * 100) / 100,
        centro: deUTM([x + LADO / 2, y + LADO / 2], region.huso).map(v => Math.round(v * 1e4) / 1e4),
        geometry: coords.length === 1 ? { type: 'Polygon', coordinates: coords[0] } : { type: 'MultiPolygon', coordinates: coords },
      });
    }
  }
}

// ---------------------------------------------------------------------
// 4. VALORES INVENTADOS ("ruido suave" + tendencias geográficas)
// ---------------------------------------------------------------------
// Ruido de valores: números pseudoaleatorios en una rejilla, interpolados
// suavemente. Varias escalas sumadas = manchas grandes con algo de detalle.
// Semilla fija → el resultado es siempre el mismo.
function hash(ix, iy, semilla) {
  let h = (ix * 374761393 + iy * 668265263 + semilla * 1442695041) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
const suave = t => t * t * (3 - 2 * t);
function ruido(x, y, semilla) {
  const ix = Math.floor(x), iy = Math.floor(y), fx = suave(x - ix), fy = suave(y - iy);
  const v = (i, j) => hash(ix + i, iy + j, semilla);
  return (v(0, 0) * (1 - fx) + v(1, 0) * fx) * (1 - fy) + (v(0, 1) * (1 - fx) + v(1, 1) * fx) * fy;
}
// Ruido "fractal" entre 0 y 1. escalaKm = tamaño típico de las manchas.
function manchas(lon, lat, semilla, escalaKm = 250) {
  const x = lon * 85 / escalaKm, y = lat * 111 / escalaKm;
  let total = 0, peso = 0, amp = 1, frec = 1;
  for (let o = 0; o < 4; o++) { total += amp * ruido(x * frec, y * frec, semilla + o * 101); peso += amp; amp *= 0.5; frec *= 2; }
  return total / peso;
}
const distanciaKm = ([lon1, lat1], [lon2, lat2]) =>
  Math.hypot((lon1 - lon2) * 111 * Math.cos(rad((lat1 + lat2) / 2)), (lat1 - lat2) * 111);
const limitar = v => Math.max(0, Math.min(100, Math.round(v)));
const cercania = (p, lugares, alcanceKm) => Math.max(...lugares.map(l => Math.exp(-distanciaKm(p, l) / alcanceKm)));

const CIUDADES = [[-3.70, 40.42], [2.17, 41.39], [-0.38, 39.47], [-5.98, 37.39], [-4.42, 36.72], [-0.89, 41.65],
  [-2.93, 43.26], [-8.41, 43.36], [-4.72, 41.65], [-1.13, 37.99], [2.65, 39.57], [-15.43, 28.12], [-16.25, 28.46]];
const ZONAS_SISMICAS = [[-3.6, 37.2], [-1.1, 38.0], [-2.4, 36.85]]; // Granada, Murcia, Almería
const CANARIAS_VOLCAN = [[-17.85, 28.6], [-18.0, 27.75]];          // La Palma, El Hierro

function valoresInventados(c) {
  const [lon, lat] = c.centro;
  const canarias = c.huso === 28;
  const r = (semilla, escala) => manchas(lon, lat, semilla, escala);

  // Energía: renovables (sol en el sur/centro, viento en Aragón/Castilla) + red eléctrica.
  const energia = 35 + 40 * r(11) + 15 * (1 - Math.abs(lat - 39.5) / 4) + (canarias ? 10 : 0);
  // Agua: más en el norte (lluvia) y cerca de grandes ríos (simulado con ruido).
  const agua = 20 + 55 * Math.min(1, Math.max(0, (lat - 37) / 6.5)) + 30 * r(23, 180) + (canarias ? 15 : 0); // Canarias: desaladoras
  // Clima: fresco = mejor para refrigerar. Mejor al norte y en el interior alto.
  const clima = 25 + 9 * (lat - 37) + 25 * r(37, 150) + (canarias ? 15 : 0);
  // Conectividad: cerca de grandes ciudades (fibra, puntos de intercambio).
  const conectividad = 15 + 70 * cercania(c.centro, CIUDADES, 110) + 20 * r(41, 120);
  // Carreteras: parecido a conectividad, pero más repartido.
  const carreteras = 35 + 45 * cercania(c.centro, CIUDADES, 180) + 25 * r(53, 90);
  // Sísmico (100 = poco riesgo): peor en el sureste y en zonas volcánicas.
  const sismico = 98 - 95 * cercania(c.centro, ZONAS_SISMICAS, 70) - 50 * cercania(c.centro, CANARIAS_VOLCAN, 25)
    - 15 * Math.max(0, lat - 42.3) * r(61) - 10 * r(67, 60);
  // Inundación (100 = poco riesgo): manchas pequeñas y más riesgo en la costa mediterránea.
  const inundacion = 92 - 70 * Math.max(0, r(71, 60) - 0.55) * 4 - (c.area < AREA_REAL_KM2 * 0.999 && lon > -1.5 && !canarias ? 25 : 0);

  const v = { energia, agua, clima, conectividad, carreteras, sismico, inundacion };
  for (const k in v) v[k] = limitar(v[k]);

  // Huecos de datos: algunas variables faltan en algunas zonas (como pasará con los reales).
  if (r(83, 120) > 0.72) v.conectividad = null;
  if (r(89, 90) > 0.78) v.agua = null;
  if (hash(Math.round(lon * 100), Math.round(lat * 100), 97) > 0.985) v.clima = null;
  if (r(101, 40) > 0.83) for (const k in v) v[k] = null;   // unos pocos cuadrados sin ningún dato

  // Suelo protegido (parques naturales, Red Natura...): manchas.
  const protegido = r(113, 70) > 0.74;
  return { v, protegido };
}

// ---------------------------------------------------------------------
// 5. ESCRIBIR EL ARCHIVO
// ---------------------------------------------------------------------
celdas.sort((p, q) => (p.huso === q.huso ? 0 : p.huso === 30 ? -1 : 1) || q.y - p.y || p.x - q.x);
const features = celdas.map((c, i) => {
  const { v, protegido } = SOLO_GEOMETRIA
    ? { v: { energia: null, agua: null, clima: null, conectividad: null, carreteras: null, sismico: null, inundacion: null }, protegido: false }
    : valoresInventados(c);
  return {
    type: 'Feature',
    geometry: c.geometry,
    properties: {
      id: `ES-${String(i + 1).padStart(5, '0')}`,
      puntuacion: null,
      descartado: protegido,
      motivo_descarte: protegido ? 'suelo_protegido' : null,
      ...v,
      area_km2: c.area,
      utm_huso: c.huso,
      utm_x: c.x,
      utm_y: c.y,
    },
  };
});

const salida = {
  type: 'FeatureCollection',
  meta: {
    pais: 'ES',
    area_cuadrado_km2: AREA_KM2,
    lado_cuadrado_km: LADO_KM,
    datos_de_prueba: !SOLO_GEOMETRIA,
    fuente: SOLO_GEOMETRIA ? 'Plantilla vacía generada por herramientas/generar_datos_prueba.mjs'
      : 'DATOS INVENTADOS generados por herramientas/generar_datos_prueba.mjs',
    fecha: new Date().toISOString().slice(0, 10),
    proyeccion_cuadricula: 'UTM huso 30 (EPSG:25830) y huso 28 en Canarias (EPSG:32628)',
  },
  // Una línea por cuadrado: más fácil de leer y de comparar con git.
  features: [],
};
const texto = JSON.stringify({ ...salida }, null, 1).replace('"features": []',
  '"features": [\n' + features.map(ft => '  ' + JSON.stringify(ft)).join(',\n') + '\n ]');
fs.writeFileSync(SALIDA, texto + '\n');

// Resumen
const n = features.length, enteros = celdas.filter(c => c.area >= AREA_REAL_KM2 * 0.999).length;
const contar = fn => features.filter(ft => fn(ft.properties)).length;
console.log(`✔ ${path.relative(process.cwd(), SALIDA)}: ${n} cuadrados de ${AREA_KM2} km² (${LADO_KM} × ${LADO_KM} km)`);
console.log(`  enteros: ${enteros} · recortados por costa/frontera: ${n - enteros}`);
console.log(`  por huso: 30 → ${celdas.filter(c => c.huso === 30).length}, 28 (Canarias) → ${celdas.filter(c => c.huso === 28).length}`);
console.log(`  área total: ${Math.round(celdas.reduce((t, c) => t + c.area, 0)).toLocaleString('es')} km²`);
if (!SOLO_GEOMETRIA) {
  console.log(`  suelo protegido: ${contar(p => p.descartado)} · sin ningún dato: ${contar(p => p.energia === null && p.agua === null && p.sismico === null)}`);
  for (const k of ['energia', 'agua', 'clima', 'conectividad', 'carreteras', 'sismico', 'inundacion'])
    console.log(`  ${k.padEnd(13)} nulls: ${String(contar(p => p[k] === null)).padStart(4)}  ` +
      `bajo 20: ${String(contar(p => p[k] !== null && p[k] < 20)).padStart(4)}`);
}
console.log(`  tamaño: ${(fs.statSync(SALIDA).size / 1e6).toFixed(2)} MB`);
