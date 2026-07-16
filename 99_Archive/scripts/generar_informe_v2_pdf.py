"""
generar_informe_v2_pdf.py — Informe ejecutivo v2 para Comite T8.

Mejoras sobre v1:
  - Incorpora hallazgos Fase 2 (ISR, retardo pilas, elasticidad, clasificacion A/B/C/D)
  - Semaforo de riesgo operacional (pagina nueva)
  - Roadmap de implementacion con fechas absolutas (pagina nueva)
  - Ventanas consecutivas (pagina nueva)
  - Recomendaciones reforzadas con acciones fechadas y responsables

Entregable:
    outputs/reports/Informe_Comite_v2_T8.pdf

Uso:
    python src/generar_informe_v2_pdf.py
"""
from __future__ import annotations

import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.image as mpimg
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE   = Path(__file__).resolve().parents[1]
FIGS   = BASE / "outputs" / "figures"
RPT    = BASE / "outputs" / "reports"
LOGS   = BASE / "logs"
XLS    = BASE / "outputs" / "excel" / "event_study_t8.xlsx"
F2     = FIGS / "fase2"

RPT.mkdir(parents=True, exist_ok=True)

# ── Paleta ────────────────────────────────────────────────────────────────────
C_BLUE   = "#1B3A5C"
C_COPPER = "#B87333"
C_ORANGE = "#C95B27"
C_RED    = "#C0392B"
C_GREEN  = "#27AE60"
C_LGRAY  = "#F4F6F9"
C_MGRAY  = "#8E9BAA"
C_WHITE  = "#FFFFFF"
C_DARK   = "#1A1A1A"
C_GOLD   = "#D4A83A"
C_AMBER  = "#F39C12"

PW, PH = 16.0, 9.0
DPI     = 150
VER     = "v2.0"
DATE_STR = datetime.now().strftime("%d/%m/%Y")
TODAY    = datetime.now()


# ═══════════════════════════════════════════════════════════════════════════════
# Utilidades de diseño (idénticas a v1 para consistencia)
# ═══════════════════════════════════════════════════════════════════════════════

def _new_page(bg: str = C_WHITE) -> plt.Figure:
    fig = plt.figure(figsize=(PW, PH))
    fig.patch.set_facecolor(bg)
    return fig


def _header(fig, title, subtitle="", bar_color=C_BLUE, page_num=0):
    ax = fig.add_axes([0, 0.88, 1, 0.12])
    ax.set_facecolor(bar_color); ax.axis("off")
    ax.text(0.02, 0.58, title, color=C_WHITE, fontsize=15, fontweight="bold",
            va="center", transform=ax.transAxes)
    if subtitle:
        ax.text(0.02, 0.18, subtitle, color=C_GOLD, fontsize=8.5,
                va="center", transform=ax.transAxes)
    if page_num:
        ax.text(0.98, 0.35, f"[ {page_num} ]", color=C_WHITE, fontsize=8,
                ha="right", va="center", transform=ax.transAxes, alpha=0.7)
    ax.text(0.98, 0.72, VER, color=C_COPPER, fontsize=7.5,
            ha="right", va="center", transform=ax.transAxes, alpha=0.9)
    ax2 = fig.add_axes([0, 0.876, 1, 0.006])
    ax2.set_facecolor(C_COPPER); ax2.axis("off")


def _footer(fig, date_str=DATE_STR, ver=VER):
    ax = fig.add_axes([0, 0, 1, 0.04])
    ax.set_facecolor(C_BLUE); ax.axis("off")
    ax.text(0.02, 0.5,
            "CODELCO División El Teniente — CIO DET — Analítica de Rendimientos",
            color=C_WHITE, fontsize=7, va="center", transform=ax.transAxes, alpha=0.85)
    ax.text(0.98, 0.5, f"{date_str}  |  {ver}  |  CONFIDENCIAL",
            color=C_GOLD, fontsize=7, ha="right", va="center",
            transform=ax.transAxes, alpha=0.9)


def _img(fig, path, left, bot, w, h):
    p = Path(path)
    if not p.exists():
        return
    ax = fig.add_axes([left, bot, w, h])
    ax.imshow(mpimg.imread(str(p)), aspect="auto")
    ax.axis("off")


def _kpi_box(fig, left, bot, w, h, value, label, sublabel="", bg=C_BLUE, tc=C_WHITE):
    ax = fig.add_axes([left, bot, w, h])
    ax.set_facecolor(bg); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.03, 0.03), 0.94, 0.94,
                                boxstyle="round,pad=0.02",
                                facecolor=bg, edgecolor=C_COPPER, linewidth=1.5))
    ax.text(0.5, 0.60, value,    color=tc, fontsize=22, fontweight="bold", ha="center", va="center")
    ax.text(0.5, 0.28, label,    color=tc, fontsize=8.5, fontweight="bold", ha="center", va="center")
    if sublabel:
        ax.text(0.5, 0.10, sublabel, color=C_GOLD, fontsize=7.5, ha="center", va="center")


def _callout(fig, left, bot, w, h, text, bg=C_BLUE, fc=C_WHITE, fontsize=11):
    ax = fig.add_axes([left, bot, w, h])
    ax.set_facecolor(bg); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.02, 0.05), 0.96, 0.90,
                                boxstyle="round,pad=0.02",
                                facecolor=bg, edgecolor=C_COPPER, linewidth=2))
    wrapped = textwrap.fill(text, width=38)
    ax.text(0.5, 0.5, wrapped, color=fc, fontsize=fontsize, fontweight="bold",
            ha="center", va="center", multialignment="center", linespacing=1.6)


def _badge(ax, x, y, w, h, text, col):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01",
                                facecolor=col, edgecolor="none"))
    ax.text(x + w / 2, y + h / 2, text, color=C_WHITE, fontsize=7,
            fontweight="bold", ha="center", va="center")


def _load_data():
    df_met  = pd.read_excel(XLS, sheet_name="metricas_evento_activo")
    df_stat = pd.read_excel(XLS, sheet_name="significancia_estadistica")
    df_act  = pd.read_excel(XLS, sheet_name="resumen_activo")
    return {"met": df_met, "stat": df_stat, "act": df_act}


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINAS
# ═══════════════════════════════════════════════════════════════════════════════

