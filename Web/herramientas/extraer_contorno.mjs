// Extrae el contorno de un país del archivo de Natural Earth 1:10m (dominio público).
// Uso (desde la carpeta pagina):
//   1) Descargar https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson
//   2) node herramientas/extraer_contorno.mjs ne_10m_admin_0_countries.geojson ES herramientas/fuentes/espana_contorno.geojson
import fs from 'node:fs';
const [,, origen, iso, destino] = process.argv;
const g = JSON.parse(fs.readFileSync(origen, 'utf8'));
const f = g.features.find(x => (x.properties.ISO_A2_EH || x.properties.ISO_A2) === iso);
if (!f) throw new Error(`No encuentro el país ${iso}`);
const r = c => Array.isArray(c[0]) ? c.map(r) : [Math.round(c[0] * 1e5) / 1e5, Math.round(c[1] * 1e5) / 1e5];
fs.writeFileSync(destino, JSON.stringify({ type: 'Feature', properties: { iso, fuente: 'Natural Earth 1:10m' },
  geometry: { type: f.geometry.type, coordinates: r(f.geometry.coordinates) } }));
console.log(iso, f.properties.NAME_ES, f.geometry.type, f.geometry.coordinates.length, 'partes');
