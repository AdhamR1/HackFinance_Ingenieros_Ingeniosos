"""Paso 1 · CARGA: una fila por celda con todo lo disponible, tolerante a cambios en los datos.

Uso:  angel_modelo/.venv/bin/python angel_modelo/src/actualizar.py carga
Escribe en la carpeta de salida: celdas.parquet, esquema.json, informe_carga.json, dc_puntos.csv.

Qué hace, en orden:
  1. Lee las tablas del ELT con el código del equipo (pipeline/src/cells.py: read_elt); si no se puede
     importar, usa un lector equivalente y lo avisa.
  2. Resuelve alias de columnas (config/columnas.yaml). Sin identificador o sin coordenadas: ERROR FATAL.
  3. Deduplica por celda (y fecha si existe) quedándose con lo más reciente; agrega lo anual (media o último).
  4. Une las capas del pipeline (feat_*.parquet: ganan al ELT), exclusiones, finanzas y etiquetas (opcionales).
  5. Convierte texto numérico a número (tipo cambiado), pasa a "sin dato" lo fuera de rango plausible.
  6. Clasifica cada columna, mide su cobertura, calcula la huella de los datos y compara con el esquema
     publicado (web_mapa/data/esquema.json) para el informe de cambios.
"""
from __future__ import annotations

import glob
import hashlib
import json
import re
import sys
import warnings

import numpy as np
import pandas as pd

from configuracion import ErrorFatal, columnas, ruta, salida, web_datos

AVISOS: list[str] = []


def aviso(msg: str):
    AVISOS.append(msg)
    print("  AVISO:", msg, flush=True)


# --------------------------------------------------------------------------- lectura
def _lector_equipo():
    """read_elt de pipeline/src/cells.py, apuntando a la carpeta de datos configurada."""
    src = ruta("pipeline_src")
    try:
        sys.path.insert(0, str(src))
        import cells  # noqa: PLC0415  (código del equipo)

        cells.ELT_DATASET = ruta("elt_dataset")
        cells.ISO = columnas()["pais"]          # el lector filtra <ISO>-p*.parquet
        return cells.read_elt, "pipeline/src/cells.py:read_elt"
    except Exception as e:  # noqa: BLE001
        aviso(f"No se pudo importar el lector del equipo ({e}); se usa un lector equivalente")

        def leer(tabla, columns=None):
            files = sorted((ruta("elt_dataset") / tabla).glob(f"{columnas()['pais']}-p*.parquet"))
            if not files:
                raise FileNotFoundError(tabla)
            return pd.concat([pd.read_parquet(f, columns=columns) for f in files], ignore_index=True)

        return leer, "lector propio"


def _comprobar_lfs(carpeta):
    for f in glob.glob(str(carpeta / "**" / "*.parquet"), recursive=True):
        with open(f, "rb") as fh:
            if fh.read(200).find(b"git-lfs") >= 0:
                raise ErrorFatal(f"{f} es un puntero de Git LFS. Ejecuta: git lfs install && git lfs pull")


def _renombrar_alias(df: pd.DataFrame) -> pd.DataFrame:
    cfg = columnas()
    pares = {cfg["identificador"]["columna"]: cfg["identificador"]["alias"]}
    for d in [cfg["coordenadas"]["lon"], cfg["coordenadas"]["lat"], cfg["admin"]["provincia"], cfg["admin"]["comunidad"]]:
        pares[d["columna"]] = d["alias"]
    pares.update(cfg.get("alias", {}))
    ren = {}
    for canon, alias in pares.items():
        if canon in df.columns:
            continue
        for a in alias or []:
            if a in df.columns:
                ren[a] = canon
                aviso(f"columna '{a}' leída como '{canon}' (alias)")
                break
    return df.rename(columns=ren)


def _a_numero(df: pd.DataFrame, cambios_tipo: list) -> pd.DataFrame:
    """Columnas de texto que casi siempre son números (tipo cambiado aguas arriba) -> número."""
    for c in df.columns:
        s = df[c]
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            nn = s.dropna()
            if len(nn) == 0:
                continue
            num = pd.to_numeric(nn.astype(str).str.replace(",", ".", regex=False), errors="coerce")
            if num.notna().mean() >= 0.9:
                df[c] = pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")
                cambios_tipo.append(c)
    return df


