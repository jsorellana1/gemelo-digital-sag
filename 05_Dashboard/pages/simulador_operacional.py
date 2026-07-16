"""
pages/simulador_operacional.py — Pagina 1: Simulador Operacional (ruta default "/")

Extraido de app.py. Se registra sobre la instancia `app` vía
`register_simulador_callbacks(app)`, llamado desde app.py despues de crear
`app = dash.Dash(...)`.
"""

import numpy as np
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output, State, ctx

from engine.simulator import simulate_scenario_cached
from engine.ode_model import compute_chancado_cap, P90
from engine.optimizer_v3 import find_optimal_v3
from engine.optimizer_v4 import find_optimal_v4
from engine.explicabilidad import explain_recommendation
from engine.optimizer_v2 import format_top5_records, BOLA1_OPTS_FULL, BOLA2_OPTS_FULL
from engine.realtime_loader import load_current_state
from engine.scheduler import (
    TURNO_START_HOUR, equipos_en_mantencion, bola_opts_restringidas,
    sag_forzado_off, hour_of_day_ticks, r16_conflicto_mantencion,
)
from components.controls import build_sidebar, build_feedback_panel
from components.graphs import (
    make_pile_chart, make_tph_chart, make_autonomia_chart,
    make_bola_timeline_chart, make_chancado_cv_chart, make_t1_t3_balance_chart,
    make_sensitivity_chart, make_mc_chart, make_mc_fan_chart, make_hourly_risk_chart,
    make_pareto_scatter, make_bola_impact_chart, make_risk_chart,
    make_gantt_operacional, make_bottleneck_map_chart, make_turno_planificador_table,
    make_pam_projection_chart,
)
from engine.bottleneck import full_bottleneck_map
from engine.harmony_index import compute_harmony_index
from engine.variability_metrics import compute_tph_variability
from engine.turno_planner import build_hourly_schedule
from components.cards import (
    make_kpi_column, make_exec_summary_bar, make_compact_compare_table, make_top5_card,
    make_mc_confidence_card, make_estado_escenario_card, make_bottleneck_card,
    make_pam_compliance_card, make_router_v2_card,
    make_cockpit_row, make_pam_probability_card, REGIMEN_LABEL_JDS,
    make_balance_neto_card, make_harmony_card,
)
from engine.production_stats import pam_compliance_stats, get_pam_monthly_projection
from engine.simulation_router import route_and_simulate
from engine.bottleneck import detect_bottleneck
from engine.balance_diagnostics import compute_recovery_time
from engine.quick_wins import evaluate_quick_wins
from engine.rate_recommendation import rank_candidates
from components.graphs import make_master_pile_chart, make_qin_qout_chart
from components.cards import (
    make_estado_general_card, make_autonomia_resumen_card, make_recomendacion_corta_table,
    make_recuperacion_card, make_quick_win_card, make_scenario_compare_table,
    build_initial_kpi_cards,
)
from components.graphs import build_empty_simulation_figure, apply_circuit_filter
from components.navigation import (
    build_section_nav, build_back_to_top_button, build_back_to_chart_link,
    build_circuit_selector, build_chart_category_selector,
    CHART_TABS, CHART_CATEGORIES, CHART_CATEGORY_DEFAULT,
    SECTION_SUMMARY, SECTION_STOCKPILES, SECTION_CHARTS,
    SECTION_CONTROLS, SECTION_DIAGNOSTICS,
)
from components.cards import (
    make_decision_banner, build_initial_decision_banner, make_confianza_card,
    RESTRICTION_REASON_LABEL_JDS, METODO_LABEL_JDS,
)

_MANT_IDS = ["sag1", "sag2", "411", "412", "511", "512",
             "ch1", "ch2", "cv315", "cv316", "t1", "t3"]
_MANT_EQUIPO = {
    "sag1": "SAG1", "sag2": "SAG2", "411": "411", "412": "412", "511": "511", "512": "512",
    "ch1": "CH1", "ch2": "CH2", "cv315": "CV315", "cv316": "CV316", "t1": "T1", "t3": "T3",
}


def _build_maint_windows(mant_values: dict) -> dict:
    """mant_values: {'sag1': [ini, fin], ...} desde los RangeSlider ctrl-mant-*.
    [0, 0] o None se interpreta como 'sin mantencion'."""
    windows = {}
    for mid, equipo in _MANT_EQUIPO.items():
        val = mant_values.get(mid)
        if not val or len(val) != 2 or val[0] == val[1]:
            windows[equipo] = None
        else:
            windows[equipo] = (float(val[0]), float(val[1]))
    return windows


def _forzar_equipos_por_mantencion(en_mant: set, ch1_on: bool, ch2_on: bool,
                                    c315: str, c316: str, t1_manual: float):
    """Restriccion dura: un equipo en mantencion al inicio del horizonte
    queda forzado a su estado apagado/inactivo para toda la corrida (mismo
    patron estatico ya usado para SAG1/SAG2 via sag_forzado_off)."""
    if "CH1" in en_mant:
        ch1_on = False
    if "CH2" in en_mant:
        ch2_on = False
    if "CV315" in en_mant:
        c315 = "inactiva"
    if "CV316" in en_mant:
        c316 = "inactiva"
    if "T1" in en_mant or "T3" in en_mant:
        t1_manual = 0.0
    return ch1_on, ch2_on, c315, c316, t1_manual

# Paleta TDA (2026-07-07) — ver components/graphs.py para la nota
# completa del origen (wireframe SVG del template, unica parte legible).
AZUL     = "#F0F4FA"
AZUL_MED = "#4FB0E5"
VERDE    = "#4FCE82"
NARANJA  = "#E8935A"
ROJO     = "#E94A4A"
AMARILLO = "#E5BB3E"
BG_CARD_DARK = "#0F2647"
BORDE_CARD_DARK = "#1a3a6c"
TEXTO_MUTED = "#8896AF"

def _sensitivity_explanation(rate1_tph: float, rate2_tph: float, duracion_t8: float,
                              current_metrics: dict) -> "html.Div":
    """Explica, con evidencia operacional (P90 historico, brecha, eventos),
    por que las tasas configuradas de SAG1/SAG2 son o no la mejor opcion."""
    from engine.optimizer_v3 import compute_brecha, get_regime_v3, SAG1_P90, SAG1_HIGH_EVENTS, SAG2_P90

    regime_key, regime = get_regime_v3(duracion_t8)
    eval_h = duracion_t8 if duracion_t8 > 0 else 24.0
    brecha1 = compute_brecha(rate1_tph, rate2_tph, eval_h)
    pct1 = brecha1["pct_p90"]
    pct2 = rate2_tph / SAG2_P90 * 100.0

    if regime_key == "normal":
        if brecha1["zona"] == "optima":
            sag1_txt = (
                f"SAG1 operando en zona optima ({rate1_tph:.0f} TPH = {pct1:.0f}% de P90 historico). "
                "Sin T8 activo, el CV315 alimenta sin interrupcion."
            )
        else:
            sag1_txt = (
                f"SAG1 operando a {rate1_tph:.0f} TPH ({pct1:.0f}% de P90 historico={SAG1_P90:.0f} TPH). "
                f"Brecha: {brecha1['brecha_tph_sag1']:.0f} TPH = {brecha1['brecha_ton_dia']:.0f} t/dia no capturadas. "
                "Sin T8 activo, el CV315 alimenta sin interrupcion: subir a P90 es viable. "
                f"Evidencia: {SAG1_HIGH_EVENTS} eventos historicos de operacion sostenida a esta tasa."
            )
    else:
        min_a1 = regime["min_auton"]["SAG1"]
        a1_min = current_metrics["a1_min"]
        margen_txt = ("dentro del margen minimo" if a1_min >= min_a1
                      else "bajo el margen minimo — riesgo de inventario")
        sag1_txt = (
            f"T8 de {duracion_t8:.0f}h activo: SAG1 a {rate1_tph:.0f} TPH, autonomia minima {a1_min:.1f}h "
            f"(minimo requerido {min_a1:.1f}h) — {margen_txt}. "
            f"Brecha vs P90: {brecha1['brecha_tph_sag1']:.0f} TPH = {brecha1['brecha_ton_dia']:.0f} t/dia."
        )

    if pct2 >= 97:
        sag2_txt = (
            f"SAG2 operando en zona optima ({rate2_tph:.0f} TPH = {pct2:.0f}% de P90 historico={SAG2_P90:.0f} TPH)."
        )
    else:
        brecha2_tph = max(SAG2_P90 - rate2_tph, 0.0)
        brecha2_ton = brecha2_tph * eval_h
        sag2_txt = (
            f"SAG2 operando a {rate2_tph:.0f} TPH ({pct2:.0f}% de P90 historico={SAG2_P90:.0f} TPH). "
            f"Brecha: {brecha2_tph:.0f} TPH = {brecha2_ton:.0f} t/dia no capturadas."
        )

    return html.Div([
        html.Div(sag1_txt, style={"marginBottom": "3px"}),
        html.Div(sag2_txt),
    ])


# ── Helpers ───────────────────────────────────────────────────────────────────
def _bola_label_short(config_value: str, sag: str) -> str:
    if config_value == "sin_bola":
        return "Sin bola"
    if sag == "SAG1":
        return "B411+412" if "ambas" in config_value else config_value.replace("_", " ")
    return "B511+512" if "ambas" in config_value else config_value.replace("_", " ")


def _build_mc_explanation(best: dict, mc_results: list[dict], duracion_t8: float) -> list[str]:
    lines = []

    validation_answer = best.get("validation_answer")
    if validation_answer:
        lines.append(validation_answer)

    r1 = float(best.get("r1", 0.0))
    b1 = best.get("b1", "sin_bola")
    best_tph = float(best.get("tph_mean", 0.0))
    best_safe = float(best.get("p_safe", 0.0)) * 100.0
    inv_sag1 = float(best.get("inv_sag1_final", 0.0))
    a1_med = float(best.get("a1_med", best.get("a1_min", 0.0)))

    alt_more_aggressive = next(
        (
            r for r in mc_results
            if float(r.get("r1", 0.0)) > r1 or r.get("b1") != b1
        ),
        None,
    )
    if alt_more_aggressive is not None:
        alt_tph = float(alt_more_aggressive.get("tph_mean", 0.0))
        alt_safe = float(alt_more_aggressive.get("p_safe", 0.0)) * 100.0
        delta_safe = best_safe - alt_safe
        delta_tph = alt_tph - best_tph
        if delta_safe > 0.5:
            lines.append(
                "Queda #1 porque, frente a alternativas mas agresivas en SAG1, "
                f"sostiene {delta_safe:.0f} pp adicionales de P(seguro) "
                f"con una diferencia de {abs(delta_tph):.0f} TPH en tonelaje esperado."
            )

    if b1 == "sin_bola":
        sag1_bolas = [r for r in mc_results if r.get("b1") != "sin_bola"]
        if sag1_bolas:
            best_with_bolas = max(sag1_bolas, key=lambda r: float(r.get("p_safe", 0.0)))
            safe_with_bolas = float(best_with_bolas.get("p_safe", 0.0)) * 100.0
            inv_with_bolas = float(best_with_bolas.get("inv_sag1_final", inv_sag1))
            lines.append(
                "La restriccion dominante sigue siendo la pila SAG1: con este inventario, "
                "activar bolas en SAG1 acelera el drenaje y obliga a castigar el circuito. "
                f"Por eso el optimo deja SAG1 {_bola_label_short(b1, 'SAG1')} y carga la produccion en SAG2; "
                f"las variantes con bolas dejan SAG1 en {inv_with_bolas:.1f}% final "
                f"y P(seguro) en {safe_with_bolas:.0f}%."
            )
        else:
            lines.append(
                "La restriccion dominante sigue siendo la pila SAG1: con este inventario, "
                "activar bolas en SAG1 aumenta el consumo de pila y reduce el margen de seguridad, "
                "por eso el optimo protege SAG1 y carga la produccion en SAG2."
            )

    if duracion_t8 > 0 and inv_sag1 <= 25:
        lines.append(
            f"SAG1 termina con {inv_sag1:.1f}% y autonomia media {a1_med:.1f}h, "
            "muy cerca de la zona donde el modelo endurece la proteccion de inventario; "
            "esa es la razon principal de la restriccion de rate en SAG1."
        )

    return lines[:3]


def _clone_figure(fig, height: int) -> go.Figure:
    cloned = go.Figure(fig)
    cloned.update_layout(height=height)
    return cloned


def _mc_frontier_or_placeholder(mc_best_cached):
    """Figura para la pestana '¿Que tan confiable es esta recomendacion?' de
    Vista principal.

    `store-mc-results` guarda el candidato ganador (`best`) de la ultima
    corrida de `run_monte_carlo`, que ahora se dispara automaticamente al
    cambiar cualquier parametro relevante del escenario (ya no solo al
    apretar el boton). Si todavia no se ha corrido nada, muestra un mensaje.
    """
    if mc_best_cached:
        try:
            return make_mc_fan_chart(mc_best_cached)
        except Exception:
            pass
    fig = go.Figure()
    fig.add_annotation(
        text=("Aun no hay resultados Monte Carlo en esta sesion.<br>"
              "Apreta <b>'Simular Monte Carlo'</b> en 'Ver detalles tecnicos' "
              "para calcular la frontera de robustez."),
        showarrow=False, font=dict(size=13, color="#888"),
        xref="paper", yref="paper", x=0.5, y=0.5,
    )
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        paper_bgcolor=BG_CARD_DARK, plot_bgcolor=BG_CARD_DARK,
    )
    return fig


def _parse_rate_band_midpoint(rate_band: str, asset: str, fallback_tph: float) -> float:
    try:
        lo_txt, hi_txt = rate_band.replace("%", "").split("-")
        lo = float(lo_txt)
        hi = float(hi_txt)
        return P90[asset] * ((lo + hi) / 2.0) / 100.0
    except Exception:
        return float(fallback_tph)


def _recommended_bola_cfg(asset: str, n_bolas: int, current_cfg: str, alerta: bool) -> str:
    if not alerta:
        return current_cfg
    if n_bolas <= 0:
        return "sin_bola"
    if asset == "SAG1":
        return "solo_411" if n_bolas == 1 else "ambas_411_412"
    return "solo_511" if n_bolas == 1 else "ambas_511_512"


def _extract_eval_metrics(sim: dict, eval_h: float) -> dict:
    time_arr = np.array(sim["time"])
    idx = min(int(np.searchsorted(time_arr, float(eval_h))), len(time_arr) - 1)
    sl = slice(0, idx + 1)

    pile1_arr = np.array(sim["pile_sag1"])
    pile2_arr = np.array(sim["pile_sag2"])
    tph_total = np.array(sim["tph_total"])
    tph1_arr = np.array(sim.get("tph_sag1", [0] * len(time_arr)))
    tph2_arr = np.array(sim.get("tph_sag2", [0] * len(time_arr)))
    a1 = np.array(sim["autonomia_sag1"])
    a2 = np.array(sim["autonomia_sag2"])
    risk1 = np.array(sim.get("riesgo_sag1", [0] * len(time_arr)))
    risk2 = np.array(sim.get("riesgo_sag2", [0] * len(time_arr)))

    tph_mean = float(tph_total[sl].mean())
    tons = tph_mean * float(eval_h)
    pile1_min = float(pile1_arr[sl].min())
    pile2_min = float(pile2_arr[sl].min())

    return {
        "tph_total": tph_mean,
        "tph1_mean": float(tph1_arr[sl].mean()),
        "tph2_mean": float(tph2_arr[sl].mean()),
        "tons": tons,
        "a1_min": float(a1[sl].min()),
        "a2_min": float(a2[sl].min()),
        "pile1_end": float(pile1_arr[idx]),
        "pile2_end": float(pile2_arr[idx]),
        "pile1_min": pile1_min,
        "pile2_min": pile2_min,
        "max_risk": int(max(risk1[sl].max(), risk2[sl].max())),
        "survives": (pile1_min >= 15.0) and (pile2_min >= 18.2),
    }


def _action_summary(action: str, survives: bool, max_risk: int) -> tuple[str, str]:
    if not survives or action in {"EMERGENCIA", "EVALUAR_DETENCION", "MINIMO_TECNICO"}:
        return "Emergencia", "danger"
    if action in {"REDUCIR_CARGA", "CONSERVADOR"} or max_risk >= 2:
        return "Reducir carga", "orange"
    if action == "MONITOREAR" or max_risk == 1:
        return "Monitorear", "warning"
    return "Operacion segura", "success"


def _fmt_delta(actual: float, recommended: float, unit: str, decimals: int = 0, inverse_good: bool = False) -> tuple[str, str]:
    delta = float(recommended) - float(actual)
    sign = "+" if delta > 0 else ""
    fmt = f"{{:{sign}.{decimals}f}}"
    delta_txt = fmt.format(delta)
    # CAMBIO 4 (UX/UI v2 JdS, 2026-07-07): Verde=mejora, Rojo=empeora, Amarillo=neutro.
    color = VERDE if ((delta < 0) if inverse_good else (delta > 0)) else (ROJO if delta != 0 else AMARILLO)
    return f"{delta_txt} {unit}".strip(), color


