# -*- coding: utf-8 -*-
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.formatting.rule import FormulaRule

M, A = "MVP", "Ampliado"
F, L, K, C = "Feature", "Etiqueta", "Clave", "Control"
R, PX, S, D = "Real", "Proxy", "Sintético", "Derivado"

# (bloque, tabla, [ (campo, tipo, unidad, descripcion, fuente_global, fuente_nacional, prioridad, rol, origen) ])
B = []

B.append(("00 Identificación y geometría", "sites", [
 ("site_id","string","-","Identificador único del emplazamiento","-","-",M,K,D),
 ("country_iso3","string","ISO 3166-1","País (USA, MYS, IND, AUS, CHN, JPN, GBR, ESP)","-","-",M,K,R),
 ("admin1","string","-","Región / estado / comunidad autónoma","GADM, geoBoundaries","-",M,F,R),
 ("admin2","string","-","Provincia / condado / prefectura","GADM, geoBoundaries","-",A,F,R),
 ("lat","float","grados WGS84","Latitud del centroide","-","-",M,K,R),
 ("lon","float","grados WGS84","Longitud del centroide","-","-",M,K,R),
 ("h3_cell_r7","string","H3 res. 7","Celda hexagonal (~5 km²) para unir capas precalculadas","Uber H3 (librería)","-",M,K,D),
 ("area_ha","float","ha","Superficie de la parcela","OSM, catastros","Catastro (ESP), HM Land Registry (GBR), condados (USA)",A,F,R),
 ("parcel_compactness","float","0-1","Índice de compacidad de la forma de la parcela","Calculado","-",A,F,D),
 ("elevation_m","float","m","Altitud media","Copernicus DEM GLO-30","IGN MDT (ESP), USGS 3DEP (USA)",M,F,R),
 ("slope_pct","float","%","Pendiente media: encarece el movimiento de tierras","Copernicus DEM GLO-30","-",M,F,D),
 ("aspect_deg","float","grados","Orientación del terreno","Copernicus DEM GLO-30","-",A,F,D),
 ("terrain_ruggedness","float","índice","Rugosidad del terreno (TRI)","Copernicus DEM GLO-30","-",A,F,D),
 ("dist_existing_dc_km","float","km","Distancia al data center existente más cercano (efecto clúster)","OSM telecom=data_center, PeeringDB facilities","Expedientes públicos",M,F,R),
 ("n_existing_dc_50km","int","número","Data centers existentes en 50 km","OSM, PeeringDB","-",A,F,R),
 ("dc_capacity_50km_mw","float","MW","Capacidad instalada de data centers en 50 km","Expedientes y prensa","-",A,F,PX),
]))

B.append(("01 Energía", "sites", [
 ("dist_substation_km","float","km","Distancia a la subestación de alta tensión más cercana","OSM power=substation","REE (ESP), EIA (USA), NESO (GBR), AEMO/GA (AUS)",M,F,R),
 ("substation_voltage_kv","float","kV","Tensión de esa subestación","OSM tag voltage","Operadores de red nacionales",M,F,R),
 ("n_substations_20km","int","número","Subestaciones en 20 km (redundancia)","OSM","-",A,F,R),
 ("dist_hv_line_km","float","km","Distancia a línea de alta tensión","OSM power=line","-",M,F,R),
 ("dist_400kv_line_km","float","km","Distancia a línea de muy alta tensión (≥345-400 kV)","OSM","REE, NESO, OCCTO",A,F,R),
 ("grid_capacity_available_mw","float","MW","Capacidad de acceso disponible en el nudo","Rara vez pública","REE publica capacidad de acceso por nudo (ESP)",M,F,S),
 ("grid_connection_wait_months","float","meses","Plazo típico de conexión a la red","Informes sectoriales","Colas de conexión: NESO (GBR), LBNL Queued Up (USA)",A,F,PX),
 ("electricity_price_industrial_usd_mwh","float","USD/MWh","Precio eléctrico industrial","IEA, Eurostat, GlobalPetrolPrices","EIA (USA), OMIE (ESP)",M,F,R),
 ("wholesale_price_mean_usd_mwh","float","USD/MWh","Precio mayorista medio anual","Ember","OMIE, AEMO, JEPX, IEX India",A,F,R),
 ("electricity_price_volatility","float","desv. típica","Volatilidad del precio mayorista","Ember","-",A,F,D),
 ("grid_carbon_intensity_gco2_kwh","float","gCO2/kWh","Intensidad de carbono de la red","Ember, Electricity Maps (parcialmente comercial)","-",M,F,R),
 ("renewable_share_pct","float","%","Cuota renovable de la generación","Ember, IRENA","-",M,F,R),
 ("dist_power_plant_km","float","km","Distancia a la central eléctrica más cercana","Global Energy Monitor, WRI GPPD","-",A,F,R),
 ("nearest_plant_type","category","-","Tecnología de esa central (nuclear, gas, eólica…)","Global Energy Monitor","-",A,F,R),
 ("gen_capacity_50km_mw","float","MW","Capacidad de generación en 50 km","Global Energy Monitor, WRI GPPD","-",A,F,R),
 ("renewable_capacity_50km_mw","float","MW","Capacidad renovable en 50 km (PPA locales)","Global Energy Monitor","-",A,F,R),
 ("dist_nuclear_plant_km","float","km","Distancia a central nuclear (energía firme; también restricción)","Global Energy Monitor, IAEA PRIS","-",A,F,R),
 ("dist_gas_pipeline_km","float","km","Distancia a gasoducto (generación de respaldo)","GEM Global Gas Infrastructure Tracker","-",A,F,R),
 ("wind_capacity_factor_pct","float","%","Factor de capacidad eólico potencial","Global Wind Atlas","-",A,F,R),
 ("grid_saidi_min_year","float","min/año","Duración media de cortes (fiabilidad de red)","World Bank (indicadores históricos)","Reguladores nacionales",A,F,R),
 ("grid_saifi_year","float","cortes/año","Frecuencia media de cortes","World Bank (histórico)","Reguladores nacionales",A,F,R),
 ("ppa_price_usd_mwh","float","USD/MWh","Precio de PPA renovable de referencia","Informes LevelTen, BNEF (parcial)","-",A,F,PX),
 ("grid_congestion_flag","bool","0/1","Zona con congestión de red conocida","-","Mapas de capacidad de operadores",A,F,PX),
]))

B.append(("02 Sísmica y geotecnia", "sites", [
 ("pga_475y_g","float","g","Aceleración máxima del suelo, periodo de retorno 475 años","GEM Global Seismic Hazard Map (licencia NC)","IGN (ESP), USGS NSHM (USA), J-SHIS (JPN), NSHA (AUS), BGS (GBR), BIS IS 1893 (IND), GB 18306 (CHN)",M,F,R),
 ("pga_2475y_g","float","g","PGA, periodo de retorno 2475 años","GEM","USGS NSHM, J-SHIS",A,F,R),
 ("sa_0_2s_g","float","g","Aceleración espectral a 0,2 s (edificios rígidos)","GEM","USGS NSHM",A,F,R),
 ("sa_1_0s_g","float","g","Aceleración espectral a 1,0 s","GEM","USGS NSHM",A,F,R),
 ("seismic_zone_national","category","-","Zona sísmica según la norma nacional","-","NCSE-02 (ESP), IS 1893 (IND), etc.",A,F,R),
 ("n_eq_m4_100km_50y","int","número","Terremotos M≥4 en 100 km en los últimos 50 años","USGS ComCat, ISC","Catálogo IGN, JMA, CENC",M,F,R),
 ("max_mag_100km_hist","float","Mw","Magnitud máxima histórica en 100 km","ISC-GEM, USGS ComCat","-",A,F,R),
 ("dist_m5_epicenter_km","float","km","Distancia al epicentro M≥5 más cercano","USGS ComCat, ISC","-",A,F,R),
 ("dist_active_fault_km","float","km","Distancia a falla activa","GEM Global Active Faults","QAFI (ESP), USGS Quaternary Faults, AIST (JPN)",M,F,R),
 ("fault_slip_rate_mm_yr","float","mm/año","Tasa de deslizamiento de esa falla","GEM Global Active Faults","-",A,F,R),
 ("vs30_ms","float","m/s","Vs30 estimada por proxy topográfico","USGS Global Vs30","J-SHIS (JPN, por microzonas)",M,F,PX),
 ("soil_class","category","A-E","Clase de suelo unificada a partir de Vs30","Derivado","-",M,F,D),
 ("sediment_thickness_m","float","m","Espesor de sedimentos sobre roca","Pelletier et al. (NASA ORNL DAAC)","-",A,F,R),
 ("depth_to_bedrock_cm","float","cm","Profundidad hasta la roca","SoilGrids (ISRIC)","-",A,F,R),
 ("lithology_class","category","-","Litología superficial dominante","GLiM (Global Lithological Map)","Mapas geológicos IGME, BGS, USGS, GSJ",M,F,R),
 ("soil_type_wrb","category","-","Tipo de suelo (clasificación WRB)","SoilGrids","-",A,F,R),
 ("clay_pct","float","%","Contenido de arcilla (suelos expansivos)","SoilGrids","-",A,F,R),
 ("sand_pct","float","%","Contenido de arena (licuefacción)","SoilGrids","-",A,F,R),
 ("bulk_density","float","kg/dm³","Densidad aparente del suelo","SoilGrids","-",A,F,R),
 ("groundwater_depth_m","float","m","Profundidad del nivel freático","Fan et al. global water table","USGS NWIS, piezómetros CHE (ESP)",A,F,R),
 ("liquefaction_susceptibility","float","0-1","Susceptibilidad a licuefacción","USGS global liquefaction model","-",A,F,R),
 ("landslide_susceptibility","float","0-5","Susceptibilidad a deslizamientos","NASA Global Landslide Susceptibility","-",A,F,R),
 ("karst_flag","bool","0/1","Terreno kárstico (dolinas, cavidades)","WOKAM (World Karst Aquifer Map)","IGME (ESP)",M,F,R),
 ("subsidence_mm_yr","float","mm/año","Velocidad de hundimiento del terreno (InSAR)","EGMS (solo Europa)","InSAR nacionales",A,F,R),
 ("expansive_soil_flag","bool","0/1","Suelo expansivo o yesífero","Derivado de SoilGrids y litología","IGME (yesos valle del Ebro)",A,F,D),
 ("dist_volcano_km","float","km","Distancia al volcán activo más cercano","Smithsonian GVP","JMA (JPN)",A,F,R),
 ("tsunami_risk_flag","bool","0/1","Zona expuesta a tsunami","GAR / ThinkHazard!","JMA, NOAA",A,F,R),
 ("induced_seismicity_flag","bool","0/1","Actividad industrial que induce sismicidad (fracking, inyección)","-","USGS (Oklahoma/Texas)",A,F,PX),
 ("dist_mine_quarry_km","float","km","Distancia a mina o cantera (voladuras y vibración)","OSM landuse=quarry","-",A,F,R),
 ("dist_railway_km","float","km","Distancia a vía férrea (vibración continua)","OSM railway","-",A,F,R),
 ("nearest_station_id","string","NET.STA","Estación sísmica usada para el H/V","FDSN (EarthScope, GEOFON, ORFEUS)","IGN, NIED, BGS, GA, NCS",M,K,R),
 ("dist_station_km","float","km","Distancia a esa estación: mide la confianza del H/V","FDSN","-",M,C,D),
 ("hv_f0_hz","float","Hz","Frecuencia de resonancia H/V (heredada de la estación)","Calculado (tabla signal_features)","-",M,F,D),
 ("hv_a0","float","adimensional","Amplitud del pico H/V","Calculado","-",M,F,D),
 ("ambient_vibration_db","float","dB","Nivel de vibración ambiental 1-30 Hz","Calculado","-",M,F,D),
 ("hv_confidence","float","0-1","Confianza del dato H/V (distancia, calidad SESAME, roca)","Calculado","-",M,C,D),
]))

