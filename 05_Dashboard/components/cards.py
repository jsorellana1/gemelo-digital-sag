"""
cards.py — Tarjetas KPI para el panel derecho del Simulador Operacional
"""

from __future__ import annotations
import dash_bootstrap_components as dbc
from dash import html

from engine.ode_model import CRITICAL_PCT as _CRITICAL_PCT, DRAIN_PCT_H as _DRAIN_RATE

# ── Paleta TDA (Plataforma TDA_Diseño_Visual_Elegido.html, 2026-07-07) ────────
# Ver components/graphs.py para la nota completa sobre el origen de esta
# paleta (unico contenido legible del template: el wireframe SVG de
# carga). Mismo mapeo de roles que en graphs.py.
AZUL     = "#F0F4FA"   # texto principal (antes navy oscuro sobre card blanca)
AZUL_MED = "#4FB0E5"
VERDE    = "#4FCE82"
NARANJA  = "#E8935A"
ROJO     = "#E94A4A"
AMARILLO = "#E5BB3E"
BG_CARD  = "#0F2647"   # panel oscuro TDA (antes: "white")
BORDE_CARD = "#1a3a6c"
TEXTO_MUTED = "#8896AF"
# Verificado con script WCAG (2026-07-14, segunda iteracion UX/UI): ROJO
# (#E94A4A) da 3.99:1 sobre BG_CARD — pasa AA solo en texto grande
# (>=18.66px negrita). Para texto pequeño en negrita (ej. valor de
# severidad en el Decision Banner) se usa esta variante mas clara,
# 4.70:1, que si cumple AA de texto normal.
ROJO_TEXTO_PEQUENO = "#F0605C"


# _DRAIN_RATE/_CRITICAL_PCT importados de engine.ode_model (unica fuente
# de verdad calibrada) para evitar que esta copia diverja silenciosamente
# si los parametros se recalibran (ver 06_Documentation/cleanup_log.md,
# 2026-07-15).
# Thresholds asimetricos: SAG1 tight (max 3.58h), SAG2 wide (max 13.24h)
_AMBER_THR = {"SAG1": 1.5,  "SAG2": 2.5}
_GREEN_THR = {"SAG1": 2.5,  "SAG2": 4.0}


def _autonomia_color(h: float, asset: str = "SAG2") -> str:
    """Color asimetrico: SAG1 amber en 1.5h, verde en 2.5h. SAG2 amber en 2.5h, verde en 4h."""
    if h < 1.0:
        return ROJO
    if h < _AMBER_THR[asset]:
        return ROJO
    if h < _GREEN_THR[asset]:
        return AMARILLO
    return VERDE


def _pile_color(pct: float, critical: float) -> str:
    if pct <= critical:
        return ROJO
    if pct <= critical + 5:
        return NARANJA
    if pct <= 40.0:
        return AMARILLO
    return VERDE


def _fmt_auton_display(h: float, asset: str) -> tuple[str, str]:
    """Retorna (valor_display, unidad_display)."""
    if asset == "SAG1" and h < 2.0:
        return f"{int(h * 60)}", "min"
    return f"{h:.1f}", "h"


