"""
graphs.py — Figuras Plotly para el dashboard de simulacion SAG T8
"""

from __future__ import annotations
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from components.cards import RESTRICTION_REASON_LABEL_JDS

# ── Paleta TDA (Plataforma TDA_Diseño_Visual_Elegido.html, 2026-07-07) ────────
# Tema oscuro extraido del wireframe SVG del template (unica parte
# legible del archivo — el resto es un bundle JS compilado, ver
# 04_Reports/Technical/20260707_Template_TDA_Mapping.md). AZUL/AZUL_MED/
# VERDE/NARANJA/ROJO/AMARILLO mantienen su ROL semantico (texto principal
# / acento / bueno / neutro-alerta / malo / atencion) pero con valores
# claros-sobre-oscuro en vez de oscuros-sobre-claro.
AZUL     = "#F0F4FA"   # texto principal (antes: navy oscuro sobre fondo claro)
AZUL_MED = "#4FB0E5"   # acento / azul TDA
VERDE    = "#4FCE82"
NARANJA  = "#E8935A"
ROJO     = "#E94A4A"
AMARILLO = "#E5BB3E"
BG       = "#07162F"   # fondo de pagina TDA
PLOT_BG  = "#0F2647"   # fondo de area de grafico TDA (panel)
GRID     = "#1a3a6c"   # gridlines/bordes TDA
TEXTO_MUTED = "#8896AF"  # labels secundarios TDA

PILE_COLORS = {"SAG1": AZUL_MED, "SAG2": NARANJA}
TPH_COLORS  = {"SAG1": AZUL_MED, "SAG2": NARANJA, "Total": VERDE}

# Plantilla Plotly oscura por defecto (tema TDA): cubre texto que NO
# recibe un color explicito en cada figura (ticks de ejes, subplot_titles,
# texto de leyenda sin "font" propio, etc.) — evita perseguir cada
# ocurrencia individual de texto negro-por-defecto de Plotly, que
# quedaria invisible sobre el nuevo fondo oscuro.
import plotly.graph_objects as _go
import plotly.io as _pio

def _build_template(bg, plot_bg, grid, azul, texto_muted):
    t = _go.layout.Template()
    t.layout.paper_bgcolor = bg
    t.layout.plot_bgcolor = plot_bg
    t.layout.font = dict(color=azul, family="'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif")
    t.layout.xaxis = dict(gridcolor=grid, linecolor=grid, zerolinecolor=grid, tickfont=dict(color=texto_muted))
    t.layout.yaxis = dict(gridcolor=grid, linecolor=grid, zerolinecolor=grid, tickfont=dict(color=texto_muted))
    t.layout.legend = dict(font=dict(color=azul))
    return t

_pio.templates["tda_dark"] = _build_template(BG, PLOT_BG, GRID, AZUL, TEXTO_MUTED)
# Modo claro ejecutivo (Fase 4, 2026-07-07): paleta corporativa original
# pre-TDA. Ver utils/theme_state.py::apply_plotly_theme, que mantiene
# ambas plantillas sincronizadas con la paleta activa.
_pio.templates["tda_light"] = _build_template("#F5F7FA", "#FFFFFF", "#eeeeee", "#1F3864", "#7F8C8D")
_pio.templates.default = "tda_dark"


# ─────────────────────────────────────────────────────────────────────────────
# Pagina 1: Graficos de simulacion
# ─────────────────────────────────────────────────────────────────────────────

def build_empty_simulation_figure(mensaje: str = "Ejecute una simulación para visualizar resultados") -> go.Figure:
    """Figura inicial deliberada para graph-main (y cualquier otro grafico
    de resultados) ANTES de que exista una simulacion real — nunca dejar
    el dcc.Graph sin 'figure' explicito: el default implicito de Dash es
    un go.Figure() vacio, que Plotly autorranguea a un rango arbitrario
    (ej. x:[-1,6] y:[-1,4]) y se ve identico a un grafico roto. Esta
    figura es visualmente distinguible (anotacion explicita) de un
    resultado real o de un fallo."""
    fig = go.Figure()
    fig.update_layout(
        xaxis=dict(title="Tiempo (h)", range=[0, 24], gridcolor=GRID),
        yaxis=dict(title="Pila (%)", range=[0, 100], gridcolor=GRID),
        annotations=[{
            "text": mensaje,
            "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5,
            "showarrow": False,
            "font": {"size": 13, "color": TEXTO_MUTED},
        }],
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=310,
        margin=dict(l=45, r=20, t=20, b=40),
    )
    return fig

def make_pile_chart(sim: dict, horizonte_h: float, duracion_t8_h: float) -> go.Figure:
    """Trayectoria de pila SAG1 y SAG2 con zonas de color y etiquetas mejoradas."""
    time  = np.array(sim["time"])
    p1    = np.array(sim["pile_sag1"])
    p2    = np.array(sim["pile_sag2"])
    fig   = go.Figure()

    # ── Zonas de fondo ────────────────────────────────────────────────────────
    fig.add_hrect(y0=0,   y1=15,  fillcolor="rgba(192,57,43,0.13)",  line_width=0)
    fig.add_hrect(y0=15,  y1=18,  fillcolor="rgba(230,126,34,0.11)", line_width=0)
    fig.add_hrect(y0=18,  y1=40,  fillcolor="rgba(243,156,18,0.08)", line_width=0)
    fig.add_hrect(y0=40,  y1=98,  fillcolor="rgba(39,174,96,0.06)",  line_width=0)
    # Zona de overflow (2026-07-06: antes "Zona segura" llegaba hasta 105%
    # sin distinguir estar comodo de estar pegado al techo — un SAG que se
    # satura en 100% quedaba invisible dentro de la zona "segura").
    fig.add_hrect(y0=98,  y1=105, fillcolor="rgba(142,68,173,0.14)", line_width=0)
    fig.add_shape(type="line", xref="paper", yref="y",
                  x0=0, x1=1, y0=98, y1=98,
                  line=dict(dash="dot", color="#8E44AD", width=1.2))

    # Etiquetas de zona dentro del area — xref="paper" posicion fija horizontal
    x_lbl = 0.76   # fraccion del ancho del grafico (centro-derecha)
    for y_mid, txt, color in [
        (7.5,  "Zona critica",  "rgba(192,57,43,0.55)"),
        (29,   "Zona alerta",   "rgba(200,100,20,0.55)"),
        (69,   "Zona segura",   "rgba(39,174,96,0.50)"),
        (101.5, "Overflow",     "rgba(142,68,173,0.65)"),
    ]:
        fig.add_annotation(
            x=x_lbl, xref="paper", y=y_mid, yref="y",
            text=txt, showarrow=False,
            font=dict(size=9, color=color),
            xanchor="center", yanchor="middle",
        )

    # ── Ventana T8 ────────────────────────────────────────────────────────────
    if duracion_t8_h > 0:
        t8_end = min(duracion_t8_h, horizonte_h)
        fig.add_vrect(x0=0, x1=t8_end,
                      fillcolor="rgba(31,56,100,0.07)", line_width=1,
                      line_dash="dash", line_color=AZUL)
        fig.add_annotation(
            x=t8_end / 2, y=0.99, xref="x", yref="paper",
            text="T8 activo", showarrow=False,
            font=dict(size=8, color=AZUL),
            xanchor="center", yanchor="top",
            bgcolor="rgba(15,38,71,0.75)",
        )

    # ── Lineas de pila ────────────────────────────────────────────────────────
    # Segunda iteracion UX/UI (2026-07-14, Fase 5 sec.14): hovertemplate
    # enriquecido con balance neto y autonomia por punto (customdata),
    # mas estado/restriccion/ventana (constantes en la corrida, se
    # repiten en cada punto via numpy.full) — todo ya calculado en sim,
    # sin agregar ningun campo fisico nuevo.
    def _customdata_circuito(qin_key, qout_key, auton_key, estado_key, reason_key):
        n = len(time)
        _qin_raw = sim.get(qin_key)
        _qout_raw = sim.get(qout_key)
        _auton_raw = sim.get(auton_key)
        qin = np.array(_qin_raw) if _qin_raw is not None else np.zeros(n)
        qout = np.array(_qout_raw) if _qout_raw is not None else np.zeros(n)
        balance = qin - qout
        auton = np.array(_auton_raw) if _auton_raw is not None else np.zeros(n)
        estado_txt = np.full(n, str(sim.get(estado_key, "—")))
        restriccion_txt = np.full(n, RESTRICTION_REASON_LABEL_JDS.get(sim.get(reason_key), sim.get(reason_key) or "—"))
        ventana_txt = np.full(n, "activa" if duracion_t8_h > 0 else "inactiva")
        return np.column_stack([balance, auton, estado_txt, restriccion_txt, ventana_txt])

    _hover_sufijo = (
        "<br>Balance neto: %{customdata[0]:.0f} TPH"
        "<br>Autonomía: %{customdata[1]:.1f} h"
        "<br>Estado: %{customdata[2]}"
        "<br>Restricción: %{customdata[3]}"
        "<br>Ventana T8: %{customdata[4]}<extra></extra>"
    )

    fig.add_trace(go.Scatter(
        x=time, y=p1, name="SAG1 (Molino 401)",
        line=dict(color=AZUL_MED, width=2.5),
        customdata=_customdata_circuito("cv315", "tph_sag1", "autonomia_sag1",
                                         "operational_state_sag1", "restriction_reason_sag1"),
        hovertemplate="t=%{x:.1f}h | SAG1=%{y:.1f}%" + _hover_sufijo,
    ))
    fig.add_trace(go.Scatter(
        x=time, y=p2, name="SAG2 (Molino 501)",
        line=dict(color=NARANJA, width=2.5),
        customdata=_customdata_circuito("cv316", "tph_sag2", "autonomia_sag2",
                                         "operational_state_sag2", "restriction_reason_sag2"),
        hovertemplate="t=%{x:.1f}h | SAG2=%{y:.1f}%" + _hover_sufijo,
    ))

    # ── Etiquetas de valor inicial (t=0) ──────────────────────────────────────
    for val, color in [(float(p1[0]), AZUL_MED), (float(p2[0]), NARANJA)]:
        fig.add_annotation(
            x=0, xref="x", y=val, yref="y",
            text=f"<b>{val:.0f}%</b>",
            showarrow=False, font=dict(size=9, color=color),
            xanchor="right", yanchor="middle",
            xshift=-6,
            bgcolor="rgba(15,38,71,0.80)",
        )

    # ── Etiquetas de valor final ───────────────────────────────────────────────
    for val, label, color in [
        (float(p1[-1]), "SAG1", AZUL_MED),
        (float(p2[-1]), "SAG2", NARANJA),
    ]:
        fig.add_annotation(
            x=1.0, xref="paper", y=val, yref="y",
            text=f"{label} {val:.0f}%",
            showarrow=False, font=dict(size=8, color=color),
            xanchor="left", yanchor="middle",
            xshift=4,
        )

    # ── Umbrales criticos — lineas + etiquetas separadas ─────────────────────
    fig.add_shape(type="line", xref="paper", yref="y",
                  x0=0, x1=1, y0=15, y1=15,
                  line=dict(dash="dot", color=ROJO, width=1.2))
    fig.add_shape(type="line", xref="paper", yref="y",
                  x0=0, x1=1, y0=18, y1=18,
                  line=dict(dash="dot", color=NARANJA, width=1.2))
    # Etiquetas de umbral ancladas al borde DERECHO (2026-07-06: antes en
    # x=0.02/margen izquierdo, donde la trayectoria SAG1 suele cruzar estos
    # umbrales en las primeras horas — se superponian con la curva real).
    fig.add_annotation(
        x=0.99, xref="paper", y=15, yref="y",
        text="Crítico SAG1 — 15%",
        showarrow=False, font=dict(size=8, color=ROJO),
        xanchor="right", yanchor="top", yshift=-2,
        bgcolor="rgba(15,38,71,0.75)",
    )
    fig.add_annotation(
        x=0.99, xref="paper", y=18, yref="y",
        text="Riesgo SAG2 — 18%",
        showarrow=False, font=dict(size=8, color=NARANJA),
        xanchor="right", yanchor="bottom", yshift=2,
        bgcolor="rgba(15,38,71,0.75)",
    )

    # ── Marcadores de vaciado / overflow ──────────────────────────────────────
    # Reutiliza t_critico_sag{1,2}_h ya calculado por simulate_scenario (no
    # se agrega ningun calculo nuevo). Overflow (pila >= 98%) se detecta
    # sobre la trayectoria ya simulada, solo para anotar — no cambia datos.
    def _mark_event(t_h, valor, texto, color, circuito=None):
        if t_h is None or t_h > horizonte_h:
            return
        fig.add_trace(go.Scatter(
            x=[t_h], y=[valor], mode="markers",
            marker=dict(size=9, color=color, symbol="circle",
                       line=dict(color="white", width=1)),
            name=f"{circuito} evento" if circuito else "",
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_annotation(
            x=t_h, y=valor, xref="x", yref="y",
            text=texto, showarrow=True, arrowhead=0, arrowcolor=color,
            ax=0, ay=-28 if valor < 50 else 28,
            font=dict(size=8, color=color),
            bgcolor="rgba(15,38,71,0.88)", bordercolor=color, borderwidth=1,
        )

    t_crit1 = sim.get("t_critico_sag1_h")
    t_crit2 = sim.get("t_critico_sag2_h")
    _mark_event(t_crit1, 15.0, f"SAG1 crítico ({t_crit1:.1f}h)" if t_crit1 is not None else "", ROJO, circuito="SAG1")
    _mark_event(t_crit2, 18.0, f"SAG2 crítico ({t_crit2:.1f}h)" if t_crit2 is not None else "", NARANJA, circuito="SAG2")

    for arr, nombre, color in [(p1, "SAG1", AZUL_MED), (p2, "SAG2", NARANJA)]:
        overflow_idx = np.argmax(arr >= 98.0) if (arr >= 98.0).any() else None
        if overflow_idx is not None:
            t_over = float(time[overflow_idx])
            _mark_event(t_over, 98.0, f"{nombre} overflow ({t_over:.1f}h)", "#8E44AD", circuito=nombre)

    fig.update_layout(
        title=dict(text="Evolución Esperada de las Pilas (%)", font=dict(color=AZUL, size=13), y=0.97),
        xaxis_title="Tiempo (h)", yaxis_title="Pila (%)",
        yaxis=dict(range=[0, 105], gridcolor=GRID),
        xaxis=dict(range=[0, horizonte_h], gridcolor=GRID),
        legend=dict(orientation="h", x=0.0, y=1.0, yanchor="bottom",
                    bgcolor="rgba(15,38,71,0.7)", font=dict(size=10)),
        margin=dict(l=45, r=90, t=65, b=40),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=310,
        uirevision="pile-chart",  # conserva zoom/pan del usuario entre redraws reactivos
    )
    return fig


def make_master_pile_chart(sim: dict, horizonte_h: float, duracion_t8_h: float,
                            maint_windows: dict | None = None,
                            recovery: dict | None = None) -> go.Figure:
    """Grafico principal unico del rediseno JdS (seccion 7): extiende
    make_pile_chart (que YA trae T8 inicio/fin, niveles criticos SAG1/SAG2,
    hora de vaciado y hora de overflow) agregando lo que faltaba: inicio/fin
    de mantencion (mismo patron que make_t1_t3_balance_chart), nivel minimo
    proyectado, e inicio de recuperacion (desde
    engine.balance_diagnostics.compute_recovery_time)."""
    fig = make_pile_chart(sim, horizonte_h, duracion_t8_h)
    time = np.array(sim["time"])

    # ── Mantenciones (mismo patron que make_t1_t3_balance_chart) ─────────────
    if maint_windows:
        for equipo, ventana in maint_windows.items():
            if not ventana:
                continue
            ini, fin = ventana
            if ini is None or fin is None or ini == fin:
                continue
            ini_h = max(0.0, float(ini))
            fin_h = min(horizonte_h, float(fin) if fin > ini else horizonte_h)
            if ini_h >= horizonte_h:
                continue
            fig.add_vline(x=ini_h, line_dash="dashdot", line_color=VERDE, line_width=1.3)
            fig.add_annotation(x=ini_h, y=-0.10, yref="paper",
                               text=f"Mant. {equipo} inicio", showarrow=False,
                               font=dict(size=8, color=VERDE), xanchor="left")
            if fin_h < horizonte_h:
                fig.add_vline(x=fin_h, line_dash="dashdot", line_color=VERDE, line_width=1.3)
                fig.add_annotation(x=fin_h, y=-0.10, yref="paper",
                                   text=f"Mant. {equipo} fin", showarrow=False,
                                   font=dict(size=8, color=VERDE), xanchor="left")

    # ── Nivel minimo proyectado (Fase 2: usa window_episode_sagX cuando
    # existe — t_minimo exacto de la ventana y si llego a STARVED — en vez
    # del argmin crudo, que puede caer fuera de la ventana relevante) ────────
    for key, ep_key, nombre, color in [
        ("pile_sag1", "window_episode_sag1", "SAG1", AZUL_MED),
        ("pile_sag2", "window_episode_sag2", "SAG2", NARANJA),
    ]:
        arr = np.array(sim.get(key) or [])
        if len(arr) == 0:
            continue
        ep = sim.get(ep_key)
        if ep is not None:
            t_min, y_min, starved = ep.time_of_minimum_h, ep.inventory_minimum_pct, ep.reached_starved
        else:
            idx_min = int(np.argmin(arr))
            t_min, y_min, starved = float(time[idx_min]), float(arr[idx_min]), False
        etiqueta_min = f"{nombre} mínimo: {y_min:.0f}% en t={t_min:.1f}h" + (" (STARVED)" if starved else "")
        fig.add_trace(go.Scatter(
            x=[t_min], y=[y_min], mode="markers",
            marker=dict(size=10 if starved else 8, color=("#E5484D" if starved else color),
                        symbol="triangle-down", line=dict(color="white", width=1)),
            name=f"{nombre} evento",
            showlegend=False,
            hovertemplate=etiqueta_min + "<extra></extra>",
        ))
        if starved:
            fig.add_annotation(x=t_min, y=y_min, text=f"{nombre} STARVED", showarrow=True,
                                arrowcolor="#E5484D", font=dict(size=8, color="#E5484D"), ay=-22)

        # ── Recuperacion completa (tiempo real hasta volver al nivel
        # pre-ventana, no solo "inicio de recuperacion") ──────────────────
        if ep is not None and ep.recovery_time_hours is not None:
            t_rec = ep.recovery_time_hours
            if t_rec <= horizonte_h:
                fig.add_vline(x=t_rec, line_dash="dot", line_color=color, line_width=1.1)
                fig.add_annotation(x=t_rec, y=1.0, yref="paper",
                                    text=f"{nombre} recuperación completa", showarrow=False,
                                    font=dict(size=8, color=color), xanchor="left", yanchor="bottom")

    # ── Inicio de recuperacion ─────────────────────────────────────────────────
    if recovery:
        for asset, color in [("SAG1", AZUL_MED), ("SAG2", NARANJA)]:
            r = recovery.get(asset)
            if r is None or r.estado != "recupera":
                continue
            t0 = duracion_t8_h if duracion_t8_h > 0 else 0.0
            if t0 > horizonte_h:
                continue
            fig.add_vline(x=t0, line_dash="dash", line_color=VERDE, line_width=1.2)
            fig.add_annotation(x=t0, y=1.06, yref="paper",
                               text=f"Inicio recuperación {asset}", showarrow=False,
                               font=dict(size=8, color=VERDE), xanchor="left")

    # ── Segunda iteración UX/UI (2026-07-14): marcas de SAG OFF, molino
    # de bolas OFF y alimentación rechazada — completa las marcas de
    # evento pedidas, reusando campos ya presentes en sim (sin calculo
    # nuevo): operational_state_sagX, dependency_message_sagX,
    # rejected_feed_sagX.
    for key, ep_arr_key, nombre, color, y_pos in [
        ("operational_state_sag1", "pile_sag1", "SAG1", AZUL_MED, 0.0),
        ("operational_state_sag2", "pile_sag2", "SAG2", NARANJA, 0.0),
    ]:
        estado_val = sim.get(key)
        if estado_val == "OFF" and len(sim.get(ep_arr_key) or []) > 0:
            fig.add_annotation(
                x=0, xref="x", y=1.12, yref="paper",
                text=f"{nombre} OFF", showarrow=False,
                font=dict(size=8, color=color), xanchor="left",
                bgcolor="rgba(15,38,71,0.85)", bordercolor=color, borderwidth=1,
            )

    for dep_key, nombre in [("dependency_message_sag1", "SAG1"), ("dependency_message_sag2", "SAG2")]:
        if sim.get(dep_key):
            fig.add_annotation(
                x=0, xref="x", y=1.19, yref="paper",
                text=f"{nombre}: molino de bolas inactivo", showarrow=False,
                font=dict(size=8, color=AMARILLO), xanchor="left",
                bgcolor="rgba(15,38,71,0.85)", bordercolor=AMARILLO, borderwidth=1,
            )

    for rej_key, nombre, color in [("rejected_feed_sag1", "SAG1", AZUL_MED), ("rejected_feed_sag2", "SAG2", NARANJA)]:
        _rej_raw = sim.get(rej_key)
        rej_arr = np.array(_rej_raw) if _rej_raw is not None else np.array([])
        if len(rej_arr) > 0 and rej_arr.max() > 0:
            idx_rej = int(np.argmax(rej_arr))
            t_rej = float(time[idx_rej])
            if t_rej <= horizonte_h:
                fig.add_annotation(
                    x=t_rej, y=1.0, yref="paper", xref="x",
                    text=f"{nombre} alimentación rechazada", showarrow=False,
                    font=dict(size=8, color=color), xanchor="left", yanchor="top",
                    bgcolor="rgba(15,38,71,0.7)",
                )

    return fig


def apply_circuit_filter(fig: go.Figure, circuito: str) -> go.Figure:
    """Selector de circuito (Ambos/SAG1/SAG2) — Fase 4 del pedido
    2026-07-14: filtra SOLO visibilidad de trazas ya calculadas
    (`legendonly`, recuperable con un clic en la leyenda), nunca vuelve a
    llamar a simulate_scenario_cached. Oculta unicamente las trazas
    identificadas del circuito contrario (por `name`); cualquier traza
    sin ese nombre (zonas de fondo, umbrales) queda intacta."""
    if circuito not in ("sag1", "sag2"):
        return fig
    objetivo = "SAG1" if circuito == "sag1" else "SAG2"
    contrario = "SAG2" if circuito == "sag1" else "SAG1"
    for trace in fig.data:
        name = trace.name or ""
        if contrario in name and objetivo not in name:
            trace.visible = "legendonly"
    return fig


def make_qin_qout_chart(sim: dict, horizonte_h: float) -> go.Figure:
    """Grafico secundario oculto por defecto (seccion 8, boton 'VER POR QUE
    CRECE O DRENA'): Qin vs Qout por asset en TPH, mismos arrays que ya usa
    engine.balance_diagnostics (sim['cv315']/['cv316'] = Qin, sim['tph_sag1']/
    ['tph_sag2'] = Qout) — no se calcula nada nuevo."""
    time = np.array(sim["time"])
    qin1 = np.array(sim.get("cv315", [0] * len(time)))
    qin2 = np.array(sim.get("cv316", [0] * len(time)))
    qout1 = np.array(sim.get("tph_sag1", [0] * len(time)))
    qout2 = np.array(sim.get("tph_sag2", [0] * len(time)))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=time, y=qin1, name="Qin SAG1 (CV315)",
                              line=dict(color=AZUL_MED, width=2),
                              hovertemplate="t=%{x:.1f}h | Qin SAG1=%{y:.0f} TPH<extra></extra>"))
    fig.add_trace(go.Scatter(x=time, y=qout1, name="Qout SAG1",
                              line=dict(color=AZUL_MED, width=2, dash="dot"),
                              hovertemplate="t=%{x:.1f}h | Qout SAG1=%{y:.0f} TPH<extra></extra>"))
    fig.add_trace(go.Scatter(x=time, y=qin2, name="Qin SAG2 (CV316)",
                              line=dict(color=NARANJA, width=2),
                              hovertemplate="t=%{x:.1f}h | Qin SAG2=%{y:.0f} TPH<extra></extra>"))
    fig.add_trace(go.Scatter(x=time, y=qout2, name="Qout SAG2",
                              line=dict(color=NARANJA, width=2, dash="dot"),
                              hovertemplate="t=%{x:.1f}h | Qout SAG2=%{y:.0f} TPH<extra></extra>"))

    fig.update_layout(
        title=dict(text="¿Por qué crece o drena? — Qin vs Qout", font=dict(color=AZUL, size=13), y=0.97),
        xaxis_title="Tiempo (h)", yaxis_title="TPH",
        xaxis=dict(range=[0, horizonte_h], gridcolor=GRID),
        yaxis=dict(gridcolor=GRID),
        legend=dict(orientation="h", x=0.0, y=1.0, yanchor="bottom",
                    bgcolor="rgba(15,38,71,0.7)", font=dict(size=10)),
        margin=dict(l=45, r=20, t=65, b=40),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=280,
        uirevision="qin-qout-chart",
    )
    return fig


