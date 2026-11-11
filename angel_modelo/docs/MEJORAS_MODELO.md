# Mejoras del modelo y de la rúbrica (tarea 4), con antes y después

Regla 13: los data centers reales solo **validan**; no fijan pesos ni exclusiones. Todo cambio de pesos se decide entre un máximo de 8 variantes **predefinidas** (`config/columnas.yaml: modelo.variantes`), con validación espacial por provincias o prefecturas.

## a) Diagnóstico con los datos nuevos (España)
| Métrica | Antes (`3585f83`) | Después | Nota |
|---|---|---|---|
| Capas de la rúbrica activas | 11 de 12 criterios (`water_stress` vacía) | igual + capa militar activa (100 %) | Siguen vacías: estrés hídrico, fibra real y capacidad de red por nudo |
| Confianza media | 0,96 | 0,96 | La capa militar está, así que no penaliza |
| Positivos de validación | 142 celdas (unión por celda) | **131** (lista maestra por distancia) | Ya no se cuenta dos veces el mismo DC |
| PR-AUC rúbrica [IC 95 % por provincias] | 0,038 [0,014–0,085] | 0,025 [0,013–0,044] | Baja: target más limpio y regla militar (los DC urbanos están cerca de bases). **No es un objetivo** de la rúbrica |
| AUC rúbrica | 0,85 | 0,83 | |
| Recall de DC en el 5 % mejor (rúbrica) | 50 % | 43 % | |
| PR-AUC logística 2 variables | 0,286 | 0,257 [0,16–0,36] | Sigue siendo la referencia más fuerte |
| PR-AUC réplica del modelo del equipo | 0,188 | 0,157 [0,10–0,21] | P(gana a ambos) = 0 → **no entra al mapa** |
| Estabilidad de Candidatas | 42 % estables con pesos ±50 % (100 sorteos) | **78 %** estables con pesos ±30 % (40 sorteos) | Métricas distintas: la de ahora es la que pide la tarea |
| Candidatas | 3.393 (8,2 %) | **3.136 (7,6 %)** | Dentro del rango razonable configurado [1, 15] % |

## b) Sesgo «ciudad o polígono industrial»
- `industrial_pct` es un criterio positivo con peso acotado (10 de 100). `urbano_pct` alto **penaliza** (≥ 50 %: −5) y **bloquea** la etiqueta Candidata (≥ 80 %, regla nueva `urbano_centro`); nunca suma.
- Ninguna de las dos variables puede dar por sí sola la etiqueta: con el 100 % del peso de `suelo_industrial`, una celda solo suma 10 puntos sobre 75.
- Cuánto explican de la ordenación (Spearman entre la nota de la rúbrica y la variable):

| País | urbano_pct | industrial_pct |
|---|---|---|
| España | 0,25 | 0,31 |
| Japón | 0,67 | 0,59 |

  En España la rúbrica **no** es «ciudad». En Japón correlaciona más porque el suelo llano con red eléctrica coincide con las llanuras urbanizadas: es geografía, no un peso.
- La logística de 2 variables **sí** es «ciudad»: PR-AUC 0,26 en España, porque los DC actuales están en ciudades. Por eso se usa solo como referencia que hay que batir.

## c) Lista maestra de data centers
Se unen datacentermap (puntos) y OSM/PeeringDB (celdas) por distancia: centroide de celda frente a punto, con tolerancia de un lado de celda (3,5 km). Se guarda la fuente de cada registro (`dc_fuente`).
- **España:** 131 celdas; 12 celdas de OSM/PeeringDB eran duplicados de datacentermap.
- **Japón:** 84 celdas; 0 duplicados.

## d) Ajuste prudente de pesos (4 variantes predefinidas, PR-AUC media por pliegues de provincia)
| Variante | España (base 0,030) | Pliegues que mejora (ES) | Japón (base 0,035) | Pliegues que mejora (JP) | ¿Se adopta? |
|---|---|---|---|---|---|
| V1 industrial 10 → 5 | 0,020 | 0 | 0,028 | 0 | No |
| V2 sin latencia | 0,034 | 4 | 0,023 | 2 | **No**: mejora en España dentro del ruido (IC 0,013–0,044) y empeora en Japón; la rúbrica es común y debe ser comparable |
| V3 subestación 20 → 30 | 0,031 | 3 | 0,033 | 2 | No |
| V4 pendiente 10 → 15 | 0,030 | 2 | 0,035 | 3 | No |

**No se cambia ningún peso.** Las variantes se evaluaron y se documentan; ninguna mejora de forma consistente y defendible en los dos países.

## e) Modelo experimental
- Solo variables que pasan los filtros:
  - sin identificadores, coordenadas, constantes ni fuga (`LEAKAGE` del equipo);
  - sin `terrain_ruggedness` ni `aspect_deg` (se queda `slope_pct`);
  - resultado: 81 variables en España y 51 en Japón.
- **Restricciones de monotonía** (`monotonic_cst` de HistGradientBoosting, configurables en `modelo.monotonia`): más distancia a la red, más pendiente o más PGA nunca suben la nota. Se suman a los criterios de expertos del equipo (`priors_voz.csv`).
- LightGBM no carga en macOS sin `libomp`. Comando para quien lo quiera: `brew install libomp`, **no ejecutado**.
- Resultado por país (validación por provincias o prefecturas):
  - España: modelo 0,157 frente a logística 0,257 y rúbrica 0,025.
  - Japón: modelo 0,075 frente a logística 0,061 y rúbrica 0,017, con P(gana a ambos) = 0,70 < 0,9.
  - **No entra al mapa en ningún país.**
- Calibración: en su decil superior predice 36 % (ES) y 47 % (JP), con tasas reales del 3 % → **no hay probabilidades**.
- Transferencia España → Japón: no se ha medido (no se entrena un modelo conjunto; queda como dato informativo pendiente).

## f) Sentido común
Ver `docs/SENTIDO_RESULTADOS.md`. La suite encontró 2 Candidatas en embalses (55-59 % de agua) y se añadió la regla objetiva `agua_dominante` (≥ 50 % impide ser Candidata).

## g) Confianza
- Candidata exige una cobertura ≥ 0,85 (`cobertura_minima_candidata`).
- En Japón la cobertura es de 0,82 en todas las celdas (faltan fibra/corredores, inundación y estrés hídrico), así que **no hay Candidatas** y el mapa arranca en «Ordenación provisional (datos incompletos)», con aviso.

## h) Balance honesto
- **Mejoró:**
  - las restricciones, que ahora tienen más sentido (militar explícita, centros urbanos densos y embalses no pueden ser Candidatas);
  - la validación, con una lista de DC sin duplicados;
  - la estabilidad de las Candidatas ante cambios de pesos;
  - la arquitectura multipaís.
- **No mejoró:**
  - la capacidad de la rúbrica para «encontrar» los DC actuales, que no es su objetivo;
  - el modelo, que sigue sin superar a la regla de 2 variables.
- **Limitación principal:** faltan capas decisivas (capacidad de red por nudo, fibra, suelo disponible y, en Japón, las capas legales de MLIT). Ninguna mejora de pesos compensa datos que no hay.