def make_autonomia_card(asset: str, autonomia_h: float, pile_pct: float, regime: str,
                        min_autonomia_h: float = None, activo: bool = True) -> dbc.Card:
    critical = _CRITICAL_PCT[asset]
    p_color  = _pile_color(pile_pct, critical)
    drain    = _DRAIN_RATE[asset]
    asset_name = "Molino 401" if asset == "SAG1" else "Molino 501"

    if not activo:
        color = TEXTO_MUTED
        val_str, unit_str = "DETENIDO", ""
    else:
        color = _autonomia_color(autonomia_h, asset)
        val_str, unit_str = _fmt_auton_display(autonomia_h, asset)

    # Badge de sensibilidad
    sensitivity = "ALTA" if asset == "SAG1" else "BAJA"
    sens_color  = NARANJA if asset == "SAG1" else VERDE

    # Pile hasta zona segura
    pile_safe = (_GREEN_THR[asset] * drain + critical)  # pile% para llegar a VERDE
    pile_delta = pile_safe - pile_pct

    # Min autonomia del horizonte simulado (solo si SAG activo)
    min_row = []
    if activo and min_autonomia_h is not None:
        min_val, min_unit = _fmt_auton_display(min_autonomia_h, asset)
        min_color = _autonomia_color(min_autonomia_h, asset)
        min_row = [html.Div([
            html.Span("Min simulado: ", style={"fontSize": "0.68rem", "color": TEXTO_MUTED}),
            html.Span(f"{min_val} {min_unit}", style={"fontSize": "0.68rem", "fontWeight": "700", "color": min_color}),
        ])]

    return dbc.Card(
        dbc.CardBody([
            # Header: nombre + badge sensibilidad
            html.Div([
                html.Span(f"Autonomia {asset_name} ({asset})",
                          style={"fontSize": "0.73rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
                html.Span(f" {drain:.0f}%/h",
                          style={"fontSize": "0.68rem", "color": sens_color, "fontWeight": "700",
                                 "marginLeft": "6px",
                                 "border": f"1px solid {sens_color}", "borderRadius": "4px",
                                 "padding": "1px 4px"}),
            ], style={"display": "flex", "alignItems": "center"}),

            # Valor principal de autonomia
            html.Div([
                html.Span(val_str, style={"fontSize": "1.8rem", "fontWeight": "800", "color": color}),
                html.Span(f" {unit_str}", style={"fontSize": "0.9rem", "color": color, "fontWeight": "600"}),
            ], className="mt-1"),

            # Pila % + regimen
            html.Div([
                html.Span("Pila: ", style={"fontSize": "0.73rem", "color": TEXTO_MUTED}),
                html.Span(f"{pile_pct:.0f}%",
                          style={"fontSize": "0.73rem", "fontWeight": "700", "color": p_color}),
                html.Span("  |  ", style={"fontSize": "0.7rem", "color": TEXTO_MUTED}),
                html.Span(regime,
                          style={"fontSize": "0.7rem", "fontWeight": "600", "color": AZUL_MED}),
            ]),

            # Min autonomia
            *min_row,

            # Indicador de distancia a zona segura (solo si activo)
            *([] if not activo or pile_delta <= 0 else [
                html.Div(
                    f"Faltan {pile_delta:.0f}% pila para zona segura",
                    style={"fontSize": "0.67rem", "color": TEXTO_MUTED, "marginTop": "2px",
                           "fontStyle": "italic"},
                )
            ]),
        ], style={"padding": "10px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {color}",
            "borderRadius": "8px",
            "marginBottom": "6px",
            "borderLeft": f"5px solid {color}",
        }
    )


_HARMONY_COLOR = {"alta": VERDE, "media": AMARILLO, "baja": ROJO}


def make_harmony_card(harmony_result: dict) -> dbc.Card:
    """
    Tarjeta del Indice de Armonia Operacional (0-100), ver
    engine/harmony_index.py::compute_harmony_index(). harmony_result es el
    dict que retorna esa funcion (con 'harmony_index' y 'sub_scores').
    """
    from engine.harmony_index import harmony_label

    idx = harmony_result["harmony_index"]
    label = harmony_label(idx)
    color = _HARMONY_COLOR[label]
    sub = harmony_result.get("sub_scores", {})

    _NOMBRES_SUB = {
        "carga_relativa": "Carga relativa SAG1/SAG2",
        "autonomia": "Diferencia de autonomia",
        "riesgo": "Diferencia de riesgo",
        "variabilidad": "Variabilidad TPH",
        "mobos": "Uso de MoBos",
        "alimentacion": "Alimentacion CV315/CV316",
    }

    return dbc.Card(
        dbc.CardBody([
            html.Div(
                html.Span("Indice de Armonia Operacional",
                          style={"fontSize": "0.73rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
            ),
            html.Div([
                html.Span(f"{idx:.0f}", style={"fontSize": "1.8rem", "fontWeight": "800", "color": color}),
                html.Span(" / 100", style={"fontSize": "0.9rem", "color": color, "fontWeight": "600"}),
                html.Span(f"  {label.upper()}",
                          style={"fontSize": "0.7rem", "fontWeight": "700", "color": color,
                                 "marginLeft": "6px", "border": f"1px solid {color}",
                                 "borderRadius": "4px", "padding": "1px 4px"}),
            ], className="mt-1"),
            html.Div([
                html.Div([
                    html.Span(f"{_NOMBRES_SUB.get(k, k)}: ", style={"fontSize": "0.67rem", "color": TEXTO_MUTED}),
                    html.Span(f"-{v:.0f}", style={"fontSize": "0.67rem", "fontWeight": "600", "color": TEXTO_MUTED}),
                ]) for k, v in sub.items()
            ], style={"marginTop": "4px"}),
        ], style={"padding": "10px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {color}",
            "borderRadius": "8px",
            "marginBottom": "6px",
            "borderLeft": f"5px solid {color}",
        }
    )


def make_iro_card(iro_result: dict) -> dbc.Card:
    iro = iro_result["iro"]
    color = iro_result["color"]

    # Texto descriptivo
    if iro > 80:
        estado = "OPTIMO"
    elif iro > 60:
        estado = "ACEPTABLE"
    elif iro > 40:
        estado = "DEGRADADO"
    else:
        estado = "CRITICO"

    # Sub-scores
    subscores = [
        ("Inventario (25%)", iro_result["inventario_score"]),
        ("Autonomia (30%)",  iro_result["autonomia_score"]),
        ("Rate (20%)",       iro_result["rate_score"]),
        ("T8 (15%)",         iro_result["t8_score"]),
        ("Correa (10%)",     iro_result["correa_score"]),
    ]

    def _bar_color_name(v):
        # dbc.Progress "color" solo acepta nombres de tema Bootstrap, no
        # hex (bar_style/backgroundColor no son props validas en dbc
        # 2.0.4) — se mapea al nombre Bootstrap semanticamente mas
        # cercano a la paleta TDA en vez de al hex exacto.
        if v >= 80: return "success"
        if v >= 60: return "warning"
        if v >= 40: return "warning"
        return "danger"

    rows = []
    for label, val in subscores:
        rows.append(html.Div([
            html.Span(label, style={"fontSize": "0.68rem", "color": TEXTO_MUTED, "width": "115px", "display": "inline-block"}),
            dbc.Progress(value=val, max=100,
                         style={"height": "8px", "width": "80px", "display": "inline-block",
                                "backgroundColor": BORDE_CARD},
                         color=_bar_color_name(val),
                         className="align-middle"),
            html.Span(f" {val:.0f}", style={"fontSize": "0.68rem", "color": TEXTO_MUTED, "marginLeft": "4px"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "3px"}))

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Span("IRO", style={"fontSize": "0.75rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
                html.Span(f" — {estado}", style={"fontSize": "0.75rem", "color": color, "fontWeight": "700"}),
            ]),
            html.Div([
                html.Span(f"{iro:.0f}", style={"fontSize": "1.5rem", "fontWeight": "800", "color": color}),
                html.Span(" / 100", style={"fontSize": "0.72rem", "color": TEXTO_MUTED}),
            ], className="mt-1 mb-1"),
            *rows,
        ], style={"padding": "6px 8px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {color}",
            "borderRadius": "8px",
            "marginBottom": "5px",
            "borderLeft": f"3px solid {color}",
        }
    )


def make_rate_card(asset: str, rate_recomendado: str, rate_actual_tph: float) -> dbc.Card:
    from engine.ode_model import P90

    asset_name = "Molino 401" if asset == "SAG1" else "Molino 501"

    status_label = ""
    status_color = AZUL_MED
    try:
        parts = rate_recomendado.replace("%", "").split("-")
        lo_pct = float(parts[0])
        hi_pct = float(parts[1])
        actual_pct = rate_actual_tph / P90[asset] * 100.0
        if actual_pct > hi_pct + 2:
            status_label = "ALTO"
            status_color = ROJO
        elif actual_pct < lo_pct - 2:
            status_label = "BAJO"
            status_color = NARANJA
        else:
            status_label = "OK"
            status_color = VERDE
    except Exception:
        pass

    border_color = status_color if status_label else AZUL_MED

    return dbc.Card(
        dbc.CardBody([
            html.Span(f"Rate recomendado {asset_name} ({asset})",
                      style={"fontSize": "0.75rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
            html.Div([
                html.Span(rate_recomendado,
                          style={"fontSize": "1.0rem", "fontWeight": "700", "color": AZUL_MED}),
                html.Span(f"  {status_label}",
                          style={"fontSize": "0.68rem", "fontWeight": "700", "color": status_color,
                                 "marginLeft": "6px"}) if status_label else html.Span(),
            ], className="mt-1", style={"display": "flex", "alignItems": "center"}),
            html.Span(f"Actual: {rate_actual_tph:.0f} TPH",
                      style={"fontSize": "0.66rem", "color": TEXTO_MUTED}),
        ], style={"padding": "6px 8px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {border_color}",
            "borderLeft": f"3px solid {border_color}",
            "borderRadius": "8px",
            "marginBottom": "4px",
        }
    )


def make_t1_card(t1_tph: float, t3_tph: float, cap_chanc: float, restriccion: bool = False) -> dbc.Card:
    """Tarjeta de balance T1: disponible, T3 desvio, disponible para CV315/CV316."""
    disponible_cv = max(0.0, t1_tph - t3_tph)
    t3_pct = (t3_tph / t1_tph * 100) if t1_tph > 0 else 0.0

    if restriccion:
        border_color = ROJO
        estado = "RESTRINGIDO"
    elif t3_pct > 25:
        border_color = NARANJA
        estado = "T3 ALTO"
    elif t1_tph > 0:
        border_color = VERDE
        estado = "NORMAL"
    else:
        border_color = ROJO
        estado = "SIN FLUJO"

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Span("Transferencia T1", style={"fontSize": "0.75rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
                html.Span(f"  {estado}", style={"fontSize": "0.72rem", "fontWeight": "700", "color": border_color,
                                                  "marginLeft": "6px"}),
            ]),
            html.Div([
                html.Span(f"{t1_tph:,.0f}", style={"fontSize": "1.05rem", "fontWeight": "800", "color": border_color}),
                html.Span(" TPH", style={"fontSize": "0.68rem", "color": TEXTO_MUTED}),
            ], className="mt-1"),
            html.Div([
                html.Span("CV315+316: ", style={"fontSize": "0.66rem", "color": TEXTO_MUTED}),
                html.Span(f"{disponible_cv:,.0f} TPH", style={"fontSize": "0.66rem", "fontWeight": "700",
                                                                "color": AZUL_MED}),
            ]),
            html.Div([
                html.Span("T3 desvio: ", style={"fontSize": "0.66rem", "color": TEXTO_MUTED}),
                html.Span(f"{t3_tph:,.0f} TPH ({t3_pct:.0f}%)",
                          style={"fontSize": "0.66rem", "fontWeight": "700",
                                 "color": NARANJA if t3_pct > 15 else TEXTO_MUTED}),
            ]),
            html.Div(
                "Asignación inválida: CV315 + CV316 supera T1 disponible.",
                style={"fontSize": "0.62rem", "fontWeight": "700", "color": ROJO,
                       "marginTop": "2px"},
            ) if restriccion else None,
        ], style={"padding": "6px 8px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {border_color}",
            "borderLeft": f"3px solid {border_color}",
            "borderRadius": "8px",
            "marginBottom": "4px",
        }
    )


def make_bottleneck_card(bottleneck: dict) -> dbc.Card:
    """Tarjeta 'Cuello de Botella' — diagnostico de que activo limita la
    produccion hoy. Puramente descriptivo sobre campos ya calculados por
    simulate_scenario (ver engine/bottleneck.py); no introduce ninguna
    relacion causal nueva."""
    activo = bottleneck.get("activo")
    sev = bottleneck.get("severidad", "baja")
    color = {"alta": ROJO, "media": NARANJA, "baja": VERDE}.get(sev, VERDE)

    if activo is None:
        body = [
            html.Div("Cuello de Botella", style={"fontSize": "0.64rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
            html.Div("Sin restricción dominante", style={"fontSize": "0.68rem", "fontWeight": "700", "color": VERDE}),
        ]
    else:
        otros = bottleneck.get("otros", [])
        body = [
            html.Div("Cuello de Botella", style={"fontSize": "0.64rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
            html.Div(activo, style={"fontSize": "0.76rem", "fontWeight": "800", "color": color}),
            html.Div(bottleneck.get("motivo", ""), style={"fontSize": "0.6rem", "color": TEXTO_MUTED}),
        ]
        if otros:
            body.append(html.Div(
                "También: " + ", ".join(o["activo"] for o in otros),
                style={"fontSize": "0.58rem", "color": TEXTO_MUTED, "marginTop": "1px"},
            ))

    return dbc.Card(
        dbc.CardBody(body, style={"padding": "6px 8px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {color}",
            "borderLeft": f"3px solid {color}",
            "borderRadius": "8px",
            "marginBottom": "4px",
        }
    )


def make_pam_compliance_card(stats_sag1: dict, stats_sag2: dict) -> dbc.Card:
    """Tarjeta 'Cumplimiento PAM' — frecuencia historica real (2.6 anos,
    produccion_diaria_gpta.parquet) de cumplimiento del plan por linea.
    Responde '¿cumplire el PAM?' / '¿cual es el deficit esperado?' con
    evidencia historica agregada, NO con una prediccion del escenario
    simulado puntual (eso queda para una iteracion futura, ver Backlog).
    """
    if not stats_sag1 and not stats_sag2:
        return dbc.Card(
            dbc.CardBody(html.P("Sin datos históricos de PAM disponibles.",
                                style={"color": TEXTO_MUTED, "fontSize": "0.78rem"})),
            style={"marginBottom": "6px"},
        )

    def _linea(nombre, stats, color):
        if not stats:
            return html.Div(f"{nombre}: sin datos", style={"fontSize": "0.72rem", "color": TEXTO_MUTED})
        p = stats["p_cumple_historico"] * 100
        cump = stats["cumplimiento_medio_pct"]
        deficit = stats["deficit_medio_ton_dia"]
        p_color = VERDE if p >= 60 else (AMARILLO if p >= 40 else ROJO)
        return html.Div([
            html.Span(f"{nombre}: ", style={"fontWeight": "700", "color": color}),
            html.Span(f"cumple PAM {p:.0f}% de los días históricos ", style={"color": p_color, "fontWeight": "600"}),
            html.Span(f"(prom. {cump:.0f}% del plan, déficit medio {deficit:,.0f} t/día)",
                      style={"color": TEXTO_MUTED, "fontSize": "0.6rem"}),
        ], style={"fontSize": "0.66rem", "marginBottom": "3px"})

    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Cumplimiento PAM (histórico, 2.6 años)",
                        style={"fontSize": "0.68rem", "color": AZUL}),
            style={"padding": "4px 8px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody([
            _linea("SAG1", stats_sag1, AZUL_MED),
            _linea("SAG2", stats_sag2, NARANJA),
            html.Div("Frecuencia histórica de días — no es predicción del escenario actual.",
                     style={"fontSize": "0.58rem", "color": TEXTO_MUTED, "fontStyle": "italic", "marginTop": "2px"}),
        ], style={"padding": "5px 8px"}),
    ], style={"marginBottom": "4px", "border": f"1px solid {AZUL_MED}"})


def make_pam_probability_card(proy_sag1: dict, proy_sag2: dict) -> dbc.Card:
    """'¿Voy a cumplir el mes?' (CAMBIO 7, UX/UI v2 JdS, 2026-07-07) —
    probabilidad de cumplimiento mensual grande, un numero, sin jerga.
    Ver engine.production_stats.get_pam_monthly_projection."""
    def _bloque(nombre, proy, color):
        if not proy:
            return dbc.Col(html.Div(f"{nombre}: sin datos", style={"fontSize": "0.64rem", "color": TEXTO_MUTED}), width=6)
        p = proy["prob_cumple_mes"] * 100.0
        p_color = VERDE if p >= 70 else (AMARILLO if p >= 40 else ROJO)
        return dbc.Col([
            html.Div(nombre, style={"fontSize": "0.64rem", "color": color, "fontWeight": "700"}),
            html.Div(f"{p:.0f}%", style={"fontSize": "1.3rem", "fontWeight": "900", "color": p_color, "lineHeight": "1"}),
            html.Div("prob. de cumplir el mes", style={"fontSize": "0.56rem", "color": TEXTO_MUTED}),
        ], width=6, style={"textAlign": "center"})

    return dbc.Card([
        dbc.CardHeader(
            html.Strong("¿Voy a cumplir el mes?", style={"fontSize": "0.68rem", "color": AZUL}),
            style={"padding": "4px 8px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody([
            dbc.Row([_bloque("SAG1", proy_sag1, AZUL_MED), _bloque("SAG2", proy_sag2, NARANJA)]),
        ], style={"padding": "5px 8px"}),
    ], style={"marginBottom": "4px", "border": f"1px solid {AZUL_MED}"})


def make_simulation_logic_card(router_result: dict) -> dbc.Card:
    """Tarjeta 'Lógica de simulación activada' — muestra la clasificación
    de escenario y las heurísticas explicativas de engine.simulation_router.
    Es puramente informativa: el motor de simulación (ODE + Optimizer V3/V4
    + Monte Carlo) es el mismo para todo escenario, ver docstring de
    simulation_router.py sobre por qué no se despacha a modelos distintos."""
    scenario = router_result.get("scenario", {})
    heur_labels = router_result.get("heuristics_labels", [])
    tipo = "Mixto" if scenario.get("mixto") else scenario.get("principal", "normal").replace("_", " ").title()

    color_map = {
        "overflow": ROJO, "inventario_critico": ROJO, "mantenimiento": NARANJA,
        "alimentacion_restringida": NARANJA, "t8_larga": NARANJA,
        "t8_corta": AMARILLO, "normal": VERDE,
    }
    color = color_map.get(scenario.get("principal", "normal"), AZUL_MED)

    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Lógica de simulación activada", style={"fontSize": "0.8rem", "color": AZUL}),
            style={"padding": "6px 10px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody([
            html.Div([
                html.Span("Escenario: ", style={"fontSize": "0.75rem", "color": TEXTO_MUTED}),
                html.Span(tipo, style={"fontSize": "0.85rem", "fontWeight": "800", "color": color}),
            ]),
            html.Div([
                html.Span(l, style={
                    "fontSize": "0.66rem", "color": "white", "backgroundColor": AZUL_MED,
                    "borderRadius": "10px", "padding": "2px 7px", "marginRight": "4px",
                    "display": "inline-block", "marginTop": "4px",
                }) for l in heur_labels
            ]),
            html.Div(router_result.get("explicacion", ""),
                     style={"fontSize": "0.68rem", "color": TEXTO_MUTED, "marginTop": "6px", "fontStyle": "italic"}),
        ], style={"padding": "8px 10px"}),
    ], style={"marginBottom": "6px", "border": f"1px solid {color}"})


# Etiquetas de regimen en lenguaje operacional (CAMBIO 9, UX/UI v2 JdS,
# 2026-07-07) — nunca mostrar el slug tecnico (t8_corta, inventario_critico...)
# directamente al usuario final.
REGIMEN_LABEL_JDS = {
    "normal": "Operación normal",
    "t8_corta": "Ventana T8 corta",
    "t8_larga": "Ventana T8 larga",
    "inventario_critico": "Inventario crítico",
    "overflow": "Riesgo de rebalse",
    "mantenimiento": "Equipos en mantención",
    "alimentacion_restringida": "Alimentación restringida",
    "mixto": "Escenario combinado",
}

# Metodo de simulacion en lenguaje operacional (CAMBIO 3).
METODO_LABEL_JDS = {
    "normal": "Simulación determinística",
    "t8_corta": "Monte Carlo adaptativo",
    "t8_larga": "Monte Carlo adaptativo",
    "inventario_critico": "Monte Carlo + Riesgo",
    "overflow": "Monte Carlo + Riesgo",
    "mantenimiento": "Monte Carlo adaptativo",
    "alimentacion_restringida": "Monte Carlo adaptativo",
    "mixto": "Router adaptativo",
}


def _regimen_label(regimen_raw: str) -> str:
    base = regimen_raw.split("_SAG")[0] if "_SAG" in regimen_raw else regimen_raw
    for b in ("overflow", "inventario_critico"):
        if regimen_raw.startswith(b):
            base = b
    return REGIMEN_LABEL_JDS.get(base, base.replace("_", " "))


def _prioridad_txt(regimen_elegido: str) -> str:
    if regimen_elegido == "normal":
        return "maximizar la producción sostenible"
    if regimen_elegido == "overflow":
        return "estabilizar la pila y evitar el rebalse"
    return "la seguridad y la factibilidad operacional por sobre la máxima producción"


def build_explicacion_operador(router_v2_result: dict) -> str:
    """Auditoria post router v2 (2026-07-07): el prompt de arquitectura
    pidió una explicación de varias oraciones en lenguaje operador (p.ej.
    "Se usó estrategia de T8 larga porque..."), no solo la frase tecnica
    de una linea que `explicacion` ya traia. Reutiliza
    `RegimeCriticality.razones` (ya son strings legibles, ver
    criticality_scorer.py) en vez de inventar texto nuevo — mismo
    principio del resto del proyecto: no fabricar informacion."""
    criticidades = router_v2_result.get("criticidades", [])
    regimen_elegido = router_v2_result.get("regimen_elegido", "normal")
    if not criticidades:
        return f"{REGIMEN_LABEL_JDS.get(regimen_elegido, regimen_elegido)}."

    primary = criticidades[0]
    razon_primary = "; ".join(primary.get("razones") or []) or "es el régimen con mayor urgencia detectada"
    frases = [f"Se usó la estrategia de {_regimen_label(primary['regimen'])} porque {razon_primary}."]

    secundarios = [c for c in criticidades[1:] if c.get("urgency_score", 0) > 30.0]
    if secundarios:
        sec = secundarios[0]
        razon_sec = "; ".join(sec.get("razones") or []) or "también superó el umbral de urgencia"
        frases.append(f"Además, se activó {_regimen_label(sec['regimen'])} porque {razon_sec}.")

    frases.append(f"Por eso el sistema priorizó {_prioridad_txt(regimen_elegido)}.")
    return " ".join(frases)


_BALANCE_ESTADO_COLOR = {"recupera": VERDE, "plana": "#E5BB3E", "drena": ROJO}
_BALANCE_ESTADO_LABEL = {"recupera": "Recupera", "plana": "Plana", "drena": "Drenando"}


def make_balance_neto_card(balance: dict) -> dbc.Card:
    """KPI "Balance Neto de Pila" (Fase 11, cierre "Sincronizacion
    recomendacion/escenario", 2026-07-09): Qin/Qout/Balance en TPH por
    SAG evaluados justo al terminar la ventana T8 — ver
    engine/balance_diagnostics.py. Solo se muestra cuando hay T8 activa
    (sin T8 no hay "post-T8" que diagnosticar)."""
    filas = []
    for asset in ("SAG1", "SAG2"):
        b = balance.get(asset)
        if b is None:
            continue
        color = _BALANCE_ESTADO_COLOR.get(b.estado, TEXTO_MUTED)
        signo = "+" if b.balance_tph >= 0 else ""
        filas.append(html.Div([
            html.Span(f"{asset}: ", style={"fontSize": "0.66rem", "fontWeight": "700", "color": AZUL}),
            html.Span(f"Qin {b.qin_tph:.0f} · Qout {b.qout_tph:.0f} · Balance {signo}{b.balance_tph:.0f} TPH",
                      style={"fontSize": "0.64rem", "color": TEXTO_MUTED}),
            html.Span(f" {_BALANCE_ESTADO_LABEL.get(b.estado, b.estado)}",
                      style={"fontSize": "0.64rem", "fontWeight": "700", "color": color, "marginLeft": "4px"}),
        ], style={"marginTop": "2px"}))

    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Balance Neto de Pila (post T8)", style={"fontSize": "0.68rem", "color": AZUL}),
            style={"padding": "4px 8px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody(filas, style={"padding": "5px 8px"}),
    ], style={"marginBottom": "4px", "border": f"1px solid {BORDE_CARD}"})


def make_router_v2_card(router_v2_result: dict) -> dbc.Card:
    """Tarjeta 'Confiabilidad de la Recomendación' (CAMBIO 6, UX/UI v2 JdS,
    2026-07-07 — reemplaza el lenguaje tecnico "Router v2" de la version
    anterior de esta misma tarjeta). Semaforo simple + lenguaje operacional
    primero; el detalle tecnico (ranking de urgencia, regimen exacto) queda
    en un acordeon colapsado para quien lo necesite. NUNCA muestra MAE/R2/
    RMSE al usuario final (los oculta detras de "error histórico X%"), y
    NUNCA reporta validación histórica "OK" si esta fuera de tolerancia o
    no disponible (ver TAREA 5 de CIERRE DE BRECHAS POST ROUTER v2)."""
    regimen = router_v2_result.get("regimen_elegido", "normal")
    validation = router_v2_result.get("validation")
    backtest = router_v2_result.get("backtest_info", {})
    criticidades = router_v2_result.get("criticidades", [])
    confianza = router_v2_result.get("confianza", "BAJA")

    es_valido = getattr(validation, "es_valido", True) if validation is not None else True

    semaforo = {"ALTA": "🟢", "MEDIA": "🟡", "BAJA": "🔴"}.get(confianza, "🔴")
    confianza_txt = {"ALTA": "Alta confianza", "MEDIA": "Confianza media", "BAJA": "Baja confianza"}.get(
        confianza, "Baja confianza")
    confianza_color = {"ALTA": VERDE, "MEDIA": AMARILLO, "BAJA": ROJO}.get(confianza, ROJO)
    if not es_valido:
        confianza_color = ROJO

    regimen_label = REGIMEN_LABEL_JDS.get(regimen, regimen.replace("_", " ").title())
    metodo_label = METODO_LABEL_JDS.get(regimen, "Router adaptativo")

    # "Basado en" — SIN MAE/R2/RMSE, solo N eventos + disponibilidad +
    # error historico redondeado a % simple (CAMBIO 6).
    basado_en = []
    if backtest.get("historica_disponible"):
        from engine.historical_backtesting import run_backtest
        bt = run_backtest(regimen if regimen != "mixto" else backtest.get("regimen", "normal"))
        basado_en.append(f"{bt.n_eventos} eventos similares")
        basado_en.append("Backtesting disponible")
        if bt.pila_mae_sag1_pp is not None:
            basado_en.append(f"Error histórico ≈{bt.pila_mae_sag1_pp:.0f}%")
    else:
        n = backtest.get("n_eventos", 0)
        basado_en.append(f"{n} eventos similares (insuficiente)")
        basado_en.append("Backtesting no disponible")

    detalle_tecnico = dbc.Collapse([
        html.Div(f"Régimen técnico: {regimen}", style={"fontSize": "0.64rem", "color": TEXTO_MUTED}),
        html.Div([
            html.Div(f"{c['regimen']}: {c['urgency_score']:.0f}/100",
                      style={"fontSize": "0.64rem", "color": TEXTO_MUTED})
            for c in criticidades[:3]
        ]),
        html.Div(router_v2_result.get("explicacion", ""),
                 style={"fontSize": "0.66rem", "color": TEXTO_MUTED, "marginTop": "4px", "fontStyle": "italic"}),
    ], id="collapse-detalle-tecnico-confiabilidad", is_open=False, style={"marginTop": "6px"})

    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Confiabilidad de la Recomendación", style={"fontSize": "0.68rem", "color": AZUL}),
            style={"padding": "4px 8px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody([
            html.Div([
                html.Span(semaforo, style={"fontSize": "1.0rem", "marginRight": "4px"}),
                html.Span(confianza_txt, style={"fontSize": "0.76rem", "fontWeight": "800", "color": confianza_color}),
            ]),
            html.Div([
                html.Span("Escenario: ", style={"fontSize": "0.62rem", "color": TEXTO_MUTED}),
                html.Span(regimen_label, style={"fontSize": "0.64rem", "fontWeight": "700", "color": AZUL}),
            ], style={"marginTop": "2px"}),
            html.Div([
                html.Span("Método: ", style={"fontSize": "0.62rem", "color": TEXTO_MUTED}),
                html.Span(metodo_label, style={"fontSize": "0.64rem", "fontWeight": "700", "color": AZUL_MED}),
            ]),
            html.Div(build_explicacion_operador(router_v2_result),
                     style={"fontSize": "0.62rem", "color": TEXTO_MUTED, "marginTop": "4px", "lineHeight": "1.35"}),
            html.Div("Basado en: " + " · ".join(basado_en),
                     style={"fontSize": "0.58rem", "color": TEXTO_MUTED, "marginTop": "3px"}),
            html.Div(
                "Validación física OK" if es_valido else "⚠ Con alertas — revisar antes de aplicar",
                style={"fontSize": "0.58rem", "color": VERDE if es_valido else ROJO, "marginTop": "2px"},
            ),
            dbc.Button("Ver detalle técnico", id="btn-detalle-tecnico-confiabilidad",
                       size="sm", color="link",
                       style={"fontSize": "0.56rem", "padding": "1px 0", "marginTop": "2px"}),
            detalle_tecnico,
        ], style={"padding": "5px 8px"}),
    ], style={"marginBottom": "4px", "border": f"1px solid {confianza_color}"})


def make_action_banner(accion: str, explicacion: str) -> dbc.Card:
    from engine.rules_engine import ACTION_COLORS
    color = ACTION_COLORS.get(accion, AZUL)

    return dbc.Card(
        dbc.CardBody([
            html.Div(accion.replace("_", " "), style={
                "fontSize": "0.8rem", "fontWeight": "800",
                "color": "white", "textAlign": "center",
                "letterSpacing": "0.04em",
            }),
            html.Div(explicacion, style={
                "fontSize": "0.64rem", "color": "rgba(255,255,255,0.9)",
                "textAlign": "center", "marginTop": "3px",
            }),
        ], style={"padding": "6px 10px"}),
        style={
            "backgroundColor": color,
            "border": "none",
            "borderRadius": "8px",
            "marginBottom": "4px",
        }
    )


def make_chancado_card(cap_tph: float, alerta_cv: bool = False) -> dbc.Card:
    """Tarjeta de capacidad de chancado y restriccion CV."""
    if cap_tph >= 3500:
        color = VERDE
        estado = "NORMAL"
    elif cap_tph >= 1500:
        color = AMARILLO
        estado = "LIMITADO"
    elif cap_tph > 0:
        color = NARANJA
        estado = "CRITICO"
    else:
        color = ROJO
        estado = "DETENIDO"

    rest_color = ROJO if alerta_cv else VERDE
    rest_text = "ALERTA CV" if alerta_cv else "OK"

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Span("Chancado Primario", style={"fontSize": "0.66rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
            ]),
            html.Div([
                html.Span(f"{cap_tph:,.0f} TPH", style={
                    "fontSize": "1.05rem", "fontWeight": "700", "color": color
                }),
                html.Span(f"  {estado}", style={"fontSize": "0.64rem", "fontWeight": "700", "color": color}),
            ], className="mt-1"),
            html.Div([
                html.Span("Restriccion CV: ", style={"fontSize": "0.62rem", "color": TEXTO_MUTED}),
                html.Span(rest_text, style={"fontSize": "0.62rem", "fontWeight": "700", "color": rest_color}),
            ]),
        ], style={"padding": "6px 8px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {color}",
            "borderRadius": "8px",
            "marginBottom": "4px",
            "borderLeft": f"3px solid {color}",
        }
    )


