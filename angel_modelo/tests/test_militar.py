"""Capa militar por celda (src/militar.py) con geometrías SINTÉTICAS (rotuladas; solo en memoria / tmp)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
gpd = pytest.importorskip("geopandas")
shapely = pytest.importorskip("shapely")
import militar as M  # noqa: E402
from configuracion import columnas, crs_rejilla  # noqa: E402

TAM = 3500.0


def celda(i, j, iso="ESP"):
    return f"{iso}_{i}_{j}"


def capa(*cajas):
    """SINTÉTICO: polígonos en metros de la rejilla."""
    return gpd.GeoDataFrame(geometry=[shapely.box(*b) for b in cajas], crs=crs_rejilla())


def test_dentro_parcial_franja_lejos_y_vacia():
    i, j = 1000, 500
    x0, y0 = i * TAM, j * TAM
    g = capa((x0 - 100, y0 - 100, x0 + TAM + 100, y0 + TAM + 100),         # cubre (i, j) y 100 m de (i+1, j)
             (x0 + 6 * TAM + 200, y0, x0 + 6 * TAM + 600, y0 + 400))       # a 200 m de (i+5, j), sin solaparla
    cells = pd.DataFrame({"site_id": [celda(i, j), celda(i + 1, j), celda(i + 5, j), celda(i + 3, j), celda(i + 20, j)]})
    r = M.por_celda(cells, g, TAM, 500).set_index("site_id")
    assert r.loc[celda(i, j), "militar_pct"] == pytest.approx(100, abs=0.1)                  # dentro -> excluida
    assert 0 < r.loc[celda(i + 1, j), "militar_pct"] < 5 and r.loc[celda(i + 1, j), "en_franja"] == 1  # parcial
    assert r.loc[celda(i + 5, j), "militar_pct"] == 0 and r.loc[celda(i + 5, j), "en_franja"] == 1     # en franja
    assert r.loc[celda(i + 5, j), "distancia_militar_km"] == pytest.approx(0.2, abs=0.01)
    assert r.loc[celda(i + 3, j), "en_franja"] == 0                                           # > 500 m
    assert r.loc[celda(i + 20, j), "distancia_militar_km"] > 40                               # lejos
    vacia = M.por_celda(cells, capa(), TAM, 500)
    assert (vacia.militar_pct == 0).all() and vacia.distancia_militar_km.isna().all()


def test_capa_ausente_deja_sin_dato_no_cero():
    r = M.por_celda(pd.DataFrame({"site_id": [celda(1, 1)]}), None, TAM, 500)
    assert r[["militar_pct", "en_franja", "distancia_militar_km"]].isna().all().all()


@pytest.mark.parametrize("pais,lonlat", [("es", (-15.43, 28.10)),     # Gran Canaria
                                         ("es", (2.73, 39.55)),       # Mallorca
                                         ("jp", (127.77, 26.35)),     # Okinawa
                                         ("jp", (142.19, 27.09))])    # Chichijima (islas Ogasawara)
def test_islas_se_procesan_en_la_proyeccion_metrica_del_pais(monkeypatch, pais, lonlat):
    monkeypatch.setenv("MAPA_PAIS", pais)
    from pyproj import Transformer

    x, y = Transformer.from_crs("EPSG:4326", crs_rejilla(), always_xy=True).transform(*lonlat)
    i, j = int(np.floor(x / TAM)), int(np.floor(y / TAM))
    iso = columnas()["pais"]
    g = capa((x - 1000, y - 1000, x + 1000, y + 1000))                 # SINTÉTICO: 4 km² alrededor del punto
    r = M.por_celda(pd.DataFrame({"site_id": [celda(i, j, iso)]}), g, TAM, 500)
    assert r.militar_pct.iloc[0] > 0 and r.en_franja.iloc[0] == 1


def test_recinto_menor_solo_aviso_y_entidad_genera_franja():
    i, j = 2000, 600
    x0, y0 = i * TAM, j * TAM
    g = capa((x0 + 100, y0 + 100, x0 + 200, y0 + 200),                      # 1 ha sin tipo: recinto menor
             (x0 + 10 * TAM + 100, y0 + 100, x0 + 10 * TAM + 200, y0 + 200)) # 1 ha, pero de tipo «base»
    g["tipo"] = ["military", "base"]                                        # SINTÉTICO
    cells = pd.DataFrame({"site_id": [celda(i, j), celda(i + 10, j)]})
    r = M.por_celda(cells, g, TAM, 500, ["base", "airfield"], 5).set_index("site_id")
    assert r.loc[celda(i, j), "en_franja"] == 0 and r.loc[celda(i, j), "militar_menor"] == 1
    assert r.loc[celda(i + 10, j), "en_franja"] == 1 and r.loc[celda(i + 10, j), "militar_menor"] == 0
    g2 = capa((x0, y0, x0 + 300, y0 + 2000))                                # 6 ha sin tipo: cuenta como entidad
    g2["tipo"] = ["military"]
    r2 = M.por_celda(cells.head(1), g2, TAM, 500, ["base"], 5)
    assert r2.en_franja.iloc[0] == 1