def make_tph_chart(sim: dict, horizonte_h: float, duracion_t8_h: float,
                   sim_baseline: dict = None) -> go.Figure:
    """
    Trayectoria de TPH con:
    A) Marcadores de eventos (pile feedback reduciendo rate automaticamente)
    B) Banda de operacion recomendada (envelope del regimen operacional)
    C) Area de tonelaje perdido por T8 vs escenario sin T8 (si sim_baseline != None)
    """
    from engine.rules_engine import determine_regime
    from engine.ode_model import P90

    t_arr  = np.array(sim["time"])
    tph1   = np.array(sim["tph_sag1"])
    tph2   = np.array(sim["tph_sag2"])
    total  = tph1 + tph2
    pile1  = np.array(sim["pile_sag1"])
    pile2  = np.array(sim["pile_sag2"])
    auton1_arr = np.array(sim.get("autonomia_sag1", np.zeros_like(t_arr)))
    auton2_arr = np.array(sim.get("autonomia_sag2", np.zeros_like(t_arr)))

    THR1 = 1000.0
    THR2 = 1600.0
    t_crit1  = sim.get("t_critico_sag1_h")
    t_crit2  = sim.get("t_critico_sag2_h")
    auton1_0 = float(auton1_arr[0])
    auton2_0 = float(auton2_arr[0])

    # ── B: Banda operacional (envelope) ─────────────────────────────────────
    env1_lo, env1_hi = [], []
    env2_lo, env2_hi = [], []
    for i, t_h in enumerate(t_arr):
        t8_act = (duracion_t8_h > 0) and (t_h < duracion_t8_h)
        _, (lo1, hi1) = determine_regime(float(pile1[i]), float(auton1_arr[i]), t8_act, "SAG1")
        _, (lo2, hi2) = determine_regime(float(pile2[i]), float(auton2_arr[i]), t8_act, "SAG2")
        env1_lo.append(P90["SAG1"] * lo1 / 100.0)
        env1_hi.append(P90["SAG1"] * hi1 / 100.0)
        env2_lo.append(P90["SAG2"] * lo2 / 100.0)
        env2_hi.append(P90["SAG2"] * hi2 / 100.0)

    fig = go.Figure()

    # ── Zonas horizontales de rendimiento ───────────────────────────────────
    fig.add_hrect(y0=0,    y1=THR1, fillcolor="rgba(192,57,43,0.06)", line_width=0)
    fig.add_hrect(y0=THR1, y1=THR1+200, fillcolor="rgba(243,156,18,0.05)", line_width=0)
    fig.add_hrect(y0=THR2, y1=THR2+200, fillcolor="rgba(243,156,18,0.05)", line_width=0)

    # ── Ventana T8 ───────────────────────────────────────────────────────────
    if duracion_t8_h > 0:
        t8_end = min(duracion_t8_h, horizonte_h)
        fig.add_vrect(x0=0, x1=t8_end,
                      fillcolor="rgba(31,56,100,0.06)", line_width=1,
                      line_dash="dash", line_color=AZUL,
                      annotation_text="T8", annotation_position="top left",
                      annotation_font_size=9)
        if t8_end < horizonte_h:
            fig.add_vline(x=t8_end, line_dash="dot", line_color=AZUL,
                          annotation_text=f"Fin T8 ({t8_end:.0f}h)",
                          annotation_position="top right", annotation_font_size=8)

    # ── C: Area tonelaje perdido vs baseline sin T8 ──────────────────────────
    tons_lost = 0.0
    if sim_baseline is not None:
        t_base   = np.array(sim_baseline["time"])
        tot_base = np.array(sim_baseline["tph_total"])
        # Interpolar baseline al mismo vector de tiempo
        tot_base_i = np.interp(t_arr, t_base, tot_base)
        loss = np.clip(tot_base_i - total, 0, None)
        tons_lost = float(np.trapezoid(loss, t_arr))

        # Baseline como linea fantasma
        fig.add_trace(go.Scatter(
            x=t_arr, y=tot_base_i,
            name="Sin T8 (referencia)",
            line=dict(color=VERDE, width=1.2, dash="dot"),
            opacity=0.45,
            hovertemplate="t=%{x:.1f}h | Sin T8=%{y:.0f} TPH<extra></extra>",
        ))
        # Area de perdida (relleno entre baseline y actual)
        fig.add_trace(go.Scatter(
            x=t_arr, y=tot_base_i,
            fill=None, mode="lines",
            line=dict(width=0), showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=t_arr, y=total,
            fill="tonexty",
            fillcolor="rgba(192,57,43,0.15)",
            mode="lines", line=dict(width=0),
            name=f"Perdida T8 (~{tons_lost:.0f} ton)",
            hovertemplate="t=%{x:.1f}h | Perdida=%{y:.0f} TPH<extra></extra>",
        ))

    # ── B: Envelopes SAG1 (azul claro) y SAG2 (naranja claro) ───────────────
    # SAG1 upper bound (invisible, solo para fill)
    fig.add_trace(go.Scatter(
        x=t_arr, y=env1_hi, mode="lines",
        line=dict(width=0), showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=t_arr, y=env1_lo,
        fill="tonexty", fillcolor="rgba(26,94,153,0.10)",
        mode="lines", line=dict(width=0),
        name="Rango SAG1",
        hovertemplate="t=%{x:.1f}h | Rango SAG1=%{y:.0f}–" + str(int(max(env1_hi))) + " TPH<extra></extra>",
    ))
    # SAG2
    fig.add_trace(go.Scatter(
        x=t_arr, y=env2_hi, mode="lines",
        line=dict(width=0), showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=t_arr, y=env2_lo,
        fill="tonexty", fillcolor="rgba(230,126,34,0.08)",
        mode="lines", line=dict(width=0),
        name="Rango SAG2",
        hovertemplate="t=%{x:.1f}h | Rango SAG2=%{y:.0f}–" + str(int(max(env2_hi))) + " TPH<extra></extra>",
    ))

    # ── Lineas de datos principales ─────────────────────────────────────────
    def _split_trace(t, y, t_cut):
        if t_cut is None or t_cut >= horizonte_h:
            return (t.tolist(), y.tolist()), ([], [])
        mask_b = t <= t_cut
        mask_a = t >= t_cut
        return (t[mask_b].tolist(), y[mask_b].tolist()), \
               (t[mask_a].tolist(), y[mask_a].tolist())

    (x1a, y1a), (x1b, y1b) = _split_trace(t_arr, tph1, t_crit1)
    fig.add_trace(go.Scatter(x=x1a, y=y1a, name="SAG1 (Molino 401)",
                             line=dict(color=AZUL_MED, width=2.5),
                             hovertemplate="t=%{x:.1f}h | SAG1=%{y:.0f} TPH<extra></extra>"))
    if x1b:
        fig.add_trace(go.Scatter(x=x1b, y=y1b, name="SAG1 emergencia",
                                 line=dict(color=AZUL_MED, width=1.5, dash="dot"),
                                 opacity=0.4, showlegend=False,
                                 hovertemplate="t=%{x:.1f}h | SAG1 EMERG=%{y:.0f} TPH<extra></extra>"))

    (x2a, y2a), (x2b, y2b) = _split_trace(t_arr, tph2, t_crit2)
    fig.add_trace(go.Scatter(x=x2a, y=y2a, name="SAG2 (Molino 501)",
                             line=dict(color=NARANJA, width=2.5),
                             hovertemplate="t=%{x:.1f}h | SAG2=%{y:.0f} TPH<extra></extra>"))
    if x2b:
        fig.add_trace(go.Scatter(x=x2b, y=y2b, name="SAG2 emergencia",
                                 line=dict(color=NARANJA, width=1.5, dash="dot"),
                                 opacity=0.4, showlegend=False,
                                 hovertemplate="t=%{x:.1f}h | SAG2 EMERG=%{y:.0f} TPH<extra></extra>"))

    fig.add_trace(go.Scatter(x=t_arr, y=total, name="Total TPH",
                             line=dict(color=VERDE, width=2, dash="dash"),
                             hovertemplate="t=%{x:.1f}h | Total=%{y:.0f} TPH<extra></extra>"))

    # ── A: Marcadores de eventos pile feedback ───────────────────────────────
    # Las etiquetas usan yref="paper" para posicion fija vertical (evita solapamiento
    # cuando todos los eventos ocurren en el mismo rango x temprano)
    _ev_y_paper = [0.93, 0.79, 0.65]   # alturas en fraccion del area del grafico
    for (threshold, label_txt, asset, pile_arr, tph_arr, color_ev), yp in zip([
        (35.0, "SAG1 rate -15%%", "SAG1", pile1, tph1, AZUL_MED),
        (25.0, "SAG1 rate -30%%", "SAG1", pile1, tph1, ROJO),
        (35.0, "SAG2 rate -15%%", "SAG2", pile2, tph2, NARANJA),
    ], _ev_y_paper):
        idx = np.where((pile_arr[:-1] >= threshold) & (pile_arr[1:] < threshold))[0]
        if len(idx) == 0:
            continue
        i0 = idx[0]
        t_ev = float(t_arr[i0])
        tph_ev = float(tph_arr[i0])
        fig.add_trace(go.Scatter(
            x=[t_ev], y=[tph_ev],
            mode="markers",
            marker=dict(symbol="triangle-down", size=11, color=color_ev,
                        line=dict(width=1.5, color="white")),
            name=label_txt,
            showlegend=True,
            hovertemplate=f"t={t_ev:.1f}h | pile={threshold:.0f}% | {label_txt}<extra></extra>",
        ))
        # Etiqueta con posicion vertical fija en el grafico (no sigue al dato)
        fig.add_annotation(
            x=t_ev, xref="x",
            y=yp,   yref="paper",
            text=f"<b>pile={threshold:.0f}%</b>  {label_txt}",
            showarrow=True, arrowhead=2, arrowcolor=color_ev,
            ax=30, ay=0, axref="pixel", ayref="pixel",
            font=dict(size=8, color=color_ev),
            xanchor="left", yanchor="middle",
            bgcolor="rgba(15,38,71,0.90)", bordercolor=color_ev, borderwidth=1,
        )

    # ── Tiempo critico de pila ───────────────────────────────────────────────
    # Usar add_shape + add_annotation con yref="paper" para control total de posicion
    if t_crit1 is not None and t_crit1 < horizonte_h:
        fig.add_vrect(x0=t_crit1, x1=horizonte_h,
                      fillcolor="rgba(192,57,43,0.09)", line_width=0)
        fig.add_shape(type="line", xref="x", yref="paper",
                      x0=t_crit1, x1=t_crit1, y0=0, y1=1,
                      line=dict(dash="dash", color=ROJO, width=1.5))
        fig.add_annotation(
            x=t_crit1, xref="x", y=0.99, yref="paper",
            text=f"SAG1 crit. {t_crit1:.1f}h",
            showarrow=False, font=dict(size=8, color=ROJO),
            xanchor="right", yanchor="top",
            bgcolor="rgba(15,38,71,0.88)", bordercolor=ROJO, borderwidth=1,
        )
    if t_crit2 is not None and t_crit2 < horizonte_h:
        if t_crit1 is None or abs(t_crit2 - t_crit1) > 0.25:
            fig.add_shape(type="line", xref="x", yref="paper",
                          x0=t_crit2, x1=t_crit2, y0=0, y1=1,
                          line=dict(dash="dash", color=NARANJA, width=1.5))
            # Si SAG1 y SAG2 estan proximos, bajar la etiqueta SAG2 para no solapar
            yp2 = 0.86 if (t_crit1 is not None and abs(t_crit2 - t_crit1) < 2.0) else 0.99
            side2 = "left" if (t_crit1 is None or t_crit2 >= t_crit1) else "right"
            fig.add_annotation(
                x=t_crit2, xref="x", y=yp2, yref="paper",
                text=f"SAG2 crit. {t_crit2:.1f}h",
                showarrow=False, font=dict(size=8, color=NARANJA),
                xanchor=side2, yanchor="top",
                bgcolor="rgba(15,38,71,0.88)", bordercolor=NARANJA, borderwidth=1,
            )

    # ── Umbrales de bolas ────────────────────────────────────────────────────
    fig.add_hline(y=THR1, line_dash="dash", line_color=AZUL_MED,
                  annotation_text="SAG1 umbral 1000 TPH",
                  annotation_position="right", annotation_font_size=8)
    fig.add_hline(y=THR2, line_dash="dash", line_color=NARANJA,
                  annotation_text="SAG2 umbral 1600 TPH",
                  annotation_position="right", annotation_font_size=8)

    # ── Recuadro autonomia + perdida T8 ─────────────────────────────────────
    def _auton_str(a, label):
        if a is None: return f"{label}: —"
        if a >= horizonte_h: return f"{label}: >{horizonte_h:.0f}h OK"
        return f"{label}: {a:.1f}h [{'CRITICA' if a<1 else 'ALERTA' if a<2.5 else 'OK'}]"

    loss_line = (f"<br><b>Perdida T8: ~{tons_lost:.0f} ton</b>"
                 if tons_lost > 0 else "")
    auton_box = (f"<b>Autonomia inicial</b><br>"
                 f"{_auton_str(auton1_0, 'SAG1')}<br>"
                 f"{_auton_str(auton2_0, 'SAG2')}{loss_line}")
    y_max = float(max(tph1.max(), tph2.max()))

    # Colocar el recuadro en la zona central del grafico (evita la zona critica izq)
    x_box = horizonte_h * 0.40
    fig.add_annotation(
        x=x_box, y=y_max * 0.99,
        text=auton_box,
        showarrow=False, font=dict(size=9, color=AZUL),
        xanchor="left", yanchor="top",
        bgcolor="rgba(15,38,71,0.92)",
        bordercolor=GRID, borderwidth=1,
    )

    fig.update_layout(
        title=dict(text="Trayectoria de TPH — Molino 401 y 501",
                   font=dict(color=AZUL, size=13), y=0.98),
        xaxis_title="Tiempo (h)", yaxis_title="TPH",
        xaxis=dict(range=[0, horizonte_h]),
        legend=dict(orientation="h", x=0.0, y=1.0, yanchor="bottom",
                    bgcolor="rgba(15,38,71,0.7)", font=dict(size=9, color=AZUL),
                    tracegroupgap=0),
        margin=dict(l=45, r=120, t=80, b=40),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=380,
        uirevision="tph-chart",  # conserva zoom/pan del usuario entre redraws reactivos
    )
    return fig


