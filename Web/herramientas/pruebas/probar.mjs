// Prueba la web en Chrome headless vía DevTools Protocol (sin dependencias).
// Uso: node probar.mjs <pasos.json> <carpeta_salida>
// Pasos: {"viewport":[w,h,movil]}, {"go":"url"}, {"wait":ms}, {"eval":"js"},
//        {"move":[x,y]}, {"click":[x,y]}, {"tap":[x,y]}, {"shot":"nombre.png"}
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const [,, pasosArchivo, salida] = process.argv;
const pasos = JSON.parse(fs.readFileSync(pasosArchivo, 'utf8'));
fs.mkdirSync(salida, { recursive: true });
const perfil = fs.mkdtempSync(path.join(os.tmpdir(), 'cibh-chrome-'));
const PUERTO = 9333;
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', `--remote-debugging-port=${PUERTO}`, `--user-data-dir=${perfil}`,
  '--no-first-run', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--window-size=1400,900', 'about:blank',
], { stdio: 'ignore' });

const dormir = ms => new Promise(r => setTimeout(r, ms));
let destino;
for (let i = 0; i < 50 && !destino; i++) {
  await dormir(200);
  try { destino = (await (await fetch(`http://127.0.0.1:${PUERTO}/json`)).json()).find(x => x.type === 'page'); } catch {}
}
const ws = new WebSocket(destino.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let n = 0; const pendientes = new Map();
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pendientes.has(m.id)) { pendientes.get(m.id)(m); pendientes.delete(m.id); }
  if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type))
    console.log(`[consola ${m.params.type}]`, m.params.args.map(a => a.value ?? a.description).join(' '));
  if (m.method === 'Runtime.exceptionThrown') console.log('[EXCEPCIÓN]', m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') console.log('[log]', m.params.entry.text, m.params.entry.url || '');
});
const cdp = (method, params = {}) => new Promise(r => { const id = ++n; pendientes.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
await cdp('Runtime.enable'); await cdp('Log.enable'); await cdp('Page.enable');

for (const p of pasos) {
  if (p.viewport) {
    const [w, h, movil] = p.viewport;
    await cdp('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: movil ? 2 : 1, mobile: !!movil });
    await cdp('Emulation.setTouchEmulationEnabled', { enabled: !!movil });
  }
  if (p.net) { await cdp('Network.enable'); await cdp('Network.setCacheDisabled', { cacheDisabled: true });
    await cdp('Network.emulateNetworkConditions', { offline: false, latency: p.net[2], downloadThroughput: p.net[0] * 1000 / 8, uploadThroughput: p.net[1] * 1000 / 8 }); }
  if (p.throttle) await cdp('Emulation.setCPUThrottlingRate', { rate: p.throttle });
  if (p.go) await cdp('Page.navigate', { url: p.go });
  if (p.wait) await dormir(p.wait);
  if (p.waitFor) for (let i = 0; i < 100; i++) {
    const r = await cdp('Runtime.evaluate', { expression: `!!(${p.waitFor})`, returnByValue: true });
    if (r.result?.result?.value) break; await dormir(250);
  }
  if (p.eval) {
    const r = await cdp('Runtime.evaluate', { expression: p.eval, awaitPromise: true, returnByValue: true });
    console.log('[eval]', JSON.stringify(r.result?.result?.value ?? r.result?.exceptionDetails?.exception?.description));
  }
  // clickJS / moveJS: expresión que devuelve [lon, lat] (se evalúa en la página)
  for (const k of ['moveJS', 'clickJS']) if (p[k]) {
    const r = await cdp('Runtime.evaluate', { expression: p[k], awaitPromise: true, returnByValue: true });
    p[k === 'moveJS' ? 'moveLL' : 'clickLL'] = r.result.result.value;
  }
  for (const k of ['moveLL', 'clickLL']) if (p[k]) {
    const r = await cdp('Runtime.evaluate', { expression: `(() => { const q = window.__mapa.project(${JSON.stringify(p[k])}); return [q.x, q.y]; })()`, returnByValue: true });
    p[k === 'moveLL' ? 'move' : 'click'] = r.result.result.value;
    if (k === 'clickLL') await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x: p.click[0], y: p.click[1] });
  }
  if (p.move) await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x: p.move[0], y: p.move[1] });
  if (p.click) for (const type of ['mousePressed', 'mouseReleased'])
    await cdp('Input.dispatchMouseEvent', { type, x: p.click[0], y: p.click[1], button: 'left', clickCount: 1 });
  if (p.tap) await cdp('Input.synthesizeTapGesture', { x: p.tap[0], y: p.tap[1], gestureSourceType: 'touch' });
  // "toque": dedo abajo + dedo arriba por separado (como una pantalla real). A diferencia de "tap",
  // el navegador sí genera el "click" después, así que sirve para pulsar botones en modo móvil.
  if (p.toque) {
    await cdp('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: p.toque[0], y: p.toque[1] }] });
    await new Promise(r => setTimeout(r, 60));
    await cdp('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  }
  if (p.shot) {
    const r = await cdp('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(salida, p.shot), Buffer.from(r.result.data, 'base64'));
    console.log('[captura]', p.shot);
  }
}
ws.close(); chrome.kill();
await dormir(500);
try { fs.rmSync(perfil, { recursive: true, force: true }); } catch {}