B.append(("03 Riesgos naturales", "sites", [
 ("flood_depth_rp100_m","float","m","Calado de inundación fluvial, retorno 100 años","JRC Global Flood Hazard, WRI Aqueduct Floods","SNCZI (ESP), FEMA NFHL (USA), EA (GBR), MLIT (JPN)",M,F,R),
 ("flood_depth_rp500_m","float","m","Calado de inundación, retorno 500 años","JRC, Aqueduct Floods","FEMA, SNCZI",A,F,R),
 ("pluvial_flood_risk","float","0-5","Riesgo de inundación por lluvia intensa","ThinkHazard! (World Bank)","EA surface water (GBR)",A,F,R),
 ("coastal_flood_depth_rp100_m","float","m","Inundación costera, retorno 100 años","Aqueduct Floods","-",A,F,R),
 ("dist_river_km","float","km","Distancia al río más cercano","HydroRIVERS (HydroSHEDS)","-",M,F,R),
 ("river_order","int","Strahler","Orden del río más cercano (tamaño)","HydroRIVERS","-",A,F,R),
 ("dist_coast_km","float","km","Distancia a la costa (corrosión salina, marejada)","Natural Earth, OSM coastline","-",M,F,R),
 ("cyclone_freq_100y","float","eventos/100 años","Frecuencia de ciclones tropicales en 200 km","IBTrACS (NOAA)","JMA, BoM",M,F,R),
 ("cyclone_max_wind_ms","float","m/s","Viento máximo histórico de ciclón","IBTrACS","-",A,F,R),
 ("wildfire_hazard","float","0-5","Peligro de incendio forestal","ThinkHazard!, GWIS (Copernicus)","-",M,F,R),
 ("burned_area_10y_pct_10km","float","%","Superficie quemada en 10 años en 10 km","NASA FIRMS / MODIS MCD64","EFFIS (ESP)",A,F,R),
 ("extreme_heat_hazard","float","0-5","Peligro de calor extremo","ThinkHazard!","-",A,F,R),
 ("multi_hazard_index","float","0-100","Índice compuesto de riesgos naturales","Derivado","INFORM Risk (país)",A,F,D),
 # --- Inundaciones (ampliado) ---
 ("flood_depth_rp10_m","float","m","Calado de inundación fluvial, retorno 10 años (eventos frecuentes)","JRC Global Flood Hazard, WRI Aqueduct Floods","FEMA, SNCZI, EA",A,F,R),
 ("flood_depth_rp1000_m","float","m","Calado de inundación, retorno 1000 años (escenario extremo)","JRC, Aqueduct Floods","SNCZI, EA",A,F,R),
 ("in_official_flood_zone","bool","0/1","Dentro de zona inundable oficial","-","SNCZI (ESP), FEMA SFHA (USA), EA Flood Zones (GBR), MLIT hazard maps (JPN)",M,F,R),
 ("flood_protection_standard_rp","float","años","Nivel de protección de diques y defensas (periodo de retorno)","FLOPROS (Scussolini et al.)","Inventarios nacionales de defensas",A,F,R),
 ("height_above_drainage_m","float","m","Altura sobre el cauce más cercano (HAND): cuanto menor, más expuesto","MERIT Hydro","-",M,F,D),
 ("topographic_wetness_index","float","índice","Tendencia del terreno a acumular agua","Copernicus DEM (calculado)","-",A,F,D),
 ("flash_flood_susceptibility","float","0-5","Susceptibilidad a avenidas súbitas","ThinkHazard!, cálculo desde pendiente y precipitación","-",A,F,PX),
 ("groundwater_flood_risk","float","0-5","Riesgo de inundación por subida del freático","-","BGS Groundwater Flooding (GBR)",A,F,R),
 ("dist_dam_upstream_km","float","km","Distancia a presa aguas arriba (riesgo de rotura)","GRanD, GDW","Inventarios de presas (SNCZI, USACE NID)",A,F,R),
 ("hist_flood_events_30km_20y","int","número","Inundaciones registradas en 30 km en 20 años","Global Flood Database (Tellman et al.), Dartmouth Flood Observatory","-",M,F,R),
 # --- Costa ---
 ("storm_surge_rp100_m","float","m","Marea meteorológica con retorno 100 años","GTSM (Global Tide and Surge Model, Copernicus)","-",A,F,R),
 ("coastal_erosion_m_yr","float","m/año","Tasa de erosión de la costa más cercana","Shoreline Monitor (Luijendijk et al.)","-",A,F,R),
 ("in_low_elevation_coastal_zone","bool","0/1","En zona costera a menos de 10 m de altitud","SEDAC LECZ","-",M,F,R),
 # --- Viento y tormentas ---
 ("cyclone_wind_rp50_ms","float","m/s","Viento de ciclón con retorno 50 años","STORM dataset (Bloemendaal et al.)","JMA, BoM",M,F,R),
 ("cyclone_wind_rp50_2050_ms","float","m/s","Viento de ciclón con retorno 50 años en clima 2050","STORM future climate","-",A,F,R),
 ("tornado_density","float","eventos/10.000 km²/año","Densidad de tornados","-","NOAA SPC (USA), ESWD (Europa), JMA",A,F,R),
 ("severe_storm_days_year","float","días/año","Días con tormenta convectiva severa","ERA5 (índices de inestabilidad, calculado)","ESSL",A,F,D),
 ("dust_storm_days_year","float","días/año","Días con tormenta de polvo o arena","CAMS, MERRA-2","IMD, BoM",A,F,PX),
 ("extreme_cold_days_year","float","días/año","Días con mínima por debajo de -15 °C","ERA5-Land","-",A,F,D),
 # --- Incendios ---
 ("fire_weather_index_p95","float","índice","Índice meteorológico de incendios (FWI), percentil 95","Copernicus CEMS Fire Weather Index","EFFIS",M,F,R),
 ("fire_weather_days_2050","float","días/año","Días con peligro de incendio alto en 2050","Copernicus CDS (proyecciones FWI)","-",A,F,R),
 ("dist_forest_edge_km","float","km","Distancia al borde de bosque o matorral","ESA WorldCover","-",A,F,D),
 ("wildland_urban_interface_flag","bool","0/1","En interfaz urbano-forestal","Global WUI map (Schug et al.)","SILVIS (USA)",A,F,R),
 # --- Riesgos geológicos no sísmicos ---
 ("hist_landslides_20km","int","número","Deslizamientos registrados en 20 km","NASA Global Landslide Catalog","IGME (ESP), BGS (GBR), USGS",A,F,R),
 ("sinkhole_events_10km","int","número","Hundimientos o dolinas registrados en 10 km","-","IGME, BGS GeoSure, USGS",A,F,R),
 ("soil_erosion_t_ha_yr","float","t/ha/año","Erosión del suelo","GloSEM (JRC ESDAC)","-",A,F,R),
 ("volcanic_ashfall_hazard","float","0-5","Peligro de caída de ceniza volcánica","GAR / GVP","JMA",A,F,R),
 # --- Clima espacial ---
 ("geomagnetic_latitude_deg","float","grados","Latitud geomagnética: riesgo de corrientes inducidas por tormentas solares en la red","Modelo IGRF (calculado)","-",A,F,D),
 ("ground_conductivity_class","category","-","Conductividad del terreno (amplifica corrientes inducidas)","Mapas geofísicos nacionales","BGS, USGS",A,F,PX),
 # --- Historial de pérdidas y seguros ---
 ("disaster_events_admin1_20y","int","número","Desastres naturales registrados en la región en 20 años","EM-DAT (CRED, registro gratuito)","-",M,F,R),
 ("disaster_losses_pct_gdp","float","% PIB","Pérdidas medias anuales por desastres","EM-DAT, UNDRR","-",A,F,R,"country_context"),
 ("insurance_protection_gap_pct","float","%","Parte de las pérdidas no aseguradas","Swiss Re sigma (público)","-",A,F,R,"country_context"),
 ("national_cat_insurance_scheme","category","-","Sistema público de cobertura de catástrofes","-","Consorcio de Compensación de Seguros (ESP), Flood Re (GBR), JER (JPN), NFIP (USA)",A,F,R,"country_context"),
 ("inform_risk_index","float","0-10","Índice de riesgo de desastres y crisis por país","INFORM Risk (JRC)","-",A,F,R,"country_context"),
 ("climate_physical_risk_2050","float","0-100","Riesgo físico climático compuesto en 2050","Derivado (inundación, calor, ciclón, incendio, sequía)","-",A,F,D),
]))

B.append(("04 Agua", "sites", [
 ("water_stress","float","0-5","Estrés hídrico de referencia","WRI Aqueduct 4.0","-",M,F,R),
 ("water_depletion","float","0-5","Agotamiento de recursos hídricos","WRI Aqueduct","-",A,F,R),
 ("interannual_variability","float","0-5","Variabilidad entre años","WRI Aqueduct","-",A,F,R),
 ("seasonal_variability","float","0-5","Variabilidad estacional","WRI Aqueduct","-",A,F,R),
 ("groundwater_decline","float","0-5","Descenso de acuíferos","WRI Aqueduct, GRACE","-",A,F,R),
 ("drought_risk","float","0-5","Riesgo de sequía","WRI Aqueduct","-",M,F,R),
 ("water_stress_2030","float","0-5","Estrés hídrico proyectado 2030","WRI Aqueduct (proyecciones)","-",A,F,R),
 ("water_stress_2050","float","0-5","Estrés hídrico proyectado 2050","WRI Aqueduct (proyecciones)","-",M,F,R),
 ("nearest_river_discharge_m3s","float","m³/s","Caudal medio del río más cercano","HydroRIVERS, GloFAS","SAIH/CHE (ESP), USGS NWIS",A,F,R),
 ("dist_reservoir_km","float","km","Distancia a embalse","GRanD, GDW","MITECO (ESP)",A,F,R),
 ("dist_wwtp_km","float","km","Distancia a depuradora (agua regenerada para refrigeración)","HydroWASTE","EEA UWWTD (ESP/GBR)",M,F,R),
 ("wwtp_capacity_pe","float","hab-eq","Capacidad de esa depuradora","HydroWASTE","-",A,F,R),
 ("aquifer_productivity","category","-","Productividad del acuífero subyacente","WHYMAP (BGR)","IGME, BGS",A,F,R),
 ("water_price_industrial_usd_m3","float","USD/m³","Tarifa industrial del agua","GWI / IBNET (parcial)","Tarifas municipales",A,F,PX),
 ("water_restriction_flag","bool","0/1","Restricciones de uso por sequía vigentes o recientes","-","Planes de sequía de cuenca",A,F,PX),
]))

