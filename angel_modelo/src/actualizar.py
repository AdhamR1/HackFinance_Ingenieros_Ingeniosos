"""Un solo comando para regenerar el mapa, o cada paso por separado.

    python angel_modelo/src/actualizar.py              # todo: carga -> rubrica -> evaluacion -> exportacion -> test
    python angel_modelo/src/actualizar.py carga        # un paso: carga | rubrica | sensibilidad | evaluacion | exportacion | test
    python angel_modelo/src/actualizar.py rapido       # todo menos la evaluación (reutiliza la última metricas.json)

Funciona igual en Windows, macOS y Linux (no necesita make). Usa el Python con el que se lanza.
Las rutas de entrada y salida se pueden cambiar con variables de entorno MAPA_* (ver configuracion.py).
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent
RAIZ = SRC.parent
PY = sys.executable
PASOS = {
    "carga": [PY, "-W", "ignore", str(SRC / "carga.py")],
    "rubrica": [PY, "-W", "ignore", str(SRC / "rubrica.py")],
    "sensibilidad": [PY, "-W", "ignore", str(SRC / "rubrica.py"), "--sensibilidad"],
    "evaluacion": [PY, "-W", "ignore", str(SRC / "evaluacion.py")],
    "exportacion": [PY, "-W", "ignore", str(SRC / "exportacion.py")],
    "test": [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(RAIZ / "tests")],
}
PLANES = {"todo": ["carga", "rubrica", "evaluacion", "exportacion", "test"],
          "rapido": ["carga", "rubrica", "exportacion", "test"],
          "sin_test": ["carga", "rubrica", "evaluacion", "exportacion"]}


def main(argv):
    plan = PLANES.get(argv[0], [argv[0]]) if argv else PLANES["todo"]
    for paso in plan:
        if paso not in PASOS:
            sys.exit(f"Paso desconocido: {paso}. Opciones: {', '.join(list(PASOS) + list(PLANES))}")
        t = time.time()
        print(f"\n=== {paso} ===", flush=True)
        r = subprocess.run(PASOS[paso], cwd=RAIZ.parent)
        if r.returncode:
            sys.exit(f"El paso '{paso}' falló (código {r.returncode}). Mira el mensaje de arriba.")
        print(f"--- {paso}: {time.time() - t:.1f} s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