def make_bola_timeline_chart(sim: dict, horizonte_h: float, duracion_t8_h: float,
                             rate_sag1_tph: float = 1400.0,
                             rate_sag2_tph: float = 2200.0) -> go.Figure:
    """
    Timeline ON/OFF de molinos de bola 411,412,511,512.
    Verde = ON y rate OK  |  Naranja = ON pero rate BASE bajo umbral (recomendar apagar)  |  Gris = OFF
    Nota: se compara el rate BASE del slider (sin bonus bola) contra el umbral.
    """
    time = sim["time"]
    n = len(time)
    # Usar rate BASE (sin bonus bola) para la comparacion de umbral
    tph1 = [rate_sag1_tph] * n
    tph2 = [rate_sag2_tph] * n
    THR1, THR2 = 1000.0, 1600.0

    COLOR_OK   = "#27AE60"   # verde — ON y rate normal
    COLOR_WARN = "#E67E22"   # naranja — ON pero rate bajo umbral
    COLOR_OFF  = "#BDBDBD"   # gris — apagado

    bolas = [
        ("411 (SAG1)", sim.get("bola411", [0]*len(time)), tph1, THR1),
        ("412 (SAG1)", sim.get("bola412", [0]*len(time)), tph1, THR1),
        ("511 (SAG2)", sim.get("bola511", [0]*len(time)), tph2, THR2),
        ("512 (SAG2)", sim.get("bola512", [0]*len(time)), tph2, THR2),
    ]
    y_pos = {"411 (SAG1)": 3, "412 (SAG1)": 2, "511 (SAG2)": 1, "512 (SAG2)": 0}

    fig = go.Figure()

    # Ventana T8
    if duracion_t8_h > 0:
        t8_end = min(duracion_t8_h, horizonte_h)
        fig.add_vrect(x0=0, x1=t8_end,
                      fillcolor="rgba(31,56,100,0.07)", line_width=1,
                      line_dash="dash", line_color=AZUL,
                      annotation_text="T8", annotation_position="top left",
                      annotation_font_size=8)

    # Trazas de estado — una por molino, coloreadas por condicion
    for name, estado_arr, rate_arr, thr in bolas:
        yp = y_pos[name]
        t_arr = np.array(time)
        e_arr = np.array(estado_arr)
        r_arr = np.array(rate_arr)

        # Segmentos continuos agrupados por color para no crear miles de traces
        for color, mask in [
            (COLOR_OFF,  e_arr == 0),
            (COLOR_OK,   (e_arr == 1) & (r_arr >= thr)),
            (COLOR_WARN, (e_arr == 1) & (r_arr < thr)),
        ]:
            if not mask.any():
                continue
            # Construir x/y con None para romper segmentos discontinuos
            xs, ys = [], []
            in_seg = False
            for k in range(len(t_arr) - 1):
                if mask[k]:
                    if not in_seg:
                        xs.append(t_arr[k])
                        ys.append(yp + 0.35)
                        in_seg = True
                    xs.append(t_arr[k + 1])
                    ys.append(yp + 0.35)
                else:
                    if in_seg:
                        xs.append(None); ys.append(None)
                    in_seg = False

            estado_txt = "ON — rate OK" if color == COLOR_OK else ("ON — reducir bola" if color == COLOR_WARN else "OFF")
            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="lines",
                line=dict(color=color, width=14),
                showlegend=False,
                hovertemplate=f"<b>{name}</b>: {estado_txt}<br>t=%{{x:.1f}}h<extra></extra>",
            ))

    # Fondo gris muy claro por fila para separar visualmente
    for yp in [0, 2]:
        fig.add_hrect(y0=yp - 0.5, y1=yp + 0.5, fillcolor="rgba(0,0,0,0.02)", line_width=0)

    fig.update_layout(
        title=dict(
            text=("Estado Molinos de Bola  |  "
                  "<span style='color:#27AE60'>■</span> ON normal  "
                  "<span style='color:#E67E22'>■</span> ON — reducir bola  "
                  "<span style='color:#BDBDBD'>■</span> OFF"),
            font=dict(color=AZUL, size=11), y=0.97,
        ),
        xaxis_title="Tiempo (h)",
        yaxis=dict(
            tickvals=[0, 1, 2, 3],
            ticktext=["512 (SAG2)", "511 (SAG2)", "412 (SAG1)", "411 (SAG1)"],
            range=[-0.6, 3.8],
            gridcolor=GRID,
        ),
        xaxis=dict(range=[0, horizonte_h]),
        margin=dict(l=95, r=20, t=55, b=38),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=215,
        showlegend=False,
    )

    # Nota inferior con regla operacional
    fig.add_annotation(
        x=horizonte_h, y=-0.55,
        text="Regla: SAG1 < 1,000 TPH → max 1 bola (411 o 412)  |  SAG2 < 1,600 TPH → max 1 bola (511 o 512)",
        showarrow=False, font=dict(size=8, color=TEXTO_MUTED),
        xanchor="right", yanchor="bottom",
    )
    return fig


def make_gantt_operacional(base_hour: float, horizonte_h: float, states: dict,
                            maint_windows: dict | None = None) -> go.Figure:
    """
    Gantt operacional "Estado Operacional por Hora": una fila por equipo,
    coloreada ON/OFF/MANTTO a lo largo del horizonte (eje X = hora del dia).

    `states`: {equipo: "on"|"off"} — estado base (constante en el horizonte;
    el optimizador de esta iteracion sigue siendo estatico).
    `maint_windows`: {equipo: (ini, fin) en horas de reloj 0-24, o None} —
    ventanas que se pintan MANTTO independientemente de `states`.
    """
    from engine.scheduler import hour_of_day_ticks, hour_in_window

    equipos = ["CH1", "CH2", "T1", "T3", "CV315", "CV316",
               "SAG1", "SAG2", "411", "412", "511", "512"]
    maint_windows = maint_windows or {}

    COLOR_ON    = "#27AE60"
    COLOR_OFF   = "#BDBDBD"
    COLOR_MANT  = "#C0392B"

    fig = go.Figure()
    legend_seen = set()
    segments_by_equipo = {}

    # Resolucion horaria para detectar cruces de la ventana de mantencion
    # dentro del horizonte (la ventana esta en hora de reloj, el horizonte
    # esta en horas relativas desde base_hour).
    n_steps = max(int(round(horizonte_h * 4)), 1)  # paso 15 min
    dt = horizonte_h / n_steps

    for row_idx, equipo in enumerate(equipos):
        base_on = states.get(equipo, "off") == "on"
        ventana = maint_windows.get(equipo)

        # Construir segmentos [t0, t1, estado] recorriendo el horizonte
        segments = []
        t = 0.0
        cur_state = None
        seg_start = 0.0
        for i in range(n_steps + 1):
            t = min(i * dt, horizonte_h)
            clock_h = (base_hour + t) % 24.0
            en_mant = bool(ventana) and hour_in_window(clock_h, ventana[0], ventana[1])
            state = "mantto" if en_mant else ("on" if base_on else "off")
            if cur_state is None:
                cur_state = state
                seg_start = t
            elif state != cur_state:
                segments.append((seg_start, t, cur_state))
                cur_state = state
                seg_start = t
        segments.append((seg_start, horizonte_h, cur_state))
        segments_by_equipo[equipo] = segments

        color_map = {"on": COLOR_ON, "off": COLOR_OFF, "mantto": COLOR_MANT}
        label_map = {"on": "ON", "off": "OFF", "mantto": "MANTTO"}
        for t0, t1, state in segments:
            if t1 <= t0:
                continue
            color = color_map[state]
            label = label_map[state]
            show_legend = label not in legend_seen
            legend_seen.add(label)
            fig.add_trace(go.Bar(
                x=[t1 - t0], y=[equipo], base=[t0],
                orientation="h",
                marker=dict(color=color, line=dict(width=0)),
                name=label,
                legendgroup=label,
                showlegend=show_legend,
                hovertemplate=f"{equipo}: {label}<br>%{{base:.1f}}h – " + f"{t1:.1f}h<extra></extra>",
            ))

    # R16 — al menos 1 molino de bolas activo por SAG: marcar en rojo los
    # tramos donde ambos molinos de un mismo SAG quedan "off" a la vez
    # (mantencion ya se distingue con su propio color, no cuenta aqui).
    def _off_intervals(equipo):
        return [(t0, t1) for t0, t1, st in segments_by_equipo.get(equipo, []) if st == "off"]

    def _overlap_intervals(a, b):
        out = []
        for a0, a1 in a:
            for b0, b1 in b:
                lo, hi = max(a0, b0), min(a1, b1)
                if hi > lo:
                    out.append((lo, hi))
        return out

    r16_windows = (
        _overlap_intervals(_off_intervals("411"), _off_intervals("412"))
        + _overlap_intervals(_off_intervals("511"), _off_intervals("512"))
    )
    for t0, t1 in r16_windows:
        fig.add_vrect(
            x0=t0, x1=t1,
            fillcolor="rgba(192,57,43,0.12)", line_width=0,
            annotation_text="🔴 R16", annotation_position="top",
            annotation_font_size=10, annotation_font_color=COLOR_MANT,
            layer="below",
        )

    tickvals, ticktext = hour_of_day_ticks(base_hour, horizonte_h, step=max(2.0, round(horizonte_h / 12)))

    fig.update_layout(
        barmode="stack",
        height=340,
        margin=dict(l=70, r=20, t=30, b=40),
        xaxis=dict(title="Hora del dia", tickvals=tickvals, ticktext=ticktext,
                   range=[0, horizonte_h]),
        yaxis=dict(title=None, categoryorder="array", categoryarray=list(reversed(equipos))),
        plot_bgcolor=PLOT_BG,
        paper_bgcolor=BG,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        bargap=0.3,
    )
    return fig


