"""Un solo comando para regenerar el mapa, o cada paso por separado.

    python angel_modelo/src/actualizar.py              # todo, por país: militar -> carga -> rubrica -> evaluacion -> exportacion; y test
    python angel_modelo/src/actualizar.py carga        # un paso: militar | carga | rubrica | sensibilidad | evaluacion | exportacion | test
    python angel_modelo/src/actualizar.py rapido       # todo menos la evaluación (reutiliza la última metricas.json)

Funciona igual en Windows, macOS y Linux (no necesita make). Usa el Python con el que se lanza.
Las rutas de entrada y salida se pueden cambiar con variables de entorno MAPA_* (ver configuracion.py).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent
RAIZ = SRC.parent
PY = sys.executable
PASOS = {
    "militar": [PY, "-W", "ignore", str(SRC / "militar.py")],
    "carga": [PY, "-W", "ignore", str(SRC / "carga.py")],
    "rubrica": [PY, "-W", "ignore", str(SRC / "rubrica.py")],
    "sensibilidad": [PY, "-W", "ignore", str(SRC / "rubrica.py"), "--sensibilidad"],
    "evaluacion": [PY, "-W", "ignore", str(SRC / "evaluacion.py")],
    "exportacion": [PY, "-W", "ignore", str(SRC / "exportacion.py")],
    "sentido": [PY, "-W", "ignore", str(SRC / "sentido.py")],
    "test": [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(RAIZ / "tests")],
}
PLANES = {"todo": ["militar", "carga", "rubrica", "evaluacion", "exportacion", "sentido", "test"],
          "rapido": ["militar", "carga", "rubrica", "exportacion", "sentido", "test"],
          "sin_test": ["militar", "carga", "rubrica", "evaluacion", "exportacion", "sentido"]}
UNICOS = ("sentido", "test")       # se ejecutan una vez para todos los países


def main(argv):
    """Cada paso se ejecuta para cada país (MAPA_PAISES="es,jp" o, si no, todos los perfiles de config/paises);
    los tests, una vez al final."""
    sys.path.insert(0, str(SRC))
    from configuracion import pais_tiene_datos, paises_disponibles

    plan = PLANES.get(argv[0], [argv[0]]) if argv else PLANES["todo"]
    paises = [p for p in os.environ.get("MAPA_PAISES", ",".join(paises_disponibles())).split(",") if p]
    sin = [p for p in paises if not pais_tiene_datos(p)]
    for p in sin:
        print(f"AVISO: el país '{p}' tiene perfil pero no hay datos del ETL: se salta (el mapa no lo ofrecerá)", flush=True)
    paises = [p for p in paises if p not in sin]
    if sin and "exportacion" in plan:              # el mapa no ofrece países sin datos (sus archivos son generados)
        import json
        import shutil

        from configuracion import ruta

        idx_f = ruta("web") / "data" / "paises.json"
        idx = json.loads(idx_f.read_text(encoding="utf-8")) if idx_f.exists() else {}
        for p in sin:
            shutil.rmtree(ruta("web") / "data" / p, ignore_errors=True)
            idx.pop(p, None)
        if idx_f.exists():
            idx_f.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    if not paises:
        sys.exit("ERROR FATAL: ningún país tiene datos del ETL")
    for paso in plan:
        if paso not in PASOS:
            sys.exit(f"Paso desconocido: {paso}. Opciones: {', '.join(list(PASOS) + list(PLANES))}")
        for p in (["-"] if paso in UNICOS else paises):
            t = time.time()
            print(f"\n=== {paso}{'' if p == '-' else ' · ' + p} ===", flush=True)
            env = dict(os.environ) if p == "-" else dict(os.environ, MAPA_PAIS=p)
            r = subprocess.run(PASOS[paso], cwd=RAIZ.parent, env=env)
            if r.returncode:
                sys.exit(f"El paso '{paso}' falló (código {r.returncode}){'' if p == '-' else ' en ' + p}. Mira el mensaje de arriba.")
            print(f"--- {paso}{'' if p == '-' else ' · ' + p}: {time.time() - t:.1f} s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
