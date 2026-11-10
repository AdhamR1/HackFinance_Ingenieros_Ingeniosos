"""Export the model results in the format of the web (pagina/DATA_FORMAT.md) -> pagina/data/ES.json.

Uses OUR grid (EPSG:3035, 3,500 m, id = site_id), clipped to the same outline of Spain the web uses
(pagina/herramientas/fuentes/espana_contorno.geojson), so no value is resampled between grids.

  puntuacion        model rank mapped to the web colours (config.js umbrales: verde >= 70, amarillo >= 50):
                    best 5 % -> 70-100, next 15 % -> 50-69, rest -> 0-49. 0 when excluded.
  descartado        exclusions_es_3500 (only what is forbidden: water, national park, floodway)
  permisos          the warnings of feat_suelo.WARN_PCT (information only, they do not change the colour)
  motivos_*         the 3 variables that weigh most in THIS cell (SHAP, from scores_es_3500.reasons),
                    in words; a reason that contradicts the plain reading of its value is dropped
  6 variables       0-100, 100 = best, compared with the rest of Spain. Informative: the score does NOT
                    come from them (it comes from the model), so the web does not need any weights.

Usage (from pipeline/): python src/exportar_web.py
"""
import json

import numpy as np
import pandas as pd
import pyproj
import shapely
import shapely.geometry

from cells import CELL_M, PROCESSED, PIPELINE, read_grid
from feat_suelo import WARN_PCT

WEB = PIPELINE.parent / "pagina"
OUTLINE = WEB / "herramientas" / "fuentes" / "espana_contorno.geojson"
OUT = WEB / "data" / "ES.json"

PERMISO = {"natura2000": "natura_2000", "parque_nacional": "parque_nacional", "urbano": "suelo_urbano",
           "zfp": "flujo_preferente", "zi_t100": "zona_inundable"}
DESCARTE = {
    "parque nacional": "parque_nacional",
    "zona de flujo preferente": {"es": "Zona de flujo preferente (cauce de avenidas)",
                                 "en": "Floodway (preferential flow zone)"},
    "agua": {"es": "Casi toda la zona es agua (embalse, lago o marisma)",
             "en": "Almost entirely water (reservoir, lake or marsh)"},
}


def num(v, d=1):
    s = f"{v:,.{d}f}" if abs(v) < 10 or d == 0 else f"{v:,.0f}"
    return s.replace(",", " ").replace(".", ",").replace(" ", ".")


def km(v):
    return num(v, 1 if v < 10 else 0)


