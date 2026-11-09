// Prepara data/ES_regiones.json: comunidades autónomas y provincias de España
// (bordes para dibujar en el mapa + nombres para el buscador).
// Fuente: Natural Earth 1:10m admin-1 (dominio público).
// Uso (desde la carpeta pagina):
//   1) Descargar https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson
//   2) cd herramientas && node preparar_regiones.mjs <ruta al archivo descargado> ../data/ES_regiones.json
import fs from 'node:fs';
import polygonClipping from 'polygon-clipping';

const [,, origen, destino] = process.argv;
const g = JSON.parse(fs.readFileSync(origen, 'utf8'));
const provincias = g.features.filter(f => f.properties.iso_a2 === 'ES');

// Nombres oficiales de las comunidades (Natural Earth trae algunos abreviados o en inglés).
const COMUNIDADES = {
  'Andalucía': ['Andalucía', 'Andalusia'],
  'Aragón': ['Aragón', 'Aragon'],
  'Asturias': ['Principado de Asturias', 'Asturias'],
  'Islas Baleares': ['Illes Balears', 'Balearic Islands', ['Islas Baleares', 'Baleares']],
  'Canary Is.': ['Canarias', 'Canary Islands', ['Islas Canarias']],
  'Cantabria': ['Cantabria', 'Cantabria'],
  'Castilla y León': ['Castilla y León', 'Castile and León'],
  'Castilla-La Mancha': ['Castilla-La Mancha', 'Castilla-La Mancha'],
  'Cataluña': ['Cataluña', 'Catalonia', ['Catalunya']],
  'Valenciana': ['Comunitat Valenciana', 'Valencian Community', ['Comunidad Valenciana']],
  'Extremadura': ['Extremadura', 'Extremadura'],
  'Galicia': ['Galicia', 'Galicia'],
  'Madrid': ['Comunidad de Madrid', 'Community of Madrid'],
  'Murcia': ['Región de Murcia', 'Region of Murcia'],
  'Foral de Navarra': ['Comunidad Foral de Navarra', 'Navarre', ['Navarra']],
  'País Vasco': ['País Vasco', 'Basque Country', ['Euskadi']],
  'La Rioja': ['La Rioja', 'La Rioja'],
  'Ceuta': ['Ceuta', 'Ceuta'],
  'Melilla': ['Melilla', 'Melilla'],
};
// Nombre oficial de provincias + otras formas de escribirlas (para el buscador).
const PROVINCIAS = {
  'La Coruña': ['A Coruña', ['La Coruña', 'Coruña']], 'Orense': ['Ourense', ['Orense']],
  'Lérida': ['Lleida', ['Lérida']], 'Gerona': ['Girona', ['Gerona']],
  'Álava': ['Araba/Álava', ['Álava', 'Araba']], 'Gipuzkoa': ['Gipuzkoa', ['Guipúzcoa']],
  'Bizkaia': ['Bizkaia', ['Vizcaya']], 'Baleares': ['Illes Balears', ['Baleares', 'Islas Baleares']],
  'Castellón': ['Castellón', ['Castelló']], 'Alicante': ['Alicante', ['Alacant']],
  'Valencia': ['Valencia', ['València']], 'Navarra': ['Navarra', ['Nafarroa']],
};

// --- Simplificación Douglas-Peucker (tolerancia en grados; 0.002 ≈ 200 m) ---
const TOL = 0.002;
function dp(pts) {
  if (pts.length < 3) return pts;
  const marca = new Uint8Array(pts.length); marca[0] = marca[pts.length - 1] = 1;
  const pila = [[0, pts.length - 1]];
  while (pila.length) {
    const [i, j] = pila.pop(); const [ax, ay] = pts[i], [bx, by] = pts[j];
    const dx = bx - ax, dy = by - ay, L = Math.hypot(dx, dy) || 1e-12;
    let max = 0, k = -1;
    for (let m = i + 1; m < j; m++) {
      const d = Math.abs(dy * pts[m][0] - dx * pts[m][1] + bx * ay - by * ax) / L;
      if (d > max) { max = d; k = m; }
    }
    if (max > TOL) { marca[k] = 1; pila.push([i, k], [k, j]); }
  }
  return pts.filter((_, n) => marca[n]);
}
const simplificarAnillo = an => {
  const n = an.length - 1, mitad = Math.floor(n / 2);
  const s = n < 8 ? an : [...dp(an.slice(0, mitad + 1)), ...dp(an.slice(mitad)).slice(1)];
  return s.map(([x, y]) => [Math.round(x * 1e4) / 1e4, Math.round(y * 1e4) / 1e4]);
};
const aMulti = geom => geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
const simplificar = multi => multi.map(poli => poli.map(simplificarAnillo).filter(an => an.length >= 4)).filter(p => p.length);
const caja = multi => { const c = multi.flat(2); const xs = c.map(p => p[0]), ys = c.map(p => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)].map(v => Math.round(v * 1000) / 1000); };

const features = [];
// Provincias
for (const f of provincias) {
  const [nombre, alias = []] = PROVINCIAS[f.properties.name] ?? [f.properties.name, []];
  const multi = simplificar(aMulti(f.geometry));
  const ccaa = COMUNIDADES[f.properties.region];
  if (!ccaa) throw new Error(`Comunidad desconocida: ${f.properties.region}`);
  features.push({ type: 'Feature',
    properties: { tipo: 'provincia', nombre_es: nombre, nombre_en: nombre, alias, comunidad: ccaa[0], caja: caja(multi) },
    geometry: { type: 'MultiPolygon', coordinates: multi } });
}
// Comunidades = unión de sus provincias
const porComunidad = {};
for (const f of provincias) (porComunidad[f.properties.region] ??= []).push(aMulti(f.geometry));
for (const [region, geoms] of Object.entries(porComunidad)) {
  const [nombre_es, nombre_en, alias = []] = COMUNIDADES[region];
  const multi = simplificar(polygonClipping.union(...geoms));
  features.push({ type: 'Feature',
    properties: { tipo: 'comunidad', nombre_es, nombre_en, alias, caja: caja(multi) },
    geometry: { type: 'MultiPolygon', coordinates: multi } });
}

fs.writeFileSync(destino, JSON.stringify({ type: 'FeatureCollection',
  meta: { pais: 'ES', fuente: 'Natural Earth 1:10m admin-1 (dominio público), simplificado' }, features }));
console.log(`✔ ${features.filter(f => f.properties.tipo === 'comunidad').length} comunidades, ` +
  `${features.filter(f => f.properties.tipo === 'provincia').length} provincias · ${(fs.statSync(destino).size / 1e3).toFixed(0)} KB`);
