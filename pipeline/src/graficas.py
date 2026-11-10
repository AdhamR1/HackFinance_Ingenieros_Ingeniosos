"""Charts for the presentation (PNG, 16:9-friendly), from the outputs of train.py.

  1_mapa.png         score band of every cell + the real data centers
  2_aciertos.png     share of real data centers found vs share of the map checked (spatial validation)
  3_variables.png    what weighs most in the score (mean |SHAP|)
  4_evolucion.png    spatial AUC as the data and the model improved

Usage (from pipeline/): python src/graficas.py
Output: pipeline/figuras/
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from cells import PIPELINE, PROCESSED  # noqa: E402

OUT = PIPELINE / "figuras"
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
BLUE, BLUE_LIGHT = "#2a78d6", "#9ec5f4"
# same meaning as the web: green = best 5 %, yellow = next 15 %, rest light; excluded dark
BAND = {"baja": "#e6e4de", "media": "#eda100", "alta": "#008300", "excluida": "#52514e"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 15, "text.color": INK, "axes.labelcolor": INK2,
    "axes.edgecolor": GRID, "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE, "axes.spines.top": False,
    "axes.spines.right": False,
})

NAMES = {
    "dist_substation_km": "Distancia a subestación eléctrica",
    "industrial_pct": "Suelo industrial en la zona",
    "urbano_pct": "Suelo urbano en la zona",
    "dist_military_km": "Distancia a zona militar",
    "dist_residential_km": "Distancia a viviendas",
    "dist_power_plant_km": "Distancia a central eléctrica",
    "population_1km": "Población a 1 km",
    "dist_mine_quarry_km": "Distancia a mina o cantera",
    "dist_fire_station_km": "Distancia a parque de bomberos",
    "sand_pct": "Arena en el suelo",
    "gen_capacity_50km_mw": "Generación eléctrica a 50 km",
    "dist_400kv_line_km": "Distancia a línea de 400 kV",
    "slope_pct": "Pendiente del terreno",
    "dist_primary_road_km": "Distancia a carretera principal",
    "diurnal_range_c": "Diferencia de temperatura día-noche",
}
# spatial AUC at each step (scores_es_3500_cv_report.csv of each run, 10-Nov-2026)
EVOLUTION = [
    ("Datos del ELT", 0.585),
    ("+ Red eléctrica\ny autovías (OSM)", 0.885),
    ("+ Riesgos, suelo\ny sismicidad", 0.905),
    ("+ Criterios de expertos\n(81 audios)", 0.919),
    ("− Variables que\nhacían trampa", 0.922),
]


def save(fig, name):
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"-> {OUT / name}")


def mapa(s):
    canary = s.lat < 30
    fig = plt.figure(figsize=(16, 10.5))
    ax = fig.add_axes([0, 0, 1, 1])
    ins = fig.add_axes([0.0, 0.02, 0.3, 0.2])
    for a, part, k in ((ax, s[~canary], 1.0), (ins, s[canary], 1.0)):
        a.set_aspect(1 / np.cos(np.radians(part.lat.mean())))
        for band in ["baja", "media", "alta", "excluida"]:
            d = part[part.band == band]
            a.scatter(d.lon, d.lat, s=2.2 * k, marker="s", c=BAND[band], linewidths=0)
        dc = part[part.y == 1]
        a.scatter(dc.lon, dc.lat, s=46, c="white", edgecolors=INK, linewidths=1.6, zorder=5)
        a.set_axis_off()
    ins.patch.set_visible(False)
    ins.text(0.02, 1.02, "Canarias", transform=ins.transAxes, color=INK2, fontsize=13)
    ax.text(0.0, 1.06, "Dónde encaja un data center en España", transform=ax.transAxes,
            fontsize=26, weight="bold")
    ax.text(0.0, 1.015, "41.296 zonas de 3,5 × 3,5 km puntuadas por el modelo", transform=ax.transAxes,
            fontsize=16, color=INK2)
    handles = [Patch(color=BAND["alta"], label="Muy buena (5 % mejor)"),
               Patch(color=BAND["media"], label="Buena (siguiente 15 %)"),
               Patch(color=BAND["baja"], label="Peor"),
               Patch(color=BAND["excluida"], label="Prohibida (parque nacional, cauce, agua)"),
               Line2D([], [], marker="o", ls="", mfc="white", mec=INK, mew=1.6, ms=9,
                      label="Data center que ya existe")]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=14, labelcolor=INK2)
    save(fig, "1_mapa.png")


def aciertos(s):
    t = s[~s.excluded].sort_values("oof_spatial_pct", ascending=False)
    x = np.arange(1, len(t) + 1) / len(t) * 100
    y = t.y.cumsum().to_numpy() / t.y.sum() * 100
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.plot([0, 100], [0, 100], color=MUTED, lw=2, ls=(0, (4, 4)))
    ax.plot(x, y, color=BLUE, lw=3)
    ax.text(62, 52, "Elegir al azar", color=INK2, fontsize=15, rotation=33)
    for f in (5, 10):
        v = y[np.searchsorted(x, f)]
        ax.plot([f], [v], "o", ms=11, color=BLUE, mec=SURFACE, mew=2, zorder=5)
        ax.annotate(f"{f} % del mapa → {v:.0f} de cada 100\ndata centers (al azar: {f})", (f, v),
                    xytext=(f + 9, v - (4 if f == 10 else 14)), fontsize=15, color=INK,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=1))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.set_xlabel("% del mapa revisado, empezando por las mejores zonas")
    ax.set_ylabel("% de data centers reales encontrados")
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_title("El modelo encuentra los data centers en zonas que no ha visto", loc="left",
                 fontsize=22, weight="bold", pad=34)
    ax.text(0, 1.03, f"Validación espacial: se esconden zonas de 70 × 70 km  ·  AUC {auc(t):.3f}".replace(".", ","),
            transform=ax.transAxes, color=INK2, fontsize=15)
    save(fig, "2_aciertos.png")


def auc(t):
    r = t.oof_spatial_pct.rank()
    p = t.y.sum()
    return (r[t.y == 1].sum() - p * (p + 1) / 2) / (p * (len(t) - p))


def variables():
    imp = pd.read_csv(PROCESSED / "scores_es_3500_importance.csv", index_col=0).mean_abs_shap.head(12)
    imp = imp / imp.sum() * 100
    pri = pd.read_csv(PROCESSED / "priors_voz.csv").feature
    fig, ax = plt.subplots(figsize=(13, 8))
    colors = [BLUE if f in set(pri) else BLUE_LIGHT for f in imp.index]
    ax.barh([NAMES.get(f, f) for f in imp.index][::-1], imp.values[::-1], color=colors[::-1], height=0.62)
    for i, v in enumerate(imp.values[::-1]):
        ax.text(v + 0.3, i, f"{v:.0f} %", va="center", color=INK2, fontsize=13)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.set_title("Lo que más pesa en la nota", loc="left", fontsize=22, weight="bold", pad=34)
    ax.text(0, 1.03, "Peso relativo de las 12 variables principales (SHAP)", transform=ax.transAxes,
            color=INK2, fontsize=15)
    ax.legend(handles=[Patch(color=BLUE, label="Con sentido fijado por expertos (audios)"),
                       Patch(color=BLUE_LIGHT, label="Aprendida solo de los datos")],
              loc="lower right", frameon=False, fontsize=13, labelcolor=INK2)
    save(fig, "3_variables.png")


def evolucion():
    labels, vals = zip(*EVOLUTION)
    x = np.arange(len(vals))
    fig, ax = plt.subplots(figsize=(14, 7.5))
    ax.axhline(0.5, color=MUTED, lw=1.5, ls=(0, (4, 4)))
    ax.text(len(vals) - 0.5, 0.51, "0,5 = azar", color=INK2, fontsize=13, ha="right")
    ax.plot(x, vals, color=BLUE, lw=2.5, zorder=3)
    ax.plot(x, vals, "o", ms=12, color=BLUE, mec=SURFACE, mew=2, zorder=4)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.025, f"{v:.3f}".replace(".", ","), ha="center", fontsize=16, weight="bold")
    ax.set_xticks(x, [lab.replace(" (", "\n(") if len(lab) > 26 else lab for lab in labels], fontsize=13)
    ax.set_ylim(0.45, 1.0)
    ax.set_yticks([0.5, 0.6, 0.7, 0.8, 0.9, 1.0], ["0,5", "0,6", "0,7", "0,8", "0,9", "1"])
    ax.set_ylabel("AUC en validación espacial")
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_title("Cada fuente de datos mejora el modelo", loc="left", fontsize=22, weight="bold", pad=34)
    ax.text(0, 1.03, "1 = acierta siempre; medido en zonas que el modelo no ha visto", transform=ax.transAxes,
            color=INK2, fontsize=15)
    save(fig, "4_evolucion.png")


def main():
    s = pd.read_parquet(PROCESSED / "scores_es_3500.parquet")
    mapa(s)
    aciertos(s)
    variables()
    evolucion()


if __name__ == "__main__":
    main()