B.append(("05 Clima y refrigeración", "sites", [
 ("koppen_class","category","-","Clase climática Köppen-Geiger","Beck et al. (GloH2O)","-",M,F,R),
 ("mean_temp_c","float","°C","Temperatura media anual","ERA5-Land, WorldClim, CHELSA","AEMET, NOAA, Met Office, BoM, JMA, IMD",M,F,R),
 ("max_temp_p99_c","float","°C","Percentil 99 de temperatura máxima (diseño de refrigeración)","ERA5-Land","-",M,F,R),
 ("min_temp_p01_c","float","°C","Percentil 1 de temperatura mínima","ERA5-Land","-",A,F,R),
 ("diurnal_range_c","float","°C","Oscilación térmica diaria media","ERA5-Land, WorldClim","-",A,F,R),
 ("cooling_degree_days","float","°C·día","Grados-día de refrigeración (base 18 °C)","ERA5 / Copernicus CDS","-",M,F,D),
 ("heating_degree_days","float","°C·día","Grados-día de calefacción (potencial de reutilizar calor residual)","ERA5","-",A,F,D),
 ("wetbulb_p99_c","float","°C","Temperatura de bulbo húmedo percentil 99","ERA5 (calculado)","ASHRAE climatic design (comercial)",M,F,D),
 ("dewpoint_mean_c","float","°C","Punto de rocío medio","ERA5","-",A,F,R),
 ("rel_humidity_mean_pct","float","%","Humedad relativa media","ERA5","-",M,F,R),
 ("free_cooling_hours","float","h/año","Horas con aire exterior suficiente para enfriar (bulbo seco <18 °C)","ERA5 horario (calculado)","-",M,F,D),
 ("adiabatic_cooling_hours","float","h/año","Horas aptas para enfriamiento evaporativo","ERA5 horario (calculado)","-",A,F,D),
 ("est_pue","float","adimensional","PUE estimado según el clima","Modelo propio","-",M,F,D),
 ("est_wue_l_kwh","float","L/kWh","Consumo de agua estimado por kWh (WUE)","Modelo propio","-",A,F,D),
 ("heatwave_days_year","float","días/año","Días con máxima >35 °C","ERA5-Land","-",M,F,D),
 ("tropical_nights_year","float","noches/año","Noches con mínima >20 °C","ERA5-Land","-",A,F,D),
 ("frost_days_year","float","días/año","Días con helada","ERA5-Land","-",A,F,D),
 ("annual_precip_mm","float","mm","Precipitación anual","ERA5-Land, CHELSA, CHIRPS","-",M,F,R),
 ("max_daily_precip_p99_mm","float","mm","Precipitación diaria extrema (drenaje)","ERA5-Land, CHIRPS","-",A,F,R),
 ("fog_days_year","float","días/año","Días de niebla","ERA5 (visibilidad, proxy)","Servicios meteorológicos nacionales",A,F,PX),
 ("wind_speed_mean_ms","float","m/s","Velocidad media del viento a 10 m","ERA5, Global Wind Atlas","-",M,F,R),
 ("extreme_gust_ms","float","m/s","Racha máxima con retorno 50 años","ERA5 (calculado)","Eurocódigo EN 1991-1-4 anexos nacionales",A,F,D),
 ("lightning_density","float","rayos/km²/año","Densidad de rayos","NASA LIS/OTD climatology","Redes nacionales de rayos",M,F,R),
 ("hail_days_year","float","días/año","Días de granizo","ERA5 (proxy convectivo)","ESSL / ESWD (Europa)",A,F,PX),
 ("snow_load_kn_m2","float","kN/m²","Carga de nieve característica","ERA5 (equivalente de agua)","Eurocódigo EN 1991-1-3, ASCE 7 (USA)",A,F,PX),
 ("solar_ghi_kwh_m2","float","kWh/m²/año","Irradiancia global horizontal","Global Solar Atlas","-",M,F,R),
 ("dust_aod","float","adimensional","Profundidad óptica de aerosoles de polvo (filtros)","CAMS (Copernicus)","-",A,F,R),
 ("pm25_ug_m3","float","µg/m³","Concentración media de PM2.5","CAMS, van Donkelaar (ACAG)","-",A,F,R),
 ("so2_ug_m3","float","µg/m³","SO2 (corrosión de electrónica, norma ISA G1-G3)","CAMS","-",A,F,R),
 ("temp_change_2050_ssp245_c","float","°C","Aumento de temperatura 2050, escenario SSP2-4.5","CMIP6 vía Copernicus CDS, WorldClim futuro","-",M,F,R),
 ("temp_change_2050_ssp585_c","float","°C","Aumento de temperatura 2050, escenario SSP5-8.5","CMIP6","-",A,F,R),
 ("cdd_2050_ssp245","float","°C·día","Grados-día de refrigeración en 2050","CMIP6 (calculado)","-",A,F,D),
 ("heatwave_days_2050_ssp245","float","días/año","Días >35 °C en 2050","CMIP6 (calculado)","-",M,F,D),
 ("wetbulb_p99_2050_c","float","°C","Bulbo húmedo extremo en 2050","CMIP6 (calculado)","-",A,F,D),
 ("precip_change_2050_pct","float","%","Cambio de precipitación en 2050","CMIP6","-",A,F,R),
 ("sea_level_rise_2050_cm","float","cm","Subida del nivel del mar en la costa más cercana","NASA Sea Level Projection Tool (IPCC AR6)","-",A,F,R),
]))

B.append(("06 Conectividad", "sites", [
 ("dist_ixp_km","float","km","Distancia al punto neutro de intercambio (IXP) más cercano","PeeringDB (API), PCH IXP directory","-",M,F,R),
 ("n_ixp_100km","int","número","IXPs en 100 km","PeeringDB","-",A,F,R),
 ("n_networks_at_ixp","int","número","Redes conectadas al IXP más cercano","PeeringDB","-",A,F,R),
 ("n_colo_facilities_100km","int","número","Instalaciones de colocation en 100 km","PeeringDB facilities","-",A,F,R),
 ("dist_major_hub_km","float","km","Distancia a gran hub (Madrid, Londres, Tokio, Ashburn, Mumbai…)","Definido por el equipo","-",M,F,D),
 ("latency_to_hub_ms","float","ms","Latencia estimada al hub (fibra ~5 µs/km)","Calculado","RIPE Atlas (medidas reales)",M,F,D),
 ("dist_cable_landing_km","float","km","Distancia a estación de amarre de cable submarino","TeleGeography Submarine Cable Map (datos abiertos)","-",M,F,R),
 ("n_submarine_cables_country","int","número","Cables submarinos que llegan al país","TeleGeography","-",A,F,R),
 ("dist_cloud_region_km","float","km","Distancia a región cloud (AWS, Azure, GCP)","Documentación pública de los proveedores","-",A,F,R),
 ("dist_fiber_backbone_km","float","km","Distancia a troncal de fibra","OSM telecom (escaso)","Operadores nacionales",A,F,PX),
 ("fixed_broadband_mbps","float","Mbps","Velocidad fija media en la zona","Ookla Open Data","-",A,F,R),
 ("intl_bandwidth_country_tbps","float","Tbps","Ancho de banda internacional del país","ITU","-",A,F,R),
 # --- Fibra terrestre ---
 ("dist_long_haul_route_km","float","km","Distancia a ruta de fibra de larga distancia","ITU Interactive Transmission Map","Operadores mayoristas",M,F,R),
 ("n_fiber_routes_20km","int","número","Rutas de fibra distintas en 20 km (diversidad de caminos)","ITU Transmission Map, OSM","-",A,F,PX),
 ("dist_metro_ring_km","float","km","Distancia a anillo metropolitano de fibra","-","Operadores mayoristas",A,F,PX),
 ("dark_fiber_available_flag","bool","0/1","Disponibilidad de fibra oscura","-","Adif, REE, operadores (ESP); Zayo, Lumen (USA)",A,F,PX),
 ("dist_infra_corridor_km","float","km","Distancia a corredor ferroviario o de autopista (por donde suele ir la fibra)","OSM","-",A,F,D),
 ("n_fiber_operators_10km","int","número","Operadores de fibra presentes en 10 km","-","Reguladores (CNMC en ESP, Ofcom en GBR, FCC en USA)",A,F,PX),
 # --- Ecosistema de red e interconexión ---
 ("n_networks_100km","int","número","Redes (ASN) presentes en colocations en 100 km","PeeringDB (netfac)","-",M,F,R),
 ("n_carriers_nearest_colo","int","número","Operadores presentes en la colocation más cercana","PeeringDB","-",A,F,R),
 ("ixp_peak_traffic_tbps","float","Tbps","Tráfico pico del IXP más cercano","PeeringDB, webs de los IXP","-",A,F,R),
 ("n_cdn_pops_100km","int","número","Puntos de presencia de CDN en 100 km","Listas públicas de Cloudflare, Akamai, Fastly","-",A,F,R),
 ("dist_cloud_onramp_km","float","km","Distancia a acceso directo a cloud (Direct Connect, ExpressRoute, Interconnect)","Documentación pública de AWS, Azure, Google","-",A,F,R),
 ("n_cloud_onramps_100km","int","número","Accesos directos a cloud en 100 km","Documentación de los proveedores","-",A,F,R),
 ("n_cloud_regions_country","int","número","Regiones cloud de hiperescalares en el país","Documentación de los proveedores","-",A,F,R,"country_context"),
 ("n_planned_cloud_regions_country","int","número","Regiones cloud anunciadas","Anuncios de los proveedores","-",A,F,R,"country_context"),
 # --- Cables submarinos ---
 ("n_cables_nearest_landing","int","número","Cables que llegan a la estación de amarre más cercana","TeleGeography Submarine Cable Map","-",M,F,R),
 ("landing_design_capacity_tbps","float","Tbps","Capacidad de diseño de esos cables","TeleGeography, informes de los consorcios","-",A,F,PX),
 ("newest_cable_year","int","año","Año del cable más reciente en ese amarre","TeleGeography","-",A,F,R),
 ("planned_cables_flag","bool","0/1","Cables nuevos anunciados en esa costa","TeleGeography","-",A,F,R),
 ("chokepoint_exposure","float","0-5","Dependencia de rutas críticas (mar Rojo, Malaca, Luzón) con riesgo de cortes","TeleGeography (calculado)","-",A,F,D),
 # --- Latencia y calidad ---
 ("latency_measured_hub_ms","float","ms","Latencia medida al hub más cercano","RIPE Atlas","-",A,F,R),
 ("latency_frankfurt_ms","float","ms","Latencia estimada a Fráncfort","RIPE Atlas, cálculo por distancia","-",A,F,D),
 ("latency_ashburn_ms","float","ms","Latencia estimada a Ashburn (Virginia)","RIPE Atlas, cálculo por distancia","-",A,F,D),
 ("latency_singapore_ms","float","ms","Latencia estimada a Singapur","RIPE Atlas, cálculo por distancia","-",A,F,D),
 ("latency_tokyo_ms","float","ms","Latencia estimada a Tokio","RIPE Atlas, cálculo por distancia","-",A,F,D),
 ("pop_within_10ms_millions","float","millones","Población alcanzable con menos de 10 ms (mercado de baja latencia)","WorldPop + modelo de latencia","-",M,F,D),
 ("packet_loss_pct","float","%","Pérdida de paquetes media","M-Lab (Measurement Lab)","-",A,F,R),
 ("jitter_ms","float","ms","Variación de latencia","M-Lab, Ookla Open Data","-",A,F,R),
 # --- Respaldo ---
 ("mobile_5g_coverage_flag","bool","0/1","Cobertura 5G en la parcela","Ookla, nPerf, GSMA coverage maps","Reguladores nacionales",A,F,R),
 ("n_mobile_operators","int","número","Operadores móviles con cobertura","GSMA, OpenCelliD","-",A,F,R),
 ("satellite_backup_available","bool","0/1","Servicio satelital de respaldo disponible en el país","Webs de los operadores","-",A,F,R,"country_context"),
 # --- Mercado e indicadores de país ---
 ("internet_resilience_index","float","0-100","Resiliencia de internet del país","Internet Society Pulse (IRI)","-",M,F,R,"country_context"),
 ("ipv6_adoption_pct","float","%","Adopción de IPv6","APNIC, Google IPv6 statistics","-",A,F,R,"country_context"),
 ("n_asns_country","int","número","Sistemas autónomos registrados en el país","RIR (RIPE, ARIN, APNIC), PeeringDB","-",A,F,R,"country_context"),
 ("ixp_density_per_10m","float","IXP/10 M hab","IXPs por cada 10 millones de habitantes","PeeringDB, PCH","-",A,F,D,"country_context"),
 ("ip_transit_price_usd_mbps","float","USD/Mbps/mes","Precio del tránsito IP","TeleGeography (parcialmente comercial)","-",A,F,PX,"country_context"),
 ("telecom_market_hhi","float","0-10.000","Concentración del mercado de telecomunicaciones","Reguladores, ITU","-",A,F,PX,"country_context"),
 ("broadband_affordability_pct","float","% ingreso","Coste de la banda ancha sobre la renta","ITU, A4AI","-",A,F,R,"country_context"),
]))

