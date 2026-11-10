// =====================================================================
//  CONFIGURACIÓN DE "CAN I BUILD HERE?"
//  Este es el ÚNICO archivo que hace falta tocar para ajustar la web.
//  Después de cambiar algo, guarda y recarga la página (Ctrl+F5).
// =====================================================================

export const CONFIG = {

  // ---------------------------------------------------------------
  // CUADRÍCULA
  // ---------------------------------------------------------------
  // Superficie de cada cuadrado en km². El lado es la raíz cuadrada:
  //   12 km² → cuadrados de 3,46 × 3,46 km   ·   144 km² → 12 × 12 km
  // Lo usa el script que genera los datos (herramientas/generar_datos_prueba.mjs)
  // y la nota del panel.
  // OJO: si lo cambias, hay que volver a generar data/ES.json.
  // (Si el archivo de datos trae "meta.area_cuadrado_km2", la web usa ese.)
  area_cuadrado_km2: 12,

  // ---------------------------------------------------------------
  // PESOS (PROVISIONALES, SOLO PARA LOS DATOS DE PRUEBA)
  // ---------------------------------------------------------------
  // La web NO enseña los pesos en ningún sitio. Solo se usan para calcular una
  // nota provisional cuando un cuadrado no trae "puntuacion" (datos inventados).
  // Con los datos reales, la nota vendrá ya calculada por el modelo del equipo
  // en "puntuacion" y estos pesos no se usarán (así el modelo no está en la web).
  // No hace falta que sumen 1. Las variables sin dato (null) no cuentan.
  pesos: {
    energia:      0.25,
    agua:         0.20,
    clima:        0.15,
    riesgos:      0.15,
    conectividad: 0.15,
    suelo:        0.10,
  },

  // ---------------------------------------------------------------
  // VARIABLES
  // ---------------------------------------------------------------
  // Orden y color del icono con que se muestran en el panel. Todas van de 0 a 100
  // y 100 = mejor (en "riesgos", 100 = poco riesgo).
  // Los dibujos de los iconos están en js/iconos.js (misma "clave").
  // Para añadir una variable: añadirla aquí, en i18n/es.json y en.json
  // ("var_<clave>") y, si se quiere, su dibujo en js/iconos.js.
  variables: [
    { clave: 'energia',      color: '#f5b301' }, // ámbar
    { clave: 'agua',         color: '#38bdf8' }, // azul
    { clave: 'clima',        color: '#fb7185' }, // rosa
    { clave: 'riesgos',      color: '#fb923c', ayuda: true }, // naranja; "ayuda" = muestra "(100 = poco riesgo)"
    { clave: 'conectividad', color: '#a78bfa' }, // violeta
    { clave: 'suelo',        color: '#d6a46b' }, // marrón tierra
  ],

  // ---------------------------------------------------------------
  // PERMISOS NECESARIOS
  // ---------------------------------------------------------------
  // Vienen en el archivo de datos, en "permisos" de cada cuadrado (lista con
  // los que le afectan). En el panel solo salen los que afectan al cuadrado.
  // descarta: true → si el cuadrado está afectado, sale ROJO ("Descartado").
  permisos: [
    { clave: 'natura_2000',      descarta: true  },
    { clave: 'parque_nacional',  descarta: true  },
    { clave: 'suelo_urbano',     descarta: false },
    { clave: 'flujo_preferente', descarta: false },
    { clave: 'zona_inundable',   descarta: false },
  ],

  // ---------------------------------------------------------------
  // REGLAS DE DESCARTE
  // ---------------------------------------------------------------
  // Un cuadrado sale ROJO directamente (sin importar su puntuación) si:
  //   1) el archivo de datos trae "descartado": true, o
  //   2) le afecta un permiso con "descarta: true" (arriba), o
  //   3) CUALQUIERA de las variables baja de este valor (100 = mejor, así que
  //      un valor muy bajo es muy malo). Una variable sin dato (null) no descarta.
  //      Poner null para desactivar esta regla.
  descarte_si_variable_menor_que: 20,

  // ---------------------------------------------------------------
  // MOTIVOS ("Por qué se acepta" / "Por qué se rechaza")
  // ---------------------------------------------------------------
  // Si el cuadrado trae "motivos_a_favor" / "motivos_en_contra", se enseñan esos.
  // Si no, la web los saca de los datos (mejores y peores variables, permisos).
  // Verde → a favor · rojo → en contra · amarillo → los dos.
  motivos_maximos: 3,

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
  // PAÍSES "PRÓXIMAMENTE"
  // ---------------------------------------------------------------
  // Países que aún no tienen datos pero que pensamos añadir. Salen en el
  // selector y con el aviso "Próximamente". El resto del mundo sale como
  // "No disponible". Códigos ISO de 2 letras (FR = Francia, US = EE. UU.…).
  // Cuando un país tenga datos, se añade a data/paises.json (y se puede
  // quitar de aquí: si está en los dos sitios, manda data/paises.json).
  paises_proximamente: ['US', 'FR', 'DE', 'GB', 'IE', 'NL', 'PT', 'IT'],

  // ---------------------------------------------------------------
  // INTERFAZ
  // ---------------------------------------------------------------
  // Si solo hay un país con datos, empezar a descargar su cuadrícula en segundo
  // plano en cuanto se abre la web (así, al elegirlo, aparece mucho antes).
  precargar_datos: true,

  // Muestra la etiqueta "DATOS DE PRUEBA". Ponla a false con datos reales.
  mostrar_etiqueta_datos_prueba: true,

  // Opacidad inicial de la cuadrícula (0 = invisible, 1 = opaca).
  opacidad_inicial: 0.4,

  // Nombres de ciudades y regiones encima del satélite (como la vista "híbrida").
  mostrar_nombres_lugares: true,

  // Buscador de lugares. Las comunidades y provincias se buscan sin internet;
  // los pueblos y ciudades, con Photon (servicio gratuito basado en OpenStreetMap).
  // Si Photon dejara de funcionar, poner a false: seguirán funcionando comunidades y provincias.
  buscar_con_photon: true,

  // Capa base al abrir la web: 'satelite' o 'mapa'.
  capa_inicial: 'satelite',

  // Idioma si el navegador no es ni español ni inglés.
  idioma_por_defecto: 'es',
  idiomas: ['es', 'en'],
};