def page_portada() -> plt.Figure:
    fig = _new_page(C_BLUE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(C_BLUE); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    ax.add_patch(mpatches.Rectangle((0, 0), 0.006, 1, color=C_COPPER))
    ax.add_patch(mpatches.Rectangle((0, 0), 1, 0.18, color=C_DARK, alpha=0.4))

    # Badge v2
    ax.add_patch(FancyBboxPatch((0.72, 0.80), 0.18, 0.08,
                                boxstyle="round,pad=0.01",
                                facecolor=C_COPPER, edgecolor="none"))
    ax.text(0.810, 0.840, "VERSIÓN 2.0", color=C_WHITE, fontsize=9,
            fontweight="bold", ha="center", va="center")

    ax.text(0.06, 0.82, "IMPACTO OPERACIONAL DE LAS", color=C_GOLD, fontsize=14, fontweight="bold")
    ax.text(0.06, 0.72, "VENTANAS TENIENTE 8", color=C_WHITE, fontsize=32, fontweight="bold")
    ax.text(0.06, 0.62, "SOBRE LOS RENDIMIENTOS DE MOLIENDA", color=C_COPPER, fontsize=16, fontweight="bold")

    ax.axhline(0.57, xmin=0.06, xmax=0.65, color=C_COPPER, linewidth=1.5)

    ax.text(0.06, 0.50, "Event Study Industrial + Validación del Mecanismo Causal (Fase 2)",
            color=C_WHITE, fontsize=11)
    ax.text(0.06, 0.43, "Período: Enero 2026 – Junio 2026   |   72 Eventos T8   |   4 Activos",
            color=C_MGRAY, fontsize=9.5)

    datos = [
        ("72", "Eventos\nAnalizados"),
        ("136.7k ton", "Pérdida\nEstimada"),
        ("42.7%", "Máxima\nCaída"),
        ("4.3h", "Autonomía\nMín. Pila"),
    ]
    for i, (val, lbl) in enumerate(datos):
        x = 0.06 + i * 0.165
        ax.add_patch(FancyBboxPatch((x, 0.24), 0.15, 0.10,
                                    boxstyle="round,pad=0.01",
                                    facecolor=C_DARK, edgecolor=C_COPPER,
                                    linewidth=1.2, alpha=0.8))
        ax.text(x + 0.075, 0.315, val, color=C_GOLD, fontsize=12,
                fontweight="bold", ha="center", va="center")
        ax.text(x + 0.075, 0.260, lbl, color=C_WHITE, fontsize=7,
                ha="center", va="center")

    # Indicador novedades v2
    novedades = ["+ Fase 2: ISR y retardo de pilas", "+ Semaforo de riesgo",
                 "+ Roadmap con fechas", "+ Ventanas consecutivas"]
    for j, nov in enumerate(novedades):
        ax.text(0.73, 0.49 - j * 0.065, nov, color=C_GOLD, fontsize=8, alpha=0.9,
                va="center")

    ax.text(0.06, 0.11, f"Fecha: {DATE_STR}", color=C_WHITE, fontsize=9, va="center", alpha=0.85)
    ax.text(0.06, 0.07, f"{VER}   |   CONFIDENCIAL", color=C_MGRAY, fontsize=8)
    ax.text(0.06, 0.03, "CIO DET — Analítica de Rendimientos — CODELCO División El Teniente",
            color=C_MGRAY, fontsize=7.5)

    # Marca decorativa T8
    theta = np.linspace(0, 2 * np.pi, 300)
    ax.plot(0.82 + 0.22 * np.cos(theta), 0.52 + 0.20 * np.sin(theta),
            color=C_COPPER, linewidth=0.5, alpha=0.2)
    ax.text(0.82, 0.52, "T8", color=C_COPPER, fontsize=60,
            fontweight="bold", ha="center", va="center", alpha=0.10)
    return fig


def page_resumen_ejecutivo() -> plt.Figure:
    fig = _new_page()
    _header(fig, "RESUMEN EJECUTIVO — v2",
            "Event Study + Fase 2 Causal | Respuesta basada en evidencia", page_num=2)
    _footer(fig)

    # 4 KPIs fila superior — ahora incluye autonomia de pilas
    kpis = [
        ("42.7%",  "SAG2 — Máxima caída",         "Activo más sensible al efecto T8",      C_RED),
        ("4.3h",   "UNITARIO — Menor autonomía",   "Pila más vulnerable ante ventana",      C_ORANGE),
        ("73 ev.",  "Eventos clase D (Severos)",   ">40% de caída — 44% de todos",          C_RED),
        ("3 de 4", "Activos con evidencia real",   "SAG1, SAG2 y PMC — p < 0.05",          C_BLUE),
    ]
    for i, (val, lbl, sub, col) in enumerate(kpis):
        _kpi_box(fig, 0.03 + i * 0.245, 0.57, 0.22, 0.27, val, lbl, sub, bg=col)

    _callout(fig, 0.03, 0.27, 0.42, 0.26,
             "T8 detiene la entrega a chancado.\nLas pilas amortiguan (4h-7h segun activo)\npero cuando se agotan, la caida es inevitable.\nFase 2 valida el mecanismo cuantitativamente.",
             bg=C_BLUE, fc=C_WHITE, fontsize=9.5)

    ax2 = fig.add_axes([0.48, 0.27, 0.50, 0.26])
    ax2.set_facecolor(C_LGRAY); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    ax2.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                 boxstyle="round,pad=0.01",
                                 facecolor=C_LGRAY, edgecolor=C_COPPER, linewidth=1.2))
    ax2.text(0.05, 0.88, "NUEVOS HALLAZGOS — FASE 2:", color=C_BLUE,
             fontsize=9, fontweight="bold", va="top")
    bullets_v2 = [
        "ISR confirma que pilas absorben el impacto DURANTE la ventana",
        "Retardo promedio: SAG1=6.9h | SAG2=5.2h | PMC=5.5h | UNITARIO=4.3h",
        "Ventanas consecutivas (<72h) agravan el impacto en todos los activos",
        "Punto de quiebre en 4h: impacto se dispara de 2,507 → 8,242 ton",
    ]
    for j, b in enumerate(bullets_v2):
        ax2.text(0.06, 0.70 - j * 0.175, f"▶  {b}", color=C_DARK, fontsize=8.5, va="center")

    ax_nota = fig.add_axes([0.03, 0.10, 0.95, 0.13])
    ax_nota.set_facecolor(C_LGRAY); ax_nota.set_xlim(0, 1); ax_nota.set_ylim(0, 1); ax_nota.axis("off")
    ax_nota.text(0.02, 0.6, "BASE ANALISIS:",
                 color=C_BLUE, fontsize=8, fontweight="bold", va="center")
    ax_nota.text(0.22, 0.6,
                 "72 ventanas T8 (ene-jun 2026)  |  47,532 registros 5-min  |  Event Study + Fase 2 Causal  |"
                 "  Modelos RF + XGBoost + SHAP  |  T-test + Mann-Whitney (α=0.05)",
                 color=C_MGRAY, fontsize=7.5, va="center")
    return fig


def page_contexto() -> plt.Figure:
    fig = _new_page()
    _header(fig, "CONTEXTO OPERACIONAL",
            "¿Qué es Teniente 8 y cómo afecta los rendimientos?", page_num=3)
    _footer(fig)

    ax = fig.add_axes([0.03, 0.12, 0.38, 0.70])
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off"); ax.set_facecolor(C_LGRAY)
    ax.add_patch(FancyBboxPatch((0.1, 0.1), 9.8, 9.8, boxstyle="round,pad=0.1",
                                facecolor=C_LGRAY, edgecolor=C_COPPER, linewidth=1))
    steps = [
        (C_BLUE,   "TENIENTE 8",                 "Ferrocarril mineral fino/grueso → pilas"),
        (C_ORANGE, "VENTANA DE MANTENIMIENTO",   "2h / 4h / 8h / 12h"),
        (C_RED,    "SIN ENTREGA A CHANCADO",     "Primario y secundario sin alimentacion"),
        (C_RED,    "SIN OFERTA A MOLINOS",       "No hay mineral disponible para moler"),
        (C_COPPER, "CONSUMO DE PILAS",           "Stock amortiguador SAG / PMC / UNITARIO"),
        (C_GREEN,  "CAIDA TPH → RECUPERACION",  "Efecto diferido y retorno gradual"),
    ]
    for (col, ttl, sub), y in zip(steps, [8.8, 7.3, 5.8, 4.3, 2.8, 1.3]):
        ax.add_patch(FancyBboxPatch((0.8, y - 0.5), 8.4, 1.1,
                                    boxstyle="round,pad=0.1",
                                    facecolor=col, edgecolor="none", alpha=0.88))
        ax.text(5, y + 0.15, ttl, color=C_WHITE, fontsize=8.5, fontweight="bold", ha="center")
        ax.text(5, y - 0.18, sub, color=C_WHITE, fontsize=7, ha="center", alpha=0.85)
        if y > 1.3:
            ax.annotate("", xy=(5, y - 0.55), xytext=(5, y - 0.42),
                        arrowprops=dict(arrowstyle="-|>", color=C_MGRAY, lw=1.2))
    ax.set_title("Cadena de impacto T8 — VALIDADA (Fase 2)",
                 color=C_BLUE, fontsize=9, fontweight="bold", pad=4)

    ax2 = fig.add_axes([0.44, 0.12, 0.54, 0.70])
    ax2.set_facecolor(C_WHITE); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    bloques = [
        ("¿QUE ES TENIENTE 8?",
         "Sistema ferroviario que transporta mineral fino y grueso desde la mina "
         "hacia las pilas SAG, PMC y UNITARIO. Es la unica fuente de mineral para los molinos."),
        ("¿QUE CONFIRMA FASE 2?",
         "El Indice de Stock Relativo (ISR) confirma que durante la ventana las pilas "
         "absorben el impacto. Cuando el stock se agota, la caida es inevitable. "
         "El retardo (autonomia) va de 4.3h (UNITARIO) a 6.9h (SAG1)."),
        ("¿POR QUE ES CRITICO?",
         "En 5.5 meses: 72 ventanas, 136.7k ton perdidas. El 70% de los eventos "
         "causan caidas >20% (clase C+D). Sin protocolo, el impacto seguira creciendo."),
        ("¿COMO SE MITIGA?",
         "La autonomia de pila es la palanca operacional. Maximizar stock antes "
         "de la ventana alarga el retardo. Evitar ventanas >4h y consecutivas "
         "es la accion de mayor ROI confirmada por el modelo."),
    ]
    y0 = 0.96
    for ttl, txt in bloques:
        ax2.add_patch(mpatches.Rectangle((0, y0 - 0.21), 0.012, 0.17, color=C_COPPER, alpha=0.9))
        ax2.text(0.025, y0 - 0.035, ttl, color=C_BLUE, fontsize=8.5, fontweight="bold", va="top")
        ax2.text(0.025, y0 - 0.09, textwrap.fill(txt, 68), color=C_DARK, fontsize=7.5,
                 va="top", linespacing=1.5)
        y0 -= 0.26
    return fig


