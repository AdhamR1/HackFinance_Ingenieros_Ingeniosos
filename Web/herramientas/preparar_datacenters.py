"""Convierte las listas de data centers del equipo en puntos para el mapa
(data/DC_ES.json, data/DC_JP.json).

Fuentes (copiadas de Modelo/data/raw/ del repo del equipo a herramientas/fuentes/):
  * dc_sites_es.csv: hecha a mano desde datacentermap.com. Ubicación aproximada
    (municipio, barrio o ciudad).
  * dc_sites_jp.csv: PeeringDB + OpenStreetMap (programa Modelo/src/dc_sites.py).
    Coordenadas exactas.
Son las mismas listas que usa el modelo, así que los puntos cuadran con lo que aprendió.

Uso (desde esta carpeta herramientas/):  python preparar_datacenters.py
Si el equipo cambia las listas: volver a copiar los CSV a fuentes/ y ejecutarlo otra vez.
"""

import csv
import json
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FUENTES = AQUI / "fuentes"
DATOS = AQUI.parent / "data"

PAISES = {
    "ES": "dc_sites_es.csv",
    "JP": "dc_sites_jp.csv",
}

# precision del CSV → nuestra clave (la web la traduce)
PRECISION = {
    "exact": "exacta",
    "district_approx": "barrio",
    "municipio": "municipio",
    "metro": "ciudad",
}
ESTADO = {"operational": "operativo", "planned": "planeado"}


def fuente_de(fila: dict) -> str:
    """De dónde sale el punto: datacentermap (España) o PeeringDB / OpenStreetMap (Japón)."""
    origen = fila["geocode_source"]
    if origen in ("PeeringDB", "OSM"):
        return "peeringdb" if origen == "PeeringDB" else "osm"
    return "datacentermap"


def convertir(iso: str, archivo: str) -> dict:
    with open(FUENTES / archivo, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    puntos = []
    for i, fila in enumerate(filas, 1):
        nombre = fila["site"].strip()
        # OSM sin nombre: el programa del equipo pone "data center (OSM)".
        # La web dirá "Sin nombre".
        sin_nombre = nombre.lower() == "data center (osm)"
        # "Digital Realty MAD1-4; Nabiax; GNET" → lista.
        # En Japón el operador repite el nombre: se quita.
        operadores = [o.strip() for o in fila["operators"].split(";") if o.strip()]
        if operadores == [nombre] or sin_nombre:
            operadores = []
        puntos.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(float(fila["lon"]), 5), round(float(fila["lat"]), 5)],
                },
                "properties": {
                    "id": f"{iso}-DC{i:03d}",
                    "nombre": None if sin_nombre else nombre,
                    "operadores": operadores,
                    "municipio": fila["municipio"].strip() or None,
                    "estado": ESTADO.get(fila["status"], fila["status"]),
                    "edificios": int(fila["n_buildings"] or 1),
                    "precision": PRECISION.get(fila["precision"], fila["precision"]),
                    "fuente": fuente_de(fila),
                },
            }
        )
    return {"type": "FeatureCollection", "features": puntos}


def main():
    for iso, archivo in PAISES.items():
        datos = convertir(iso, archivo)
        destino = DATOS / f"DC_{iso}.json"
        destino.write_text(
            json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        n = len(datos["features"])
        edificios = sum(p["properties"]["edificios"] for p in datos["features"])
        print(f"{iso}: {n} sitios ({edificios} edificios) → {destino.name}")


if __name__ == "__main__":
    main()