def _find_optimal_params(
    pila1: float, pila2: float, duracion_t8: float,
    sag1_on: bool, sag2_on: bool,
    ch1_on: bool, ch2_on: bool,
    c315: str, c316: str,
    t1_mode: str, t1_manual: float,
    t3_frac: float, distribucion_t1: str,
    horizonte: float = 24,
    bola1_opts: list | None = None,
    bola2_opts: list | None = None,
    tolerancia_riesgo: str = "balanceado",
):
    """Wrapper sobre optimizer_v3.find_optimal_v3 — mantiene interfaz legacy.

    Ademas re-rankea con Optimizer V4 (engine/optimizer_v4.py) usando la
    tolerancia de riesgo seleccionada — re-ranking puro sobre el Top-20 ya
    evaluado por V3, sin recalcular nada. Si V4 recomienda un split
    distinto (prioriza SAG2, mas estable segun CV real medido), queda
    disponible en el dict de stats para mostrarlo en la UI."""
    best, all_results = find_optimal_v3(
        pila1=pila1, pila2=pila2, duracion_t8=duracion_t8,
        sag1_on=sag1_on, sag2_on=sag2_on,
        ch1_on=ch1_on, ch2_on=ch2_on,
        c315=c315, c316=c316,
        t1_mode=t1_mode, t1_manual=t1_manual,
        t3_frac=t3_frac, distribucion_t1=distribucion_t1,
        horizonte=horizonte,
        mode="balanced",
        bola1_opts=bola1_opts, bola2_opts=bola2_opts,
    )
    best_v4 = find_optimal_v4(all_results, tolerancia=tolerancia_riesgo)
    v4_diverge = bool(best_v4) and (best_v4.get("r1") != best["r1"] or best_v4.get("r2") != best["r2"])

    exp_sag1 = explain_recommendation(best, pila1, pila2, duracion_t8, asset="SAG1")
    exp_sag2 = explain_recommendation(best, pila1, pila2, duracion_t8, asset="SAG2")

    brecha = best.get("brecha_p90", {})
    return (best["r1"], best["b1"], best["r2"], best["b2"]), {
        "tph":           best.get("tph_mean", 0),
        "a1":            best.get("a1_med", 0),
        "a2":            best.get("a2_med", 0),
        "iro":           0,
        "safe":          best.get("p_safe", 0) >= 0.5,
        "p_safe":        best.get("p_safe", 0),
        "regime":        best.get("regime", ""),
        "brecha_tph":    brecha.get("brecha_tph_sag1", 0),
        "brecha_ton":    brecha.get("brecha_ton_dia", 0),
        "zona":          brecha.get("zona", ""),
        "n_sim":         best.get("n_samples_used", 0),
        "converged":     best.get("converged", False),
        "v4_diverge":    v4_diverge,
        "v4_r1":         best_v4.get("r1") if v4_diverge else None,
        "v4_r2":         best_v4.get("r2") if v4_diverge else None,
        "explicabilidad_sag1": exp_sag1,
        "explicabilidad_sag2": exp_sag2,
    }


# ── Layout ────────────────────────────────────────────────────────────────────
def page_simulador_operacional():
    # Rediseño JdS (2026-07-13, ver 04_Reports/Technical/
    # 20260713_Rediseno_Autonomia_Pilas_JDS.md): la vista principal se
    # reduce a 6 bloques fijos + 1 grafico dominante, respondibles en <10s.
    # Todo lo que antes vivia siempre visible (10 vistas de grafico, tabs
    # secundarias, sensibilidad, Monte Carlo, top5) se mueve dentro de
    # "Ver detalle tecnico" — NO se elimina, sigue intacto para quien lo
    # necesite.
    # Fase 3 (2026-07-14, ver 04_Reports/Technical/
    # 20260714_Persistencia_Estado_Obsoleto.md): los 6 bloques y el
    # grafico principal NUNCA se construyen vacios/implicitos — su
    # contenido inicial "idle" existe desde el primer render, antes de
    # que cualquier callback corra. Esto es lo que evita que un estado
    # persistido invalido (o simplemente la ventana entre el primer
    # paint y la respuesta del callback) se vea como "grafico roto".
    _initial = build_initial_kpi_cards()

    return html.Div([
        build_section_nav(),

        html.Div([
            # Segunda iteración UX/UI (2026-07-14, Fase 2 del pedido): bloque
            # de decisión principal — UNA sola conclusión operacional antes
            # de cualquier otra tarjeta, para responder estado→riesgo→acción
            # en <10s sin leer el resto de la página.
            dcc.Loading(html.Div(id="div-decision-banner", children=build_initial_decision_banner()),
                        type="dot", color=AZUL_MED),

            html.Div(id="sim-summary-bar", className="mb-1 mt-2"),

            # Cockpit Inventario | Produccion | Riesgo | PAM (CAMBIO 5, UX/UI v2
            # JdS 2026-07-07) — restaurado 2026-07-14: se habia quitado por error
            # de la vista principal al reestructurar el layout en 6 bloques, pero
            # update_simulation sigue escribiendo Output("kpi-column","children")
            # (kpis = make_cockpit_row(kpi_groups)) — sin este Div, Dash lanza
            # "A nonexistent object was used in an Output".
            dbc.Card(
                dbc.CardBody(
                    dcc.Loading(html.Div(id="kpi-column"), type="dot", color=AZUL_MED),
                    style={"padding": "8px 10px"},
                ),
                className="sim-cockpit-card mb-2",
                style={"backgroundColor": BG_CARD_DARK, "border": f"1px solid {BORDE_CARD_DARK}", "borderRadius": "10px"},
            ),
        ], id=SECTION_SUMMARY, className="dashboard-section"),

        # Segunda iteración UX/UI (2026-07-14, Fase 2-3 del pedido): el
        # bloque "Estado general" ahora vive en el Decision Banner de
        # arriba (más completo) — se retira de la grilla para no repetir
        # la misma conclusión dos veces, pero el Div/Output NO se borra
        # (queda oculto, display:none) para no reproducir el bug ya
        # corregido esta sesión de "A nonexistent object was used in an
        # Output" si algún consumidor externo aún lo esperara. Grilla
        # agrupada por circuito: SAG1 | SAG2 | Recomendación en la fila 1,
        # Recuperación | Quick win | Confianza en la fila 2.
        html.Div([
            html.Div(id="div-estado-general", children=_initial["div-estado-general"],
                      style={"display": "none"}),
            dbc.Row([
                dbc.Col(dcc.Loading(html.Div(id="div-autonomia-sag1", children=_initial["div-autonomia-sag1"]),
                                    type="dot", color=AZUL_MED), xs=12, md=6, lg=4, className="mb-2"),
                dbc.Col(dcc.Loading(html.Div(id="div-autonomia-sag2", children=_initial["div-autonomia-sag2"]),
                                    type="dot", color=AZUL_MED), xs=12, md=6, lg=4, className="mb-2"),
                dbc.Col(dcc.Loading(html.Div(id="div-recomendacion-corta", children=_initial["div-recomendacion-corta"]),
                                    type="dot", color=AZUL_MED), xs=12, md=6, lg=4, className="mb-2"),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dcc.Loading(html.Div(id="div-recuperacion", children=_initial["div-recuperacion"]),
                                    type="dot", color=AZUL_MED), xs=12, md=6, lg=4, className="mb-2"),
                dbc.Col(dcc.Loading(html.Div(id="div-quick-win", children=_initial["div-quick-win"]),
                                    type="dot", color=AZUL_MED), xs=12, md=6, lg=4, className="mb-2"),
                dbc.Col(dcc.Loading(html.Div(id="div-confianza-card", children=make_confianza_card("BAJA", "—")),
                                    type="dot", color=AZUL_MED), xs=12, md=6, lg=4, className="mb-2"),
            ], className="mb-2"),
        ], id=SECTION_STOCKPILES, className="dashboard-section"),

        # ── Grafico principal unico (seccion 7): evolucion de pilas ──────
        # Rediseno navegacion (2026-07-14, ver 04_Reports/Technical/
        # 20260714_Rediseno_Navegacion_UX_Simulador.md): el selector de
        # vista (sim-main-view) y los botones expandir/reset vivian en el
        # Accordion "Ver detalle tecnico", ~2 pantallas mas abajo que este
        # grafico (confirmado visualmente en graficos y botones.pdf,
        # paginas 3 vs 5) — obligaba a seleccionar abajo y volver a
        # scrollear arriba para ver el resultado. Se movieron aca, mismos
        # ids, mismo callback (update_simulation, que sigue leyendo el
        # valor de sim-main-view como antes), cero cambio de logica fisica.
        html.Div([
        dbc.Card(
            dbc.CardBody([
                html.Div([
                    html.Div("Análisis gráfico", className="section-header",
                             style={"marginBottom": "6px"}),
                    # Segunda iteración UX/UI (2026-07-14, Fase 5 sec.11):
                    # categorías por encima de las 10 vistas planas, para
                    # que sim-main-view no muestre las 10 opciones
                    # simultáneas en pantallas chicas.
                    build_chart_category_selector(),
                    dbc.RadioItems(
                        id="sim-main-view",
                        options=CHART_TABS,
                        value="pilas",
                        inline=True,
                        className="sim-chart-tabs",
                        inputStyle={"marginRight": "4px"},
                        labelStyle={"fontSize": "0.76rem", "marginRight": "12px"},
                    ),
                    html.Div([
                        dbc.Button("Expandir gráfico", id="btn-expand-main", size="sm",
                                   color="primary", outline=True, className="me-2",
                                   style={"fontSize": "0.72rem"}),
                        dbc.Button("Reiniciar zoom", id="btn-reset-zoom", size="sm",
                                   color="secondary", outline=True, style={"fontSize": "0.72rem"}),
                    ], className="mt-2 mb-2"),
                    html.Div([
                        html.Span("Circuito: ", style={"fontSize": "0.74rem", "color": TEXTO_MUTED,
                                                        "marginRight": "6px"}),
                        build_circuit_selector(),
                    ], className="mb-2"),
                ]),
                dcc.Loading(
                    dcc.Graph(
                        id="graph-main",
                        figure=build_empty_simulation_figure(),
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
                                "displaylogo": False},
                        className="sim-main-graph",
                    ),
                    type="circle", color=AZUL_MED,
                ),
                html.Div(id="div-main-view-explanation",
                         style={"fontSize": "0.72rem", "color": TEXTO_MUTED, "padding": "4px 6px 0"}),
                dbc.Button(
                    "VER POR QUÉ CRECE O DRENA  ▾", id="btn-toggle-qin-qout", size="sm", color="light",
                    # 2026-07-14: mismo fix de contraste que btn-toggle-sensitivity/btn-toggle-mc.
                    style={"fontSize": "0.72rem", "marginTop": "6px", "border": f"1px solid {AZUL_MED}",
                           "color": AZUL_MED, "fontWeight": "600", "backgroundColor": BG_CARD_DARK},
                ),
                dbc.Collapse(
                    dcc.Graph(id="graph-qin-qout", figure=build_empty_simulation_figure("Sin datos aún"),
                              config={"displayModeBar": False}),
                    id="collapse-qin-qout", is_open=False,
                ),
            ], style={"padding": "12px"}),
            className="sim-main-card mb-2",
        ),

        # ── Seccion 9 — Comparar escenarios (Actual/Recomendado/Alternativo) ──
        dcc.Loading(html.Div(id="div-scenario-compare", children=_initial["div-scenario-compare"]),
                    type="dot", color=AZUL_MED),

        build_feedback_panel(),
        ], id=SECTION_CHARTS, className="dashboard-section"),

        dbc.Row([
            dbc.Col([
                build_sidebar(),
            ], xs=12, lg=4, xl=3, className="mb-3 mb-xl-0", id=SECTION_CONTROLS),
            dbc.Col([
                build_back_to_chart_link(),
                dbc.Accordion(
                    [
                        dbc.AccordionItem(
                            html.Div([
                                html.Div(id="sim-compare-block", className="mb-2"),
                                # 2026-07-14 (auditoria de contraste sobre captura real de la
                                # app): estos 8 dcc.Graph secundarios no traian `figure=` inicial
                                # — Dash los renderiza con la figura vacia por defecto de Plotly
                                # (ejes con rango arbitrario, sin ningun aviso), exactamente el
                                # problema que build_empty_simulation_figure ya resuelve para
                                # graph-main/graph-qin-qout pero no se habia extendido aca.
                                dbc.Tabs([
                                    dbc.Tab(dcc.Graph(id="graph-gantt-operacional",
                                                       figure=build_empty_simulation_figure(
                                                           "Ejecuta una simulación para ver la disponibilidad de equipos"),
                                                       config={"displayModeBar": False}),
                                            label="Disponibilidad de equipos", tab_id="tab-gantt"),
                                    dbc.Tab(dcc.Graph(id="graph-autonomia",
                                                       figure=build_empty_simulation_figure(
                                                           "Ejecuta una simulación para ver la autonomía"),
                                                       config={"displayModeBar": False}), label="Autonomia"),
                                    dbc.Tab(dcc.Graph(id="graph-chancado",
                                                       figure=build_empty_simulation_figure(
                                                           "Ejecuta una simulación para ver la alimentación"),
                                                       config={"displayModeBar": False}), label="Alimentacion"),
                                    dbc.Tab(dcc.Graph(id="graph-bolas",
                                                       figure=build_empty_simulation_figure(
                                                           "Ejecuta una simulación para ver los molinos de bolas"),
                                                       config={"displayModeBar": False}), label="Molinos de bolas"),
                                ], active_tab="tab-gantt", className="sim-secondary-tabs mb-3"),
                                dbc.Button(
                                    "Sensibilidad: Rate -> Autonomia  ▾",
                                    id="btn-toggle-sensitivity",
                                    size="sm",
                                    color="light",
                                    # 2026-07-14 (auditoria de contraste sobre captura real de la
                                    # app): color="light" trae el fondo gris/blanco por defecto de
                                    # Bootstrap, no cubierto por --bs-accordion-* — combinado con
                                    # texto claro (AZUL_MED) quedaba casi ilegible. Se fija el fondo
                                    # explicitamente al panel oscuro del tema.
                                    style={"fontSize": "0.78rem", "width": "100%",
                                           "textAlign": "left", "border": f"1px solid {AZUL_MED}",
                                           "color": AZUL_MED, "fontWeight": "600",
                                           "backgroundColor": BG_CARD_DARK},
                                ),
                                dbc.Collapse(
                                    html.Div([
                                        dcc.Graph(id="graph-sensitivity",
                                                  figure=build_empty_simulation_figure(
                                                      "Ejecuta una simulación para ver la sensibilidad Rate → Autonomía"),
                                                  config={"displayModeBar": False}),
                                        html.Div(
                                            id="div-sensitivity-explanation",
                                            style={"fontSize": "0.72rem", "color": TEXTO_MUTED,
                                                   "padding": "4px 6px 2px"},
                                        ),
                                    ]),
                                    id="collapse-sensitivity",
                                    is_open=False,
                                ),
                                html.Hr(style={"margin": "8px 0"}),
                                dbc.Button(
                                    "¿Qué tan confiable es esta recomendación?  ▴",
                                    id="btn-toggle-mc",
                                    size="sm",
                                    color="light",
                                    # 2026-07-14: mismo fix de contraste que btn-toggle-sensitivity.
                                    style={"fontSize": "0.78rem", "width": "100%",
                                           "textAlign": "left", "border": f"1px solid {AZUL}",
                                           "color": AZUL, "fontWeight": "600",
                                           "backgroundColor": BG_CARD_DARK},
                                ),
                                dbc.Collapse(
                                    dcc.Loading(
                                        [
                                            dcc.Graph(id="graph-mc",
                                                      figure=build_empty_simulation_figure(
                                                          "Ejecuta 'Monte Carlo' para ver la confiabilidad de la recomendación"),
                                                      config={"displayModeBar": False}),
                                            html.Div(id="div-mc-confidence"),
                                            html.Div(id="div-mc-summary", style={"fontSize": "0.78rem", "padding": "6px 8px"}),
                                            dcc.Graph(id="graph-hourly-risk",
                                                      figure=build_empty_simulation_figure(
                                                          "Ejecuta 'Monte Carlo' para ver el riesgo por hora"),
                                                      config={"displayModeBar": False}),
                                            dcc.Graph(id="graph-pareto",
                                                      figure=build_empty_simulation_figure(
                                                          "Ejecuta 'Monte Carlo' para ver las configuraciones Pareto"),
                                                      config={"displayModeBar": False}),
                                            html.Div(id="div-top5-mc", style={"padding": "4px 0"}),
                                        ],
                                        type="circle",
                                        color=AZUL_MED,
                                    ),
                                    id="collapse-mc",
                                    is_open=True,
                                ),
                            ]),
                            title="Ver detalle técnico",
                            item_id="sim-detail-tech",
                        ),
                    ],
                    start_collapsed=True,
                    active_item=None,
                    always_open=True,
                    className="sim-detail-accordion",
                ),
            ], xs=12, lg=8, xl=9, id=SECTION_DIAGNOSTICS),
        ]),

        build_back_to_top_button(),
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Vista principal ampliada"), close_button=False),
                dbc.ModalBody(
                    dcc.Graph(
                        id="graph-main-modal",
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                                "displaylogo": False},
                    )
                ),
                dbc.ModalFooter(
                    dbc.Button("Cerrar", id="btn-close-main-modal", color="secondary", outline=True)
                ),
            ],
            id="main-graph-modal",
            is_open=False,
            size="xl",
            centered=True,
            scrollable=True,
        ),
    ])