def _numericas(df: pd.DataFrame) -> pd.DataFrame:
    keep = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c])]
    out = {}
    for c in keep:
        s = df[c]
        if s.dtype == "boolean" or s.dtype == bool:
            s = s.astype("Float64")
        out[c] = pd.to_numeric(s, errors="coerce").astype(float)
    return pd.DataFrame(out, index=df.index)


def _dedup(df: pd.DataFrame, idc: str, nombre: str, stats: dict) -> pd.DataFrame:
    fechas = [c for c in columnas()["agregacion_temporal"]["columnas_fecha_dedup"] if c in df.columns]
    clave = [idc] + fechas
    n0 = len(df)
    if fechas:
        df = df.sort_values(fechas, kind="stable")
    df = df.drop_duplicates(subset=clave, keep="last")
    if len(df) < n0:
        aviso(f"{nombre}: {n0 - len(df)} filas duplicadas (misma celda{' y fecha' if fechas else ''}); se queda la última")
    stats[f"duplicadas_{nombre}"] = int(n0 - len(df))
    return df


def _rango(col: str):
    r = columnas()["rangos"]
    if col in r["por_columna"]:
        return r["por_columna"][col]
    for pat, lo, hi in r["por_patron"]:
        if re.search(pat, col):
            return [lo, hi]
    return None


def leer_csv(f) -> pd.DataFrame:
    """CSV en UTF-8; si no lo es (p. ej. atributos de MLIT en Shift_JIS/CP932), se reintenta en CP932 y se avisa."""
    try:
        return pd.read_csv(f, encoding="utf-8")
    except UnicodeDecodeError:
        aviso(f"{f.name} no está en UTF-8: se ha leído como CP932 (Shift_JIS) y se convierte a UTF-8")
        return pd.read_csv(f, encoding="cp932")


def _clasificar(df: pd.DataFrame, idc: str) -> dict:
    cfg = columnas()["clasificacion"]
    out = {}
    for c in df.columns:
        s = df[c]
        if c == idc or c in cfg["identificadores"]:
            k = "identificador"
        elif c in cfg["coordenadas"]:
            k = "coordenada"
        elif pd.api.types.is_datetime64_any_dtype(s):
            k = "fecha"
        elif s.nunique(dropna=True) <= 1:
            k = "constante"
        elif pd.api.types.is_bool_dtype(s) or (pd.api.types.is_numeric_dtype(s) and set(s.dropna().unique()) <= {0, 1}):
            k = "booleana"
        elif pd.api.types.is_numeric_dtype(s):
            k = "numerica"
        else:
            k = "categorica"
        out[c] = k
    return out


def _huella(df: pd.DataFrame, idc: str) -> dict:
    esquema = "|".join(f"{c}:{df[c].dtype}" for c in sorted(df.columns))
    num = df.select_dtypes("number").round(6)
    filas = pd.util.hash_pandas_object(pd.concat([df[[idc]], num], axis=1).sort_values(idc), index=False)
    return {"esquema": hashlib.sha256(esquema.encode()).hexdigest()[:12],
            "filas": hashlib.sha256(filas.values.tobytes()).hexdigest()[:12]}


