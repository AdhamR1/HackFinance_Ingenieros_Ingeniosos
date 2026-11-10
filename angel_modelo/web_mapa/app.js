/* Mapa de cribado de data centers (España, celdas de 3,5 km).
 * Sin claves ni dependencias de servidor: lee data/*.json generados por angel_modelo/src/exportacion.py.
 * Las ~41.000 celdas se pintan en un único <canvas> (mucho más rápido que 41.000 polígonos SVG).
 */
(() => {
  'use strict';

  // ---------------------------------------------------------------- constantes
  const CLASE = ['cand', 'duda', 'nov', 'noev'];
  const COLOR = { cand: '#0072B2', duda: '#E69F00', nov: '#d9d9d9', noev: '#f3d7e8', excl: '#d9d9d9' };
  const VIRIDIS = ['#440154', '#3B528B', '#21918C', '#5EC962', '#FDE725'];
  const DC_COLOR = '#D55E00';
  const ALPHA = 0.72;
  const BUCKET = 0.05;   // grados, para localizar la celda bajo el ratón

  const $ = (s) => document.querySelector(s);
  const el = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
    }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  const fmt = (v, d = 1) => (v == null || Number.isNaN(v)) ? '—' :
    Number(v).toLocaleString('es-ES', { maximumFractionDigits: d, minimumFractionDigits: 0 });
  const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

  // ---------------------------------------------------------------- estado de la app
  const st = { vista: 'estado', estados: [true, true, true, true], prov: -1, conf: 0, dc: true, sel: -1 };
  let D, C, N, nLat, nLon, nodesOf, cLat, cLon, buckets, byIJ, DC = null;
  const provCache = new Map();
  let map, canvas, ctx, dpr = 1, px = null, pxZoom = null, patterns = {}, raf = 0;

  // ---------------------------------------------------------------- carga
  async function init() {
    map = L.map('map', { preferCanvas: true, zoomControl: true, minZoom: 5, maxZoom: 14, keyboard: true })
      .setView([40.2, -3.7], 6);
    // Teselas estándar de OpenStreetMap (política de uso: tráfico bajo y atribución visible).
    // Para producción con mucho tráfico, cambiar TILE_URL por un proveedor propio (ver README).
    L.tileLayer(window.TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; colaboradores de <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    const t0 = performance.now();
    const [d, dc] = await Promise.all([
      fetch('data/celdas.json').then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
      fetch('data/dc.json').then((r) => r.json()).catch(() => null),
    ]);
    performance.mark('datos');
    D = d; C = d.cells; DC = dc; N = C.i.length;
    buildGeometry();
    performance.mark('geometria');
    setupCanvas();
    performance.mark('canvas');
    setupUI();
    performance.mark('ui');
    $('#fecha').textContent = `${D.meta.fecha_datos} · huella ${D.meta.huella.esquema}/${D.meta.huella.filas}`;
    avisosDatos();
    $('#cargando').hidden = true;
    if (/\/mapa\/?/.test(location.pathname)) $('#volver').hidden = false;   // dentro de la web del equipo
    console.info(`celdas: ${N} en ${(performance.now() - t0).toFixed(0)} ms`);
    const h = new URLSearchParams(location.hash.slice(1)).get('celda');
    if (h) { const k = idToCell(h); if (k >= 0) select(k, true); }
  }

  function buildGeometry() {
    if (D.geometria === 'centroide') return buildCentroides();
    const nd = D.nodes, nn = nd.i.length;
    nLat = new Float64Array(nn); nLon = new Float64Array(nn);
    const nodeKey = new Map();
    for (let q = 0; q < nn; q++) {
      nLat[q] = nd.lat[q] / 1e5; nLon[q] = nd.lon[q] / 1e5; nodeKey.set(nd.i[q] * 10000 + nd.j[q], q);
    }
    nodesOf = new Int32Array(N * 4); cLat = new Float64Array(N); cLon = new Float64Array(N);
    byIJ = new Map(); buckets = new Map();
    const off = [[0, 0], [1, 0], [1, 1], [0, 1]];
    for (let k = 0; k < N; k++) {
      let la = 0, lo = 0;
      for (let q = 0; q < 4; q++) {
        const n = nodeKey.get((C.i[k] + off[q][0]) * 10000 + C.j[k] + off[q][1]);
        nodesOf[k * 4 + q] = n; la += nLat[n]; lo += nLon[n];
      }
      cLat[k] = la / 4; cLon[k] = lo / 4;
      byIJ.set(C.i[k] * 10000 + C.j[k], k);
      const b = Math.floor(cLon[k] / BUCKET) + ',' + Math.floor(cLat[k] / BUCKET);
      if (!buckets.has(b)) buckets.set(b, []);
      buckets.get(b).push(k);
    }
  }

  // Rejilla desconocida: cuadrados reconstruidos desde el centroide (4 nodos propios por celda)
  function buildCentroides() {
    nLat = new Float64Array(N * 4); nLon = new Float64Array(N * 4);
    nodesOf = new Int32Array(N * 4); cLat = new Float64Array(N); cLon = new Float64Array(N);
    byIJ = new Map(); buckets = new Map();
    const hlat = D.medio_lado_lat, off = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
    for (let k = 0; k < N; k++) {
      cLat[k] = C.lat[k] / 1e5; cLon[k] = C.lon[k] / 1e5;
      const hlon = C.hl[k] / 1e6;
      for (let q = 0; q < 4; q++) {
        nLat[k * 4 + q] = cLat[k] + off[q][1] * hlat; nLon[k * 4 + q] = cLon[k] + off[q][0] * hlon;
        nodesOf[k * 4 + q] = k * 4 + q;
      }
      const b = Math.floor(cLon[k] / BUCKET) + ',' + Math.floor(cLat[k] / BUCKET);
      if (!buckets.has(b)) buckets.set(b, []);
      buckets.get(b).push(k);
    }
  }

  function avisosDatos() {
    const m = D.meta, box = $('#aviso-datos');
    const partes = [];
    if (m.datos_cambiados) partes.push('Los datos han cambiado respecto a la versión publicada anterior (ver informe de datos).');
    if (m.capas_omitidas && m.capas_omitidas.length) partes.push(`Capas omitidas por falta de datos: ${m.capas_omitidas.join(', ')}.`);
    if (!partes.length) return;
    box.replaceChildren(el('strong', { text: 'Aviso de datos. ' }), partes.join(' '), ' ',
      el('a', { href: 'data/informe_datos.md', text: 'Informe de datos' }));
    box.hidden = false;
  }

  const idToCell = (id) => {
    if (C.ids) { const k = C.ids.indexOf(id); return k; }
    const m = /^ESP_(-?\d+)_(-?\d+)$/.exec(id || '');
    return m ? (byIJ.get(+m[1] * 10000 + +m[2]) ?? -1) : -1;
  };
  const cellId = (k) => (C.ids ? C.ids[k] : `ESP_${C.i[k]}_${C.j[k]}`);

  // ---------------------------------------------------------------- canvas
  function setupCanvas() {
    canvas = el('canvas', { class: 'capa-celdas', 'aria-hidden': 'true' });
    Object.assign(canvas.style, { position: 'absolute', left: 0, top: 0, zIndex: 450, pointerEvents: 'none' });
    map.getContainer().appendChild(canvas);
    ctx = canvas.getContext('2d');
    patterns = {
      duda: makePattern(6, (g) => { g.fillStyle = '#000'; g.beginPath(); g.arc(3, 3, 0.9, 0, 7); g.fill(); }),
      nov: makePattern(6, (g) => { g.strokeStyle = 'rgba(70,70,70,.8)'; g.lineWidth = 1; diag(g, 6); }),
      excl: makePattern(5, (g) => { g.strokeStyle = '#222'; g.lineWidth = 1.2; diag(g, 5); }),
      noev: makePattern(5, (g) => { g.fillStyle = '#CC79A7'; g.fillRect(0, 3, 5, 2); }),
    };
    resize();
    map.on('resize', () => { resize(); schedule(); });
    map.on('move', schedule);
    map.on('zoomstart', () => { canvas.style.visibility = 'hidden'; });
    map.on('zoomend', () => { canvas.style.visibility = 'visible'; schedule(); });
    map.on('moveend', () => { schedule(); updateTop(); });
    map.on('click', (e) => { const k = cellAt(e.latlng.lat, e.latlng.lng); if (k >= 0) select(k); });
    map.getContainer().addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target === map.getContainer()) {
        const c = map.getCenter(); const k = cellAt(c.lat, c.lng);
        if (k >= 0) { e.preventDefault(); select(k); }
      }
    });
    schedule();
  }

  function makePattern(s, fn) {
    const c = document.createElement('canvas'); c.width = c.height = s;
    fn(c.getContext('2d')); return ctx.createPattern(c, 'repeat');
  }
  function diag(g, s) { g.beginPath(); g.moveTo(0, s); g.lineTo(s, 0); g.moveTo(-1, 1); g.lineTo(1, -1); g.moveTo(s - 1, s + 1); g.lineTo(s + 1, s - 1); g.stroke(); }

  function resize() {
    const s = map.getSize(); dpr = window.devicePixelRatio || 1;
    canvas.width = s.x * dpr; canvas.height = s.y * dpr;
    canvas.style.width = s.x + 'px'; canvas.style.height = s.y + 'px';
  }
  function schedule() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); }

  // Web Mercator igual que Leaflet (EPSG:3857, teselas de 256 px): evita crear 45.000 objetos LatLng
  function project(lat, lon, z) {
    const s = 256 * 2 ** z, r = Math.PI / 180, la = Math.max(-85, Math.min(85, lat)) * r;
    return [s * (lon + 180) / 360, s * (1 - Math.log(Math.tan(la) + 1 / Math.cos(la)) / Math.PI) / 2];
  }
  function ensurePx(z) {
    if (pxZoom === z) return;
    px = new Float64Array(nLat.length * 2);
    for (let q = 0; q < nLat.length; q++) { const p = project(nLat[q], nLon[q], z); px[2 * q] = p[0]; px[2 * q + 1] = p[1]; }
    pxZoom = z;
  }

  const visible = (k) => st.estados[C.e[k]] && (st.prov < 0 || C.p[k] === st.prov) && C.c[k] >= st.conf;
  function styleOf(k) {
    if (C.x[k]) return 'excl';
    if (st.vista === 'orden') return 'v' + Math.min(4, Math.floor(Math.max(0, C.s[k]) / 20));
    return CLASE[C.e[k]];
  }

  function draw() {
    const tDraw = performance.now();
    if (!canvas.dataset.ms) performance.mark('inicio_dibujo');
    const z = map.getZoom(); ensurePx(z);
    const pb = map.getPixelBounds(), ox = pb.min.x, oy = pb.min.y, w = pb.max.x - ox, h = pb.max.y - oy;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const groups = new Map();
    for (let k = 0; k < N; k++) {
      if (!visible(k)) continue;
      const n0 = nodesOf[k * 4], x = px[2 * n0] - ox, y = px[2 * n0 + 1] - oy;
      if (x < -60 || y < -60 || x > w + 60 || y > h + 60) continue;
      const s = styleOf(k);
      if (!groups.has(s)) groups.set(s, []);
      groups.get(s).push(k);
    }
    // Alejado (celdas < 8 px) se pintan rectángulos con fillRect: rellenar un trazado con 40.000
    // subtrazados es lentísimo en rasterizado por software. De cerca, polígonos exactos.
    const n0 = nodesOf[0], n1 = nodesOf[1];
    const small = Math.abs(px[2 * n1] - px[2 * n0]) < 8;
    for (const [s, ks] of groups) {
      const color = s[0] === 'v' && s.length === 2 ? VIRIDIS[+s[1]] : COLOR[s];
      if (small) {
        const fills = [[ALPHA, color]];
        if (patterns[s] && z >= 7) fills.push([0.9, patterns[s]]);
        for (const [a, fs] of fills) {
          ctx.globalAlpha = a; ctx.fillStyle = fs;
          for (const k of ks) rectOf(k, ox, oy);
        }
        continue;
      }
      ctx.beginPath();
      for (const k of ks) path(k, ox, oy);
      ctx.globalAlpha = ALPHA; ctx.fillStyle = color; ctx.fill();
      if (patterns[s]) { ctx.globalAlpha = 0.9; ctx.fillStyle = patterns[s]; ctx.fill(); }
      if (z >= 10) { ctx.globalAlpha = 0.9; ctx.strokeStyle = '#fff'; ctx.lineWidth = 0.6; ctx.stroke(); }
    }
    ctx.globalAlpha = 1;
    let drawn = 0; for (const ks of groups.values()) drawn += ks.length;
    canvas.dataset.dibujadas = drawn;              // para tests y depuración
    if (!canvas.dataset.ms) performance.mark('primer_dibujo');
    if (!canvas.dataset.ms) canvas.dataset.ms = Math.round(performance.now());  // ms desde la navegación
    canvas.dataset.tam = `${canvas.width}x${canvas.height}`;
    if (st.dc && DC) drawDC(z, ox, oy);
    if (st.sel >= 0) {
      ctx.beginPath(); path(st.sel, ox, oy);
      ctx.strokeStyle = '#000'; ctx.lineWidth = 4; ctx.stroke();
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke();
    }
    canvas.dataset.drawMs = Math.round(performance.now() - tDraw);
  }
  function rectOf(k, ox, oy) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let q = 0; q < 4; q++) {
      const n = nodesOf[k * 4 + q], x = px[2 * n] - ox, y = px[2 * n + 1] - oy;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    const xa = Math.floor(x0), ya = Math.floor(y0);
    ctx.fillRect(xa, ya, Math.max(1, Math.ceil(x1) - xa), Math.max(1, Math.ceil(y1) - ya));
  }
  function path(k, ox, oy) {
    for (let q = 0; q < 4; q++) {
      const n = nodesOf[k * 4 + q], x = px[2 * n] - ox, y = px[2 * n + 1] - oy;
      if (q === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
  }
  function drawDC(z, ox, oy) {
    const r = z >= 9 ? 6 : z >= 7 ? 4.5 : 3.2;
    const dot = (lat, lon, square) => {
      const p = project(lat, lon, z), x = p[0] - ox, y = p[1] - oy;
      ctx.beginPath();
      if (square) ctx.rect(x - r, y - r, 2 * r, 2 * r); else ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = DC_COLOR; ctx.fill(); ctx.lineWidth = 1.5; ctx.strokeStyle = '#fff'; ctx.stroke();
      ctx.lineWidth = 0.8; ctx.strokeStyle = '#000'; ctx.stroke();
    };
    for (const p of DC.puntos) dot(p.lat, p.lon, false);
    for (const [lon, lat] of DC.celdas_osm) dot(lat, lon, true);
  }

  // punto dentro del cuadrilátero (lon/lat; a 3,5 km la celda es prácticamente plana)
  function cellAt(lat, lon) {
    const bx = Math.floor(lon / BUCKET), by = Math.floor(lat / BUCKET);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const k of buckets.get((bx + dx) + ',' + (by + dy)) || []) {
        let inside = false;
        for (let a = 0, b = 3; a < 4; b = a++) {
          const na = nodesOf[k * 4 + a], nb = nodesOf[k * 4 + b];
          if ((nLat[na] > lat) !== (nLat[nb] > lat) &&
              lon < (nLon[nb] - nLon[na]) * (lat - nLat[na]) / (nLat[nb] - nLat[na]) + nLon[na]) inside = !inside;
        }
        if (inside) return k;
      }
    }
    return -1;
  }

  // ---------------------------------------------------------------- UI
  function setupUI() {
    const fe = $('#f-estados');
    const sw = ['cand', 'duda', 'nov', 'noev'];
    D.estados.forEach((name, e) => {
      const cb = el('input', { type: 'checkbox', checked: '', 'data-e': e });
      cb.addEventListener('change', () => { st.estados[e] = cb.checked; refresh(); });
      fe.append(el('label', {}, cb, el('span', { class: `sw ${sw[e]}`, 'aria-hidden': 'true' }), name,
        el('span', { class: 'cnt', id: `cnt-${e}` })));
    });
    const sp = $('#f-prov');
    D.provincias.map((p, k) => [p, k]).sort((a, b) => a[0].localeCompare(b[0], 'es'))
      .forEach(([p, k]) => sp.append(el('option', { value: k, text: p })));
    sp.addEventListener('change', () => {
      st.prov = +sp.value; refresh();
      if (st.prov >= 0) fitProv(st.prov);
    });
    const fc = $('#f-conf');
    fc.addEventListener('input', () => { st.conf = +fc.value; $('#o-conf').textContent = fc.value + ' %'; refresh(); });
    $('#f-dc').addEventListener('change', (e) => { st.dc = e.target.checked; schedule(); legend(); });
    document.querySelectorAll('input[name=vista]').forEach((r) => r.addEventListener('change', () => {
      st.vista = r.value; $('#nota-orden').hidden = st.vista !== 'orden'; refresh();
    }));
    $('#buscar').addEventListener('submit', (e) => { e.preventDefault(); search($('#q').value); });
    $('#btn-sobre').addEventListener('click', openAbout);
    // Si casi todo es "No evaluable", empieza en la ordenación provisional
    const noev = C.e.filter((e) => e === 3).length;
    if (noev > 0.5 * N) { document.querySelector('input[value=orden]').click(); }
    if (window.matchMedia('(max-width: 720px)').matches) $('#leyenda').classList.add('plegada');
    legend(); counts(); updateTop();
  }

  function refresh() { schedule(); counts(); updateTop(); legend(); }

  function counts() {
    const n = [0, 0, 0, 0];
    for (let k = 0; k < N; k++) if ((st.prov < 0 || C.p[k] === st.prov) && C.c[k] >= st.conf) n[C.e[k]]++;
    n.forEach((v, e) => { $(`#cnt-${e}`).textContent = v.toLocaleString('es-ES'); });
  }

  function legend() {
    const lg = $('#leyenda'); lg.replaceChildren();
    const titulo = (t) => {
      const b = el('button', { type: 'button', 'aria-expanded': String(!lg.classList.contains('plegada')), text: t + ' ▾' });
      b.addEventListener('click', () => { lg.classList.toggle('plegada'); b.setAttribute('aria-expanded', String(!lg.classList.contains('plegada'))); });
      return el('h2', {}, b);
    };
    if (st.vista === 'estado') {
      lg.append(titulo('Estado (rúbrica)'));
      D.estados.forEach((name, e) => lg.append(el('div', {}, el('span', { class: `sw ${CLASE[e]}` }), name)));
      lg.append(el('div', {}, el('span', { class: 'sw excl' }), 'Excluida (dentro de No viable)'));
    } else {
      lg.append(titulo('Percentil de ordenación'), el('div', { class: 'grad', role: 'img',
        'aria-label': 'De morado (percentil 0) a amarillo (percentil 100)' }),
      el('div', {}, el('span', { text: '0 · peor' }), el('span', { style: 'margin-left:auto', text: '100 · mejor' })),
      el('div', {}, el('span', { class: 'sw excl' }), 'Excluida'),
      el('p', { class: 'nota', text: 'Ordenación provisional, no probabilidad.' }));
    }
    if (st.dc) {
      lg.append(el('div', {}, el('span', { class: 'sw dc' }), 'Data center (datacentermap)'),
        el('div', {}, el('span', { class: 'sw dc', style: 'border-radius:0' }), 'Celda con DC (OSM/PeeringDB)'));
    }
  }

  function updateTop() {
    if (!map) return;
    const b = map.getBounds(), ol = $('#top'); ol.replaceChildren();
    const ks = [];
    for (let k = 0; k < N; k++) {
      if (!visible(k) || C.x[k] || C.e[k] === 3) continue;
      if (!b.contains([cLat[k], cLon[k]])) continue;
      ks.push(k);
    }
    ks.sort((a, z) => C.n[z] - C.n[a] || C.c[z] - C.c[a]);
    for (const k of ks.slice(0, 10)) {
      ol.append(el('li', {}, el('button', { type: 'button', onclick: () => select(k, true),
        text: `${D.provincias[C.p[k]]} · nota ${C.n[k]} · P${C.s[k]} · ${D.estados[C.e[k]]}` })));
    }
    if (!ks.length) ol.append(el('li', { text: 'Ninguna celda visible con estos filtros.' }));
  }

  function fitProv(p) {
    let s = 90, n = -90, w = 180, e = -180;
    for (let k = 0; k < N; k++) if (C.p[k] === p) {
      s = Math.min(s, cLat[k]); n = Math.max(n, cLat[k]); w = Math.min(w, cLon[k]); e = Math.max(e, cLon[k]);
    }
    map.fitBounds([[s, w], [n, e]], { padding: [20, 20] });
  }

  // ---------------------------------------------------------------- ficha
  async function loadProv(p) {
    if (!provCache.has(p)) provCache.set(p, fetch(`data/prov/${p}.json`).then((r) => r.json()));
    return provCache.get(p);
  }

  async function select(k, fly = false) {
    st.sel = k; schedule();
    history.replaceState(null, '', '#celda=' + cellId(k));
    if (fly) map.flyTo([cLat[k], cLon[k]], Math.max(map.getZoom(), 10), { duration: 0.6 });
    const f = $('#ficha'); f.replaceChildren(el('p', { text: 'Cargando ficha…' }));
    const P = await loadProv(C.p[k]);
    if (st.sel !== k) return;
    renderFicha(k, P.celdas[String(k)], P);
  }

  function motivoTexto(code, det) {
    const txt = D.motivos[code], cod = D.motivo_codigos[code];
    const m = /^[-+]:(.+)$/.exec(cod);
    if (m && det) {
      const ci = D.criterios.findIndex((c) => c.id === m[1]);
      if (ci >= 0) return `${txt}: ${fmt(det.v[ci], 2)} ${D.criterios[ci].unidad} (subnota ${fmt(det.sub[ci], 0)}/100)`;
    }
    return txt;
  }

  function renderFicha(k, det, P) {
    const f = $('#ficha'); f.replaceChildren();
    const e = C.e[k], conf = C.c[k], nivel = conf >= 95 ? 'alta' : conf >= 85 ? 'media' : 'baja';
    f.append(
      el('h2', { text: `Celda ${cellId(k)}` }),
      el('p', { class: 'nota', text: `${P.provincia} (${P.comunidad}) · centro ${fmt(det.lat, 4)}, ${fmt(det.lon, 4)}` }),
      el('p', {}, el('span', { class: 'estado-tag' }, el('span', { class: `sw ${C.x[k] ? 'excl' : CLASE[e]}` }),
        D.estados[e] + (C.x[k] ? ' (excluida)' : ''))),
      el('div', { class: 'kpis' },
        el('div', { class: 'kpi' }, el('b', { text: C.s[k] >= 0 ? `P${C.s[k]}` : '—' }),
          el('span', { text: 'Percentil de ordenación (no es probabilidad)' })),
        el('div', { class: 'kpi' }, el('b', { text: `${C.n[k]}/100` }), el('span', { text: 'Nota de la rúbrica' })),
        el('div', { class: 'kpi' }, el('b', { text: `${conf} %` }), el('span', { text: `Confianza ${nivel}: parte del peso con datos` })),
        el('div', { class: 'kpi' }, el('b', { text: `${fmt(P.media_nota, 1)}` }),
          el('span', { text: `Nota media en ${P.provincia} (España ${fmt(P.media_nota_espana, 1)})` }))),
    );

    const mot = [0, 1, 2].map((q) => C.m[k * 3 + q]).filter((c) => c >= 0);
    f.append(el('h3', { text: 'Motivos principales' }),
      mot.length ? el('ul', { class: 'motivos' }, ...mot.map((c) => el('li', { text: motivoTexto(c, det) })))
        : el('p', { class: 'nota', text: 'Sin motivos destacados.' }));

    f.append(el('h3', { text: 'Exclusiones aplicadas' }),
      el('p', { text: det.excl ? det.excl.split(',').map((x) => x.replace(/_/g, ' ')).join(', ') : 'Ninguna' }));

    f.append(el('h3', { text: 'Data center real en la celda' }),
      el('p', { text: det.dc_fuente ? `Sí (${det.dc_fuente})${det.dc ? ': ' + det.dc : ''}` : 'No consta' }));

    const tb = el('tbody');
    D.criterios.forEach((c, i) => {
      const bar = el('div', { class: 'bar' }, el('i', { style: `width:${det.sub[i]}%` }));
      tb.append(el('tr', {},
        el('td', {}, `${c.etiqueta} `, el('span', { class: 'nota', text: `(peso ${c.peso})` }), bar),
        el('td', { class: 'num', text: det.v[i] == null ? 'sin dato' : `${fmt(det.v[i], 2)} ${c.unidad}` }),
        el('td', { class: 'num', text: P.media_valores[i] == null ? '—' : `${fmt(P.media_valores[i], 2)}` })));
    });
    f.append(el('h3', { text: 'Datos usados' }),
      el('table', {}, el('thead', {}, el('tr', {}, el('th', { text: 'Criterio y subnota' }),
        el('th', { class: 'num', text: 'Celda' }), el('th', { class: 'num', text: 'Media prov.' }))), tb),
      el('p', { class: 'nota', text: `Nota sin condicionantes ${fmt(det.nota_bruta, 1)} − penalizaciones ${fmt(det.pen, 0)} = ${C.n[k]}.` }));

    const falt = det.faltan ? det.faltan.split(',').map((id) => (D.criterios.find((c) => c.id === id) || { etiqueta: id }).etiqueta) : [];
    f.append(el('h3', { text: 'Datos que faltan' }),
      el('ul', { class: 'motivos' },
        ...(falt.length ? falt.map((t) => el('li', { text: `${t} (sin dato en esta celda)` })) : [el('li', { text: 'Ninguno de los criterios de la rúbrica.' })]),
        ...D.meta.capas_no_disponibles.map((t) => el('li', { text: t }))));

    if (det.avisos_equipo) {
      f.append(el('h3', { text: 'Avisos (reglas del equipo)' }),
        el('ul', { class: 'motivos' }, ...det.avisos_equipo.split(' | ').map((t) => el('li', { text: t }))));
    }
    if (det.inv_eur_m2 != null) {
      f.append(el('h3', { text: 'Estimación financiera (equipo)' }),
        el('p', { text: `Inversión orientativa: ${fmt(det.inv_eur_m2, 0)} €/m² para un data center de 10 MW (pipeline/src/finanzas.py, con supuestos).` }));
    }
    const nav = el('div', { class: 'vecinas', role: 'group', 'aria-label': 'Ir a una celda vecina' });
    [['', 0, 0], ['↑ Norte', 0, 1], ['', 0, 0], ['← Oeste', -1, 0], ['', 0, 0], ['Este →', 1, 0], ['', 0, 0], ['↓ Sur', 0, -1], ['', 0, 0]]
      .forEach(([t, di, dj]) => {
        if (!t) { nav.append(el('span', { class: 'c' })); return; }
        const kk = C.i ? byIJ.get((C.i[k] + di) * 10000 + C.j[k] + dj) : undefined;
        const b = el('button', { type: 'button', 'aria-label': t, title: t, text: t.split(' ')[0].length === 1 ? t.split(' ')[0] : t.slice(-1) });
        if (kk === undefined) b.disabled = true; else b.addEventListener('click', () => select(kk, true));
        nav.append(b);
      });
    f.append(el('h3', { text: 'Celdas vecinas' }), nav);
    const out = el('p', { class: 'explicacion', 'aria-live': 'polite' });
    const btn = el('button', { type: 'button', class: 'btn-sec', text: 'Explicar esta celda' });
    btn.addEventListener('click', () => explicar(k, det, P, btn, out));
    f.append(el('h3', { text: 'Explicación' }), btn, out);
    if (det.nota_modelo_equipo != null) {
      f.append(el('details', {}, el('summary', { text: 'Experimento: modelo del equipo (no se usa en el mapa)' }),
        el('p', { class: 'nota', text: `Percentil del modelo LightGBM del equipo: P${det.nota_modelo_equipo}. Mide parecido a donde ya hay data centers; en validación por provincias no supera a una regla de 2 variables. Ver "Sobre el modelo".` })));
    }
  }

  // ---------------------------------------------------------------- explicación (Claude o plantilla)
  function plantilla(det, P) {
    const mot = (det.motivos || []).map((i) => P.motivos_textos[i]).join('; ').toLowerCase() || 'sin motivos destacados';
    return `La celda ${det.id} (${P.provincia}) sale como «${det.estado}» con una nota de ${fmt(det.nota, 1)}/100 ` +
      `(media de la provincia: ${fmt(P.media_nota, 1)}) y está en el percentil ${det.score_pct ?? '—'} de la ordenación. ` +
      `Lo que más pesa: ${mot}. Exclusiones: ${det.excl || 'ninguna'}. Hay datos para el ${Math.round(det.cobertura * 100)} % del peso de la rúbrica. ` +
      'Es un cribado inicial, no un estudio geotécnico ni urbanístico; la puntuación es una ordenación, no una probabilidad.';
  }
  async function explicar(k, det, P, btn, out) {
    btn.disabled = true; out.textContent = 'Generando explicación…';
    try {
      const r = await fetch('api/explicar', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ prov: C.p[k], k }) });
      const j = r.ok || r.status === 429 ? await r.json() : null;
      if (j && j.texto) { out.textContent = j.texto; out.append(el('span', { class: 'nota', text: ` (${j.fuente})` })); }
      else if (j && j.error) { out.textContent = j.error; }
      else throw new Error(String(r.status));
    } catch {
      out.textContent = plantilla(det, P);
      out.append(el('span', { class: 'nota', text: ' (plantilla automática: el servicio de IA no está disponible aquí)' }));
    } finally { btn.disabled = false; }
  }

  // ---------------------------------------------------------------- buscador
  async function search(q) {
    const out = $('#resultados'); out.replaceChildren();
    const s = q.trim(); if (!s) return;
    const add = (txt, fn) => out.append(el('li', {}, el('button', { type: 'button', onclick: fn, text: txt })));
    const mc = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/.exec(s);
    if (mc) {
      const lat = +mc[1], lon = +mc[2], k = cellAt(lat, lon);
      if (k >= 0) { select(k, true); add(`Celda ${cellId(k)} (${lat}, ${lon})`, () => select(k, true)); }
      else add('Esas coordenadas no caen en ninguna celda de España', () => map.flyTo([lat, lon], 9));
      return;
    }
    const n = norm(s);
    D.provincias.forEach((p, k) => {
      if (norm(p).includes(n)) add(`Provincia: ${p}`, () => { $('#f-prov').value = k; st.prov = k; refresh(); fitProv(k); });
    });
    if (DC) DC.puntos.filter((p) => norm(`${p.mun} ${p.n}`).includes(n)).slice(0, 5)
      .forEach((p) => add(`Data center: ${p.n}`, () => { const k = cellAt(p.lat, p.lon); if (k >= 0) select(k, true); else map.flyTo([p.lat, p.lon], 11); }));
    out.append(el('li', { class: 'nota', text: 'Buscando municipios en OpenStreetMap…' }));
    try {
      const url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=es&limit=5&accept-language=es&q=' + encodeURIComponent(s);
      const r = await fetch(url, { headers: { Accept: 'application/json' } });
      const res = r.ok ? await r.json() : [];
      out.lastChild.remove();
      res.forEach((x) => add(x.display_name.split(',').slice(0, 3).join(','), () => {
        const k = cellAt(+x.lat, +x.lon);
        if (k >= 0) select(k, true); else map.flyTo([+x.lat, +x.lon], 10);
      }));
      if (!out.children.length) out.append(el('li', { text: 'Sin resultados.' }));
    } catch {
      out.lastChild.textContent = 'No se pudo consultar Nominatim (sin conexión). Prueba con una provincia o coordenadas.';
    }
  }

  // ---------------------------------------------------------------- sobre el modelo
  async function openAbout() {
    const dlg = $('#sobre'), body = $('#sobre-body');
    dlg.showModal();
    try {
      const M = await fetch('data/metricas.json').then((r) => r.json());
      const R = M.resultados.dc_real;
      const nombre = { rubrica: 'Rúbrica (no entrenada)', logistica_2_variables: 'Regresión logística: % urbano + % industrial',
        modelo_equipo_replica: 'Modelo del equipo (réplica, gradient boosting)', aleatorio: 'Azar (referencia)' };
      const iv = (a) => `[${fmt(a[0], 3)} – ${fmt(a[1], 3)}]`;
      const tb = el('tbody');
      for (const key of Object.keys(nombre)) {
        const r = R[key]; if (!r) continue;
        tb.append(el('tr', {}, el('td', { text: nombre[key] }), el('td', { class: 'num', text: `${fmt(r.pr_auc, 3)} ${iv(r.pr_auc_ic95)}` }),
          el('td', { class: 'num', text: `${fmt(r.auc, 3)} ${iv(r.auc_ic95)}` }), el('td', { class: 'num', text: `${fmt(100 * r.recall_top5, 0)} %` })));
      }
      const cal = R.modelo_equipo_replica.calibracion;
      body.replaceChildren(
        el('p', {}, el('strong', { text: 'Quién decide el estado de cada celda: ' }),
          'una rúbrica transparente con exclusiones (agua, parque nacional, zona de flujo preferente, pendiente extrema), condicionantes que restan puntos y ',
          `${D.criterios.length} criterios ponderados (los pesos suman 100). Candidata: nota ≥ ${D.meta.umbral_candidata}; Dudosa: a menos de ${D.meta.margen_duda} puntos del umbral o con datos incompletos.`),
        el('h3', { text: 'Qué se ha medido' }),
        el('p', { class: 'nota', text: `${M.validacion}. Objetivo de validación: ${M.target}. ${R.positivos} celdas con data center entre ${R.celdas.toLocaleString('es-ES')}.` }),
        el('table', {}, el('thead', {}, el('tr', {}, el('th', { text: 'Puntuación' }), el('th', { class: 'num', text: 'PR-AUC [IC 95 %]' }),
          el('th', { class: 'num', text: 'AUC [IC 95 %]' }), el('th', { class: 'num', text: 'DC en el 5 % mejor' }))), tb),
        el('p', {}, el('strong', { text: M.modelo_entra_al_mapa ? 'El modelo entra al mapa como capa de afinidad. ' : 'El modelo entrenado NO entra al mapa. ' }),
          `Regla fijada de antemano: ${M.regla_de_decision}. Probabilidad observada: ${fmt(100 * R.prob_modelo_supera_a_ambos, 1)} %. `,
          'Una regla de 2 variables (suelo urbano e industrial) encuentra mejor los data centers existentes: el modelo aprende «ciudad o polígono», no «buen sitio».'),
        el('p', { class: 'nota', text: `Calibración del modelo: en su 10 % superior predice ${fmt(100 * cal.decil_superior_prob_media, 1)} % y la tasa real es ${fmt(100 * cal.decil_superior_tasa_real, 1)} %. Por eso ninguna nota se presenta como probabilidad.` }),
        el('p', { class: 'nota', text: 'La rúbrica no se diseñó para encontrar los data centers existentes, sino para puntuar condiciones de construcción; aun así ninguna exclusión deja fuera un data center real.' }),
        el('h3', { text: 'Lo que no se ha medido' }), el('ul', {}, ...M.lo_que_no_se_ha_medido.map((t) => el('li', { text: t }))),
        el('h3', { text: 'Capas que faltan' }), el('ul', {}, ...D.meta.capas_no_disponibles.map((t) => el('li', { text: t }))),
        el('h3', { text: 'Pesos de la rúbrica' }),
        el('ul', {}, ...D.criterios.map((c) => el('li', { text: `${c.etiqueta}: ${c.peso}` }))),
        el('p', { class: 'nota', text: `Métricas calculadas con los datos de huella ${M.huella_datos ? M.huella_datos.esquema + '/' + M.huella_datos.filas : '—'}` +
          (M.huella_datos && M.huella_datos.filas !== D.meta.huella.filas ? ' (OJO: no son los datos actuales).' : ' (los datos actuales).') }));
    } catch (err) {
      body.textContent = 'No se pudieron cargar las métricas (data/metricas.json).';
    }
  }

  init().catch((err) => {
    console.error(err);
    $('#cargando').textContent = 'No se pudieron cargar los datos del mapa. Sirve la carpeta con un servidor (python -m http.server) en vez de abrir el archivo directamente.';
  });
})();
