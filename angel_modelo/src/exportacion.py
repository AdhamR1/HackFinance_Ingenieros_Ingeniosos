"""Paso 4 · EXPORTACIÓN: salida por celda, informe de datos y archivos compactos del mapa.

Uso:  angel_modelo/.venv/bin/python angel_modelo/src/actualizar.py exportacion
Lee <salida>/celdas.parquet, rubrica.parquet, rubrica_capas.json, informe_carga.json y metricas.json.
Escribe:
  <salida>/salida_celdas.parquet y .csv      una fila por celda (contrato en docs/INTEGRACION.md)
  <salida>/informe_datos.md                  qué ha cambiado en los datos y cobertura por capa
  web_mapa/data/celdas.json                  carga inicial del mapa (estados, percentil, motivos, geometría)
  web_mapa/data/prov/<n>.json                detalle por provincia (se carga al hacer clic)
  web_mapa/data/dc.json, metricas.json, esquema.json, informe_datos.md
  pagina/mapa/                               copia del mapa dentro de la web de Dani (si está configurada)

Sin marcas de tiempo: dos ejecuciones con los mismos datos producen archivos idénticos.
La fecha que se muestra es la de los datos (última modificación de las entradas) y la huella sale de carga.py.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import rubrica as R
from configuracion import columnas, crs_rejilla, perfil, ruta, salida, web_datos

MAX_MB = 10


def _int(a, fill=-1):
    a = np.asarray(a, dtype=float)
    return np.where(np.isnan(a), fill, np.round(a)).astype(int).tolist()


def _textos_motivo(cfg):
    t = {"F:datos": "Faltan datos para evaluarla con confianza"}
    for r in cfg["exclusiones"]:
        t[f"E:{r['id']}"] = "Excluida: " + r["motivo"]
    for r in cfg["condicionantes"]:
        t[f"C:{r['id']}"] = "Condicionante: " + r["aviso"]
    for c in cfg["criterios"]:
        t[f"-:{c['id']}"] = "En contra: " + c["etiqueta"]
        t[f"+:{c['id']}"] = "A favor: " + c["etiqueta"]
    return t


def _geometria(df, idc, lonc, latc, avisos):
    """Rejilla de nodos compartidos (si los ids codifican la rejilla y cuadran con el centroide) o, si no,
    cuadrados reconstruidos desde el centroide y el tamaño configurado."""
    cfg = columnas()
    tam = float(cfg["rejilla"]["tamano_celda_m"])
    ids = df[idc].astype(str)
    m = ids.str.extract(cfg["identificador"]["patron"])
    if m.notna().all().all():
        from pyproj import Transformer

        ij = m.astype(int).to_numpy()
        t = Transformer.from_crs(crs_rejilla(), "EPSG:4326", always_xy=True)
        clon, clat = t.transform((ij[:, 0] + 0.5) * tam, (ij[:, 1] + 0.5) * tam)
        dm = np.hypot((np.asarray(clon) - df[lonc].to_numpy()) * 111320 * np.cos(np.radians(df[latc].to_numpy())),
                      (np.asarray(clat) - df[latc].to_numpy()) * 111320)
        if np.nanmedian(dm) <= cfg["rejilla"]["tolerancia_centroide"] * tam:
            nodes = np.unique(np.concatenate([ij, ij + [1, 0], ij + [1, 1], ij + [0, 1]]), axis=0)
            nlon, nlat = t.transform(nodes[:, 0] * tam, nodes[:, 1] * tam)
            return {"modo": "rejilla", "i": ij[:, 0].tolist(), "j": ij[:, 1].tolist(),
                    "nodes": {"i": nodes[:, 0].tolist(), "j": nodes[:, 1].tolist(),
                              "lon": np.round(np.asarray(nlon) * 1e5).astype(int).tolist(),
                              "lat": np.round(np.asarray(nlat) * 1e5).astype(int).tolist()}}
        avisos.append(f"El centroide no cuadra con el id de celda (mediana {np.nanmedian(dm):.0f} m): ¿ha cambiado "
                      "el tamaño de la rejilla? Se dibujan cuadrados desde el centroide.")
    else:
        avisos.append("Los ids de celda no siguen el patrón configurado: se dibujan cuadrados desde el centroide.")
    h = tam / 2 / 111320
    lat, lon = df[latc].to_numpy(), df[lonc].to_numpy()
    hl = h / np.cos(np.radians(lat))
    return {"modo": "centroide", "ids": ids.tolist(), "lon": np.round(lon * 1e5).astype(int).tolist(),
            "lat": np.round(lat * 1e5).astype(int).tolist(), "medio_lado": [round(h, 6)],
            "medio_lado_lon": np.round(hl * 1e6).astype(int).tolist()}


def _fecha_datos():
    ts = [p.stat().st_mtime for carpeta in (ruta("elt_dataset"), ruta("pipeline_processed"))
          for p in carpeta.rglob("*.parquet")]
    return datetime.fromtimestamp(max(ts), timezone.utc).strftime("%Y-%m-%d") if ts else "desconocida"


def _informe(info, capas, avisos_exp, met) -> str:
    s, c = info["stats"], info["cambios"]
    L = ["# Informe de datos", "",
         f"Huella de los datos: esquema `{info['huella']['esquema']}` · filas `{info['huella']['filas']}`. "
         f"Lector: {s.get('lector')}.", "",
         f"- Celdas: {s['celdas']:,} · provincias: {s['provincias']} · años agregados: {s.get('anios_disponibles', [])}",
         f"- Data centers (celdas): {s['dc']}"]
    dups = {k: v for k, v in s.items() if k.startswith("duplicadas_") and v}
    L.append(f"- Filas duplicadas descartadas (se queda la última): {dups or 'ninguna'}")
    L.append(f"- Valores fuera de rango plausible pasados a «sin dato»: {s['fuera_de_rango'] or 'ninguno'}")
    L.append(f"- Columnas con tipo de texto convertidas a número: {s['tipo_cambiado'] or 'ninguna'}")
    L += ["", "## Cambios respecto a los datos publicados"]
    if c.get("primera_ejecucion"):
        L.append("Primera ejecución: no hay esquema publicado con el que comparar.")
    else:
        hay = any(c[k] for k in ("nuevas", "desaparecidas", "tipo_cambiado", "rango_cambiado", "cobertura_cambiada")) \
            or c.get("filas_antes") != c.get("filas_ahora")
        L.append("**Los datos han cambiado.**" if hay else "Sin cambios de esquema ni de cobertura.")
        L.append(f"- Celdas: {c.get('filas_antes')} → {c.get('filas_ahora')}")
        for k, t in [("nuevas", "Columnas nuevas (no cambian el mapa hasta registrarlas en config/rubrica.yaml)"),
                     ("desaparecidas", "Columnas desaparecidas"), ("tipo_cambiado", "Tipo cambiado"),
                     ("rango_cambiado", "Rango cambiado"), ("cobertura_cambiada", "Cobertura cambiada")]:
            L.append(f"- {t}: {', '.join(c[k][:40]) if c[k] else 'ninguna'}" + (" …" if len(c[k]) > 40 else ""))
    mil = info.get("militar", {})
    L += ["", "## Capa militar (control)",
          f"- Estado: {mil.get('estado', 'ausente')} · polígonos: {mil.get('poligonos', 0)} · área: {mil.get('area_km2', '—')} km² · "
          f"fuente: {mil.get('fuente', '—')} ({mil.get('fecha_descarga', '—')})",
          f"- Celdas con instalación: {mil.get('celdas_con_instalacion', 0)} · en franja: {mil.get('celdas_en_franja', 0)}",
          "- Limitación: huella física de OpenStreetMap, NO el perímetro legal; puede estar incompleta."]
    L += ["", "## Capas de la rúbrica (activa = cobertura ≥ umbral configurado)", "",
          "| Capa | Tipo | Columna | Cobertura | Activa |", "|---|---|---|---|---|"]
    for k, v in capas["capas"].items():
        L.append(f"| {k} | {v['tipo']} | `{v['columna']}` | {v['cobertura']:.0%} | {'sí' if v['activa'] else '**no**'} |")
    L.append(f"\nParte del peso de criterios con capa activa: {capas['fraccion_peso_activo']:.0%}.")
    usadas = met.get("variables_usadas", [])
    nuevas_mod = [x for x in usadas if x in (c.get("nuevas") or [])]
    L += ["", "## Experimento de modelo (no alimenta el mapa salvo que supere la regla de decisión)",
          f"- Variables usadas: {len(usadas)}; de ellas nuevas: {nuevas_mod or 'ninguna'} (revisar a mano)",
          f"- Descartadas por filtros automáticos: {len(met.get('variables_descartadas', {}))}"]
    if not met.get("huella_datos") or met.get("huella_datos") != info["huella"]:
        L.append("- **Aviso:** las métricas son de otros datos (ejecuta el paso `evaluacion`).")
    L += ["", "## Avisos"] + [f"- {a}" for a in (info["avisos"] + avisos_exp)] if (info["avisos"] + avisos_exp) \
        else ["", "## Avisos", "- Ninguno"]
    return "\n".join(L) + "\n"


def main():
    cfg = R.cargar_config()
    cc = columnas()
    idc, lonc, latc = cc["identificador"]["columna"], cc["coordenadas"]["lon"]["columna"], cc["coordenadas"]["lat"]["columna"]
    provc, comc = cc["admin"]["provincia"]["columna"], cc["admin"]["comunidad"]["columna"]
    out_dir = salida()
    cells = pd.read_parquet(out_dir / "celdas.parquet")
    rub = pd.read_parquet(out_dir / "rubrica.parquet")
    info = json.loads((out_dir / "informe_carga.json").read_text(encoding="utf-8"))
    capas = json.loads((out_dir / "rubrica_capas.json").read_text(encoding="utf-8"))
    f_met = out_dir / "metricas.json"
    if not f_met.exists():
        f_met = web_datos() / "metricas.json"
    met = json.loads(f_met.read_text(encoding="utf-8")) if f_met.exists() else {"modelo_entra_al_mapa": False}
    assert (cells[idc].to_numpy() == rub[idc].to_numpy()).all(), "celdas y rúbrica desalineadas"
    df = pd.concat([cells, rub.drop(columns=idc)], axis=1)
    efectiva, _ = R.config_efectiva(cells, cfg)
    crit = efectiva["criterios"]
    avisos = []

    afin = None
    if met.get("modelo_entra_al_mapa") and met.get("huella_datos") == info["huella"] and (out_dir / "afinidad.parquet").exists():
        afin = df[[idc]].merge(pd.read_parquet(out_dir / "afinidad.parquet"), on=idc, how="left")["afinidad_pct"]

    # ---------------------------------------------------------------- salida por celda (contrato)
    sal = pd.DataFrame({
        "site_id": df[idc], "lon": df[lonc].round(5), "lat": df[latc].round(5),
        "comunidad": df[comc], "provincia": df[provc], "estado": df.estado,
        "score_pct": df.score_pct, "nota_rubrica": df.score, "cobertura": df.cobertura, "confianza": df.confianza,
        "motivos": df.motivos, "exclusiones": df.exclusiones, "capas_faltan": df.capas_faltan,
        "dc_real": df.dc_real, "dc_fuente": df.dc_fuente, "dc_nombres": df.get("sites", "")})
    if afin is not None:
        sal["afinidad_pct"] = afin
    sal.to_parquet(out_dir / "salida_celdas.parquet", index=False)
    sal.to_csv(out_dir / "salida_celdas.csv", index=False)

    # ---------------------------------------------------------------- carga inicial del mapa
    provs = sorted(df[provc].unique())
    pidx = {p: k for k, p in enumerate(provs)}
    texts = _textos_motivo(cfg)
    codes = list(texts)
    cidx = {c: k for k, c in enumerate(codes)}
    m = np.full((len(df), 3), -1, dtype=int)
    for k, s in enumerate(df.motivos):
        for q, c in enumerate([x for x in s.split("|") if x][:3]):
            m[k, q] = cidx[c]
    dcode = df.dc_fuente.map({"": 0, "datacentermap": 1, "OSM/PeeringDB": 2, "ambas": 3}).fillna(0).astype(int)
    geo = _geometria(df, idc, lonc, latc, avisos)
    cambios = info["cambios"]
    hay_cambios = (not cambios.get("primera_ejecucion")) and (
        any(cambios.get(k) for k in ("nuevas", "desaparecidas", "tipo_cambiado", "rango_cambiado", "cobertura_cambiada"))
        or cambios.get("filas_antes") != cambios.get("filas_ahora"))
    inactivas = [k for k, v in capas["capas"].items() if not v["activa"]]
    # ---------------------------------------------------------------- capa militar: control y capa del mapa
    pf = perfil()
    mil = json.loads((out_dir / "capa_militar.json").read_text(encoding="utf-8")) if (out_dir / "capa_militar.json").exists() \
        else {"estado": "ausente"}
    ant_f = web_datos() / "meta_militar.json"
    mil_ant = json.loads(ant_f.read_text(encoding="utf-8")) if ant_f.exists() else {}
    umbral_caida = pf.get("militar", {}).get("caida_alerta_pct", 20)
    if mil.get("estado") == "ausente":
        avisos.append("Capa militar AUSENTE: restricción militar no verificada (baja la confianza de todas las celdas).")
    elif mil.get("estado") == "vacia" or not mil.get("poligonos"):
        avisos.append("ALERTA: la capa militar ha llegado VACÍA (0 polígonos).")
    elif mil_ant.get("poligonos") and mil["poligonos"] < mil_ant["poligonos"] * (1 - umbral_caida / 100):
        avisos.append(f"ALERTA: la capa militar ha caído de {mil_ant['poligonos']} a {mil['poligonos']} polígonos "
                      f"(más del {umbral_caida} %).")
    from militar import archivo_capa

    pct_cand = 100 * float((df.estado == "Candidata").mean()) if len(df) else 0
    lo, hi = cfg["salida"].get("rango_candidatas_pct", [0, 100])
    if not lo <= pct_cand <= hi:
        avisos.append(f"Candidatas = {pct_cand:.1f} % de las celdas, fuera del rango razonable [{lo}, {hi}] %: "
                      "revisar la rúbrica (¿demasiado laxa o estricta?).")

    meta = {
        "fecha_datos": _fecha_datos(), "huella": info["huella"], "celdas": len(df),
        "umbral_candidata": cfg["salida"]["umbral_candidata"], "margen_duda": cfg["salida"]["margen_duda"],
        "modelo_en_mapa": afin is not None, "capas_no_disponibles": cfg.get("capas_no_disponibles", []),
        "capas_omitidas": inactivas, "datos_cambiados": bool(hay_cambios),
        "resumen_cambios": {k: cambios.get(k) for k in ("nuevas", "desaparecidas", "tipo_cambiado")} if hay_cambios else {},
        "avisos": (info["avisos"] + avisos)[:20],
        "pais": pf["pais"], "nombre_pais": pf.get("nombre", pf["pais"]), "division": pf.get("etiqueta_division", "provincia"),
        "militar": {k: mil.get(k) for k in ("estado", "fuente", "licencia", "fecha_descarga", "poligonos", "area_km2",
                                            "celdas_con_instalacion", "celdas_en_franja")},
        "limitaciones": cfg.get("_limitaciones", []),
        "atribucion": pf.get("atribucion", ""),
        "pct_candidatas": round(pct_cand, 2),
    }
    cells_json = {
        "e": df.estado.map({e: k for k, e in enumerate(R.ESTADOS)}).astype(int).tolist(),
        "s": _int(df.score_pct), "n": _int(df.score), "c": _int(df.cobertura * 100),
        "p": df[provc].map(pidx).astype(int).tolist(), "d": dcode.tolist(), "m": m.ravel().tolist(),
        "x": df.excluida.astype(int).tolist(),
    }
    if geo["modo"] == "rejilla":
        cells_json.update({"i": geo["i"], "j": geo["j"]})
    else:
        cells_json.update({"ids": geo["ids"], "lon": geo["lon"], "lat": geo["lat"], "hl": geo["medio_lado_lon"]})
    if afin is not None:
        cells_json["a"] = _int(afin)
    main_json = {"meta": meta, "geometria": geo["modo"], "estados": R.ESTADOS, "provincias": provs,
                 "comunidades": [str(df.loc[df[provc] == p, comc].iloc[0]) for p in provs],
                 "motivos": [texts[c] for c in codes], "motivo_codigos": codes,
                 "criterios": [{"id": c["id"], "etiqueta": c["etiqueta"], "unidad": c["unidad"],
                                "peso": round(c["peso"], 2), "columna": c["columna"]} for c in crit],
                 "cells": cells_json}
    if geo["modo"] == "rejilla":
        main_json["nodes"] = geo["nodes"]
    else:
        main_json["medio_lado_lat"] = geo["medio_lado"][0]

    # ---------------------------------------------------------------- detalle por provincia
    web = web_datos()
    web.mkdir(parents=True, exist_ok=True)
    (web / "prov").mkdir(parents=True, exist_ok=True)
    for old in (web / "prov").glob("*.json"):
        old.unlink()
    raw_cols = [c["columna"] for c in crit]
    ok = ~df.excluida
    nota_esp = round(float(df.loc[ok, "score"].mean()), 1) if ok.any() else None
    for p, k in pidx.items():
        sub = df[df[provc] == p]
        okp = sub[~sub.excluida]
        det = {"provincia": p, "comunidad": str(sub[comc].iloc[0]),
               "media_nota": round(float(okp.score.mean()), 1) if len(okp) else None, "media_nota_espana": nota_esp,
               "media_valores": [None if okp[c].isna().all() else round(float(okp[c].mean()), 2) for c in raw_cols],
               "criterios": [{"etiqueta": c["etiqueta"], "unidad": c["unidad"], "peso": round(c["peso"], 2)} for c in crit],
               "motivos_textos": main_json["motivos"], "celdas": {}}
        V = sub[raw_cols].to_numpy(dtype=float)
        S = sub[[f"sub_{c['id']}" for c in crit]].to_numpy(dtype=float)
        for row, (idx, r) in enumerate(sub.iterrows()):
            det["celdas"][str(idx)] = {
                "id": r[idc], "lon": round(float(r[lonc]), 4), "lat": round(float(r[latc]), 4),
                "v": [None if np.isnan(x) else round(float(x), 3) for x in V[row]],
                "sub": [round(float(x), 1) for x in S[row]], "pen": float(r.penalizacion),
                "nota_bruta": float(r.score_bruto), "excl": r.exclusiones, "faltan": r.capas_faltan,
                "avisos_equipo": r.get("avisos_equipo", "") if isinstance(r.get("avisos_equipo", ""), str) else "",
                "dc": r.get("sites", "") or "", "dc_fuente": r.dc_fuente,
                "inv_eur_m2": None if pd.isna(r.get("inversion_eur_m2", np.nan)) else round(float(r["inversion_eur_m2"])),
                "nota_modelo_equipo": None if pd.isna(r.get("equipo_score_pct", np.nan)) else round(float(r["equipo_score_pct"])),
                "estado": r.estado, "score_pct": None if pd.isna(r.score_pct) else round(float(r.score_pct)),
                "nota": round(float(r.score), 1), "cobertura": round(float(r.cobertura), 2),
                "motivos": [cidx[c] for c in r.motivos.split("|") if c],
                "mil": [None if pd.isna(r.get(c, np.nan)) else round(float(r[c]), 3)
                        for c in ("militar_pct", "distancia_militar_km", "en_franja")]}
        (web / "prov" / f"{k}.json").write_text(json.dumps(det, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---------------------------------------------------------------- DC, métricas, esquema, informe
    dc = pd.read_csv(out_dir / "dc_puntos.csv")
    osm = df[df.dc_fuente == "OSM/PeeringDB"]
    dc_json = {"puntos": [{"n": str(r.get("site", "")), "o": r.get("operators") if isinstance(r.get("operators"), str) else "",
                           "mun": str(r.get("municipio", "")), "st": str(r.get("status", "")), "prec": str(r.get("precision", "")),
                           "lat": float(r["lat"]), "lon": float(r["lon"])} for _, r in dc.iterrows()],
               "celdas_osm": [[round(float(a), 4), round(float(b), 4)] for a, b in zip(osm[lonc], osm[latc])],
               "fuente": "datacentermap.com (geocodificado a mano) + OSM/PeeringDB (ELT)"}
    info["militar"] = mil
    informe = _informe(info, capas, avisos, met)
    (out_dir / "informe_datos.md").write_text(informe, encoding="utf-8")
    escritos = {  # (más meta_militar.json, abajo)
        "dc.json": json.dumps(dc_json, ensure_ascii=False, separators=(",", ":")),
        "metricas.json": json.dumps(met, ensure_ascii=False, indent=1),
        "esquema.json": json.dumps({"celdas": len(df), "huella": info["huella"], "columnas": info["esquema"]},
                                   ensure_ascii=False, indent=0, sort_keys=True),
        "informe_datos.md": informe,
        "celdas.json": json.dumps(main_json, ensure_ascii=False, separators=(",", ":")),
    }
    escritos["meta_militar.json"] = json.dumps(mil, ensure_ascii=False, indent=1, sort_keys=True)
    for nombre, texto in escritos.items():
        (web / nombre).write_text(texto, encoding="utf-8")
    if archivo_capa().exists():
        shutil.copyfile(archivo_capa(), web / "militar.geojson")
    else:
        (web / "militar.geojson").unlink(missing_ok=True)
    # índice de países con datos (el mapa carga solo el elegido)
    idx_f = ruta("web") / "data" / "paises.json"
    idx = json.loads(idx_f.read_text(encoding="utf-8")) if idx_f.exists() else {}
    idx[web.name] = {"nombre": pf.get("nombre", pf["pais"]), "iso3": pf["pais"], "celdas": len(df),
                     "fecha_datos": meta["fecha_datos"], "huella": info["huella"], "division": meta["division"],
                     "limites": [[round(float(df[lonc].min()), 2), round(float(df[latc].min()), 2)],
                                 [round(float(df[lonc].max()), 2), round(float(df[latc].max()), 2)]]}
    idx = {k: idx[k] for k in sorted(idx) if (ruta("web") / "data" / k / "celdas.json").exists()}
    idx_f.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------------------------------------------------------- copia dentro de la web de Dani
    destino = ruta("web_integrada")
    if str(destino) not in ("", ".") and destino.parent.exists():
        if destino.exists():
            shutil.rmtree(destino)
        origen = ruta("web")
        shutil.copytree(origen, destino, ignore=shutil.ignore_patterns(
            "node_modules", "functions", "package.json", "package-lock.json", ".dev.vars", ".wrangler"))
        print(f"mapa copiado a {destino}")

    sizes = {f.relative_to(web).as_posix(): f.stat().st_size / 1e6 for f in web.rglob("*.json")}
    print(f"salida_celdas: {len(sal):,} filas · estados {sal.estado.value_counts().to_dict()}")
    print(f"web: celdas.json {sizes['celdas.json']:.2f} MB · prov/ {sum(v for k, v in sizes.items() if k.startswith('prov')):.2f} MB "
          f"· geometría {geo['modo']} · datos cambiados: {hay_cambios}")
    if sizes["celdas.json"] > MAX_MB:
        raise SystemExit(f"celdas.json supera {MAX_MB} MB")


if __name__ == "__main__":
    main()
