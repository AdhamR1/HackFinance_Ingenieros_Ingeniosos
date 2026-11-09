// Servidor de prueba que comprime con brotli (como hace Cloudflare). Solo para medir velocidad.
// Uso: node servidor_comprimido.mjs <carpeta> <puerto>
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const [,, raiz, puerto = '8001'] = process.argv;
const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.geojson': 'application/json', '.png': 'image/png' };
const cache = new Map();

http.createServer((req, res) => {
  const ruta = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  let archivo = path.join(raiz, ruta === '/' ? 'index.html' : ruta);
  if (!archivo.startsWith(path.resolve(raiz)) || !fs.existsSync(archivo) || fs.statSync(archivo).isDirectory()) { res.writeHead(404); res.end(); return; }
  const ext = path.extname(archivo);
  const tipo = TIPOS[ext] || 'application/octet-stream';
  const quiereBr = /\bbr\b/.test(req.headers['accept-encoding'] || '') && tipo !== 'image/png';
  if (!quiereBr) { res.writeHead(200, { 'Content-Type': tipo }); fs.createReadStream(archivo).pipe(res); return; }
  const clave = archivo + '@' + fs.statSync(archivo).mtimeMs; // si el archivo cambia, se vuelve a comprimir
  if (!cache.has(clave)) cache.set(clave, zlib.brotliCompressSync(fs.readFileSync(archivo), { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 5 } }));
  const cuerpo = cache.get(clave);
  res.writeHead(200, { 'Content-Type': tipo, 'Content-Encoding': 'br', 'Content-Length': cuerpo.length });
  res.end(cuerpo);
}).listen(Number(puerto), '127.0.0.1', () => console.log(`Servidor comprimido en http://127.0.0.1:${puerto}`));
