// Dibujos de los iconos del panel (energía, agua, clima…).
// Cada uno es un dibujo de línea en una cuadrícula de 24 × 24 (formato SVG). El color de cada
// variable NO va aquí: se pone en config.js → variables.
//
// ¿Nueva variable? Añade aquí su dibujo con la misma "clave" que en config.js. Si una variable
// no tiene dibujo, el panel muestra un círculo sencillo (no se rompe nada).
// Para dibujar uno nuevo: https://lucide.dev tiene miles de iconos con este mismo estilo
// (24 × 24, línea): basta con copiar lo que hay dentro de su <svg>…</svg>.

export const DIBUJOS = {
  energia:      '<path d="M13 2.5 5 13.5h6l-1 8 8-11h-6l1-8z"/>',
  agua:         '<path d="M12 3c-3.3 4.2-6 7.8-6 11a6 6 0 0 0 12 0c0-3.2-2.7-6.8-6-11z"/>',
  clima:        '<path d="M10 13.6V5.5a2 2 0 0 1 4 0v8.1a4 4 0 1 1-4 0z"/><path d="M12 10v6"/>',
  conectividad: '<path d="M3 9.5a13 13 0 0 1 18 0"/><path d="M6 13a8.5 8.5 0 0 1 12 0"/><path d="M9 16.5a4 4 0 0 1 6 0"/><circle cx="12" cy="20" r=".9" fill="currentColor"/>',
  riesgos:      '<path d="M12 3l7.5 3v5.5c0 4.5-3.2 8.2-7.5 9.5-4.3-1.3-7.5-5-7.5-9.5V6z"/><path d="M12 8.5v4.5"/><circle cx="12" cy="16.3" r=".9" fill="currentColor"/>',
  suelo:        '<path d="M12 3.5 2.5 8.5 12 13.5l9.5-5z"/><path d="M2.5 12.5 12 17.5l9.5-5"/><path d="M2.5 16.5 12 21.5l9.5-5"/>',
};

const POR_DEFECTO = '<circle cx="12" cy="12" r="7"/>';

// Devuelve el icono listo para meter en la página, con el color indicado.
export function icono(clave, color = 'currentColor') {
  return `<svg viewBox="0 0 24 24" style="color:${color}" aria-hidden="true">${DIBUJOS[clave] ?? POR_DEFECTO}</svg>`;
}