def make_bolas_rec_card(asset: str, bolas_rec: int, alerta: bool, rate_tph: float,
                        accion: str = None) -> dbc.Card:
    """Tarjeta de bolas recomendadas para SAG."""
    asset_name = "Molino 401 (SAG1)" if asset == "SAG1" else "Molino 501 (SAG2)"
    bolas_names = "411/412" if asset == "SAG1" else "511/512"
    if accion in ("EMERGENCIA", "EVALUAR_DETENCION", "MINIMO_TECNICO"):
        color = ROJO
        label = "REVISAR"
    elif alerta:
        color = NARANJA
        label = "ALERTA"
    else:
        color = VERDE
        label = "OK"

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Span(f"Bolas rec. {asset_name}",
                          style={"fontSize": "0.64rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
            ]),
            html.Div([
                html.Span(f"{bolas_rec} bola(s) {bolas_names}",
                          style={"fontSize": "0.85rem", "fontWeight": "700", "color": color}),
            ], className="mt-1"),
            html.Div([
                html.Span(f"Rate: {rate_tph:.0f} TPH  ", style={"fontSize": "0.62rem", "color": TEXTO_MUTED}),
                html.Span(label, style={"fontSize": "0.62rem", "fontWeight": "700", "color": color}),
            ]),
        ], style={"padding": "6px 8px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {color}",
            "borderRadius": "8px",
            "marginBottom": "4px",
            "borderLeft": f"3px solid {color}",
        }
    )


