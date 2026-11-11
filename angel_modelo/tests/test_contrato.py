"""Contrato con los datos del equipo: qué es ERROR FATAL y qué es solo AVISO.

Trabaja sobre un recorte REAL (300 celdas) de ELT/dataset y pipeline/data/processed copiado a un
directorio temporal; nunca modifica los datos del repositorio.
"""
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
import carga  # noqa: E402
import configuracion as K  # noqa: E402

N = 300


@pytest.fixture()
def datos(tmp_path, monkeypatch):
    """Copia recortada de las entradas + variables MAPA_* apuntando a ella."""
    elt, proc, raw = tmp_path / "elt", tmp_path / "proc", tmp_path / "raw"
    src_elt, src_proc = K.ruta("elt_dataset"), K.ruta("pipeline_processed")
    if not (src_elt / "sites_static").exists():
        pytest.skip("no hay datos del ELT en el repositorio")
    st = pd.read_parquet(sorted((src_elt / "sites_static").glob("ESP-p*.parquet"))[0]).head(N)
    ids = set(st.site_id)
    (elt / "sites_static").mkdir(parents=True)
    st.to_parquet(elt / "sites_static" / "ESP-p00.parquet", index=False)
    yf = sorted((src_elt / "sites_yearly").glob("ESP-p*.parquet"))
    if yf:
        (elt / "sites_yearly").mkdir()
        y = pd.read_parquet(yf[0])
        y[y.site_id.isin(ids)].to_parquet(elt / "sites_yearly" / "ESP-p00.parquet", index=False)
    proc.mkdir()
    for f in src_proc.glob("*.parquet"):
        d = pd.read_parquet(f)
        if "site_id" in d.columns:
            d[d.site_id.isin(ids)].to_parquet(proc / f.name, index=False)
    raw.mkdir()
    for k, v in {"ELT_DATASET": elt, "PIPELINE_PROCESSED": proc, "PIPELINE_RAW": raw, "SALIDA": tmp_path / "out",
                 "DATOS_PROPIOS": tmp_path / "propios"}.items():
        monkeypatch.setenv("MAPA_" + k, str(v))
    return {"elt": elt, "proc": proc}


def _static(d):
    return d["elt"] / "sites_static" / "ESP-p00.parquet"


def test_datos_actuales_cargan_sin_errores(datos):
    df, info = carga.cargar()
    assert len(df) == N and df.site_id.is_unique and info["huella"]["filas"]


@pytest.mark.parametrize("quitar", ["site_id", "lon", "lat"])
def test_sin_identificador_o_coordenadas_es_fatal(datos, quitar):
    f = _static(datos)
    pd.read_parquet(f).drop(columns=[quitar]).to_parquet(f, index=False)
    with pytest.raises(K.ErrorFatal, match="identificador|coordenadas"):
        carga.cargar()


def test_sin_carpeta_de_datos_es_fatal(datos, monkeypatch, tmp_path):
    monkeypatch.setenv("MAPA_ELT_DATASET", str(tmp_path / "no_existe"))
    with pytest.raises(K.ErrorFatal, match="no existe"):
        carga.cargar()


def test_puntero_lfs_es_fatal(datos):
    _static(datos).write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n")
    with pytest.raises(K.ErrorFatal, match="LFS"):
        carga.cargar()


def test_alias_de_coordenadas_es_aviso(datos):
    f = _static(datos)
    pd.read_parquet(f).rename(columns={"lon": "longitude"}).to_parquet(f, index=False)
    df, info = carga.cargar()
    assert "lon" in df.columns and any("alias" in a for a in info["avisos"])


def test_tabla_opcional_ausente_es_aviso(datos):
    os.remove(datos["proc"] / "finanzas_es_3500.parquet")
    df, info = carga.cargar()
    assert len(df) == N and any("finanzas" in a for a in info["avisos"])


def test_duplicados_tipo_cambiado_y_valores_imposibles(datos):
    f = _static(datos)
    st = pd.read_parquet(f)
    st["slope_pct"] = st["slope_pct"].astype(str)              # tipo cambiado a texto
    st.loc[st.index[:5], "elevation_m"] = 99999.0              # imposible
    pd.concat([st, st.head(10)]).to_parquet(f, index=False)     # 10 filas duplicadas
    df, info = carga.cargar()
    s = info["stats"]
    assert len(df) == N and s["duplicadas_estatica"] == 10
    assert "slope_pct" in s["tipo_cambiado"] and pd.api.types.is_float_dtype(df.slope_pct)
    assert s["fuera_de_rango"].get("elevation_m") == 5 and df.elevation_m.isna().sum() >= 5


def test_comparar_esquema_detecta_cambios():
    a = {"x": {"tipo": "float64", "cobertura": 1.0, "min": 0, "max": 10}, "y": {"tipo": "float64", "cobertura": 0.0}}
    b = {"x": {"tipo": "object", "cobertura": 0.5, "min": 0, "max": 100}, "z": {"tipo": "float64", "cobertura": 1.0}}
    c = carga.comparar(b, a, 10, 12)
    assert c["nuevas"] == ["z"] and c["desaparecidas"] == ["y"] and c["tipo_cambiado"] and c["rango_cambiado"]
    assert c["filas_antes"] == 10 and c["filas_ahora"] == 12
    assert carga.comparar(b, None, None, 12) == {"primera_ejecucion": True}


def test_no_quedan_copias_en_el_repo(datos):
    assert not np.any([p.name == "elt" for p in (K.REPO / "angel_modelo").iterdir()])
    shutil.rmtree(datos["elt"])
