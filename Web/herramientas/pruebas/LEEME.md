# Pruebas automáticas en el navegador

Chrome sin ventana ("headless"), controlado con el protocolo de DevTools. No necesita instalar nada.

## Uso
```
# 1) Servidor normal (desde la carpeta pagina):
python -m http.server 8000 --bind 127.0.0.1
# 2) Lanzar una prueba (los pasos van en un .json):
node herramientas/pruebas/probar.mjs herramientas/pruebas/ejemplos/panel_movil.json <carpeta_para_capturas>
```

## Pasos disponibles (en orden dentro del .json)
- `{"viewport":[ancho, alto, esMovil]}` · `{"throttle":4}` (CPU 4× más lenta) · `{"net":[kbps_bajada, kbps_subida, latencia_ms]}`
- `{"go":"url"}` · `{"wait":ms}` · `{"waitFor":"expresión JS"}` (espera hasta 25 s a que sea verdadera)
- `{"eval":"expresión JS"}` (imprime el resultado; puede ser una promesa)
- `{"move":[x,y]}` / `{"click":[x,y]}` en píxeles CSS · `{"tap":[x,y]}` (gesto de toque: el mapa lo reconoce,
  pero **no genera "click"**) · `{"toque":[x,y]}` (dedo abajo + arriba: sí genera "click"; usarlo para botones)
- `{"moveLL":[lon,lat]}` / `{"clickLL":[lon,lat]}` · `{"moveJS":"expr→[lon,lat]"}` / `{"clickJS":"..."}`
- `{"shot":"nombre.png"}` (captura)

## Velocidad "como en Cloudflare"
`node herramientas/pruebas/servidor_comprimido.mjs . 8001` sirve la web comprimida con brotli en el puerto 8001
(recomprime si cambia un archivo). Usar con `{"net":[9000,1500,85]}` + `{"throttle":4}` para un móvil 4G.

## Trucos aprendidos
- Escribir los pasos con comillas simples dentro del JS y evitar `\` (barras invertidas) y regex: rompen el JSON.
- Las capturas en modo móvil salen a doble resolución: las coordenadas de `tap` son la mitad de lo que se ve.
- Un `eval` que lanza un error dentro de un `setTimeout` deja la prueba colgada: usar `async` y `return`.
- Chrome sin tarjeta gráfica dibuja por software: los tiempos son pesimistas respecto a un móvil real.