B.append(("07 Suelo y economía", "sites", [
 ("land_price_usd_m2","float","USD/m²","Precio del suelo industrial o rústico","Portales inmobiliarios (scraping con ToS)","MITMA valor del suelo (ESP), USDA land values (USA), MLIT 地価公示 (JPN), HM Land Registry (GBR), Valuer General (AUS), NAPIC (MYS)",M,F,PX),
 ("land_price_trend_5y_pct","float","%","Variación del precio del suelo en 5 años","Índices nacionales","INE (ESP), FHFA (USA), RBI (IND)",A,F,R),
 ("zoning_class","category","-","Calificación urbanística (industrial, rústico…)","OSM landuse","Planeamiento municipal, SIU (ESP)",M,F,R),
 ("industrial_land_20km_ha","float","ha","Suelo industrial disponible en 20 km","OSM landuse=industrial","-",A,F,R),
 ("land_cover_class","category","-","Cobertura del suelo","ESA WorldCover 10 m","CORINE (ESP, GBR)",M,F,R),
 ("construction_cost_index","float","índice","Coste de construcción de data centers por país","Turner & Townsend Data Centre Cost Index (informe público)","-",M,F,R),
 ("labor_cost_hourly_usd","float","USD/h","Coste laboral medio","ILOSTAT, OCDE","-",A,F,R),
 ("tech_workforce_index","float","índice","Disponibilidad de técnicos e ingenieros","ILOSTAT, OCDE","Estadísticas regionales",A,F,PX),
 ("unemployment_rate_pct","float","%","Tasa de paro regional","OCDE regional, ILOSTAT","INE, BLS, ONS",A,F,R),
 ("gdp_per_capita_ppp","float","USD PPA","PIB per cápita regional","OCDE regional, World Bank","-",A,F,R),
 ("corporate_tax_pct","float","%","Impuesto de sociedades","Tax Foundation, KPMG tax rates","-",M,F,R),
 ("property_tax_pct","float","%","Impuesto sobre la propiedad","-","Ordenanzas locales",A,F,PX),
 ("dc_tax_incentive_flag","bool","0/1","Incentivos fiscales específicos a data centers","-","Leyes estatales (USA), PIGA (Aragón), MDEC (MYS)",M,F,R),
 ("interest_rate_pct","float","%","Tipo de interés de referencia (coste de capital)","IMF IFS, bancos centrales","-",A,F,R),
 ("inflation_pct","float","%","Inflación","IMF WEO, World Bank","-",A,F,R),
 ("country_risk_premium_pct","float","%","Prima de riesgo país","Damodaran (NYU, público)","-",M,F,R),
 ("sovereign_rating","category","-","Rating soberano","Agencias de rating (públicos)","-",A,F,R),
 ("fx_volatility","float","desv. típica","Volatilidad de la divisa frente al USD","IMF, BIS","-",A,F,D),
 ("ppp_factor","float","ratio","Factor de conversión por paridad de poder adquisitivo","World Bank ICP","-",M,C,R),
]))

B.append(("08 Accesos y entorno", "sites", [
 ("dist_highway_km","float","km","Distancia a autopista o autovía","OSM highway=motorway","-",M,F,R),
 ("dist_primary_road_km","float","km","Distancia a carretera principal","OSM","-",A,F,R),
 ("dist_airport_km","float","km","Distancia a aeropuerto comercial","OurAirports","-",A,F,R),
 ("dist_port_km","float","km","Distancia a puerto (logística de equipos)","World Port Index (NGA)","-",A,F,R),
 ("dist_city_100k_km","float","km","Distancia a ciudad de más de 100.000 habitantes","GHSL Urban Centres, GeoNames","-",M,F,R),
 ("dist_city_1m_km","float","km","Distancia a ciudad de más de 1 millón","GHSL","-",A,F,R),
 ("population_10km","int","habitantes","Población en 10 km","WorldPop, GHSL","-",A,F,R),
 ("population_50km","int","habitantes","Población en 50 km (mano de obra y demanda)","WorldPop, GHSL","-",M,F,R),
 ("built_up_pct_5km","float","%","Superficie construida en 5 km","GHSL","-",A,F,R),
 ("nightlights_radiance","float","nW/cm²/sr","Luz nocturna (actividad económica)","VIIRS (NASA Black Marble)","-",A,F,R),
 ("dist_hazardous_industry_km","float","km","Distancia a industria peligrosa (Seveso, química)","OSM, E-PRTR","Registros Seveso nacionales",A,F,R),
 ("dist_military_km","float","km","Distancia a instalación militar","OSM landuse=military","-",A,F,R),
 ("dist_fire_station_km","float","km","Distancia a parque de bomberos","OSM amenity=fire_station","-",A,F,R),
]))

B.append(("08b Tráfico, tráfico aéreo y viviendas", "sites", [
 ("aadt_nearest_road","float","vehículos/día","Intensidad media diaria de tráfico en la carretera principal más cercana","OSM (solo clase de vía, como proxy)","Mapa de tráfico del Ministerio de Transportes (ESP), FHWA HPMS (USA), DfT road traffic counts (GBR), MLIT road traffic census (JPN), datos estatales (AUS)",M,F,R),
 ("heavy_vehicle_pct","float","%","Porcentaje de vehículos pesados (más vibración)","-","Mismas fuentes de aforos nacionales",A,F,R),
 ("road_density_km_km2","float","km/km²","Densidad de carreteras en 2 km","OSM","-",M,F,D),
 ("dist_motorway_junction_km","float","km","Distancia al enlace de autopista más cercano (acceso de camiones)","OSM motorway_junction","-",A,F,R),
 ("road_noise_lden_db","float","dB","Ruido de tráfico rodado (indicador día-tarde-noche)","EEA Noise (solo Europa)","Mapas estratégicos de ruido (ESP), Defra noise maps (GBR), BTS National Transportation Noise Map (USA)",A,F,R),
 ("rail_trains_day","float","trenes/día","Circulaciones diarias en la vía férrea más cercana","OSM (proxy por tipo de línea)","Adif (ESP), Network Rail (GBR), FRA (USA)",A,F,PX),
 ("dist_freight_rail_km","float","km","Distancia a línea de mercancías (vibración de baja frecuencia)","OSM railway usage=freight","-",A,F,R),
 ("dist_airport_runway_km","float","km","Distancia a la pista del aeropuerto más cercano","OurAirports (pistas)","AIP nacionales",M,F,R),
 ("airport_annual_movements","float","operaciones/año","Operaciones anuales de ese aeropuerto","OpenSky Network (cálculo propio)","AENA (ESP), FAA ATADS (USA), CAA (GBR), MLIT (JPN), BITRE (AUS), AAI (IND)",M,F,R),
 ("overflights_per_day","float","vuelos/día","Sobrevuelos diarios por debajo de 3.000 m en 5 km","OpenSky Network (acceso de investigación), ADS-B Exchange","-",A,F,D),
 ("in_flight_path_flag","bool","0/1","Bajo cono de aproximación o despegue (riesgo de impacto y límites de altura)","OurAirports + geometría de pistas","AIP nacionales",M,F,D),
 ("in_aero_easement_flag","bool","0/1","Dentro de servidumbres aeronáuticas","-","AESA/ENAIRE (ESP), FAA Part 77 (USA), CAA safeguarding (GBR)",M,F,R),
 ("max_building_height_m","float","m","Altura máxima permitida por servidumbres","-","ENAIRE (ESP), FAA (USA)",A,F,R),
 ("aircraft_noise_lden_db","float","dB","Ruido aeronáutico","EEA Noise (aeropuertos grandes, Europa)","Huellas de ruido de AENA, FAA",A,F,R),
 ("dist_heliport_km","float","km","Distancia a helipuerto","OurAirports, OSM aeroway=helipad","-",A,F,R),
 ("dist_military_airbase_km","float","km","Distancia a base aérea militar","OSM military=airfield, OurAirports","-",A,F,R),
 ("in_drone_restricted_zone","bool","0/1","Zona restringida a drones (seguridad e inspecciones)","-","ENAIRE Drones (ESP), FAA UAS Facility Maps (USA)",A,F,R),
 ("dist_residential_km","float","km","Distancia a la zona residencial más cercana","OSM landuse=residential, GHSL","Planeamiento municipal",M,F,R),
 ("dist_nearest_dwelling_m","float","m","Distancia a la vivienda más cercana (ruido de refrigeración y generadores)","Microsoft Global Building Footprints, Google Open Buildings, OSM building","Catastro (ESP), OS MasterMap (GBR, parcial)",M,F,R),
 ("n_buildings_1km","int","número","Edificios en 1 km","Microsoft / Google building footprints","Catastro (ESP)",A,F,R),
 ("n_dwellings_1km","int","número","Viviendas en 1 km","GHSL (uso residencial), OSM","Catastro (ESP), Census Bureau (USA), ONS (GBR)",M,F,R),
 ("housing_density_km2","float","viviendas/km²","Densidad de viviendas en 2 km","GHSL, WorldPop","Censos nacionales",A,F,R),
 ("population_1km","int","habitantes","Población en 1 km","WorldPop, GHSL","-",A,F,R),
 ("n_sensitive_receptors_2km","int","número","Colegios, hospitales y residencias en 2 km","OSM amenity=school/hospital/nursing_home","-",A,F,R),
 ("planned_residential_flag","bool","0/1","Suelo residencial planificado cerca (conflicto futuro)","-","Planeamiento municipal, SIU (ESP)",A,F,PX),
 ("housing_pressure_index","float","índice","Tensión de vivienda en la zona (riesgo de oposición vecinal)","-","INE (ESP), ONS (GBR), Zillow (USA)",A,F,PX),
]))

B.append(("09 Regulación y ESG", "sites", [
 ("permitting_months","float","meses","Plazo típico de licencias y permisos","Informes sectoriales","Expedientes públicos",M,F,PX),
 ("eia_required_flag","bool","0/1","Exige evaluación de impacto ambiental completa","-","Ley 21/2013 (ESP), NEPA (USA), EPBC (AUS)",A,F,R),
 ("moratorium_flag","bool","0/1","Moratoria o restricción a nuevos data centers","Prensa, normativa","Normativa local",M,F,R),
 ("pue_cap_regulation","float","PUE","Límite legal de PUE para nuevos data centers","-","Normativa china (PUE máx. en zonas clave), Alemania (EnEfG)",A,F,R),
 ("heat_reuse_mandate_flag","bool","0/1","Obligación de reutilizar calor residual","Directiva UE de eficiencia energética","-",A,F,R),
 ("data_sovereignty_flag","bool","0/1","Ley de localización de datos","-","PIPL (CHN), DPDP (IND)",A,F,R),
 ("carbon_price_usd_t","float","USD/tCO2","Precio del carbono aplicable","World Bank Carbon Pricing Dashboard","EU ETS, UK ETS",A,F,R),
 ("renewable_target_pct","float","%","Objetivo renovable nacional","IRENA, IEA","PNIEC (ESP)",A,F,R),
 ("noise_limit_night_db","float","dB(A)","Límite de ruido nocturno aplicable","-","Normativa municipal",A,F,PX),
 ("dist_unesco_site_km","float","km","Distancia a Patrimonio Mundial","UNESCO World Heritage List","-",A,F,R),
 ("dist_heritage_site_km","float","km","Distancia a bien cultural o yacimiento protegido","OSM historic=*","Inventarios nacionales de patrimonio",A,F,R),
 ("indigenous_land_flag","bool","0/1","Tierras con derechos indígenas","LandMark","NNTT (AUS), JKOA (MYS)",A,F,R),
 ("local_opposition_index","float","índice","Cobertura mediática negativa sobre data centers en la zona","GDELT","Prensa local",A,F,PX),
]))