def make_inventario_card(
    asset: str,
    rate_tph: float,
    feed_tph: float,
    pile_pct: float,
    cap_ton: float,
    crit_pct: float,
    activo: bool = True,
) -> dbc.Card:
    """
    Tarjeta de estado de inventario: DRENANDO / EQUILIBRIO / LLENANDO.
    Muestra autonomia (vaciado) o tiempo hasta overflow segun el regimen real.
    """
    cv_name    = "CV315" if asset == "SAG1" else "CV316"
    asset_name = "Molino 401" if asset == "SAG1" else "Molino 501"

    if not activo:
        border_color = TEXTO_MUTED
        estado       = "DETENIDO"
        tendencia    = "—"
        tend_color   = TEXTO_MUTED
        kpi_val_str  = "—"
        kpi_unit     = ""
        net_str      = ""
    else:
        net = rate_tph - feed_tph
        dh  = net / cap_ton * 100          # %/h  (+ drena, - llena)
        net_str = f"{net:+.0f} TPH"

        if abs(net) < 10:                  # EQUILIBRIO
            estado       = "EQUILIBRIO"
            border_color = AMARILLO
            tendencia    = "◆"
            tend_color   = AMARILLO
            kpi_val_str  = "Estable"
            kpi_unit     = ""

        elif net > 0:                      # DRENANDO → autonomia
            estado = "DRENANDO"
            if pile_pct <= crit_pct:
                auton_h = 0.0
            else:
                auton_h = (pile_pct - crit_pct) / dh
            if auton_h < 6:
                border_color = ROJO
            elif auton_h < 24:
                border_color = NARANJA
            else:
                border_color = VERDE
            if auton_h < 2.0:
                kpi_val_str = f"{int(auton_h * 60)}"
                kpi_unit    = "min autonomia"
            else:
                kpi_val_str = f"{auton_h:.1f}"
                kpi_unit    = "h autonomia"
            tendencia  = "⬇"
            tend_color = border_color

        else:                              # LLENANDO → tiempo hasta overflow
            estado     = "LLENANDO"
            remaining  = 100.0 - pile_pct
            fill_rate  = abs(dh)
            overflow_h = remaining / fill_rate if fill_rate > 0.001 else 9999.0
            if overflow_h < 6:
                border_color = ROJO
            elif overflow_h < 24:
                border_color = NARANJA
            else:
                border_color = VERDE
            kpi_val_str = f"{min(overflow_h, 999):.1f}" if overflow_h < 999 else ">999"
            kpi_unit    = "h overflow"
            tendencia   = "⬆"
            tend_color  = border_color

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Span(f"Inventario {asset_name} ({asset})",
                          style={"fontSize": "0.66rem", "color": TEXTO_MUTED, "fontWeight": "600"}),
                html.Span(f"  {cv_name}={feed_tph:.0f} TPH",
                          style={"fontSize": "0.6rem", "color": TEXTO_MUTED, "marginLeft": "3px"}),
            ]),
            html.Div([
                html.Span(tendencia,
                          style={"fontSize": "0.9rem", "fontWeight": "800",
                                 "color": tend_color, "marginRight": "4px"}),
                html.Span(kpi_val_str,
                          style={"fontSize": "1.15rem", "fontWeight": "800",
                                 "color": border_color}),
                html.Span(f"  {kpi_unit}",
                          style={"fontSize": "0.66rem", "color": border_color, "fontWeight": "600"}),
            ], className="mt-1", style={"display": "flex", "alignItems": "center"}),
            html.Div([
                html.Span(estado,
                          style={"fontSize": "0.62rem", "fontWeight": "700",
                                 "color": border_color,
                                 "border": f"1px solid {border_color}",
                                 "borderRadius": "4px", "padding": "0px 5px",
                                 "marginRight": "6px"}),
                html.Span(f"Pila {pile_pct:.0f}%  {net_str}",
                          style={"fontSize": "0.6rem", "color": TEXTO_MUTED}),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={"padding": "6px 8px"}),
        style={
            "backgroundColor": BG_CARD,
            "border": f"1px solid {border_color}",
            "borderRadius": "8px",
            "marginBottom": "4px",
            "borderLeft": f"3px solid {border_color}",
        },
    )


def make_kpi_column(sim_result: dict, rate_sag1: float, rate_sag2: float) -> dict:
    """Retorna un dict {'inventario', 'produccion', 'riesgo', 'pam'} con las
    tarjetas agrupadas por categoria (CAMBIO 5, UX/UI v2 JdS, 2026-07-07) —
    ya no una lista plana vertical. `make_cockpit_row()` arma la fila
    horizontal final; los llamadores que quieran agregar tarjetas
    adicionales (bottleneck, PAM, confiabilidad) las pasan a esa funcion
    en vez de `.append()` sobre una lista, ver pages/simulador_operacional.py."""
    from engine.ode_model import CAP_TON, CRITICAL_PCT

    pile1 = sim_result["pile_sag1"][0]
    pile2 = sim_result["pile_sag2"][0]
    min_a1 = sim_result.get("min_autonomia_sag1")
    min_a2 = sim_result.get("min_autonomia_sag2")

    cap_chanc = sim_result.get("chancado_cap_tph", 4000.0)
    cv315_0   = float(sim_result.get("cv315", [0])[0])
    cv316_0   = float(sim_result.get("cv316", [0])[0])
    alerta_cv = (cv315_0 + cv316_0) > (cap_chanc + 0.1)

    sag1_act = sim_result.get("sag1_activo", True)
    sag2_act = sim_result.get("sag2_activo", True)
    alerta_bola1 = sim_result.get("alerta_bola_sag1", False)
    alerta_bola2 = sim_result.get("alerta_bola_sag2", False)
    bolas_rec1   = sim_result.get("bolas_recomendadas_sag1", 2)
    bolas_rec2   = sim_result.get("bolas_recomendadas_sag2", 2)
    r1_tph = float(sim_result.get("rate_sag1_tph_actual", rate_sag1))
    r2_tph = float(sim_result.get("rate_sag2_tph_actual", rate_sag2))
    accion  = sim_result.get("accion_recomendada", "OPERACION_NORMAL")
    t1_tph  = sim_result.get("t1_tph", cap_chanc)
    t3_tph  = sim_result.get("t3_tph", 0.0)
    t1_rest = sim_result.get("t1_restriccion", False)

    return {
        "inventario": [
            make_inventario_card("SAG1", r1_tph, cv315_0, pile1,
                                 CAP_TON["SAG1"], CRITICAL_PCT["SAG1"], activo=sag1_act),
            make_inventario_card("SAG2", r2_tph, cv316_0, pile2,
                                 CAP_TON["SAG2"], CRITICAL_PCT["SAG2"], activo=sag2_act),
        ],
        "produccion": [
            make_chancado_card(cap_chanc, alerta_cv),
            make_t1_card(t1_tph, t3_tph, cap_chanc, t1_rest),
            make_bolas_rec_card("SAG1", bolas_rec1, alerta_bola1, r1_tph, accion=accion),
            make_bolas_rec_card("SAG2", bolas_rec2, alerta_bola2, r2_tph, accion=accion),
            make_rate_card("SAG1", sim_result.get("rate_recomendado_sag1", "N/A"), r1_tph),
            make_rate_card("SAG2", sim_result.get("rate_recomendado_sag2", "N/A"), r2_tph),
        ],
        "riesgo": [
            make_action_banner(accion, sim_result["explicacion"]),
            make_iro_card(sim_result["iro_result"]),
        ],
        "pam": [],
    }


