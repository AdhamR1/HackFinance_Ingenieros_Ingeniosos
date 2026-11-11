# Informe de datos

Huella de los datos: esquema `98eddeed9e01` · filas `4fb4d7dc43d8`. Lector: pipeline/src/cells.py:read_elt.

- Celdas: 30,779 · provincias: 47 · años agregados: [2025]
- Data centers (celdas): {'datacentermap': 84, 'osm_peeringdb': 28, 'ambas': 28, 'lista_maestra': 84}
- Filas duplicadas descartadas (se queda la última): ninguna
- Valores fuera de rango plausible pasados a «sin dato»: ninguno
- Columnas con tipo de texto convertidas a número: ninguna

## Cambios respecto a los datos publicados
**Los datos han cambiado.**
- Celdas: 30779 → 30779
- Columnas nuevas (no cambian el mapa hasta registrarlas en config/rubrica.yaml): militar_menor
- Columnas desaparecidas: ninguna
- Tipo cambiado: ninguna
- Rango cambiado: ninguna
- Cobertura cambiada: ninguna

## Capa militar (control)
- Estado: ok · polígonos: 670 · área: 1680.3 km² · fuente: OpenStreetMap (Overpass API) (2026-11-11)
- Celdas con instalación: 617 · en franja: 964
- Limitación: huella física de OpenStreetMap, NO el perímetro legal; puede estar incompleta.

## Capas de la rúbrica (activa = cobertura ≥ umbral configurado)

| Capa | Tipo | Columna | Cobertura | Activa |
|---|---|---|---|---|
| agua | exclusiones | `agua_pct` | 0% | **no** |
| parque_nacional | exclusiones | `parque_nacional_pct` | 100% | sí |
| pendiente_extrema | exclusiones | `slope_pct` | 100% | sí |
| militar | exclusiones | `militar_pct` | 100% | sí |
| control_urbanizacion | exclusiones | `control_urbanizacion_pct` | 0% | **no** |
| espacio_protegido | condicionantes | `in_protected_area` | 100% | sí |
| urbano_denso | condicionantes | `urbano_pct` | 100% | sí |
| agua_dominante | condicionantes | `agua_pct` | 0% | **no** |
| urbano_centro | condicionantes | `urbano_pct` | 100% | sí |
| servidumbre_aeronautica | condicionantes | `in_flight_path_flag` | 100% | sí |
| costa_baja | condicionantes | `in_low_elevation_coastal_zone` | 100% | sí |
| altitud_alta | condicionantes | `elevation_m` | 100% | sí |
| militar_franja | condicionantes | `en_franja` | 100% | sí |
| militar_menor | condicionantes | `militar_menor` | 100% | sí |
| sedimentos | condicionantes | `sedimentos_especial_pct` | 0% | **no** |
| subestacion | criterios | `dist_substation_220kv_km` | 99% | sí |
| alta_tension | criterios | `dist_hv_line_km` | 100% | sí |
| corredor_fibra | criterios | `dist_infra_corridor_km` | 0% | **no** |
| latencia | criterios | `latency_to_hub_ms` | 100% | sí |
| suelo_industrial | criterios | `industrial_pct` | 100% | sí |
| pendiente | criterios | `slope_pct` | 100% | sí |
| refrigeracion | criterios | `free_cooling_hours` | 100% | sí |
| calor_extremo | criterios | `wetbulb_p99_c` | 100% | sí |
| estres_hidrico | criterios | `water_stress` | 0% | **no** |
| agua_proxy | criterios | `annual_precip_mm` | 100% | sí |
| sismicidad | criterios | `pga475_ign_g` | 100% | sí |
| inundacion | criterios | `zi_t500_pct` | 0% | **no** |
| accesos | criterios | `dist_motorway_junction_km` | 100% | sí |

Parte del peso de criterios con capa activa: 82%.

## Experimento de modelo (no alimenta el mapa salvo que supere la regla de decisión)
- Variables usadas: 53; de ellas nuevas: ['militar_menor'] (revisar a mano)
- Descartadas por filtros automáticos: 243

## Avisos
- columna 'pga_475y_g' leída como 'pga475_ign_g' (alias)
- falta finanzas_jp_3500.parquet: lo que depende de ella queda 'no disponible'
- Candidatas = 0.0 % de las celdas, fuera del rango razonable [1, 15] %: revisar la rúbrica (¿demasiado laxa o estricta?).
