// Prepara data/mundo.geojson a partir de Natural Earth (escala 1:110m, dominio público).
// Uso (desde la carpeta pagina):
//   1) Descargar https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson
//   2) node herramientas/preparar_mundo.mjs ne_110m_admin_0_countries.geojson data/mundo.geojson
// Deja solo código ISO y nombre en español/inglés, redondea coordenadas y quita la Antártida.
// En la tabla SEPARAR se indican territorios que se separan de su país (salen como "No disponible").
import fs from 'node:fs';
const [,, src, dst] = process.argv;
const g = JSON.parse(fs.readFileSync(src, 'utf8'));
const r = c => Array.isArray(c[0]) ? c.map(r) : [Math.round(c[0]*1000)/1000, Math.round(c[1]*1000)/1000];

// Países de los que solo nos quedamos con el territorio principal. El resto de
// trozos pasan a ser zonas aparte, siempre "No disponible".
// Cada trozo se identifica por la longitud/latitud de su centro.
const SEPARAR = {
  FR: [ { si: ([x]) => x < -40, iso: 'X-GF', es: 'Guayana Francesa', en: 'French Guiana' },
        { si: ([x, y]) => x > 8.3 && y < 43.1, iso: 'X-COR', es: 'Córcega', en: 'Corsica' } ],
  IT: [ { si: ([x, y]) => y < 38.3 && x > 12, iso: 'X-SIC', es: 'Sicilia', en: 'Sicily' },
        { si: ([x]) => x < 10, iso: 'X-SAR', es: 'Cerdeña', en: 'Sardinia' } ],
  US: [ { si: ([x, y]) => y < 23 && x < -150, iso: 'X-HI', es: 'Hawái', en: 'Hawaii' },
        { si: ([x, y]) => y > 50 && x < -129, iso: 'X-AK', es: 'Alaska', en: 'Alaska' } ],
};
const centro = anillo => { const xs = anillo.map(c => c[0]), ys = anillo.map(c => c[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]; };

const features = [];
for (const f of g.features) {
  const p = f.properties;
  const iso = p.ISO_A2_EH && p.ISO_A2_EH !== '-99' ? p.ISO_A2_EH : p.ISO_A2;
  if (iso === 'AQ') continue;
  let geom = { type: f.geometry.type, coordinates: r(f.geometry.coordinates) };
  const reglas = SEPARAR[iso];
  if (reglas && geom.type === 'MultiPolygon') {
    const quedan = [], aparte = {};
    for (const poli of geom.coordinates) {
      const regla = reglas.find(x => x.si(centro(poli[0])));
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
for (const iso of ['FR', 'IT', 'US', 'X-GF', 'X-COR', 'X-SIC', 'X-SAR', 'X-HI', 'X-AK']) {
  const f = features.find(x => x.properties.iso === iso);
  console.log(iso, f.properties.nombre_es, f.geometry.type, f.geometry.type === 'Polygon' ? 1 : f.geometry.coordinates.length, 'trozo(s)');
}