def make_cockpit_row(groups: dict) -> html.Div:
    """Arma la fila horizontal 'cockpit' — Inventario | Produccion | Riesgo
    | PAM — a partir del dict que retorna make_kpi_column (ya extendido
    por el llamador con tarjetas adicionales en cada categoria). Cada
    columna scrollea verticalmente de forma independiente solo si excede
    la altura maxima — evita forzar scroll horizontal de toda la pagina
    para comparar categorias (CAMBIO 5)."""
    col_style = {"maxHeight": "440px", "overflowY": "auto", "paddingRight": "4px"}
    titulos = {"inventario": "📦 Inventario", "produccion": "🏭 Producción",
               "riesgo": "⚠️ Riesgo", "pam": "🎯 PAM"}
    cols = []
    for key in ("inventario", "produccion", "riesgo", "pam"):
        items = groups.get(key, [])
        cols.append(dbc.Col([
            html.H6(titulos[key], className="text-center mb-1",
                     style={"color": AZUL, "fontWeight": "700", "fontSize": "0.76rem",
                            "borderBottom": f"2px solid {AZUL_MED}", "paddingBottom": "3px"}),
            html.Div(items if items else html.Div(
                "Sin datos", style={"fontSize": "0.7rem", "color": TEXTO_MUTED, "textAlign": "center"}),
                style=col_style),
        ], xs=12, md=6, xl=3, className="mb-1"))
    return html.Div([
        html.H6("KPIs Operacionales", className="text-center mb-1",
                style={"color": AZUL, "fontWeight": "700", "fontSize": "0.8rem"}),
        dbc.Row(cols, className="g-2"),
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Optimizer v2 — Tabla Top-5 configuraciones
# ─────────────────────────────────────────────────────────────────────────────

# Iconos por KPI de la franja ejecutiva (feedback 2026-07-07: la franja se
# veia "muy grande" y sin referencia visual rapida — un icono por label
# ayuda a escanear sin leer el texto completo).
_SUMMARY_ICONS = {
    "Producción esperada": "🏭",
    "Cumplimiento PAM": "🎯",
    "Autonomía mínima": "⏱️",
    "Riesgo global": "⚠️",
    "Confiabilidad": "✅",
    "Cuello de botella": "🔧",
    "Estado del Inventario": "📦",
}


def make_exec_summary_bar(items: list[dict]) -> dbc.Row:
    """Franja KPI ejecutiva compacta — tarjeta oscura estilo TDA
    (Plataforma TDA_Diseño_Visual_Elegido.html, 2026-07-07): panel
    #0F2647 con borde #1a3a6c, label muted arriba, badge de estado
    (pill) a la derecha del label, y el valor grande en negrita abajo —
    mismo patron que las 8 KPI-cards del wireframe SVG del template
    (unica parte legible del bundle, ver
    04_Reports/Technical/20260707_Template_TDA_Mapping.md)."""
    tone_map = {
        "success": VERDE,
        "warning": AMARILLO,
        "orange": NARANJA,
        "danger": ROJO,
        "info": AZUL_MED,
    }
    cols = []
    for item in items:
        tone = item.get("tone", "info")
        color = tone_map.get(tone, AZUL_MED)
        label = item.get("label", "")
        icon = _SUMMARY_ICONS.get(label, "")
        cols.append(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody([
                        html.Div([
                            html.Span([
                                html.Span(icon, style={"marginRight": "4px", "fontSize": "0.78rem"}) if icon else None,
                                html.Span(label),
                            ], style={
                                "fontSize": "0.6rem", "fontWeight": "700", "color": TEXTO_MUTED,
                                "letterSpacing": "0.03em", "textTransform": "uppercase",
                                "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis",
                            }),
                            # Badge/pill de estado (TDA: rectangulo de color junto al label)
                            html.Span(style={
                                "display": "inline-block", "width": "22px", "height": "6px",
                                "borderRadius": "3px", "backgroundColor": color, "marginLeft": "6px",
                            }),
                        ], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginBottom": "4px"}),
                        html.Div(
                            item.get("value", "-"),
                            style={
                                "fontSize": "1.15rem", "fontWeight": "800", "color": AZUL,
                                "lineHeight": "1.1", "marginBottom": "1px",
                            },
                        ),
                        html.Div(
                            item.get("meta", ""),
                            style={"fontSize": "0.62rem", "color": TEXTO_MUTED, "minHeight": "14px", "lineHeight": "1.2"},
                        ),
                    ], style={"padding": "8px 10px"}),
                    className="sim-summary-card",
                    style={
                        "backgroundColor": BG_CARD,
                        "border": f"1px solid {BORDE_CARD}",
                        "borderRadius": "8px",
                        "height": "100%",
                        "boxShadow": "0 4px 10px rgba(7,22,47,0.35)",
                    },
                ),
                xs=6,
                md=4,
                xl=2,
                className="mb-1",
            )
        )
    return dbc.Row(cols, className="g-1")


def make_compact_compare_table(title: str, rows: list[dict], note: str | None = None) -> dbc.Card:
    body_rows = []
    for row in rows:
        body_rows.append(
            html.Tr([
                html.Td(
                    row.get("label", ""),
                    style={"fontSize": "0.74rem", "fontWeight": "600", "color": AZUL},
                ),
                html.Td(
                    row.get("actual", "-"),
                    style={"fontSize": "0.74rem", "textAlign": "right"},
                ),
                html.Td(
                    row.get("recommended", "-"),
                    style={"fontSize": "0.74rem", "textAlign": "right", "fontWeight": "700"},
                ),
                html.Td(
                    row.get("delta", "-"),
                    style={
                        "fontSize": "0.74rem",
                        "textAlign": "right",
                        "fontWeight": "700",
                        "color": row.get("delta_color", AZUL_MED),
                    },
                ),
            ])
        )

    footer = []
    if note:
        footer.append(html.Hr(style={"margin": "8px 0 6px 0"}))
        footer.append(
            html.Div(
                note,
                style={"fontSize": "0.71rem", "color": TEXTO_MUTED, "lineHeight": "1.35"},
            )
        )

    return dbc.Card(
        [
            dbc.CardHeader(
                html.Strong(title, style={"fontSize": "0.82rem", "color": AZUL}),
                style={"padding": "8px 12px", "backgroundColor": "#123059"},
            ),
            dbc.CardBody([
                dbc.Table(
                    [
                        html.Thead(
                            html.Tr([
                                html.Th("Metrica", style={"fontSize": "0.7rem"}),
                                html.Th("Actual", style={"fontSize": "0.7rem", "textAlign": "right"}),
                                html.Th("Recomendado", style={"fontSize": "0.7rem", "textAlign": "right"}),
                                html.Th("Dif.", style={"fontSize": "0.7rem", "textAlign": "right"}),
                            ])
                        ),
                        html.Tbody(body_rows),
                    ],
                    bordered=False,
                    hover=True,
                    size="sm",
                    style={"marginBottom": "0"},
                ),
                *footer,
            ], style={"padding": "8px 10px"}),
        ],
        className="sim-compare-card",
        style={
            "border": f"1px solid {AZUL_MED}",
            "borderRadius": "10px",
            "boxShadow": "0 8px 18px rgba(31,56,100,0.07)",
        },
    )


def make_top5_card(top5_records: list[dict], mode_label: str = "Balance Optimo",
                    compact: bool = False) -> dbc.Card:
    """
    Tabla Top-5 configuraciones del optimizador v2.
    top5_records: lista de dicts con keys rank, config_label, tph, riesgo,
                  inventario, autonomia, multi_score, pareto, converged, n_sim.

    compact=True: oculta la columna "Inventario" y permite wrap del texto
    de configuracion — pensado para columnas angostas (sidebar "Ver
    detalles tecnicos"), donde "whiteSpace: nowrap" con 6 columnas
    forzaba overflow horizontal feo.
    """
    if not top5_records:
        return dbc.Card(
            dbc.CardBody(html.P("Sin resultados — ejecute el optimizador.",
                                style={"color": TEXTO_MUTED, "fontSize": "0.8rem"})),
            style={"marginTop": "8px", "backgroundColor": BG_CARD, "border": f"1px solid {BORDE_CARD}"},
        )

    def _riesgo_color(riesgo_str: str) -> str:
        try:
            pct = float(riesgo_str.replace("P(crisis)=", "").replace("%", ""))
            if pct < 10:   return VERDE
            if pct < 25:   return "#F39C12"
            return ROJO
        except Exception:
            return TEXTO_MUTED

    _fs = "0.68rem" if compact else "0.72rem"

    # CAMBIO 8 (UX/UI v2 JdS, 2026-07-07): tabla horizontal Rank | SAG1 |
    # SAG2 | Riesgo | Cumplimiento | Score — sin texto multilinea ni
    # traslapado (una celda = un valor, sin combinar SAG1+SAG2 en un
    # solo string largo como antes).
    rows = []
    for r in top5_records:
        rank_badge = [html.Span(f"#{r['rank']}", style={"fontWeight": "bold"})]
        if r.get("pareto"):
            rank_badge.append(
                dbc.Badge("Pareto", color="primary", className="ms-1",
                          style={"fontSize": "0.6rem"})
            )
        if r["rank"] == 1:
            rank_badge.append(
                dbc.Badge("Mejor", color="warning", className="ms-1",
                          style={"fontSize": "0.6rem", "color": "#000"})
            )
        riesgo_col = r.get("riesgo", "-")
        cells = [
            html.Td(rank_badge, style={"whiteSpace": "nowrap"}),
            html.Td(r.get("sag1_label", r.get("config_label", "-")),
                    style={"fontSize": _fs, "whiteSpace": "nowrap"}),
            html.Td(r.get("sag2_label", "-"),
                    style={"fontSize": _fs, "whiteSpace": "nowrap"}),
            html.Td(riesgo_col,
                    style={"textAlign": "right",
                           "color": _riesgo_color(riesgo_col),
                           "fontWeight": "600", "fontSize": _fs}),
            html.Td(r.get("cumplimiento", "-"),
                    style={"textAlign": "right", "fontWeight": "600",
                           "color": AZUL_MED, "fontSize": _fs}),
            html.Td(r.get("multi_score", "-"),
                    style={"textAlign": "right", "fontWeight": "700", "color": AZUL, "fontSize": _fs}),
        ]
        rows.append(html.Tr(cells, style={"backgroundColor": "#2a2210" if r["rank"] == 1 else BG_CARD}))

    conv_summary = ""
    if top5_records:
        r0 = top5_records[0]
        conv_summary = f"Sim: {r0.get('n_sim', '?')} — {'Convergente' if r0.get('converged') else 'No convergente'}"

    header_cells = [
        html.Th("Rank", style={"width": "8%"}),
        html.Th("SAG1", style={"width": "24%"}),
        html.Th("SAG2", style={"width": "24%"}),
        html.Th("Riesgo", style={"textAlign": "right", "width": "16%"}),
        html.Th("Cumplimiento", style={"textAlign": "right", "width": "16%"}),
        html.Th("Score", style={"textAlign": "right", "width": "12%"}),
    ]

    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.Strong(f"Top-5 Configuraciones — {mode_label}",
                            style={"fontSize": "0.78rem" if compact else "0.82rem", "color": AZUL}),
                html.Span(conv_summary,
                          style={"fontSize": "0.65rem" if compact else "0.68rem", "color": TEXTO_MUTED,
                                 "marginLeft": "10px"}),
            ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"}),
            style={"padding": "6px 10px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody(
            dbc.Table(
                [
                    html.Thead(html.Tr(header_cells, style={"backgroundColor": "#123059"})),
                    html.Tbody(rows),
                ],
                striped=False, hover=True, size="sm", bordered=True,
                style={"fontSize": _fs, "marginBottom": "0", "tableLayout": "fixed"},
            ),
            style={"padding": "6px"},
        ),
    ], style={"marginTop": "8px", "border": f"1px solid {AZUL_MED}"})