def page_hallazgo_gaviota() -> plt.Figure:
    fig = _new_page()
    _header(fig, "HALLAZGO 1 — EFECTO GAVIOTA",
            "Patron repetitivo estadisticamente significativo — confirmado en 72 eventos", page_num=4)
    _footer(fig)
    _img(fig, FIGS / "event_study" / "09_Efecto_Gaviota_Global.png", 0.03, 0.12, 0.66, 0.72)

    msgs = [
        (C_ORANGE, "PATRON REPETITIVO",
         "72 eventos: misma curva.\nCaida diferida, recuperacion\ngradual. Estadisticamente real."),
        (C_RED, "CAIDA DIFERIDA",
         "Pila absorbe hasta agotar stock.\nRetardo: 4.3h (UNITARIO)\na 6.9h (SAG1). VALIDADO Fase 2."),
        (C_GREEN, "RECUPERACION LENTA",
         "90% del baseline: entre 5.8h\n(UNITARIO) y 11.4h (SAG2).\nExcede un turno completo."),
    ]
    for i, (col, ttl, body) in enumerate(msgs):
        y = 0.73 - i * 0.22
        ax = fig.add_axes([0.73, y, 0.25, 0.19])
        ax.set_facecolor(C_LGRAY); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
        ax.add_patch(mpatches.Rectangle((0, 0), 0.03, 1, color=col))
        ax.text(0.07, 0.78, ttl,  color=col,    fontsize=8.5, fontweight="bold", va="top")
        ax.text(0.07, 0.50, body, color=C_DARK, fontsize=7.5, va="top", linespacing=1.5)

    _callout(fig, 0.73, 0.12, 0.25, 0.13,
             "La evidencia NO es casual:\nFase 2 valida el mecanismo\ncausal de forma cuantitativa.",
             bg=C_BLUE)
    return fig


def page_mecanismo_causal() -> plt.Figure:
    """NUEVA — Fase 2: ISR y Retardo de pilas."""
    fig = _new_page()
    _header(fig, "VALIDACION MECANISMO CAUSAL — FASE 2",
            "ISR (proxy stock pila) confirma agotamiento progresivo y diferido", page_num=5)
    _footer(fig)

    _img(fig, F2 / "Stock_Relativo_Pilas.png", 0.03, 0.12, 0.65, 0.72)

    ax2 = fig.add_axes([0.71, 0.12, 0.27, 0.72])
    ax2.set_facecolor(C_LGRAY); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    ax2.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                 boxstyle="round,pad=0.01",
                                 facecolor=C_LGRAY, edgecolor=C_COPPER, linewidth=1.5))

    ax2.text(0.5, 0.95, "AUTONOMIA DE PILA", color=C_BLUE,
             fontsize=10, fontweight="bold", ha="center", va="top")
    ax2.text(0.5, 0.87, "Horas hasta caida ISR < 90%",
             color=C_MGRAY, fontsize=7.5, ha="center", va="top")

    autos = [("SAG1",     "6.9h", C_BLUE,   0.78),
             ("SAG2",     "5.2h", C_ORANGE, 0.65),
             ("PMC",      "5.5h", C_GREEN,  0.52),
             ("UNITARIO", "4.3h", C_RED,    0.39)]
    for activo, val, col, y in autos:
        ax2.add_patch(FancyBboxPatch((0.06, y - 0.08), 0.88, 0.12,
                                     boxstyle="round,pad=0.01",
                                     facecolor=col, edgecolor="none", alpha=0.13))
        ax2.add_patch(mpatches.Rectangle((0.06, y - 0.08), 0.022, 0.12, color=col))
        ax2.text(0.12, y - 0.02, activo, color=col, fontsize=9, fontweight="bold", va="center")
        ax2.text(0.92, y - 0.02, val, color=col, fontsize=12, fontweight="bold",
                 ha="right", va="center")

    ax2.add_patch(FancyBboxPatch((0.05, 0.06), 0.90, 0.28,
                                 boxstyle="round,pad=0.02",
                                 facecolor=C_BLUE, edgecolor="none", alpha=0.10))
    ax2.text(0.5, 0.27, "QUE SIGNIFICA:", color=C_BLUE, fontsize=8,
             fontweight="bold", ha="center", va="center")
    ax2.text(0.5, 0.19,
             "Cuando T8 se detiene, la pila\nsostiene el TPH durante ESTAS horas.\nDespues el colapso es inevitable.",
             color=C_DARK, fontsize=8, ha="center", va="center", linespacing=1.5)
    ax2.text(0.5, 0.09,
             "Maximizar stock = alargar autonomia.",
             color=C_COPPER, fontsize=8, fontweight="bold", ha="center", va="center")
    return fig


def page_hallazgo_duracion() -> plt.Figure:
    fig = _new_page()
    _header(fig, "HALLAZGO 2 — VENTANAS LARGAS GENERAN MAYOR DANO",
            "Comparacion del efecto por duracion de ventana | Punto de quiebre: 4h", page_num=6)
    _footer(fig)

    layout = [
        ("05_EventStudy_2h.png",  0.03, 0.47, 0.45, 0.41, "2h  |  34.9% caida  |  540 ton/evento",   C_BLUE),
        ("06_EventStudy_4h.png",  0.51, 0.47, 0.45, 0.41, "4h  |  38.3% caida  |  2,507 ton/evento", C_ORANGE),
        ("07_EventStudy_8h.png",  0.03, 0.11, 0.45, 0.41, "8h  |  ~39% caida   |  ~5,375 ton/evento", C_GREEN),
        ("08_EventStudy_12h.png", 0.51, 0.11, 0.45, 0.41, "12h |  39.9% caida  |  8,242 ton/evento", C_RED),
    ]
    for fname, left, bot, w, h, lbl, col in layout:
        _img(fig, FIGS / "event_study" / fname, left, bot + 0.045, w, h - 0.05)
        ax_lbl = fig.add_axes([left, bot, w, 0.04])
        ax_lbl.set_facecolor(col); ax_lbl.axis("off")
        ax_lbl.text(0.5, 0.5, lbl, color=C_WHITE, fontsize=8, fontweight="bold",
                    ha="center", va="center", transform=ax_lbl.transAxes)
    return fig


def page_elasticidad() -> plt.Figure:
    """NUEVA — Fase 2: elasticidad y punto de quiebre."""
    fig = _new_page()
    _header(fig, "HALLAZGO 3 — ELASTICIDAD Y PUNTO DE QUIEBRE",
            "La relacion duracion vs impacto NO es lineal — el quiebre ocurre en 4h", page_num=7)
    _footer(fig)

    _img(fig, F2 / "Elasticidad_T8.png", 0.03, 0.12, 0.65, 0.72)

    ax2 = fig.add_axes([0.71, 0.12, 0.27, 0.72])
    ax2.set_facecolor(C_LGRAY); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    ax2.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                 boxstyle="round,pad=0.01",
                                 facecolor=C_LGRAY, edgecolor=C_COPPER, linewidth=1.5))
    ax2.text(0.5, 0.94, "IMPLICANCIA CRITICA", color=C_BLUE,
             fontsize=10, fontweight="bold", ha="center", va="top")

    zonas = [
        ("ZONA MANEJABLE", "≤ 4 horas",
         "Caida ~38% | 2,507 ton\nRecuperacion en 1 turno\nZona aceptable con protocolo",
         C_GREEN, 0.80),
        ("ZONA CRITICA", "4h – 12h",
         "Cada hora extra: +717 ton\nAmplia el retardo de recuperacion\nVentanas 12h = 3.3x el dano",
         C_RED, 0.52),
        ("RECOMENDACION", "Duracion max.",
         "4 horas es el limite\nSin excepcion sin protocolo\nde pila llena documentado",
         C_BLUE, 0.24),
    ]
    for ttl, sub, body, col, y in zonas:
        ax2.add_patch(FancyBboxPatch((0.04, y - 0.22), 0.92, 0.24,
                                     boxstyle="round,pad=0.01",
                                     facecolor=col, edgecolor="none", alpha=0.12))
        ax2.add_patch(mpatches.Rectangle((0.04, y - 0.22), 0.018, 0.24, color=col))
        ax2.text(0.08, y - 0.01, ttl, color=col, fontsize=9, fontweight="bold", va="center")
        ax2.text(0.08, y - 0.09, sub, color=col, fontsize=8, va="center", alpha=0.85)
        ax2.text(0.08, y - 0.17, body, color=C_DARK, fontsize=7.5,
                 va="center", linespacing=1.4)
    return fig