def make_chancado_cv_chart(sim: dict, horizonte_h: float, duracion_t8_h: float) -> go.Figure:
    """
    Balance alimentacion vs procesado, separado por linea SAG (pilas independientes).

    Fila 1: SAG1 — feed CV315 vs procesado TPH SAG1.
    Fila 2: SAG2 — feed CV316 vs procesado TPH SAG2.
    Eje izquierdo de cada fila: TPH feed / TPH procesado.
    Eje derecho de cada fila:   Balance = Feed - Procesado.
      Azul  (+) → pila creciendo (feed > procesado)
      Rojo  (-) → pila drenando  (procesado > feed)
    """
    time  = np.array(sim["time"])
    cv315 = np.array(sim.get("cv315",    [0] * len(time)))
    cv316 = np.array(sim.get("cv316",    [0] * len(time)))
    tph1  = np.array(sim.get("tph_sag1", [0] * len(time)))
    tph2  = np.array(sim.get("tph_sag2", [0] * len(time)))

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        specs=[[{"secondary_y": True}], [{"secondary_y": True}]],
        vertical_spacing=0.22,
        subplot_titles=("SAG1 (Molino 401) — CV315 vs Procesado",
                         "SAG2 (Molino 501) — CV316 vs Procesado"),
    )

    lineas = [
        dict(row=1, feed=cv315, proc=tph1, feed_name="Feed CV315", proc_name="Procesado SAG1"),
        dict(row=2, feed=cv316, proc=tph2, feed_name="Feed CV316", proc_name="Procesado SAG2"),
    ]

    # Rango fijo y acotado para el eje secundario "Balance". Si no se fija,
    # el autorango se ajusta exactamente al dato: cuando el balance tiene un
    # solo signo durante todo el horizonte (feed=0 en ventana T8, por ejemplo),
    # las barras terminan ocupando el 100% del alto del panel en vez de una
    # franja bajo la linea cero. Con padding fijo, la franja queda acotada
    # aunque el balance sea siempre positivo o siempre negativo.
    max_abs_balance = max(
        float(np.max(np.abs(cv315 - tph1))) if len(cv315) else 0.0,
        float(np.max(np.abs(cv316 - tph2))) if len(cv316) else 0.0,
        1.0,
    )
    balance_range = [-max_abs_balance * 2.3, max_abs_balance * 2.3]

    for ln in lineas:
        row = ln["row"]
        feed, procesado = ln["feed"], ln["proc"]
        balance = feed - procesado
        bar_colors = [AZUL_MED if b >= 0 else ROJO for b in balance]
        saldo_neto = float(np.trapezoid(balance, time))
        feed_mean  = float(feed.mean())
        proc_mean  = float(procesado.mean())

        if duracion_t8_h > 0:
            t8_end = min(duracion_t8_h, horizonte_h)
            fig.add_vrect(x0=0, x1=t8_end,
                          fillcolor="rgba(31,56,100,0.07)", line_width=1,
                          line_dash="dash", line_color=AZUL,
                          row=row, col=1)

        fig.add_trace(
            go.Bar(
                x=time, y=balance,
                name="Balance feed−SAG", legendgroup="balance",
                showlegend=(row == 1),
                marker_color=bar_colors,
                opacity=0.45,
                hovertemplate="t=%{x:.1f}h | Balance=%{y:+.0f} TPH<extra></extra>",
            ),
            row=row, col=1, secondary_y=True,
        )
        fig.add_hline(y=0, line_dash="dot", line_color=TEXTO_MUTED,
                      line_width=1, row=row, col=1, secondary_y=True)

        fig.add_trace(
            go.Scatter(
                x=time, y=feed,
                name=ln["feed_name"],
                line=dict(color="#8E44AD", width=2.5),
                hovertemplate="t=%{x:.1f}h | Feed=%{y:.0f} TPH<extra></extra>",
            ),
            row=row, col=1, secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=time, y=procesado,
                name=ln["proc_name"],
                line=dict(color=VERDE, width=2.5),
                hovertemplate="t=%{x:.1f}h | Procesado=%{y:.0f} TPH<extra></extra>",
            ),
            row=row, col=1, secondary_y=False,
        )

        # Anotacion compacta, anclada al margen IZQUIERDO (2026-07-06: antes
        # en x=0.98/borde derecho, exactamente donde vive el titulo del eje
        # secundario "Balance (TPH)" — se superponian visualmente).
        saldo_txt = f"Saldo: {saldo_neto:+.0f} TPH·h"
        color_saldo = AZUL_MED if saldo_neto >= 0 else ROJO
        fig.add_annotation(
            x=horizonte_h * 0.02, y=max(feed.max(), procesado.max()) * 0.97,
            xref=f"x{row}" if row > 1 else "x", yref=f"y{2*row-1}" if row > 1 else "y",
            text=(f"Feed {feed_mean:.0f} / Proc {proc_mean:.0f} TPH · "
                  f"<span style='color:{color_saldo}'><b>{saldo_txt}</b></span>"),
            showarrow=False,
            font=dict(size=9),
            xanchor="left", yanchor="top",
            bgcolor="rgba(15,38,71,0.85)",
            bordercolor=GRID, borderwidth=1,
        )

        fig.update_yaxes(title_text="TPH", row=row, col=1, secondary_y=False, showgrid=True)
        fig.update_yaxes(title_text="Balance (TPH)", row=row, col=1, secondary_y=True,
                         showgrid=False, zeroline=True,
                         zerolinecolor=GRID, zerolinewidth=1,
                         range=balance_range)

    # ── Layout ───────────────────────────────────────────────────────────────
    # Nota: la leyenda va abajo (y negativo) en vez de arriba-izquierda para no
    # pisar el subtitulo de la fila 1 ("SAG1 ... CV315 vs Procesado"), que Plotly
    # ancla justo en esa misma esquina cuando se usan subplot_titles de 2 filas.
    fig.update_layout(
        title=dict(
            text=("Balance Alimentacion vs Procesado por linea SAG  |  "
                  "<span style='color:#1A5E99'>■</span> Pila crece  "
                  "<span style='color:#C0392B'>■</span> Pila drena"),
            font=dict(color=AZUL, size=12), y=0.99,
        ),
        xaxis2_title="Tiempo (h)",
        xaxis=dict(range=[0, horizonte_h]),
        xaxis2=dict(range=[0, horizonte_h]),
        legend=dict(orientation="h", x=0.5, y=-0.12, xanchor="center", yanchor="top",
                    bgcolor="rgba(15,38,71,0.7)", font=dict(size=10)),
        bargap=0,
        margin=dict(l=50, r=75, t=80, b=75),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=540,
        barmode="overlay",
    )
    return fig


def make_t1_t3_balance_chart(sim: dict, horizonte_h: float, duracion_t8_h: float,
                              maint_windows: dict | None = None) -> go.Figure:
    """
    Balance de Alimentacion: T1, CV315, CV316 y T3 — todas las series en TPH
    (2026-07-06: T3 debe mostrarse siempre en TPH, nunca en %, ver
    04_Reports/Technical/*_Sync_Portable_Localhost_T3_TPH.md).

    Conservacion de masa (invariante, no se recalcula aqui — viene ya
    garantizada por engine.ode_model.compute_t1_distribution):
      T1 = CV315 + CV316 + T3

    CAMBIO 12 (UX/UI v2 JdS, 2026-07-07): altura +50% (420->640), zonas de
    fondo verde/amarillo/rojo segun el balance neto de las pilas
    (feed CV315+CV316 vs consumo tph_sag1+tph_sag2), y anotaciones de
    inicio/fin de T8 y de mantenciones activas en la ventana.
    """
    time  = np.array(sim["time"])
    t1    = np.array(sim.get("t1",    [0] * len(time)))
    cv315 = np.array(sim.get("cv315", [0] * len(time)))
    cv316 = np.array(sim.get("cv316", [0] * len(time)))
    t3    = np.array(sim.get("t3",    [0] * len(time)))
    tph1  = np.array(sim.get("tph_sag1", [0] * len(time)))
    tph2  = np.array(sim.get("tph_sag2", [0] * len(time)))

    fig = go.Figure()

    # ── Zonas de fondo: balanceado (verde) / pila creciendo (amarillo) /
    # pila drenando (rojo) — segun balance neto feed-consumo por tramo.
    balance = (cv315 + cv316) - (tph1 + tph2)
    feed_ref = max(float((cv315 + cv316).mean()), 1.0)
    umbral = 0.05 * feed_ref

    def _zona(b):
        if b > umbral:
            return "creciendo"
        if b < -umbral:
            return "drenando"
        return "balanceado"

    zona_color = {"balanceado": "rgba(39,174,96,0.08)", "creciendo": "rgba(243,156,18,0.10)",
                  "drenando": "rgba(192,57,43,0.08)"}
    if len(time) > 1:
        zonas = [_zona(b) for b in balance]
        i0 = 0
        for i in range(1, len(zonas) + 1):
            if i == len(zonas) or zonas[i] != zonas[i0]:
                fig.add_vrect(x0=time[i0], x1=time[min(i, len(time) - 1)],
                              fillcolor=zona_color[zonas[i0]], line_width=0, layer="below")
                i0 = i

    if duracion_t8_h > 0:
        t8_end = min(duracion_t8_h, horizonte_h)
        fig.add_vrect(x0=0, x1=t8_end, fillcolor="rgba(31,56,100,0.07)",
                      line_width=1, line_dash="dash", line_color=AZUL)
        fig.add_annotation(x=0, y=1.06, yref="paper", text="Inicio T8", showarrow=False,
                           font=dict(size=9, color=AZUL), xanchor="left")
        fig.add_annotation(x=t8_end, y=1.06, yref="paper", text="Fin T8", showarrow=False,
                           font=dict(size=9, color=AZUL), xanchor="left")

    # Anotaciones de mantencion activa (si el llamador las provee) —
    # reusa las mismas ventanas [ini,fin] en hora de reloj que ya usa
    # engine.scheduler.equipos_en_mantencion, sin duplicar esa logica.
    if maint_windows:
        for equipo, ventana in maint_windows.items():
            if not ventana:
                continue
            ini, fin = ventana
            if ini is None or fin is None or ini == fin:
                continue
            ini_h = max(0.0, float(ini))
            fin_h = min(horizonte_h, float(fin) if fin > ini else horizonte_h)
            if ini_h >= horizonte_h:
                continue
            fig.add_vline(x=ini_h, line_dash="dot", line_color=NARANJA, line_width=1.5)
            fig.add_annotation(x=ini_h, y=-0.10, yref="paper",
                               text=f"Mant. {equipo} inicio", showarrow=False,
                               font=dict(size=8, color=NARANJA), xanchor="left")
            if fin_h < horizonte_h:
                fig.add_vline(x=fin_h, line_dash="dot", line_color=NARANJA, line_width=1.5)
                fig.add_annotation(x=fin_h, y=-0.10, yref="paper",
                                   text=f"Mant. {equipo} fin", showarrow=False,
                                   font=dict(size=8, color=NARANJA), xanchor="left")

    fig.add_trace(go.Scatter(
        x=time, y=t1, name="T1 disponible (TPH)",
        line=dict(color=AZUL, width=2.5),
        hovertemplate="t=%{x:.1f}h | T1=%{y:.0f} TPH<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=time, y=cv315, name="CV315 hacia SAG1 (TPH)",
        line=dict(color=AZUL_MED, width=2, dash="dot"),
        hovertemplate="t=%{x:.1f}h | CV315=%{y:.0f} TPH<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=time, y=cv316, name="CV316 hacia SAG2 (TPH)",
        line=dict(color=VERDE, width=2, dash="dot"),
        hovertemplate="t=%{x:.1f}h | CV316=%{y:.0f} TPH<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=time, y=t3, name="T3 desvío (TPH)",
        line=dict(color=NARANJA, width=2.5),
        fill="tozeroy", fillcolor="rgba(230,126,34,0.12)",
        hovertemplate="t=%{x:.1f}h | T3=%{y:.0f} TPH<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text=("Balance de Alimentación: T1, CV315, CV316 y T3 (TPH)  |  "
                  "<span style='color:#27AE60'>■</span> Balanceado  "
                  "<span style='color:#F39C12'>■</span> Pila creciendo  "
                  "<span style='color:#C0392B'>■</span> Pila drenando"),
            font=dict(color=AZUL, size=12), y=0.98,
        ),
        xaxis_title="Tiempo (h)", yaxis_title="TPH",
        xaxis=dict(range=[0, horizonte_h]),
        legend=dict(orientation="h", x=0.5, y=-0.13, xanchor="center", yanchor="top",
                    bgcolor="rgba(15,38,71,0.7)", font=dict(size=10)),
        margin=dict(l=50, r=30, t=70, b=90),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        # CAMBIO 12: altura minima +50% vs los 420px originales.
        height=640,
        uirevision="t1-t3-balance-chart",
    )
    return fig


def make_bottleneck_map_chart(mapa: list) -> go.Figure:
    """Mapa de Cuellos de Botella — barra horizontal por componente,
    coloreada segun estado (engine.bottleneck.full_bottleneck_map).
    Sin relacion causal nueva: solo visualiza el diagnostico ya calculado."""
    color_map = {"verde": VERDE, "amarillo": AMARILLO, "rojo": ROJO}
    nombres = [m["activo"] for m in mapa][::-1]
    colores = [color_map.get(m["color"], "#999") for m in mapa][::-1]
    valores = [1] * len(mapa)
    textos = []
    for m in mapa[::-1]:
        txt = m["activo"]
        if m.get("impacto_tph"):
            txt += f" (-{m['impacto_tph']:.0f} TPH est.)"
        textos.append(txt)

    fig = go.Figure(go.Bar(
        y=nombres, x=valores, orientation="h",
        marker_color=colores,
        text=textos, textposition="inside", insidetextanchor="start",
        hovertemplate="%{y}: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Mapa de Cuellos de Botella", font=dict(color=AZUL, size=13)),
        xaxis=dict(visible=False, range=[0, 1]),
        yaxis=dict(title=""),
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=380,
        showlegend=False,
        uirevision="bottleneck-map",
    )
    return fig


def make_turno_planificador_table(rows: list) -> go.Figure:
    """Planificador de Turno — cronograma horario de disponibilidad de
    equipos y rate recomendado (engine.turno_planner.build_hourly_schedule)."""
    if not rows:
        fig = go.Figure()
        fig.update_layout(paper_bgcolor=BG, height=200,
                          title="Planificador de Turno — sin datos")
        return fig

    def _cell_color(v):
        return "rgba(233,74,74,0.25)" if v == "MANTENCIÓN" else PLOT_BG

    headers = ["Hora", "SAG1 (TPH)", "Bolas SAG1", "SAG2 (TPH)", "Bolas SAG2",
               "411", "412", "511", "512", "T8"]
    cols = [
        [r["hora_reloj"] for r in rows],
        [r["sag1_tph"] for r in rows],
        [r["bolas_sag1"] for r in rows],
        [r["sag2_tph"] for r in rows],
        [r["bolas_sag2"] for r in rows],
        [r["411"] for r in rows],
        [r["412"] for r in rows],
        [r["511"] for r in rows],
        [r["512"] for r in rows],
        ["T8" if r["t8_activo"] else "" for r in rows],
    ]
    fill_colors = [
        [PLOT_BG] * len(rows),
        [PLOT_BG] * len(rows),
        [PLOT_BG] * len(rows),
        [PLOT_BG] * len(rows),
        [PLOT_BG] * len(rows),
        [_cell_color(v) for v in cols[5]],
        [_cell_color(v) for v in cols[6]],
        [_cell_color(v) for v in cols[7]],
        [_cell_color(v) for v in cols[8]],
        ["rgba(79,176,229,0.20)" if v else PLOT_BG for v in cols[9]],
    ]

    fig = go.Figure(go.Table(
        header=dict(values=headers, fill_color="#123059", font=dict(color=AZUL, size=11), align="center",
                    line_color=GRID),
        cells=dict(values=cols, fill_color=fill_colors, align="center", font=dict(size=10, color=AZUL),
                   height=24, line_color=GRID),
    ))
    fig.update_layout(
        title=dict(text="Planificador de Turno", font=dict(color=AZUL, size=13)),
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor=BG,
        height=min(120 + 26 * len(rows), 620),
    )
    return fig


