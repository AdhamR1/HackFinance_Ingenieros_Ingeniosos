// =====================================================================
//  Prepara los LÍMITES de España a partir de UNA sola fuente precisa:
//    - data/ES_regiones.json                → bordes de provincias y comunidades + nombres (para la web)
//    - herramientas/fuentes/espana_contorno.geojson → contorno para recortar la cuadrícula
//  Así los bordes de los cuadrados, de las comunidades y de las provincias coinciden.
//
//  Fuente: geoBoundaries ESP ADM2 (provincias, del INE; licencia CC BY 4.0 / INE).
//    Las comunidades = unión de sus provincias; España = unión de todas.
//  Se simplifica con mapshaper (respeta los bordes compartidos: no deja huecos).
//
//  Uso (desde la carpeta herramientas):
//    1) Descargar https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/ESP/ADM2/geoBoundaries-ESP-ADM2.geojson
//    2) node preparar_regiones.mjs <archivo descargado>
//    3) node generar_datos_prueba.mjs   (para volver a recortar la cuadrícula)
// =====================================================================
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import mapshaper from 'mapshaper';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const [,, origen] = process.argv;
const PRECISION_M = 25; // los puntos se separan como mínimo ~25 m (los bordes siguen ríos y costa)

// Comunidades: código → [nombre oficial, nombre en inglés, otros nombres para el buscador]
const CCAA = {
  AN: ['Andalucía', 'Andalusia'], AR: ['Aragón', 'Aragon'], AS: ['Principado de Asturias', 'Asturias', ['Asturias']],
  IB: ['Illes Balears', 'Balearic Islands', ['Islas Baleares', 'Baleares']], CN: ['Canarias', 'Canary Islands', ['Islas Canarias']],
  CB: ['Cantabria', 'Cantabria'], CL: ['Castilla y León', 'Castile and León'], CM: ['Castilla-La Mancha', 'Castilla-La Mancha'],
  CT: ['Cataluña', 'Catalonia', ['Catalunya']], VC: ['Comunitat Valenciana', 'Valencian Community', ['Comunidad Valenciana']],
  EX: ['Extremadura', 'Extremadura'], GA: ['Galicia', 'Galicia'], MD: ['Comunidad de Madrid', 'Community of Madrid', ['Madrid']],
  MC: ['Región de Murcia', 'Region of Murcia', ['Murcia']], NC: ['Comunidad Foral de Navarra', 'Navarre', ['Navarra']],
  PV: ['País Vasco', 'Basque Country', ['Euskadi']], RI: ['La Rioja', 'La Rioja'],
  CE: ['Ceuta', 'Ceuta', ['Ciudad Autónoma de Ceuta']], ML: ['Melilla', 'Melilla', ['Ciudad Autónoma de Melilla']],
};
// Provincias: nombre en el archivo → [nombre oficial, comunidad, otros nombres]
const PROV = {
  'Alava': ['Araba/Álava', 'PV', ['Álava', 'Araba']], 'Albacete': ['Albacete', 'CM'], 'Alicante': ['Alicante/Alacant', 'VC', ['Alicante', 'Alacant']],
  'Almeria': ['Almería', 'AN'], 'Avila': ['Ávila', 'CL'], 'Badajoz': ['Badajoz', 'EX'], 'Balears, Illes': ['Illes Balears', 'IB', ['Baleares', 'Islas Baleares']],
  'Barcelona': ['Barcelona', 'CT'], 'Burgos': ['Burgos', 'CL'], 'Caceres': ['Cáceres', 'EX'], 'Cadiz': ['Cádiz', 'AN'],
  'Castellon': ['Castellón/Castelló', 'VC', ['Castellón', 'Castelló']], 'Ciudad Real': ['Ciudad Real', 'CM'], 'Cordoba': ['Córdoba', 'AN'],
  'Coruna': ['A Coruña', 'GA', ['La Coruña', 'Coruña']], 'Cuenca': ['Cuenca', 'CM'], 'Girona': ['Girona', 'CT', ['Gerona']],
  'Granada': ['Granada', 'AN'], 'Guadalajara': ['Guadalajara', 'CM'], 'Gipuzkoa': ['Gipuzkoa', 'PV', ['Guipúzcoa']], 'Huelva': ['Huelva', 'AN'],
  'Huesca': ['Huesca', 'AR'], 'Jaen': ['Jaén', 'AN'], 'Leon': ['León', 'CL'], 'Lleida': ['Lleida', 'CT', ['Lérida']],
  'Rioja, La': ['La Rioja', 'RI'], 'Lugo': ['Lugo', 'GA'], 'Madrid': ['Madrid', 'MD'], 'Malaga': ['Málaga', 'AN'], 'Murcia': ['Murcia', 'MC'],
  'Navarra': ['Navarra', 'NC', ['Nafarroa']], 'Ourense': ['Ourense', 'GA', ['Orense']], 'Asturias': ['Asturias', 'AS'], 'Palencia': ['Palencia', 'CL'],
  'Palmas, Las': ['Las Palmas', 'CN'], 'Pontevedra': ['Pontevedra', 'GA'], 'Salamanca': ['Salamanca', 'CL'],
  'Santa Cruz de Tenerife': ['Santa Cruz de Tenerife', 'CN', ['Tenerife']], 'Cantabria': ['Cantabria', 'CB'], 'Segovia': ['Segovia', 'CL'],
  'Sevilla': ['Sevilla', 'AN'], 'Soria': ['Soria', 'CL'], 'Tarragona': ['Tarragona', 'CT'], 'Teruel': ['Teruel', 'AR'], 'Toledo': ['Toledo', 'CM'],
  'Valencia': ['Valencia/València', 'VC', ['Valencia', 'València']], 'Valladolid': ['Valladolid', 'CL'], 'Bizkaia': ['Bizkaia', 'PV', ['Vizcaya']],
  'Zamora': ['Zamora', 'CL'], 'Zaragoza': ['Zaragoza', 'AR'], 'Ceuta': ['Ceuta', 'CE'], 'Melilla': ['Melilla', 'ML'],
};