def page_hallazgo_activos() -> plt.Figure:
    fig = _new_page()
    _header(fig, "HALLAZGO 4 — ¿QUIEN SE AFECTA MAS?",
            "Comparacion normalizada entre activos — TPH como % del baseline pre-ventana", page_num=8)
    _footer(fig)
    _img(fig, FIGS / "event_study" / "10_Comparacion_Activos.png", 0.03, 0.12, 0.66, 0.72)

    ax_tbl = fig.add_axes([0.72, 0.12, 0.26, 0.72])
    ax_tbl.set_facecolor(C_LGRAY); ax_tbl.set_xlim(0, 1); ax_tbl.set_ylim(0, 1); ax_tbl.axis("off")
    ax_tbl.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                    boxstyle="round,pad=0.01",
                                    facecolor=C_LGRAY, edgecolor=C_COPPER, linewidth=1))
    ax_tbl.text(0.5, 0.94, "RANKING DE IMPACTO", color=C_BLUE,
                fontsize=9, fontweight="bold", ha="center", va="top")

    ranking = [
        ("1°", "SAG2",     "42.7%", "6.9h*", "11.4h", C_RED),
        ("2°", "PMC",      "39.3%", "5.5h*",  "8.4h", C_ORANGE),
        ("3°", "SAG1",     "37.3%", "5.2h*", "10.4h", C_BLUE),
        ("4°", "UNITARIO", "19.4%", "4.3h*",  "5.8h", C_GREEN),
    ]
    headers = ["Pos", "Activo", "Caida%", "Aut.*", "Rec90"]
    hx = [0.04, 0.18, 0.47, 0.66, 0.84]
    for h, x in zip(headers, hx):
        ax_tbl.text(x, 0.86, h, color=C_MGRAY, fontsize=7, fontweight="bold")
    ax_tbl.axhline(0.83, color=C_COPPER, linewidth=0.8, xmin=0.02, xmax=0.98)

    for j, (pos, act, caida, aut, rec, col) in enumerate(ranking):
        y = 0.76 - j * 0.17
        ax_tbl.add_patch(mpatches.Rectangle((0.02, y - 0.04), 0.96, 0.13, color=col, alpha=0.08))
        ax_tbl.add_patch(mpatches.Rectangle((0.02, y - 0.04), 0.012, 0.13, color=col))
        for val, x in zip([pos, act, caida, aut, rec], hx):
            ax_tbl.text(x, y + 0.02, val, color=C_DARK if val not in [pos, caida] else col,
                        fontsize=8, fontweight="bold" if val in [pos, act] else "normal", va="center")

    ax_tbl.axhline(0.38, color=C_MGRAY, linewidth=0.4, xmin=0.02, xmax=0.98, linestyle="--")
    ax_tbl.text(0.5, 0.30, "* Autonomia pila (Fase 2)", color=C_MGRAY,
                fontsize=7, ha="center", va="center", style="italic")
    ax_tbl.text(0.5, 0.18, "UNITARIO: activo\nmas resiliente,\nmenor autonomia",
                color=C_GREEN, fontsize=8, ha="center", va="center", linespacing=1.4, fontweight="bold")
    return fig


def page_clasificacion_eventos() -> plt.Figure:
    """NUEVA — Fase 2: clasificacion A/B/C/D de eventos."""
    fig = _new_page()
    _header(fig, "CLASIFICACION DE EVENTOS — A / B / C / D",
            "Severidad del impacto por caida% | Fase 2 Mecanismo Causal", page_num=9)
    _footer(fig)

    ax = fig.add_axes([0.03, 0.12, 0.60, 0.72])
    ax.set_facecolor(C_WHITE)

    clases = ["A — Sin impacto\n(<5%)", "B — Leve\n(5-20%)",
              "C — Moderado\n(20-40%)", "D — Severo\n(>40%)"]
    vals   = [11, 24, 58, 73]
    total  = sum(vals)
    colors = [C_GREEN, C_AMBER, C_ORANGE, C_RED]
    x_pos  = np.arange(len(clases))
    bars   = ax.bar(x_pos, vals, color=colors, alpha=0.85, width=0.55, edgecolor=C_WHITE, linewidth=1.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.5,
                f"{v}\n({v/total*100:.0f}%)",
                ha="center", va="bottom", fontsize=11, fontweight="bold", color=C_DARK)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(clases, fontsize=10)
    ax.set_ylabel("N° registros (evento × activo)", fontsize=10)
    ax.set_title("Distribución de eventos por clase de impacto\n(166 registros = 72 eventos × 4 activos, con cobertura parcial)",
                 fontsize=10)
    ax.grid(True, alpha=0.2, axis="y")
    ax.set_ylim(0, 90)

    # Panel derecho: características y decisión
    ax2 = fig.add_axes([0.66, 0.12, 0.32, 0.72])
    ax2.set_facecolor(C_LGRAY); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    ax2.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                 boxstyle="round,pad=0.01",
                                 facecolor=C_LGRAY, edgecolor=C_COPPER, linewidth=1.5))
    ax2.text(0.5, 0.95, "GUIA DE DECISION", color=C_BLUE,
             fontsize=9.5, fontweight="bold", ha="center", va="top")

    decisiones = [
        ("D — SEVERO",  ">40%", "Activar compensacion\ninmediata desde circuito\nalternativo. Notificar.",  C_RED,    0.82),
        ("C — MODERADO","20-40%","Monitorear recuperacion.\nPrepara compensacion si\nno recupera en 8h.",   C_ORANGE, 0.61),
        ("B — LEVE",    "5-20%", "Seguimiento normal.\nRegistrar para estadistica.\nNo accion inmediata.",  C_AMBER,  0.40),
        ("A — OK",      "<5%",   "Sin accion. Evento\nabsorbido por la pila.\nRegistrar autonomia.",        C_GREEN,  0.19),
    ]
    for cls, rng, accion, col, y in decisiones:
        ax2.add_patch(FancyBboxPatch((0.03, y - 0.15), 0.94, 0.18,
                                     boxstyle="round,pad=0.01",
                                     facecolor=col, edgecolor="none", alpha=0.12))
        ax2.add_patch(mpatches.Rectangle((0.03, y - 0.15), 0.016, 0.18, color=col))
        ax2.text(0.09, y - 0.02, cls, color=col, fontsize=8.5, fontweight="bold", va="center")
        ax2.text(0.09, y - 0.08, rng, color=col, fontsize=7.5, va="center", alpha=0.85)
        ax2.text(0.09, y - 0.12, accion, color=C_DARK, fontsize=7.5, va="center", linespacing=1.4)
    return fig


def page_consecutivas() -> plt.Figure:
    """NUEVA — Fase 2: ventanas consecutivas."""
    fig = _new_page()
    _header(fig, "EFECTO ACUMULATIVO — VENTANAS CONSECUTIVAS",
            "Ventanas separadas por menos de 72h generan mayor dano que eventos aislados", page_num=10)
    _footer(fig)

    _img(fig, F2 / "Eventos_Acumulados_T8.png", 0.03, 0.12, 0.70, 0.72)

    ax2 = fig.add_axes([0.76, 0.12, 0.22, 0.72])
    ax2.set_facecolor(C_LGRAY); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    ax2.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                 boxstyle="round,pad=0.01",
                                 facecolor=C_LGRAY, edgecolor=C_RED, linewidth=2))
    ax2.text(0.5, 0.93, "ALERTA", color=C_RED,
             fontsize=11, fontweight="bold", ha="center", va="top")
    ax2.text(0.5, 0.84, "VENTANAS\nCONSECUTIVAS",
             color=C_RED, fontsize=8.5, fontweight="bold", ha="center", va="top")

    ax2.add_patch(FancyBboxPatch((0.06, 0.52), 0.88, 0.28,
                                 boxstyle="round,pad=0.02",
                                 facecolor=C_RED, edgecolor="none", alpha=0.10))
    ax2.text(0.5, 0.70, "116 / 166", color=C_RED, fontsize=14,
             fontweight="bold", ha="center", va="center")
    ax2.text(0.5, 0.60, "registros son\nconsecutivos (70%!)",
             color=C_DARK, fontsize=8.5, ha="center", va="center", linespacing=1.4)

    ax2.text(0.5, 0.43,
             "La segunda ventana no\nencuentra la pila llena.\nEl sistema NO se recupero.",
             color=C_DARK, fontsize=8, ha="center", va="center", linespacing=1.5)

    ax2.text(0.5, 0.24, "ACCION:", color=C_BLUE, fontsize=8.5,
             fontweight="bold", ha="center", va="center")
    ax2.text(0.5, 0.15,
             "Minimo 72h entre\nventanas programadas\nsin excepcion.",
             color=C_BLUE, fontsize=8, ha="center", va="center", linespacing=1.5)
    return fig