# variable -> (good direction: -1 lower is better / +1 higher / 0 depends, es text, en text)
TEXT = {
    "dist_substation_km": (-1, "Subestación eléctrica a {km} km", "Electrical substation {km} km away"),
    "dist_substation_220kv_km": (-1, "Subestación de 220 kV a {km} km", "220 kV substation {km} km away"),
    "dist_substation_400kv_km": (-1, "Subestación de 400 kV a {km} km", "400 kV substation {km} km away"),
    "dist_hv_line_km": (-1, "Línea de alta tensión a {km} km", "High-voltage line {km} km away"),
    "dist_400kv_line_km": (-1, "Línea de 400 kV a {km} km", "400 kV line {km} km away"),
    "n_substations_20km": (1, "{n} subestaciones en 20 km", "{n} substations within 20 km"),
    "n_towers_5km": (1, "{n} torres de alta tensión en 5 km", "{n} high-voltage towers within 5 km"),
    "dist_power_plant_km": (-1, "Central eléctrica a {km} km", "Power plant {km} km away"),
    "gen_capacity_50km_mw": (1, "{n} MW de generación eléctrica en 50 km", "{n} MW of power generation within 50 km"),
    "renewable_capacity_50km_mw": (1, "{n} MW renovables en 50 km", "{n} MW of renewables within 50 km"),
    "industrial_pct": (1, "Suelo industrial: {pct} % de la zona", "Industrial land: {pct} % of the area"),
    "urbano_pct": (0, "Suelo urbano: {pct} % de la zona", "Urban land: {pct} % of the area"),
    "population_1km": (0, "{n} habitantes a menos de 1 km", "{n} people within 1 km"),
    "dist_residential_km": (0, "Viviendas a {km} km", "Housing {km} km away"),
    "dist_military_km": (0, "Zona militar a {km} km", "Military area {km} km away"),
    "dist_mine_quarry_km": (0, "Mina o cantera a {km} km", "Mine or quarry {km} km away"),
    "dist_fire_station_km": (-1, "Parque de bomberos a {km} km", "Fire station {km} km away"),
    "dist_primary_road_km": (-1, "Carretera principal a {km} km", "Main road {km} km away"),
    "dist_motorway_junction_km": (-1, "Salida de autovía a {km} km", "Motorway exit {km} km away"),
    "road_density_km_km2": (1, "Densidad de carreteras: {x} km/km²", "Road density: {x} km/km²"),
    "dist_infra_corridor_km": (-1, "Corredor de fibra a {km} km", "Fibre corridor {km} km away"),
    "dist_station_km": (-1, "Estación de tren a {km} km", "Train station {km} km away"),
    "dist_airport_km": (-1, "Aeropuerto a {km} km", "Airport {km} km away"),
    "dist_cable_landing_km": (-1, "Cable submarino a {km} km", "Subsea cable landing {km} km away"),
    "slope_pct": (-1, "Pendiente del terreno: {x} %", "Terrain slope: {x} %"),
    "sand_pct": (0, "Arena en el suelo: {pct} %", "Sand in the soil: {pct} %"),
    "zi_t100_pct": (-1, "Zona inundable (100 años): {pct} % de la zona", "Flood zone (100 years): {pct} % of the area"),
    "zfp_pct": (-1, "Zona de flujo preferente: {pct} % de la zona", "Floodway: {pct} % of the area"),
    "pga_475y_g": (-1, "Peligro sísmico: {x} g", "Seismic hazard: {x} g"),
    "dist_active_fault_km": (1, "Falla activa a {km} km", "Active fault {km} km away"),
    "cooling_degree_days": (-1, "{n} grados-día de refrigeración al año", "{n} cooling degree days a year"),
    "tropical_nights_year": (-1, "{n} noches tropicales al año", "{n} tropical nights a year"),
    "mean_temp_c": (-1, "Temperatura media: {x} °C", "Mean temperature: {x} °C"),
    "dewpoint_mean_c": (-1, "Punto de rocío medio: {x} °C", "Mean dew point: {x} °C"),
    "diurnal_range_c": (0, "Diferencia día-noche: {x} °C", "Day-night range: {x} °C"),
    "solar_ghi_kwh_m2": (1, "Radiación solar: {n} kWh/m²", "Solar radiation: {n} kWh/m²"),
    "ambient_vibration_db": (-1, "Vibración ambiental: {n} dB", "Ambient vibration: {n} dB"),
    "dist_parque_nacional_km": (0, "Parque nacional a {km} km", "National park {km} km away"),
    "agua_pct": (-1, "Agua: {pct} % de la zona", "Water: {pct} % of the area"),
    "natura2000_pct": (-1, "Red Natura 2000: {pct} % de la zona", "Natura 2000: {pct} % of the area"),
}


def phrase(feat, v, lang):
    _, es, en = TEXT[feat]
    tpl = es if lang == "es" else en
    f = num if lang == "es" else (lambda x, d=1: f"{x:,.{d}f}")
    return tpl.format(km=f(v, 1 if v < 10 else 0), n=f(v, 0), pct=f(v, 0), x=f(v, 2 if abs(v) < 1 else 1))


def motivos(reasons: str, med: dict) -> tuple[list, list]:
    favor, contra = [], []
    for r in (reasons or "").split("; "):
        if "=" not in r:
            continue
        feat, rest = r.split("=", 1)
        val, sign = rest.rsplit(" (", 1)
        if feat not in TEXT or val == "nan":
            continue
        v, plus = float(val), sign.startswith("+")
        good = TEXT[feat][0]
        if good and v != med[feat] and ((v - med[feat]) * good > 0) != plus:
            continue                           # e.g. "substation 0.8 km away" as a point against
        (favor if plus else contra).append({"es": phrase(feat, v, "es"), "en": phrase(feat, v, "en")})
    return favor, contra


def pr(s, higher_better=True):
    p = s.rank(pct=True) * 100
    return p if higher_better else 100 - p


def indicators(f: pd.DataFrame, agua: pd.DataFrame) -> pd.DataFrame:
    i = pd.DataFrame(index=f.index)
    i["energia"] = pd.concat([pr(f.dist_substation_220kv_km, False), pr(f.dist_hv_line_km, False),
                              pr(f.gen_capacity_50km_mw)], axis=1).mean(axis=1)
    i["agua"] = 100 - agua.water_stress.reindex(f.index) * 20          # Aqueduct 0 (low) - 5 (extreme)
    i["clima"] = pr(f.est_pue, False)
    i["riesgos"] = pd.concat([pr(f.pga_475y_g, False), 100 - f.zi_t500_pct.clip(0, 100)], axis=1).mean(axis=1)
    i["conectividad"] = pd.concat([pr(f.dist_infra_corridor_km, False),
                                   pr(f.dist_motorway_junction_km, False)], axis=1).mean(axis=1)
    i["suelo"] = 0.7 * pr(f.slope_pct, False) + 0.3 * (f.industrial_pct * 5).clip(0, 100)
    return i.round()


