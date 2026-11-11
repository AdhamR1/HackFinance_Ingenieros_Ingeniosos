"""Capa de INSTALACIONES MILITARES por celda (España, Japón o cualquier país con perfil).

Uso:
    python angel_modelo/src/militar.py descargar      # (una vez) polígonos de OpenStreetMap -> datos/militar/<iso>.geojson
    python angel_modelo/src/actualizar.py militar     # enriquecimiento por celda (lo llama 'todo')

Fuente: OpenStreetMap vía Overpass (landuse=military y military=base|airfield|naval_base|barracks|range|
training_area|ammunition). ODbL © colaboradores de OpenStreetMap. LIMITACIONES (se muestran en el mapa):
OSM puede estar incompleto, algunas instalaciones sensibles pueden no figurar, y la HUELLA FÍSICA NO ES el
perímetro legal (zonas de seguridad de la Ley 8/1975 en España; áreas vigiladas de la Ley 84/2021 en Japón).

Por celda (en la proyección métrica de igual área de la rejilla del ETL, la misma que define las celdas):
    militar_pct           % de la celda ocupado por instalaciones (unión de polígonos)
    distancia_militar_km  distancia de la celda a la instalación más cercana (0 si se solapan)
    en_franja             1 si la celda toca la instalación o su franja (buffer configurable), si no 0
Si no hay archivo de la capa, no se escribe nada: la rúbrica la marca «no verificada» y baja la confianza.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date

import numpy as np
import pandas as pd

from configuracion import columnas, crs_rejilla, perfil, ruta, salida

OVERPASS = "https://overpass-api.de/api/interpreter"
VALORES = "base|airfield|naval_base|barracks|range|training_area|ammunition"


def archivo_capa():
    return ruta("datos_propios") / "militar" / f"{perfil()['pais'].lower()}.geojson"


def descargar():
    """Descarga los polígonos de OSM del país (una petición, con reintentos). Guarda un GeoJSON compacto."""
    import requests

    iso2 = perfil()["iso2"]
    q = (f'[out:json][timeout:600];area["ISO3166-1"="{iso2}"][admin_level=2]->.a;'
         f'(way["landuse"="military"](area.a);relation["landuse"="military"](area.a);'
         f'way["military"~"^({VALORES})$"](area.a);relation["military"~"^({VALORES})$"](area.a););out geom;')
    for intento in range(4):
        try:
            r = requests.post(OVERPASS, data={"data": q}, timeout=900,
                              headers={"User-Agent": "hackfinance-cribado-dc/1.0 (hackathon UC3M)"})
            if r.status_code == 200:
                break
            print(f"  Overpass {r.status_code}; reintento", flush=True)
        except requests.RequestException as e:
            print(f"  Overpass: {e}; reintento", flush=True)
        time.sleep(30 * (intento + 1))
    else:
        raise SystemExit("No se pudo descargar la capa militar de Overpass")
    feats = []
    for el in r.json().get("elements", []):
        anillos = []
        if el["type"] == "way" and el.get("geometry"):
            anillos = [[[p["lon"], p["lat"]] for p in el["geometry"]]]
        elif el["type"] == "relation":
            anillos = [[[p["lon"], p["lat"]] for p in m["geometry"]] for m in el.get("members", [])
                       if m.get("role") == "outer" and m.get("geometry")]
        anillos = [[[round(x, 5), round(y, 5)] for x, y in a] for a in anillos if len(a) >= 4 and a[0] == a[-1]]
        if not anillos:
            continue
        t = el.get("tags", {})
        feats.append({"type": "Feature", "properties": {"osm": f"{el['type'][0]}{el['id']}",
                                                         "tipo": t.get("military") or t.get("landuse"),
                                                         "nombre": t.get("name", "")},
                      "geometry": {"type": "MultiPolygon", "coordinates": [[a] for a in anillos]}})
    f = archivo_capa()
    f.parent.mkdir(parents=True, exist_ok=True)
    meta = {"fuente": "OpenStreetMap (Overpass API)", "licencia": "ODbL 1.0 · © colaboradores de OpenStreetMap",
            "fecha_descarga": date.today().isoformat(), "consulta": q, "poligonos": len(feats)}
    f.write_text(json.dumps({"type": "FeatureCollection", "meta": meta, "features": feats},
                            ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(feats)} polígonos -> {f} ({f.stat().st_size / 1e6:.1f} MB)")


def leer_capa():
    """GeoDataFrame en la proyección de la rejilla, o None si no hay archivo. Valida y repara geometrías."""
    import geopandas as gpd
    import shapely

    f = archivo_capa()
    if not f.exists():
        return None, {"estado": "ausente", "archivo": str(f)}
    raw = f.read_bytes()
    try:
        d = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:                      # p. ej. nombres en Shift_JIS/CP932
        print("  AVISO: la capa militar no está en UTF-8; se lee como CP932", flush=True)
        d = json.loads(raw.decode("cp932"))
    meta = d.get("meta", {})
    if not d.get("features"):
        return gpd.GeoDataFrame(geometry=[], crs=4326), {**meta, "estado": "vacia", "poligonos": 0}
    g = gpd.GeoDataFrame.from_features(d["features"], crs=4326).to_crs(crs_rejilla())
    g["geometry"] = shapely.make_valid(g.geometry.values)
    g = g[~g.geometry.is_empty]
    return g, {**meta, "estado": "ok", "poligonos": int(len(g)), "area_km2": round(float(g.union_all().area) / 1e6, 1)}


def por_celda(cells: pd.DataFrame, g, tam: float, buffer_m: float, tipos_entidad=None, area_min_ha: float = 0.0) -> pd.DataFrame:
    """Por celda (ids con patrón de rejilla):
      militar_pct           % de la celda ocupado por CUALQUIER recinto militar (decide la exclusión)
      distancia_militar_km  distancia a la instalación con entidad más cercana (si no hay, a cualquier recinto)
      en_franja             1 si toca una instalación CON ENTIDAD o su franja (buffer_m); 0 si no
      militar_menor         1 si solo toca un recinto MENOR (sin tipo de entidad y < area_min_ha) o su franja
    «Con entidad» = tipo en `tipos_entidad` (base, aeródromo, base naval, campo de tiro...) o área >= area_min_ha.
    Si la capa no trae tipo, todos los recintos cuentan como instalaciones con entidad."""
    import shapely

    patron = columnas()["identificador"]["patron"]
    ij = cells["site_id"].astype(str).str.extract(patron).astype(float).to_numpy()
    ok = ~np.isnan(ij).any(axis=1)
    out = pd.DataFrame({"site_id": cells["site_id"], "militar_pct": np.nan, "distancia_militar_km": np.nan,
                        "en_franja": np.nan, "militar_menor": np.nan})
    if g is None:
        return out
    boxes = shapely.box(ij[ok, 0] * tam, ij[ok, 1] * tam, (ij[ok, 0] + 1) * tam, (ij[ok, 1] + 1) * tam)
    if len(g) == 0:                         # capa vacía: no hay instalaciones registradas (dato = 0, con alerta)
        out.loc[ok, ["militar_pct", "en_franja", "militar_menor"]] = 0.0
        return out
    polys = np.array(g.geometry.values, dtype=object)
    tree = shapely.STRtree(polys)
    pct = np.zeros(len(boxes))
    ci, pi = tree.query(boxes, predicate="intersects")
    if len(ci):
        partes = shapely.intersection(boxes[ci], polys[pi])
        df = pd.DataFrame({"c": ci, "g": partes})
        for c, grp in df.groupby("c"):
            pct[c] = shapely.union_all(grp["g"].values).area
    pct = 100 * pct / (tam * tam)
    if "tipo" in g.columns and tipos_entidad is not None:
        entidad = (g["tipo"].isin(tipos_entidad) | (g.geometry.area >= area_min_ha * 1e4)).to_numpy()
    else:
        entidad = np.ones(len(g), bool)

    def distancia(mask):
        if not mask.any():
            return np.full(len(boxes), np.inf)
        sub = polys[mask]
        t = shapely.STRtree(sub)
        return shapely.distance(boxes, sub[t.nearest(boxes)])

    d_ent, d_men = distancia(entidad), distancia(~entidad)
    en_franja = d_ent <= buffer_m
    out.loc[ok, "militar_pct"] = np.round(pct, 2)
    out.loc[ok, "distancia_militar_km"] = np.round(np.where(np.isfinite(d_ent), d_ent, d_men) / 1000, 3)
    out.loc[ok, "en_franja"] = en_franja.astype(float)
    out.loc[ok, "militar_menor"] = ((d_men <= buffer_m) & ~en_franja).astype(float)
    return out


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "descargar":
        return descargar()
    cfg = perfil().get("militar", {})
    from carga import _lector_equipo, _renombrar_alias

    out_dir = salida()
    leer, _ = _lector_equipo()
    st = _renombrar_alias(leer(columnas()["tablas"]["estatica"]))
    idc = columnas()["identificador"]["columna"]
    cells = st[[idc]].drop_duplicates().rename(columns={idc: "site_id"}).reset_index(drop=True)
    g, info = leer_capa()
    res = por_celda(cells, g, float(columnas()["rejilla"]["tamano_celda_m"]), float(cfg.get("buffer_m", 500)),
                    cfg.get("tipos_entidad"), float(cfg.get("area_min_ha", 0)))
    res = res.rename(columns={"site_id": idc})
    (out_dir / "capas").mkdir(exist_ok=True)
    f = out_dir / "capas" / "militar.parquet"
    if g is None:
        f.unlink(missing_ok=True)
    else:
        res.to_parquet(f, index=False)
    info["celdas_con_instalacion"] = int((res.militar_pct > 0).sum())
    info["celdas_en_franja"] = int((res.en_franja == 1).sum())
    info["celdas_recinto_menor"] = int((res.militar_menor == 1).sum())
    if g is not None and len(g) and "tipo" in g.columns:
        ent = g["tipo"].isin(cfg.get("tipos_entidad") or []) | (g.geometry.area >= float(cfg.get("area_min_ha", 0)) * 1e4)
        info["poligonos_con_entidad"] = int(ent.sum())
    (out_dir / "capa_militar.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"capa militar: {info.get('estado')} · polígonos {info.get('poligonos', 0)} · celdas con instalación "
          f"{info['celdas_con_instalacion']} · en franja {info['celdas_en_franja']}")


if __name__ == "__main__":
    main()
