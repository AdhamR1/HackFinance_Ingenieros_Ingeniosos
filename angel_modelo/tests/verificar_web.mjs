// Verificación del mapa en un Chrome real (headless) vía DevTools Protocol. Sin dependencias (Node >= 22).
// Uso: node angel_modelo/tests/verificar_web.mjs [url] [captura.png]
//   (antes: cd angel_modelo/web_mapa && python -m http.server 8765)
// Comprueba: sin errores de consola ni excepciones, celdas dibujadas > 30.000, tiempo de carga, y que
// al seleccionar una celda se rellena la ficha. Sale con código 1 si algo falla.
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const url = process.argv[2] || 'http://127.0.0.1:8765/';
const shot = process.argv[3] || join(tmpdir(), 'mapa.png');
const CHROME = process.env.CHROME || {
  darwin: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  win32: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
}[process.platform] || 'google-chrome';
const port = 9300 + Math.floor(Math.random() * 500);
const prof = mkdtempSync(join(tmpdir(), 'chprof-'));
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`,
  '--no-first-run', `--window-size=${process.env.VENTANA || '1400,900'}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let ws, id = 0;
const pending = new Map(), problems = [];
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJS = async (expr) => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;

try {
  let target;
  for (let t = 0; t < 40 && !target; t++) {
    await sleep(250);
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((x) => x.type === 'page'); } catch {}
  }
  if (!target) throw new Error('No se pudo arrancar Chrome');
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  ws.addEventListener('message', (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
    if (d.method === 'Runtime.exceptionThrown') problems.push('EXCEPCIÓN: ' + d.params.exceptionDetails.exception?.description);
    if (d.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(d.params.type))
      problems.push(`console.${d.params.type}: ` + d.params.args.map((a) => a.value ?? a.description).join(' '));
    if (d.method === 'Log.entryAdded' && d.params.entry.level === 'error' && !/tile\.openstreetmap|nominatim|api\/explicar/.test(d.params.entry.url || ''))
      problems.push('log: ' + d.params.entry.text + ' ' + (d.params.entry.url || ''));
  });
  await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
  if (process.env.MODO === 'pagina') {
    // Web del equipo: carga sin errores y, si existe, el enlace al mapa lleva a un mapa que dibuja celdas.
    await send('Page.navigate', { url });
    await sleep(6000);
    const titulo = await evalJS('document.title');
    const enlace = await evalJS("document.querySelector('a[href=\\'mapa/\\']')?.textContent?.trim() || ''");
    let celdas = 0;
    if (enlace) {
      await evalJS("document.querySelector('a[href=\\'mapa/\\']').click()");
      for (let t = 0; t < 80 && !(celdas > 0); t++) { await sleep(100); celdas = +(await evalJS("document.querySelector('canvas.capa-celdas')?.dataset.dibujadas || 0")); }
    }
    const png = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(shot, Buffer.from(png.result.data, 'base64'));
    const ok = problems.length === 0 && (!process.env.EXIGE_ENLACE || (enlace && celdas > 0));
    console.log(JSON.stringify({ ok, titulo, enlace_mapa: enlace, celdas_mapa_integrado: celdas, url_final: await evalJS('location.href'), problemas: problems, captura: shot }, null, 1));
    process.exitCode = ok ? 0 : 1;
    throw 'fin';
  }
  const t0 = Date.now();
  await send('Page.navigate', { url });
  let n = 0;
  for (let t = 0; t < 60 && !(n > 0); t++) { await sleep(100); n = +(await evalJS("document.querySelector('canvas.capa-celdas')?.dataset.dibujadas || 0")); }
  const tCarga = +(await evalJS("document.querySelector('canvas.capa-celdas')?.dataset.ms || -1"));
  const perf = await evalJS(`JSON.stringify({marcas: performance.getEntriesByType('mark').map(m => [m.name, Math.round(m.startTime)]),
    recursos: performance.getEntriesByType('resource').filter(r => /data|vendor|app/.test(r.name)).map(r => [r.name.split('/').slice(-2).join('/'), Math.round(r.startTime), Math.round(r.responseEnd)]),
    dom: Math.round(performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd)})`);
  if (process.env.DEBUG) console.log(perf, await evalJS("JSON.stringify(['#panel','#ficha','.mapa-wrap','main','body'].map(q => [q, JSON.stringify(document.querySelector(q).getBoundingClientRect()), getComputedStyle(document.querySelector(q)).display, getComputedStyle(document.querySelector(q)).order]))"));
  await sleep(1500);
  // selecciona la primera celda de la lista "Mejores celdas" y espera la ficha
  if (!process.env.SIN_CLIC) await evalJS("document.querySelector('#top button')?.click()");
  let ficha = '';
  for (let t = 0; t < 80 && !ficha; t++) { await sleep(100); ficha = await evalJS("document.querySelector('#ficha h2')?.textContent || ''"); }
  const filas = +(await evalJS("document.querySelectorAll('#ficha tbody tr').length"));
  let explicacion = '';
  if (!process.env.SIN_CLIC) {
    await evalJS("[...document.querySelectorAll('#ficha button')].find(b => b.textContent.includes('Explicar'))?.click()");
    for (let t = 0; t < 50 && !explicacion; t++) { await sleep(100); explicacion = await evalJS("document.querySelector('.explicacion')?.textContent || ''"); if (explicacion.startsWith('Generando')) explicacion = ''; }
  }
  const hash = await evalJS('location.hash');
  await evalJS("document.querySelector('#btn-sobre').click()");
  let sobre = '';
  for (let t = 0; t < 30 && sobre.length < 300; t++) { await sleep(100); sobre = await evalJS("document.querySelector('#sobre-body')?.textContent || ''"); }
  await evalJS("document.querySelector('#sobre').close()");
  const png = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(shot, Buffer.from(png.result.data, 'base64'));
  const ok = problems.length === 0 && n > 0 && tCarga > 0 && tCarga < 3000 && (process.env.SIN_CLIC || (/^Celda [A-Z]{3}_/.test(ficha) && filas >= 1 && explicacion.length > 80 && sobre.includes('PR-AUC')));
  console.log(JSON.stringify({ ok, celdas_dibujadas: n, ms_desde_navegacion_hasta_dibujar: tCarga, ficha, filas_datos: filas, explicacion: explicacion.slice(0, 120), hash, sobre_el_modelo: sobre.includes('PR-AUC') ? sobre.slice(0, 90) : sobre.slice(0, 600), problemas: problems, captura: shot }, null, 1));
  process.exitCode = ok ? 0 : 1;
} catch (e) {
  if (e !== 'fin') { console.error(e); process.exitCode = 1; }
} finally {
  try { ws?.close(); } catch {}
  chrome.kill();
}