B.append(("10 Biodiversidad", "sites", [
 ("in_protected_area","bool","0/1","Dentro de espacio protegido","Protected Planet (WDPA)","Red Natura 2000 (ESP), PAD-US (USA), JNCC (GBR), CAPAD (AUS)",M,F,R),
 ("dist_protected_area_km","float","km","Distancia a espacio protegido","WDPA","-",M,F,R),
 ("protected_area_iucn_cat","category","Ia-VI","Categoría UICN del espacio más cercano","WDPA","-",A,F,R),
 ("dist_natura2000_km","float","km","Distancia a Red Natura 2000 (solo ESP)","EEA Natura 2000","MITECO",A,F,R),
 ("in_kba","bool","0/1","Dentro de Área Clave de Biodiversidad","KBA (requiere solicitud), IBAT","-",M,F,R),
 ("in_iba","bool","0/1","Dentro de Área Importante para las Aves","BirdLife DataZone","SEO/BirdLife (ESP)",A,F,R),
 ("dist_ramsar_km","float","km","Distancia a humedal Ramsar","Ramsar Sites Information Service","-",A,F,R),
 ("dist_critical_habitat_km","float","km","Distancia a hábitat crítico designado","-","USFWS ECOS (USA), EPBC (AUS)",A,F,R),
 ("n_threatened_species_10km","int","número","Especies amenazadas (VU, EN, CR) cuyo rango cubre la zona","IUCN Red List spatial data (licencia NC)","Catálogo Español de Especies Amenazadas, Lista Roja de Japón",M,F,R),
 ("n_cr_en_species_10km","int","número","Especies en peligro crítico o en peligro","IUCN Red List","-",M,F,R),
 ("n_threatened_mammals","int","número","Mamíferos amenazados","IUCN Red List","-",A,F,R),
 ("n_threatened_birds","int","número","Aves amenazadas","BirdLife / IUCN","-",A,F,R),
 ("n_threatened_amphibians_reptiles","int","número","Anfibios y reptiles amenazados","IUCN Red List","-",A,F,R),
 ("n_threatened_plants","int","número","Plantas amenazadas","IUCN Red List, BGCI","Inventarios nacionales de flora",A,F,R),
 ("n_endemic_species","int","número","Especies endémicas","IUCN Red List (rango restringido)","-",A,F,R),
 ("species_richness","int","número","Riqueza total de especies","IUCN, BiodiversityMapping.org","-",A,F,R),
 ("range_rarity","float","índice","Rareza de rango (especies con distribución pequeña)","BiodiversityMapping.org","-",A,F,R),
 ("star_threat_score","float","índice","Métrica STAR de reducción de amenazas","IBAT (UICN)","-",A,F,R),
 ("biodiversity_intactness","float","0-1","Índice de intactitud de la biodiversidad (BII)","Natural History Museum (BII)","-",A,F,R),
 ("n_gbif_threatened_occ_5km","int","número","Avistamientos de especies amenazadas en 5 km (sesgo de muestreo)","GBIF (API)","-",A,F,R),
 ("habitat_type","category","-","Tipo de hábitat según clasificación UICN","Jung et al. habitat map","-",A,F,R),
 ("forest_cover_pct_1km","float","%","Cobertura forestal en 1 km","Hansen Global Forest Change","-",A,F,R),
 ("tree_cover_loss_10y_pct","float","%","Pérdida de cubierta arbórea en 10 años","Hansen GFC, Global Forest Watch","-",A,F,R),
 ("ndvi_mean","float","-1 a 1","Índice de vegetación medio","Sentinel-2, MODIS","-",A,F,R),
 ("migration_route_flag","bool","0/1","En ruta migratoria de aves","BirdLife (flyways)","-",A,F,R),
 ("biodiversity_sensitivity","float","0-100","Índice compuesto de sensibilidad ecológica","Derivado","-",M,F,D),
]))

B.append(("11 Señal sísmica", "signal_features", [
 ("record_id","string","-","Identificador del registro analizado","-","-",M,K,D),
 ("station_id","string","NET.STA","Red y estación","FDSN","-",M,K,R),
 ("channel_codes","string","SEED","Canales usados (p. ej. HHZ, HHN, HHE)","FDSN","-",M,C,R),
 ("sampling_rate_hz","float","Hz","Frecuencia de muestreo","FDSN","-",M,C,R),
 ("sensor_type","category","-","Banda ancha, corto periodo o acelerómetro","FDSN StationXML","-",A,F,R),
 ("station_on_rock_flag","bool","0/1","Estación instalada sobre roca (sesga el H/V)","Metadatos de red, litología","-",M,C,PX),
 ("record_start_utc","datetime","UTC","Inicio del registro","-","-",M,C,R),
 ("record_hours","float","h","Horas de ruido analizadas","-","-",M,C,R),
 ("n_windows_valid","int","número","Ventanas válidas tras eliminar transitorios","Calculado","-",M,C,D),
 ("data_completeness_pct","float","%","Porcentaje sin huecos","Calculado","-",M,C,D),
 ("hv_f0_hz","float","Hz","Frecuencia del pico H/V","Calculado (ObsPy, SciPy)","-",M,F,D),
 ("hv_a0","float","adimensional","Amplitud del pico H/V","Calculado","-",M,F,D),
 ("hv_f0_std","float","Hz","Desviación de f0 entre ventanas","Calculado","-",M,F,D),
 ("hv_sesame_reliable","bool","0/1","Cumple criterios de fiabilidad SESAME","Calculado","-",M,C,D),
 ("hv_sesame_clear_peak","bool","0/1","Cumple criterios de pico claro SESAME","Calculado","-",A,C,D),
 ("hv_second_peak_hz","float","Hz","Segundo pico (estructura de capas)","Calculado","-",A,F,D),
 ("hv_curve","array","vector","Curva H/V completa (p. ej. 100 bins log 0,2-20 Hz)","Calculado","-",A,F,D),
 ("psd_p50_db_0_1_1hz","float","dB","PSD mediana 0,1-1 Hz (microsismo oceánico)","Calculado (PPSD de ObsPy)","-",A,F,D),
 ("psd_p50_db_1_10hz","float","dB","PSD mediana 1-10 Hz (tráfico, maquinaria)","Calculado","-",M,F,D),
 ("psd_p50_db_10_30hz","float","dB","PSD mediana 10-30 Hz (fuentes cercanas, industria)","Calculado","-",M,F,D),
 ("psd_vs_nlnm_db","float","dB","Exceso sobre el modelo de ruido bajo de Peterson","Calculado","-",A,F,D),
 ("day_night_ratio","float","ratio","Relación de ruido día/noche (actividad humana)","Calculado","-",M,F,D),
 ("weekday_weekend_ratio","float","ratio","Relación laborable/fin de semana","Calculado","-",A,F,D),
 ("dominant_freq_hz","float","Hz","Frecuencia dominante del espectro","Calculado","-",A,F,D),
 ("spectral_centroid_hz","float","Hz","Centroide espectral","librosa","-",A,F,D),
 ("spectral_bandwidth_hz","float","Hz","Ancho de banda espectral","librosa","-",A,F,D),
 ("spectral_rolloff_hz","float","Hz","Frecuencia bajo la que está el 85% de la energía","librosa","-",A,F,D),
 ("rms_velocity","float","m/s","Valor eficaz de la velocidad","Calculado","-",A,F,D),
 ("kurtosis","float","adimensional","Curtosis (impulsividad, voladuras)","SciPy","-",A,F,D),
 ("n_transients_hour","float","eventos/h","Transitorios por hora (trenes, camiones)","Calculado (STA/LTA)","-",A,F,D),
 ("mfcc_1_13","array","vector","Coeficientes MFCC adaptados a baja frecuencia","librosa","-",A,F,D),
 ("audio_embedding","array","vector","Embedding de modelo de audio preentrenado (PANNs, YAMNet)","Modelo preentrenado","-",A,F,D),
 ("noise_source_class","category","-","Fuente de vibración dominante (tráfico, industria, natural)","Clasificador propio o reglas","-",A,L,D),
]))

B.append(("12 Estaciones", "stations", [
 ("station_id","string","NET.STA","Red y estación","FDSN","-",M,K,R),
 ("network_code","string","-","Código de red (ES, GB, AU, IU, II, BO…)","FDSN","-",M,C,R),
 ("lat","float","grados","Latitud","FDSN StationXML","-",M,K,R),
 ("lon","float","grados","Longitud","FDSN StationXML","-",M,K,R),
 ("elevation_m","float","m","Altitud del sensor","FDSN StationXML","-",A,F,R),
 ("depth_m","float","m","Profundidad del sensor (pozo, superficie)","FDSN StationXML","KiK-net tiene sensor en superficie y en pozo",A,F,R),
 ("datacenter_fdsn","string","-","Servidor FDSN que lo distribuye","EarthScope, GEOFON, ORFEUS, IGN, BGS, AusPass","NIED (registro)",M,C,R),
 ("operational_start","date","-","Fecha de alta","FDSN","-",A,C,R),
 ("vs30_measured","float","m/s","Vs30 medida en la estación (ETIQUETA)","USGS Vs30 compilation, CESMD","KiK-net/K-NET (JPN)",M,L,R),
 ("vs_profile_available","bool","0/1","Existe perfil de velocidades medido","-","KiK-net (JPN), CESMD (USA)",A,C,R),
 ("site_geology","category","-","Geología local de la estación","Metadatos de red, GLiM","-",A,F,R),
 # --- Identificación y acceso ---
 ("location_code","string","SEED","Código de ubicación (varios sensores en una estación)","FDSN","-",M,C,R),
 ("station_name","string","-","Nombre de la estación","FDSN StationXML","-",A,C,R),
 ("country_iso3","string","ISO 3166-1","País","Calculado","-",M,K,D),
 ("h3_cell_r7","string","H3 res. 7","Celda H3 para unir con capas","Calculado","-",M,K,D),
 ("operator_agency","string","-","Organismo que opera la estación","FDSN StationXML, EarthScope MDA","IGN, NIED, BGS, GA, NCS, MetMalaysia, USGS",A,C,R),
 ("network_type","category","-","Red permanente o temporal","FDSN, FDSN network registry","-",M,C,R),
 ("open_data_flag","bool","0/1","Formas de onda de acceso abierto","FDSN","-",M,C,R),
 ("data_license","string","-","Licencia de los datos (DOI de red)","FDSN network DOIs","-",A,C,R),
 ("operational_end","date","-","Fecha de baja (vacío si sigue activa)","FDSN","-",A,C,R),
 ("is_active","bool","0/1","Estación activa hoy","FDSN","-",M,C,D),
 # --- Instrumentación ---
 ("sensor_model","string","-","Modelo de sensor (STS-2, Trillium, CMG-3T…)","FDSN StationXML","-",A,F,R),
 ("digitizer_model","string","-","Modelo de digitalizador","FDSN StationXML","-",A,C,R),
 ("sensor_corner_period_s","float","s","Periodo de corte del sensor (limita las frecuencias bajas fiables)","FDSN StationXML (respuesta)","-",M,F,R),
 ("n_components","int","número","Componentes registradas (H/V necesita 3)","FDSN","-",M,C,R),
 ("has_broadband_flag","bool","0/1","Tiene sensor de banda ancha","FDSN (códigos de canal BH/HH)","-",A,F,R),
 ("has_accelerometer_flag","bool","0/1","Tiene acelerómetro (registros de terremotos fuertes)","FDSN (códigos de canal HN/BN)","-",A,F,R),
 ("max_sampling_rate_hz","float","Hz","Frecuencia de muestreo máxima disponible","FDSN","-",A,C,R),
 ("response_available_flag","bool","0/1","Respuesta instrumental completa en los metadatos","FDSN StationXML","-",M,C,R),
 ("installation_type","category","-","Tipo de instalación (bóveda, pozo, superficie, sótano de edificio)","Metadatos de red, ESM, NGA-West2","Fichas de estación (IGN, NIED)",M,F,PX),
 ("in_building_flag","bool","0/1","Instalada dentro de un edificio (la estructura altera el H/V)","Metadatos de red, ESM","-",M,C,PX),
 # --- Caracterización del sitio (etiquetas y validación) ---
 ("vs30_method","category","-","Método de medida de Vs30 (sondeo, MASW, SPAC, inferido)","NGA-West2 site database, ESM, USGS Vs30 compilation","KiK-net PS logging (JPN)",M,C,R),
 ("vs30_uncertainty_ms","float","m/s","Incertidumbre de la Vs30","NGA-West2, ESM","-",A,C,R),
 ("vs_profile_depth_m","float","m","Profundidad del perfil de velocidades medido","-","KiK-net (pozos de 100-200 m)",A,C,R),
 ("f0_published_hz","float","Hz","Frecuencia fundamental publicada para la estación (validación del H/V propio)","NGA-West2, ESM","Estudios de sitio nacionales",M,L,R),
 ("kappa0_s","float","s","Atenuación del sitio a altas frecuencias","NGA-West2, ESM","-",A,F,R),
 ("site_class_measured","category","A-E","Clase de suelo medida","NGA-West2, ESM","-",M,L,R),
 ("site_class_source","string","-","Norma de la clase (Eurocódigo 8, NEHRP, japonesa)","-","-",A,C,R),
 ("empirical_amplification","float","ratio","Amplificación del sitio medida con terremotos reales","ESM, NGA-West2 (residuos de sitio)","KiK-net (cociente superficie/pozo)",A,L,R),
 ("n_strong_motion_records","int","número","Terremotos registrados con movimiento fuerte","ESM, CESMD, K-NET/KiK-net","-",A,C,R),
 ("geology_unit_detailed","string","-","Unidad geológica detallada bajo la estación","Mapas geológicos nacionales","IGME, BGS, USGS, GSJ",A,F,R),
 ("slope_station_pct","float","%","Pendiente del terreno en la estación (efectos topográficos)","Copernicus DEM","-",A,F,D),
 # --- Entorno de ruido ---
 ("dist_station_road_m","float","m","Distancia de la estación a la carretera más cercana","OSM","-",A,F,D),
 ("dist_station_coast_km","float","km","Distancia a la costa (microsismo oceánico)","Natural Earth","-",A,F,D),
 ("urban_rural_class","category","Urbano/Periurbano/Rural","Entorno de la estación","GHSL Degree of Urbanisation","-",M,F,R),
 # --- Calidad y disponibilidad de datos ---
 ("availability_pct_last_year","float","%","Datos disponibles en el último año","FDSN availability web service","-",M,C,R),
 ("n_gaps_last_month","int","número","Huecos en el último mes","FDSN availability","-",A,C,R),
 ("median_psd_vs_nlnm_db","float","dB","Ruido mediano sobre el modelo de Peterson (calidad del emplazamiento)","EarthScope MUSTANG, cálculo propio","-",A,F,D),
 ("noise_seasonal_range_db","float","dB","Variación estacional del ruido","Cálculo propio (PPSD)","-",A,F,D),
 ("timing_quality_pct","float","%","Calidad del reloj (GPS)","EarthScope MUSTANG","-",A,C,R),
 ("metadata_issues_flag","bool","0/1","Problemas conocidos de metadatos (orientación, ganancia)","EarthScope MUSTANG, avisos de la red","-",A,C,R),
 ("n_days_downloaded","int","días","Días de forma de onda descargados al data lake","Pipeline propio","-",M,C,D),
 # --- Uso en el proyecto ---
 ("dist_nearest_other_station_km","float","km","Distancia a la siguiente estación (densidad de la red)","Calculado","-",A,F,D),
 ("n_sites_assigned","int","número","Emplazamientos que usan esta estación","Calculado","-",A,C,D),
 ("is_label_station","bool","0/1","Tiene Vs30 o f0 medidos y sirve para entrenar","Calculado","-",M,C,D),
 ("spatial_cv_fold","int","número","Pliegue de validación cruzada espacial (evita fuga entre estaciones cercanas)","Calculado","-",M,C,D),
 ("data_split","category","train/val/test","Partición asignada","Calculado","-",M,C,D),
]))

