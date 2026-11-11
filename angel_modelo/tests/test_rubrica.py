"""Casos límite de la rúbrica. Uso: angel_modelo/.venv/bin/python -m pytest -q angel_modelo/tests"""
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rubrica as R  # noqa: E402

CFG = R.cargar_config()
CRIT_COLS = [c["columna"] for c in CFG["criterios"]]


def good_cell(**kw):
    """Una celda excelente en todo (todas las columnas con dato)."""
    base = {"site_id": "ESP_1_1", "agua_pct": 0.0, "parque_nacional_pct": 0.0, "zfp_pct": 0.0, "slope_pct": 2.0,
            "natura2000_pct": 0.0, "in_protected_area": 0, "zi_t100_pct": 0.0, "urbano_pct": 10.0,
            "in_flight_path_flag": 0, "in_low_elevation_coastal_zone": 0, "elevation_m": 500.0,
            "dist_substation_220kv_km": 1.0, "dist_hv_line_km": 0.5, "dist_infra_corridor_km": 0.5,
            "latency_to_hub_ms": 2.0, "industrial_pct": 20.0, "free_cooling_hours": 7500.0, "wetbulb_p99_c": 18.0,
            "annual_precip_mm": 900.0, "water_stress": 0.0, "pga475_ign_g": 0.03, "zi_t500_pct": 0.0, "dist_motorway_junction_km": 1.0,
            "militar_pct": 0.0, "distancia_militar_km": 20.0, "en_franja": 0, "militar_menor": 0}
    base.update(kw)
    return base


def run(*cells, cfg=CFG):
    return R.aplicar(pd.DataFrame(list(cells)), cfg)


def test_celda_perfecta_es_candidata_con_confianza_alta():
    r = run(good_cell()).iloc[0]
    assert r.score == 100 and r.cobertura == 1 and r.estado == "Candidata" and r.confianza == "alta"
    assert r.motivos.startswith("+:") and r.capas_faltan == ""


def test_pesos_deben_sumar_100_e_ids_unicos():
    bad = copy.deepcopy(CFG)
    bad["criterios"][0]["peso"] += 1
    with pytest.raises(ValueError):
        R.validar(bad)
    bad = copy.deepcopy(CFG)
    bad["criterios"][1]["id"] = bad["criterios"][0]["id"]
    with pytest.raises(ValueError):
        R.validar(bad)


def test_exclusion_justo_en_el_umbral_y_justo_debajo():
    r = run(good_cell(agua_pct=90.0), good_cell(agua_pct=89.99), good_cell(slope_pct=40.0))
    assert list(r.excluida) == [True, False, True]
    assert list(r.estado) == ["No viable", "Dudosa", "No viable"]   # 89,99 % de agua: no excluida, pero agua dominante
    assert r.motivos.iloc[0].startswith("E:agua")
    assert np.isnan(r.score_pct.iloc[0])          # las excluidas no se ordenan


def test_varias_exclusiones_se_listan_todas():
    r = run(good_cell(agua_pct=95, parque_nacional_pct=60)).iloc[0]
    assert r.exclusiones == "agua,parque_nacional"


def test_dato_de_exclusion_que_falta_impide_ser_candidata():
    # la capa está activa (2 de 3 celdas con dato) pero a esta celda le falta: no puede ser Candidata
    r = run(good_cell(zfp_pct=np.nan), good_cell(), good_cell()).iloc[0]
    assert not r.excluida and r.estado == "Dudosa" and "F:datos" in r.motivos


def test_curva_constante_fuera_de_los_extremos_e_interpolada_dentro():
    r = run(good_cell(latency_to_hub_ms=0.1), good_cell(latency_to_hub_ms=50), good_cell(latency_to_hub_ms=3.5))
    assert list(r.sub_latencia) == [100, 0, 87.5]


def test_dato_que_falta_puntua_pesimista_baja_cobertura_y_se_lista():
    r = run(good_cell(dist_substation_220kv_km=np.nan), good_cell(), good_cell()).iloc[0]
    assert r.sub_subestacion == 40 and r.cobertura == pytest.approx(0.80)
    assert r.confianza == "baja" and r.capas_faltan == "subestacion"


def test_columna_inexistente_omite_el_criterio_y_renormaliza():
    c = good_cell()
    del c["pga475_ign_g"]
    r = run(c).iloc[0]
    assert "sub_sismicidad" not in r.index                      # criterio omitido
    assert r.score == 100                                       # pesos repartidos entre los demás
    assert r.cobertura == pytest.approx(0.94) and r.confianza == "media"
    assert "sismicidad" in r.capas_faltan


def test_capa_vacia_se_omite_y_al_rellenarse_se_activa():
    vacia = [good_cell(pga475_ign_g=np.nan) for _ in range(5)]
    act = R.capas_activas(pd.DataFrame(vacia), CFG)
    assert not act["sismicidad"]["activa"]
    llena = [good_cell(pga475_ign_g=0.2) for _ in range(5)]
    assert R.capas_activas(pd.DataFrame(llena), CFG)["sismicidad"]["activa"]
    assert (run(*llena).sub_sismicidad < 100).all()


