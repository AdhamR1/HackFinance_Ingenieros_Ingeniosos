// Prepara data/mundo.geojson a partir de Natural Earth (escala 1:50m, dominio público).
// Uso (desde la carpeta pagina):
//   1) Descargar https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson
//   2) node herramientas/preparar_mundo.mjs ne_50m_admin_0_countries.geojson data/mundo.geojson
// Deja solo código ISO y nombre en español/inglés, redondea coordenadas y quita la Antártida.
// En la tabla SEPARAR se indican territorios que se separan de su país (salen como "No disponible").
import fs from 'node:fs';
const [,, src, dst] = process.argv;
const g = JSON.parse(fs.readFileSync(src, 'utf8'));
// Redondeo a 2 decimales (~1 km): suficiente para la vista del mundo y el archivo pesa poco.
// Se quitan los puntos repetidos que salen al redondear.
const PREC = 100;
const punto = c => [Math.round(c[0] * PREC) / PREC, Math.round(c[1] * PREC) / PREC];
// Simplificación Douglas-Peucker: quita puntos que se desvían menos de TOL grados (~3 km).
const TOL = 0.03;
// Los anillos están cerrados (primer punto = último), así que se parten en dos mitades.
function simplificar(anilloCerrado) {
  const n = anilloCerrado.length - 1;
  if (n < 8) return anilloCerrado;
  const mitad = Math.floor(n / 2);
  const a = dp(anilloCerrado.slice(0, mitad + 1)), b = dp(anilloCerrado.slice(mitad));
  return [...a, ...b.slice(1)];
}
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
const anillo = an => { const out = []; for (const c of simplificar(an).map(punto)) { const u = out[out.length - 1];
  if (!u || u[0] !== c[0] || u[1] !== c[1]) out.push(c); } return out; };
// Islas diminutas (caja menor de ~0,05 grados², unos 500 km²) se quitan: no se ven en el mapa del mundo.
const grande = poli => { const xs = poli[0].map(c => c[0]), ys = poli[0].map(c => c[1]);
  return (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys)) >= 0.05; };
const r = coords => typeof coords[0][0][0] === 'number'
  ? coords.map(anillo).filter(an => an.length >= 4)                       // Polygon
  : (() => { const g = coords.filter(grande); return (g.length ? g : coords); })()
      .map(poli => poli.map(anillo).filter(an => an.length >= 4)).filter(poli => poli.length); // MultiPolygon

// Países de los que solo nos quedamos con el territorio principal ("principal" =
// caja [oeste, sur, este, norte]). Los trozos cuyo centro cae fuera pasan a ser
// zonas aparte, siempre "No disponible". Con nombre si encajan en una regla;
// si no, "Territorios de ultramar".
const SEPARAR = {
  FR: { principal: [-5.5, 42.2, 8.4, 51.2], reglas: [
        { si: ([x, y]) => x < -50 && x > -55 && y > 1 && y < 6.5, iso: 'X-GF', es: 'Guayana Francesa', en: 'French Guiana' },
        { si: ([x, y]) => x > 8.4 && x < 10 && y > 41 && y < 43.2, iso: 'X-COR', es: 'Córcega', en: 'Corsica' } ] },
  IT: { principal: [6.5, 36, 18.6, 47.1], reglas: [
        { si: ([x, y]) => y < 38.4 && x > 12, iso: 'X-SIC', es: 'Sicilia', en: 'Sicily' },
        { si: ([x, y]) => x < 10 && y < 41.4, iso: 'X-SAR', es: 'Cerdeña', en: 'Sardinia' } ] },
  US: { principal: [-125, 24, -66, 50], reglas: [
        { si: ([x, y]) => y < 23 && x < -150, iso: 'X-HI', es: 'Hawái', en: 'Hawaii' },
        { si: ([x, y]) => y > 50 || x > 170, iso: 'X-AK', es: 'Alaska', en: 'Alaska' } ] },
};
const centro = anillo => { const xs = anillo.map(c => c[0]), ys = anillo.map(c => c[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]; };
const dentro = ([x, y], [o, s, e, n]) => x >= o && x <= e && y >= s && y <= n;

const features = [];
for (const f of g.features) {
  const p = f.properties;
  const iso = p.ISO_A2_EH && p.ISO_A2_EH !== '-99' ? p.ISO_A2_EH : p.ISO_A2;
  if (iso === 'AQ') continue;
  let geom = { type: f.geometry.type, coordinates: r(f.geometry.coordinates) };
  const sep = SEPARAR[iso];
  if (sep && geom.type === 'MultiPolygon') {
    const quedan = [], aparte = {};
    const otros = { iso: `X-${iso}-OTROS`, es: 'Territorios de ultramar', en: 'Overseas territories' };
    for (const poli of geom.coordinates) {
      const c = centro(poli[0]);
      const regla = sep.reglas.find(x => x.si(c)) ?? (dentro(c, sep.principal) ? null : otros);
      if (regla) (aparte[regla.iso] ??= { regla, polis: [] }).polis.push(poli); else quedan.push(poli);
    }
    geom = quedan.length === 1 ? { type: 'Polygon', coordinates: quedan[0] } : { type: 'MultiPolygon', coordinates: quedan };
    for (const { regla, polis } of Object.values(aparte))
      features.push({ type: 'Feature', properties: { iso: regla.iso, nombre_es: regla.es, nombre_en: regla.en },
        geometry: { type: 'MultiPolygon', coordinates: polis } });
  }
  features.push({ type: 'Feature', properties: { iso, nombre_es: p.NAME_ES, nombre_en: p.NAME_EN }, geometry: geom });
}
fs.writeFileSync(dst, JSON.stringify({ type: 'FeatureCollection', features }));
for (const f of features.filter(x => ['FR', 'IT', 'US'].includes(x.properties.iso) || x.properties.iso.startsWith('X-'))) {
  const iso = f.properties.iso;
  console.log(iso, f.properties.nombre_es, f.geometry.type, f.geometry.type === 'Polygon' ? 1 : f.geometry.coordinates.length, 'trozo(s)');
}