# --------------------------------------------------------------------------- principal
def cargar() -> tuple[pd.DataFrame, dict]:
    AVISOS.clear()
    cfg = columnas()
    idc = cfg["identificador"]["columna"]
    lonc, latc = cfg["coordenadas"]["lon"]["columna"], cfg["coordenadas"]["lat"]["columna"]
    provc, comc = cfg["admin"]["provincia"]["columna"], cfg["admin"]["comunidad"]["columna"]
    stats: dict = {}
    cambios_tipo: list = []

    elt = ruta("elt_dataset")
    if not elt.exists():
        raise ErrorFatal(f"no existe la carpeta de datos del ELT: {elt}")
    _comprobar_lfs(elt)
    leer, lector = _lector_equipo()
    stats["lector"] = lector

    try:
        st = leer(cfg["tablas"]["estatica"])
    except FileNotFoundError:
        raise ErrorFatal(f"no hay tabla '{cfg['tablas']['estatica']}' en {elt}") from None
    st = _renombrar_alias(st)
    if idc not in st.columns:
        raise ErrorFatal(f"la tabla estática no tiene identificador de celda ('{idc}' ni sus alias)")
    if lonc not in st.columns or latc not in st.columns:
        raise ErrorFatal(f"la tabla estática no tiene coordenadas ('{lonc}', '{latc}' ni sus alias)")
    stats["filas_leidas_estatica"] = len(st)
    st = _a_numero(st, cambios_tipo)
    st = _dedup(st, idc, "estatica", stats)
    st = st.dropna(subset=[idc, lonc, latc])
    for c, defecto in [(provc, "Sin provincia"), (comc, "Sin comunidad")]:
        if c not in st.columns:
            aviso(f"falta la columna '{c}': se usa '{defecto}'")
            st[c] = defecto
        st[c] = st[c].fillna(defecto).astype(str)

    base = st[list(dict.fromkeys([idc, lonc, latc, comc, provc]))].copy()
    feats = _numericas(st.set_index(idc))

    # anual -> una fila por celda
    tcol = cfg["agregacion_temporal"]["columna_tiempo"]
    try:
        yr = _renombrar_alias(leer(cfg["tablas"]["anual"]))
        yr = _a_numero(yr, cambios_tipo)
        yr = _dedup(yr, idc, "anual", stats)
        num = _numericas(yr.drop(columns=[c for c in [tcol] if c in yr.columns]))
        num[idc] = yr[idc].to_numpy()
        if cfg["agregacion_temporal"]["metodo"] == "ultimo" and tcol in yr.columns:
            num[tcol] = yr[tcol].to_numpy()
            agg = num.sort_values(tcol).groupby(idc).last().drop(columns=tcol)
        else:
            agg = num.groupby(idc).mean()
        stats["anios_disponibles"] = sorted(int(x) for x in yr[tcol].dropna().unique()) if tcol in yr.columns else []
        feats = feats.join(agg, how="left", rsuffix="_anual")
    except FileNotFoundError:
        aviso(f"no hay tabla '{cfg['tablas']['anual']}': se sigue sin datos anuales")

    # capas del pipeline (ganan al ELT)
    proc = ruta("pipeline_processed")
    capas = {}
    for f in sorted(proc.glob(cfg["tablas"]["capas_pipeline"])):
        d = _renombrar_alias(pd.read_parquet(f))
        if idc not in d.columns:
            aviso(f"{f.name} no tiene '{idc}': se ignora")
            continue
        d = _dedup(_a_numero(d, cambios_tipo), idc, f.stem, stats).set_index(idc)
        extra = _numericas(d)
        capas[f.stem] = list(extra.columns)
        feats = feats.drop(columns=[c for c in extra.columns if c in feats.columns]).join(extra, how="left")
    # capas propias de este módulo (p. ej. capas/militar.parquet de src/militar.py)
    for f in sorted((salida() / "capas").glob("*.parquet")):
        d = _dedup(pd.read_parquet(f), idc, f"capa_{f.stem}", stats).set_index(idc)
        extra = _numericas(d)
        capas[f"propia_{f.stem}"] = list(extra.columns)
        feats = feats.drop(columns=[c for c in extra.columns if c in feats.columns]).join(extra, how="left")
    stats["capas_pipeline"] = capas
    feats = feats.drop(columns=[c for c in (lonc, latc) if c in feats.columns])

    df = base.merge(feats.reset_index().rename(columns={"index": idc}), on=idc, how="left")

    def opcional(nombre, cols, carpeta=proc):
        f = carpeta / cfg["tablas"][nombre]
        if not f.exists():
            aviso(f"falta {f.name}: lo que depende de ella queda 'no disponible'")
            return None
        d = _renombrar_alias(pd.read_parquet(f))
        d = _dedup(d, idc, nombre, stats)
        presentes = [c for c in cols if c in d.columns]
        if len(presentes) < len(cols):
            aviso(f"{f.name}: faltan columnas {sorted(set(cols) - set(presentes))}")
        return d[[idc] + presentes]

    ex = opcional("exclusiones_equipo", ["excluded", "motivo_descarte", "avisos"])
    if ex is not None:
        df = df.merge(ex.rename(columns={"excluded": "excl_equipo", "motivo_descarte": "motivo_equipo",
                                         "avisos": "avisos_equipo"}), on=idc, how="left")
    fin = opcional("finanzas", ["inversion_eur_m2"])
    if fin is not None:
        df = df.merge(fin, on=idc, how="left")
    lab = opcional("etiquetas", ["y", "sites"])
    if lab is not None:
        df = df.merge(lab, on=idc, how="left")
    sc = opcional("notas_equipo", ["score_pct", "oof_spatial_pct"])
    if sc is not None:
        df = df.merge(sc.rename(columns={"score_pct": "equipo_score_pct", "oof_spatial_pct": "equipo_oof_pct"}),
                      on=idc, how="left")
    for c, v in [("avisos_equipo", ""), ("sites", ""), ("motivo_equipo", "")]:
        df[c] = df[c].fillna(v) if c in df.columns else v

    df = df.copy()                                      # desfragmenta tras las uniones
    # data centers: unión de las dos listas
    dcp = df["y"].fillna(0).astype(bool) if "y" in df.columns else pd.Series(False, index=df.index)
    elt_col = cfg["data_centers"]["elt"]["columna"]
    if elt_col in st.columns:
        dce = df[[idc]].merge(st[[idc, elt_col]], on=idc, how="left")[elt_col]
        dce = dce.astype("boolean").fillna(False).astype(bool).to_numpy()
    else:
        aviso(f"la tabla estática no tiene '{elt_col}': solo se usa la lista de datacentermap")
        dce = np.zeros(len(df), bool)
    df["dc_pipeline"], df["dc_elt"] = dcp.to_numpy(), dce
    # Lista maestra (tarea 4c): una celda OSM/PeeringDB es el MISMO data center que uno de datacentermap si su
    # centroide está a menos de un lado de celda de la celda de datacentermap más cercana -> no se cuenta dos veces.
    tol_km = float(cfg["rejilla"]["tamano_celda_m"]) / 1000
    pts = df.loc[df.dc_pipeline, [latc, lonc]].to_numpy()
    solo_elt = df.dc_elt.to_numpy() & ~df.dc_pipeline.to_numpy()
    duplicada = np.zeros(len(df), bool)
    if len(pts) and solo_elt.any():
        la, lo = np.radians(df.loc[solo_elt, latc].to_numpy())[:, None], np.radians(df.loc[solo_elt, lonc].to_numpy())[:, None]
        pla, plo = np.radians(pts[:, 0])[None, :], np.radians(pts[:, 1])[None, :]
        d = 2 * 6371 * np.arcsin(np.sqrt(np.sin((pla - la) / 2) ** 2 + np.cos(la) * np.cos(pla) * np.sin((plo - lo) / 2) ** 2))
        duplicada[np.flatnonzero(solo_elt)] = d.min(axis=1) <= tol_km
    df["dc_real"] = df["dc_pipeline"] | (df["dc_elt"] & ~duplicada)
    stats["dc_elt_duplicadas_de_datacentermap"] = int(duplicada.sum())
    df["dc_fuente"] = np.select([df.dc_pipeline & df.dc_elt, df.dc_pipeline, df.dc_elt],
                                ["ambas", "datacentermap", "OSM/PeeringDB"], "")
    df = df.drop(columns=[c for c in ["y"] if c in df.columns])

    # rangos plausibles -> sin dato
    fuera = {}
    for c in df.select_dtypes("number").columns:
        r = _rango(c)
        if r is None:
            continue
        mal = (df[c] < r[0]) | (df[c] > r[1])
        if mal.any():
            fuera[c] = int(mal.sum())
            df.loc[mal, c] = np.nan
    if fuera:
        aviso(f"valores fuera de rango plausible pasados a 'sin dato': {fuera}")

    df = df.sort_values(idc, kind="stable").reset_index(drop=True)
    stats.update({"celdas": len(df), "fuera_de_rango": fuera, "tipo_cambiado": sorted(set(cambios_tipo)),
                  "pais": cfg["pais"],
                  "provincias": int(df[provc].nunique()),
                  "dc": {"datacentermap": int(df.dc_pipeline.sum()), "osm_peeringdb": int(df.dc_elt.sum()),
                         "ambas": int((df.dc_pipeline & df.dc_elt).sum()), "lista_maestra": int(df.dc_real.sum())}})

    # esquema, clases, cobertura y huella
    clases = _clasificar(df, idc)
    esquema = {c: {"tipo": str(df[c].dtype), "clase": clases[c],
                   "cobertura": round(float(df[c].notna().mean()), 4),
                   **({"min": round(float(df[c].min()), 4), "max": round(float(df[c].max()), 4)}
                      if pd.api.types.is_numeric_dtype(df[c]) and df[c].notna().any() else {})}
               for c in df.columns}
    huella = _huella(df, idc)
    return df, {"stats": stats, "esquema": esquema, "huella": huella, "avisos": list(AVISOS)}