def page_hallazgo_recuperacion() -> plt.Figure:
    fig = _new_page()
    _header(fig, "HALLAZGO 5 — TIEMPO DE RECUPERACION",
            "Horas necesarias para recuperar 80%, 90%, 95% y 100% del baseline", page_num=11)
    _footer(fig)

    _img(fig, FIGS / "event_study" / "11_Tiempo_Recuperacion.png", 0.03, 0.12, 0.48, 0.72)
    _img(fig, F2 / "Recuperacion_vs_Ventana.png", 0.53, 0.12, 0.45, 0.72)
    return fig


def page_hallazgo_estadistica(data: dict) -> plt.Figure:
    fig = _new_page()
    _header(fig, "HALLAZGO 6 — EVIDENCIA ESTADISTICA",
            "T-test de Welch + Mann-Whitney U  |  alpha = 0.05", page_num=12)
    _footer(fig)

    df_stat = data["stat"]
    ax_tbl = fig.add_axes([0.03, 0.38, 0.62, 0.46])
    ax_tbl.set_facecolor(C_LGRAY); ax_tbl.set_xlim(0, 10); ax_tbl.set_ylim(0, 5.5); ax_tbl.axis("off")
    headers = ["Activo", "TPH Pre", "TPH Post", "Delta%", "p-value T-test", "Resultado"]
    hx      = [0.3, 1.9, 3.6, 5.2, 6.6, 8.5]
    ax_tbl.add_patch(mpatches.Rectangle((0, 4.7), 10, 0.7, color=C_BLUE))
    for h, x in zip(headers, hx):
        ax_tbl.text(x, 5.0, h, color=C_WHITE, fontsize=8.5, fontweight="bold", va="center")

    row_data = [
        (r["activo"], f"{r['tph_pre_mean']:.0f}", f"{r['tph_post_mean']:.0f}",
         f"{r['delta_pct']:+.1f}%", f"{r['t_pval']:.4f}", r["significativo"])
        for _, r in df_stat.iterrows()
    ]
    for j, (act, pre, post, delta, pval, sig) in enumerate(row_data):
        y = 3.9 - j * 1.0
        ax_tbl.add_patch(mpatches.Rectangle((0.1, y - 0.3), 9.8, 0.85,
                                             color=C_LGRAY if j % 2 == 0 else C_WHITE, alpha=0.7))
        sig_col = C_GREEN if sig == "SI" else C_MGRAY
        for val, x in zip([act, pre, post, delta, pval,
                            "SIGNIFICATIVO  ✓" if sig == "SI" else "No significativo"],
                           hx):
            ax_tbl.text(x, y + 0.1, val, color=sig_col if val.startswith("SIG") or val.startswith("No") else C_DARK,
                        fontsize=8.5, va="center",
                        fontweight="bold" if val.startswith("SIG") else "normal")

    ax_int = fig.add_axes([0.67, 0.38, 0.30, 0.46])
    ax_int.set_facecolor(C_BLUE); ax_int.set_xlim(0, 1); ax_int.set_ylim(0, 1); ax_int.axis("off")
    ax_int.add_patch(FancyBboxPatch((0.02, 0.02), 0.96, 0.96,
                                    boxstyle="round,pad=0.02",
                                    facecolor=C_BLUE, edgecolor=C_COPPER, linewidth=1.5))
    ax_int.text(0.5, 0.88, "INTERPRETACION", color=C_GOLD,
                fontsize=8.5, fontweight="bold", ha="center", va="top")
    ax_int.text(0.5, 0.68,
                "Los resultados NO son\natribuibles al azar.\n\nSAG1, SAG2 y PMC:\ndiferencia pre/post\nestadisticamente real.\n\nEl efecto T8 existe y\npuede ser medido\ncon confianza.",
                color=C_WHITE, fontsize=8.5, ha="center", va="top", linespacing=1.6)

    _callout(fig, 0.03, 0.14, 0.45, 0.20,
             "UNITARIO: p=0.24, no significativo.\nMenor caida (19.4%) con mayor variabilidad.\nRequiere mas eventos para confirmar.",
             bg=C_LGRAY, fc=C_DARK, fontsize=9)
    _callout(fig, 0.52, 0.14, 0.45, 0.20,
             "SAG2: mayor impacto economico absoluto.\n61.7k ton perdidas. Accion prioritaria.",
             bg=C_LGRAY, fc=C_DARK, fontsize=9)
    return fig


def page_impacto() -> plt.Figure:
    fig = _new_page()
    _header(fig, "IMPACTO OPERACIONAL",
            "Toneladas no producidas y costo estimado — periodo ene-jun 2026", page_num=13)
    _footer(fig)

    ton_data = [
        ("136.7k ton", "TOTAL PERDIDO",  "72 eventos · 5.5 meses",       C_RED),
        ("61.7k ton",  "SAG2 — Lider",   "45% de la perdida total",       C_ORANGE),
        ("23.2k ton",  "SAG1",           "17.7% de produccion esperada",  C_BLUE),
        ("33.6k ton",  "PMC",            "13.6% de produccion esperada",  C_COPPER),
    ]
    for i, (val, lbl, sub, col) in enumerate(ton_data):
        _kpi_box(fig, 0.03 + i * 0.245, 0.60, 0.22, 0.24, val, lbl, sub, bg=col)

    _img(fig, FIGS / "prescriptivo" / "P2_Toneladas_Perdidas.png", 0.03, 0.12, 0.60, 0.44)

    ax_val = fig.add_axes([0.66, 0.12, 0.32, 0.44])
    ax_val.set_facecolor(C_DARK); ax_val.set_xlim(0, 1); ax_val.set_ylim(0, 1); ax_val.axis("off")
    ax_val.add_patch(FancyBboxPatch((0.02, 0.02), 0.96, 0.96,
                                    boxstyle="round,pad=0.02",
                                    facecolor=C_DARK, edgecolor=C_GOLD, linewidth=1.5))
    ax_val.text(0.5, 0.91, "VALOR REFERENCIAL", color=C_GOLD,
                fontsize=8.5, fontweight="bold", ha="center", va="top")
    items = [("Grade mineral", "1.2% Cu"), ("Recuperacion", "86%"),
             ("Precio LME ref.", "USD 9,500/ton Cu"), ("Cu perdido", "~1,414 ton Cu"),
             ("Valor periodo", "~USD 13.4M"), ("Valor anual", "~USD 29.2M")]
    for j, (k, v) in enumerate(items):
        y = 0.74 - j * 0.11
        ax_val.text(0.08, y, k + ":", color=C_MGRAY, fontsize=8, va="center")
        ax_val.text(0.92, y, v, color=C_GOLD, fontsize=8.5, va="center",
                    ha="right", fontweight="bold")
    ax_val.text(0.5, 0.03, "Referencial — sujeto a grade y recuperacion real",
                color=C_MGRAY, fontsize=6.5, ha="center", va="bottom", alpha=0.7)
    return fig