def make_autonomia_chart(sim: dict, horizonte_h: float) -> go.Figure:
    """Serie de autonomia SAG1 y SAG2.

    Reencuadre semántico Etapa 1 (2026-07-14): la línea graficada es la
    trayectoria de autonomía PREVENTIVA HISTÓRICA (`compute_autonomia`,
    tasa de drenaje fija) — es lo único con serie temporal completa,
    porque la autonomía dinámica (`classify_dynamic_autonomy`) solo se
    evalúa en el último paso de `simulate_ode`. Se agrega un marcador
    puntual con el estado dinámico final (Fase 10 del pedido: nunca
    dibujar una línea infinita ni convertir `None` a cero para la
    dinámica) con tooltip que distingue explícitamente ambos conceptos."""
    time = sim["time"]
    fig = go.Figure()

    fig.add_hrect(y0=0, y1=1.0, fillcolor="rgba(192,57,43,0.15)", line_width=0)
    fig.add_hrect(y0=1.0, y1=2.5, fillcolor="rgba(243,156,18,0.10)", line_width=0)
    fig.add_hline(y=2.5, line_dash="dot", line_color=AMARILLO,
                  annotation_text="Alarma (2.5h)", annotation_position="right",
                  annotation_font_size=9)
    fig.add_hline(y=1.0, line_dash="dot", line_color=ROJO,
                  annotation_text="Critico (1h)", annotation_position="right",
                  annotation_font_size=9)

    fig.add_trace(go.Scatter(x=time, y=sim["autonomia_sag1"], name="Autonomía preventiva histórica SAG1",
                             line=dict(color=AZUL_MED, width=2.5),
                             hovertemplate="t=%{x:.1f}h | Preventiva histórica SAG1=%{y:.2f}h<extra></extra>"))
    fig.add_trace(go.Scatter(x=time, y=sim["autonomia_sag2"], name="Autonomía preventiva histórica SAG2",
                             line=dict(color=NARANJA, width=2.5),
                             hovertemplate="t=%{x:.1f}h | Preventiva histórica SAG2=%{y:.2f}h<extra></extra>"))

    _dyn_marker_specs = [
        ("SAG1", AZUL_MED, "diamond"),
        ("SAG2", NARANJA, "diamond-open"),
    ]
    for asset, marker_color, symbol in _dyn_marker_specs:
        _status = sim.get(f"dynamic_net_autonomy_{asset.lower()}_status")
        if _status is None:
            continue
        _h = sim.get(f"dynamic_net_autonomy_{asset.lower()}_h")
        _msg = sim.get(f"dynamic_net_autonomy_{asset.lower()}_message", "")
        _vuln = sim.get(f"historical_vulnerability_{asset.lower()}", "—")
        _hist_h = sim.get(f"historical_preventive_autonomy_{asset.lower()}_h")
        _tooltip = (
            f"Estado: {_status}<br>Balance neto: {sim.get(f'dynamic_net_autonomy_{asset.lower()}_rate_tph', 0):+.0f} t/h"
            f"<br>Autonomía dinámica: {f'{_h:.1f} h' if _h is not None else 'no aplica'}"
            f"<br>Autonomía preventiva histórica: {f'{_hist_h:.1f} h' if _hist_h is not None else '—'}"
            f"<br>Vulnerabilidad histórica: {_vuln}<br>{_msg}"
        )
        if _h is not None:
            # DRAINING / AT_CRITICAL_LEVEL: hay un valor numérico real que
            # graficar en la misma escala de horas de la serie histórica.
            fig.add_trace(go.Scatter(
                x=[time[-1]], y=[_h], mode="markers", name=f"Autonomía dinámica {asset} (final)",
                marker=dict(color=marker_color, size=12, symbol=symbol, line=dict(width=1.5, color="white")),
                hovertext=[_tooltip], hoverinfo="text",
            ))
        else:
            # FILLING / STABLE / SAG_OFF: sin valor en horas por diseño (Fase
            # 10 del pedido) — nunca se dibuja en cero ni con una línea
            # infinita; se anota el estado categórico como texto en el borde
            # superior del gráfico, con el mismo tooltip.
            fig.add_annotation(
                x=time[-1], y=1.0, yref="paper", yanchor="bottom",
                text=f"{asset}: {_status}", showarrow=False,
                font=dict(color=marker_color, size=10),
                hovertext=_tooltip,
            )

    fig.update_layout(
        title=dict(text="Autonomia Operacional (h)", font=dict(color=AZUL, size=13)),
        xaxis_title="Tiempo (h)", yaxis_title="Autonomia (h)",
        xaxis=dict(range=[0, horizonte_h]),
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
        margin=dict(l=40, r=60, t=50, b=40),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=260,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Pagina 1 adicional: Sensibilidad y What-If
# ─────────────────────────────────────────────────────────────────────────────

def make_sensitivity_chart(
    pila_sag1: float,
    pila_sag2: float,
    rate_sag1_tph: float,
    rate_sag2_tph: float,
    cv315_tph: float,
    cv316_tph: float,
) -> go.Figure:
    """
    Inventario Operacional: KPI dual adaptativo.

    Izquierda del equilibrio (rate < feed): Tiempo hasta overflow (pila creciendo).
    Derecha del equilibrio (rate > feed):   Autonomia hasta vaciado (pila drenando).

    Zonas: < 6h critico | 6-24h alerta | > 24h seguro.
    Curva discontinua = zona overflow  |  Curva solida = zona autonomia.
    """
    from engine.ode_model import CRITICAL_PCT, CAP_TON

    CRIT = CRITICAL_PCT
    CAP  = CAP_TON

    VIS_CAP_MIN = 6.0

    # ── KPI unificado: overflow u autonomia segun regimen ─────────────────────
    def _kpi(pile, rate, feed, cap, crit):
        net = rate - feed
        if abs(net) < 0.5:
            return np.inf
        dh = net / cap * 100          # %/h  (+= drena, -= llena)
        if net > 0:                    # DRENANDO → autonomia
            return 0.0 if pile <= crit else (pile - crit) / dh
        else:                          # LLENANDO → tiempo hasta overflow
            remaining = 100.0 - pile
            return 0.0 if remaining <= 0.0 else remaining / abs(dh)

    # ── Grid centrado en el equilibrio (feed) ─────────────────────────────────
    def _grid(feed_tph, curr_tph, lo, hi, ref_tph):
        half = max(ref_tph * 0.42, 550.0)
        x_lo = max(lo, feed_tph - half)
        x_hi = min(hi, feed_tph + half)
        x_lo = min(x_lo, max(lo, curr_tph - 150.0))
        x_hi = max(x_hi, min(hi, curr_tph + 150.0))
        min_w = max(ref_tph * 0.55, 700.0)
        if x_hi - x_lo < min_w:
            mid = (x_lo + x_hi) / 2.0
            x_lo, x_hi = max(lo, mid - min_w / 2.0), min(hi, mid + min_w / 2.0)
        return np.linspace(x_lo, x_hi, 220), x_lo, x_hi

    # ── vis_cap separado fill/drain para no colapsar el eje Y ─────────────────
    def _vc_arm(vals):
        fin = [v for v in vals if np.isfinite(v) and v > 0]
        if not fin:
            return VIS_CAP_MIN
        return min(72.0, max(VIS_CAP_MIN, min(fin) * 1.35, float(np.percentile(fin, 35))))

    def _vis_cap(rs, kpi_raw, feed):
        fill_v  = [v for r, v in zip(rs, kpi_raw) if r < feed]
        drain_v = [v for r, v in zip(rs, kpi_raw) if r > feed]
        return max(_vc_arm(fill_v), _vc_arm(drain_v))

    SAG1_PHYS_MAX = 1700.0
    SAG2_PHYS_MAX = 2800.0
    hi1 = max(SAG1_PHYS_MAX, cv315_tph * 1.06 + 150.0) if cv315_tph > SAG1_PHYS_MAX else SAG1_PHYS_MAX
    hi2 = max(SAG2_PHYS_MAX, cv316_tph * 1.06 + 150.0) if cv316_tph > SAG2_PHYS_MAX else SAG2_PHYS_MAX

    rs1, x1_lo, x1_hi = _grid(cv315_tph, rate_sag1_tph, 400.0, hi1, 1454.0)
    rs2, x2_lo, x2_hi = _grid(cv316_tph, rate_sag2_tph, 800.0, hi2, 2516.0)

    kpi1_raw = [_kpi(pila_sag1, r, cv315_tph, CAP["SAG1"], CRIT["SAG1"]) for r in rs1]
    kpi2_raw = [_kpi(pila_sag2, r, cv316_tph, CAP["SAG2"], CRIT["SAG2"]) for r in rs2]

    vc1 = _vis_cap(rs1, kpi1_raw, cv315_tph)
    vc2 = _vis_cap(rs2, kpi2_raw, cv316_tph)

    kpi1 = [min(v, vc1) if np.isfinite(v) else vc1 for v in kpi1_raw]
    kpi2 = [min(v, vc2) if np.isfinite(v) else vc2 for v in kpi2_raw]

    kpi1_act = _kpi(pila_sag1, rate_sag1_tph, cv315_tph, CAP["SAG1"], CRIT["SAG1"])
    kpi2_act = _kpi(pila_sag2, rate_sag2_tph, cv316_tph, CAP["SAG2"], CRIT["SAG2"])

    # Modo de operacion actual
    def _mode(rate, feed):
        d = rate - feed
        if d > 10:   return "DRENANDO"
        if d < -10:  return "LLENANDO"
        return "EQUILIBRIO"

    mode1 = _mode(rate_sag1_tph, cv315_tph)
    mode2 = _mode(rate_sag2_tph, cv316_tph)

    ICON = {"DRENANDO": "⬇", "LLENANDO": "⬆", "EQUILIBRIO": "◆"}
    MCLR = {"DRENANDO": ROJO, "LLENANDO": VERDE, "EQUILIBRIO": AMARILLO}
    MLBL = {"DRENANDO": "Autonomía", "LLENANDO": "T. overflow", "EQUILIBRIO": "Equilibrio"}

    def _kpi_str(val, vc):
        if not np.isfinite(val) or val >= vc:
            return f">{vc:.0f}h"
        return f"{val:.1f}h"

    sub1 = (f"SAG1  Pila {pila_sag1:.0f}%  |  Feed CV315={cv315_tph:.0f} TPH  |  "
            f"{ICON[mode1]} {mode1}: {_kpi_str(kpi1_act, vc1)}")
    sub2 = (f"SAG2  Pila {pila_sag2:.0f}%  |  Feed CV316={cv316_tph:.0f} TPH  |  "
            f"{ICON[mode2]} {mode2}: {_kpi_str(kpi2_act, vc2)}")

    fig = make_subplots(rows=1, cols=2, subplot_titles=[sub1, sub2],
                        horizontal_spacing=0.13)

    # ── Zonas horizontales (6h / 24h, validas para ambos modos) ──────────────
    for col, vc in [(1, vc1), (2, vc2)]:
        fig.add_hrect(y0=0,    y1=6.0,   fillcolor="rgba(192,57,43,0.12)",  line_width=0, row=1, col=col)
        fig.add_hrect(y0=6.0,  y1=24.0,  fillcolor="rgba(243,156,18,0.10)", line_width=0, row=1, col=col)
        fig.add_hrect(y0=24.0, y1=vc + 1, fillcolor="rgba(39,174,96,0.06)", line_width=0, row=1, col=col)
        for yh, lbl, clr in [(6.0, "6h critico", ROJO), (24.0, "24h alerta", AMARILLO)]:
            fig.add_hline(y=yh, line_dash="dot", line_color=clr, line_width=1.2,
                          annotation_text=lbl, annotation_font=dict(size=8, color=clr),
                          annotation_position="bottom right", row=1, col=col)

    # ── Curvas por SAG ────────────────────────────────────────────────────────
    cfgs = [
        dict(col=1, rs=rs1, kpi=kpi1, kpi_act=kpi1_act, vc=vc1,
             feed=cv315_tph, curr=rate_sag1_tph, pile=pila_sag1,
             color=AZUL_MED, mode=mode1, phys=SAG1_PHYS_MAX,
             name="SAG1", x_hi=x1_hi),
        dict(col=2, rs=rs2, kpi=kpi2, kpi_act=kpi2_act, vc=vc2,
             feed=cv316_tph, curr=rate_sag2_tph, pile=pila_sag2,
             color=NARANJA, mode=mode2, phys=SAG2_PHYS_MAX,
             name="SAG2", x_hi=x2_hi),
    ]

    for c in cfgs:
        col     = c["col"]
        rs      = c["rs"]
        kpi     = c["kpi"]
        vc      = c["vc"]
        feed    = c["feed"]
        curr    = c["curr"]
        color   = c["color"]
        mode    = c["mode"]
        phys    = c["phys"]
        name    = c["name"]
        x_hi    = c["x_hi"]
        kpi_act = c["kpi_act"]

        # Zona fuera de rango fisico operacional
        if feed > phys:
            fig.add_vrect(x0=phys, x1=x_hi,
                          fillcolor="rgba(120,120,120,0.08)", line_width=0,
                          annotation_text=f"Fuera rango<br>{name}",
                          annotation_position="top left",
                          annotation_font=dict(size=7, color=TEXTO_MUTED), row=1, col=col)

        # Separar tramos: izquierda = overflow (dash), derecha = autonomia (solid)
        fill_pts  = [(r, v) for r, v in zip(rs, kpi) if r <= feed]
        drain_pts = [(r, v) for r, v in zip(rs, kpi) if r >= feed]

        if fill_pts:
            fx, fy = zip(*fill_pts)
            fig.add_trace(go.Scatter(
                x=list(fx), y=list(fy),
                name=f"T. overflow {name}",
                line=dict(color=color, width=2.5, dash="dash"),
                hovertemplate=(
                    f"{name}: Rate=%{{x:.0f}} TPH<br>"
                    "Overflow en %{y:.1f}h<extra></extra>"
                ),
                showlegend=True,
            ), row=1, col=col)

        if drain_pts:
            dx, dy = zip(*drain_pts)
            fig.add_trace(go.Scatter(
                x=list(dx), y=list(dy),
                name=f"Autonomia {name}",
                line=dict(color=color, width=2.5),
                hovertemplate=(
                    f"{name}: Rate=%{{x:.0f}} TPH<br>"
                    "Autonomia %{y:.1f}h<extra></extra>"
                ),
                showlegend=True,
            ), row=1, col=col)

        # Marcador punto actual
        kpi_disp = min(kpi_act, vc - 0.3) if np.isfinite(kpi_act) else vc - 0.3
        kpi_str  = _kpi_str(kpi_act, vc)
        fig.add_trace(go.Scatter(
            x=[curr], y=[kpi_disp],
            mode="markers+text",
            marker=dict(size=13, color=color, symbol="circle",
                        line=dict(width=2, color="white")),
            text=[f" {kpi_str}"],
            textposition="middle right",
            textfont=dict(size=10, color=color, family="Arial Black"),
            name=f"Actual {name}: {curr:.0f} TPH",
            hovertemplate=(
                f"Actual {name}: {curr:.0f} TPH<br>"
                f"{MLBL[mode]}: {kpi_str}<extra></extra>"
            ),
            showlegend=True,
        ), row=1, col=col)

        # Vline: rate actual
        fig.add_vline(x=curr, line_dash="dash", line_color=color,
                      line_width=1.2, row=1, col=col)

        # Vline: equilibrio (mas grueso, gris oscuro)
        fig.add_vline(x=feed, line_dash="dot", line_color="#5D6D7E",
                      line_width=1.8, row=1, col=col)

        # Anotacion equilibrio
        eq_anchor = "left" if curr <= feed else "right"
        fig.add_annotation(
            x=feed, y=vc - 0.5,
            text=f"Equilibrio {feed:.0f} TPH",
            showarrow=False, font=dict(size=8, color="#5D6D7E"),
            bgcolor="rgba(15,38,71,0.90)", bordercolor="#BDC3C7", borderwidth=1,
            xanchor=eq_anchor, yanchor="top",
            row=1, col=col,
        )

        # Anotacion estado operacional
        state_clr = MCLR[mode]
        if mode == "LLENANDO":
            state_txt = f"⬆ Pila creciendo — overflow en {kpi_str}"
        elif mode == "DRENANDO":
            state_txt = f"⬇ Pila drenando — autonomia {kpi_str}"
        else:
            state_txt = "◆ Inventario en equilibrio"

        ann_y  = max(1.5, kpi_disp * 0.35)
        ann_ax = 60 if curr <= feed else -60
        fig.add_annotation(
            x=curr, y=ann_y,
            text=state_txt,
            showarrow=True, arrowhead=2, arrowcolor=state_clr,
            ax=ann_ax, ay=0,
            font=dict(size=8.5, color=state_clr),
            bgcolor="rgba(15,38,71,0.94)", bordercolor=state_clr, borderwidth=1.2,
            xanchor="left" if curr <= feed else "right", yanchor="middle",
            row=1, col=col,
        )

    # ── Layout ───────────────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(
            text=("Inventario Operacional SAG  —  "
                  "- - -  Overflow (pila llena)     ——  Autonomia (pila drena)"),
            font=dict(color=AZUL, size=11), x=0.01, y=0.99, xanchor="left",
        ),
        legend=dict(
            orientation="h", x=0.5, y=-0.24, xanchor="center",
            bgcolor="rgba(15,38,71,0.85)", font=dict(size=9),
            bordercolor="#ddd", borderwidth=1,
        ),
        margin=dict(l=55, r=15, t=80, b=75),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=335,
    )

    TICK_V = [0, 6, 12, 18, 24, 36, 48, 60, 72]
    fig.update_yaxes(
        range=[0, vc1 + 0.5], title_text="Horas",
        tickvals=[t for t in TICK_V if t <= vc1 + 0.5],
        gridcolor=GRID, row=1, col=1,
    )
    fig.update_yaxes(
        range=[0, vc2 + 0.5], title_text="",
        tickvals=[t for t in TICK_V if t <= vc2 + 0.5],
        gridcolor=GRID, row=1, col=2,
    )
    x1_ttl = f"Rate SAG1 (TPH)  ← overflow | autonomia →  (eq. {cv315_tph:.0f} TPH)"
    x2_ttl = f"Rate SAG2 (TPH)  ← overflow | autonomia →  (eq. {cv316_tph:.0f} TPH)"
    fig.update_xaxes(title_text=x1_ttl, gridcolor=GRID,
                     range=[x1_lo, x1_hi], row=1, col=1)
    fig.update_xaxes(title_text=x2_ttl, gridcolor=GRID,
                     range=[x2_lo, x2_hi], row=1, col=2)
    return fig