def make_mc_confidence_card(best: dict) -> dbc.Card:
    """"¿Por qué puedo confiar en esta recomendación?" — traduce las metricas
    Monte Carlo del candidato ganador (ver adaptive_mc_eval) a lenguaje
    operacional en vez de estadistico."""
    if not best:
        return dbc.Card(
            dbc.CardBody(html.P("Sin resultados — ejecute el optimizador.",
                                style={"color": TEXTO_MUTED, "fontSize": "0.8rem"})),
            style={"marginTop": "8px", "backgroundColor": BG_CARD, "border": f"1px solid {BORDE_CARD}"},
        )

    pct_prod   = best.get("pct_cumple_produccion", 0.0)
    pct_v1     = best.get("pct_vacia_sag1", 0.0)
    pct_v2     = best.get("pct_vacia_sag2", 0.0)
    pct_auton  = best.get("pct_cumple_autonomia", 0.0)

    def _line(txt, color):
        return html.Div(txt, style={"fontSize": "0.78rem", "color": color,
                                     "fontWeight": "600", "marginBottom": "3px"})

    lines = [
        _line(f"{pct_prod:.0f}% de las simulaciones mantienen la producción objetivo",
              VERDE if pct_prod >= 80 else (AMARILLO if pct_prod >= 60 else ROJO)),
        _line(f"Solo {pct_v1:.0f}% de los escenarios vacían SAG1",
              VERDE if pct_v1 <= 5 else (AMARILLO if pct_v1 <= 15 else ROJO)),
        _line(f"{pct_v2:.0f}% de los escenarios vacían SAG2",
              VERDE if pct_v2 <= 5 else (AMARILLO if pct_v2 <= 15 else ROJO)),
        _line(f"{pct_auton:.0f}% cumplen la autonomía mínima requerida",
              VERDE if pct_auton >= 80 else (AMARILLO if pct_auton >= 60 else ROJO)),
    ]

    n_used = best.get("n_samples_used", 0)
    converged = best.get("converged", False)

    # Autonomia probabilistica (2026-07-06): P10/P90 sobre las mismas
    # muestras Monte Carlo ya recolectadas (adaptive_mc_eval) — sin costo
    # adicional. Responde "¿cual es la autonomia probabilistica?" en vez
    # de solo el punto medio (a1_med/a2_med).
    a1_p10, a1_p90 = best.get("a1_p10"), best.get("a1_p90")
    a2_p10, a2_p90 = best.get("a2_p10"), best.get("a2_p90")
    auton_block = []
    if a1_p10 is not None and a2_p10 is not None:
        auton_block = [
            html.Div("Autonomía probabilística (P10 — P90):",
                     style={"fontSize": "0.72rem", "color": TEXTO_MUTED, "fontWeight": "600", "marginTop": "6px"}),
            html.Div(f"SAG1: {a1_p10:.1f} h — {a1_p90:.1f} h  (mediana {best.get('a1_med', 0):.1f} h)",
                     style={"fontSize": "0.74rem", "color": AZUL_MED}),
            html.Div(f"SAG2: {a2_p10:.1f} h — {a2_p90:.1f} h  (mediana {best.get('a2_med', 0):.1f} h)",
                     style={"fontSize": "0.74rem", "color": NARANJA}),
        ]

    return dbc.Card([
        dbc.CardHeader(
            html.Strong("¿Por qué puedo confiar en esta recomendación?",
                        style={"fontSize": "0.8rem", "color": AZUL}),
            style={"padding": "6px 10px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody(
            [*lines, *auton_block,
             html.Div(
                 f"Basado en {n_used} simulaciones "
                 + ("(convergente)" if converged else "(no convergente — usar con cautela)"),
                 style={"fontSize": "0.68rem", "color": TEXTO_MUTED, "marginTop": "4px", "fontStyle": "italic"},
             )],
            style={"padding": "8px 10px"},
        ),
    ], style={"marginTop": "6px", "border": f"1px solid {AZUL_MED}"})


def make_estado_escenario_card(iro: float, p_safe: float, autonomia_min_h: float) -> dbc.Card:
    """Tarjeta semaforo "Estado del Escenario": combina IRO (risk_engine),
    P(seguro) del ultimo Monte Carlo, y la autonomia minima (SAG mas
    restrictivo) en una sola lectura de 1 segundo."""
    if iro >= 75 or p_safe < 0.5 or autonomia_min_h < 1.0:
        icon, label, color = "🔴", "Riesgo Alto", ROJO
    elif iro >= 50 or p_safe < 0.7 or autonomia_min_h < 1.5:
        icon, label, color = "🟠", "Riesgo Moderado", NARANJA
    elif iro >= 25 or p_safe < 0.9 or autonomia_min_h < 2.5:
        icon, label, color = "🟡", "Atención", AMARILLO
    else:
        icon, label, color = "🟢", "Seguro", VERDE

    return dbc.Card(
        dbc.CardBody(
            html.Div([
                html.Span(icon, style={"fontSize": "1.4rem", "marginRight": "8px"}),
                html.Strong("Estado del Escenario: ", style={"fontSize": "0.82rem", "color": AZUL}),
                html.Strong(label, style={"fontSize": "0.9rem", "color": color}),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "8px 12px"},
        ),
        style={
            "backgroundColor": BG_CARD, "border": f"1px solid {BORDE_CARD}",
            "borderLeft": f"5px solid {color}", "marginBottom": "8px",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# Segunda iteración UX/UI (2026-07-14) — bloque de decisión principal, ver
# 04_Reports/Technical/20260714_Rediseno_Navegacion_UX_Simulador.md
# ═══════════════════════════════════════════════════════════════════════════

# Semáforo de 5 niveles sobre los 6 operational_state reales del kernel
# (engine/circuit_state.py: OFF/STARTING/RUNNING/RESTRICTED/STARVED/
# STOPPING) — nunca depende solo del color, siempre trae icono + texto.
OPERATIONAL_STATE_SEMAFORO = {
    "OFF":        {"nivel": "Detenido",     "color": TEXTO_MUTED, "icono": "⏸"},
    "STARTING":   {"nivel": "Atención",     "color": AMARILLO,    "icono": "▶"},
    "RUNNING":    {"nivel": "Normal",       "color": VERDE,       "icono": "●"},
    "RESTRICTED": {"nivel": "Atención",     "color": AMARILLO,    "icono": "▲"},
    "STARVED":    {"nivel": "Crítico",      "color": ROJO,        "icono": "■"},
    "STOPPING":   {"nivel": "Atención",     "color": AMARILLO,    "icono": "▼"},
}
_ESTADO_SEMAFORO_DEFAULT = {"nivel": "No disponible", "color": TEXTO_MUTED, "icono": "?"}

# Catálogo de motivos de restricción (engine/circuit_state.py) traducido a
# lenguaje de sala — misma fuente de verdad, sin duplicar la lógica de
# cuál es el motivo, solo su presentación.
RESTRICTION_REASON_LABEL_JDS = {
    "SAG_OFF": "el molino está detenido",
    "BALL_MILLS_OFF": "no hay molinos de bolas disponibles",
    "ONE_BALL_MILL_AVAILABLE": "opera con solo 1 molino de bolas",
    "LOW_STOCKPILE": "inventario de pila bajo",
    "STARVED": "la pila está agotada",
    "WINDOW_FEED_REDUCTION": "ventana T8 reduciendo la alimentación",
    "RATE_RAMP_UP": "en rampa de arranque",
    "RATE_RAMP_DOWN": "en rampa de detención",
    "DOWNSTREAM_CAPACITY": "capacidad limitada aguas abajo",
    "PILE_FULL": "la pila está llena",
    "FEED_REJECTED": "alimentación rechazada por capacidad",
    "NORMAL_OPERATION": "operación normal, sin restricciones",
}


def make_circuit_chip(nombre_corto: str, molino: str) -> html.Span:
    """Identidad visual reusada en el banner de decisión, las tarjetas
    SAG1/SAG2 y el selector de circuito — nunca solo el nombre corto,
    siempre "SAG1 · Molino 401" para que no dependa de memorizar cuál
    molino es cuál."""
    return html.Span([
        html.Span(nombre_corto, style={"fontWeight": "800"}),
        html.Span(f" · {molino}", style={"fontWeight": "500", "color": TEXTO_MUTED}),
    ], style={"fontSize": "0.78rem", "color": AZUL_MED})


def make_confianza_card(confianza: str, metodo_label: str) -> dbc.Card:
    """Tarjeta compacta de confianza del router — mismo semáforo
    ALTA/MEDIA/BAJA que ya usa make_router_v2_card, en formato tarjeta
    corta para la fila 2 del grid de decisión (no duplica la tarjeta
    completa de 'Confiabilidad de la Recomendación', que sigue disponible
    en Diagnóstico con el detalle técnico)."""
    semaforo = {"ALTA": "🟢", "MEDIA": "🟡", "BAJA": "🔴"}.get(confianza, "🔴")
    color = {"ALTA": VERDE, "MEDIA": AMARILLO, "BAJA": ROJO_TEXTO_PEQUENO}.get(confianza, ROJO_TEXTO_PEQUENO)
    txt = {"ALTA": "Alta", "MEDIA": "Media", "BAJA": "Baja"}.get(confianza, "Baja")

    return dbc.Card(
        dbc.CardBody([
            html.Div("CONFIANZA", style={"fontSize": "0.68rem", "fontWeight": "700",
                                          "color": TEXTO_MUTED, "letterSpacing": "0.03em"}),
            html.Div([
                html.Span(semaforo, style={"fontSize": "1.1rem", "marginRight": "6px"}),
                html.Span(txt, style={"fontSize": "1.0rem", "fontWeight": "800", "color": color}),
            ], style={"marginTop": "2px", "marginBottom": "2px"}),
            html.Div(metodo_label, style={"fontSize": "0.72rem", "color": TEXTO_MUTED}),
        ], style={"padding": "10px 12px"}),
        style={
            "backgroundColor": BG_CARD, "border": f"1px solid {BORDE_CARD}",
            "borderLeft": f"5px solid {color}", "borderRadius": "8px",
        },
    )


def make_decision_banner(
    estado: str, circuito_afectado: str, molino_afectado: str,
    horizonte_txt: str, causa: str, accion_txt: str, severidad: str,
    confianza: str,
) -> dbc.Card:
    """Bloque de decisión principal (Fase 2 del pedido 2026-07-14): UNA
    sola conclusión operacional arriba de todo — estado, circuito
    afectado, horizonte, causa, acción sugerida, severidad, confianza —
    para que el Jefe de Sala entienda estado→riesgo→acción sin leer las
    tarjetas de abajo. Sustituye a la tarjeta 'Estado general' anterior
    (misma conclusión, formato más completo) — no coexisten ambas para
    no repetir el mismo mensaje en dos lugares."""
    color = {"Sostenible": VERDE, "Atención": AMARILLO, "Acción requerida": ROJO}.get(estado, TEXTO_MUTED)

    def _campo(label, valor, color_valor=AZUL):
        return html.Div([
            html.Span(f"{label}: ", style={"fontSize": "0.72rem", "color": TEXTO_MUTED}),
            html.Span(valor, style={"fontSize": "0.8rem", "fontWeight": "700", "color": color_valor}),
        ], className="decision-banner-field")

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Div(estado.upper(), style={
                    "fontSize": "1.3rem", "fontWeight": "800", "color": color,
                    "letterSpacing": "0.02em",
                }),
                make_circuit_chip(circuito_afectado, molino_afectado),
            ], className="decision-banner-head"),
            html.Div([
                _campo("Horizonte", horizonte_txt),
                _campo("Causa principal", causa),
                _campo("Severidad", severidad, {"Alto": ROJO_TEXTO_PEQUENO, "Medio": AMARILLO, "Bajo": VERDE}.get(severidad, AZUL)),
                _campo("Confianza", {"ALTA": "Alta", "MEDIA": "Media", "BAJA": "Baja"}.get(confianza, confianza)),
            ], className="decision-banner-fields"),
            html.Div(accion_txt, className="decision-banner-action"),
            html.Div([
                dbc.Button("Aplicar recomendación", id="btn-aplicar-recomendacion", size="sm",
                           color="success", className="me-2"),
                dbc.Button("Ver detalle", id="btn-ver-detalle-decision", size="sm",
                           color="secondary", outline=True, href="#section-diagnostics",
                           external_link=False),
            ], className="decision-banner-actions"),
        ], style={"padding": "14px 16px"}),
        className="decision-banner",
        style={
            "backgroundColor": BG_CARD, "border": f"1px solid {BORDE_CARD}",
            "borderTop": f"5px solid {color}", "borderRadius": "12px", "marginBottom": "10px",
        },
    )


