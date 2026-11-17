"""Gráficas técnicas generadas en vivo a partir del CSV (perfiles vs. profundidad)."""
from __future__ import annotations

import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORES = ["#1e40af", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0891b2"]


def _perfil(datos, columna, titulo, etiqueta_x, limites=None):
    fig, ax = plt.subplots(figsize=(5.2, 4.4), dpi=150)
    for i, (s, g) in enumerate(datos.groupby("Sondeo")):
        g = g.sort_values("Prof_Inicio_m")
        ys, xs = [], []
        for _, f in g.iterrows():
            ys += [f["Prof_Inicio_m"], f["Prof_Fin_m"]]
            xs += [f[columna], f[columna]]
        ax.plot(xs, ys, color=COLORES[i % len(COLORES)], lw=2, label=s)
        ax.scatter(g[columna], (g["Prof_Inicio_m"] + g["Prof_Fin_m"]) / 2,
                   color=COLORES[i % len(COLORES)], s=18, zorder=3)
    for z in (1.5, 3.0, 4.5):
        ax.axhline(z, color="#94a3b8", lw=0.6, ls="--")
    if limites:
        for valor, texto, color in limites:
            ax.axvline(valor, color=color, lw=1, ls=":")
            ax.text(valor, 0.15, f" {texto}", color=color, fontsize=7, va="top")
    ax.set_ylim(datos["Prof_Fin_m"].max(), 0)
    ax.set_xlabel(etiqueta_x, fontsize=9)
    ax.set_ylabel("Profundidad (m)", fontsize=9)
    ax.set_title(titulo, fontsize=10, fontweight="bold", color="#0f172a")
    ax.grid(alpha=0.25)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7, loc="lower left", frameon=True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    fig.tight_layout()
    return fig


def figura_nspt(datos):
    return _perfil(datos, "N_SPT", r"Variación de $N_{SPT}$ con la profundidad", r"$N_{SPT}$ (golpes/30 cm)",
                   limites=[(15, "N=15", "#d97706"), (50, "N=50", "#16a34a")] if datos["N_SPT"].max() > 45
                   else [(15, "N=15 (límite D/E)", "#d97706")])


def figura_qa(datos):
    return _perfil(datos, "qa_tm2", r"Capacidad portante admisible $q_a$", r"$q_a$ (t/m²) con FS ≥ 3,0",
                   limites=[(15, "15 t/m²", "#d97706")])


def a_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