def make_risk_chart(sim: dict, horizonte_h: float, duracion_t8_h: float) -> go.Figure:
    """Riesgo operacional discreto por inventario: 0 seguro, 1 monitorear, 2 critico."""
    time = np.array(sim["time"])
    risk1 = np.array(sim.get("riesgo_sag1", [0] * len(time)))
    risk2 = np.array(sim.get("riesgo_sag2", [0] * len(time)))

    fig = go.Figure()

    fig.add_hrect(y0=-0.1, y1=0.5, fillcolor="rgba(39,174,96,0.08)", line_width=0)
    fig.add_hrect(y0=0.5, y1=1.5, fillcolor="rgba(243,156,18,0.10)", line_width=0)
    fig.add_hrect(y0=1.5, y1=2.2, fillcolor="rgba(192,57,43,0.12)", line_width=0)

    if duracion_t8_h > 0:
        t8_end = min(duracion_t8_h, horizonte_h)
        fig.add_vrect(
            x0=0,
            x1=t8_end,
            fillcolor="rgba(31,56,100,0.06)",
            line_width=1,
            line_dash="dash",
            line_color=AZUL,
            annotation_text="T8",
            annotation_position="top left",
            annotation_font_size=9,
        )

    fig.add_trace(go.Scatter(
        x=time,
        y=risk1,
        mode="lines+markers",
        name="Riesgo SAG1",
        line=dict(color=AZUL_MED, width=2.5, shape="hv"),
        marker=dict(size=5),
        hovertemplate="t=%{x:.1f}h | SAG1=%{y}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=time,
        y=risk2,
        mode="lines+markers",
        name="Riesgo SAG2",
        line=dict(color=NARANJA, width=2.5, shape="hv"),
        marker=dict(size=5),
        hovertemplate="t=%{x:.1f}h | SAG2=%{y}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text="¿Cuándo podría aparecer un problema?", font=dict(color=AZUL, size=13)),
        xaxis_title="Tiempo (h)",
        yaxis_title="Nivel",
        xaxis=dict(range=[0, horizonte_h], gridcolor=GRID),
        yaxis=dict(
            range=[-0.1, 2.2],
            tickvals=[0, 1, 2],
            ticktext=["Seguro", "Monitorear", "Critico"],
            gridcolor=GRID,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=55, r=30, t=55, b=40),
        paper_bgcolor=BG,
        plot_bgcolor=PLOT_BG,
        height=280,
    )
    return fig


def make_whatif_comparison_chart(resultados: list[dict]) -> go.Figure:
    """
    Grafico de barras agrupadas comparando N escenarios.
    resultados: lista de dicts con keys nombre, iro, auton_sag1, auton_sag2, tph_total, accion.
    """
    nombres = [r["nombre"] for r in resultados]
    iros    = [r["iro"]    for r in resultados]
    a1s     = [min(r["auton_sag1"], 24.0) for r in resultados]
    a2s     = [min(r["auton_sag2"], 24.0) for r in resultados]
    tphs    = [r["tph_total"] / 100 for r in resultados]   # /100 para escalar al eje

    iro_colors  = [VERDE if v >= 70 else (AMARILLO if v >= 50 else (NARANJA if v >= 35 else ROJO))
                   for v in iros]
    a1_colors   = [VERDE if v >= 2.5 else (AMARILLO if v >= 1.5 else ROJO) for v in a1s]
    a2_colors   = [VERDE if v >= 4.0 else (AMARILLO if v >= 2.5 else ROJO) for v in a2s]

    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=["IRO (0-100)", "Autonomía SAG1 (h)", "Autonomía SAG2 (h)"],
        horizontal_spacing=0.08,
    )

    fig.add_trace(go.Bar(x=nombres, y=iros,  marker_color=iro_colors, name="IRO",
                         text=[f"{v:.0f}" for v in iros], textposition="outside",
                         hovertemplate="%{x}<br>IRO=%{y:.0f}<extra></extra>"),
                  row=1, col=1)
    fig.add_trace(go.Bar(x=nombres, y=a1s,   marker_color=a1_colors,  name="Auton SAG1",
                         text=[f"{v:.1f}h" for v in a1s], textposition="outside",
                         hovertemplate="%{x}<br>SAG1=%{y:.1f}h<extra></extra>"),
                  row=1, col=2)
    fig.add_trace(go.Bar(x=nombres, y=a2s,   marker_color=a2_colors,  name="Auton SAG2",
                         text=[f"{v:.1f}h" for v in a2s], textposition="outside",
                         hovertemplate="%{x}<br>SAG2=%{y:.1f}h<extra></extra>"),
                  row=1, col=3)

    # Lineas de umbral critico
    fig.add_hline(y=40,  line_dash="dot", line_color=ROJO,     line_width=1, row=1, col=1)
    fig.add_hline(y=1.5, line_dash="dot", line_color=AMARILLO, line_width=1, row=1, col=2)
    fig.add_hline(y=2.5, line_dash="dot", line_color=AMARILLO, line_width=1, row=1, col=3)

    fig.update_layout(
        showlegend=False,
        margin=dict(l=40, r=20, t=55, b=45),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=300,
    )
    fig.update_yaxes(range=[0, 108], row=1, col=1, gridcolor=GRID)
    fig.update_yaxes(range=[0, 16],  row=1, col=2, gridcolor=GRID)
    fig.update_yaxes(range=[0, 16],  row=1, col=3, gridcolor=GRID)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Pagina 2: Curvas historicas
# ─────────────────────────────────────────────────────────────────────────────

# Datos dose-response hardcodeados (medians validados de 70 eventos T8)
DOSE_DATA = {
    "SAG1": {"dur": [2, 4, 12], "med": [108, 69, 44],  "n": [11, 29, 2]},
    "SAG2": {"dur": [2, 4, 12], "med": [98, 99, 85],   "n": [18, 38, 3]},
    "PMC":  {"dur": [2, 4, 12], "med": [97, 85, 89],   "n": [16, 43, 3]},
    "UNITARIO": {"dur": [2, 4, 12], "med": [96, 100, 95], "n": [7, 17, 2]},
}


def make_dose_response_chart(asset: str) -> go.Figure:
    """
    Curva dose-response con bandas de color y anotaciones.
    asset: 'SAG1' | 'SAG2' | 'PMC' | 'UNITARIO'
    """
    d = DOSE_DATA[asset]
    durs = d["dur"]
    meds = d["med"]
    ns   = d["n"]
    colors_asset = {"SAG1": AZUL_MED, "SAG2": NARANJA, "PMC": VERDE, "UNITARIO": "#8E44AD"}

    fig = go.Figure()

    # ── Bandas horizontales de rendimiento ──────────────────────────────────
    fig.add_hrect(y0=90, y1=120, fillcolor="rgba(39,174,96,0.12)",  line_width=0,
                  annotation_text=">90% P90 (verde)", annotation_position="right",
                  annotation_font_size=9)
    fig.add_hrect(y0=80, y1=90,  fillcolor="rgba(243,156,18,0.12)", line_width=0)
    fig.add_hrect(y0=70, y1=80,  fillcolor="rgba(230,126,34,0.12)", line_width=0)
    fig.add_hrect(y0=0,  y1=70,  fillcolor="rgba(192,57,43,0.12)",  line_width=0)

    # Linea de referencia 100%
    fig.add_hline(y=100, line_dash="dot", line_color="#999",
                  annotation_text="Baseline (100%)", annotation_position="left",
                  annotation_font_size=9)

    # ── Fit cuadratico ───────────────────────────────────────────────────────
    if len(durs) >= 3:
        x_fit = np.linspace(1, 14, 50)
        coeffs = np.polyfit(durs, meds, 2)
        y_fit = np.polyval(coeffs, x_fit)
        fig.add_trace(go.Scatter(
            x=x_fit, y=y_fit, name="Fit cuadratico",
            line=dict(color=colors_asset.get(asset, AZUL), width=2, dash="dash"),
            hoverinfo="skip",
        ))

    # ── Puntos de datos ────────────────────────────────────────────────────
    marker_colors = [ROJO if n < 15 else colors_asset.get(asset, AZUL) for n in ns]
    n_labels = [f"n={n}" for n in ns]

    fig.add_trace(go.Scatter(
        x=durs, y=meds, name=f"{asset} mediana",
        mode="markers+lines+text",
        marker=dict(size=14, color=marker_colors, symbol="circle",
                    line=dict(width=2, color="white")),
        line=dict(color=colors_asset.get(asset, AZUL), width=2.5),
        text=n_labels,
        textposition="top center",
        textfont=dict(size=10, color=[ROJO if n < 15 else "#555" for n in ns]),
        customdata=list(zip(meds, ns, [f"{m-100:+.0f}%" for m in meds])),
        hovertemplate=(
            "<b>Duracion T8: %{x}h</b><br>"
            "TPH mediano: %{customdata[0]:.0f}% P90<br>"
            "n eventos: %{customdata[1]}<br>"
            "Caida: %{customdata[2]}<extra></extra>"
        ),
    ))

    # ── Anotacion de impacto severo (para SAG1 a 4h) ────────────────────────
    if asset == "SAG1":
        fig.add_annotation(
            x=4, y=69,
            text="[!] Impacto severo",
            showarrow=True, arrowhead=2, arrowcolor=ROJO,
            ax=40, ay=-40,
            font=dict(color=ROJO, size=10),
            bgcolor="rgba(15,38,71,0.8)",
        )

    fig.update_layout(
        title=dict(text=f"Dose-Response {asset} — 70 eventos T8", font=dict(color=AZUL, size=13)),
        xaxis_title="Duracion T8 (h)",
        yaxis_title="TPH mediano (% P90)",
        xaxis=dict(tickvals=[2, 4, 8, 12], range=[0.5, 14]),
        yaxis=dict(range=[30, 125]),
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
        margin=dict(l=50, r=80, t=55, b=45),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=320,
    )
    return fig


def make_autonomia_historica(df_hist) -> go.Figure:
    """
    Serie temporal de autonomia historica SAG1/SAG2 (ultimos 30 dias).
    df_hist: DataFrame con fecha, pila_sag1, pila_sag2.
    """
    from engine.ode_model import compute_autonomia

    df = df_hist.copy()
    df = df.sort_values("fecha")
    # Ultimos 30 dias
    fecha_max = df["fecha"].max()
    df = df[df["fecha"] >= fecha_max - np.timedelta64(30, "D")]

    # Resample a 30 min (Fase 7 performance): el dato fuente viene a 5 min
    # (~8,640 puntos/30 dias) pero una tendencia de autonomia no pierde
    # informacion operacional relevante a resolucion de 30 min (~1,440
    # puntos) — reduce ~6x el payload enviado al navegador en el arranque.
    df = (
        df.set_index("fecha")[["pila_sag1", "pila_sag2"]]
        .resample("30min").mean()
        .dropna(how="all")
        .reset_index()
    )

    auton1 = df["pila_sag1"].apply(lambda p: compute_autonomia(p, "SAG1"))
    auton2 = df["pila_sag2"].apply(lambda p: compute_autonomia(p, "SAG2"))

    fig = go.Figure()

    fig.add_hrect(y0=0, y1=1.0, fillcolor="rgba(192,57,43,0.12)", line_width=0)
    fig.add_hrect(y0=1.0, y1=2.5, fillcolor="rgba(243,156,18,0.09)", line_width=0)
    fig.add_hline(y=2.5, line_dash="dot", line_color=AMARILLO, annotation_text="Alarma 2.5h",
                  annotation_position="right", annotation_font_size=9)
    fig.add_hline(y=1.0, line_dash="dot", line_color=ROJO, annotation_text="Critico 1h",
                  annotation_position="right", annotation_font_size=9)

    fig.add_trace(go.Scatter(x=df["fecha"], y=auton1, name="Autonomia SAG1",
                             line=dict(color=AZUL_MED, width=1.5),
                             hovertemplate="%{x|%Y-%m-%d %H:%M} | SAG1=%{y:.2f}h<extra></extra>"))
    fig.add_trace(go.Scatter(x=df["fecha"], y=auton2, name="Autonomia SAG2",
                             line=dict(color=NARANJA, width=1.5),
                             hovertemplate="%{x|%Y-%m-%d %H:%M} | SAG2=%{y:.2f}h<extra></extra>"))

    fig.update_layout(
        title=dict(text="Autonomia Historica — Ultimos 30 dias", font=dict(color=AZUL, size=13)),
        xaxis_title="Fecha",
        yaxis_title="Autonomia (h)",
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
        margin=dict(l=50, r=80, t=55, b=45),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=320,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Pagina 3: Mapa de calor de decision
# ─────────────────────────────────────────────────────────────────────────────

def make_decision_heatmap() -> go.Figure:
    """
    Heatmap: pila_inicial (eje Y) vs duracion_t8 (eje X).
    Color = nivel de riesgo simulado.
    """
    from engine.simulator import simulate_scenario_cached

    pilas = [20, 30, 40, 50, 60, 70, 80]
    durs  = [0, 2, 4, 8, 12]

    z = np.zeros((len(pilas), len(durs)))
    hover = [["" for _ in durs] for _ in pilas]

    for i, p in enumerate(pilas):
        for j, d in enumerate(durs):
            sim = simulate_scenario_cached(
                pila_sag1_pct=p, pila_sag2_pct=p,
                rate_sag1_pct=85, rate_sag2_pct=88,
                estado_bola_1=False, estado_bola_2=False,
                sag1_activo=True, sag2_activo=True,
                duracion_t8_h=d,
                correa315_estado="activa",
                correa316_estado="activa",
                horizonte_horas=24,
            )
            # z = min autonomia SAG1 (peor caso)
            min_a1 = sim["min_autonomia_sag1"]
            min_a2 = sim["min_autonomia_sag2"]
            min_a = min(min_a1, min_a2)
            # Score 0=critico, 1=warning, 2=ok
            if min_a < 1.0:
                z[i, j] = 0
            elif min_a < 2.5:
                z[i, j] = 1
            else:
                z[i, j] = 2
            hover[i][j] = f"Pila {p}% | T8 {d}h | Auton min {min_a:.1f}h"

    colorscale = [
        [0.0, ROJO],
        [0.5, AMARILLO],
        [1.0, VERDE],
    ]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"{d}h" for d in durs],
        y=[f"{p}%" for p in pilas],
        colorscale=colorscale,
        zmin=0, zmax=2,
        text=hover,
        hovertemplate="%{text}<extra></extra>",
        showscale=True,
        colorbar=dict(
            tickvals=[0, 1, 2],
            ticktext=["Critico (<1h)", "Alerta (1-2.5h)", "Seguro (>2.5h)"],
        ),
    ))

    fig.update_layout(
        title=dict(text="Matriz de Decision: Pila Inicial vs Duracion T8", font=dict(color=AZUL, size=13)),
        xaxis_title="Duracion T8",
        yaxis_title="Pila Inicial (%)",
        margin=dict(l=60, r=60, t=55, b=45),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=380,
    )
    return fig