def page_semaforo() -> plt.Figure:
    """NUEVA — Semáforo de riesgo operacional."""
    fig = _new_page()
    _header(fig, "SEMAFORO DE RIESGO OPERACIONAL",
            "Estado actual del sistema ante ventanas T8 — evaluacion integrada Fase 1 + Fase 2",
            page_num=14)
    _footer(fig)

    ax = fig.add_axes([0.03, 0.12, 0.46, 0.72])
    ax.set_facecolor(C_LGRAY); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                boxstyle="round,pad=0.01",
                                facecolor=C_LGRAY, edgecolor=C_BLUE, linewidth=1.5))

    # Dimension filas x columna
    dimensiones = [
        ("VULNERABILIDAD SAG2",       "CRITICO",    C_RED,    "42.7% caida  |  61.7k ton  |  11.4h rec."),
        ("VENTANAS CONSECUTIVAS",     "CRITICO",    C_RED,    "70% de registros son consecutivos (<72h)"),
        ("AUTONOMIA PILA UNITARIO",   "ALTO",       C_RED,    "4.3h autonomia — menor del sistema"),
        ("VENTANAS 12H ACTIVAS",      "ALTO",       C_RED,    "7 eventos en periodo → 57.7k ton"),
        ("RECUPERACION SAG1/SAG2",    "ALTO",       C_ORANGE, "Excede un turno (>10h para recuperar 90%)"),
        ("PROTOCOLO PILA LLENA",      "PENDIENTE",  C_ORANGE, "No existe protocolo formal documentado"),
        ("MONITOREO TIEMPO REAL",     "PENDIENTE",  C_AMBER,  "Sin alerta automatica de caida durante ventana"),
        ("EVIDENCIA ESTADISTICA",     "CONFIRMADO", C_GREEN,  "3 de 4 activos — p < 0.05 — accion respaldada"),
    ]

    # Encabezados
    ax.add_patch(mpatches.Rectangle((0.03, 0.915), 0.94, 0.065, color=C_BLUE))
    ax.text(0.06, 0.948, "DIMENSIÓN", color=C_WHITE, fontsize=8, fontweight="bold", va="center")
    ax.text(0.60, 0.948, "NIVEL", color=C_WHITE, fontsize=8, fontweight="bold", va="center")
    ax.text(0.73, 0.948, "DESCRIPCIÓN", color=C_WHITE, fontsize=8, fontweight="bold", va="center")

    step = 0.86 / len(dimensiones)
    for i, (dim, nivel, col, desc) in enumerate(dimensiones):
        y = 0.905 - (i + 1) * step
        bg = col if col == C_GREEN else "none"
        ax.add_patch(mpatches.Rectangle((0.03, y + 0.005), 0.94, step - 0.01,
                                         color=col, alpha=0.07))
        ax.add_patch(mpatches.Rectangle((0.03, y + 0.005), 0.010, step - 0.01, color=col))
        ax.text(0.06, y + step * 0.5, dim, color=C_DARK, fontsize=7.5, fontweight="bold", va="center")
        ax.add_patch(FancyBboxPatch((0.575, y + 0.01), 0.125, step - 0.025,
                                    boxstyle="round,pad=0.01", facecolor=col, edgecolor="none", alpha=0.88))
        ax.text(0.637, y + step * 0.5, nivel, color=C_WHITE, fontsize=6.5,
                fontweight="bold", ha="center", va="center")
        ax.text(0.72, y + step * 0.5, desc, color=C_DARK, fontsize=7, va="center")

    # Leyenda semaforo
    ax2 = fig.add_axes([0.52, 0.12, 0.46, 0.72])
    ax2.set_facecolor(C_LGRAY); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    ax2.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                 boxstyle="round,pad=0.01",
                                 facecolor=C_LGRAY, edgecolor=C_COPPER, linewidth=1.5))

    ax2.text(0.5, 0.94, "ESTADO GLOBAL DEL SISTEMA", color=C_BLUE,
             fontsize=10, fontweight="bold", ha="center", va="top")

    # Semaforo visual
    sema_cx = 0.5
    for j, (col, lbl, radio) in enumerate([(C_RED, "CRITICO", 0.11),
                                            (C_ORANGE, "ALTO", 0.085),
                                            (C_AMBER, "MEDIO", 0.07),
                                            (C_GREEN, "OK", 0.06)]):
        theta = np.linspace(0, 2 * np.pi, 200)
        y_circ = 0.73 - j * 0.165
        es_activo = j <= 1
        alpha_c = 1.0 if es_activo else 0.25
        ax2.fill(sema_cx + radio * np.cos(theta), y_circ + radio * 0.8 * np.sin(theta),
                 color=col, alpha=alpha_c)
        ax2.text(sema_cx, y_circ, lbl, color=C_WHITE, fontsize=8,
                 fontweight="bold", ha="center", va="center")

    ax2.text(0.5, 0.33,
             "El sistema esta en zona\nCRITICO / ALTO.\nSe requieren acciones\ninmediatas en ventanas\nconsecutivas y SAG2.",
             color=C_DARK, fontsize=9, ha="center", va="center", linespacing=1.6)

    ax2.add_patch(FancyBboxPatch((0.05, 0.04), 0.90, 0.10,
                                 boxstyle="round,pad=0.02",
                                 facecolor=C_RED, edgecolor="none", alpha=0.12))
    ax2.text(0.5, 0.09,
             "SIN ACCION: El riesgo seguira creciendo\npor efecto acumulativo de ventanas consecutivas.",
             color=C_RED, fontsize=8, fontweight="bold", ha="center", va="center", linespacing=1.4)
    return fig


def page_roadmap() -> plt.Figure:
    """NUEVA — Roadmap de implementación con fechas."""
    fig = _new_page()
    _header(fig, "ROADMAP DE IMPLEMENTACION",
            "Acciones fechadas con responsable y KPI de seguimiento", page_num=15)
    _footer(fig)

    # Fechas relativas a hoy
    hoy = TODAY
    dates = {
        "CP1": hoy + timedelta(days=3),
        "CP2": hoy + timedelta(days=7),
        "CP3": hoy + timedelta(days=14),
        "CP4": hoy + timedelta(days=21),
        "MP1": hoy + timedelta(days=45),
        "MP2": hoy + timedelta(days=60),
        "MP3": hoy + timedelta(days=75),
        "MP4": hoy + timedelta(days=90),
        "LP1": hoy + timedelta(days=120),
        "LP2": hoy + timedelta(days=150),
        "LP3": hoy + timedelta(days=180),
    }

    columnas = [
        ("CORTO PLAZO", "0 – 30 días", C_RED, [
            ("CP1", "Protocolo Pila Llena",
             "Regla: stock mínimo antes de ventana ≥4h",
             "Operaciones", dates["CP1"].strftime("%d/%m"),
             "Stock pila > umbral antes de ventana"),
            ("CP2", "Alerta Automática SAG2",
             "Notificación si caida TPH > 30% durante ventana",
             "CIO / Automatización", dates["CP2"].strftime("%d/%m"),
             "Tiempo respuesta < 15 min"),
            ("CP3", "Aviso 48h Ventanas T8",
             "PAM notifica con 48h de anticipación",
             "PAM Mantto", dates["CP3"].strftime("%d/%m"),
             "100% de ventanas avisadas con anticipación"),
            ("CP4", "Prohibición Ventanas Consecutivas",
             "Sin ventanas T8 a menos de 72h de separación",
             "Planificación + PAM", dates["CP4"].strftime("%d/%m"),
             "0 eventos consecutivos < 72h"),
        ]),
        ("MEDIANO PLAZO", "1 – 3 meses", C_ORANGE, [
            ("MP1", "Redistribuir Ventanas 12h",
             "Mover trabajos 12h a próxima parada mayor",
             "Planificación", dates["MP1"].strftime("%d/%m"),
             "0 ventanas 12h en periodo normal"),
            ("MP2", "Diagnóstico Capacidad UNITARIO",
             "Evaluar ampliación de pila (menor IAP)",
             "Opt. Activos", dates["MP2"].strftime("%d/%m"),
             "IAP UNITARIO > 2.5"),
            ("MP3", "Registro Duracion Real vs Planif.",
             "PAM registra brecha duracion planif./real",
             "PAM Mantto", dates["MP3"].strftime("%d/%m"),
             "Brecha media < 15%"),
            ("MP4", "Protocolo Compensación Alternativo",
             "Compensación desde circuito alternativo si clase D",
             "Operaciones", dates["MP4"].strftime("%d/%m"),
             "Activado en 100% de eventos clase D"),
        ]),
        ("LARGO PLAZO", "3 – 6 meses", C_BLUE, [
            ("LP1", "Modelo Predictivo Impacto",
             "Score de riesgo por ventana antes de autorizar",
             "CIO / Analítica", dates["LP1"].strftime("%d/%m"),
             "Precisión modelo > 75%"),
            ("LP2", "Dashboard Tiempo Real TPH",
             "Mural operacional: TPH vs ventana activa",
             "CIO", dates["LP2"].strftime("%d/%m"),
             "Uso diario por turno confirmado"),
            ("LP3", "Programa Anual Ventanas T8",
             "Límite semestral de ventanas 12h por contrato",
             "Planificación + Contratos", dates["LP3"].strftime("%d/%m"),
             "Max 3 ventanas 12h por semestre"),
        ]),
    ]

    for col_i, (ttl, period, col, items) in enumerate(columnas):
        x = 0.02 + col_i * 0.328
        ax_h = fig.add_axes([x, 0.76, 0.315, 0.085])
        ax_h.set_facecolor(col); ax_h.axis("off")
        ax_h.text(0.5, 0.65, ttl, color=C_WHITE, fontsize=10, fontweight="bold",
                  ha="center", va="center")
        ax_h.text(0.5, 0.20, period, color=C_GOLD, fontsize=8.5, ha="center", va="center")

        n_items = len(items)
        item_h  = 0.62 / n_items
        for j, (cod, ttl_a, desc, resp, fecha, kpi) in enumerate(items):
            y = 0.12 + (n_items - 1 - j) * item_h
            ax_i = fig.add_axes([x, y, 0.315, item_h - 0.008])
            ax_i.set_facecolor(C_LGRAY); ax_i.set_xlim(0, 1); ax_i.set_ylim(0, 1); ax_i.axis("off")
            ax_i.add_patch(mpatches.Rectangle((0, 0), 0.007, 1, color=col))
            # Código + fecha
            ax_i.add_patch(FancyBboxPatch((0.01, 0.55), 0.12, 0.40,
                                          boxstyle="round,pad=0.01",
                                          facecolor=col, edgecolor="none"))
            ax_i.text(0.07, 0.74, cod, color=C_WHITE, fontsize=7.5,
                      fontweight="bold", ha="center", va="center")
            ax_i.text(0.5, 0.86, ttl_a, color=col, fontsize=8, fontweight="bold", va="center")
            ax_i.text(0.5, 0.68, desc[:55], color=C_DARK, fontsize=7, va="center")
            # Responsable y fecha
            ax_i.add_patch(FancyBboxPatch((0.02, 0.06), 0.44, 0.28,
                                          boxstyle="round,pad=0.01",
                                          facecolor=col, edgecolor="none", alpha=0.18))
            ax_i.text(0.24, 0.20, f"Resp: {resp}", color=col, fontsize=6.5,
                      ha="center", va="center", fontweight="bold")
            ax_i.add_patch(FancyBboxPatch((0.50, 0.06), 0.22, 0.28,
                                          boxstyle="round,pad=0.01",
                                          facecolor=col, edgecolor="none", alpha=0.18))
            ax_i.text(0.61, 0.20, fecha, color=col, fontsize=7.5,
                      ha="center", va="center", fontweight="bold")
            ax_i.text(0.76, 0.20, kpi[:28], color=C_MGRAY, fontsize=6,
                      ha="center", va="center")

    return fig