B.append(("13 Contexto país", "country_context", [
 ("country_iso3","string","ISO 3166-1","País","-","-",M,K,R),
 ("dc_market_size_mw","float","MW","Capacidad total de data centers instalada","Informes públicos de consultoras (CBRE, JLL), IEA","-",A,F,PX),
 ("dc_pipeline_mw","float","MW","Capacidad en construcción o planificada","Informes públicos, prensa","-",A,F,PX),
 ("dc_electricity_share_pct","float","%","Peso de los data centers en el consumo eléctrico","IEA (Energy and AI)","EirGrid, EIA",A,F,R),
 ("internet_users_pct","float","%","Usuarios de internet","ITU, World Bank","-",A,F,R),
 ("cloud_adoption_index","float","índice","Adopción cloud empresarial","Eurostat, OCDE","-",A,F,PX),
 ("seismic_code","string","-","Norma sísmica vigente","-","NCSE-02/EC8, ASCE 7, IS 1893, GB 50011, AS 1170.4, BSL Japón",A,C,R),
 ("currency","string","ISO 4217","Moneda","-","-",M,C,R),
 ("usd_fx_rate","float","moneda/USD","Tipo de cambio de referencia","IMF, BCE","-",M,C,R),
 ("data_coverage_level","category","Alto/Medio/Bajo","Calidad de datos disponible en el país","Evaluación del equipo","-",M,C,D),
 # --- Gobernanza e instituciones ---
 ("political_stability_wgi","float","-2,5 a 2,5","Estabilidad política y ausencia de violencia","World Bank WGI","-",M,F,R),
 ("government_effectiveness_wgi","float","-2,5 a 2,5","Eficacia de la administración pública","World Bank WGI","-",M,F,R),
 ("regulatory_quality_wgi","float","-2,5 a 2,5","Calidad regulatoria","World Bank WGI","-",A,F,R),
 ("rule_of_law_wgi","float","-2,5 a 2,5","Estado de derecho","World Bank WGI","-",M,F,R),
 ("control_of_corruption_wgi","float","-2,5 a 2,5","Control de la corrupción","World Bank WGI","-",A,F,R),
 ("voice_accountability_wgi","float","-2,5 a 2,5","Participación ciudadana y rendición de cuentas","World Bank WGI","-",A,F,R),
 ("corruption_perceptions_index","float","0-100","Índice de percepción de la corrupción","Transparency International CPI","-",M,F,R),
 ("electoral_democracy_index","float","0-1","Índice de democracia electoral","V-Dem","-",A,F,R),
 ("government_system","category","-","Sistema de gobierno (presidencial, parlamentario, partido único…)","V-Dem, CIA World Factbook","-",A,F,R),
 ("state_structure","category","-","Estado federal, regional o unitario (quién concede los permisos)","Forum of Federations, Factbook","-",A,F,R),
 ("local_autonomy_index","float","índice","Autonomía de las administraciones locales","Local Autonomy Index (Comisión Europea, Ladner et al.)","-",A,F,R),
 ("legal_origin","category","-","Tradición jurídica (common law, civil law, mixto)","La Porta et al., JuriGlobe","-",A,F,R),
 ("property_rights_index","float","0-100","Protección de la propiedad","International Property Rights Index (PRA)","-",M,F,R),
 ("contract_enforcement_days","float","días","Tiempo para hacer cumplir un contrato en los tribunales","World Bank Doing Business (histórico) / B-READY","-",A,F,R),
 ("expropriation_risk","float","0-5","Riesgo de expropiación o cambios regulatorios retroactivos","Agencias de crédito a la exportación (OCDE country risk)","-",A,F,PX),
 # --- Política económica e industrial ---
 ("policy_uncertainty_index","float","índice","Incertidumbre de política económica","Economic Policy Uncertainty (Baker, Bloom, Davis)","-",M,F,R),
 ("election_within_2y_flag","bool","0/1","Elecciones generales en los próximos 2 años","IFES ElectionGuide","-",A,F,R),
 ("national_dc_ai_strategy_flag","bool","0/1","Estrategia nacional de IA o data centers con apoyo explícito","OECD.AI Policy Observatory","Planes nacionales",M,F,R),
 ("dc_policy_stance","category","Favorable/Neutral/Restrictiva","Postura del gobierno hacia nuevos data centers","Evaluación del equipo a partir de normativa y prensa","-",M,F,PX),
 ("fdi_screening_strictness","float","0-5","Control de inversiones extranjeras en infraestructura crítica","OECD FDI Regulatory Restrictiveness Index","-",M,F,R),
 ("foreign_ownership_limit_pct","float","%","Límite a la propiedad extranjera en telecomunicaciones o data centers","OECD FDI Index, UNCTAD Investment Policy Hub","-",A,F,R),
 ("chip_export_control_tier","category","-","Exposición a controles de exportación de chips avanzados","Normativa de EE. UU. (BIS) y equivalentes","-",M,F,R),
 ("sanctions_exposure_flag","bool","0/1","Sanciones internacionales que afectan a equipos o capital","OFAC, UE, ONU","-",A,F,R),
 ("trade_openness_pct","float","% PIB","Apertura comercial (importar equipos)","World Bank WDI","-",A,F,R),
 ("energy_policy_stability","float","0-100","Estabilidad de la política energética","WEC Energy Trilemma Index","-",A,F,R),
 ("nuclear_policy_stance","category","Expansión/Mantenimiento/Cierre","Política nuclear del país (energía firme a largo plazo)","IAEA, World Nuclear Association","-",A,F,R),
 # --- Riesgo geopolítico y seguridad ---
 ("geopolitical_risk_index","float","índice","Riesgo geopolítico por país","Geopolitical Risk Index (Caldara e Iacoviello)","-",M,F,R),
 ("fragile_states_index","float","0-120","Índice de fragilidad del Estado","Fund for Peace","-",A,F,R),
 ("global_peace_index","float","1-5","Índice de paz global","Institute for Economics and Peace","-",A,F,R),
 ("cybersecurity_index","float","0-100","Madurez en ciberseguridad","ITU Global Cybersecurity Index","-",M,F,R),
 ("internet_freedom_score","float","0-100","Libertad en internet (cortes, censura, bloqueos)","Freedom House, Freedom on the Net","-",A,F,R),
 ("internet_shutdowns_5y","int","número","Cortes de internet ordenados por el gobierno en 5 años","Access Now #KeepItOn","-",A,F,R),
 ("data_protection_regime","category","-","Régimen de protección de datos (GDPR, PIPL, DPDP, ninguno…)","UNCTAD Data Protection Legislation","-",M,F,R),
 ("gov_data_access_risk","float","0-5","Acceso del gobierno a datos alojados (leyes de vigilancia)","Evaluación del equipo a partir de normativa","-",A,F,PX),
 # --- Cultura y sociedad ---
 ("hofstede_power_distance","float","0-100","Distancia jerárquica (cómo se negocia con la administración)","Hofstede Insights","-",A,F,R),
 ("hofstede_uncertainty_avoidance","float","0-100","Aversión a la incertidumbre (exigencia de garantías y normas)","Hofstede Insights","-",A,F,R),
 ("hofstede_individualism","float","0-100","Individualismo frente a colectivismo","Hofstede Insights","-",A,F,R),
 ("hofstede_long_term_orientation","float","0-100","Orientación a largo plazo","Hofstede Insights","-",A,F,R),
 ("generalized_trust_pct","float","%","Confianza en los demás","World Values Survey","-",A,F,R),
 ("trust_in_government_pct","float","%","Confianza en el gobierno","OCDE Trust Survey, Gallup","-",A,F,R),
 ("environmental_concern_index","float","índice","Preocupación ciudadana por el medio ambiente","World Values Survey, Eurobarómetro (ESP)","-",A,F,R),
 ("dc_public_opposition_index","float","índice","Oposición social a data centers (protestas, campañas, prensa)","GDELT, Data Center Watch (USA)","Prensa local",A,F,PX),
 ("english_proficiency_index","float","índice","Nivel de inglés (contratos, equipos internacionales)","EF English Proficiency Index","-",A,F,R),
 ("business_language","string","-","Idioma de negocio y de la tramitación","-","-",A,C,R),
 ("trade_union_density_pct","float","%","Afiliación sindical (relaciones laborales en obra y operación)","ILOSTAT, OCDE","-",A,F,R),
 ("days_lost_strikes_1000","float","días/1000 empleados","Días de trabajo perdidos por huelgas","ILOSTAT","-",A,F,R),
 ("weekly_work_hours","float","h","Horas semanales trabajadas","ILOSTAT, OCDE","-",A,F,R),
 ("public_holidays_year","int","días","Festivos nacionales al año","Calendarios oficiales","-",A,F,R),
 ("time_zone_utc_offset","float","h","Huso horario (solape con clientes e inversores)","IANA tz","-",A,C,R),
 ("human_development_index","float","0-1","Índice de desarrollo humano","PNUD","-",A,F,R),
 ("tertiary_stem_grads_pct","float","%","Graduados en ciencias e ingeniería","UNESCO UIS","-",A,F,R),
]))

