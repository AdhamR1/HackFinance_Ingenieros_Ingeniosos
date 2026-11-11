"""Prueba de aceptación en 9 escenarios de datos, siempre sobre COPIAS temporales (nunca toca el repo).

Uso (desde la raíz del repo, con el entorno creado según el README):
    angel_modelo/.venv/bin/python angel_modelo/tests/aceptacion.py [--escenarios 1,2,...,9] [--sin-web]

  1 actuales            los datos tal cual (todos los países)
  2 ampliados           + columnas nuevas y la capa `water_stress` (hoy vacía) rellena: SINTÉTICO, solo en la copia
  3 degradados          sin una columna existente, tipo cambiado, filas duplicadas y valores imposibles
  4 repetible           datos actuales dos veces: resultados idénticos byte a byte
  5 sin capa militar    -> «restricción militar no verificada», baja la confianza
  6 capa militar vacía  -> alerta en el informe
  7 solo España         sin nada de Japón: el pipeline y el mapa funcionan igual (Japón se salta con aviso)
  8 Japón parcial/CP932 sin una capa de Japón y con un CSV en Shift_JIS/CP932: avisos claros, sin errores
  9 huella de España    los resultados de España de (1) y (7) coinciden entre sí y con los publicados en el repo
Termina con código 1 si algo falla.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
AM = RAIZ / "angel_modelo"
PY = sys.executable
RES: list[tuple[str, bool, str]] = []
TABLAS_ETL = ("sites_static", "sites_yearly")          # lo que lee el mapa (el resto del ETL no hace falta copiarlo)
GUARDA: dict = {}


def check(nombre, ok, detalle=""):
    RES.append((nombre, bool(ok), detalle))
    print(f"  [{'OK' if ok else 'FALLO'}] {nombre} {detalle}", flush=True)


def copiar(dst: Path) -> dict:
    r = {"ELT_DATASET": dst / "etl", "PIPELINE_PROCESSED": dst / "proc", "PIPELINE_RAW": dst / "raw",
         "SALIDA": dst / "salida", "WEB": dst / "web", "WEB_INTEGRADA": "", "DATOS_PROPIOS": dst / "propios"}
    for t in TABLAS_ETL:
        shutil.copytree(RAIZ / "ETL" / "dataset" / t, r["ELT_DATASET"] / t)
    shutil.copytree(RAIZ / "Modelo" / "data" / "processed", r["PIPELINE_PROCESSED"])
    shutil.copytree(RAIZ / "Modelo" / "data" / "raw", r["PIPELINE_RAW"], ignore=shutil.ignore_patterns("cache"))
    shutil.copytree(AM / "web_mapa", r["WEB"], ignore=shutil.ignore_patterns("node_modules"))
    shutil.copytree(AM / "datos", r["DATOS_PROPIOS"])
    return r


def ejecutar(r: dict, paises: str = "", plan="sin_test") -> tuple[int, str]:
    env = dict(os.environ, MAPA_N_BOOT="100", **{"MAPA_" + k: str(v) for k, v in r.items()})
    env.pop("MAPA_PAISES", None)
    if paises:
        env["MAPA_PAISES"] = paises
    p = subprocess.run([PY, str(AM / "src" / "actualizar.py"), plan], cwd=RAIZ, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def web_ok(web: Path, pais="es") -> tuple[bool, str]:
    if shutil.which("node") is None:
        return True, "(sin Node: comprobación del navegador omitida)"
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([PY, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=web,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        p = subprocess.run(["node", str(AM / "tests" / "verificar_web.mjs"), f"http://127.0.0.1:{port}/#pais={pais}",
                            str(web / f"captura_{pais}.png")], capture_output=True, text=True, timeout=180)
        if "No se pudo arrancar Chrome" in p.stderr:
            return True, "(sin Chrome: comprobación del navegador omitida)"
        try:
            j = json.loads(p.stdout)
        except ValueError:
            return False, (p.stdout + p.stderr)[-300:]
        return j.get("ok", False), f"{pais}: celdas={j.get('celdas_dibujadas')} ms={j.get('ms_desde_navegacion_hasta_dibujar')} problemas={j.get('problemas')}"
    finally:
        srv.terminate()


def informe(r, pais="es"):
    f = r["SALIDA"] / pais / "informe_datos.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def huella(r, pais="es"):
    f = r["WEB"] / "data" / pais / "celdas.json"
    return hashlib.sha256(f.read_bytes()).hexdigest()[:16] if f.exists() else None


def comun(n, r, codigo, log, sin_web, paises=("es",)):
    check(f"{n}: el pipeline termina", codigo == 0, "" if codigo == 0 else log[-900:])
    for p in paises:
        check(f"{n}: informe_datos.md de {p}", bool(informe(r, p)))
        if not sin_web and codigo == 0:
            ok, det = web_ok(r["WEB"], p)
            check(f"{n}: el mapa de {p} carga sin errores de consola", ok, det)


def e1(t, sw):
    r = copiar(t); c, log = ejecutar(r)
    comun("E1 actuales", r, c, log, sw, ("es", "jp"))
    GUARDA["e1_es"] = huella(r, "es")
    txt = informe(r, "es")
    check("E1: capa militar presente y activa en España", "| militar | exclusiones | `militar_pct` |" in txt and "Estado: ok" in txt)


def e2(t, sw):
    r = copiar(t); rng = np.random.default_rng(0)
    for f in sorted((r["ELT_DATASET"] / "sites_static").glob("ESP-p*.parquet")):
        st = pd.read_parquet(f)
        st["sintetico_columna_nueva"] = rng.normal(size=len(st))            # SINTÉTICO
        st["water_stress"] = rng.uniform(0, 5, len(st))                     # SINTÉTICO: capa antes vacía
        st.to_parquet(f, index=False)
    c, log = ejecutar(r, "es"); comun("E2 ampliados (sintético)", r, c, log, sw)
    txt = informe(r)
    check("E2: lista las columnas nuevas", "sintetico_columna_nueva" in txt and "**Los datos han cambiado.**" in txt)
    check("E2: la capa antes vacía se activa sola", "| estres_hidrico | criterios | `water_stress` | 100% | sí |" in txt)


def e3(t, sw):
    r = copiar(t)
    for f in sorted((r["ELT_DATASET"] / "sites_yearly").glob("ESP-p*.parquet")):
        pd.read_parquet(f).drop(columns=["free_cooling_hours"]).to_parquet(f, index=False)
    for f in sorted((r["ELT_DATASET"] / "sites_static").glob("ESP-p*.parquet")):
        st = pd.read_parquet(f)
        st["slope_pct"] = st["slope_pct"].map(lambda v: f"{v:.3f}")
        st.loc[st.index[:7], "elevation_m"] = 99999.0
        pd.concat([st, st.head(25)]).to_parquet(f, index=False)
    c, log = ejecutar(r, "es"); comun("E3 degradados", r, c, log, sw)
    txt = informe(r)
    check("E3: columna desaparecida y criterio omitido", "free_cooling_hours" in txt and "| refrigeracion | criterios | `free_cooling_hours` | 0% | **no** |" in txt)
    check("E3: tipo cambiado, duplicados e imposibles", "slope_pct" in txt and "duplicadas_estatica" in txt and "elevation_m" in txt)


def e4(t, sw):
    ra, rb = copiar(t / "a"), copiar(t / "b")
    ca, la = ejecutar(ra); cb, lb = ejecutar(rb)
    check("E4: dos ejecuciones terminan", ca == 0 and cb == 0, (la + lb)[-600:] if ca or cb else "")
    ok = all(huella(ra, p) == huella(rb, p) for p in ("es", "jp")) and all(
        (ra["SALIDA"] / p / "salida_celdas.csv").read_bytes() == (rb["SALIDA"] / p / "salida_celdas.csv").read_bytes()
        for p in ("es", "jp"))
    check("E4: resultados idénticos byte a byte (España y Japón)", ok)


def e5(t, sw):
    r = copiar(t); (r["DATOS_PROPIOS"] / "militar" / "esp.geojson").unlink()
    c, log = ejecutar(r, "es"); comun("E5 sin capa militar", r, c, log, sw)
    txt = informe(r)
    check("E5: aviso «no verificada» y capa ausente", "Capa militar AUSENTE" in txt and "Estado: ausente" in txt)
    s = pd.read_parquet(r["SALIDA"] / "es" / "salida_celdas.parquet")
    check("E5: baja la confianza y lo lista en capas que faltan", s.capas_faltan.str.contains("militar\\(no verificada\\)").all()
          and s.cobertura.max() <= 0.92)


def e6(t, sw):
    r = copiar(t)
    (r["DATOS_PROPIOS"] / "militar" / "esp.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "meta": {"fuente": "PRUEBA vacía"}, "features": []}), encoding="utf-8")
    c, log = ejecutar(r, "es"); comun("E6 capa militar vacía", r, c, log, sw)
    check("E6: alerta de capa vacía", "ALERTA: la capa militar ha llegado VACÍA" in informe(r))


def e7(t, sw):
    r = copiar(t)
    for f in list(r["ELT_DATASET"].rglob("JPN-p*.parquet")):
        f.unlink()
    shutil.rmtree(r["PIPELINE_PROCESSED"] / "JPN")
    c, log = ejecutar(r)                                                    # todos los perfiles: Japón se salta
    comun("E7 solo España", r, c, log, sw)
    check("E7: Japón se salta con aviso", "AVISO: el país 'jp'" in log)
    idx = json.loads((r["WEB"] / "data" / "paises.json").read_text(encoding="utf-8"))
    check("E7: el mapa solo ofrece España", list(idx) == ["es"])
    GUARDA["e7_es"] = huella(r, "es")


def e8(t, sw):
    r = copiar(t)
    (r["PIPELINE_PROCESSED"] / "JPN" / "feat_infra.parquet").unlink()       # capa parcial: sin red eléctrica
    f = r["PIPELINE_RAW"] / "dc_sites_jp.csv"
    f.write_bytes(f.read_text(encoding="utf-8").encode("cp932", errors="replace"))   # atributos en Shift_JIS
    c, log = ejecutar(r, "jp"); comun("E8 Japón parcial y CP932", r, c, log, sw, ("jp",))
    txt = informe(r, "jp")
    check("E8: aviso de CP932", "CP932" in txt)
    check("E8: capa de subestación omitida con aviso", "| subestacion | criterios | `dist_substation_220kv_km` | 0% | **no** |" in txt)


def e9(t, sw):
    pub = hashlib.sha256((AM / "web_mapa" / "data" / "es" / "celdas.json").read_bytes()).hexdigest()[:16]
    check("E9: huella de España: E1 = E7 = publicada", GUARDA.get("e1_es") == GUARDA.get("e7_es") == pub,
          f"E1={GUARDA.get('e1_es')} E7={GUARDA.get('e7_es')} publicada={pub}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--escenarios", default="1,2,3,4,5,6,7,8,9")
    ap.add_argument("--sin-web", action="store_true")
    a = ap.parse_args()
    fns = {str(i): f for i, f in enumerate([e1, e2, e3, e4, e5, e6, e7, e8, e9], 1)}
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="aceptacion_mapa_") as d:
        for e in a.escenarios.split(","):
            print(f"\n=== Escenario {e} ===", flush=True)
            tmp = Path(d) / f"e{e}"
            tmp.mkdir()
            fns[e](tmp, a.sin_web)
            shutil.rmtree(tmp, ignore_errors=True)
    fallos = [x for x in RES if not x[1]]
    print(f"\n{len(RES) - len(fallos)}/{len(RES)} comprobaciones OK en {time.time() - t0:.0f} s")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