def build_initial_decision_banner() -> dbc.Card:
    """Placeholder inicial (mismo patrón que build_initial_estado_general
    y el resto de bloques 6.x) — nunca None/vacío antes del primer
    callback."""
    return make_decision_banner(
        estado="Sostenible", circuito_afectado="—", molino_afectado="—",
        horizonte_txt="—", causa="Sin simulación aún", accion_txt="Ejecuta una simulación para ver la recomendación.",
        severidad="Bajo", confianza="BAJA",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Rediseño JdS (2026-07-13) — vista principal de 6 bloques, ver
# 04_Reports/Technical/20260713_Rediseno_Autonomia_Pilas_JDS.md
# ═══════════════════════════════════════════════════════════════════════════

def make_estado_general_card(iro: float, p_safe: float, autonomia_min_h: float) -> dbc.Card:
    """Bloque 6.1 — Estado general, 3 niveles exactos del brief (distinto
    del semaforo de 4 niveles de make_estado_escenario_card, que sigue
    disponible en detalle tecnico)."""
    if iro >= 60 or p_safe < 0.6 or autonomia_min_h < 1.0:
        label, color = "ACCIÓN REQUERIDA", ROJO
    elif iro >= 30 or p_safe < 0.85 or autonomia_min_h < 2.0:
        label, color = "ATENCIÓN", AMARILLO
    else:
        label, color = "OPERACIÓN SOSTENIBLE", VERDE

    return dbc.Card(
        dbc.CardBody(
            html.Div(label, style={
                "fontSize": "1.15rem", "fontWeight": "800", "color": color,
                "textAlign": "center", "letterSpacing": "0.03em",
            }),
            style={"padding": "10px 12px"},
        ),
        className="estado-general-banner",
        style={
            "backgroundColor": BG_CARD, "border": f"1px solid {BORDE_CARD}",
            "borderTop": f"5px solid {color}", "marginBottom": "10px",
        },
    )


def make_autonomia_resumen_card(asset: str, autonomia_h: float, tiempo_critico_h: float | None,
                                pila_min_pct: float, estado: str,
                                dependency_message: str = "",
                                diverge_flag: bool = False, diverge_diff_h: float | None = None,
                                dynamic_status: str | None = None, dynamic_hours: float | None = None,
                                dynamic_message: str = "", vulnerability: str | None = None,
                                divergence_class: str | None = None) -> dbc.Card:
    """Bloques 6.2/6.3 — autonomía esperada, tiempo hasta crítico, pila
    mínima proyectada, estado.

    `dependency_message`: texto de engine.circuit_state::
    resolve_equipment_dependencies (Regla 4) cuando el SAG está OFF y
    tenía molinos de bolas solicitados ON — nunca se silencia el cambio
    de estado efectivo vs. lo seleccionado por el usuario.

    `diverge_flag`/`diverge_diff_h` (P0-1 Opción A, 2026-07-14): forma
    binaria original de la alerta de divergencia. Se conserva para
    compatibilidad — solo se usa si `dynamic_status` no viene informado
    (ver más abajo).

    `dynamic_status`/`dynamic_hours`/`dynamic_message`/`vulnerability`/
    `divergence_class` (reencuadre semántico, Etapa 1, 2026-07-14 — ver
    04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md,
    'Quinta pasada'): separan formalmente la AUTONOMÍA DINÁMICA (balance
    neto real del instante, `engine.circuit_state::
    classify_dynamic_autonomy`) — badge principal de decisión — de la
    VULNERABILIDAD HISTÓRICA (`compute_autonomia` + `classify_historical_
    vulnerability`, alerta de peor-caso calibrada con 27 episodios reales
    de drenaje) — badge secundario. Todos opcionales: si `dynamic_status`
    es `None` (comportamiento por defecto), la tarjeta se renderiza
    exactamente igual que antes de esta separación."""
    color = {"Sostenible": VERDE, "Atención": AMARILLO, "Acción requerida": ROJO}.get(estado, TEXTO_MUTED)
    t_crit_txt = f"{tiempo_critico_h:.1f} h" if tiempo_critico_h is not None else "No alcanza nivel crítico"

    def _row(label, value, value_color=AZUL):
        return html.Div([
            html.Span(f"{label}: ", style={"fontSize": "0.76rem", "color": TEXTO_MUTED}),
            html.Span(value, style={"fontSize": "0.82rem", "fontWeight": "700", "color": value_color}),
        ], className="mb-1")

    dependencia_row = []
    if dependency_message:
        dependencia_row = [html.Div(
            dependency_message,
            style={"fontSize": "0.68rem", "color": NARANJA, "fontStyle": "italic", "marginTop": "2px"},
        )]

    if dynamic_status is None:
        # Comportamiento previo a la Etapa 1, sin cambios.
        divergencia_row = []
        if diverge_flag:
            _txt = (f"⚠ Autonomía de balance neto difiere en {abs(diverge_diff_h):.1f} h"
                    if diverge_diff_h is not None else
                    "⚠ La autonomía de balance neto no coincide con este valor")
            divergencia_row = [html.Div(
                _txt,
                style={"fontSize": "0.68rem", "color": AMARILLO, "fontStyle": "italic", "marginTop": "2px"},
            )]
        return dbc.Card(
            dbc.CardBody([
                html.Div(asset, style={"fontSize": "0.85rem", "fontWeight": "800", "color": AZUL_MED,
                                        "marginBottom": "4px"}),
                _row("Autonomía esperada", f"{autonomia_h:.1f} h", color),
                _row("Tiempo hasta nivel crítico", t_crit_txt),
                _row("Pila mínima proyectada", f"{pila_min_pct:.0f}%"),
                _row("Estado", estado, color),
                *dependencia_row,
                *divergencia_row,
            ], style={"padding": "10px 12px"}),
            style={
                "backgroundColor": BG_CARD, "border": f"1px solid {BORDE_CARD}",
                "borderLeft": f"5px solid {color}", "borderRadius": "8px",
            },
        )

    # ── Layout Etapa 1: badge dinámico principal + vulnerabilidad secundaria ──
    _dyn_color = {
        "DRAINING": ROJO if (dynamic_hours or 0.0) < 1.5 else AMARILLO,
        "AT_CRITICAL_LEVEL": ROJO,
        "STABLE": AZUL_MED,
        "FILLING": VERDE,
        "SAG_OFF": TEXTO_MUTED,
    }.get(dynamic_status, AZUL_MED)
    dynamic_row = [
        html.Div("AUTONOMÍA DINÁMICA", style={"fontSize": "0.68rem", "color": TEXTO_MUTED,
                                                "fontWeight": "700", "letterSpacing": "0.03em"}),
        html.Div(dynamic_message, style={"fontSize": "0.85rem", "fontWeight": "800", "color": _dyn_color,
                                          "marginBottom": "4px"}),
    ]

    vulnerability_row = []
    if vulnerability is not None:
        _vuln_color = {"CRITICA": ROJO, "ALTA": NARANJA, "MEDIA": AMARILLO, "BAJA": VERDE}.get(
            vulnerability, TEXTO_MUTED)
        vulnerability_row = [html.Div([
            html.Span("VULNERABILIDAD HISTÓRICA: ", style={"fontSize": "0.68rem", "color": TEXTO_MUTED,
                                                             "fontWeight": "700"}),
            html.Span(f"{vulnerability} — nivel actual equivale a {autonomia_h:.1f} h ante un drenaje típico",
                      style={"fontSize": "0.7rem", "fontStyle": "italic", "color": _vuln_color}),
        ], className="mb-1")]

    divergencia_row = []
    if divergence_class in ("POTENTIAL_UI_CONFLICT", "UNEXPECTED_MODEL_DIFFERENCE"):
        divergencia_row = [html.Div(
            "⚠ Ambas métricas describen la misma condición actual pero difieren más de lo esperado — revisar.",
            style={"fontSize": "0.68rem", "color": AMARILLO, "fontStyle": "italic", "marginTop": "2px"},
        )]
    elif divergence_class == "EXPECTED_CONTEXT_DIFFERENCE":
        divergencia_row = [html.Div(
            "La pila no está drenando ahora — la vulnerabilidad histórica refleja un escenario "
            "hipotético de drenaje típico, no el estado actual.",
            style={"fontSize": "0.66rem", "color": TEXTO_MUTED, "fontStyle": "italic", "marginTop": "2px"},
        )]

    return dbc.Card(
        dbc.CardBody([
            html.Div(asset, style={"fontSize": "0.85rem", "fontWeight": "800", "color": AZUL_MED,
                                    "marginBottom": "4px"}),
            *dynamic_row,
            *vulnerability_row,
            _row("Tiempo hasta nivel crítico (vulnerabilidad)", t_crit_txt),
            _row("Pila mínima proyectada", f"{pila_min_pct:.0f}%"),
            _row("Estado", estado, color),
            *dependencia_row,
            *divergencia_row,
        ], style={"padding": "10px 12px"}),
        style={
            "backgroundColor": BG_CARD, "border": f"1px solid {BORDE_CARD}",
            "borderLeft": f"5px solid {_dyn_color}", "borderRadius": "8px",
        },
    )


def make_recomendacion_corta_table(rows: list[dict]) -> dbc.Card:
    """Bloque 6.4 — tabla corta: Línea | Rate actual | Rate recomendado | MoBos recomendados.
    rows: [{"linea": "SAG1", "rate_actual": "1.450 TPH", "rate_recomendado": "1.320 TPH",
             "mobos": "411 + 412"}, ...]"""
    body_rows = [
        html.Tr([
            html.Td(r.get("linea", ""), style={"fontSize": "0.78rem", "fontWeight": "700", "color": AZUL}),
            html.Td(r.get("rate_actual", "-"), style={"fontSize": "0.78rem", "textAlign": "right"}),
            html.Td(r.get("rate_recomendado", "-"),
                    style={"fontSize": "0.78rem", "textAlign": "right", "fontWeight": "700", "color": AZUL_MED}),
            html.Td(r.get("mobos", "-"), style={"fontSize": "0.78rem", "textAlign": "right"}),
        ]) for r in rows
    ]
    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Recomendación de operación", style={"fontSize": "0.82rem", "color": AZUL}),
            style={"padding": "8px 12px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody(
            dbc.Table(
                [
                    html.Thead(html.Tr([
                        html.Th("Línea", style={"fontSize": "0.7rem"}),
                        html.Th("Rate actual", style={"fontSize": "0.7rem", "textAlign": "right"}),
                        html.Th("Rate recomendado", style={"fontSize": "0.7rem", "textAlign": "right"}),
                        html.Th("MoBos recomendados", style={"fontSize": "0.7rem", "textAlign": "right"}),
                    ])),
                    html.Tbody(body_rows),
                ],
                bordered=False, hover=True, size="sm", style={"marginBottom": "0"},
            ),
            style={"padding": "8px 10px"},
        ),
    ], style={"border": f"1px solid {AZUL_MED}", "borderRadius": "10px", "marginBottom": "10px"})