def page_riesgos() -> plt.Figure:
    fig = _new_page()
    _header(fig, "RIESGOS OPERACIONALES",
            "Top 5 riesgos identificados — estado actualizado con Fase 2", page_num=16)
    _footer(fig)

    riesgos = [
        ("R1", "VULNERABILIDAD CRITICA DE SAG2",
         "SAG2: 42.7% caida, 61.7k ton perdidas (45% del total), 11.4h para 90%. "
         "Prioridad maxima en protocolo de ventanas y compensacion.",
         "CRITICO", C_RED),
        ("R2", "VENTANAS CONSECUTIVAS — EFECTO ACUMULATIVO",
         "El 70% de los registros corresponden a ventanas consecutivas (<72h). "
         "La pila no se recupera entre eventos: el dano se amplifica. FASE 2 confirma el riesgo.",
         "CRITICO", C_RED),
        ("R3", "VENTANAS 12H — IMPACTO SEVERO UNITARIO",
         "7 eventos 12h = 57.7k ton (42% del total). Maximo recomendable: 4h. "
         "Sin protocolo de compensacion el impacto es irrecuperable.",
         "ALTO", C_ORANGE),
        ("R4", "AUTONOMIA MINIMA UNITARIO",
         "UNITARIO tiene solo 4.3h de autonomia (pila se agota primero). "
         "Si la ventana dura ≥4h con pila baja, la caida ocurre DURANTE la ventana.",
         "ALTO", C_ORANGE),
        ("R5", "RECUPERACION EXCEDE EL TURNO",
         "SAG2 (11.4h) y SAG1 (10.4h) para recuperar 90%. El efecto se arrastra al turno siguiente. "
         "Sin protocolo post-ventana la perdida no queda registrada ni compensada.",
         "MEDIO", C_AMBER),
    ]
    for i, (cod, ttl, desc, nivel, col) in enumerate(riesgos):
        y = 0.77 - i * 0.132
        ax = fig.add_axes([0.03, y, 0.94, 0.113])
        ax.set_facecolor(C_LGRAY); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
        ax.add_patch(mpatches.Rectangle((0, 0), 0.010, 1, color=col))
        ax.add_patch(FancyBboxPatch((0.013, 0.10), 0.055, 0.80,
                                    boxstyle="round,pad=0.02", facecolor=col, edgecolor="none"))
        ax.text(0.040, 0.50, cod, color=C_WHITE, fontsize=9, fontweight="bold",
                ha="center", va="center")
        ax.text(0.082, 0.72, ttl, color=col, fontsize=9, fontweight="bold", va="center")
        ax.text(0.082, 0.27, desc, color=C_DARK, fontsize=7.5, va="center")
        ax.add_patch(FancyBboxPatch((0.87, 0.18), 0.115, 0.62,
                                    boxstyle="round,pad=0.02", facecolor=col, edgecolor="none", alpha=0.15))
        ax.text(0.928, 0.49, nivel, color=col, fontsize=8, fontweight="bold",
                ha="center", va="center")
    return fig


def page_recomendaciones() -> plt.Figure:
    fig = _new_page()
    _header(fig, "RECOMENDACIONES OPERACIONALES",
            "Acciones validadas por Event Study + Fase 2 Causal | Reforzadas con datos", page_num=17)
    _footer(fig)

    # Refuerzo: mensaje central sobre datos
    ax_top = fig.add_axes([0.03, 0.77, 0.94, 0.075])
    ax_top.set_facecolor(C_BLUE); ax_top.set_xlim(0, 1); ax_top.set_ylim(0, 1); ax_top.axis("off")
    ax_top.text(0.5, 0.5,
                "Todas las acciones estan respaldadas por evidencia cuantitativa (Event Study + Fase 2). "
                "La autonomia de pila es la palanca operacional principal.",
                color=C_GOLD, fontsize=9, ha="center", va="center", fontweight="bold")

    columns = [
        ("INMEDIATO", "Esta semana", C_RED, [
            ("Operaciones", "Protocolo pila llena (min. 48h antes de ventana ≥4h)", "CRITICO", "INMEDIATA"),
            ("Operaciones", "Regla: min. 72h entre ventanas T8 consecutivas",         "CRITICO", "INMEDIATA"),
            ("PAM Mantto",  "Aviso ventana T8 con 48h de anticipacion",               "ALTO",   "INMEDIATA"),
            ("Planificacion","Evitar toda ventana 12h sin parada mayor autorizada",    "ALTO",   "INMEDIATA"),
        ]),
        ("CORTO-MEDIO", "1 – 3 meses", C_ORANGE, [
            ("Planificacion", "Redistribuir trabajos 12h a proxima parada programada", "MUY ALTO", "ALTA"),
            ("Opt. Activos",  "Evaluar capacidad pila UNITARIO (autonomia 4.3h < 4h)", "ALTO",    "ALTA"),
            ("PAM Mantto",    "Registrar duracion real vs planificada por evento",      "MEDIO",   "ALTA"),
            ("Operaciones",   "Protocolo compensacion clase D: activar circuito alterno","ALTO",   "ALTA"),
        ]),
        ("LARGO PLAZO", "3 – 6 meses", C_BLUE, [
            ("CIO / Opt.",    "Modelo predictivo score de riesgo por ventana",  "ALTO",    "MEDIA"),
            ("Opt. Activos",  "Evaluar inversion capacidad pila SAG2",          "ALTO",    "MEDIA"),
            ("Planificacion", "Programa anual: maximo 3 ventanas 12h/semestre", "MUY ALTO","ALTA"),
            ("CIO",           "Dashboard TPH tiempo real vs ventana activa",    "MEDIO",   "MEDIA"),
        ]),
    ]

    for col_i, (ttl, period, col, items) in enumerate(columns):
        x = 0.03 + col_i * 0.325
        ax_h = fig.add_axes([x, 0.64, 0.31, 0.10])
        ax_h.set_facecolor(col); ax_h.axis("off")
        ax_h.text(0.5, 0.65, ttl,    color=C_WHITE, fontsize=10, fontweight="bold", ha="center", va="center")
        ax_h.text(0.5, 0.22, period, color=C_GOLD,  fontsize=8.5, ha="center", va="center")

        for j, (area, accion, imp, prio) in enumerate(items):
            y = 0.48 - j * 0.127
            ax_i = fig.add_axes([x, y, 0.31, 0.112])
            ax_i.set_facecolor(C_LGRAY); ax_i.set_xlim(0, 1); ax_i.set_ylim(0, 1); ax_i.axis("off")
            ax_i.add_patch(mpatches.Rectangle((0, 0), 0.007, 1, color=col))
            ax_i.text(0.03, 0.83, area,   color=col,    fontsize=7, fontweight="bold", va="top")
            ax_i.text(0.03, 0.50, accion[:65], color=C_DARK, fontsize=7, va="top", linespacing=1.3)
            ax_i.add_patch(FancyBboxPatch((0.03, 0.04), 0.30, 0.28,
                                          boxstyle="round,pad=0.01",
                                          facecolor=col, edgecolor="none", alpha=0.18))
            ax_i.text(0.18, 0.18, f"Imp: {imp}", color=col, fontsize=6.5,
                      ha="center", va="center", fontweight="bold")
            ax_i.add_patch(FancyBboxPatch((0.35, 0.04), 0.28, 0.28,
                                          boxstyle="round,pad=0.01",
                                          facecolor=C_MGRAY, edgecolor="none", alpha=0.18))
            ax_i.text(0.49, 0.18, f"Prio: {prio}", color=C_MGRAY, fontsize=6.5,
                      ha="center", va="center")
    return fig


