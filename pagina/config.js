// =====================================================================
//  CONFIGURACIÓN DE "CAN I BUILD HERE?"
//  Este es el ÚNICO archivo que hace falta tocar para ajustar la web.
//  Después de cambiar algo, guarda y recarga la página (Ctrl+F5).
// =====================================================================

export const CONFIG = {

  // ---------------------------------------------------------------
  // CUADRÍCULA
  // ---------------------------------------------------------------
  // Lado de cada cuadrado en kilómetros. Lo usa el script que genera
  // los datos (herramientas/generar_datos_prueba.mjs) y la nota del panel.
  // OJO: si lo cambias, hay que volver a generar data/ES.json.
  // (Si el archivo de datos trae "meta.tamano_cuadrado_km", la web usa ese.)
  tamano_cuadrado_km: 12,

  // ---------------------------------------------------------------
  // PESOS DE LAS VARIABLES QUE PUNTÚAN
  // ---------------------------------------------------------------
  // Cuánto cuenta cada variable en la puntuación final (0-100).
  // No hace falta que sumen 1: la web los reparte proporcionalmente.
  // Las variables sin dato (null) no cuentan: su peso se reparte
  // entre las que sí tienen dato.
  // Poner un peso a 0 = la variable se muestra pero no puntúa.
  pesos: {
    energia:      0.25,  // disponibilidad y precio de la electricidad
    agua:         0.25,  // agua para refrigeración
    clima:        0.15,  // clima fresco = menos gasto en refrigerar
    conectividad: 0.15,  // fibra, puntos de intercambio de internet
    carreteras:   0.10,  // acceso para obra y mantenimiento
    sismico:      0.10,  // 100 = poco riesgo sísmico
    inundacion:   0,     // 100 = poco riesgo. Ahora solo sirve para descartar
  },

  // Orden e iconos con que se muestran las variables en el panel.
  variables: [
    { clave: 'energia',      icono: '⚡' },
    { clave: 'agua',         icono: '💧' },
    { clave: 'clima',        icono: '🌡️' },
    { clave: 'conectividad', icono: '📡' },
    { clave: 'carreteras',   icono: '🛣️' },
    { clave: 'sismico',      icono: '🌋' },
    { clave: 'inundacion',   icono: '🌊' },
  ],

  // ---------------------------------------------------------------
  // REGLAS DE DESCARTE
  // ---------------------------------------------------------------
  // Un cuadrado sale ROJO directamente (sin importar su puntuación) si:
  //   1) el archivo de datos trae "descartado": true (p. ej. suelo protegido), o
  //   2) cumple alguna de estas reglas. Recuerda: 100 = mejor, así que un
  //      valor MUY BAJO de riesgo significa riesgo MUY ALTO.
  reglas_descarte: [
    { variable: 'inundacion', menor_que: 20, motivo: 'inundacion' }, // inundación alta
    { variable: 'sismico',    menor_que: 10, motivo: 'sismico' },    // riesgo sísmico extremo
  ],

  // ---------------------------------------------------------------
  // COLORES (umbrales de puntuación)
  // ---------------------------------------------------------------
  umbrales: {
    verde:    70,  // >= 70 → viable
    amarillo: 40,  // 40-69 → con condiciones;  < 40 → no viable (rojo)
  },
  colores: {
    verde:     '#22c55e',
    amarillo:  '#facc15',
    rojo:      '#ef4444',
    sin_datos: '#6b7280', // gris: el cuadrado no tiene ningún dato
  },

  // ---------------------------------------------------------------
  // PUNTUACIÓN YA CALCULADA EN EL ARCHIVO
  // ---------------------------------------------------------------
  // true  → si un cuadrado trae "puntuacion" (p. ej. de un modelo de
  //         vuestro equipo), se usa esa. Si no la trae, se calcula.
  // false → siempre se calcula con los pesos de arriba.
  // En ambos casos, los descartes siguen mandando (rojo).
  usar_puntuacion_del_archivo: true,

  // ---------------------------------------------------------------
  // INTERFAZ
  // ---------------------------------------------------------------
  // Muestra la etiqueta "DATOS DE PRUEBA". Ponla a false con datos reales.
  mostrar_etiqueta_datos_prueba: true,

  // Opacidad inicial de la cuadrícula (0 = invisible, 1 = opaca).
  opacidad_inicial: 0.55,

  // Capa base al abrir la web: 'satelite' o 'mapa'.
  capa_inicial: 'satelite',

  // Idioma si el navegador no es ni español ni inglés.
  idioma_por_defecto: 'es',
  idiomas: ['es', 'en'],
};
