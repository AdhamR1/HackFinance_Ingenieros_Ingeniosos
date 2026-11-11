(async () => {
  const sel = ['.marca', '.buscador', '#boton-mundo', '#selector-pais', '.idiomas', '#etiqueta-prueba', '#controles-mapa', '#opacidad-valor', '#leyenda', '.maplibregl-ctrl-attrib', '.maplibregl-ctrl-group', '#panel', '.panel-cerrar', '#boton-plegar', '.segmentado', '#tooltip'];
  const medir = () => Object.fromEntries(sel.map(s => { const e = document.querySelector(s); if (!e || !e.getClientRects().length) return [s, '-']; const b = e.getBoundingClientRect(); return [s, `${Math.round(b.left)}-${Math.round(b.right)} x ${Math.round(b.top)}-${Math.round(b.bottom)}`]; }));
  const espera = ms => new Promise(r => setTimeout(r, ms));
  const pon = async l => { document.querySelector('.idiomas [data-idioma=' + l + ']').click(); await espera(1500); };
  await pon('es'); const es = medir();
  await pon('en'); const en = medir();
  await pon('es');
  return sel.filter(s => es[s] !== en[s]).map(s => `${s}: ES ${es[s]} | EN ${en[s]}`).join('\n') || 'todo igual';
})()