def web_score(pct: pd.Series) -> pd.Series:
    """Percentile (0-100) -> web score: 0-80 -> 0-49, 80-95 -> 50-69, 95-100 -> 70-100."""
    return pd.Series(np.interp(pct, [0, 80, 80.0001, 95, 95.0001, 100], [0, 49, 50, 69, 70, 100]),
                     index=pct.index).round()


def reproject(geom, src, dst):
    t = pyproj.Transformer.from_crs(src, dst, always_xy=True)
    return shapely.transform(geom, lambda xy: np.column_stack(t.transform(xy[:, 0], xy[:, 1])))


def geometry(grid: pd.DataFrame):
    outline = reproject(shapely.geometry.shape(json.loads(OUTLINE.read_text())["geometry"]), 4326, 3035)
    h = CELL_M / 2
    boxes = shapely.box(grid.x_m - h, grid.y_m - h, grid.x_m + h, grid.y_m + h)
    shapely.prepare(outline)
    inside = shapely.contains(outline, boxes)
    clipped = boxes.copy()
    edge = ~inside
    clipped[edge] = shapely.intersection(boxes[edge], outline, grid_size=1)
    area = shapely.area(clipped) / 1e6
    return list(shapely.set_precision(reproject(clipped, 3035, 4326), 1e-4)), area


def main():
    grid = read_grid().set_index("site_id")
    s = pd.read_parquet(PROCESSED / "scores_es_3500.parquet").set_index("site_id").reindex(grid.index)
    e = pd.read_parquet(PROCESSED / "exclusions_es_3500.parquet").set_index("site_id").reindex(grid.index)
    f = pd.read_parquet(PROCESSED / "features_es_3500.parquet").set_index("site_id").reindex(grid.index)
    agua = pd.read_parquet(PROCESSED / "agua_es_3500.parquet").set_index("site_id")
    ind = indicators(f, agua)
    score = web_score(s.score_pct)
    med = {c: f[c].median() for c in TEXT if c in f}
    pct = e
    geoms, area = geometry(grid.reset_index())
    stress = agua.water_stress.reindex(grid.index)

    feats, n_poly = [], 0
    for k, (sid, row) in enumerate(grid.iterrows()):
        g = geoms[k]
        if g.is_empty or area[k] < 0.01:
            continue
        excl = bool(e.excluded.get(sid, False))
        permisos = [PERMISO[c] for c, lim in WARN_PCT.items() if (pct.at[sid, f"{c}_pct"] or 0) >= lim]
        favor, contra = ([], []) if excl else motivos(s.reasons.get(sid), med)
        if not excl and stress.get(sid, 0) >= 4:
            contra.insert(0, {"es": "Estrés hídrico extremadamente alto en la cuenca",
                              "en": "Extremely high water stress in the basin"})
        props = {
            "id": sid,
            # 0 when excluded: with null the web would make up a provisional score from the variables
            "puntuacion": 0 if excl else (None if pd.isna(score[sid]) else int(score[sid])),
            "descartado": excl,
            "motivo_descarte": DESCARTE.get(e.motivo_descarte.get(sid)) if excl else None,
            **{c: (None if pd.isna(ind.at[sid, c]) else int(ind.at[sid, c])) for c in ind.columns},
            "permisos": permisos,
            "area_km2": round(float(area[k]), 2),
        }
        # an empty list would show nothing; without the field the web builds it (discard reason, permits)
        if favor:
            props["motivos_a_favor"] = favor[:3]
        if contra:
            props["motivos_en_contra"] = contra[:3]
        feats.append({"type": "Feature", "geometry": shapely.geometry.mapping(g), "properties": props})
        n_poly += g.geom_type == "MultiPolygon"

    doc = {"type": "FeatureCollection",
           "meta": {"pais": "ES", "area_cuadrado_km2": CELL_M ** 2 / 1e6, "lado_cuadrado_km": CELL_M / 1000,
                    "datos_de_prueba": False, "fecha": pd.Timestamp.today().strftime("%Y-%m-%d"),
                    "fuente": "Equipo de datos: modelo LightGBM (pipeline/src/train.py) sobre el ELT, "
                              "OpenStreetMap, SNCZI, IGN, CORINE, Natura 2000 y WRI Aqueduct",
                    "proyeccion_cuadricula": "ETRS89-LAEA (EPSG:3035), celdas de 3,5 km"},
           "features": feats}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    p = pd.Series([x["properties"]["puntuacion"] for x in feats]).dropna()
    print(f"{len(feats):,} cuadrados ({n_poly} partidos en varios trozos), {sum(x['properties']['descartado'] for x in feats)} descartados")
    print(f"verde {(p >= 70).sum():,}  amarillo {((p >= 50) & (p < 70)).sum():,}  rojo {(p < 50).sum():,}")
    print(f"-> {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