B.append(("14 Etiquetas y salidas", "sites", [
 ("is_datacenter","bool","0/1","Hay un data center construido o en obra","OSM, PeeringDB, expedientes públicos","-",M,L,R),
 ("dc_status","category","-","Operativo, en obra, planificado o cancelado","Expedientes, prensa","-",M,L,R),
 ("dc_cancelled_flag","bool","0/1","Proyecto cancelado o denegado (negativo valioso)","Prensa, expedientes","-",A,L,R),
 ("capacity_mw","float","MW","Capacidad eléctrica del proyecto","Expedientes, prensa","-",A,L,R),
 ("operator_type","category","-","Hiperescalar, colocation o empresa","PeeringDB, prensa","-",A,F,R),
 ("year_commissioned","int","año","Año de puesta en marcha","Prensa, expedientes","-",A,F,R),
 ("sample_type","category","-","Positivo real, negativo aleatorio o negativo cancelado","Diseño del muestreo","-",M,C,D),
 ("viability_score","float","0-100","Puntuación de viabilidad calculada","Modelo propio","-",M,L,D),
 ("capex_per_mw_usd","float","USD/MW","Inversión estimada por MW","Modelo de costes","Turner & Townsend como referencia",M,L,D),
 ("foundation_overcost_pct","float","%","Sobrecoste de cimentación por tipo de suelo","Modelo de costes (supuesto)","-",M,L,S),
 ("opex_per_mw_year_usd","float","USD/MW/año","Coste operativo anual por MW","Modelo de costes","-",A,L,D),
 ("time_to_power_months","float","meses","Plazo estimado hasta tener energía","Modelo propio","-",A,L,D),
]))

B.append(("15 Control y linaje", "todas", [
 ("source","string","-","Fuente de cada dato o capa","-","-",M,C,R),
 ("source_url","string","URL","Enlace a la fuente","-","-",M,C,R),
 ("license","string","-","Licencia (CC BY, ODbL, NC…)","-","-",M,C,R),
 ("retrieved_at","datetime","UTC","Fecha de descarga","-","-",M,C,R),
 ("reference_year","int","año","Año al que se refiere el dato","-","-",M,C,R),
 ("spatial_resolution_m","float","m","Resolución espacial de la capa de origen","-","-",A,C,R),
 ("is_synthetic","bool","0/1","El dato es simulado","-","-",M,C,R),
 ("imputation_method","category","-","Cómo se rellenó si faltaba (ninguno, media país, modelo)","-","-",M,C,R),
 ("confidence","float","0-1","Confianza en el dato","-","-",A,C,D),
 ("crs","string","EPSG","Sistema de referencia (EPSG:4326)","-","-",M,C,R),
 ("pipeline_version","string","semver","Versión del script que generó el dato","-","-",A,C,R),
]))


YEARLY = set("""
electricity_price_industrial_usd_mwh wholesale_price_mean_usd_mwh electricity_price_volatility grid_carbon_intensity_gco2_kwh renewable_share_pct
mean_temp_c max_temp_p99_c min_temp_p01_c diurnal_range_c cooling_degree_days heating_degree_days wetbulb_p99_c dewpoint_mean_c rel_humidity_mean_pct
free_cooling_hours adiabatic_cooling_hours est_pue est_wue_l_kwh heatwave_days_year tropical_nights_year frost_days_year annual_precip_mm
max_daily_precip_p99_mm fog_days_year wind_speed_mean_ms hail_days_year solar_ghi_kwh_m2 dust_aod pm25_ug_m3 so2_ug_m3 extreme_cold_days_year
severe_storm_days_year dust_storm_days_year
fixed_broadband_mbps packet_loss_pct jitter_ms
land_price_usd_m2 land_price_trend_5y_pct construction_cost_index labor_cost_hourly_usd unemployment_rate_pct gdp_per_capita_ppp corporate_tax_pct
interest_rate_pct inflation_pct country_risk_premium_pct sovereign_rating fx_volatility ppp_factor
population_10km population_50km built_up_pct_5km nightlights_radiance
aadt_nearest_road airport_annual_movements overflights_per_day population_1km housing_pressure_index
carbon_price_usd_t local_opposition_index moratorium_flag ndvi_mean
""".split())

def temporalidad(tabla, campo):
    if tabla == "country_context": return "Anual"
    if tabla == "signal_features": return "Por registro"
    if tabla == "todas": return "Metadato"
    if tabla == "stations": return "Estático"
    return "Anual" if campo in YEARLY else "Estático"

# Variables diarias (tabla sites_daily o country_daily) y a qué campo del diccionario alimentan
DAILY = [
 ("sites_daily","site_id","string","-","Clave de la celda","-","-"),
 ("sites_daily","date","date","AAAA-MM-DD","Día (UTC)","-","-"),
 ("sites_daily","t2m_mean_c","float","°C","Temperatura media diaria","ERA5-Land time-series (CDS)","mean_temp_c, cooling_degree_days, heating_degree_days"),
 ("sites_daily","t2m_max_c","float","°C","Temperatura máxima diaria","ERA5-Land time-series (CDS)","max_temp_p99_c, heatwave_days_year, diurnal_range_c"),
 ("sites_daily","t2m_min_c","float","°C","Temperatura mínima diaria","ERA5-Land time-series (CDS)","min_temp_p01_c, frost_days_year, tropical_nights_year"),
 ("sites_daily","td2m_mean_c","float","°C","Punto de rocío medio diario","ERA5-Land time-series (CDS)","dewpoint_mean_c"),
 ("sites_daily","rh_mean_pct","float","%","Humedad relativa media (desde T y Td)","Derivado","rel_humidity_mean_pct"),
 ("sites_daily","wetbulb_max_c","float","°C","Bulbo húmedo máximo (fórmula de Stull)","Derivado","wetbulb_p99_c"),
 ("sites_daily","wind10m_mean_ms","float","m/s","Viento medio a 10 m","ERA5-Land time-series (CDS)","wind_speed_mean_ms"),
 ("sites_daily","wind10m_max_ms","float","m/s","Viento horario máximo a 10 m","ERA5-Land time-series (CDS)","-"),
 ("sites_daily","precip_mm","float","mm","Precipitación diaria","ERA5-Land time-series (CDS)","annual_precip_mm, max_daily_precip_p99_mm"),
 ("sites_daily","snowfall_mm_we","float","mm eq. agua","Nevada diaria","ERA5-Land time-series (CDS)","snow_load_kn_m2"),
 ("sites_daily","ssrd_kwh_m2","float","kWh/m²","Radiación solar diaria","ERA5-Land time-series (CDS)","solar_ghi_kwh_m2"),
 ("sites_daily","soil_moisture_l1","float","m³/m³","Humedad del suelo 0-7 cm (sequía)","ERA5-Land time-series (CDS)","drought_risk"),
 ("sites_daily","cdd_18","float","°C·día","Grados-día de refrigeración","Derivado","cooling_degree_days"),
 ("sites_daily","hdd_18","float","°C·día","Grados-día de calefacción","Derivado","heating_degree_days"),
 ("sites_daily","free_cooling_hours","int","h","Horas con T < umbral de free cooling","Derivado (horario)","free_cooling_hours, est_pue"),
 ("sites_daily","adiabatic_cooling_hours","int","h","Horas con bulbo húmedo < umbral","Derivado (horario)","adiabatic_cooling_hours, est_wue_l_kwh"),
 ("sites_daily","heatwave_flag","bool","0/1","Máxima > 35 °C","Derivado","heatwave_days_year"),
 ("sites_daily","tropical_night_flag","bool","0/1","Mínima > 20 °C","Derivado","tropical_nights_year"),
 ("sites_daily","frost_flag","bool","0/1","Mínima < 0 °C","Derivado","frost_days_year"),
 ("sites_daily","extreme_cold_flag","bool","0/1","Mínima < -15 °C","Derivado","extreme_cold_days_year"),
 ("sites_daily","eq_count_100km","int","número","Terremotos en 100 km ese día","EMSC FDSN (catálogo)","n_eq_m4_100km_50y"),
 ("sites_daily","eq_max_mag_100km","float","M","Magnitud máxima en 100 km ese día","EMSC FDSN (catálogo)","max_mag_100km_hist"),
 ("sites_daily","fire_detections_10km","int","número","Focos de incendio en 10 km","NASA FIRMS (MODIS_SP, VIIRS_SNPP_SP)","burned_area_10y_pct_10km, wildfire_hazard"),
 ("sites_daily","fire_frp_sum_10km","float","MW","Potencia radiativa total de esos focos","NASA FIRMS","-"),
 ("sites_daily","river_discharge_m3s","float","m³/s","Caudal del río más cercano","GloFAS (EWDS) — pendiente","nearest_river_discharge_m3s"),
 ("sites_daily","pm25_ug_m3","float","µg/m³","PM2.5 diario","CAMS EAC4 (ADS) — pendiente","pm25_ug_m3"),
 ("sites_daily","dust_aod","float","adimensional","Aerosol de polvo diario","CAMS EAC4 (ADS) — pendiente","dust_aod"),
 ("country_daily","country_iso3","string","ISO 3166-1","País (solo ESP de momento)","-","-"),
 ("country_daily","date","date","AAAA-MM-DD","Día","-","-"),
 ("country_daily","omie_price_mean_eur_mwh","float","EUR/MWh","Precio medio del mercado diario","OMIE (marginalpdbc)","wholesale_price_mean_usd_mwh, electricity_price_volatility"),
 ("country_daily","omie_price_max_eur_mwh","float","EUR/MWh","Precio máximo horario","OMIE","-"),
 ("country_daily","omie_price_min_eur_mwh","float","EUR/MWh","Precio mínimo horario","OMIE","-"),
 ("country_daily","eur_usd","float","USD por EUR","Tipo de cambio de referencia del BCE","BCE Data API","conversión a USD"),
 ("country_daily","omie_price_mean_usd_mwh","float","USD/MWh","Precio medio en USD","Derivado","wholesale_price_mean_usd_mwh"),
 ("country_daily","gen_total_gwh","float","GWh","Generación total peninsular","REE REData","-"),
 ("country_daily","renewable_share_pct","float","%","Cuota renovable diaria","REE REData","renewable_share_pct"),
 ("country_daily","carbon_intensity_gco2_kwh","float","gCO2/kWh","Intensidad de carbono (factores de emisión por tecnología)","Derivado de REE REData","grid_carbon_intensity_gco2_kwh"),
]

