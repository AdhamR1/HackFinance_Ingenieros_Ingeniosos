# Sentido de los resultados (generado por src/sentido.py)

Comprobaciones automáticas por país (fallos = 0 en 1, 2 y 4). Ejecuta `actualizar.py sentido` para regenerarlo.

## ES · 41,296 celdas · Candidatas 3219 (7.79 %)
- Estados: {'No viable': 33951, 'Dudosa': 4125, 'Candidata': 3219, 'No evaluable': 1}
- (1) Candidatas con exclusión activa: **0**
- (2) Candidatas en agua dominante o centro urbano denso: **0**
- (3) Monotonía: probada en tests/test_sentido.py (empeorar un criterio nunca sube la nota)
- (4) NaN inesperados: **0**
- (5) % Candidatas en el rango [1, 15]: sí
- (6) Estabilidad con pesos ±30 % (Candidatas que lo siguen siendo en ≥ 90 % de 40 sorteos): 77.9 %
- Revisión: 100 celdas (20 mejores de 5 divisiones); sospechosas: 0 · {}
  (lista completa en salida/es/top20_divisiones.csv)

## JP · 30,779 celdas · Candidatas 0 (0.0 %)
- Estados: {'No viable': 30032, 'Dudosa': 624, 'No evaluable': 123}
- (1) Candidatas con exclusión activa: **0**
- (2) Candidatas en agua dominante o centro urbano denso: **0**
- (3) Monotonía: probada en tests/test_sentido.py (empeorar un criterio nunca sube la nota)
- (4) NaN inesperados: **0**
- (5) % Candidatas en el rango [1, 15]: **NO (aviso)**
- (6) Estabilidad con pesos ±30 % (Candidatas que lo siguen siendo en ≥ 90 % de 40 sorteos): None %
- Revisión: 100 celdas (20 mejores de 5 divisiones); sospechosas: 1 · {'a menos de 1 km de una pista de aeropuerto': 1}
  (lista completa en salida/jp/top20_divisiones.csv)

| División | Celda | Estado | Nota | Sospecha |
|---|---|---|---|---|
| Nagano | JPN_23_5 | Dudosa | 74.6 | a menos de 1 km de una pista de aeropuerto |

## Reglas propuestas para las sospechas
- Pista de aeropuerto a < 1 km: ya penaliza `servidumbre_aeronautica` cuando la celda está en la trayectoria; una distancia < 1 km a la pista sin trayectoria no se ha convertido en regla (sin base normativa verificada).
- Montaña (> 1.200 m): `altitud_alta` penaliza desde 1.500 m; el sobrecoste entre 1.200 y 1.500 m lo recoge la pendiente.
- Embalses: `agua` excluye desde el 90 % de la celda; entre 20 y 90 % la parcela útil se reduce, pero no se veta.
- Polígono lleno (> 60 % industrial): no se puede verificar la disponibilidad real de parcelas con los datos actuales (limitación).