def make_recuperacion_card(fin_restriccion_h: float | None, recovery: dict) -> dbc.Card:
    """Bloque 6.5 — recuperación post-ventana/mantención.
    recovery: {'SAG1': RecoveryResult, 'SAG2': RecoveryResult} de
    engine.balance_diagnostics.compute_recovery_time (o None si no aplica)."""
    if not recovery:
        body = [html.Div("Sin ventana T8/mantención activa en este escenario.",
                          style={"fontSize": "0.76rem", "color": TEXTO_MUTED})]
    else:
        body = []
        if fin_restriccion_h is not None:
            body.append(html.Div([
                html.Span("Fin de la restricción: ", style={"fontSize": "0.76rem", "color": TEXTO_MUTED}),
                html.Span(f"{fin_restriccion_h:.1f} h", style={"fontSize": "0.78rem", "fontWeight": "700", "color": AZUL}),
            ], className="mb-1"))
        for asset in ("SAG1", "SAG2"):
            r = recovery.get(asset)
            if r is None:
                continue
            if r.estado == "recupera" and r.hora_recuperacion_h is not None:
                texto = f"Pila {asset} vuelve a {r.target_pct:.0f}%: {r.hora_recuperacion_h:.1f} h"
                color = VERDE
            elif r.estado == "plana":
                texto = f"{asset}: la pila quedará prácticamente estable."
                color = AMARILLO
            else:
                texto = f"{asset}: la pila seguirá drenando con la configuración actual."
                color = ROJO
            body.append(html.Div(texto, style={"fontSize": "0.78rem", "fontWeight": "600", "color": color,
                                                "marginBottom": "2px"}))

    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Recuperación post-ventana / post-mantención", style={"fontSize": "0.82rem", "color": AZUL}),
            style={"padding": "8px 12px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody(body, style={"padding": "8px 12px"}),
    ], style={"border": f"1px solid {AZUL_MED}", "borderRadius": "10px", "marginBottom": "10px"})


def _fmt_delta_dinamica(delta_h: float) -> str:
    """Fase 1.3 del roadmap de cierre (2026-07-15): delta_dynamic_
    autonomy_h puede venir con el sentinel de 'sin riesgo' (999h) — se
    muestra como texto cualitativo, nunca como un número sin sentido."""
    if delta_h >= 900.0:
        return "ya sin riesgo inmediato"
    return f"{delta_h:+.1f} h dinámica"


def _quick_win_effect_line(qw) -> "html.Div":
    return html.Div([
        html.Span(f"+{qw.delta_historical_buffer_h:.1f} h colchón preventivo  ",
                  style={"color": VERDE, "fontWeight": "700"}),
        html.Span(f"{_fmt_delta_dinamica(qw.delta_dynamic_autonomy_h)}  ",
                  style={"color": AZUL_MED, "fontWeight": "700"}),
        html.Span(f"{qw.delta_riesgo_vaciado_pp:+.0f} pp riesgo de vaciado  ", style={"color": AMARILLO, "fontWeight": "700"}),
        html.Span(f"Impacto productivo: {qw.impacto_produccion_pct:+.1f}%", style={"color": NARANJA, "fontWeight": "700"}),
    ], style={"fontSize": "0.72rem"})


def make_quick_win_card(principal, secundarios: list | None = None) -> dbc.Card:
    """Bloque 6.6 — quick win principal + hasta 2 secundarios.
    principal/secundarios: engine.quick_wins.QuickWin (o None si no hay
    ninguna acción que aporte autonomía en este escenario)."""
    secundarios = secundarios or []

    if principal is None:
        body = [html.Div("No hay una acción simple que mejore la autonomía en este escenario.",
                          style={"fontSize": "0.76rem", "color": TEXTO_MUTED})]
    else:
        body = [
            html.Div("QUICK WIN PRINCIPAL", style={"fontSize": "0.7rem", "fontWeight": "800",
                                                     "color": VERDE, "letterSpacing": "0.04em"}),
            html.Div(principal.titulo, style={"fontSize": "0.86rem", "fontWeight": "700", "color": AZUL,
                                               "marginBottom": "4px"}),
            _quick_win_effect_line(principal),
        ]
        if secundarios:
            body.append(html.Hr(style={"margin": "8px 0 6px 0"}))
            for qw in secundarios[:2]:
                body.append(html.Div(qw.titulo, style={"fontSize": "0.76rem", "fontWeight": "600", "color": AZUL_MED}))
                body.append(_quick_win_effect_line(qw))

    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Quick wins", style={"fontSize": "0.82rem", "color": AZUL}),
            style={"padding": "8px 12px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody(body, style={"padding": "8px 12px"}),
    ], className="quick-win-card",
       style={"border": f"1px solid {VERDE}", "borderRadius": "10px", "marginBottom": "10px"})


def make_scenario_compare_table(rows: list[dict]) -> dbc.Card:
    """Sección 9 — comparación de escenarios (máx. 3 columnas: Actual /
    Recomendado / Alternativo, generado automáticamente).
    rows: [{"label": "Autonomía mínima", "actual": "...", "recomendado": "...",
            "alternativo": "..."}, ...] (máx. 7 filas segun el brief)."""
    body_rows = [
        html.Tr([
            html.Td(r.get("label", ""), style={"fontSize": "0.74rem", "fontWeight": "600", "color": AZUL}),
            html.Td(r.get("actual", "-"), style={"fontSize": "0.74rem", "textAlign": "right"}),
            html.Td(r.get("recomendado", "-"),
                    style={"fontSize": "0.74rem", "textAlign": "right", "fontWeight": "700", "color": AZUL_MED}),
            html.Td(r.get("alternativo", "-"), style={"fontSize": "0.74rem", "textAlign": "right"}),
        ]) for r in rows
    ]
    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Comparar escenarios", style={"fontSize": "0.82rem", "color": AZUL}),
            style={"padding": "8px 12px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody(
            dbc.Table(
                [
                    html.Thead(html.Tr([
                        html.Th("Indicador", style={"fontSize": "0.7rem"}),
                        html.Th("Actual", style={"fontSize": "0.7rem", "textAlign": "right"}),
                        html.Th("Recomendado", style={"fontSize": "0.7rem", "textAlign": "right"}),
                        html.Th("Alternativo", style={"fontSize": "0.7rem", "textAlign": "right"}),
                    ])),
                    html.Tbody(body_rows),
                ],
                bordered=False, hover=True, size="sm", style={"marginBottom": "0"},
            ),
            style={"padding": "8px 10px"},
        ),
    ], style={"border": f"1px solid {AZUL_MED}", "borderRadius": "10px"})


# ═══════════════════════════════════════════════════════════════════════════
# Estado inicial explicito (2026-07-14) — placeholders "idle" de los 6
# bloques y del bloque de comparacion, para que el layout inicial (antes
# de que corra cualquier callback, o si el estado persistido de una
# sesion/version anterior fue descartado) muestre un mensaje deliberado
# en vez de un div vacio invisible o una tarjeta con numeros en cero que
# se confunda con un resultado real. Ver utils/state_schema.py.
# ═══════════════════════════════════════════════════════════════════════════

def _placeholder_card(titulo: str, mensaje: str = "Ejecute una simulación para obtener resultados") -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.Div(titulo, style={"fontSize": "0.78rem", "fontWeight": "700", "color": TEXTO_MUTED,
                                     "marginBottom": "4px"}),
            html.Div(mensaje, style={"fontSize": "0.76rem", "color": TEXTO_MUTED, "fontStyle": "italic"}),
        ], style={"padding": "10px 12px"}),
        style={"backgroundColor": BG_CARD, "border": f"1px dashed {BORDE_CARD}", "borderRadius": "8px"},
    )


def build_initial_estado_general() -> dbc.Card:
    """Bloque 6.1 en estado idle — 'Sin simulación'."""
    return dbc.Card(
        dbc.CardBody(
            html.Div("SIN SIMULACIÓN — ejecute una simulación para ver el estado", style={
                "fontSize": "0.9rem", "fontWeight": "700", "color": TEXTO_MUTED, "textAlign": "center",
            }),
            style={"padding": "10px 12px"},
        ),
        className="estado-general-banner",
        style={"backgroundColor": BG_CARD, "border": f"1px dashed {BORDE_CARD}", "marginBottom": "10px"},
    )


def build_initial_autonomia_card(asset: str) -> dbc.Card:
    """Bloques 6.2/6.3 en estado idle."""
    return _placeholder_card(asset, "Sin simulación — valores en —")


def build_initial_recomendacion_corta() -> dbc.Card:
    """Bloque 6.4 en estado idle."""
    return make_recomendacion_corta_table([
        {"linea": "SAG1", "rate_actual": "—", "rate_recomendado": "—", "mobos": "—"},
        {"linea": "SAG2", "rate_actual": "—", "rate_recomendado": "—", "mobos": "—"},
    ])


def build_initial_recuperacion_card() -> dbc.Card:
    """Bloque 6.5 en estado idle."""
    return _placeholder_card("Recuperación post-ventana/mantención",
                              "Sin simulación — ejecute una simulación con T8 o mantención activa")


def build_initial_quick_win_card() -> dbc.Card:
    """Bloque 6.6 en estado idle."""
    return make_quick_win_card(None, [])


def build_initial_scenario_compare() -> dbc.Card:
    """Sección 9 en estado idle."""
    return make_scenario_compare_table([
        {"label": "Autonomía mínima", "actual": "—", "recomendado": "—", "alternativo": "—"},
        {"label": "Producción total", "actual": "—", "recomendado": "—", "alternativo": "—"},
    ])


def build_initial_kpi_cards() -> dict:
    """Diccionario {id_layout: componente} con el estado idle de los 6
    bloques + comparacion — un unico punto de verdad para el layout
    inicial (page_simulador_operacional) y para cualquier callback que
    necesite 'resetear' la vista ante un estado persistido invalido."""
    return {
        "div-estado-general": build_initial_estado_general(),
        "div-autonomia-sag1": build_initial_autonomia_card("SAG1"),
        "div-autonomia-sag2": build_initial_autonomia_card("SAG2"),
        "div-recomendacion-corta": build_initial_recomendacion_corta(),
        "div-recuperacion": build_initial_recuperacion_card(),
        "div-quick-win": build_initial_quick_win_card(),
        "div-scenario-compare": build_initial_scenario_compare(),
    }