def comparar(esquema: dict, anterior: dict | None, ids_ant: int | None, n: int) -> dict:
    """Diferencias con el esquema publicado: columnas nuevas, desaparecidas, tipo y rango cambiados."""
    if not anterior:
        return {"primera_ejecucion": True}
    nuevas = sorted(set(esquema) - set(anterior))
    fuera = sorted(set(anterior) - set(esquema))
    tipo, rango, cob = [], [], []
    for c in sorted(set(esquema) & set(anterior)):
        a, b = anterior[c], esquema[c]
        if a.get("tipo") != b.get("tipo"):
            tipo.append(f"{c}: {a.get('tipo')} -> {b.get('tipo')}")
        if "min" in a and "min" in b:
            span = max(abs(a["max"] - a["min"]), 1e-9)
            if abs(a["min"] - b["min"]) > 0.25 * span or abs(a["max"] - b["max"]) > 0.25 * span:
                rango.append(f"{c}: [{a['min']}, {a['max']}] -> [{b['min']}, {b['max']}]")
        if abs(a.get("cobertura", 0) - b.get("cobertura", 0)) >= 0.05:
            cob.append(f"{c}: {a.get('cobertura', 0):.0%} -> {b.get('cobertura', 0):.0%}")
    return {"primera_ejecucion": False, "nuevas": nuevas, "desaparecidas": fuera, "tipo_cambiado": tipo,
            "rango_cambiado": rango, "cobertura_cambiada": cob,
            "filas_antes": ids_ant, "filas_ahora": n}


