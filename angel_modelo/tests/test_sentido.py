"""Suite de sentido común (tarea 4f). Lee <salida>/<pais>/sentido.json (src/sentido.py) de cada país que
tenga resultados, y prueba la monotonía de la rúbrica con celdas sintéticas (rotuladas, en memoria)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rubrica as R  # noqa: E402
from configuracion import paises_disponibles, ruta  # noqa: E402

RES = [(p, ruta("salida") / p / "sentido.json") for p in paises_disponibles()]


@pytest.mark.parametrize("pais,f", RES)
def test_resultados_con_sentido(pais, f):
    if not f.exists():
        pytest.skip(f"sin resultados de {pais}: ejecuta actualizar.py")
    r = json.loads(f.read_text(encoding="utf-8"))
    assert r["c1_candidata_con_exclusion"] == 0
    assert r["c2_candidata_en_agua_o_centro_urbano"] == 0
    assert r["c4_nan_inesperados"] == 0


def test_monotonia_empeorar_un_criterio_nunca_mejora_la_nota():
    cfg = R.cargar_config()
    base = {c["columna"]: c["puntos"][0][0] for c in cfg["criterios"]}       # SINTÉTICO
    for c in cfg["criterios"]:
        ys = [y for _, y in c["puntos"]]
        mejor = c["puntos"][int(np.argmax(ys))][0]
        peor = c["puntos"][int(np.argmin(ys))][0]
        df = pd.DataFrame([{**base, c["columna"]: mejor}, {**base, c["columna"]: peor}])
        s = R.aplicar(df, cfg)["score"].to_numpy()
        assert s[1] <= s[0], c["id"]


def test_condicionante_nunca_sube_la_nota():
    cfg = R.cargar_config()
    for r in cfg["condicionantes"]:
        v = r["valor"] if r["op"] in (">=", "==") else r["valor"] - 1
        df = pd.DataFrame([{r["columna"]: (0 if r["op"] != "==" else 1 - v)}, {r["columna"]: v}])
        s = R.aplicar(df, cfg)
        assert s["score"].iloc[1] <= s["score"].iloc[0] or s["score_bruto"].iloc[1] <= s["score_bruto"].iloc[0], r["id"]