# Variables semanales (tabla sites_weekly): lo que se carga en el data lake. Semana ISO (lunes a domingo),
# particionada por el año ISO de la semana. Cada campo sale de uno diario con una regla de agregación.
# (campo semanal, campo diario, agregación, tipo, unidad, descripción)
WEEKLY_AGG = [
 ("t2m_mean_c","t2m_mean_c","media","float","°C","Temperatura media de la semana"),
 ("t2m_max_c","t2m_max_c","máximo","float","°C","Temperatura máxima de la semana"),
 ("t2m_min_c","t2m_min_c","mínimo","float","°C","Temperatura mínima de la semana"),
 ("td2m_mean_c","td2m_mean_c","media","float","°C","Punto de rocío medio"),
 ("rh_mean_pct","rh_mean_pct","media","float","%","Humedad relativa media"),
 ("wetbulb_max_c","wetbulb_max_c","máximo","float","°C","Bulbo húmedo máximo de la semana"),
 ("wind10m_mean_ms","wind10m_mean_ms","media","float","m/s","Viento medio a 10 m"),
 ("wind10m_max_ms","wind10m_max_ms","máximo","float","m/s","Viento horario máximo de la semana"),
 ("precip_mm","precip_mm","suma","float","mm","Precipitación de la semana"),
 ("precip_max_day_mm","precip_mm","máximo","float","mm","Precipitación del día más lluvioso de la semana"),
 ("snowfall_mm_we","snowfall_mm_we","suma","float","mm eq. agua","Nevada de la semana"),
 ("ssrd_kwh_m2","ssrd_kwh_m2","suma","float","kWh/m²","Radiación solar de la semana"),
 ("soil_moisture_l1","soil_moisture_l1","media","float","m³/m³","Humedad del suelo 0-7 cm"),
 ("cdd_18","cdd_18","suma","float","°C·día","Grados-día de refrigeración"),
 ("hdd_18","hdd_18","suma","float","°C·día","Grados-día de calefacción"),
 ("free_cooling_hours","free_cooling_hours","suma","int","h","Horas con T < umbral de free cooling"),
 ("adiabatic_cooling_hours","adiabatic_cooling_hours","suma","int","h","Horas con bulbo húmedo < umbral"),
 ("heatwave_days","heatwave_flag","días","int","días","Días con máxima > 35 °C"),
 ("tropical_nights","tropical_night_flag","días","int","días","Días con mínima > 20 °C"),
 ("frost_days","frost_flag","días","int","días","Días con mínima < 0 °C"),
 ("extreme_cold_days","extreme_cold_flag","días","int","días","Días con mínima < -15 °C"),
 ("eq_count_100km","eq_count_100km","suma","int","número","Terremotos en 100 km durante la semana"),
 ("eq_max_mag_100km","eq_max_mag_100km","máximo","float","M","Magnitud máxima en 100 km"),
 ("fire_detections_10km","fire_detections_10km","suma","int","número","Focos de incendio en 10 km"),
 ("fire_frp_sum_10km","fire_frp_sum_10km","suma","float","MW","Potencia radiativa total de los focos"),
 ("river_discharge_m3s","river_discharge_m3s","media","float","m³/s","Caudal medio del río más cercano"),
 ("pm25_ug_m3","pm25_ug_m3","media","float","µg/m³","PM2.5 medio"),
 ("dust_aod","dust_aod","media","float","adimensional","Aerosol de polvo medio"),
]

wb = Workbook()
ws = wb.active
ws.title = "Diccionario"
hdr = ["Bloque","Tabla","Campo","Tipo","Unidad","Descripción","Fuentes globales","Fuentes nacionales / notas","Prioridad","Rol","Origen esperado","Temporalidad"]
ws.append(hdr)
for bloque, tabla, rows in B:
    for r in rows:
        ws.append([bloque, r[9] if len(r)>9 else tabla, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], temporalidad(r[9] if len(r)>9 else tabla, r[0])])
n = ws.max_row

font = Font(name="Arial", size=10)
hfont = Font(name="Arial", size=10, bold=True, color="FFFFFF")
hfill = PatternFill("solid", fgColor="1F3A5F")
for row in ws.iter_rows(min_row=1, max_row=n):
    for c in row:
        c.font = font
        c.alignment = Alignment(vertical="top", wrap_text=True)
for c in ws[1]:
    c.font = hfont; c.fill = hfill
    c.alignment = Alignment(vertical="center", wrap_text=True)
widths = [26,16,32,10,14,52,40,44,11,11,14,14]
for i,w in enumerate(widths,1):
    ws.column_dimensions[get_column_letter(i)].width = w
ws.freeze_panes = "D2"
tab = Table(displayName="Diccionario", ref=f"A1:L{n}")
tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
ws.add_table(tab)
ws.conditional_formatting.add(f"I2:I{n}", FormulaRule(formula=[f'$I2="MVP"'], font=Font(name="Arial", bold=True, color="1F6F3F"), fill=PatternFill("solid", fgColor="E3F2E6")))
ws.conditional_formatting.add(f"K2:K{n}", FormulaRule(formula=[f'$K2="Sintético"'], fill=PatternFill("solid", fgColor="FDE2E1")))
ws.conditional_formatting.add(f"K2:K{n}", FormulaRule(formula=[f'$K2="Proxy"'], fill=PatternFill("solid", fgColor="FFF4D6")))

# Resumen
rs = wb.create_sheet("Resumen")
rs.append(["Bloque","Total campos","MVP","Ampliado","Features","Etiquetas","Reales","Proxy","Sintéticos","Derivados"])
blocks = [b[0] for b in B]
for i,b in enumerate(blocks, start=2):
    rs.cell(i,1,b)
    D_ = "Diccionario!$A$2:$A$%d" % n
    def ci(col, val): return f'=COUNTIFS({D_},$A{i},Diccionario!${col}$2:${col}${n},"{val}")'
    rs.cell(i,2,f"=COUNTIF({D_},$A{i})")
    rs.cell(i,3,ci("I","MVP")); rs.cell(i,4,ci("I","Ampliado"))
    rs.cell(i,5,ci("J","Feature")); rs.cell(i,6,ci("J","Etiqueta"))
    rs.cell(i,7,ci("K","Real")); rs.cell(i,8,ci("K","Proxy"))
    rs.cell(i,9,ci("K","Sintético")); rs.cell(i,10,ci("K","Derivado"))
last = len(blocks)+1
tr = last+1
rs.cell(tr,1,"TOTAL")
for col in range(2,11):
    L_ = get_column_letter(col)
    rs.cell(tr,col,f"=SUM({L_}2:{L_}{last})")
for row in rs.iter_rows(min_row=1, max_row=tr):
    for c in row: c.font = font
for c in rs[1]: c.font = hfont; c.fill = hfill; c.alignment = Alignment(wrap_text=True, vertical="center")
for c in rs[tr]: c.font = Font(name="Arial", size=10, bold=True)
rs.column_dimensions["A"].width = 30
for col in range(2,11): rs.column_dimensions[get_column_letter(col)].width = 12
rs.freeze_panes = "B2"

# Tablas del lake
tl = wb.create_sheet("Tablas del lake")
tl.append(["Tabla","Granularidad (una fila por…)","Clave","Se une con","Zona del lake","Formato recomendado"])
for r in [
 ["sites","Emplazamiento (parcela o punto muestreado)","site_id","stations por nearest_station_id; country_context por country_iso3","processed/ y features/","GeoParquet"],
 ["stations","Estación sísmica","station_id","signal_features por station_id","processed/","GeoParquet"],
 ["signal_features","Registro de ruido analizado","record_id","stations por station_id","features/","Parquet (formas de onda crudas en raw/ como MiniSEED)"],
 ["country_context","País","country_iso3","sites por country_iso3","processed/","Parquet"],
 ["grid_h3_r7","Celda H3 resolución 7 con capas precalculadas","h3_cell_r7","sites por h3_cell_r7","features/","Parquet"],
 ["catalog","Dataset descargado","dataset_id","-","metadata/","CSV"],
]: tl.append(r)
for row in tl.iter_rows():
    for c in row: c.font = font; c.alignment = Alignment(wrap_text=True, vertical="top")
for c in tl[1]: c.font = hfont; c.fill = hfill
for col,w in zip("ABCDEF",[18,40,16,48,22,36]): tl.column_dimensions[col].width = w

# Leyenda
lg = wb.create_sheet("Leyenda")
for r in [
 ["Columna","Valores","Significado"],
 ["Prioridad","MVP","Imprescindible para la demo de 4 días"],
 ["","Ampliado","Aporta al modelo general; puede quedar nulo"],
 ["Rol","Feature","Variable de entrada del modelo"],
 ["","Etiqueta","Lo que el modelo aprende a predecir"],
 ["","Clave","Identificador para unir tablas"],
 ["","Control","Metadato de calidad o trazabilidad; no entra al modelo"],
 ["Origen esperado","Real","Dato publicado por la fuente"],
 ["","Proxy","Aproximación indirecta (p. ej. Vs30 desde pendiente)"],
 ["","Sintético","Simulado para el MVP; marcar is_synthetic = 1"],
 ["","Derivado","Calculado por el equipo a partir de otros campos"],
 ["Temporalidad","Estático","Un valor por celda (tabla sites_static)"],
 ["","Anual","Un valor por celda o país y año (sites_yearly, country_context)"],
 ["","Por registro","Una fila por grabación sísmica analizada (signal_features)"],
 ["","Metadato","Linaje y control (tabla field_lineage)"],
 ["",""," "],
 ["Notas","","Licencias no comerciales: GEM y Lista Roja UICN. Registro previo: NIED (Japón), Copernicus CDS, KBA, BirdLife."],
 ["","","Unidades: SI; moneda única USD (ajustar por PPA con ppp_factor)."],
 ["","","Fuentes no verificadas una a una a fecha de hoy: comprobar acceso y licencia antes de descargar."],
]: lg.append(r)
for row in lg.iter_rows():
    for c in row: c.font = font; c.alignment = Alignment(wrap_text=True, vertical="top")
for c in lg[1]: c.font = hfont; c.fill = hfill
lg.column_dimensions["A"].width = 18; lg.column_dimensions["B"].width = 14; lg.column_dimensions["C"].width = 80


# Variables diarias
vd = wb.create_sheet("Variables diarias", 1)
vd.append(["Tabla","Campo","Tipo","Unidad","Descripción","Fuente","Alimenta a (campo del diccionario)"])
for r in DAILY: vd.append(list(r))
for row in vd.iter_rows():
    for c in row: c.font = font; c.alignment = Alignment(wrap_text=True, vertical="top")
for c in vd[1]: c.font = hfont; c.fill = hfill
for col,w in zip("ABCDEFG",[15,28,9,13,44,36,46]): vd.column_dimensions[col].width = w
vd.freeze_panes = "C2"

# Variables semanales (lo que va al data lake)
vw = wb.create_sheet("Variables semanales", 2)
vw.append(["Tabla","Campo","Tipo","Unidad","Descripción","Desde (campo diario)","Agregación"])
vw.append(["sites_weekly","site_id","string","-","Clave de la celda","site_id","-"])
vw.append(["sites_weekly","week_start","date","AAAA-MM-DD","Lunes de la semana ISO (partición: año ISO de la semana)","date","-"])
vw.append(["sites_weekly","n_days_week","int","días","Días de la semana dentro del periodo (7 salvo en los extremos)","date","recuento"])
for f, src, agg, typ, unit, desc in WEEKLY_AGG:
    vw.append(["sites_weekly", f, typ, unit, desc, src, agg])
for row in vw.iter_rows():
    for c in row: c.font = font; c.alignment = Alignment(wrap_text=True, vertical="top")
for c in vw[1]: c.font = hfont; c.fill = hfill
for col,w in zip("ABCDEFG",[15,26,9,13,50,26,12]): vw.column_dimensions[col].width = w
vw.freeze_panes = "C2"
tl.append(["sites_weekly","Celda y semana ISO","site_id + week_start","sites por site_id","data lake (tabla de entrenamiento)",
           "Parquet particionado por año ISO"])
lg.append(["Temporalidad","Semanal","Celda y semana ISO (sites_weekly), agregada desde las variables diarias"])

wb.save("diccionario_datos_datacenters.xlsx")
print("filas:", n-1)