def main():
    df, info = cargar()
    out = salida()
    web_data = web_datos()
    anterior = None
    f_ant = web_data / "esquema.json"
    if f_ant.exists():
        anterior = json.loads(f_ant.read_text(encoding="utf-8"))
    info["cambios"] = comparar(info["esquema"], (anterior or {}).get("columnas"), (anterior or {}).get("celdas"), len(df))
    pts = ruta("pipeline_raw") / columnas()["tablas"]["dc_puntos"]
    if pts.exists():
        p = leer_csv(pts).dropna(subset=["lat", "lon"])
        p[[c for c in ["site", "operators", "municipio", "status", "precision", "lat", "lon"] if c in p.columns]].to_csv(
            out / "dc_puntos.csv", index=False)
    else:
        aviso(f"falta {pts}: el mapa no mostrará puntos de datacentermap")
        pd.DataFrame(columns=["site", "lat", "lon"]).to_csv(out / "dc_puntos.csv", index=False)
    info["avisos"] = list(AVISOS)              # incluye los avisos de la lectura de los puntos (p. ej. CP932)
    df.to_parquet(out / "celdas.parquet", index=False)
    (out / "informe_carga.json").write_text(json.dumps(info, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    s = info["stats"]
    print(f"celdas={s['celdas']:,}  columnas={df.shape[1]}  provincias={s['provincias']}  DC={s['dc']}  "
          f"huella={info['huella']}  avisos={len(info['avisos'])}")


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    main()