def test_columna_nueva_no_registrada_no_cambia_el_veredicto():
    base = run(good_cell(), good_cell(slope_pct=25))
    nueva = run(good_cell(columna_nueva=1.0), good_cell(slope_pct=25, columna_nueva=99.0))
    assert list(base.estado) == list(nueva.estado) and list(base.score) == list(nueva.score)


def test_confianza_baja_exige_margen_extra():
    thr, m = CFG["salida"]["umbral_candidata"], CFG["salida"]["margen_duda"]
    cfg = copy.deepcopy(CFG)
    cfg["salida"]["cobertura_minima_candidata"] = 0          # aquí se prueba solo el margen
    c = good_cell(dist_substation_220kv_km=np.nan)           # cobertura 0,80 -> confianza baja
    otras = [good_cell(), good_cell()]                        # para que la capa siga activa
    r = run(c, *otras, cfg=cfg).iloc[0]
    cfg["salida"]["umbral_candidata"] = r.score - m + 1      # supera el umbral, no umbral + margen
    r2 = run(c, *otras, cfg=cfg).iloc[0]
    assert r2.estado == "Dudosa"
    cfg["salida"]["umbral_candidata"] = r.score - m - 1
    assert run(c, *otras, cfg=cfg).iloc[0].estado == "Candidata"
    assert thr > 0


def test_no_evaluable_por_cobertura():
    vacia = good_cell(**{k: np.nan for k in CRIT_COLS})
    r = run(vacia, good_cell(), good_cell()).iloc[0]
    assert r.cobertura == 0 and r.estado == "No evaluable" and "F:datos" in r.motivos


def test_condicionante_resta_y_natura_no_se_duplica():
    r = run(good_cell(natura2000_pct=30), good_cell(natura2000_pct=60), good_cell(in_flight_path_flag=1))
    assert list(r.penalizacion) == [5, 15, 5]
    assert r.motivos.iloc[1].count("natura2000") == 1


def test_estados_y_rangos_en_lote_aleatorio():
    rng = np.random.default_rng(0)
    cells = [good_cell(slope_pct=s, natura2000_pct=n, dist_substation_220kv_km=d, industrial_pct=0)
             for s, n, d in zip(rng.uniform(0, 45, 200), rng.uniform(0, 100, 200), rng.uniform(0, 60, 200))]
    r = run(*cells)
    assert r.score.between(0, 100).all() and r.cobertura.between(0, 1).all()
    assert set(r.estado) <= set(R.ESTADOS)
    assert r.loc[~r.excluida, "score_pct"].between(0, 100).all()
    assert (r.motivos.str.count(r"\|") <= 2).all()
    assert not (r.excluida & (r.estado == "Candidata")).any()


def test_confianza_minima_impide_candidata():
    c = good_cell(dist_substation_220kv_km=np.nan)           # cobertura 0,80 < 0,85
    r = run(c, good_cell(), good_cell())
    assert r.estado.iloc[0] != "Candidata" and r.estado.iloc[1] == "Candidata"


def test_centro_urbano_denso_no_puede_ser_candidata():
    r = run(good_cell(urbano_pct=85), good_cell(urbano_pct=79))
    assert list(r.estado) == ["Dudosa", "Candidata"]


def test_militar_dentro_parcial_franja_lejos():
    r = run(good_cell(militar_pct=95, en_franja=1, distancia_militar_km=0),      # dentro (>= 90 %): excluida
            good_cell(militar_pct=3, en_franja=1, distancia_militar_km=0),       # solape parcial: condicionada
            good_cell(militar_pct=0, en_franja=1, distancia_militar_km=0.3),     # en franja: condicionada
            good_cell(militar_pct=0, en_franja=0, distancia_militar_km=12))      # lejos: sin efecto
    assert list(r.excluida) == [True, False, False, False]
    assert r.motivos.iloc[0].startswith("E:militar")
    assert list(r.estado[1:]) == ["Dudosa", "Dudosa", "Candidata"]
    assert all("C:militar_franja" in m for m in r.motivos.iloc[1:3])


def test_capa_militar_ausente_no_verificada_y_baja_confianza():
    cells = [good_cell() for _ in range(3)]
    for c in cells:
        for k in ("militar_pct", "en_franja", "distancia_militar_km"):
            del c[k]
    r = run(*cells)
    assert np.allclose(r.cobertura, 0.95) and r.capas_faltan.str.contains("militar\\(no verificada\\)").all()


def test_militar_60_pct_ya_no_excluye_y_recinto_menor_solo_avisa():
    r = run(good_cell(militar_pct=60, en_franja=1, distancia_militar_km=0),      # mayoría, pero < 90 %: condicionada
            good_cell(militar_pct=0.1, en_franja=0, militar_menor=1),            # recinto menor cerca: solo aviso
            good_cell())
    assert list(r.excluida) == [False, False, False]
    assert list(r.estado) == ["Dudosa", "Candidata", "Candidata"]
    assert "C:militar_menor" in r.motivos.iloc[1]
