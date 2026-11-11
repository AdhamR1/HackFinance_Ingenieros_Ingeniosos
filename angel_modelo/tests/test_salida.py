"""Tests de la salida por celda y de los datos del mapa. Necesitan haber ejecutado el pipeline
(python angel_modelo/src/actualizar.py); si no hay salida, se saltan."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))
import rubrica as R  # noqa: E402
from configuracion import ruta, web_datos  # noqa: E402

OUT = ruta("salida") / "es"          # el país por defecto; los datos de cada país en web_mapa/data/<pais>/
WEB = web_datos()
COLS = ["site_id", "lon", "lat", "comunidad", "provincia", "estado", "score_pct", "nota_rubrica", "cobertura",
        "confianza", "motivos", "exclusiones", "capas_faltan", "dc_real", "dc_fuente", "dc_nombres"]

need_out = pytest.mark.skipif(not (OUT / "salida_celdas.parquet").exists(), reason="sin salida: ejecuta actualizar.py")
need_web = pytest.mark.skipif(not (WEB / "celdas.json").exists(), reason="sin datos web: ejecuta exportar.py")


@pytest.fixture(scope="module")
def sal():
    return pd.read_parquet(OUT / "salida_celdas.parquet")


@need_out
def test_esquema_y_una_fila_por_celda(sal):
    assert list(sal.columns[: len(COLS)]) == COLS
    assert sal.site_id.is_unique and len(sal) > 40000
    assert sal.site_id.str.match(r"^ESP_\d+_\d+$").all()


@need_out
def test_rangos_y_sin_nan_inesperados(sal):
    assert sal.lon.between(-19, 5).all() and sal.lat.between(27, 44.5).all()
    assert sal.nota_rubrica.between(0, 100).all() and sal.cobertura.between(0, 1).all()
    assert set(sal.estado) <= set(R.ESTADOS) and set(sal.confianza) <= {"alta", "media", "baja"}
    excl = sal.exclusiones.ne("")
    assert sal.loc[~excl, "score_pct"].between(0, 100).all()          # solo las excluidas no se ordenan
    assert sal.loc[excl, "score_pct"].isna().all()
    for c in ["site_id", "provincia", "estado", "nota_rubrica", "cobertura", "dc_real"]:
        assert sal[c].notna().all(), c


@need_out
def test_reglas_coherentes(sal):
    excl = sal.exclusiones.ne("")
    assert (sal.loc[excl, "estado"] == "No viable").all()
    assert not ((sal.estado == "Candidata") & (sal.confianza == "baja") &
                (sal.nota_rubrica < R.cargar_config()["salida"]["umbral_candidata"])).any()
    assert (sal.motivos.str.count(r"\|") <= 2).all()
    # calibración de las exclusiones: ningún data center real queda excluido
    assert not (excl & sal.dc_real).any()


@need_out
def test_metricas_json():
    f = OUT / "metricas.json" if (OUT / "metricas.json").exists() else WEB / "metricas.json"
    m = json.loads(f.read_text(encoding="utf-8"))
    r = m["resultados"]["dc_real"]
    for k in ("rubrica", "logistica_2_variables", "modelo_equipo_replica"):
        assert 0 <= r[k]["pr_auc"] <= 1 and len(r[k]["auc_ic95"]) == 2 and 0 <= r[k]["recall_top5"] <= 1
    assert isinstance(m["modelo_entra_al_mapa"], bool) and m["lo_que_no_se_ha_medido"]


@need_web
def test_datos_web_coherentes_y_ligeros():
    d = json.loads((WEB / "celdas.json").read_text(encoding="utf-8"))
    n = len(d["cells"]["e"])
    for k, v in d["cells"].items():
        assert len(v) == (3 * n if k == "m" else n), k
    assert max(d["cells"]["m"]) < len(d["motivos"]) and min(d["cells"]["p"]) >= 0
    assert (WEB / "celdas.json").stat().st_size < 10e6
    assert all(f.stat().st_size < 10e6 for f in WEB.rglob("*.json"))
    assert len(list((WEB / "prov").glob("*.json"))) == len(d["provincias"])
    assert d["meta"]["huella"]["filas"] and d["meta"]["fecha_datos"]
    if d["geometria"] == "rejilla":
        nodes = set(zip(d["nodes"]["i"], d["nodes"]["j"]))
        i, j = np.array(d["cells"]["i"]), np.array(d["cells"]["j"])
        assert all((a + 1, b + 1) in nodes for a, b in zip(i[:500], j[:500]))


@need_web
def test_sin_claves_en_el_cliente():
    for f in (HERE / "web_mapa").rglob("*"):
        if f.suffix in {".js", ".html", ".json", ".css"} and "vendor" not in f.parts:
            t = f.read_text(encoding="utf-8", errors="ignore")
            assert "sk-ant-" not in t and "ANTHROPIC_API_KEY=" not in t, f