def page_conclusiones() -> plt.Figure:
    fig = _new_page()
    _header(fig, "CONCLUSIONES FINALES — v2",
            "Respuestas directas del comite — validadas por Fase 2 Mecanismo Causal", page_num=18)
    _footer(fig)

    preguntas = [
        ("¿Existe efecto gaviota?",
         "SI — Confirmado en 72 eventos. Las pilas absorben el impacto (4.3h a 6.9h segun activo)\n"
         "pero cuando se agotan, la caida es estadisticamente significativa (p<0.05) en SAG1, SAG2 y PMC.",
         C_GREEN),
        ("¿Que activo es mas vulnerable?",
         "SAG2: mayor caida (42.7%), mayor perdida absoluta (61.7k ton). "
         "UNITARIO: menor autonomia de pila (4.3h), expuesto si ventana ≥4h con stock bajo.",
         C_RED),
        ("¿Que duracion genera mayor impacto?",
         "Las ventanas de 12h: 8,242 ton por evento (3.3x vs 4h). "
         "Punto de quiebre confirmado en 4h. MAXIMO RECOMENDABLE: 4h sin excepcion.",
         C_ORANGE),
        ("¿Son peligrosas las ventanas consecutivas?",
         "SI — 70% de los registros son consecutivos (<72h). La pila no se recupera entre eventos.\n"
         "Regla minima: 72h de separacion entre ventanas. Confirmado por Fase 2.",
         C_RED),
        ("¿Que accion deberia priorizar el comite?",
         "1° Prohibir ventanas consecutivas (<72h) — accion inmediata, costo cero.\n"
         "2° Protocolo pila llena antes de toda ventana ≥4h — palanca operacional principal.",
         C_COPPER),
    ]

    for i, (preg, resp, col) in enumerate(preguntas):
        y = 0.78 - i * 0.132
        ax = fig.add_axes([0.03, y, 0.94, 0.115])
        ax.set_facecolor(C_LGRAY); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
        ax.add_patch(mpatches.Rectangle((0, 0), 0.005, 1, color=col))
        ax.add_patch(FancyBboxPatch((0.008, 0.05), 0.048, 0.90,
                                    boxstyle="round,pad=0.01",
                                    facecolor=col, edgecolor="none", alpha=0.15))
        ax.text(0.032, 0.50, f"P{i+1}", color=col, fontsize=11, fontweight="bold",
                ha="center", va="center")
        ax.text(0.070, 0.75, preg, color=col, fontsize=9, fontweight="bold", va="center")
        ax.text(0.070, 0.32, resp, color=C_DARK, fontsize=8, va="center", linespacing=1.4)
    return fig


def page_cierre() -> plt.Figure:
    fig = _new_page(C_BLUE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(C_BLUE); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(mpatches.Rectangle((0, 0), 0.006, 1, color=C_COPPER))

    ax.text(0.5, 0.80, "GRACIAS", color=C_GOLD, fontsize=36, fontweight="bold", ha="center")
    ax.text(0.5, 0.66, f"Analítica de Rendimientos — CIO DET — {VER}",
            color=C_WHITE, fontsize=13, ha="center")
    ax.axhline(0.60, xmin=0.20, xmax=0.80, color=C_COPPER, linewidth=1.5)
    ax.text(0.5, 0.50,
            "Informe: Impacto Operacional Ventanas Teniente 8\n"
            "Período: Enero 2026 – Junio 2026  |  72 eventos  |  Event Study + Fase 2 Causal",
            color=C_MGRAY, fontsize=10, ha="center", linespacing=1.8)
    ax.text(0.5, 0.36, "Contacto analítica: CIO DET — División El Teniente",
            color=C_MGRAY, fontsize=9, ha="center")
    ax.text(0.5, 0.14,
            f"CODELCO División El Teniente  |  {DATE_STR}  |  {VER}  |  CONFIDENCIAL",
            color=C_MGRAY, fontsize=8, ha="center", alpha=0.7)

    # Resumen acciones clave al pie
    ax.add_patch(FancyBboxPatch((0.10, 0.18), 0.80, 0.12,
                                boxstyle="round,pad=0.01",
                                facecolor=C_COPPER, edgecolor="none", alpha=0.15))
    ax.text(0.5, 0.27, "ACCION INMEDIATA: Regla 72h entre ventanas + Protocolo Pila Llena",
            color=C_GOLD, fontsize=9, fontweight="bold", ha="center", va="center")
    ax.text(0.5, 0.21, "ROI estimado: hasta USD 29M/año en toneladas recuperadas",
            color=C_GOLD, fontsize=8, ha="center", va="center", alpha=0.85)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# Build PDF
# ═══════════════════════════════════════════════════════════════════════════════

def build_pdf() -> Path:
    data = _load_data()
    out  = RPT / "Informe_Comite_v2_T8.pdf"

    pages = [
        page_portada(),
        page_resumen_ejecutivo(),
        page_contexto(),
        page_hallazgo_gaviota(),
        page_mecanismo_causal(),          # NUEVA — ISR + Retardo
        page_hallazgo_duracion(),
        page_elasticidad(),               # NUEVA — Elasticidad Fase 2
        page_hallazgo_activos(),
        page_clasificacion_eventos(),     # NUEVA — A/B/C/D
        page_consecutivas(),              # NUEVA — Ventanas consecutivas
        page_hallazgo_recuperacion(),
        page_hallazgo_estadistica(data),
        page_impacto(),
        page_semaforo(),                  # NUEVA — Semaforo de riesgo
        page_roadmap(),                   # NUEVA — Roadmap con fechas
        page_riesgos(),
        page_recomendaciones(),
        page_conclusiones(),
        page_cierre(),
    ]

    with PdfPages(str(out)) as pdf:
        d = pdf.infodict()
        d["Title"]    = "Impacto Operacional Ventanas Teniente 8 — v2"
        d["Author"]   = "CIO DET — Analitica de Rendimientos"
        d["Subject"]  = "Informe Comite T8 v2 — Event Study + Fase 2 Causal"
        d["Keywords"] = "Teniente 8, rendimiento, molienda, SAG, mecanismo causal, ISR"
        d["CreationDate"] = datetime.now()
        for fig in pages:
            pdf.savefig(fig, dpi=DPI, bbox_inches="tight")
            plt.close(fig)

    print(f"  PDF v2: {out.name}  ({out.stat().st_size // 1024} KB)  —  {len(pages)} paginas")
    return out


if __name__ == "__main__":
    import json
    LOGS.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print(f"  Generando Informe_Comite_v2_T8.pdf  [{VER}]")
    print("=" * 60)
    out = build_pdf()
    with open(LOGS / "skill_audit.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "fecha": datetime.now().isoformat(),
            "script": "src/generar_informe_v2_pdf.py",
            "output": str(out),
            "version": VER,
        }, ensure_ascii=False) + "\n")
    print(f"\n  Listo: {out}")