// 1) Leer provincias y ponerles nombre y comunidad
const fuente = JSON.parse(fs.readFileSync(origen, 'utf8'));
const provincias = {
  type: 'FeatureCollection',
  features: fuente.features.map(f => {
    const info = PROV[f.properties.shapeName];
    if (!info) throw new Error(`Provincia desconocida: ${f.properties.shapeName}`);
    return { type: 'Feature', geometry: f.geometry, properties: { nombre: info[0], ccaa: info[1] } };
  }),
};

// 2) mapshaper: simplificar (sin abrir huecos), y unir provincias → comunidades → España
const salida = await mapshaper.applyCommands(
  `-i provincias.json -proj wgs84 -simplify interval=${PRECISION_M} keep-shapes -clean ` +
  `-o format=geojson precision=0.00001 provincias_s.json ` +
  `-dissolve ccaa + name=comunidades -o format=geojson precision=0.00001 comunidades_s.json ` +
  `-dissolve target=provincias + name=pais -o format=geojson precision=0.00001 pais_s.json ` +
  // Para dibujar: cada borde interior UNA sola vez (sin repetir el de cada lado)
  `-innerlines target=provincias + name=lp -o format=geojson precision=0.00001 lineas_prov.json ` +
  `-innerlines target=comunidades + name=lc -o format=geojson precision=0.00001 lineas_ccaa.json`,
  { 'provincias.json': provincias });
const leer = nombre => JSON.parse(salida[nombre].toString());
const [provS, ccaaS, paisRaw] = ['provincias_s.json', 'comunidades_s.json', 'pais_s.json'].map(leer);
// Al unir sin campo, mapshaper devuelve una GeometryCollection: se pasa a FeatureCollection.
const paisS = paisRaw.features ? paisRaw
  : { features: paisRaw.geometries.map(geometry => ({ type: 'Feature', properties: {}, geometry })) };

const caja = geom => { const c = JSON.stringify(geom.coordinates).match(/-?\d+\.?\d*/g).map(Number);
  const xs = c.filter((_, i) => i % 2 === 0), ys = c.filter((_, i) => i % 2 === 1);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)].map(v => Math.round(v * 1000) / 1000); };

// 3) Archivo para la web:
//    - líneas de borde entre provincias y entre comunidades (para dibujar)
//    - comunidades y provincias SIN forma, solo nombre y rectángulo (para el buscador)
const lineas = (archivo, tipo) => { const j = leer(archivo); const fs_ = j.features ?? j.geometries.map(geometry => ({ geometry }));
  return fs_.map(f => ({ type: 'Feature', properties: { tipo }, geometry: f.geometry })); };
const features = [
  ...lineas('lineas_prov.json', 'linea_provincia'),
  ...lineas('lineas_ccaa.json', 'linea_comunidad'),
  ...ccaaS.features.map(f => { const [es, en, alias = []] = CCAA[f.properties.ccaa];
    return { type: 'Feature', properties: { tipo: 'comunidad', nombre_es: es, nombre_en: en, alias, caja: caja(f.geometry) }, geometry: null }; }),
  ...provS.features.map(f => { const info = Object.values(PROV).find(p => p[0] === f.properties.nombre);
    return { type: 'Feature', properties: { tipo: 'provincia', nombre_es: info[0], nombre_en: info[0], alias: info[2] || [],
      comunidad: CCAA[info[1]][0], caja: caja(f.geometry) }, geometry: null }; }),
];
const destinoWeb = path.join(AQUI, '../data/ES_regiones.json');
fs.writeFileSync(destinoWeb, JSON.stringify({ type: 'FeatureCollection',
  meta: { pais: 'ES', fuente: 'geoBoundaries ESP ADM2 (INE), simplificado a ~25 m con mapshaper', licencia: 'CC BY 4.0' }, features }));

// 4) Contorno de España para recortar la cuadrícula (mismo dibujo exacto)
const destinoContorno = path.join(AQUI, 'fuentes/espana_contorno.geojson');
fs.writeFileSync(destinoContorno, JSON.stringify({ type: 'Feature',
  properties: { iso: 'ES', fuente: 'geoBoundaries ESP ADM2 (INE), unión de provincias, ~25 m' }, geometry: paisS.features[0].geometry }));

const puntos = g => JSON.stringify(g).split('],[').length;
console.log(`✔ ${ccaaS.features.length} comunidades, ${provS.features.length} provincias`);
console.log(`  data/ES_regiones.json: ${(fs.statSync(destinoWeb).size / 1e6).toFixed(2)} MB`);
console.log(`  fuentes/espana_contorno.geojson: ${(fs.statSync(destinoContorno).size / 1e6).toFixed(2)} MB, ${puntos(paisS.features[0].geometry)} puntos`);
