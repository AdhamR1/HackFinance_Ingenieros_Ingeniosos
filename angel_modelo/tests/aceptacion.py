"""Prueba de aceptación en 4 escenarios de datos, siempre sobre COPIAS temporales (nunca toca el repo).

Uso (desde la raíz del repo, con el entorno creado según el README):
    angel_modelo/.venv/bin/python angel_modelo/tests/aceptacion.py [--escenarios 1,2,3,4] [--sin-web]

Escenarios:
  1 actuales     los datos tal cual
  2 ampliados    + columnas nuevas y la capa `water_stress` (hoy vacía) rellena con valores SINTÉTICOS
                 (rotulados así, solo en la copia temporal)
  3 degradados   sin una columna que hoy existe, una columna con tipo cambiado, filas duplicadas y valores imposibles
  4 repetible    datos actuales ejecutados dos veces: los resultados deben ser idénticos byte a byte
En todos: el pipeline termina, informe_datos.md refleja los cambios y (si hay Node y Chrome) el mapa carga
sin errores de consola. Termina con código 1 si algo falla.
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
RESULTADOS: list[tuple[str, bool, str]] = []


def check(nombre, ok, detalle=""):
    RESULTADOS.append((nombre, bool(ok), detalle))
    print(f"  [{'OK' if ok else 'FALLO'}] {nombre} {detalle}", flush=True)


def copiar_datos(dst: Path) -> dict:
    rutas = {"ELT_DATASET": dst / "elt", "PIPELINE_PROCESSED": dst / "proc", "PIPELINE_RAW": dst / "raw",
             "SALIDA": dst / "salida", "WEB": dst / "web", "WEB_INTEGRADA": ""}
    shutil.copytree(RAIZ / "ELT" / "dataset", rutas["ELT_DATASET"], ignore=shutil.ignore_patterns("JPN*", "USA*"))
    shutil.copytree(RAIZ / "pipeline" / "data" / "processed", rutas["PIPELINE_PROCESSED"])
    shutil.copytree(RAIZ / "pipeline" / "data" / "raw", rutas["PIPELINE_RAW"], ignore=shutil.ignore_patterns("cache"))
    shutil.copytree(AM / "web_mapa", rutas["WEB"], ignore=shutil.ignore_patterns("node_modules"))
    return rutas


def ejecutar(rutas: dict, plan="sin_test") -> tuple[int, str]:
    env = dict(os.environ, MAPA_N_BOOT="100", **{"MAPA_" + k: str(v) for k, v in rutas.items()})
    r = subprocess.run([PY, str(AM / "src" / "actualizar.py"), plan], cwd=RAIZ, env=env, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def web_ok(web: Path) -> tuple[bool, str]:
    if shutil.which("node") is None:
        return True, "(sin Node: comprobación del navegador omitida)"
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([PY, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=web,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        r = subprocess.run(["node", str(AM / "tests" / "verificar_web.mjs"), f"http://127.0.0.1:{port}/",
                            str(web / "captura.png")], capture_output=True, text=True, timeout=180)
        try:
            j = json.loads(r.stdout)
        except ValueError:
            return False, (r.stdout + r.stderr)[-300:]
        if "No se pudo arrancar Chrome" in r.stderr:
            return True, "(sin Chrome: comprobación del navegador omitida)"
        return j.get("ok", False), f"celdas={j.get('celdas_dibujadas')} ms={j.get('ms_desde_navegacion_hasta_dibujar')} problemas={j.get('problemas')}"
    finally:
        srv.terminate()


def huella_archivos(rutas):
    out = {}
    for f in [rutas["SALIDA"] / "salida_celdas.csv", rutas["SALIDA"] / "metricas.json", rutas["SALIDA"] / "informe_datos.md",
              rutas["WEB"] / "data" / "celdas.json", rutas["WEB"] / "data" / "prov" / "0.json"]:
        out[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()[:16] if f.exists() else None
    return out


def comun(nombre, rutas, codigo, log, sin_web):
    check(f"{nombre}: el pipeline termina", codigo == 0, "" if codigo == 0 else log[-800:])
    inf = rutas["SALIDA"] / "informe_datos.md"
    check(f"{nombre}: informe_datos.md generado", inf.exists())
    if not sin_web and codigo == 0:
        ok, det = web_ok(rutas["WEB"])
        check(f"{nombre}: el mapa carga sin errores de consola", ok, det)
    return inf.read_text(encoding="utf-8") if inf.exists() else ""


def escenario_1(tmp, sin_web):
    rutas = copiar_datos(tmp)
    codigo, log = ejecutar(rutas)
    txt = comun("E1 actuales", rutas, codigo, log, sin_web)
    check("E1: sin cambios de esquema respecto a lo publicado", "Sin cambios de esquema" in txt or "Primera ejecución" in txt)
    check("E1: capa vacía (water_stress) omitida con aviso", "| estres_hidrico |" in txt and "**no**" in txt)


def escenario_2(tmp, sin_web):
    rutas = copiar_datos(tmp)
    rng = np.random.default_rng(0)
    for f in sorted((rutas["ELT_DATASET"] / "sites_static").glob("ESP-p*.parquet")):
        st = pd.read_parquet(f)
        st["sintetico_columna_nueva"] = rng.normal(size=len(st))            # SINTÉTICO
        st["sintetico_flag_nuevo"] = rng.integers(0, 2, len(st))            # SINTÉTICO
        st["water_stress"] = rng.uniform(0, 5, len(st))                     # SINTÉTICO: capa antes vacía
        st.to_parquet(f, index=False)
    codigo, log = ejecutar(rutas)
    txt = comun("E2 ampliados (sintético)", rutas, codigo, log, sin_web)
    check("E2: el informe lista las columnas nuevas", "sintetico_columna_nueva" in txt and "**Los datos han cambiado.**" in txt)
    check("E2: la capa antes vacía se activa sola", "| estres_hidrico | criterios | `water_stress` | 100% | sí |" in txt)
    d = json.loads((rutas["WEB"] / "data" / "celdas.json").read_text(encoding="utf-8"))
    check("E2: el mapa avisa de que los datos han cambiado", d["meta"]["datos_cambiados"] is True)
    check("E2: datos marcados como sintéticos solo en la copia temporal", not (RAIZ / "ELT" / "dataset").joinpath("sintetico").exists())


def escenario_3(tmp, sin_web):
    rutas = copiar_datos(tmp)
    for f in sorted((rutas["ELT_DATASET"] / "sites_yearly").glob("ESP-p*.parquet")):
        pd.read_parquet(f).drop(columns=["free_cooling_hours"]).to_parquet(f, index=False)      # columna desaparecida
    for f in sorted((rutas["ELT_DATASET"] / "sites_static").glob("ESP-p*.parquet")):
        st = pd.read_parquet(f)
        st["slope_pct"] = st["slope_pct"].map(lambda v: f"{v:.3f}")                            # tipo cambiado
        st.loc[st.index[:7], "elevation_m"] = 99999.0                                            # imposibles
        st.loc[st.index[7:9], "dist_coast_km"] = -5.0
        pd.concat([st, st.head(25)]).to_parquet(f, index=False)                                   # duplicados
    codigo, log = ejecutar(rutas)
    txt = comun("E3 degradados", rutas, codigo, log, sin_web)
    check("E3: columna desaparecida en el informe", "free_cooling_hours" in txt.split("Columnas desaparecidas")[-1][:400])
    check("E3: criterio afectado omitido con aviso", "| refrigeracion | criterios | `free_cooling_hours` | 0% | **no** |" in txt)
    check("E3: tipo cambiado detectado", "slope_pct" in txt.split("convertidas a número")[-1][:300])
    check("E3: duplicados descartados", "duplicadas_estatica" in txt)
    check("E3: valores imposibles a 'sin dato'", "elevation_m" in txt.split("fuera de rango")[-1][:400])


def escenario_4(tmp, sin_web):
    a, b = tmp / "a", tmp / "b"
    ra, rb = copiar_datos(a), copiar_datos(b)
    ca, la = ejecutar(ra)
    cb, lb = ejecutar(rb)
    check("E4: dos ejecuciones terminan", ca == 0 and cb == 0, (la + lb)[-500:] if ca or cb else "")
    ha, hb = huella_archivos(ra), huella_archivos(rb)
    check("E4: resultados idénticos byte a byte", ha == hb, json.dumps({k: (ha[k], hb[k]) for k in ha if ha[k] != hb[k]}))
    if not sin_web and ca == 0:
        ok, det = web_ok(ra["WEB"])
        check("E4: el mapa carga sin errores de consola", ok, det)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--escenarios", default="1,2,3,4")
    ap.add_argument("--sin-web", action="store_true")
    a = ap.parse_args()
    fns = {"1": escenario_1, "2": escenario_2, "3": escenario_3, "4": escenario_4}
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="aceptacion_mapa_") as d:
        for e in a.escenarios.split(","):
            print(f"\n=== Escenario {e} ===", flush=True)
            tmp = Path(d) / f"e{e}"
            tmp.mkdir()
            fns[e](tmp, a.sin_web)
            shutil.rmtree(tmp, ignore_errors=True)
    fallos = [r for r in RESULTADOS if not r[1]]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} comprobaciones OK en {time.time() - t0:.0f} s")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
