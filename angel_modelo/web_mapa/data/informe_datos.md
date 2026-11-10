# Informe de datos

Huella de los datos: esquema `aaa96582a9f8` · filas `a7befea4e987`. Lector: pipeline/src/cells.py:read_elt.

- Celdas: 41,296 · provincias: 52 · años agregados: [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
- Data centers (celdas): {'datacentermap': 100, 'osm_peeringdb': 63, 'ambas': 21, 'union': 142}
- Filas duplicadas descartadas (se queda la última): ninguna
- Valores fuera de rango plausible pasados a «sin dato»: ninguno
- Columnas con tipo de texto convertidas a número: ninguna

## Cambios respecto a los datos publicados
Sin cambios de esquema ni de cobertura.
- Celdas: 41296 → 41296
- Columnas nuevas (no cambian el mapa hasta registrarlas en config/rubrica.yaml): ninguna
- Columnas desaparecidas: ninguna
- Tipo cambiado: ninguna
- Rango cambiado: ninguna
- Cobertura cambiada: ninguna

## Capas de la rúbrica (activa = cobertura ≥ umbral configurado)

| Capa | Tipo | Columna | Cobertura | Activa |
|---|---|---|---|---|
| agua | exclusiones | `agua_pct` | 100% | sí |
| parque_nacional | exclusiones | `parque_nacional_pct` | 100% | sí |
| flujo_preferente | exclusiones | `zfp_pct` | 100% | sí |
| pendiente_extrema | exclusiones | `slope_pct` | 100% | sí |
| natura2000_alta | condicionantes | `natura2000_pct` | 100% | sí |
| natura2000_parcial | condicionantes | `natura2000_pct` | 100% | sí |
| espacio_protegido | condicionantes | `in_protected_area` | 100% | sí |
| inundable_t100 | condicionantes | `zi_t100_pct` | 100% | sí |
| urbano_denso | condicionantes | `urbano_pct` | 100% | sí |
| servidumbre_aeronautica | condicionantes | `in_flight_path_flag` | 100% | sí |
| costa_baja | condicionantes | `in_low_elevation_coastal_zone` | 100% | sí |
| altitud_alta | condicionantes | `elevation_m` | 100% | sí |
| subestacion | criterios | `dist_substation_220kv_km` | 100% | sí |
| alta_tension | criterios | `dist_hv_line_km` | 100% | sí |
| corredor_fibra | criterios | `dist_infra_corridor_km` | 100% | sí |
| latencia | criterios | `latency_to_hub_ms` | 100% | sí |
| suelo_industrial | criterios | `industrial_pct` | 100% | sí |
| pendiente | criterios | `slope_pct` | 100% | sí |
| refrigeracion | criterios | `free_cooling_hours` | 100% | sí |
| calor_extremo | criterios | `wetbulb_p99_c` | 100% | sí |
| estres_hidrico | criterios | `water_stress` | 0% | **no** |
| agua_proxy | criterios | `annual_precip_mm` | 100% | sí |
| sismicidad | criterios | `pga475_ign_g` | 100% | sí |
| inundacion | criterios | `zi_t500_pct` | 100% | sí |
| accesos | criterios | `dist_motorway_junction_km` | 100% | sí |

Parte del peso de criterios con capa activa: 96%.

## Experimento de modelo (no alimenta el mapa salvo que supere la regla de decisión)
- Variables usadas: 78; de ellas nuevas: ninguna (revisar a mano)
- Descartadas por filtros automáticos: 217

## Avisos
- Ninguno