def _p_safe_confianza_label(p_safe: float) -> tuple[str, str]:
    """Mapea P(seguro) a etiqueta categorica + color (mismos cortes que
    make_mc_chart._clr: >=90 Muy Alta, >=70 Alta, >=50 Media, <50 Baja)."""
    p = p_safe * 100.0
    if p >= 90: return "Muy Alta", VERDE
    if p >= 70: return "Alta", AMARILLO
    if p >= 50: return "Media", NARANJA
    return "Baja", ROJO


def make_mc_fan_chart(best: dict) -> go.Figure:
    """
    "¿Que tan confiable es esta recomendacion?" — banda de confianza (fan
    chart) de TPH por SAG sobre el 95% de los escenarios Monte Carlo del
    candidato ganador, con la recomendacion puntual e indicador categorico
    de confiabilidad. Reemplaza el frontier plot estadistico make_mc_chart
    en la vista operacional.
    """
    fig = go.Figure()
    if not best:
        fig.update_layout(title="Sin datos — ejecute el optimizador primero",
                          paper_bgcolor=BG, height=320)
        return fig

    r1, r2 = best.get("r1", 0), best.get("r2", 0)
    p10_1, p50_1, p90_1 = best.get("tph1_p10", r1), best.get("tph1_p50", r1), best.get("tph1_p90", r1)
    p10_2, p50_2, p90_2 = best.get("tph2_p10", r2), best.get("tph2_p50", r2), best.get("tph2_p90", r2)
    label, color = _p_safe_confianza_label(best.get("p_safe", 0.0))

    rows = [("SAG1", p10_1, p50_1, p90_1, r1), ("SAG2", p10_2, p50_2, p90_2, r2)]
    for i, (name, p10, p50, p90, rec) in enumerate(rows):
        y = i
        fig.add_trace(go.Scatter(
            x=[p10, p90], y=[y, y], mode="lines",
            line=dict(color=color, width=14),
            opacity=0.25, showlegend=False,
            hovertemplate=f"{name} — 95% de escenarios: {p10:.0f} → {p90:.0f} TPH<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[p50], y=[y], mode="markers+text",
            marker=dict(size=10, color=AZUL, symbol="line-ns-open", line=dict(width=3, color=AZUL)),
            text=[f"{rec:.0f} TPH"], textposition="top center",
            textfont=dict(size=11, color=AZUL, weight="bold"),
            showlegend=False,
            hovertemplate=f"{name} recomendado: {rec:.0f} TPH (mediana MC: {p50:.0f})<extra></extra>",
        ))

    fig.update_layout(
        # 2026-07-07: se saco el texto del titulo (duplicaba el del boton
        # colapsable "¿Que tan confiable es esta recomendacion?" que ya
        # esta justo arriba) — queda solo el indicador de confiabilidad.
        title=dict(text="Rango esperado de producción (P10–P90)",
                   font=dict(size=12, color=AZUL)),
        xaxis=dict(title="TPH", gridcolor=GRID),
        yaxis=dict(tickvals=[0, 1], ticktext=["SAG1", "SAG2"], range=[-0.6, 1.6]),
        annotations=[dict(
            x=0.99, y=1.12, xref="paper", yref="paper", showarrow=False,
            text=f"Confiabilidad: <b>{label}</b>",
            font=dict(size=12, color=color), align="right",
        )],
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=220, margin=dict(l=60, r=20, t=50, b=40),
    )
    return fig


def make_hourly_risk_chart(best: dict, compact: bool = False) -> go.Figure:
    """Riesgo por hora: P(vaciado)/P(overflow) por SAG a lo largo del
    horizonte, calculado desde las trayectorias Monte Carlo del candidato
    ganador (`best["hourly_risk"]`, ver adaptive_mc_eval).

    compact=True: leyenda vertical mas chica y alto reducido, pensado
    para la columna angosta del sidebar "Ver detalles tecnicos"."""
    fig = go.Figure()
    hr = (best or {}).get("hourly_risk")
    if not hr or not hr.get("hours"):
        fig.update_layout(title="Sin datos — ejecute el optimizador primero",
                          paper_bgcolor=BG, height=200 if compact else 280)
        return fig

    hours = hr["hours"]
    series = [
        ("P(vaciado SAG1)", hr.get("p_vacia_sag1", []), ROJO, "solid"),
        ("P(vaciado SAG2)", hr.get("p_vacia_sag2", []), NARANJA, "solid"),
        ("P(overflow SAG1)", hr.get("p_overflow_sag1", []), AZUL_MED, "dash"),
        ("P(overflow SAG2)", hr.get("p_overflow_sag2", []), AZUL, "dash"),
    ]
    for name, y, color, dash in series:
        if not y:
            continue
        fig.add_trace(go.Scatter(
            x=hours, y=y, mode="lines", name=name,
            line=dict(color=color, width=2, dash=dash),
            hovertemplate=f"{name}: %{{y:.1f}}%<extra></extra>",
        ))

    if compact:
        legend = dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
                      font=dict(size=8))
        margin = dict(l=40, r=90, t=35, b=35)
    else:
        legend = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
        margin = dict(l=50, r=20, t=60, b=40)

    fig.update_layout(
        title=dict(text="¿Cuándo podría aparecer un problema?",
                   font=dict(size=11 if compact else 13, color=AZUL)),
        xaxis=dict(title="Hora del día", gridcolor=GRID),
        yaxis=dict(title="Probabilidad %", gridcolor=GRID, range=[0, 100]),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        legend=legend,
        height=200 if compact else 280, margin=margin,
        font=dict(size=9 if compact else 12),
    )
    return fig


def make_mc_chart(mc_results: list[dict]) -> go.Figure:
    """
    Frontera de robustez Monte Carlo: E[TPH] vs P(seguro).
    Cada punto es una configuración (rate_sag1, bolas, rate_sag2, bolas).
    Tamaño: rango de incertidumbre TPH (P90-P10).
    Color: probabilidad de operación segura.
    """
    if not mc_results:
        return go.Figure()

    results = sorted(mc_results, key=lambda x: x["robust_score"], reverse=True)

    e_tph   = [r["tph_mean"]             for r in results]
    p_safe  = [r["p_safe"] * 100         for r in results]
    tph_rng = [r["tph_p90"] - r["tph_p10"] for r in results]
    labels  = [r["label_short"]           for r in results]

    # Color: verde>=90%, amarillo>=70%, naranja>=50%, rojo<50%
    def _clr(p):
        if p >= 90: return VERDE
        if p >= 70: return AMARILLO
        if p >= 50: return NARANJA
        return ROJO

    colors   = [_clr(p) for p in p_safe]
    # Bubble size normalizado entre 14 y 36
    sz_min, sz_max = min(tph_rng), max(tph_rng)
    sz_range = sz_max - sz_min if sz_max > sz_min else 1
    sizes = [14 + 22 * (v - sz_min) / sz_range for v in tph_rng]

    hover = [
        f"<b>{lbl}</b><br>"
        f"P(seguro): {p:.0f}%<br>"
        f"E[TPH]: {t:.0f}<br>"
        f"TPH P10-P90: {r['tph_p10']:.0f}–{r['tph_p90']:.0f}<br>"
        f"Auton SAG1 med: {r['a1_med']:.1f}h<br>"
        f"Auton SAG2 med: {r['a2_med']:.1f}h<extra></extra>"
        for lbl, p, t, r in zip(labels, p_safe, e_tph, results)
    ]

    fig = go.Figure()

    # Zona segura (P>=80%)
    x_pad = (max(e_tph) - min(e_tph)) * 0.04
    fig.add_shape(type="rect",
                  x0=min(e_tph) - x_pad, x1=max(e_tph) + x_pad,
                  y0=80, y1=106,
                  fillcolor="rgba(39,174,96,0.06)", line_width=0, layer="below")

    # Burbujas sin texto (texto superpuesto es ilegible cuando están cerca)
    fig.add_trace(go.Scatter(
        x=e_tph, y=p_safe,
        mode="markers",
        marker=dict(
            size=sizes,
            color=colors,
            line=dict(width=2, color="white"),
            opacity=0.88,
        ),
        hovertemplate=hover,
        showlegend=False,
    ))

    # Números de ranking dentro de cada burbuja
    fig.add_trace(go.Scatter(
        x=e_tph, y=p_safe,
        mode="text",
        text=[f"{'★' if i == 0 else str(i + 1)}" for i in range(len(labels))],
        textfont=dict(size=9, color="white", family="Arial Black"),
        hoverinfo="skip",
        showlegend=False,
    ))

    # Etiquetas solo para top 3 — posición alternada para evitar solapamiento
    top_n = min(3, len(results))
    text_positions = ["top center", "bottom center", "top right"]
    for i in range(top_n):
        lbl_short = labels[i].replace(" ", " ")  # non-breaking space
        fig.add_annotation(
            x=e_tph[i], y=p_safe[i],
            text=f"<b>{lbl_short}</b>",
            showarrow=False,
            xshift=0,
            yshift=sizes[i] / 2 + 8 if i % 2 == 0 else -(sizes[i] / 2 + 8),
            font=dict(size=9, color=AZUL),
            bgcolor="rgba(15,38,71,0.82)",
            bordercolor=GRID, borderwidth=1,
        )

    # Línea umbral 80%
    fig.add_hline(y=80, line_dash="dot", line_color="#777", line_width=1.2,
                  annotation_text="umbral 80%",
                  annotation_font=dict(size=8, color="#777"),
                  annotation_position="bottom right")

    # Leyenda de colores como anotación en esquina
    for clr_pct, clr_lbl, clr_val in [
        ("≥90%", "P(seguro)≥90%", VERDE),
        ("70-89%", "70–89%", AMARILLO),
        ("<70%", "<70%", NARANJA),
    ]:
        pass  # se comunica por color de burbuja y hover

    fig.update_layout(
        title=dict(
            text="Confiabilidad de la Recomendación — Producción vs Seguridad",
            font=dict(color=AZUL, size=11), x=0.01, xanchor="left",
        ),
        xaxis=dict(title="TPH promedio esperado", gridcolor=GRID),
        yaxis=dict(title="P(seguro) %", range=[0, 110], gridcolor=GRID,
                   tickvals=[0, 20, 40, 60, 80, 100]),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        margin=dict(l=55, r=20, t=50, b=50),
        height=340,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Pagina 5: Riesgo Operacional Bayesiano (MH calibrado)
# ─────────────────────────────────────────────────────────────────────────────

def make_prior_posterior_chart() -> go.Figure:
    """Comparación Prior vs Posterior MH para consumo de pila SAG1 y SAG2."""
    x = np.linspace(-2, 8, 400)

    from scipy.stats import norm

    # SAG1
    prior_mu1, prior_s1   = 0.50, 2.00
    post_mu1,  post_s1    = 1.88, 1.77
    # SAG2
    prior_mu2, prior_s2   = 0.50, 2.00
    post_mu2,  post_s2    = 1.46, 1.33

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["SAG1 — Consumo pila (pp/h)", "SAG2 — Consumo pila (pp/h)"],
        horizontal_spacing=0.10,
    )

    for col, (pmu, ps, mmu, ms, label) in enumerate([
        (prior_mu1, prior_s1, post_mu1, post_s1, "SAG1"),
        (prior_mu2, prior_s2, post_mu2, post_s2, "SAG2"),
    ], 1):
        prior_y = norm.pdf(x, pmu, ps)
        post_y  = norm.pdf(x, mmu, ms)

        fig.add_trace(go.Scatter(
            x=x, y=prior_y, name="Prior" if col == 1 else None,
            showlegend=(col == 1),
            line=dict(color="#AAB7C4", width=2, dash="dot"),
            hovertemplate="x=%{x:.2f}<br>Prior=%{y:.4f}<extra></extra>",
        ), row=1, col=col)

        fig.add_trace(go.Scatter(
            x=x, y=post_y, name="Posterior MH" if col == 1 else None,
            showlegend=(col == 1),
            line=dict(color=AZUL_MED if col == 1 else NARANJA, width=2.5),
            fill="tozeroy",
            fillcolor=f"rgba(26,94,153,0.12)" if col == 1 else f"rgba(230,126,34,0.12)",
            hovertemplate="x=%{x:.2f}<br>Posterior=%{y:.4f}<extra></extra>",
        ), row=1, col=col)

        # Línea vertical en medias
        fig.add_vline(x=pmu, line_dash="dot", line_color="#AAB7C4",
                      line_width=1.5, row=1, col=col)
        fig.add_vline(x=mmu, line_dash="solid",
                      line_color=AZUL_MED if col == 1 else NARANJA,
                      line_width=2, row=1, col=col)

        # Anotaciones
        fig.add_annotation(
            x=pmu, y=0.95, xref=f"x{'' if col==1 else col}", yref="paper",
            text=f"Prior μ={pmu}", showarrow=False,
            font=dict(size=9, color="#999"), xanchor="left",
        )
        fig.add_annotation(
            x=mmu, y=0.80, xref=f"x{'' if col==1 else col}", yref="paper",
            text=f"<b>MH μ={mmu}</b>", showarrow=False,
            font=dict(size=9, color=AZUL_MED if col == 1 else NARANJA), xanchor="left",
        )

    fig.update_xaxes(title_text="Consumo pila (pp/h)", range=[-2, 8], gridcolor=GRID)
    fig.update_yaxes(title_text="Densidad", gridcolor=GRID)
    fig.update_layout(
        title=dict(text="Prior vs Posterior MH — Actualización Bayesiana del Consumo de Pila",
                   font=dict(color=AZUL, size=11), y=0.98),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        margin=dict(l=45, r=20, t=55, b=45),
        height=300,
        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
    )
    return fig