# ── Callbacks ─────────────────────────────────────────────────────────────────
def register_simulador_callbacks(app):

    # Backlog #4 (UX/UI v2 JdS, 2026-07-07): al abrir el ejecutable,
    # precargar el ultimo escenario simulado (en vez de partir siempre de
    # los defaults 55%/55%/sin T8) y mostrar hace cuanto tiempo fue. Se
    # dispara una sola vez al cargar la pagina (Input sobre "url.pathname",
    # que existe en app.py::serve_layout). allow_duplicate=True porque
    # estos mismos controles ya tienen Output en otros callbacks
    # (Optimo segun pila / Monte Carlo / Cargar PI) — prevent_initial_call
    # "initial_duplicate" es la unica combinacion que permite ambas cosas
    # a la vez (duplicado + disparo en la carga inicial).
    @app.callback(
        Output("ctrl-pila-sag1",   "value", allow_duplicate=True),
        Output("ctrl-pila-sag2",   "value", allow_duplicate=True),
        Output("ctrl-duracion-t8", "value", allow_duplicate=True),
        Output("ctrl-rate-sag1",   "value", allow_duplicate=True),
        Output("ctrl-rate-sag2",   "value", allow_duplicate=True),
        Output("ctrl-bolas-sag1",  "value", allow_duplicate=True),
        Output("ctrl-bolas-sag2",  "value", allow_duplicate=True),
        Output("ctrl-turno",       "value", allow_duplicate=True),
        Output("div-ultima-simulacion", "children"),
        Output("header-ultima-simulacion", "children"),
        Input("url", "pathname"),
        prevent_initial_call="initial_duplicate",
    )
    def precargar_ultimo_escenario(_pathname):
        from dash import no_update
        from utils.scenario_state import load_last_scenario
        from components.cards import REGIMEN_LABEL_JDS

        # Bug real (2026-07-09, reportado por el usuario en vivo): este
        # callback dispara con Input("url","pathname"), que cambia en
        # CUALQUIER navegacion, no solo en la carga inicial. Los primeros
        # 8 Output son componentes del sidebar del simulador (ctrl-*) que
        # no existen en el layout de otras paginas (/analisis, /riesgo,
        # /desempeno_gemelo, /performance) — navegar ahi disparaba
        # "A nonexistent object was used in an Output". Se restringe a
        # la pagina del simulador (pathname "/" o vacio/None).
        if _pathname not in (None, "", "/"):
            return (no_update,) * 10

        ultimo = load_last_scenario()
        if not ultimo:
            msg = "Primera vez que se abre — sin escenario previo."
            return (no_update,) * 8 + (msg, "· Última simulación: —")

        horas = ultimo.get("horas_desde", 0.0)
        tiempo_txt = f"{horas*60:.0f} min" if horas < 1 else f"{horas:.1f} h"
        regimen_txt = REGIMEN_LABEL_JDS.get(ultimo.get("regimen_activo"), ultimo.get("regimen_activo", "—"))
        msg = f"Última simulación: hace {tiempo_txt} — {regimen_txt}"
        header_msg = f"· Última simulación: hace {tiempo_txt}"

        return (
            ultimo.get("pila1", 55), ultimo.get("pila2", 55), ultimo.get("duracion_t8", 0),
            ultimo.get("rate1_tph", 1236), ultimo.get("rate2_tph", 2214),
            ultimo.get("bolas_sag1", "solo_411"), ultimo.get("bolas_sag2", "solo_511"),
            ultimo.get("turno", "A"), msg, header_msg,
        )

    # CAMBIO 6 (UX/UI v2 JdS, 2026-07-07): boton "Ver detalle tecnico" de
    # la tarjeta "Confiabilidad de la Recomendacion" — colapsa/expande el
    # detalle tecnico (regimen exacto, ranking de urgencia) que por
    # defecto queda oculto para priorizar la decision sobre el modelo.
    @app.callback(
        Output("collapse-detalle-tecnico-confiabilidad", "is_open"),
        Input("btn-detalle-tecnico-confiabilidad", "n_clicks"),
        State("collapse-detalle-tecnico-confiabilidad", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_detalle_tecnico_confiabilidad(n_clicks, is_open):
        return not is_open

    # Backlog #3 (UX/UI v2 JdS, 2026-07-07): mismo patron para el badge
    # "Optimo segun pila" — la jerga (P(safe), Sim: N, brecha P90, V3/V4)
    # queda oculta hasta click explicito.
    @app.callback(
        Output("collapse-detalle-tecnico-optimo", "is_open"),
        Input("btn-detalle-tecnico-optimo", "n_clicks"),
        State("collapse-detalle-tecnico-optimo", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_detalle_tecnico_optimo(n_clicks, is_open):
        return not is_open

    # Rediseño JdS (2026-07-13): se elimina el toggle Rapido/Avanzado
    # (callback toggle_modo_rapido_avanzado) — el detalle tecnico completo
    # (10 vistas de sim-main-view incluida "Robustez MC", boton Monte
    # Carlo, Optimo segun pila) ahora vive siempre dentro del panel "Ver
    # detalle tecnico" de la vista principal y del AccordionItem
    # "Avanzado" del sidebar (components/controls.py), no detras de un
    # modo. sim-main-view mantiene sus 10 opciones fijas definidas en el
    # layout (page_simulador_operacional), sin necesidad de un callback
    # que las filtre.

    # CAMBIO 3 (UX/UI v2 JdS, 2026-07-07): boton unico "GENERAR RECOMENDACION".
    # El usuario NO elige Monte Carlo/Determinístico/Hibrido — el motor decide
    # segun criticidad del escenario (mismo CriticalityScorer de route_and_
    # simulate, engine/criticality_scorer.py) y encadena los dos botones
    # tecnicos existentes via su propio n_clicks (patron Dash estandar) en
    # vez de duplicar su logica ya validada.
    @app.callback(
        Output("btn-params-ideales", "n_clicks"),
        Output("btn-monte-carlo",    "n_clicks"),
        Output("div-metodo-usado",   "children"),
        Output("store-ultima-recomendacion-id", "data"),
        Input("btn-generar-recomendacion", "n_clicks"),
        State("btn-params-ideales",  "n_clicks"),
        State("btn-monte-carlo",     "n_clicks"),
        State("ctrl-pila-sag1",      "value"),
        State("ctrl-pila-sag2",      "value"),
        State("ctrl-duracion-t8",    "value"),
        State("ctrl-turno",          "value"),
        State("ctrl-mant-sag1", "value"), State("ctrl-mant-sag2", "value"),
        State("ctrl-mant-411",  "value"), State("ctrl-mant-412",  "value"),
        State("ctrl-mant-511",  "value"), State("ctrl-mant-512",  "value"),
        State("ctrl-mant-ch1",  "value"), State("ctrl-mant-ch2",  "value"),
        State("ctrl-mant-cv315","value"), State("ctrl-mant-cv316","value"),
        State("ctrl-mant-t1",   "value"), State("ctrl-mant-t3",   "value"),
        prevent_initial_call=True,
    )
    def generar_recomendacion(
        n_gen, n_ideal, n_mc, pila1, pila2, duracion_t8, turno,
        mant_sag1, mant_sag2, mant_411, mant_412, mant_511, mant_512,
        mant_ch1, mant_ch2, mant_cv315, mant_cv316, mant_t1, mant_t3,
    ):
        from dash import no_update
        from datetime import datetime
        from engine.scenario_inputs import ScenarioInputs
        from engine.criticality_scorer import CriticalityScorer
        from components.cards import METODO_LABEL_JDS

        pila1 = pila1 or 55
        pila2 = pila2 or 55
        duracion_t8 = duracion_t8 or 0
        turno = turno or "A"
        maint_windows = _build_maint_windows({
            "sag1": mant_sag1, "sag2": mant_sag2, "411": mant_411,
            "412": mant_412, "511": mant_511, "512": mant_512,
            "ch1": mant_ch1, "ch2": mant_ch2, "cv315": mant_cv315,
            "cv316": mant_cv316, "t1": mant_t1, "t3": mant_t3,
        })
        now_hour = TURNO_START_HOUR[turno]
        en_mant = list(equipos_en_mantencion(maint_windows, now_hour))

        def _scenario(pila):
            return ScenarioInputs(
                pila_actual_pct=pila, pila_proyectada_pct=pila,
                qin_actual=0.0, qout_actual=0.0,
                t1_disponible=True, cv315_disponible=True, cv316_disponible=True,
                equipos_en_mantencion=en_mant, sag1_disponible=True, sag2_disponible=True,
                mobo1_disponible=True, mobo2_disponible=True,
                t8_activa=duracion_t8 > 0, t8_duracion_h=float(duracion_t8),
                timestamp=datetime.now(),
            )

        criticidades = CriticalityScorer().score(_scenario(pila1), _scenario(pila2))
        top = criticidades[0].regimen
        top_base = top
        for base in ("overflow", "inventario_critico"):
            if top.startswith(base):
                top_base = base

        necesita_mc = top_base != "normal"
        metodo_label = METODO_LABEL_JDS.get(top_base, "Monte Carlo adaptativo")
        metodo_txt = f"Método utilizado: {metodo_label}"

        import uuid
        from utils.state_schema import make_envelope
        rec_id = str(uuid.uuid4())[:8]
        try:
            import getpass
            from utils.usage_logger import log_event
            log_event("recomendacion_generada", regimen_activo=top_base, metodo=metodo_label,
                      usuario=getpass.getuser(), vista_activa="simulador_operacional", rec_id=rec_id)
        except Exception:
            pass

        nuevo_ideal = (n_ideal or 0) + 1
        nuevo_mc = ((n_mc or 0) + 1) if necesita_mc else no_update
        return nuevo_ideal, nuevo_mc, metodo_txt, make_envelope({"rec_id": rec_id})

    # Validacion Operacional Real (Fases 1/2/10, cierre de brechas
    # 2026-07-07): un solo callback para el panel combinado
    # (components/controls.py::build_feedback_panel) — feedback
    # SI/NO/PARCIAL sobre la ultima recomendacion, guardado del caso
    # completo si "Validar escenario real" esta marcado, y el
    # formulario jefe de sala 1-5. Se guarda el caso (si corresponde)
    # en CUALQUIERA de los 4 triggers — puede duplicar un caso si el
    # operador click feedback Y el formulario para la misma
    # recomendacion, tradeoff aceptado por simplicidad (dos registros
    # del mismo escenario no rompe nada, solo es redundante).
    @app.callback(
        Output("div-feedback-confirmacion", "children"),
        Output("div-form-confirmacion",     "children"),
        Input("btn-feedback-si",       "n_clicks"),
        Input("btn-feedback-no",       "n_clicks"),
        Input("btn-feedback-parcial",  "n_clicks"),
        Input("btn-guardar-feedback",  "n_clicks"),
        State("store-ultima-recomendacion-id", "data"),
        State("store-ultimo-snapshot-caso",    "data"),
        State("chk-validar-escenario-real",    "value"),
        State("form-util-value",               "value"),
        State("form-razonable-value",          "value"),
        State("form-decision-distinta-value",  "value"),
        State("form-comentario",               "value"),
        prevent_initial_call=True,
    )
    def registrar_validacion_operacional(
        n_si, n_no, n_parcial, n_form, rec_id, snapshot, validar_vals,
        util_v, razonable_v, decision_v, comentario,
    ):
        from dash import no_update
        from datetime import datetime as _dt
        from utils.state_schema import (
            get_data, RECOMENDACION_ID_DEFAULT, SNAPSHOT_CASO_DEFAULT,
        )

        rec_id = get_data(rec_id, RECOMENDACION_ID_DEFAULT, kind="ultima_recomendacion_id").get("rec_id")
        snapshot = get_data(snapshot, SNAPSHOT_CASO_DEFAULT, kind="ultimo_snapshot_caso") or None

        triggered = ctx.triggered_id
        validar = bool(validar_vals and "validar" in validar_vals)

        case_id = None
        if validar and snapshot:
            try:
                from utils.operational_case_logger import save_operational_case
                from utils.decisions_log import append_decision
                case_id = save_operational_case(snapshot)
                if case_id:
                    append_decision(case_id, _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
                                     snapshot.get("regimen", ""), snapshot.get("recomendacion", ""))
            except Exception:
                pass

        msg_feedback, msg_form = no_update, no_update

        if triggered in ("btn-feedback-si", "btn-feedback-no", "btn-feedback-parcial"):
            aceptada = {"btn-feedback-si": "SI", "btn-feedback-no": "NO",
                        "btn-feedback-parcial": "PARCIAL"}[triggered]
            try:
                import getpass
                from utils.usage_logger import log_event
                log_event("recomendacion_feedback", rec_id=rec_id, recomendacion_aceptada=aceptada,
                           usuario=getpass.getuser())
            except Exception:
                pass
            msg_feedback = f"Feedback registrado: {aceptada}" + (" · caso guardado" if case_id else "")

        if triggered == "btn-guardar-feedback":
            try:
                from validation.feedback_form import append_jefe_sala_feedback
                append_jefe_sala_feedback(case_id, _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
                                           util_v, razonable_v, decision_v, comentario or "")
            except Exception:
                pass
            msg_form = "Formulario guardado" + (" · caso guardado" if case_id else " (sin caso vinculado)")

        return msg_feedback, msg_form

    @app.callback(
        Output("ctrl-rate-sag1",       "value"),
        Output("ctrl-rate-sag2",       "value"),
        Output("ctrl-bolas-sag1",      "value"),
        Output("ctrl-bolas-sag2",      "value"),
        Output("badge-params-ideales", "children"),
        Output("store-recommendation-scenario-hash",   "data"),
        Output("store-recommendation-scenario-params", "data"),
        Output("store-recommendation-contexto",        "data"),
        Input("btn-params-ideales",  "n_clicks"),
        State("ctrl-pila-sag1",      "value"),
        State("ctrl-pila-sag2",      "value"),
        State("ctrl-duracion-t8",    "value"),
        State("ctrl-sag1-on",        "value"),
        State("ctrl-sag2-on",        "value"),
        State("ctrl-ch1",            "value"),
        State("ctrl-ch2",            "value"),
        State("ctrl-correa315",      "value"),
        State("ctrl-correa316",      "value"),
        State("ctrl-t1-mode",        "value"),
        State("ctrl-t1-manual",      "value"),
        State("ctrl-t3-frac",        "value"),
        State("ctrl-distribucion-t1","value"),
        State("ctrl-horizonte",      "value"),
        State("ctrl-turno",          "value"),
        State("ctrl-mant-sag1", "value"), State("ctrl-mant-sag2", "value"),
        State("ctrl-mant-411",  "value"), State("ctrl-mant-412",  "value"),
        State("ctrl-mant-511",  "value"), State("ctrl-mant-512",  "value"),
        State("ctrl-mant-ch1",  "value"), State("ctrl-mant-ch2",  "value"),
        State("ctrl-mant-cv315","value"), State("ctrl-mant-cv316","value"),
        State("ctrl-mant-t1",   "value"), State("ctrl-mant-t3",   "value"),
        State("ctrl-tolerancia-riesgo", "value"),
        State("ctrl-cv-mode",       "value"),
        State("ctrl-cv315-manual",  "value"),
        State("ctrl-cv316-manual",  "value"),
        prevent_initial_call=True,
    )
    def apply_ideal_params(
        n_clicks, pila1, pila2, duracion_t8,
        sag1_on_sw, sag2_on_sw, ch1_vals, ch2_vals,
        c315, c316, t1_mode, t1_manual, t3_frac_pct,
        distribucion_t1, horizonte, turno,
        mant_sag1, mant_sag2, mant_411, mant_412, mant_511, mant_512,
        mant_ch1, mant_ch2, mant_cv315, mant_cv316, mant_t1, mant_t3,
        tolerancia_riesgo, cv_mode, cv315_manual, cv316_manual,
    ):
        tolerancia_riesgo = tolerancia_riesgo or "balanceado"
        pila1       = pila1       or 55
        pila2       = pila2       or 55
        duracion_t8 = duracion_t8 or 0
        sag1_on     = bool(sag1_on_sw) if sag1_on_sw is not None else True
        sag2_on     = bool(sag2_on_sw) if sag2_on_sw is not None else True
        ch1_on      = bool(ch1_vals)
        ch2_on      = bool(ch2_vals)
        c315        = c315        or "activa"
        c316        = c316        or "activa"
        t1_mode     = t1_mode     or "chancado"
        t1_manual   = t1_manual   or 4000
        t3_frac     = (t3_frac_pct or 0) / 100.0
        distribucion_t1 = distribucion_t1 or "proporcional"
        horizonte   = horizonte   or 24
        turno       = turno       or "A"

        maint_windows = _build_maint_windows({
            "sag1": mant_sag1, "sag2": mant_sag2, "411": mant_411,
            "412": mant_412, "511": mant_511, "512": mant_512,
            "ch1": mant_ch1, "ch2": mant_ch2, "cv315": mant_cv315,
            "cv316": mant_cv316, "t1": mant_t1, "t3": mant_t3,
        })
        now_hour = TURNO_START_HOUR[turno]
        en_mant = equipos_en_mantencion(maint_windows, now_hour)
        if sag_forzado_off("SAG1", en_mant):
            sag1_on = False
        if sag_forzado_off("SAG2", en_mant):
            sag2_on = False
        ch1_on, ch2_on, c315, c316, t1_manual = _forzar_equipos_por_mantencion(
            en_mant, ch1_on, ch2_on, c315, c316, t1_manual)
        bola1_opts = bola_opts_restringidas(BOLA1_OPTS_FULL, en_mant, "SAG1")
        bola2_opts = bola_opts_restringidas(BOLA2_OPTS_FULL, en_mant, "SAG2")
        r16_conflicto_sag1 = r16_conflicto_mantencion(en_mant, "SAG1")
        r16_conflicto_sag2 = r16_conflicto_mantencion(en_mant, "SAG2")

        (r1, b1, r2, b2), stats = _find_optimal_params(
            pila1=pila1, pila2=pila2, duracion_t8=duracion_t8,
            sag1_on=sag1_on, sag2_on=sag2_on,
            ch1_on=ch1_on, ch2_on=ch2_on,
            c315=c315, c316=c316,
            t1_mode=t1_mode, t1_manual=t1_manual,
            t3_frac=t3_frac, distribucion_t1=distribucion_t1,
            horizonte=horizonte,
            bola1_opts=bola1_opts, bola2_opts=bola2_opts,
            tolerancia_riesgo=tolerancia_riesgo,
        )

        _bl = {
            "sin_bola": "sin bola", "solo_411": "B411", "solo_412": "B412",
            "ambas_411_412": "B411+412",
            "solo_511": "B511", "solo_512": "B512", "ambas_511_512": "B511+512",
        }
        t8_lbl      = f"T8 {int(duracion_t8)}h" if duracion_t8 > 0 else "Sin T8"
        cap_lbl     = f"{compute_chancado_cap(ch1_on, ch2_on):.0f} TPH chancado"
        tph_val     = stats.get("tph", 0)
        a1_val      = stats.get("a1", 0)
        a2_val      = stats.get("a2", 0)
        safe        = stats.get("safe", True)
        p_safe      = stats.get("p_safe", 0)
        regime      = stats.get("regime", "")
        brecha_tph  = stats.get("brecha_tph", 0)
        brecha_ton  = stats.get("brecha_ton", 0)
        zona        = stats.get("zona", "")
        n_sim       = stats.get("n_sim", 0)
        converged   = stats.get("converged", False)
        v4_diverge  = stats.get("v4_diverge", False)
        v4_r1       = stats.get("v4_r1")
        v4_r2       = stats.get("v4_r2")
        exp_sag1    = stats.get("explicabilidad_sag1", [])
        exp_sag2    = stats.get("explicabilidad_sag2", [])

        badge_color = "success" if safe else "warning"
        brecha_color = VERDE if brecha_tph == 0 else NARANJA
        brecha_txt = (f"Brecha P90: 0 TPH — zona {zona}" if brecha_tph == 0
                      else f"Brecha P90: {brecha_tph:.0f} TPH → {brecha_ton:.0f} t/día no capturadas")
        conv_txt = f"Sim: {n_sim} {'✓' if converged else '~'} | P(safe): {p_safe*100:.0f}%"

        r16_lines = []
        if r16_conflicto_sag1:
            r16_lines.append("Error de planificación: 411 y 412 en mantención simultánea — "
                              "SAG1 queda sin molinos de bolas disponibles (R16).")
        if r16_conflicto_sag2:
            r16_lines.append("Error de planificación: 511 y 512 en mantención simultánea — "
                              "SAG2 queda sin molinos de bolas disponibles (R16).")
        if r16_lines:
            badge_color = "danger"

        # Backlog #2 (UX/UI v2 JdS, 2026-07-07): regimen SIEMPRE traducido a
        # lenguaje operacional (REGIMEN_LABEL_JDS) — nunca el slug crudo
        # ("t8_corta") visible al usuario. Backlog #3: la jerga tecnica
        # (P(safe), Sim: N, brecha P90, V3/V4) queda detras de un click
        # explicito "Ver detalle técnico" — solo el resumen en lenguaje
        # operacional se ve por defecto.
        regimen_label = REGIMEN_LABEL_JDS.get(regime, regime.replace("_", " ").title())

        # Sincronizacion recomendacion/escenario (2026-07-09): hash del
        # escenario EXACTO usado para calcular r1/r2/b1/b2 (con esos
        # mismos valores recien calculados, no los que estaban antes en
        # los inputs) — ver utils/scenario_hash.py. update_simulation
        # compara esto contra el escenario actual en cada render.
        from datetime import datetime as _dt
        from utils.scenario_hash import build_scenario_dict, hash_scenario
        # Mismo criterio de normalizacion que update_simulation: en modo
        # "auto" los valores de CV315/CV316 manual no se usan para nada
        # (la simulacion los ignora), asi que se fuerzan a 0 igual que
        # alla — si no, el hash queda sensible al valor "leftover" que
        # tengan esos inputs aunque cv_mode="auto", generando un
        # desajuste espurio permanente (bug real encontrado en QA visual
        # 2026-07-09: el CV315/316 manual del layout arranca en 1000,
        # nunca en 0, y esta rama lo pasaba crudo sin normalizar).
        cv_mode_norm = cv_mode or "auto"
        cv315_manual_norm = float(cv315_manual) if (cv_mode_norm == "manual" and cv315_manual is not None) else 0.0
        cv316_manual_norm = float(cv316_manual) if (cv_mode_norm == "manual" and cv316_manual is not None) else 0.0
        scenario_dict = build_scenario_dict(
            duracion_t8=duracion_t8, pila1=pila1, pila2=pila2,
            rate_sag1_tph=r1, rate_sag2_tph=r2,
            bolas_sag1=b1, bolas_sag2=b2,
            sag1_on=sag1_on, sag2_on=sag2_on, ch1_on=ch1_on, ch2_on=ch2_on,
            c315=c315, c316=c316, horizonte=horizonte,
            cv_mode=cv_mode_norm, cv315_manual=cv315_manual_norm, cv316_manual=cv316_manual_norm,
            t1_mode=t1_mode, t1_manual=t1_manual, t3_frac=t3_frac, distribucion_t1=distribucion_t1,
            turno=turno,
            mantenciones={"sag1": mant_sag1, "sag2": mant_sag2, "411": mant_411, "412": mant_412,
                          "511": mant_511, "512": mant_512, "ch1": mant_ch1, "ch2": mant_ch2,
                          "cv315": mant_cv315, "cv316": mant_cv316, "t1": mant_t1, "t3": mant_t3},
            tolerancia_riesgo=tolerancia_riesgo,
        )
        recommendation_hash = hash_scenario(scenario_dict)
        fecha_calculo = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        contexto_txt = (
            f"Calculado para: T8={t8_lbl} · Turno={turno} · Horizonte={horizonte:.0f}h · {fecha_calculo}"
        )

        resumen = dbc.Alert([
            *[html.Div(line, style={"fontSize": "0.69rem", "fontWeight": "700", "color": ROJO})
              for line in r16_lines],
            html.Div([
                html.Span(f"{regimen_label} ({t8_lbl}). ", style={"fontWeight": "700"}),
                html.Span(f"SAG1 → {r1} TPH / {_bl[b1]}. "),
                html.Span(f"SAG2 → {r2} TPH / {_bl[b2]}."),
            ], style={"fontSize": "0.72rem"}),
            html.Div(contexto_txt, style={"fontSize": "0.6rem", "color": "#8896AF", "marginTop": "2px"}),
        ], color=badge_color,
           style={"padding": "4px 8px", "marginBottom": "2px"},
           dismissable=True)

        detalle_tecnico = dbc.Collapse([
            html.Div(f"TPH prom esperado: {tph_val:.0f}",
                     style={"fontSize": "0.66rem", "fontWeight": "600"}),
            html.Div(brecha_txt, style={"fontSize": "0.66rem", "color": brecha_color, "fontWeight": "600"}),
            html.Div(conv_txt, style={"fontSize": "0.64rem", "color": "#888"}),
            html.Div(
                f"V4 ({tolerancia_riesgo}): sugiere SAG1={v4_r1} / SAG2={v4_r2} TPH "
                f"(reparte mas hacia SAG2, linea historicamente mas estable)",
                style={"fontSize": "0.64rem", "color": AZUL_MED, "fontWeight": "600", "marginTop": "2px"},
            ) if v4_diverge else None,
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div([html.Div(l, style={"fontSize": "0.64rem"}) for l in exp_sag1],
                              style={"marginBottom": "4px"}),
                    html.Div([html.Div(l, style={"fontSize": "0.64rem"}) for l in exp_sag2]),
                ], title="¿Por qué?", item_id="explicabilidad"),
            ], start_collapsed=True, style={"marginTop": "4px"}),
        ], id="collapse-detalle-tecnico-optimo", is_open=False, style={"marginTop": "2px"})

        badge = html.Div([
            resumen,
            dbc.Button("Ver detalle técnico", id="btn-detalle-tecnico-optimo",
                       size="sm", color="link",
                       style={"fontSize": "0.6rem", "padding": "0"}),
            detalle_tecnico,
        ])

        from utils.state_schema import make_envelope
        return (r1, r2, b1, b2, badge,
                make_envelope({"hash": recommendation_hash}),
                make_envelope(scenario_dict),
                make_envelope({"texto": contexto_txt}))

    @app.callback(
        Output("display-cap-chancado", "children"),
        Input("ctrl-ch1", "value"),
        Input("ctrl-ch2", "value"),
    )
    def update_cap_chancado_display(ch1_vals, ch2_vals):
        ch1 = bool(ch1_vals)
        ch2 = bool(ch2_vals)
        cap = compute_chancado_cap(ch1, ch2)
        if cap == 0:
            color = ROJO
            label = "Chancado DETENIDO"
        elif cap < 2000:
            color = NARANJA
            label = f"Cap. chancado: {cap:.0f} TPH (limitado)"
        else:
            color = VERDE
            label = f"Cap. chancado: {cap:.0f} TPH"
        return html.Span(label, style={"color": color, "fontSize": "0.78rem", "fontWeight": "700"})

    @app.callback(
        Output("cv-manual-controls", "style"),
        Input("ctrl-cv-mode", "value"),
    )
    def toggle_cv_manual(cv_mode):
        if cv_mode == "manual":
            return {"display": "block"}
        return {"display": "none"}

    @app.callback(
        Output("t1-extra-controls", "style"),
        Input("ctrl-t1-mode", "value"),
    )
    def toggle_t1_extra(t1_mode):
        if t1_mode in ("t1_con_t3", "manual"):
            return {"display": "block"}
        return {"display": "none"}

    @app.callback(
        Output("display-t3-estimado", "children"),
        Input("ctrl-t1-mode",    "value"),
        Input("ctrl-t1-manual",  "value"),
        Input("ctrl-t3-frac",    "value"),
        Input("ctrl-ch1",        "value"),
        Input("ctrl-ch2",        "value"),
    )
    def update_t3_display(t1_mode, t1_manual, t3_frac_pct, ch1_vals, ch2_vals):
        from engine.ode_model import compute_t1_tph
        t1_mode  = t1_mode  or "chancado"
        t3_frac  = (t3_frac_pct or 0) / 100.0
        ch1_on   = bool(ch1_vals)
        ch2_on   = bool(ch2_vals)
        cap      = compute_chancado_cap(ch1_on, ch2_on)
        t1_val   = compute_t1_tph(t1_mode, t1_manual or 4000, cap, ch1_on, ch2_on)
        t3_val   = t1_val * t3_frac
        disp_cv  = max(0.0, t1_val - t3_val)
        return html.Span(
            f"T1={t1_val:,.0f} | T3={t3_val:,.0f} | Para CVs={disp_cv:,.0f} TPH",
            style={"fontSize": "0.73rem"},
        )

    @app.callback(
        Output("alerta-bolas", "children"),
        Input("ctrl-bolas-sag1", "value"),
        Input("ctrl-bolas-sag2", "value"),
        Input("ctrl-rate-sag1",  "value"),
        Input("ctrl-rate-sag2",  "value"),
        Input("ctrl-sag1-on",    "value"),
        Input("ctrl-sag2-on",    "value"),
    )
    def check_bola_alert(bolas_sag1, bolas_sag2, rate1_tph, rate2_tph, sag1_on_sw, sag2_on_sw):
        from engine.ode_model import BOLA_THRESHOLD_TPH, BOLA_CONFIG_SAG1, BOLA_CONFIG_SAG2
        bolas_sag1 = bolas_sag1 or "solo_411"
        bolas_sag2 = bolas_sag2 or "solo_511"
        rate1_tph = rate1_tph or 1236
        rate2_tph = rate2_tph or 2214
        sag1_on = bool(sag1_on_sw) if sag1_on_sw is not None else True
        sag2_on = bool(sag2_on_sw) if sag2_on_sw is not None else True
        n1 = BOLA_CONFIG_SAG1.get(bolas_sag1, {"n": 0})["n"]
        n2 = BOLA_CONFIG_SAG2.get(bolas_sag2, {"n": 0})["n"]

        r16_alertas = []
        if bolas_sag1 == "sin_bola" and sag1_on:
            r16_alertas.append(
                "[R16] Configuracion no permitida: SAG1 debe tener al menos "
                "un molino de bolas activo (411 o 412)."
            )
        if bolas_sag2 == "sin_bola" and sag2_on:
            r16_alertas.append(
                "[R16] Configuracion no permitida: SAG2 debe tener al menos "
                "un molino de bolas activo (511 o 512)."
            )

        alertas = []
        if n1 > 1 and rate1_tph < BOLA_THRESHOLD_TPH["SAG1"]:
            alertas.append(
                f"[!] SAG1 (Molino 401): {rate1_tph:.0f} TPH < 1000 TPH — max 1 bola activa"
            )
        if n2 > 1 and rate2_tph < BOLA_THRESHOLD_TPH["SAG2"]:
            alertas.append(
                f"[!] SAG2 (Molino 501): {rate2_tph:.0f} TPH < 1600 TPH — max 1 bola activa"
            )

        if r16_alertas:
            return dbc.Alert(
                [html.Div(a, style={"fontSize": "0.75rem"}) for a in r16_alertas + alertas],
                color="danger",
                style={"padding": "6px 10px", "marginTop": "4px"},
                dismissable=False,
            )
        if alertas:
            return dbc.Alert(
                [html.Div(a, style={"fontSize": "0.75rem"}) for a in alertas],
                color="warning",
                style={"padding": "6px 10px", "marginTop": "4px"},
                dismissable=False,
            )
        return html.Div()

    @app.callback(
        Output("ctrl-pila-sag1",      "value"),
        Output("ctrl-pila-sag2",      "value"),
        Output("ctrl-rate-sag1",      "value",  allow_duplicate=True),
        Output("ctrl-rate-sag2",      "value",  allow_duplicate=True),
        Output("ctrl-bolas-sag1",     "value",  allow_duplicate=True),
        Output("ctrl-bolas-sag2",     "value",  allow_duplicate=True),
        Output("ctrl-sag1-on",         "value"),
        Output("ctrl-sag2-on",         "value"),
        Output("ctrl-ch1",            "value"),
        Output("ctrl-ch2",            "value"),
        Output("ctrl-duracion-t8",    "value"),
        Output("badge-estado-actual", "children"),
        Input("btn-cargar-estado",    "n_clicks"),
        prevent_initial_call=True,
    )
    def cargar_estado_actual(n_clicks):
        try:
            state = load_current_state()
        except Exception as exc:
            badge = dbc.Badge(f"Error: {exc}", color="danger",
                              style={"fontSize": "0.62rem", "whiteSpace": "normal"})
            return (55, 55, 1236, 2214, "solo_411", "solo_511",
                    True, True, ["on"], ["on"], 0, badge)

        import pandas as pd
        ts = state["timestamp"]
        ts_str = pd.Timestamp(ts).strftime("%d/%m %H:%M") if ts is not None else "?"

        t8_info  = state["t8_info"]
        t8_activo = t8_info["t8_activo"]
        if t8_activo:
            tipo = t8_info["tipo_ventana"]
            ela  = t8_info["elapsed_h"]
            drop = t8_info["drop_pct"]
            t8_txt   = f"T8 {tipo}h | {ela:.1f}h | -{drop:.0f}%"
            t8_color = "warning"
        else:
            t8_txt   = "Sin T8"
            t8_color = "success"

        badge = html.Div([
            dbc.Badge(ts_str, color="info",
                      style={"fontSize": "0.62rem", "display": "block", "marginBottom": "2px"}),
            dbc.Badge(t8_txt, color=t8_color,
                      style={"fontSize": "0.62rem", "display": "block"}),
        ])

        ch1_val = ["on"] if state["ch1_on"] else []
        ch2_val = ["on"] if state["ch2_on"] else []

        sag_activos = state["sag_activos"]
        return (
            state["pila_sag1"],
            state["pila_sag2"],
            state["rate_sag1_tph"],
            state["rate_sag2_tph"],
            state["bolas_sag1"],
            state["bolas_sag2"],
            sag_activos in ("ambos", "sag1"),
            sag_activos in ("ambos", "sag2"),
            ch1_val,
            ch2_val,
            state["t8_duracion_selector"],
            badge,
        )

    @app.callback(
        Output("collapse-sensitivity", "is_open"),
        Output("btn-toggle-sensitivity", "children"),
        Input("btn-toggle-sensitivity", "n_clicks"),
        State("collapse-sensitivity", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_sensitivity(n, is_open):
        new_open = not is_open
        label = ("Sensibilidad: Rate → Autonomía  ▴" if new_open
                 else "Sensibilidad: Rate → Autonomía  ▾")
        return new_open, label

    @app.callback(
        Output("collapse-mc",     "is_open"),
        Output("btn-toggle-mc",   "children"),
        Input("btn-toggle-mc",    "n_clicks"),
        State("collapse-mc",      "is_open"),
        prevent_initial_call=True,
    )
    def toggle_mc_collapse(n, is_open):
        new_open = not is_open
        label = ("¿Qué tan confiable es esta recomendación?  ▴" if new_open
                 else "¿Qué tan confiable es esta recomendación?  ▾")
        return new_open, label

    @app.callback(
        Output("collapse-qin-qout", "is_open"),
        Output("btn-toggle-qin-qout", "children"),
        Input("btn-toggle-qin-qout", "n_clicks"),
        State("collapse-qin-qout", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_qin_qout(n, is_open):
        new_open = not is_open
        label = "VER POR QUÉ CRECE O DRENA  ▴" if new_open else "VER POR QUÉ CRECE O DRENA  ▾"
        return new_open, label

    # Segunda iteración UX/UI (2026-07-14, Fase 5 sec.11): cambiar de
    # categoría filtra las opciones de sim-main-view — puramente visual,
    # no toca update_simulation ni dispara simulate_scenario_cached.
    @app.callback(
        Output("sim-main-view", "options"),
        Output("sim-main-view", "value"),
        Input("sim-chart-category", "value"),
        prevent_initial_call=True,
    )
    def filtrar_vistas_por_categoria(categoria_id):
        categoria = next((c for c in CHART_CATEGORIES if c["id"] == categoria_id), CHART_CATEGORIES[0])
        opciones = [t for t in CHART_TABS if t["value"] in categoria["vistas"]]
        return opciones, opciones[0]["value"] if opciones else "pilas"

    # Segunda iteración UX/UI (2026-07-14, Fase 2 sec.4): "Aplicar
    # recomendación" del Decision Banner reusa 100% la logica ya probada
    # de apply_ideal_params, encadenando via btn-params-ideales.n_clicks
    # — mismo patron ya usado por btn-generar-recomendacion (linea ~745),
    # no se duplica la logica de calculo de parametros ideales.
    @app.callback(
        Output("btn-params-ideales", "n_clicks", allow_duplicate=True),
        Input("btn-aplicar-recomendacion", "n_clicks"),
        State("btn-params-ideales", "n_clicks"),
        prevent_initial_call=True,
    )
    def aplicar_recomendacion_desde_banner(_n_clicks_banner, n_clicks_actual):
        return (n_clicks_actual or 0) + 1

    @app.callback(
        Output("ctrl-rate-sag1",        "value",  allow_duplicate=True),
        Output("ctrl-rate-sag2",        "value",  allow_duplicate=True),
        Output("ctrl-bolas-sag1",       "value",  allow_duplicate=True),
        Output("ctrl-bolas-sag2",       "value",  allow_duplicate=True),
        Output("badge-mc-status",       "children"),
        Output("graph-mc",              "figure"),
        Output("div-mc-confidence",     "children"),
        Output("div-mc-summary",        "children"),
        Output("collapse-mc",           "is_open", allow_duplicate=True),
        Output("div-mc-convergencia",   "children", allow_duplicate=True),
        Output("graph-hourly-risk",     "figure"),
        Output("graph-pareto",          "figure"),
        Output("div-top5-mc",           "children"),
        Output("store-mc-results",      "data"),
        Input("btn-monte-carlo",        "n_clicks"),
        # 2026-07-06: revertido de Input a State — Monte Carlo/optimizador
        # SOLO corren al presionar "btn-monte-carlo" (Fase 6, gating
        # explicito pedido por el usuario). Reemplaza la decision anterior
        # de 2026-07-02 (reactividad en vivo en cada slider), documentada
        # en 04_Reports/Technical/20260702_UX_UI_Operational_Control_Center.md
        # — ver nota de reversion en ese mismo archivo.
        State("ctrl-pila-sag1",         "value"),
        State("ctrl-pila-sag2",         "value"),
        State("ctrl-duracion-t8",       "value"),
        State("ctrl-sag1-on",           "value"),
        State("ctrl-sag2-on",           "value"),
        State("ctrl-ch1",               "value"),
        State("ctrl-ch2",               "value"),
        State("ctrl-correa315",         "value"),
        State("ctrl-correa316",         "value"),
        State("ctrl-t1-mode",           "value"),
        State("ctrl-t1-manual",         "value"),
        State("ctrl-t3-frac",           "value"),
        State("ctrl-distribucion-t1",   "value"),
        State("ctrl-horizonte",         "value"),
        State("store-plant-state",      "data"),
        State("ctrl-turno",             "value"),
        State("ctrl-mant-sag1", "value"), State("ctrl-mant-sag2", "value"),
        State("ctrl-mant-411",  "value"), State("ctrl-mant-412",  "value"),
        State("ctrl-mant-511",  "value"), State("ctrl-mant-512",  "value"),
        State("ctrl-mant-ch1",  "value"), State("ctrl-mant-ch2",  "value"),
        State("ctrl-mant-cv315","value"), State("ctrl-mant-cv316","value"),
        State("ctrl-mant-t1",   "value"), State("ctrl-mant-t3",   "value"),
        prevent_initial_call=True,
    )
    def run_monte_carlo(
        _clicks,
        pila1, pila2, duracion_t8,
        sag1_on_sw, sag2_on_sw, ch1_vals, ch2_vals,
        c315, c316, t1_mode, t1_manual, t3_frac_pct,
        distribucion_t1, horizonte, plant_state, turno,
        mant_sag1, mant_sag2, mant_411, mant_412, mant_511, mant_512,
        mant_ch1, mant_ch2, mant_cv315, mant_cv316, mant_t1, mant_t3,
    ):
        pila1       = pila1       or 55
        pila2       = pila2       or 55
        duracion_t8 = duracion_t8 or 0
        sag1_on     = bool(sag1_on_sw) if sag1_on_sw is not None else True
        sag2_on     = bool(sag2_on_sw) if sag2_on_sw is not None else True
        ch1_on      = bool(ch1_vals)
        ch2_on      = bool(ch2_vals)
        c315        = c315        or "activa"
        c316        = c316        or "activa"
        t1_mode     = t1_mode     or "chancado"
        t1_manual   = t1_manual   or 4000
        t3_frac     = (t3_frac_pct or 0) / 100.0
        distribucion_t1 = distribucion_t1 or "proporcional"
        horizonte   = horizonte   or 24
        turno       = turno       or "A"

        maint_windows = _build_maint_windows({
            "sag1": mant_sag1, "sag2": mant_sag2, "411": mant_411,
            "412": mant_412, "511": mant_511, "512": mant_512,
            "ch1": mant_ch1, "ch2": mant_ch2, "cv315": mant_cv315,
            "cv316": mant_cv316, "t1": mant_t1, "t3": mant_t3,
        })
        now_hour = TURNO_START_HOUR[turno]
        en_mant = equipos_en_mantencion(maint_windows, now_hour)
        if sag_forzado_off("SAG1", en_mant):
            sag1_on = False
        if sag_forzado_off("SAG2", en_mant):
            sag2_on = False
        ch1_on, ch2_on, c315, c316, t1_manual = _forzar_equipos_por_mantencion(
            en_mant, ch1_on, ch2_on, c315, c316, t1_manual)
        bola1_opts = bola_opts_restringidas(BOLA1_OPTS_FULL, en_mant, "SAG1")
        bola2_opts = bola_opts_restringidas(BOLA2_OPTS_FULL, en_mant, "SAG2")
        r16_conflicto_sag1 = r16_conflicto_mantencion(en_mant, "SAG1")
        r16_conflicto_sag2 = r16_conflicto_mantencion(en_mant, "SAG2")

        cap = compute_chancado_cap(ch1_on, ch2_on)
        from utils.state_schema import get_data, PLANT_STATE_DEFAULT
        plant_state = get_data(plant_state, PLANT_STATE_DEFAULT, kind="plant_state")
        if plant_state:
            cv315_nom = float(plant_state.get("cv315", cap * 0.29))
            cv316_nom = float(plant_state.get("cv316", cap * 0.71))
        else:
            cv315_nom = cap * 0.29
            cv316_nom = cap * 0.71

        best, mc_results = find_optimal_v3(
            pila1=pila1, pila2=pila2, duracion_t8=duracion_t8,
            sag1_on=sag1_on, sag2_on=sag2_on,
            ch1_on=ch1_on, ch2_on=ch2_on,
            c315=c315, c316=c316,
            cv315_nom=cv315_nom, cv316_nom=cv316_nom,
            t1_mode=t1_mode, t1_manual=t1_manual,
            t3_frac=t3_frac, distribucion_t1=distribucion_t1,
            horizonte=horizonte,
            mode="pareto",
            bola1_opts=bola1_opts, bola2_opts=bola2_opts,
        )

        r1, b1, r2, b2 = best["r1"], best["b1"], best["r2"], best["b2"]

        fig_mc = make_mc_fan_chart(best)
        mc_confidence_card = make_mc_confidence_card(best)
        fig_hourly_risk = make_hourly_risk_chart(best, compact=True)
        _hr_tickvals, _hr_ticktext = hour_of_day_ticks(TURNO_START_HOUR[turno], horizonte)
        fig_hourly_risk.update_xaxes(tickvals=_hr_tickvals, ticktext=_hr_ticktext)

        p_safe_pct  = best["p_safe"] * 100
        badge_color = "success" if p_safe_pct >= 80 else ("warning" if p_safe_pct >= 60 else "danger")
        _bl  = {"sin_bola": "SB", "ambas_411_412": "B411+412"}
        _bl2 = {"sin_bola": "SB", "ambas_511_512": "B511+512"}

        brecha      = best.get("brecha_p90", {})
        brecha_tph  = brecha.get("brecha_tph_sag1", 0)
        brecha_ton  = brecha.get("brecha_ton_dia", 0)
        zona        = brecha.get("zona", "")
        brecha_badge = (f"Zona:{zona}" if brecha_tph == 0
                        else f"Brecha:{brecha_tph:.0f}TPH={brecha_ton:.0f}t/d")

        r16_txt = ""
        if r16_conflicto_sag1 or r16_conflicto_sag2:
            badge_color = "danger"
            equipos_conflicto = []
            if r16_conflicto_sag1:
                equipos_conflicto.append("SAG1 (411+412)")
            if r16_conflicto_sag2:
                equipos_conflicto.append("SAG2 (511+512)")
            r16_txt = f" | ⚠ R16: mantención simultánea en {', '.join(equipos_conflicto)}"

        # Backlog #3 (UX/UI v2 JdS, 2026-07-07): este badge vive en el
        # sidebar, SIEMPRE visible (no esta detras de ningun click) — no
        # puede llevar jerga ("P(seg)", "MC V3"). El detalle tecnico
        # completo (P(safe), TPH, brecha) ya se muestra en `summary` mas
        # abajo, que SI esta detras de "collapse-mc".
        confianza_txt = "Alta" if p_safe_pct >= 80 else ("Media" if p_safe_pct >= 60 else "Baja")
        badge = dbc.Badge(
            f"Confiabilidad {confianza_txt}: SAG1+SAG2 ≈{best['tph_mean']:.0f} TPH{r16_txt}",
            color=badge_color,
            style={"fontSize": "0.62rem", "whiteSpace": "nowrap"},
        )

        n_used     = best.get("n_samples_used", 0)
        converged  = best.get("converged", False)
        conv_label = "Convergente" if converged else "No convergente (usar con cautela)"
        conv_div   = html.Span(
            f"Simulaciones: {n_used} — {conv_label}",
            style={"fontSize": "0.68rem", "color": "#888"},
        )

        explanation_lines = _build_mc_explanation(best, mc_results, duracion_t8)

        summary = html.Div([
            html.Strong("Configuracion mas robusta (MC Pareto):",
                        style={"color": AZUL, "fontSize": "0.78rem"}),
            dbc.Row([
                dbc.Col([
                    html.Div(f"SAG1: {r1} TPH / {_bl.get(b1, b1)}",
                             style={"fontSize": "0.75rem"}),
                    html.Div(f"SAG2: {r2} TPH / {_bl2.get(b2, b2)}",
                             style={"fontSize": "0.75rem"}),
                ], width=5),
                dbc.Col([
                    html.Div(f"P(seguro): {p_safe_pct:.0f}%",
                             style={"fontSize": "0.75rem",
                                    "color": VERDE if p_safe_pct >= 80 else NARANJA,
                                    "fontWeight": "700"}),
                    html.Div(
                        f"TPH: {best.get('tph_p10', 0):.0f} - "
                        f"{best['tph_mean']:.0f} - "
                        f"{best.get('tph_p90', 0):.0f} (P10/med/P90)",
                        style={"fontSize": "0.72rem", "color": "#555"},
                    ),
                ], width=7),
            ], className="mt-1"),
            html.Hr(style={"margin": "4px 0"}),
            html.Div([
                html.Div(
                    "Por que es la mejor configuracion",
                    style={
                        "fontSize": "0.71rem",
                        "fontWeight": "700",
                        "color": AZUL,
                        "marginBottom": "3px",
                    },
                ),
                html.Ul(
                    [
                        html.Li(
                            line,
                            style={
                                "fontSize": "0.71rem",
                                "color": TEXTO_MUTED,
                                "marginBottom": "2px",
                            },
                        )
                        for line in explanation_lines
                    ],
                    style={"paddingLeft": "18px", "marginBottom": "6px"},
                ),
            ], style={"backgroundColor": BG_CARD_DARK, "borderRadius": "4px", "padding": "6px 8px"}),
            html.Hr(style={"margin": "4px 0"}),
            html.Div(
                "Incertidumbres modeladas: pilas +/-2.5%, feed +/-12%"
                + (", T8 +/-1h" if duracion_t8 > 0 else ""),
                style={"fontSize": "0.68rem", "color": "#888", "fontStyle": "italic"},
            ),
        ], style={"backgroundColor": "#123059", "borderRadius": "4px", "padding": "8px"})

        fig_pareto   = make_pareto_scatter(mc_results, compact=True)
        top5_mc_card = make_top5_card(format_top5_records(mc_results[:5]), "Balance Optimo MC",
                                      compact=True)

        from utils.state_schema import make_envelope
        return (r1, r2, b1, b2, badge, fig_mc, mc_confidence_card, summary, True, conv_div,
                fig_hourly_risk, fig_pareto, top5_mc_card, make_envelope(best))

    @app.callback(
        Output("graph-main",        "figure"),
        Output("div-main-view-explanation", "children"),
        Output("graph-autonomia",   "figure"),
        Output("graph-bolas",       "figure"),
        Output("graph-chancado",    "figure"),
        Output("sim-summary-bar",   "children"),
        Output("sim-compare-block", "children"),
        Output("kpi-column",        "children"),
        Output("graph-sensitivity", "figure"),
        Output("div-sensitivity-explanation", "children"),
        Output("graph-gantt-operacional", "figure"),
        Output("r16-status-badge", "children"),
        Output("store-plant-state", "data"),
        Output("store-ultimo-snapshot-caso", "data"),
        Output("div-recomendacion-desactualizada", "children"),
        Output("div-estado-general",     "children"),
        Output("div-autonomia-sag1",     "children"),
        Output("div-autonomia-sag2",     "children"),
        Output("div-recomendacion-corta", "children"),
        Output("div-recuperacion",       "children"),
        Output("div-quick-win",          "children"),
        Output("graph-qin-qout",         "figure"),
        Output("div-scenario-compare",   "children"),
        Output("div-decision-banner",    "children"),
        Output("div-confianza-card",     "children"),
        Input("sim-main-view",      "value"),
        Input("ctrl-circuito",      "value"),
        Input("ctrl-modo-vista",   "value"),
        Input("ctrl-duracion-t8",  "value"),
        Input("ctrl-pila-sag1",    "value"),
        Input("ctrl-pila-sag2",    "value"),
        Input("ctrl-rate-sag1",    "value"),
        Input("ctrl-rate-sag2",    "value"),
        Input("ctrl-bolas-sag1",   "value"),
        Input("ctrl-bolas-sag2",   "value"),
        Input("ctrl-sag1-on",      "value"),
        Input("ctrl-sag2-on",      "value"),
        Input("ctrl-correa315",    "value"),
        Input("ctrl-correa316",    "value"),
        Input("ctrl-horizonte",    "value"),
        Input("ctrl-ch1",          "value"),
        Input("ctrl-ch2",          "value"),
        Input("ctrl-cv-mode",       "value"),
        Input("ctrl-cv315-manual",  "value"),
        Input("ctrl-cv316-manual",  "value"),
        Input("ctrl-t1-mode",       "value"),
        Input("ctrl-t1-manual",     "value"),
        Input("ctrl-t3-frac",       "value"),
        Input("ctrl-distribucion-t1", "value"),
        Input("btn-reset-zoom",     "n_clicks"),
        Input("store-mc-results",   "data"),
        Input("ctrl-turno",         "value"),
        Input("ctrl-mant-sag1", "value"), Input("ctrl-mant-sag2", "value"),
        Input("ctrl-mant-411",  "value"), Input("ctrl-mant-412",  "value"),
        Input("ctrl-mant-511",  "value"), Input("ctrl-mant-512",  "value"),
        Input("ctrl-mant-ch1",  "value"), Input("ctrl-mant-ch2",  "value"),
        Input("ctrl-mant-cv315","value"), Input("ctrl-mant-cv316","value"),
        Input("ctrl-mant-t1",   "value"), Input("ctrl-mant-t3",   "value"),
        Input("ctrl-tolerancia-riesgo", "value"),
        Input("ctrl-feed-recovery-mode",       "value"),
        Input("ctrl-feed-recovery-time-min",   "value"),
        Input("ctrl-sag-ramp-up-min",          "value"),
        Input("ctrl-enforce-ball-capacity",    "value"),
        Input("ctrl-one-ball-capacity-factor", "value"),
        Input("ctrl-redistribution-enabled",   "value"),
        State("store-recommendation-scenario-hash",   "data"),
        State("store-recommendation-scenario-params", "data"),
    )
    def update_simulation(
        main_view, circuito, modo_vista, duracion_t8, pila1, pila2, rate1_tph, rate2_tph,
        bolas_sag1, bolas_sag2, sag1_on_sw, sag2_on_sw, c315, c316, horizonte,
        ch1_vals, ch2_vals, cv_mode, cv315_val, cv316_val,
        t1_mode, t1_manual_val, t3_frac_pct, distribucion_t1,
        _reset_clicks, mc_results_cached, turno,
        mant_sag1, mant_sag2, mant_411, mant_412, mant_511, mant_512,
        mant_ch1, mant_ch2, mant_cv315, mant_cv316, mant_t1, mant_t3,
        tolerancia_riesgo,
        feed_recovery_mode, feed_recovery_time_min, sag_ramp_up_min,
        enforce_ball_capacity_sw, one_ball_capacity_factor, redistribution_enabled_sw,
        recommendation_hash, recommendation_params,
    ):
        import time as _time
        _t0_sim = _time.perf_counter()

        # Fase 5 (Skill UX/UI — Auditoria de Contraste TDA, 2026-07-07):
        # aplica la preferencia de tema (claro/oscuro) a los modulos que
        # construyen graficos/tarjetas ANTES de generar nada — ver
        # utils/theme_state.py para por que reasignar las constantes de
        # color en el namespace global de cada modulo es suficiente
        # (no requiere tocar cada funcion individualmente).
        try:
            from utils.theme_state import apply_theme_to_module, apply_plotly_theme, get_theme
            _theme = get_theme()
            import components.graphs as _graphs_mod, components.cards as _cards_mod, components.controls as _controls_mod
            apply_theme_to_module(_graphs_mod.__dict__, _theme)
            apply_theme_to_module(_cards_mod.__dict__, _theme)
            apply_theme_to_module(_controls_mod.__dict__, _theme)
            apply_theme_to_module(globals(), _theme)
            apply_plotly_theme(_theme)
        except Exception:
            pass

        # Defaults seguros
        main_view     = main_view     or "pilas"
        circuito      = circuito      or "ambos"
        duracion_t8  = duracion_t8  or 0
        pila1        = pila1        or 55
        pila2        = pila2        or 55
        rate1_tph    = rate1_tph    or 1236
        rate2_tph    = rate2_tph    or 2214
        bolas_sag1   = bolas_sag1   or "solo_411"
        bolas_sag2   = bolas_sag2   or "solo_511"
        c315         = c315         or "activa"
        c316         = c316         or "activa"
        horizonte    = horizonte    or 24
        cv_mode      = cv_mode      or "auto"

        t1_mode        = t1_mode        or "chancado"
        t1_manual_val  = t1_manual_val  or 4000
        t3_frac        = (t3_frac_pct   or 0) / 100.0
        distribucion_t1 = distribucion_t1 or "proporcional"
        tolerancia_riesgo = tolerancia_riesgo or "balanceado"

        # Fase 2 (2026-07-14, controles avanzados del kernel
        # engine/circuit_state.py): todos con default que reproduce el
        # comportamiento anterior — nadie que no abra "Avanzado" ve cambio.
        _phase2_kwargs = {
            "feed_recovery_mode": feed_recovery_mode or "linear",
            "feed_recovery_time_min": float(feed_recovery_time_min or 0.0),
            "sag_ramp_up_time_min": float(sag_ramp_up_min or 0.0),
            "enforce_downstream_ball_capacity": bool(enforce_ball_capacity_sw),
            "one_ball_capacity_factor": float(one_ball_capacity_factor or 0.55),
            "redistribution_enabled": bool(redistribution_enabled_sw),
        }

        # Estado persistido (dcc.Store de sesion) — nunca se usa "pelado".
        # Un store de una version anterior de la app (schema_version
        # distinto o ausente) se descarta automaticamente y se trata como
        # "sin recomendacion vigente", nunca como un error.
        from utils.state_schema import (
            get_data, RECOMMENDATION_HASH_DEFAULT, RECOMMENDATION_PARAMS_DEFAULT,
            RECOMMENDATION_PARAMS_REQUIRED, MC_RESULTS_DEFAULT,
        )
        recommendation_hash = get_data(
            recommendation_hash, RECOMMENDATION_HASH_DEFAULT, kind="recommendation_scenario_hash",
        ).get("hash")
        recommendation_params = get_data(
            recommendation_params, RECOMMENDATION_PARAMS_DEFAULT,
            required_keys=RECOMMENDATION_PARAMS_REQUIRED, kind="recommendation_scenario_params",
        ) or None
        mc_results_cached = get_data(mc_results_cached, MC_RESULTS_DEFAULT, kind="mc_results") or None

        sag1_on = bool(sag1_on_sw) if sag1_on_sw is not None else True
        sag2_on = bool(sag2_on_sw) if sag2_on_sw is not None else True
        ch1_on = bool(ch1_vals)
        ch2_on = bool(ch2_vals)

        # Turno / mantenciones — restriccion dura: un equipo en mantencion al
        # inicio del horizonte no puede estar operando en la simulacion.
        turno = turno or "A"
        base_hour = TURNO_START_HOUR[turno]
        maint_windows = _build_maint_windows({
            "sag1": mant_sag1, "sag2": mant_sag2, "411": mant_411,
            "412": mant_412, "511": mant_511, "512": mant_512,
            "ch1": mant_ch1, "ch2": mant_ch2, "cv315": mant_cv315,
            "cv316": mant_cv316, "t1": mant_t1, "t3": mant_t3,
        })
        en_mant = equipos_en_mantencion(maint_windows, base_hour)
        if sag_forzado_off("SAG1", en_mant):
            sag1_on = False
        if sag_forzado_off("SAG2", en_mant):
            sag2_on = False
        ch1_on, ch2_on, c315, c316, t1_manual_val = _forzar_equipos_por_mantencion(
            en_mant, ch1_on, ch2_on, c315, c316, t1_manual_val)
        r16_conflicto_sag1 = r16_conflicto_mantencion(en_mant, "SAG1")
        r16_conflicto_sag2 = r16_conflicto_mantencion(en_mant, "SAG2")

        # Si la seleccion manual cae en mantencion, preferir el molino
        # restante valido (R16: nunca degradar a "sin_bola" mientras exista
        # una opcion con al menos 1 molino operativo).
        valid1 = bola_opts_restringidas(BOLA1_OPTS_FULL, en_mant, "SAG1")
        if bolas_sag1 not in valid1:
            bolas_sag1 = next((o for o in valid1 if o != "sin_bola"), "sin_bola")
        valid2 = bola_opts_restringidas(BOLA2_OPTS_FULL, en_mant, "SAG2")
        if bolas_sag2 not in valid2:
            bolas_sag2 = next((o for o in valid2 if o != "sin_bola"), "sin_bola")

        # Valores manuales de CV
        cap = compute_chancado_cap(ch1_on, ch2_on)
        if cv_mode == "manual":
            cv315_manual = float(cv315_val) if cv315_val is not None else cap * 0.5
            cv316_manual = float(cv316_val) if cv316_val is not None else cap * 0.5
        else:
            cv315_manual = 0.0
            cv316_manual = 0.0

        sim = simulate_scenario_cached(
            pila_sag1_pct=pila1,
            pila_sag2_pct=pila2,
            rate_sag1_pct=100.0,
            rate_sag2_pct=100.0,
            bolas_sag1=bolas_sag1,
            bolas_sag2=bolas_sag2,
            sag1_activo=sag1_on,
            sag2_activo=sag2_on,
            duracion_t8_h=duracion_t8,
            correa315_estado=c315,
            correa316_estado=c316,
            horizonte_horas=horizonte,
            ch1_on=ch1_on,
            ch2_on=ch2_on,
            cv_mode=cv_mode,
            cv315_manual_tph=cv315_manual,
            cv316_manual_tph=cv316_manual,
            rate_sag1_tph=rate1_tph,
            rate_sag2_tph=rate2_tph,
            t1_mode=t1_mode,
            t1_manual_tph=t1_manual_val,
            t3_frac=t3_frac,
            distribucion_t1=distribucion_t1,
            **_phase2_kwargs,
        )

        # Baseline sin T8 (mismos params) para calcular tonelaje perdido
        sim_baseline = None
        if duracion_t8 > 0:
            sim_baseline = simulate_scenario_cached(
                pila_sag1_pct=pila1, pila_sag2_pct=pila2,
                rate_sag1_pct=100.0, rate_sag2_pct=100.0,
                bolas_sag1=bolas_sag1, bolas_sag2=bolas_sag2,
                sag1_activo=sag1_on, sag2_activo=sag2_on,
                duracion_t8_h=0,
                correa315_estado=c315, correa316_estado=c316,
                horizonte_horas=horizonte,
                ch1_on=ch1_on, ch2_on=ch2_on,
                cv_mode=cv_mode,
                cv315_manual_tph=cv315_manual, cv316_manual_tph=cv316_manual,
                rate_sag1_tph=rate1_tph, rate_sag2_tph=rate2_tph,
                t1_mode=t1_mode, t1_manual_tph=t1_manual_val,
                t3_frac=t3_frac, distribucion_t1=distribucion_t1,
                **_phase2_kwargs,
            )

        # Sincronizacion recomendacion/escenario (2026-07-09): hash del
        # escenario ACTUAL (mismos campos, mismo orden que
        # apply_ideal_params — ver utils/scenario_hash.py) comparado
        # contra el hash congelado en el ultimo "GENERAR RECOMENDACION"
        # (store-recommendation-scenario-hash, State — no dispara este
        # callback por si solo). Si no coinciden, la recomendacion
        # vigente en pantalla ya no corresponde al escenario actual.
        from utils.scenario_hash import build_scenario_dict, hash_scenario
        current_scenario_dict = build_scenario_dict(
            duracion_t8=duracion_t8, pila1=pila1, pila2=pila2,
            rate_sag1_tph=rate1_tph, rate_sag2_tph=rate2_tph,
            bolas_sag1=bolas_sag1, bolas_sag2=bolas_sag2,
            sag1_on=sag1_on, sag2_on=sag2_on, ch1_on=ch1_on, ch2_on=ch2_on,
            c315=c315, c316=c316, horizonte=horizonte,
            cv_mode=cv_mode, cv315_manual=cv315_manual, cv316_manual=cv316_manual,
            t1_mode=t1_mode, t1_manual=t1_manual_val, t3_frac=t3_frac, distribucion_t1=distribucion_t1,
            turno=turno,
            mantenciones={"sag1": mant_sag1, "sag2": mant_sag2, "411": mant_411, "412": mant_412,
                          "511": mant_511, "512": mant_512, "ch1": mant_ch1, "ch2": mant_ch2,
                          "cv315": mant_cv315, "cv316": mant_cv316, "t1": mant_t1, "t3": mant_t3},
            tolerancia_riesgo=tolerancia_riesgo,
        )
        current_scenario_hash = hash_scenario(current_scenario_dict)
        recomendacion_vigente = (recommendation_hash is not None and current_scenario_hash == recommendation_hash)

        banner_desactualizada = None
        if recommendation_hash is not None and not recomendacion_vigente:
            banner_desactualizada = dbc.Alert(
                [
                    html.Strong("⚠ Recomendación desactualizada", style={"fontSize": "0.72rem"}),
                    html.Div(
                        "Cambiaste parámetros después de generar la recomendación. "
                        "Presiona GENERAR RECOMENDACION para recalcular.",
                        style={"fontSize": "0.66rem"},
                    ),
                ],
                color="warning", style={"padding": "5px 8px", "marginBottom": "4px"},
            )

        # Modo de vista "Recomendacion vigente" (Fase 7): re-simula con
        # los parametros CONGELADOS del ultimo click en GENERAR
        # RECOMENDACION (no los actuales) — solo si el hash coincide.
        # simulate_scenario_cached ya cachea por parametros exactos, asi
        # que si el usuario nunca salio de ese escenario esto es un cache
        # hit, no una simulacion nueva. Si esta desactualizada, se cae a
        # "Simulacion actual" (nunca se deja el panel en blanco) y se
        # avisa en la explicacion del grafico.
        modo_vista_no_disponible = False
        if modo_vista == "recomendacion":
            if recomendacion_vigente and recommendation_params:
                sim = simulate_scenario_cached(
                    pila_sag1_pct=recommendation_params["pila1"],
                    pila_sag2_pct=recommendation_params["pila2"],
                    rate_sag1_pct=100.0, rate_sag2_pct=100.0,
                    bolas_sag1=recommendation_params["bolas_sag1"],
                    bolas_sag2=recommendation_params["bolas_sag2"],
                    sag1_activo=recommendation_params["sag1_on"],
                    sag2_activo=recommendation_params["sag2_on"],
                    duracion_t8_h=recommendation_params["duracion_t8"],
                    correa315_estado=recommendation_params["c315"],
                    correa316_estado=recommendation_params["c316"],
                    horizonte_horas=recommendation_params["horizonte"],
                    ch1_on=recommendation_params["ch1_on"], ch2_on=recommendation_params["ch2_on"],
                    cv_mode=recommendation_params["cv_mode"],
                    cv315_manual_tph=recommendation_params["cv315_manual"] or 0.0,
                    cv316_manual_tph=recommendation_params["cv316_manual"] or 0.0,
                    rate_sag1_tph=recommendation_params["rate_sag1_tph"],
                    rate_sag2_tph=recommendation_params["rate_sag2_tph"],
                    t1_mode=recommendation_params["t1_mode"],
                    t1_manual_tph=recommendation_params["t1_manual"] or 4000.0,
                    t3_frac=recommendation_params["t3_frac"] or 0.0,
                    distribucion_t1=recommendation_params["distribucion_t1"],
                    **_phase2_kwargs,
                )
            else:
                modo_vista_no_disponible = True

        _t0_render = _time.perf_counter()
        # Rediseño JdS (2026-07-13): hora de recuperación post-T8/mantención
        # (bloque 6.5 y marcador "Inicio de recuperación" del gráfico
        # principal, seccion 7) — se calcula antes de fig_pile porque
        # make_master_pile_chart la necesita para anotar el grafico.
        recovery = compute_recovery_time(sim, duracion_t8) if duracion_t8 > 0 else None
        fig_pile       = make_master_pile_chart(sim, horizonte, duracion_t8,
                                                 maint_windows=maint_windows, recovery=recovery)
        # Segunda iteración UX/UI (2026-07-14, Fase 4 sec.10): selector de
        # circuito — solo ajusta `visible` de trazas ya calculadas, no
        # vuelve a simular ni cambia fig_pile fuera de esa propiedad.
        fig_pile = apply_circuit_filter(fig_pile, circuito)
        fig_tph        = make_tph_chart(sim, horizonte, duracion_t8, sim_baseline=sim_baseline)
        fig_risk       = make_risk_chart(sim, horizonte, duracion_t8)
        fig_bolas      = make_bola_timeline_chart(sim, horizonte, duracion_t8,
                                                  rate_sag1_tph=rate1_tph,
                                                  rate_sag2_tph=rate2_tph)
        fig_chancado   = make_chancado_cv_chart(sim, horizonte, duracion_t8)
        fig_balance_t3 = make_t1_t3_balance_chart(sim, horizonte, duracion_t8, maint_windows=maint_windows)
        fig_autonomia  = make_autonomia_chart(sim, horizonte)
        try:
            from utils.perf_logger import log_duration
            log_duration("render_figuras", (_time.perf_counter() - _t0_render) * 1000.0, vista=main_view)
        except Exception:
            pass
        # CAMBIO 5 (UX/UI v2 JdS, 2026-07-07): make_kpi_column ahora retorna
        # un dict agrupado por categoria en vez de una lista plana — las
        # tarjetas adicionales se insertan en su categoria correspondiente
        # (no se apilan verticalmente todas juntas). make_cockpit_row()
        # arma la fila horizontal final mas abajo, junto al return.
        kpi_groups     = make_kpi_column(sim, rate1_tph, rate2_tph)
        bottleneck     = detect_bottleneck(sim, ch1_on=ch1_on, ch2_on=ch2_on,
                                           correa315_estado=c315, correa316_estado=c316)
        kpi_groups["riesgo"].append(make_bottleneck_card(bottleneck))

        # Reenfoque autonomia/armonia: Indice de Armonia Operacional
        # (engine/harmony_index.py) — variabilidad se mide sobre la serie
        # simulada completa (sin_ventana si no hay T8, durante si la hay),
        # riesgo se aproxima desde el nivel categorico 0/1/2 de sim
        # (riesgo_sag1/2, ver ode_model.py::_pile_risk) a fraccion [0,1].
        _var1 = compute_tph_variability(
            sim["tph_sag1"], sim["time"], duracion_t8, "durante" if duracion_t8 > 0 else "sin_ventana")
        _var2 = compute_tph_variability(
            sim["tph_sag2"], sim["time"], duracion_t8, "durante" if duracion_t8 > 0 else "sin_ventana")
        _harmony = compute_harmony_index(
            rate1_tph=rate1_tph, rate2_tph=rate2_tph,
            p90_sag1=P90["SAG1"], p90_sag2=P90["SAG2"],
            autonomia1_h=sim["autonomia_sag1"][-1], autonomia2_h=sim["autonomia_sag2"][-1],
            riesgo1=sim["riesgo_sag1"][-1] / 2.0, riesgo2=sim["riesgo_sag2"][-1] / 2.0,
            cv_tph1=_var1["cv"], cv_tph2=_var2["cv"],
            n_bolas1=round(sim["bola411"][-1] + sim["bola412"][-1]),
            n_bolas2=round(sim["bola511"][-1] + sim["bola512"][-1]),
        )
        kpi_groups["riesgo"].append(make_harmony_card(_harmony))
        _pam1_stats = pam_compliance_stats("SAG1")
        _pam2_stats = pam_compliance_stats("SAG2")
        kpi_groups["pam"].append(make_pam_compliance_card(_pam1_stats, _pam2_stats))
        kpi_groups["pam"].append(make_pam_probability_card(
            get_pam_monthly_projection("SAG1"), get_pam_monthly_projection("SAG2")))

        # Fase 11: KPI "Balance Neto de Pila" — solo con T8 activa (sin
        # T8 no hay "post-T8" que diagnosticar). Reusa el mismo
        # compute_post_t8_balance que alimenta la explicacion textual
        # mas abajo — el calculo es solo indexar arrays ya calculados,
        # costo despreciable repetirlo aca.
        if duracion_t8 > 0:
            from engine.balance_diagnostics import compute_post_t8_balance as _compute_balance_kpi
            _balance_kpi = _compute_balance_kpi(sim, duracion_t8)
            if _balance_kpi:
                kpi_groups["inventario"].append(make_balance_neto_card(_balance_kpi))

        # Nota 2026-07-07: se saco la tarjeta v1 "Logica de simulacion
        # activada" (run_adaptive_simulation) de la vista — quedaba
        # duplicada en contenido con "Confiabilidad de la Recomendacion"
        # (CAMBIO 6) y sumaba clutter. run_adaptive_simulation/
        # simulation_router v1 siguen intactos en engine/, solo se dejo de
        # renderizar esta tarjeta especifica en el cockpit.

        # Router v2 (PROMPT v2, 2026-07-07): decide la estrategia ANTES de
        # simular (CriticalityScorer + BaseSimulationStrategy), en vez de
        # clasificar el `sim` ya calculado con parametros por defecto (v1
        # arriba). Card adicional — no reemplaza la de v1.
        _mant_activa = equipos_en_mantencion(maint_windows or {}, base_hour)
        router_v2_result = route_and_simulate(
            pila1=pila1, pila2=pila2, duracion_t8=duracion_t8,
            qin1_actual=float(sim.get("cv315", [0])[0]) if sim.get("cv315") else 0.0,
            qin2_actual=float(sim.get("cv316", [0])[0]) if sim.get("cv316") else 0.0,
            qout1_actual=rate1_tph, qout2_actual=rate2_tph,
            ch1_on=ch1_on, ch2_on=ch2_on,
            correa315_estado=c315, correa316_estado=c316,
            maint_windows=maint_windows, now_hour=base_hour, horizonte=horizonte,
            sag1_on=sag1_on, sag2_on=sag2_on,
            mobo1_disponible=not ({"411", "412"} & _mant_activa),
            mobo2_disponible=not ({"511", "512"} & _mant_activa),
            tolerancia_riesgo=tolerancia_riesgo,
            t1_mode=t1_mode, t1_manual=t1_manual_val,
            t3_frac=t3_frac, distribucion_t1=distribucion_t1,
        )
        kpi_groups["riesgo"].insert(0, make_router_v2_card(router_v2_result))
        kpis = make_cockpit_row(kpi_groups)

        bottleneck_map  = full_bottleneck_map(sim, ch1_on=ch1_on, ch2_on=ch2_on,
                                              correa315_estado=c315, correa316_estado=c316)
        fig_bottleneck  = make_bottleneck_map_chart(bottleneck_map)

        turno_rows      = build_hourly_schedule(
            base_hour=base_hour, horizonte_h=horizonte, duracion_t8=duracion_t8,
            maint_windows=maint_windows, rate1_tph=rate1_tph, rate2_tph=rate2_tph,
            bola1_label=bolas_sag1, bola2_label=bolas_sag2,
        )
        fig_turno       = make_turno_planificador_table(turno_rows)

        # Eje "hora del dia" real (turno + horizonte movil) sobre los graficos
        # de horas relativas existentes.
        _tickvals, _ticktext = hour_of_day_ticks(base_hour, horizonte)
        for _fig in (fig_pile, fig_tph, fig_risk, fig_chancado, fig_balance_t3, fig_autonomia):
            _fig.update_xaxes(tickvals=_tickvals, ticktext=_ticktext)

        # Gantt "Estado Operacional por Hora"
        from engine.ode_model import BOLA_CONFIG_SAG1, BOLA_CONFIG_SAG2
        _cfg1 = BOLA_CONFIG_SAG1.get(bolas_sag1, {"b411": 0, "b412": 0})
        _cfg2 = BOLA_CONFIG_SAG2.get(bolas_sag2, {"b511": 0, "b512": 0})
        gantt_states = {
            "CH1": "on" if ch1_on else "off",
            "CH2": "on" if ch2_on else "off",
            "T1": "on" if (ch1_on or ch2_on) else "off",
            "T3": "on" if (t1_mode in ("t1_con_t3", "manual") and t3_frac > 0) else "off",
            "CV315": "on" if c315 != "inactiva" else "off",
            "CV316": "on" if c316 != "inactiva" else "off",
            "SAG1": "on" if sag1_on else "off",
            "SAG2": "on" if sag2_on else "off",
            "411": "on" if (sag1_on and _cfg1.get("b411")) else "off",
            "412": "on" if (sag1_on and _cfg1.get("b412")) else "off",
            "511": "on" if (sag2_on and _cfg2.get("b511")) else "off",
            "512": "on" if (sag2_on and _cfg2.get("b512")) else "off",
        }
        fig_gantt = make_gantt_operacional(base_hour, horizonte, gantt_states, maint_windows)

        # Sensibilidad: usar CV inicial del escenario simulado
        cv315_init = float(np.array(sim.get("cv315", [cap * 0.29])).flat[0])
        cv316_init = float(np.array(sim.get("cv316", [cap * 0.71])).flat[0])
        fig_sens = make_sensitivity_chart(
            pila_sag1=pila1, pila_sag2=pila2,
            rate_sag1_tph=rate1_tph, rate_sag2_tph=rate2_tph,
            cv315_tph=cv315_init, cv316_tph=cv316_init,
        )

        recommended_rate1 = _parse_rate_band_midpoint(sim.get("rate_recomendado_sag1", "72-95%"), "SAG1", rate1_tph)
        recommended_rate2 = _parse_rate_band_midpoint(sim.get("rate_recomendado_sag2", "82-100%"), "SAG2", rate2_tph)
        rec_bolas1 = _recommended_bola_cfg("SAG1", sim.get("bolas_recomendadas_sag1", 2), bolas_sag1, sim.get("alerta_bola_sag1", False))
        rec_bolas2 = _recommended_bola_cfg("SAG2", sim.get("bolas_recomendadas_sag2", 2), bolas_sag2, sim.get("alerta_bola_sag2", False))

        sim_recommended = simulate_scenario_cached(
            pila_sag1_pct=pila1,
            pila_sag2_pct=pila2,
            rate_sag1_pct=100.0,
            rate_sag2_pct=100.0,
            bolas_sag1=rec_bolas1,
            bolas_sag2=rec_bolas2,
            sag1_activo=sag1_on,
            sag2_activo=sag2_on,
            duracion_t8_h=duracion_t8,
            correa315_estado=c315,
            correa316_estado=c316,
            horizonte_horas=horizonte,
            ch1_on=ch1_on,
            ch2_on=ch2_on,
            cv_mode=cv_mode,
            cv315_manual_tph=cv315_manual,
            cv316_manual_tph=cv316_manual,
            rate_sag1_tph=recommended_rate1,
            rate_sag2_tph=recommended_rate2,
            t1_mode=t1_mode,
            t1_manual_tph=t1_manual_val,
            t3_frac=t3_frac,
            distribucion_t1=distribucion_t1,
        )

        eval_h = float(duracion_t8) if float(duracion_t8) > 0 else float(horizonte)
        current_metrics = _extract_eval_metrics(sim, eval_h)
        rec_metrics = _extract_eval_metrics(sim_recommended, eval_h)
        action_label, action_tone = _action_summary(
            sim.get("accion_recomendada", "OPERACION_NORMAL"),
            current_metrics["survives"],
            current_metrics["max_risk"],
        )

        p_safe_actual = mc_results_cached.get("p_safe", 1.0) if isinstance(mc_results_cached, dict) else 1.0
        autonomia_min_h = min(current_metrics["a1_min"], current_metrics["a2_min"])

        # KPI nuevo: Estado del Inventario (5 estados, prompt UX/UI v2 JdS
        # 2026-07-07) — combina overflow/critico/tendencia de ambas pilas
        # en un unico semaforo de 5 colores.
        _p1_arr = np.array(sim["pile_sag1"]); _p2_arr = np.array(sim["pile_sag2"])
        _overflow = bool((_p1_arr.max() >= 95.0) or (_p2_arr.max() >= 95.0))
        _critico = current_metrics["a1_min"] < 1.5 or current_metrics["a2_min"] < 1.5
        _delta1, _delta2 = float(_p1_arr[-1] - pila1), float(_p2_arr[-1] - pila2)
        _drenando = min(_delta1, _delta2) < -5.0
        _creciendo = (min(_delta1, _delta2) > 5.0) and not _drenando
        if _overflow:
            inv_emoji, inv_txt, inv_tone = "🟣", "Riesgo de overflow", "danger"
        elif _critico:
            inv_emoji, inv_txt, inv_tone = "🔴", "Riesgo de vaciado", "danger"
        elif _drenando:
            inv_emoji, inv_txt, inv_tone = "🟡", "Drenando", "warning"
        elif _creciendo:
            inv_emoji, inv_txt, inv_tone = "🔵", "Creciendo", "info"
        else:
            inv_emoji, inv_txt, inv_tone = "🟢", "Estable", "success"

        _pam_p_cumple = [s["p_cumple_historico"] for s in (_pam1_stats, _pam2_stats) if s.get("p_cumple_historico") is not None]
        _pam_pct = (sum(_pam_p_cumple) / len(_pam_p_cumple) * 100.0) if _pam_p_cumple else None
        _confianza_txt = router_v2_result.get("confianza", "BAJA")
        _confianza_tone = {"ALTA": "success", "MEDIA": "warning", "BAJA": "danger"}.get(_confianza_txt, "danger")
        _cuello_activo = bottleneck.get("activo") or "Ninguno"

        # CAMBIO 11 (UX/UI v2 JdS, 2026-07-07): franja KPI ejecutiva —
        # Produccion esperada, Cumplimiento PAM, Autonomia minima, Riesgo
        # global, Confiabilidad, Cuello de botella + Estado del Inventario.
        # KPI grande + semaforo, sin tablas (reusa make_exec_summary_bar,
        # ya construida en ese formato).
        summary_items = [
            {
                "label": "Producción esperada",
                "value": f"{current_metrics['tph_total']:.0f} TPH",
                "meta": f"{current_metrics['tons']:.0f} t en {eval_h:.0f}h",
                "tone": "info",
            },
            {
                "label": "Cumplimiento PAM",
                "value": f"{_pam_pct:.0f}%" if _pam_pct is not None else "—",
                "meta": "prob. histórica de cumplir el mes" if _pam_pct is not None else "sin datos suficientes",
                "tone": "success" if (_pam_pct or 0) >= 70 else ("warning" if (_pam_pct or 0) >= 40 else "danger"),
            },
            {
                "label": "Autonomía mínima",
                "value": f"{autonomia_min_h:.1f} h",
                "meta": "la más restrictiva entre SAG1/SAG2",
                "tone": "success" if autonomia_min_h >= 2.5 else ("warning" if autonomia_min_h >= 1.0 else "danger"),
            },
            {
                "label": "Riesgo global",
                "value": action_label,
                "meta": f"IRO {sim['iro_result']['iro']:.0f}/100",
                "tone": action_tone,
            },
            {
                "label": "Confiabilidad",
                "value": _confianza_txt.title(),
                "meta": "de la recomendación",
                "tone": _confianza_tone,
            },
            {
                "label": "Cuello de botella",
                "value": _cuello_activo,
                "meta": bottleneck.get("severidad", "baja"),
                "tone": "danger" if bottleneck.get("severidad") == "alta" else (
                    "warning" if bottleneck.get("severidad") == "media" else "success"),
            },
            {
                "label": "Estado del Inventario",
                "value": f"{inv_emoji} {inv_txt}",
                "meta": f"SAG1 {pila1:.0f}%→{_p1_arr[-1]:.0f}% · SAG2 {pila2:.0f}%→{_p2_arr[-1]:.0f}%",
                "tone": inv_tone,
            },
        ]
        estado_card = make_estado_escenario_card(
            iro=float(sim["iro_result"]["iro"]),
            p_safe=float(p_safe_actual),
            autonomia_min_h=autonomia_min_h,
        )
        summary_bar = html.Div([estado_card, make_exec_summary_bar(summary_items)])

        tph1_delta, tph1_color = _fmt_delta(current_metrics["tph1_mean"], rec_metrics["tph1_mean"], "TPH", 0)
        tph2_delta, tph2_color = _fmt_delta(current_metrics["tph2_mean"], rec_metrics["tph2_mean"], "TPH", 0)
        a1_delta, a1_color = _fmt_delta(current_metrics["a1_min"], rec_metrics["a1_min"], "h", 1)
        a2_delta, a2_color = _fmt_delta(current_metrics["a2_min"], rec_metrics["a2_min"], "h", 1)
        risk_delta, risk_color = _fmt_delta(current_metrics["max_risk"], rec_metrics["max_risk"], "niv", 0, inverse_good=True)
        p1_delta, p1_color = _fmt_delta(current_metrics["pile1_end"], rec_metrics["pile1_end"], "%", 1)
        p2_delta, p2_color = _fmt_delta(current_metrics["pile2_end"], rec_metrics["pile2_end"], "%", 1)
        ton_delta, ton_color = _fmt_delta(current_metrics["tons"], rec_metrics["tons"], "t", 0)

        mobo1_actual, mobo1_rec = _bola_label_short(bolas_sag1, "SAG1"), _bola_label_short(rec_bolas1, "SAG1")
        mobo2_actual, mobo2_rec = _bola_label_short(bolas_sag2, "SAG2"), _bola_label_short(rec_bolas2, "SAG2")

        # CAMBIO 4 (UX/UI v2 JdS, 2026-07-07): orden y filas exactas del
        # prompt — SAG1 TPH, SAG2 TPH, MoBo SAG1, MoBo SAG2, Autonomia
        # SAG1/SAG2, Riesgo. Se agregan Pila final y Toneladas como filas
        # adicionales (informacion ya calculada, no se descarta).
        compare_rows = [
            {"label": "SAG1 TPH", "actual": f"{current_metrics['tph1_mean']:.0f}", "recommended": f"{rec_metrics['tph1_mean']:.0f}", "delta": tph1_delta, "delta_color": tph1_color},
            {"label": "SAG2 TPH", "actual": f"{current_metrics['tph2_mean']:.0f}", "recommended": f"{rec_metrics['tph2_mean']:.0f}", "delta": tph2_delta, "delta_color": tph2_color},
            {"label": "MoBo SAG1", "actual": mobo1_actual, "recommended": mobo1_rec, "delta": "", "delta_color": VERDE if mobo1_actual != mobo1_rec else "#999"},
            {"label": "MoBo SAG2", "actual": mobo2_actual, "recommended": mobo2_rec, "delta": "", "delta_color": VERDE if mobo2_actual != mobo2_rec else "#999"},
            {"label": "Autonomia SAG1", "actual": f"{current_metrics['a1_min']:.1f} h", "recommended": f"{rec_metrics['a1_min']:.1f} h", "delta": a1_delta, "delta_color": a1_color},
            {"label": "Autonomia SAG2", "actual": f"{current_metrics['a2_min']:.1f} h", "recommended": f"{rec_metrics['a2_min']:.1f} h", "delta": a2_delta, "delta_color": a2_color},
            {"label": "Riesgo", "actual": f"{current_metrics['max_risk']}", "recommended": f"{rec_metrics['max_risk']}", "delta": risk_delta, "delta_color": risk_color},
            {"label": "Pila final SAG1", "actual": f"{current_metrics['pile1_end']:.1f}%", "recommended": f"{rec_metrics['pile1_end']:.1f}%", "delta": p1_delta, "delta_color": p1_color},
            {"label": "Pila final SAG2", "actual": f"{current_metrics['pile2_end']:.1f}%", "recommended": f"{rec_metrics['pile2_end']:.1f}%", "delta": p2_delta, "delta_color": p2_color},
            {"label": "Toneladas esperadas", "actual": f"{current_metrics['tons']:.0f}", "recommended": f"{rec_metrics['tons']:.0f}", "delta": ton_delta, "delta_color": ton_color},
        ]
        compare_note = (
            "Recomendado operativo inmediato segun bandas del simulador y reglas de bolas. "
            "La optimizacion completa sigue disponible en 'Optimo segun pila' y Monte Carlo."
        )
        if sim.get("alerta_bola_sag1", False):
            compare_note += " SAG1 mantiene la restriccion dominante de inventario, por lo que conviene proteger pila antes de cargar mas el circuito."
        compare_block = make_compact_compare_table("Actual vs Recomendado", compare_rows, compare_note)

        # CAMBIO 7 (UX/UI v2 JdS, 2026-07-07): "¿Voy a cumplir el mes?" —
        # produccion proyectada vs meta PAM con banda P10/P50/P90.
        _proy_sag1 = get_pam_monthly_projection("SAG1")
        _proy_sag2 = get_pam_monthly_projection("SAG2")
        fig_pam_proyeccion = make_pam_projection_chart(_proy_sag1, "SAG1")

        main_fig_map = {
            "pilas": fig_pile,
            "tph": fig_tph,
            "riesgo": fig_risk,
            "alimentacion": fig_chancado,
            "balance_t1t3": fig_balance_t3,
            "cuellos_botella": fig_bottleneck,
            "planificador_turno": fig_turno,
            "cumplimiento_pam": fig_pam_proyeccion,
            "sensibilidad": fig_sens,
        }
        if main_view == "robustez_mc":
            fig_selected = _mc_frontier_or_placeholder(mc_results_cached)
        else:
            fig_selected = main_fig_map.get(main_view, fig_pile)
        # CAMBIO 12: el grafico T1/CV (balance_t1t3) necesita +50% de altura
        # vs el resto (420 -> 640) para las zonas de fondo + anotaciones.
        _main_height = 640 if main_view == "balance_t1t3" else 420
        fig_main = _clone_figure(fig_selected, _main_height)
        sensitivity_explanation = _sensitivity_explanation(rate1_tph, rate2_tph, duracion_t8, current_metrics)
        main_view_explanation = sensitivity_explanation if main_view == "sensibilidad" else ""

        # Fase 8: si "Recomendacion vigente" no esta disponible (sin
        # recomendacion generada aun, o desactualizada), avisar en vez de
        # dejar el grafico de "Simulacion actual" sin explicacion de por
        # que no es lo que el usuario pidio ver.
        if modo_vista_no_disponible:
            aviso_modo = ("Recomendación vigente no disponible. Recalcule la recomendación para "
                          "este escenario (mostrando Simulación actual).")
            main_view_explanation = f"{aviso_modo} {main_view_explanation}".strip()

        # Fase 10/12: diagnostico fisico de recuperacion post-T8 (Qin vs
        # Qout al terminar la ventana) — ver engine/balance_diagnostics.py.
        balance_post_t8 = None
        if duracion_t8 > 0:
            from engine.balance_diagnostics import compute_post_t8_balance, explain_post_t8
            balance_post_t8 = compute_post_t8_balance(sim, duracion_t8)
            if balance_post_t8 and main_view in ("pilas", "riesgo"):
                main_view_explanation = f"{main_view_explanation} {explain_post_t8(balance_post_t8)}".strip()

        # Overflow/rechazo registrado (Reglas 6-7, engine/circuit_state.py) —
        # antes se descartaba en silencio en el clip de step_pile(); ahora se
        # avisa explicitamente si hubo alimentacion rechazada por capacidad.
        _ovf1_total = sum(sim.get("overflow_sag1") or [])
        _ovf2_total = sum(sim.get("overflow_sag2") or [])
        if _ovf1_total > 1.0 or _ovf2_total > 1.0:
            _ovf_partes = []
            if _ovf1_total > 1.0:
                _ovf_partes.append(f"SAG1 rechazó ~{_ovf1_total:.0f} t por overflow")
            if _ovf2_total > 1.0:
                _ovf_partes.append(f"SAG2 rechazó ~{_ovf2_total:.0f} t por overflow")
            main_view_explanation = f"{main_view_explanation} {' · '.join(_ovf_partes)}.".strip()
        fig_autonomia = _clone_figure(fig_autonomia, 300)
        fig_bolas = _clone_figure(fig_bolas, 220)
        fig_chancado = _clone_figure(fig_chancado, 300)
        fig_sens = _clone_figure(fig_sens, 300)

        # Store para What-If
        plant_state = dict(pila_sag1=pila1, pila_sag2=pila2,
                           rate_sag1=rate1_tph, rate_sag2=rate2_tph,
                           cv315=cv315_init, cv316=cv316_init)

        # Badge "Restricciones Operacionales" — R16: al menos 1 molino de
        # bolas activo por SAG.
        r16_violacion = ((bolas_sag1 == "sin_bola" and sag1_on) or
                          (bolas_sag2 == "sin_bola" and sag2_on) or
                          r16_conflicto_sag1 or r16_conflicto_sag2)
        r16_badge = dbc.Badge(
            "R16 ✗" if r16_violacion else "R16 ✓",
            color="danger" if r16_violacion else "success",
            style={"fontSize": "0.62rem", "whiteSpace": "nowrap"},
            title="Al menos 1 molino de bolas activo por SAG",
        )

        try:
            import getpass
            from utils.usage_logger import log_event
            log_event("simulacion_disparada", vista_activa=main_view,
                      regimen_activo=router_v2_result.get("regimen_elegido"),
                      usuario=getpass.getuser(),
                      tiempo_total_seg=round(_time.perf_counter() - _t0_sim, 2))
        except Exception:
            pass

        try:
            from utils.scenario_state import save_last_scenario
            save_last_scenario({
                "pila1": pila1, "pila2": pila2, "duracion_t8": duracion_t8,
                "rate1_tph": rate1_tph, "rate2_tph": rate2_tph,
                "bolas_sag1": bolas_sag1, "bolas_sag2": bolas_sag2, "turno": turno,
                "regimen_activo": router_v2_result.get("regimen_elegido"),
            })
        except Exception:
            pass

        # Validacion Operacional Real (cierre de brechas, 2026-07-07):
        # snapshot completo del escenario, usado por Fase 2 ("Validar
        # escenario real") y Fase 10 (formulario jefe de sala) — se arma
        # aca porque todos estos valores ya estan calculados, no se
        # recalcula nada solo para el snapshot.
        # pila_sag1_pct/tph_sag1 se leen de `sim` (no de pila1/rate1_tph
        # directamente) para que el snapshot sea consistente incluso en
        # modo "Recomendacion vigente", donde `sim` puede ser una
        # re-simulacion con parametros congelados distintos de los
        # inputs actuales de la sidebar.
        snapshot_caso = {
            "pila_sag1_pct": sim.get("pile_sag1", [pila1])[0], "pila_sag2_pct": sim.get("pile_sag2", [pila2])[0],
            "tph_sag1": sim.get("rate_sag1_tph_actual", rate1_tph), "tph_sag2": sim.get("rate_sag2_tph_actual", rate2_tph),
            "t1_tph": sim.get("t1_tph"), "cv315_tph": sim.get("cv315", [None])[0] if sim.get("cv315") else None,
            "cv316_tph": sim.get("cv316", [None])[0] if sim.get("cv316") else None,
            "t3_tph": sim.get("t3_tph"),
            "duracion_t8_h": duracion_t8, "turno": turno,
            "mantenciones": {k: v for k, v in {
                "sag1": mant_sag1, "sag2": mant_sag2, "411": mant_411, "412": mant_412,
                "511": mant_511, "512": mant_512, "ch1": mant_ch1, "ch2": mant_ch2,
                "cv315": mant_cv315, "cv316": mant_cv316, "t1": mant_t1, "t3": mant_t3,
            }.items() if v and v != [0, 0]},
            "regimen": router_v2_result.get("regimen_elegido"),
            "recomendacion": router_v2_result.get("explicacion"),
        }

        # ── Rediseño JdS (2026-07-13): 6 bloques de la vista principal ──────
        # (ver 04_Reports/Technical/20260713_Rediseno_Autonomia_Pilas_JDS.md)
        # Reusa lo ya calculado arriba (sim, current_metrics, rec_metrics,
        # recommended_rate1/2, rec_bolas1/2, recovery, iro, p_safe_actual,
        # autonomia_min_h) — no se recalcula nada innecesariamente.
        def _estado_txt(a1_min, a2_min, iro_val, p_safe_val):
            amin = min(a1_min, a2_min)
            if iro_val >= 60 or p_safe_val < 0.6 or amin < 1.0:
                return "Acción requerida"
            if iro_val >= 30 or p_safe_val < 0.85 or amin < 2.0:
                return "Atención"
            return "Sostenible"

        estado_general_card = make_estado_general_card(
            iro=float(sim["iro_result"]["iro"]), p_safe=float(p_safe_actual),
            autonomia_min_h=autonomia_min_h,
        )
        _estado_global = _estado_txt(current_metrics["a1_min"], current_metrics["a2_min"],
                                      float(sim["iro_result"]["iro"]), float(p_safe_actual))
        autonomia_sag1_card = make_autonomia_resumen_card(
            "SAG1", current_metrics["a1_min"], sim.get("t_critico_sag1_h"),
            float(_p1_arr.min()), _estado_global,
            dependency_message=sim.get("dependency_message_sag1", ""),
            diverge_flag=bool(sim.get("autonomy_diverges_sag1")),
            diverge_diff_h=sim.get("autonomy_diff_sag1_h"),
            dynamic_status=sim.get("dynamic_net_autonomy_sag1_status"),
            dynamic_hours=sim.get("dynamic_net_autonomy_sag1_h"),
            dynamic_message=sim.get("dynamic_net_autonomy_sag1_message", ""),
            vulnerability=sim.get("historical_vulnerability_sag1"),
            divergence_class=sim.get("autonomy_divergence_class_sag1"),
        )
        autonomia_sag2_card = make_autonomia_resumen_card(
            "SAG2", current_metrics["a2_min"], sim.get("t_critico_sag2_h"),
            float(_p2_arr.min()), _estado_global,
            dependency_message=sim.get("dependency_message_sag2", ""),
            diverge_flag=bool(sim.get("autonomy_diverges_sag2")),
            dynamic_status=sim.get("dynamic_net_autonomy_sag2_status"),
            dynamic_hours=sim.get("dynamic_net_autonomy_sag2_h"),
            dynamic_message=sim.get("dynamic_net_autonomy_sag2_message", ""),
            vulnerability=sim.get("historical_vulnerability_sag2"),
            divergence_class=sim.get("autonomy_divergence_class_sag2"),
            diverge_diff_h=sim.get("autonomy_diff_sag2_h"),
        )

        recomendacion_corta = make_recomendacion_corta_table([
            {"linea": "SAG1", "rate_actual": f"{rate1_tph:.0f} TPH",
             "rate_recomendado": f"{recommended_rate1:.0f} TPH", "mobos": mobo1_rec},
            {"linea": "SAG2", "rate_actual": f"{rate2_tph:.0f} TPH",
             "rate_recomendado": f"{recommended_rate2:.0f} TPH", "mobos": mobo2_rec},
        ])

        recuperacion_card = make_recuperacion_card(
            fin_restriccion_h=(duracion_t8 if duracion_t8 > 0 else None), recovery=recovery,
        )

        try:
            quick_wins_list = evaluate_quick_wins(dict(
                pila_sag1_pct=pila1, pila_sag2_pct=pila2, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
                bolas_sag1=bolas_sag1, bolas_sag2=bolas_sag2, sag1_activo=sag1_on, sag2_activo=sag2_on,
                duracion_t8_h=duracion_t8, correa315_estado=c315, correa316_estado=c316,
                horizonte_horas=horizonte, ch1_on=ch1_on, ch2_on=ch2_on, cv_mode=cv_mode,
                cv315_manual_tph=cv315_manual, cv316_manual_tph=cv316_manual,
                rate_sag1_tph=rate1_tph, rate_sag2_tph=rate2_tph, t1_mode=t1_mode,
                t1_manual_tph=t1_manual_val, t3_frac=t3_frac, distribucion_t1=distribucion_t1,
            ), sim_base=sim)
        except Exception:
            quick_wins_list = []
        quick_win_card_ui = make_quick_win_card(
            quick_wins_list[0] if quick_wins_list else None, quick_wins_list[1:3],
        )

        fig_qin_qout = make_qin_qout_chart(sim, horizonte)
        # Sincroniza el eje de horas con el gráfico principal (mismo
        # _tickvals/_ticktext ya calculado arriba a partir de base_hour) —
        # sin esto, "¿Por qué crece o drena?" mostraba horas relativas
        # 0-24 mientras el gráfico principal ya mostraba hora de reloj
        # (ej. 08:00...08:00 del día siguiente), desincronizados entre sí.
        fig_qin_qout.update_xaxes(tickvals=_tickvals, ticktext=_ticktext)

        # Escenario "alternativo" (sección 9) — generado automáticamente,
        # no editable a mano: se re-rankea Actual/Recomendado/Producción
        # máxima (P90 ambos MoBos) con engine.rate_recommendation, mismo
        # orden de prioridad estricto que decide el bloque 6.4. Usa
        # simulate_scenario_cached (ya cacheada) en vez de una busqueda V3
        # completa para no empeorar el SLA de 3s (ver nota Requisito 8).
        cand_actual = {"r1": rate1_tph, "r2": rate2_tph, "b1": bolas_sag1, "b2": bolas_sag2,
                       "a1_min": current_metrics["a1_min"], "a2_min": current_metrics["a2_min"],
                       "tph_mean": current_metrics["tph1_mean"] + current_metrics["tph2_mean"]}
        cand_recomendado = {"r1": recommended_rate1, "r2": recommended_rate2,
                             "b1": rec_bolas1, "b2": rec_bolas2,
                             "a1_min": rec_metrics["a1_min"], "a2_min": rec_metrics["a2_min"],
                             "tph_mean": rec_metrics["tph1_mean"] + rec_metrics["tph2_mean"]}
        try:
            sim_prod_max = simulate_scenario_cached(
                pila_sag1_pct=pila1, pila_sag2_pct=pila2, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
                bolas_sag1="ambas_411_412", bolas_sag2="ambas_511_512",
                sag1_activo=sag1_on, sag2_activo=sag2_on, duracion_t8_h=duracion_t8,
                correa315_estado=c315, correa316_estado=c316, horizonte_horas=horizonte,
                ch1_on=ch1_on, ch2_on=ch2_on, cv_mode=cv_mode,
                cv315_manual_tph=cv315_manual, cv316_manual_tph=cv316_manual,
                rate_sag1_tph=float(P90["SAG1"]), rate_sag2_tph=float(P90["SAG2"]),
                t1_mode=t1_mode, t1_manual_tph=t1_manual_val, t3_frac=t3_frac,
                distribucion_t1=distribucion_t1,
            )
            _prod_metrics = _extract_eval_metrics(sim_prod_max, eval_h)
            cand_prod_max = {"r1": float(P90["SAG1"]), "r2": float(P90["SAG2"]),
                              "b1": "ambas_411_412", "b2": "ambas_511_512",
                              "a1_min": _prod_metrics["a1_min"], "a2_min": _prod_metrics["a2_min"],
                              "tph_mean": _prod_metrics["tph1_mean"] + _prod_metrics["tph2_mean"]}
        except Exception:
            cand_prod_max = None

        candidatos_9 = [cand_actual, cand_recomendado] + ([cand_prod_max] if cand_prod_max else [])
        ranked_9 = rank_candidates(candidatos_9, rate1_tph, rate2_tph)
        alternativo_9 = next((c for c in ranked_9 if c is not cand_actual and c is not cand_recomendado), None)

        def _mobo_txt(b1, b2):
            return f"SAG1 {_bola_label_short(b1, 'SAG1')} / SAG2 {_bola_label_short(b2, 'SAG2')}"

        def _riesgo_txt(a1_min, a2_min):
            return "Alto" if min(a1_min, a2_min) < 1.0 else ("Medio" if min(a1_min, a2_min) < 2.0 else "Bajo")

        # Segunda iteración UX/UI (2026-07-14): bloque de decisión
        # principal — reusa datos ya calculados arriba (_estado_global,
        # router_v2_result, quick_wins_list, restriction_reason_sagX de
        # sim, _riesgo_txt), sin logica fisica nueva.
        _circuito_restrictivo = "SAG1" if current_metrics["a1_min"] <= current_metrics["a2_min"] else "SAG2"
        _molino_restrictivo = "Molino 401" if _circuito_restrictivo == "SAG1" else "Molino 501"
        _reason_key = sim.get(f"restriction_reason_sag{'1' if _circuito_restrictivo == 'SAG1' else '2'}")
        _causa_txt = RESTRICTION_REASON_LABEL_JDS.get(_reason_key, _reason_key or "sin restricción detectada")
        _t_crit_restrictivo = sim.get("t_critico_sag1_h" if _circuito_restrictivo == "SAG1" else "t_critico_sag2_h")
        _horizonte_txt = (
            f"{_t_crit_restrictivo:.1f} h hasta nivel crítico" if _t_crit_restrictivo is not None
            else f"autonomía {min(current_metrics['a1_min'], current_metrics['a2_min']):.1f} h"
        )
        if quick_wins_list:
            _qw0 = quick_wins_list[0]
            _accion_txt = f"{_qw0.titulo} — +{_qw0.delta_historical_buffer_h:.1f} h colchón preventivo"
        else:
            _accion_txt = router_v2_result.get("explicacion") or "Mantener configuración actual."
        decision_banner_ui = make_decision_banner(
            estado=_estado_global,
            circuito_afectado=_circuito_restrictivo,
            molino_afectado=_molino_restrictivo,
            horizonte_txt=_horizonte_txt,
            causa=_causa_txt,
            accion_txt=_accion_txt,
            severidad=_riesgo_txt(current_metrics["a1_min"], current_metrics["a2_min"]),
            confianza=router_v2_result.get("confianza", "BAJA"),
        )
        confianza_card_ui = make_confianza_card(
            router_v2_result.get("confianza", "BAJA"),
            METODO_LABEL_JDS.get(router_v2_result.get("regimen_elegido"), "Router adaptativo"),
        )

        _hora_rec_txt = "—"
        if recovery:
            _horas = [r.hora_recuperacion_h for r in recovery.values() if r and r.hora_recuperacion_h is not None]
            if _horas:
                _hora_rec_txt = f"{min(_horas):.1f} h"

        scenario_compare_rows = [
            {"label": "Autonomía mínima",
             "actual": f"{cand_actual['a1_min']:.1f}/{cand_actual['a2_min']:.1f} h",
             "recomendado": f"{cand_recomendado['a1_min']:.1f}/{cand_recomendado['a2_min']:.1f} h",
             "alternativo": (f"{alternativo_9['a1_min']:.1f}/{alternativo_9['a2_min']:.1f} h" if alternativo_9 else "—")},
            {"label": "Pila mínima SAG1", "actual": f"{_p1_arr.min():.0f}%",
             "recomendado": f"{rec_metrics['pile1_end']:.0f}%", "alternativo": "—"},
            {"label": "Pila mínima SAG2", "actual": f"{_p2_arr.min():.0f}%",
             "recomendado": f"{rec_metrics['pile2_end']:.0f}%", "alternativo": "—"},
            {"label": "Hora de recuperación", "actual": _hora_rec_txt,
             "recomendado": _hora_rec_txt, "alternativo": "—"},
            {"label": "Producción total",
             "actual": f"{cand_actual['tph_mean']:.0f} TPH",
             "recomendado": f"{cand_recomendado['tph_mean']:.0f} TPH",
             "alternativo": (f"{alternativo_9['tph_mean']:.0f} TPH" if alternativo_9 else "—")},
            {"label": "Riesgo de vaciado",
             "actual": _riesgo_txt(cand_actual["a1_min"], cand_actual["a2_min"]),
             "recomendado": _riesgo_txt(cand_recomendado["a1_min"], cand_recomendado["a2_min"]),
             "alternativo": (_riesgo_txt(alternativo_9["a1_min"], alternativo_9["a2_min"]) if alternativo_9 else "—")},
            {"label": "Configuración MoBos",
             "actual": _mobo_txt(bolas_sag1, bolas_sag2),
             "recomendado": _mobo_txt(rec_bolas1, rec_bolas2),
             "alternativo": (_mobo_txt(alternativo_9["b1"], alternativo_9["b2"]) if alternativo_9 else "—")},
        ]
        scenario_compare_ui = make_scenario_compare_table(scenario_compare_rows)

        try:
            from utils.perf_logger import log_duration
            log_duration("update_simulation_total", (_time.perf_counter() - _t0_sim) * 1000.0, vista=main_view)
        except Exception:
            pass

        from utils.state_schema import make_envelope
        return (fig_main, main_view_explanation, fig_autonomia, fig_bolas, fig_chancado, summary_bar,
                compare_block, kpis, fig_sens, sensitivity_explanation, fig_gantt, r16_badge,
                make_envelope(plant_state), make_envelope(snapshot_caso), banner_desactualizada,
                estado_general_card, autonomia_sag1_card, autonomia_sag2_card, recomendacion_corta,
                recuperacion_card, quick_win_card_ui, fig_qin_qout, scenario_compare_ui,
                decision_banner_ui, confianza_card_ui)

    @app.callback(
        Output("main-graph-modal", "is_open"),
        Output("graph-main-modal", "figure"),
        Input("btn-expand-main", "n_clicks"),
        Input("btn-close-main-modal", "n_clicks"),
        State("main-graph-modal", "is_open"),
        State("graph-main", "figure"),
        prevent_initial_call=True,
    )
    def toggle_main_graph_modal(open_clicks, close_clicks, is_open, main_figure):
        trigger = ctx.triggered_id
        figure = _clone_figure(main_figure or go.Figure(), 680)
        if trigger == "btn-expand-main":
            return True, figure
        if trigger == "btn-close-main-modal":
            return False, figure
        return is_open, figure
