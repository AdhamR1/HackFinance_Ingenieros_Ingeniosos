# Atajos (macOS/Linux), desde la raíz del repo: make -C angel_modelo actualizar
# En Windows (sin make): python angel_modelo/src/actualizar.py [paso]
PY ?= $(CURDIR)/.venv/bin/python

.PHONY: actualizar rapido militar carga rubrica sensibilidad evaluacion exportacion sentido test entorno servir servir-web aceptacion

actualizar:
	cd .. && $(PY) angel_modelo/src/actualizar.py todo

rapido militar carga rubrica sensibilidad evaluacion exportacion sentido test:
	cd .. && $(PY) angel_modelo/src/actualizar.py $@

entorno:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

servir:          # solo el mapa
	cd web_mapa && $(PY) -m http.server 8001

servir-web:      # la web del equipo con el mapa integrado (http://localhost:8000 -> "Cribado detallado")
	cd ../Web && $(PY) -m http.server 8000

aceptacion:      # prueba de aceptación en 4 escenarios sobre copias temporales de los datos
	cd .. && $(PY) angel_modelo/tests/aceptacion.py