def make_mh_risk_comparison_chart(duracion_t8_h: int = 4) -> go.Figure:
    """Barras agrupadas MC vs MH+MC para los KPIs de riesgo."""
    risk_by_dur = {
        2:  {"mc": 0.8,  "mh": 0.0},
        4:  {"mc": 4.3,  "mh": 5.8},
        8:  {"mc": 25.0, "mh": 30.0},
        12: {"mc": 31.4, "mh": 41.5},
    }
    durs   = list(risk_by_dur.keys())
    mc_vals = [risk_by_dur[d]["mc"] for d in durs]
    mh_vals = [risk_by_dur[d]["mh"] for d in durs]
    labels  = [f"T8={d}h" for d in durs]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="MC clásico",
        x=labels, y=mc_vals,
        marker_color="#AAB7C4",
        text=[f"{v:.1f}%" for v in mc_vals], textposition="outside",
        hovertemplate="%{x}<br>MC clásico: %{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="MC+MH calibrado",
        x=labels, y=mh_vals,
        marker_color=AZUL_MED,
        text=[f"{v:.1f}%" for v in mh_vals], textposition="outside",
        hovertemplate="%{x}<br>MH calibrado: %{y:.1f}%<extra></extra>",
    ))

    # Destacar duración seleccionada
    idx = durs.index(duracion_t8_h) if duracion_t8_h in durs else 1
    fig.add_vline(x=idx, line_dash="dot", line_color=NARANJA, line_width=2)

    fig.update_layout(
        title=dict(text="P(inventario SAG1 <15%) por duración T8 — MC vs MC+MH",
                   font=dict(color=AZUL, size=11), y=0.98),
        barmode="group",
        xaxis=dict(title="Duración T8", gridcolor=GRID),
        yaxis=dict(title="Probabilidad (%)", gridcolor=GRID, range=[0, 55]),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        margin=dict(l=45, r=20, t=55, b=45),
        height=290,
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
    )
    return fig


def make_mh_kpi_delta_chart() -> go.Figure:
    """Gráfico horizontal comparando riesgos MC vs MH para los 3 KPIs clave."""
    kpis = [
        "P(inv. SAG1 <15%)",
        "P(inv. SAG2 <18.2%)",
        "P(emergencia doble)",
    ]
    mc_vals  = [5.6,  24.0, 1.8]
    mh_vals  = [7.8,  29.2, 2.8]
    deltas   = [f"+{mh-mc:.1f}pp ({(mh-mc)/mc*100:.0f}%)" for mc, mh in zip(mc_vals, mh_vals)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="MC clásico",
        y=kpis, x=mc_vals,
        orientation="h",
        marker_color="#C8D6E0",
        text=[f"{v}%" for v in mc_vals], textposition="inside",
        insidetextanchor="middle",
        hovertemplate="%{y}<br>MC: %{x:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="MC+MH calibrado",
        y=kpis, x=[m - c for c, m in zip(mc_vals, mh_vals)],
        orientation="h",
        marker_color=ROJO,
        base=mc_vals,
        text=deltas, textposition="outside",
        hovertemplate="%{y}<br>Δ MH: +%{x:.1f}pp<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text="Riesgo Operacional — Subestimación MC clásico vs MH calibrado",
                   font=dict(color=AZUL, size=11), y=0.98),
        barmode="overlay",
        xaxis=dict(title="Probabilidad (%)", gridcolor=GRID, range=[0, 38]),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        margin=dict(l=170, r=80, t=55, b=45),
        height=260,
        legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Pagina 5: Riesgo Operacional — comparador de escenarios
# ─────────────────────────────────────────────────────────────────────────────

def make_ro_compare_chart(escenarios: list[dict]) -> go.Figure:
    """
    Compara hasta 3 escenarios operacionales (TPH, pilas, autonomía).

    escenarios: list of dicts con keys:
        nombre (str), tph (float), pile1_min (float), pile2_min (float), auton_min (float)
    """
    if not escenarios:
        return go.Figure()

    nombres  = [e["nombre"]           for e in escenarios]
    tphs     = [e.get("tph", 0)       for e in escenarios]
    p1s      = [e.get("pile1_min", 0) for e in escenarios]
    p2s      = [e.get("pile2_min", 0) for e in escenarios]
    auts     = [min(e.get("auton_min", 0), 24.0) for e in escenarios]

    _palette = [AZUL_MED, VERDE, NARANJA]
    bar_col  = [_palette[i % len(_palette)] for i in range(len(escenarios))]
    p1_col   = [VERDE if v >= 20   else (NARANJA if v >= 15   else ROJO) for v in p1s]
    p2_col   = [VERDE if v >= 28   else (NARANJA if v >= 18.2 else ROJO) for v in p2s]
    aut_col  = [VERDE if v >= 3    else (NARANJA if v >= 1.5  else ROJO) for v in auts]

    fig = make_subplots(
        rows=1, cols=4,
        subplot_titles=["TPH promedio", "Pila SAG1 mín %", "Pila SAG2 mín %", "Autonomía mín h"],
        horizontal_spacing=0.06,
    )

    def _add_bars(col, ys, colors, sfx):
        for x, y, c in zip(nombres, ys, colors):
            fig.add_trace(go.Bar(
                x=[x], y=[y], marker_color=c,
                text=[f"{y:.1f}{sfx}"], textposition="outside",
                showlegend=False,
                hovertemplate=f"{x}<br>={y:.1f}{sfx}<extra></extra>",
            ), row=1, col=col)

    _add_bars(1, tphs, bar_col, "")
    _add_bars(2, p1s,  p1_col,  "%")
    _add_bars(3, p2s,  p2_col,  "%")
    _add_bars(4, auts, aut_col, "h")

    fig.add_hline(y=15.0, line_dash="dot", line_color=ROJO,     line_width=1.5, row=1, col=2)
    fig.add_hline(y=18.2, line_dash="dot", line_color=ROJO,     line_width=1.5, row=1, col=3)
    fig.add_hline(y=2.0,  line_dash="dot", line_color=AMARILLO, line_width=1.5, row=1, col=4)

    fig.update_layout(
        showlegend=False,
        margin=dict(l=30, r=20, t=50, b=40),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        height=260,
        font=dict(size=10),
    )
    fig.update_yaxes(gridcolor=GRID)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Optimizer v2 — Pareto scatter y Bola-impact chart
# ─────────────────────────────────────────────────────────────────────────────

def make_pareto_scatter(mc_results: list[dict], compact: bool = False) -> go.Figure:
    """
    Mapa Produccion vs Riesgo (Pareto frontier).
    X: TPH total medio | Y: P(crisis) % | Color: inventario final medio
    Puntos Pareto: borde azul + tamaño mayor.

    compact=True: version para columnas angostas (sidebar "Ver detalles
    tecnicos") — colorbar mas chica, sin anotaciones #1-#3 (no caben
    legibles en ~300px de ancho) y margenes/alto mas ajustados.
    """
    if not mc_results:
        fig = go.Figure()
        fig.update_layout(title="Sin datos — ejecute el optimizador primero",
                          paper_bgcolor=BG, height=240 if compact else 320)
        return fig

    x    = [r["tph_mean"]                             for r in mc_results]
    y    = [r.get("p_crisis", 1 - r["p_safe"]) * 100  for r in mc_results]
    col  = [(r.get("inv_sag1_final", 0) + r.get("inv_sag2_final", 0)) / 2 for r in mc_results]
    labs = [r.get("label_short", "")                  for r in mc_results]
    pareto = [r.get("pareto", False)                  for r in mc_results]
    scores = [r.get("multi_criteria_score", 0)        for r in mc_results]

    sizes  = [18 if p else 10 for p in pareto]
    widths = [3  if p else 0  for p in pareto]

    fig = go.Figure()

    # Trace principal: todos los puntos
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="markers",
        marker=dict(
            size=sizes,
            color=col,
            colorscale="RdYlGn",
            cmin=15, cmax=75,
            showscale=True,
            colorbar=dict(title="Inv.<br>final %",
                          thickness=8 if compact else 12,
                          len=0.55 if compact else 0.7),
            line=dict(width=widths, color=[AZUL if p else "white" for p in pareto]),
        ),
        text=labs,
        hovertemplate=(
            "<b>%{text}</b><br>"
            "TPH: %{x:.0f}<br>"
            "P(crisis): %{y:.1f}%<br>"
            "Inv. medio: %{marker.color:.0f}%"
            "<extra></extra>"
        ),
    ))

    # Anotaciones para top-3 por score — se omiten en modo compacto
    # porque no caben legibles en una columna angosta.
    if not compact:
        top3 = sorted(range(len(mc_results)), key=lambda i: scores[i], reverse=True)[:3]
        for rank, idx in enumerate(top3):
            sign = 1 if rank % 2 == 0 else -1
            fig.add_annotation(
                x=x[idx], y=y[idx],
                text=f"#{rank+1}",
                showarrow=True,
                arrowhead=2, arrowsize=0.8, arrowwidth=1.5,
                arrowcolor=AZUL,
                ax=0, ay=sign * (-28 - rank * 10),
                font=dict(size=9, color=AZUL, weight="bold"),
                bgcolor="rgba(15,38,71,0.85)",
                bordercolor=AZUL, borderwidth=1, borderpad=2,
            )

    # Linea umbral seguro
    fig.add_hline(y=5, line_dash="dot", line_color=VERDE, line_width=1.5,
                  annotation_text="Umbral seguro", annotation_position="top right",
                  annotation_font_size=9)

    fig.update_layout(
        title=dict(text="¿Cuál es la probabilidad de cumplir la producción?", x=0.01, xanchor="left",
                   font=dict(size=11 if compact else 12, color=AZUL)),
        xaxis=dict(title="TPH Total (medio MC)", gridcolor=GRID),
        yaxis=dict(title="P(crisis) %", gridcolor=GRID,
                   range=[-2, max(max(y) * 1.15, 15)]),
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        margin=dict(l=45, r=15, t=40, b=40) if compact else dict(l=50, r=80, t=45, b=45),
        height=240 if compact else 320,
        font=dict(size=9 if compact else 10),
        showlegend=False,
    )
    return fig


def make_bola_impact_chart(mc_results: list[dict]) -> go.Figure:
    """
    Impacto de molinos de bola: barras agrupadas DELTA_TPH / Delta_Auton / Delta_Inv
    para 0, 1 y 2 bolas en SAG1 y SAG2.
    Datos derivados de mc_results agrupando por config de bola.
    """
    from engine.ode_model import BOLA_DELTA_TPH  # deltas calibrados

    if not mc_results:
        fig = go.Figure()
        fig.update_layout(title="Sin datos", paper_bgcolor=BG, height=300)
        return fig

    # Agrupar por (n_bolas_SAG1, n_bolas_SAG2) para extraer deltas
    def _n(bstr):
        if "ambas" in bstr: return 2
        if "411" in bstr or "511" in bstr or "412" in bstr or "512" in bstr: return 1
        return 0

    # Separar baselines (sin bola en un SAG, otro fijo) para calcular deltas
    def _delta_for_sag(sag: str, fix_b_other: str = "sin_bola"):
        """Para un SAG, calcula dTPH, dAuton, dInv variando n_bola del SAG."""
        results_by_n: dict[int, list] = {0: [], 1: [], 2: []}
        for r in mc_results:
            nb1 = _n(r["b1"])
            nb2 = _n(r["b2"])
            if sag == "SAG1":
                results_by_n.get(nb1, []).append(r)
            else:
                results_by_n.get(nb2, []).append(r)

        base = results_by_n.get(0, [])
        if not base:
            # No hay baseline: usar delta calibrado
            return {
                0: (0, 0, 0),
                1: (BOLA_DELTA_TPH[sag][1], -0.3, -1.5),
                2: (BOLA_DELTA_TPH[sag][2], -0.7, -3.0),
            }

        tph0 = float(np.mean([r["tph_mean"] for r in base]))
        a0   = float(np.mean([r["a1_med" if sag == "SAG1" else "a2_med"] for r in base]))
        inv0 = float(np.mean([(r["inv_sag1_final"] if sag == "SAG1" else r["inv_sag2_final"]) for r in base]))

        deltas = {0: (0.0, 0.0, 0.0)}
        for n in [1, 2]:
            grp = results_by_n.get(n, [])
            if grp:
                dt = float(np.mean([r["tph_mean"]    for r in grp])) - tph0
                da = float(np.mean([r["a1_med" if sag == "SAG1" else "a2_med"] for r in grp])) - a0
                di = float(np.mean([(r["inv_sag1_final"] if sag == "SAG1" else r["inv_sag2_final"]) for r in grp])) - inv0
            else:
                # Interpolacion desde calibracion
                dt = BOLA_DELTA_TPH[sag].get(n, 0)
                da = -0.4 * n
                di = -2.0 * n
            deltas[n] = (dt, da, di)
        return deltas

    d1 = _delta_for_sag("SAG1")
    d2 = _delta_for_sag("SAG2")

    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=("ΔTPH (TPH)", "ΔAutonomía (h)", "ΔInventario (%)"),
        shared_xaxes=False,
    )

    colors_n = {0: AZUL_MED, 1: AMARILLO, 2: VERDE}
    labels_n = {0: "0 bolas", 1: "1 bola", 2: "2 bolas"}
    assets   = ["SAG1", "SAG2"]
    deltas   = [d1, d2]
    x_grp    = ["SAG1", "SAG2"]

    for n in [0, 1, 2]:
        dtph = [deltas[i][n][0] for i in range(2)]
        dauton = [deltas[i][n][1] for i in range(2)]
        dinv   = [deltas[i][n][2] for i in range(2)]

        bar_colors = [
            ROJO if v < 0 else colors_n[n] for v in dtph
        ]

        fig.add_trace(go.Bar(
            x=x_grp, y=dtph,
            name=labels_n[n],
            marker_color=[ROJO if v < 0 else colors_n[n] for v in dtph],
            showlegend=(n > 0),
            legendgroup=str(n),
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            x=x_grp, y=dauton,
            name=labels_n[n],
            marker_color=[ROJO if v < 0 else colors_n[n] for v in dauton],
            showlegend=False,
            legendgroup=str(n),
        ), row=1, col=2)
        fig.add_trace(go.Bar(
            x=x_grp, y=dinv,
            name=labels_n[n],
            marker_color=[ROJO if v < 0 else colors_n[n] for v in dinv],
            showlegend=False,
            legendgroup=str(n),
        ), row=1, col=3)

    fig.update_layout(
        title=dict(text="Impacto de Molinos de Bola", x=0.01, xanchor="left",
                   font=dict(size=12, color=AZUL)),
        barmode="group",
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        margin=dict(l=40, r=20, t=55, b=40),
        height=300,
        font=dict(size=10),
        legend=dict(orientation="h", x=0.5, y=-0.15, xanchor="center"),
    )
    for col in [1, 2, 3]:
        fig.update_yaxes(gridcolor=GRID, zeroline=True,
                         zerolinecolor=TEXTO_MUTED, zerolinewidth=1.5, row=1, col=col)
    return fig


def make_pam_projection_chart(proyeccion: dict, asset: str) -> go.Figure:
    """'¿Voy a cumplir el mes?' (CAMBIO 7, UX/UI v2 JdS, 2026-07-07):
    produccion acumulada proyectada (banda P10/P50/P90, evidencia real —
    ver engine.production_stats.get_pam_monthly_projection) vs meta PAM
    mensual (linea horizontal)."""
    fig = go.Figure()
    if not proyeccion:
        fig.update_layout(title=f"Sin datos históricos suficientes — {asset}",
                          paper_bgcolor=BG, plot_bgcolor=PLOT_BG, height=320)
        return fig

    dias = proyeccion["dias"]
    fig.add_trace(go.Scatter(
        x=dias + dias[::-1], y=proyeccion["p90_cum"] + proyeccion["p10_cum"][::-1],
        fill="toself", fillcolor="rgba(26,94,153,0.15)", line=dict(width=0),
        name="Banda P10-P90", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=dias, y=proyeccion["p50_cum"], mode="lines", name="P50 (esperado)",
        line=dict(color=AZUL_MED, width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=dias, y=[proyeccion["meta_mensual"]] * len(dias), mode="lines",
        name="Meta PAM", line=dict(color=ROJO, width=2, dash="dash"),
    ))

    prob = proyeccion.get("prob_cumple_mes", 0.0) * 100.0
    color_prob = VERDE if prob >= 70 else (AMARILLO if prob >= 40 else ROJO)
    fig.update_layout(
        title=dict(text=f"{asset} — Producción proyectada vs Meta PAM "
                         f"(prob. de cumplir el mes: {prob:.0f}%)",
                   font=dict(color=color_prob, size=12), x=0.01, xanchor="left"),
        xaxis_title="Día del mes", yaxis_title="Producción acumulada (t)",
        paper_bgcolor=BG, plot_bgcolor=PLOT_BG,
        margin=dict(l=50, r=20, t=55, b=40), height=340,
        legend=dict(orientation="h", x=0.5, y=-0.18, xanchor="center"),
    )
    fig.update_xaxes(gridcolor=GRID)
    fig.update_yaxes(gridcolor=GRID)
    return fig
    return fig
