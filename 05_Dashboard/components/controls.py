"""
controls.py — Sidebar compacta para Pagina 1 (Simulador Operacional)

Nomenclatura:
  SAG1 = Molino 401, bolas 411 y 412
  SAG2 = Molino 501, bolas 511 y 512
"""

import dash_bootstrap_components as dbc
from dash import dcc, html


# Paleta TDA (2026-07-07) — ver components/graphs.py para la nota
# completa del origen (wireframe SVG del template, unica parte legible).
AZUL = "#F0F4FA"
AZUL_MED = "#4FB0E5"
CARD_BG = "#0F2647"
BORDE_CARD = "#1a3a6c"
TEXTO_MUTED = "#8896AF"


def _label(text: str):
    return html.Label(
        text,
        style={
            "fontSize": "0.74rem",
            "fontWeight": "700",
            "color": AZUL,
            "marginTop": "6px",
            "marginBottom": "4px",
            "display": "block",
        },
    )


def _section_card(children):
    return html.Div(children, className="sim-control-section")


def build_sidebar() -> dbc.Card:
    action_bar = html.Div([
        html.Div([
            html.Div("Escenario de simulacion", className="sim-sidebar-title"),
            html.Div("Controles compactos para Jefe de Sala", className="sim-sidebar-subtitle"),
        ], className="sim-sidebar-copy"),
        # Rediseño JdS (2026-07-13): el toggle Rapido/Avanzado se elimina —
        # el detalle tecnico (tolerancia V4, modo de vista, acciones
        # manuales) ahora vive siempre en el AccordionItem "Avanzado" de
        # abajo, no detras de un modo. ctrl-tolerancia-riesgo y
        # ctrl-modo-vista se movieron ahi (ver seccion `avanzado` mas abajo)
        # — mismos ids, callbacks intactos.
        html.Div(id="div-recomendacion-desactualizada"),
        # Backlog #4 (UX/UI v2 JdS, 2026-07-07): el operador no parte de
        # cero al abrir el ejecutable — se precarga el ultimo escenario y
        # se muestra hace cuanto fue.
        html.Div(id="div-ultima-simulacion", style={"fontSize": "0.66rem", "color": TEXTO_MUTED, "marginBottom": "4px"}),
        html.Div([
            dbc.Button(
                "▶ GENERAR RECOMENDACIÓN",
                id="btn-generar-recomendacion",
                size="md",
                color="primary",
                className="sim-action-btn-principal",
                style={"fontWeight": "800", "width": "100%", "marginBottom": "6px"},
            ),
        ]),
        html.Div(id="div-metodo-usado", style={"fontSize": "0.7rem", "color": TEXTO_MUTED, "marginBottom": "4px"}),
        html.Div([
            dbc.Button(
                "Cargar PI",
                id="btn-cargar-estado",
                size="sm",
                color="info",
                outline=True,
                className="sim-action-btn",
            ),
        ], id="div-botones-avanzados", className="sim-sidebar-actions"),
        html.Div([
            # Requisito 8 (Skill UX/UI v3, 2026-07-07): find_optimal_v3
            # (detras de este badge) mide 4-9.5s en frio — no cumple el
            # SLA de 3s (ver tests/test_ui_response_time.py, documentado
            # sin fingir que pasa). Mientras no exista un callback
            # dividido (fallback progresivo real, backlog — no
            # implementado aqui), el minimo viable es que la pantalla NO
            # se vea congelada: dcc.Loading muestra un spinner + texto
            # explicito en vez de dejar el badge en blanco sin feedback.
            dcc.Loading(
                html.Div(id="badge-params-ideales"),
                type="dot", color=AZUL_MED,
                custom_spinner=html.Div(
                    "⏳ Cálculo avanzado en progreso...",
                    style={"fontSize": "0.68rem", "color": AZUL_MED, "fontWeight": "600", "padding": "4px 0"},
                ),
            ),
            html.Div(id="badge-mc-status"),
            html.Div(id="badge-estado-actual"),
            html.Div(id="r16-status-badge"),
        ], className="sim-sidebar-badges"),
        html.Div(
            id="div-mc-convergencia",
            style={"fontSize": "0.68rem", "color": TEXTO_MUTED, "marginTop": "6px"},
        ),
    ], className="sim-sidebar-header")

    escenario = _section_card([
        _label("Ventana T8"),
        dbc.RadioItems(
            id="ctrl-duracion-t8",
            options=[
                {"label": "Sin T8", "value": 0},
                {"label": "2 h", "value": 2},
                {"label": "4 h", "value": 4},
                {"label": "8 h", "value": 8},
                {"label": "12 h", "value": 12},
            ],
            value=0,
            inline=True,
            inputStyle={"marginRight": "4px"},
            labelStyle={"fontSize": "0.74rem", "marginRight": "10px"},
            className="mb-1",
        ),
        _label("Horizonte simulacion"),
        dbc.RadioItems(
            id="ctrl-horizonte",
            options=[
                {"label": "6 h", "value": 6},
                {"label": "12 h", "value": 12},
                {"label": "24 h", "value": 24},
                {"label": "48 h", "value": 48},
            ],
            value=24,
            inline=True,
            inputStyle={"marginRight": "4px"},
            labelStyle={"fontSize": "0.74rem", "marginRight": "10px"},
            className="mb-1",
        ),
        _label("Turno inicial"),
        dbc.RadioItems(
            id="ctrl-turno",
            options=[
                {"label": "Turno C (00-08)", "value": "C"},
                {"label": "Turno A (08-16)", "value": "A"},
                {"label": "Turno B (16-00)", "value": "B"},
            ],
            value="A",
            inline=True,
            inputStyle={"marginRight": "4px"},
            labelStyle={"fontSize": "0.74rem", "marginRight": "10px"},
            className="mb-1",
        ),
        _label("Chancado primario"),
        dbc.Row([
            dbc.Col(
                dbc.Checklist(
                    id="ctrl-ch1",
                    options=[{"label": "CH1 1500 TPH", "value": "on"}],
                    value=["on"],
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"fontSize": "0.74rem"},
                ),
                width=6,
            ),
            dbc.Col(
                dbc.Checklist(
                    id="ctrl-ch2",
                    options=[{"label": "CH2 2500 TPH", "value": "on"}],
                    value=["on"],
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"fontSize": "0.74rem"},
                ),
                width=6,
            ),
        ], className="mb-1"),
        html.Div(
            id="display-cap-chancado",
            style={"fontSize": "0.72rem", "color": AZUL_MED, "fontWeight": "600", "marginBottom": "4px"},
        ),
        _label("Transferencia T1"),
        dbc.RadioItems(
            id="ctrl-t1-mode",
            options=[
                {"label": "Desde chancado", "value": "chancado"},
                {"label": "Con desvio a T3", "value": "t1_con_t3"},
                {"label": "Manual", "value": "manual"},
            ],
            value="chancado",
            inline=False,
            inputStyle={"marginRight": "6px"},
            labelStyle={"fontSize": "0.74rem"},
            className="mb-1",
        ),
        html.Div(id="t1-extra-controls", children=[
            _label("Fraccion a T3 (%)"),
            dcc.Slider(
                id="ctrl-t3-frac",
                min=0, max=50, step=5, value=20,
                marks={0: "0", 20: "20", 40: "40", 50: "50"},
                tooltip={"placement": "bottom", "always_visible": False},
                className="mb-2",
            ),
            _label("T1 disponible (TPH)"),
            dcc.Slider(
                id="ctrl-t1-manual",
                min=0, max=6000, step=100, value=4000,
                marks={0: "0", 1500: "1.5k", 2500: "2.5k", 4000: "4k", 6000: "6k"},
                tooltip={"placement": "bottom", "always_visible": False},
                className="mb-2",
            ),
            html.Div(
                id="display-t3-estimado",
                style={"fontSize": "0.72rem", "color": "#E67E22", "fontWeight": "600", "marginBottom": "4px"},
            ),
        ], style={"display": "none"}),
        _label("Correas T8"),
        dbc.Row([
            dbc.Col([
                html.Div("CV315", className="sim-mini-label"),
                dbc.RadioItems(
                    id="ctrl-correa315",
                    options=[
                        {"label": "Activa", "value": "activa"},
                        {"label": "Reducida", "value": "reducida"},
                        {"label": "Inactiva", "value": "inactiva"},
                    ],
                    value="activa",
                    inline=False,
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"fontSize": "0.72rem"},
                    className="mb-1",
                ),
            ], width=6),
            dbc.Col([
                html.Div("CV316", className="sim-mini-label"),
                dbc.RadioItems(
                    id="ctrl-correa316",
                    options=[
                        {"label": "Activa", "value": "activa"},
                        {"label": "Reducida", "value": "reducida"},
                        {"label": "Inactiva", "value": "inactiva"},
                    ],
                    value="activa",
                    inline=False,
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"fontSize": "0.72rem"},
                    className="mb-1",
                ),
            ], width=6),
        ]),
        _label("Distribucion CV315/CV316"),
        dbc.RadioItems(
            id="ctrl-cv-mode",
            options=[
                {"label": "Automatico", "value": "auto"},
                {"label": "Manual", "value": "manual"},
            ],
            value="auto",
            inline=True,
            inputStyle={"marginRight": "4px"},
            labelStyle={"fontSize": "0.74rem", "marginRight": "10px"},
            className="mb-1",
        ),
        html.Div(id="cv-manual-controls", children=[
            _label("CV315 (TPH)"),
            dcc.Slider(
                id="ctrl-cv315-manual",
                min=0, max=4000, step=50, value=1000,
                tooltip={"placement": "bottom", "always_visible": False},
                className="mb-2",
            ),
            _label("CV316 (TPH)"),
            dcc.Slider(
                id="ctrl-cv316-manual",
                min=0, max=4000, step=50, value=1000,
                tooltip={"placement": "bottom", "always_visible": False},
                className="mb-1",
            ),
        ], style={"display": "none"}),
    ])

    sag = _section_card([
        _label("Estado de molinos SAG"),
        dbc.Row([
            dbc.Col(
                dbc.Switch(
                    id="ctrl-sag1-on",
                    label="SAG1 (Molino 401)",
                    value=True,
                    labelStyle={"fontSize": "0.74rem", "fontWeight": "700", "color": AZUL},
                    className="mb-2",
                ),
                width=6,
            ),
            dbc.Col(
                dbc.Switch(
                    id="ctrl-sag2-on",
                    label="SAG2 (Molino 501)",
                    value=True,
                    labelStyle={"fontSize": "0.74rem", "fontWeight": "700", "color": AZUL},
                    className="mb-2",
                ),
                width=6,
            ),
        ]),
        _label("Rate Molino 401 (SAG1)"),
        dcc.Slider(
            id="ctrl-rate-sag1",
            min=500, max=1600, step=10, value=1236,
            marks={727: "P25", 1018: "P50", 1309: "P75", 1454: "P90", 1527: "Max"},
            tooltip={"placement": "bottom", "always_visible": True},
            className="mb-2",
        ),
        _label("Rate Molino 501 (SAG2)"),
        dcc.Slider(
            id="ctrl-rate-sag2",
            min=1000, max=2642, step=10, value=2214,
            marks={1888: "P25", 2214: "P50", 2365: "P75", 2516: "P90", 2642: "Max"},
            tooltip={"placement": "bottom", "always_visible": True},
            className="mb-1",
        ),
    ])

    bolas = _section_card([
        _label("Molinos 411 / 412 — SAG1"),
        dbc.RadioItems(
            id="ctrl-bolas-sag1",
            options=[
                {"label": "1 MoBo activo (411)", "value": "solo_411"},
                {"label": "1 MoBo activo (412)", "value": "solo_412"},
                {"label": "2 MoBos activos (411+412)", "value": "ambas_411_412"},
            ],
            value="solo_411",
            inline=False,
            inputStyle={"marginRight": "6px"},
            labelStyle={"fontSize": "0.74rem"},
            className="mb-2",
        ),
        _label("Molinos 511 / 512 — SAG2"),
        dbc.RadioItems(
            id="ctrl-bolas-sag2",
            options=[
                {"label": "1 MoBo activo (511)", "value": "solo_511"},
                {"label": "1 MoBo activo (512)", "value": "solo_512"},
                {"label": "2 MoBos activos (511+512)", "value": "ambas_511_512"},
            ],
            value="solo_511",
            inline=False,
            inputStyle={"marginRight": "6px"},
            labelStyle={"fontSize": "0.74rem"},
            className="mb-1",
        ),
        html.Div(id="alerta-bolas", className="mb-1"),
    ])

    pilas = _section_card([
        _label("Pila inicial SAG1 (%)"),
        dcc.Slider(
            id="ctrl-pila-sag1",
            min=0, max=100, step=1, value=55,
            marks={15: "15", 20: "20", 40: "40", 60: "60", 80: "80"},
            tooltip={"placement": "bottom", "always_visible": False},
            className="mb-2",
        ),
        _label("Pila inicial SAG2 (%)"),
        dcc.Slider(
            id="ctrl-pila-sag2",
            min=0, max=100, step=1, value=55,
            marks={18: "18", 20: "20", 40: "40", 60: "60", 80: "80"},
            tooltip={"placement": "bottom", "always_visible": False},
            className="mb-1",
        ),
    ])

    _mant_marks = {h: f"{h}" for h in range(0, 25, 4)}

    def _mant_slider(equipo_id: str, label: str):
        return html.Div([
            html.Div(label, className="sim-mini-label"),
            dcc.RangeSlider(
                id=f"ctrl-mant-{equipo_id}",
                min=0, max=24, step=1, value=[0, 0],
                marks=_mant_marks,
                tooltip={
                    "placement": "bottom",
                    "always_visible": True,
                    "template": "{value}h",
                },
                allowCross=False,
                className="mb-2 mant-slider",
            ),
        ])

    mantenciones = _section_card([
        _label("Mantenciones programadas (hora de reloj, 0-24h)"),
        html.Div(
            "Ventana [0, 0] = sin mantencion. El equipo en mantencion al "
            "inicio del horizonte queda excluido del optimizador.",
            style={"fontSize": "0.68rem", "color": TEXTO_MUTED, "marginBottom": "6px"},
        ),
        _mant_slider("sag1", "SAG1 (Molino 401)"),
        _mant_slider("sag2", "SAG2 (Molino 501)"),
        _mant_slider("411", "Bola 411"),
        _mant_slider("412", "Bola 412"),
        _mant_slider("511", "Bola 511"),
        _mant_slider("512", "Bola 512"),
        _mant_slider("ch1", "Chancador 1 (CH1)"),
        _mant_slider("ch2", "Chancador 2 (CH2)"),
        _mant_slider("cv315", "Correa CV315"),
        _mant_slider("cv316", "Correa CV316"),
        _mant_slider("t1", "Transferencia T1"),
        _mant_slider("t3", "Desvio T3"),
    ])

    # Rediseño JdS (2026-07-13): controles que NO estan en las "entradas
    # minimas" del Jefe de Sala (seccion 4 del brief) pero siguen
    # alimentando V4/acciones manuales — se agrupan en un AccordionItem
    # colapsado por defecto en vez de mostrarse siempre. Mismos ids,
    # mismos defaults; ningun callback cambia.
    avanzado = _section_card([
        _label("Tolerancia de riesgo (V4)"),
        dbc.RadioItems(
            id="ctrl-tolerancia-riesgo",
            options=[
                {"label": "Conservador", "value": "conservador"},
                {"label": "Balanceado", "value": "balanceado"},
                {"label": "Agresivo", "value": "agresivo"},
            ],
            value="balanceado",
            inline=True,
            inputStyle={"marginRight": "4px"},
            labelStyle={"fontSize": "0.72rem", "marginRight": "10px"},
            className="mb-2",
        ),
        # Sincronizacion recomendacion/escenario (2026-07-09): "Simulacion
        # actual" (default) usa los inputs de la sidebar tal cual estan —
        # comportamiento de siempre. "Recomendacion vigente" re-simula con
        # los parametros CONGELADOS del ultimo click en "GENERAR
        # RECOMENDACION", solo si el escenario no cambio desde entonces.
        _label("Modo de vista"),
        dbc.RadioItems(
            id="ctrl-modo-vista",
            options=[
                {"label": "Simulación actual", "value": "actual"},
                {"label": "Recomendación vigente", "value": "recomendacion"},
            ],
            value="actual",
            inline=True,
            inputStyle={"marginRight": "4px"},
            labelStyle={"fontSize": "0.72rem", "marginRight": "10px"},
            className="mb-2",
        ),
        _label("Distribucion T1 a CV315/CV316"),
        dbc.RadioItems(
            id="ctrl-distribucion-t1",
            options=[
                {"label": "Historica 29/71", "value": "balanceado"},
                {"label": "Priorizar SAG1", "value": "priorizar_sag1"},
                {"label": "Priorizar SAG2", "value": "priorizar_sag2"},
                {"label": "Proporcional a demanda", "value": "proporcional"},
            ],
            value="balanceado",
            inline=False,
            inputStyle={"marginRight": "6px"},
            labelStyle={"fontSize": "0.74rem"},
            className="mb-2",
        ),
        _label("Acciones manuales"),
        html.Div([
            dbc.Button("Optimo segun pila", id="btn-params-ideales", size="sm",
                       color="success", outline=True, className="sim-action-btn"),
            dbc.Button("Monte Carlo", id="btn-monte-carlo", size="sm",
                       color="primary", outline=True, className="sim-action-btn"),
        ], className="sim-sidebar-actions"),

        # Fase 2 (2026-07-14): parametros del kernel engine/circuit_state.py
        # que hoy son opcionales en simulate_ode/simulate_scenario y por
        # defecto reproducen el comportamiento anterior (recuperacion
        # instantanea, sin rampas, capacidad de bolas no forzada como techo
        # fisico). Se exponen aca colapsados para quien quiera explorarlos;
        # nadie que no toque estos controles ve cambio de comportamiento.
        html.Hr(style={"borderColor": BORDE_CARD, "margin": "10px 0"}),
        _label("Recuperacion de alimentacion post-ventana"),
        dbc.RadioItems(
            id="ctrl-feed-recovery-mode",
            options=[
                {"label": "Instantanea (actual)", "value": "linear"},
                {"label": "Exponencial", "value": "exponential"},
            ],
            value="linear",
            inline=True,
            inputStyle={"marginRight": "4px"},
            labelStyle={"fontSize": "0.72rem", "marginRight": "10px"},
            className="mb-2",
        ),
        _label("Tiempo de recuperacion (min) — 0 = instantaneo"),
        dcc.Slider(
            id="ctrl-feed-recovery-time-min", min=0, max=120, step=5, value=0,
            marks={0: "0", 30: "30", 60: "60", 90: "90", 120: "120"},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        _label("Rampa de arranque SAG (min) — 0 = instantaneo"),
        dcc.Slider(
            id="ctrl-sag-ramp-up-min", min=0, max=60, step=5, value=0,
            marks={0: "0", 15: "15", 30: "30", 45: "45", 60: "60"},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        dbc.Checklist(
            id="ctrl-enforce-ball-capacity",
            options=[{"label": "Forzar capacidad de 1 bola como techo fisico del SAG", "value": "on"}],
            value=[],
            switch=True,
            inputStyle={"marginRight": "6px"},
            labelStyle={"fontSize": "0.72rem"},
            className="mb-1",
        ),
        _label("Factor de capacidad con 1 bola (supuesto, no calibrado)"),
        dcc.Slider(
            id="ctrl-one-ball-capacity-factor", min=0.40, max=0.70, step=0.05, value=0.55,
            marks={0.40: "0.40", 0.55: "0.55", 0.70: "0.70"},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        dbc.Checklist(
            id="ctrl-redistribution-enabled",
            options=[{"label": "Redistribuir alimentacion entre SAC1/SAC2 si un circuito no puede recibir", "value": "on"}],
            value=[],
            switch=True,
            inputStyle={"marginRight": "6px"},
            labelStyle={"fontSize": "0.72rem"},
            className="mb-1",
        ),
    ])

    accordion = dbc.Accordion(
        [
            dbc.AccordionItem(escenario, title="Escenario", item_id="sim-acc-escenario"),
            dbc.AccordionItem(sag, title="SAG", item_id="sim-acc-sag"),
            dbc.AccordionItem(bolas, title="Bolas", item_id="sim-acc-bolas"),
            dbc.AccordionItem(pilas, title="Pilas", item_id="sim-acc-pilas"),
            dbc.AccordionItem(mantenciones, title="Mantenciones", item_id="sim-acc-mantenciones"),
            dbc.AccordionItem(avanzado, title="Avanzado", item_id="sim-acc-avanzado"),
        ],
        start_collapsed=False,
        active_item=["sim-acc-escenario", "sim-acc-sag"],
        always_open=True,
        className="sim-control-accordion",
    )

    return dbc.Card(
        dbc.CardBody([action_bar, accordion], style={"padding": "12px"}),
        className="sim-sidebar-card",
        style={
            "backgroundColor": CARD_BG,
            "border": f"1px solid {AZUL_MED}",
            "borderRadius": "12px",
            "boxShadow": "0 10px 24px rgba(31,56,100,0.08)",
        },
    )


def _escala_1_5(pregunta: str, id_prefix: str):
    return html.Div([
        html.Div(pregunta, style={"fontSize": "0.62rem", "color": TEXTO_MUTED, "marginTop": "4px"}),
        dbc.RadioItems(
            id=f"{id_prefix}-value",
            options=[{"label": str(n), "value": n} for n in range(1, 6)],
            inline=True,
            style={"fontSize": "0.62rem"},
        ),
    ])


def build_feedback_panel() -> dbc.Card:
    """Panel unico de validacion operacional (Fases 1/2/10, cierre de
    brechas "Validacion Operacional Real", 2026-07-07): checkbox
    "Validar escenario real" (Fase 2), feedback SI/NO/PARCIAL sobre la
    ultima recomendacion (Fase 1, campo `recomendacion_aceptada`), y
    formulario jefe de sala 1-5 (Fase 10) — un solo panel, no tres
    separados, para no fragmentar el flujo del operador tras generar
    una recomendacion."""
    return dbc.Card([
        dbc.CardHeader(
            html.Strong("Validación operacional", style={"fontSize": "0.68rem", "color": AZUL}),
            style={"padding": "4px 8px", "backgroundColor": "#123059"},
        ),
        dbc.CardBody([
            dbc.Checklist(
                options=[{"label": " Validar escenario real (guarda el caso completo)", "value": "validar"}],
                value=[], id="chk-validar-escenario-real", switch=True,
                style={"fontSize": "0.66rem", "color": TEXTO_MUTED},
            ),
            html.Div("¿Siguió la recomendación?",
                     style={"fontSize": "0.62rem", "color": TEXTO_MUTED, "marginTop": "6px"}),
            dbc.ButtonGroup([
                dbc.Button("SÍ", id="btn-feedback-si", size="sm", color="success", outline=True, n_clicks=0),
                dbc.Button("NO", id="btn-feedback-no", size="sm", color="danger", outline=True, n_clicks=0),
                dbc.Button("PARCIAL", id="btn-feedback-parcial", size="sm", color="warning", outline=True, n_clicks=0),
            ], size="sm", style={"marginTop": "2px"}),
            html.Div(id="div-feedback-confirmacion",
                     style={"fontSize": "0.6rem", "color": TEXTO_MUTED, "marginTop": "4px"}),
            html.Hr(style={"margin": "8px 0", "borderColor": BORDE_CARD}),
            html.Div("Formulario jefe de sala (opcional)",
                     style={"fontSize": "0.62rem", "fontWeight": "700", "color": AZUL}),
            _escala_1_5("¿Fue útil?", "form-util"),
            _escala_1_5("¿La recomendación era razonable?", "form-razonable"),
            _escala_1_5("¿Tomó una decisión distinta?", "form-decision-distinta"),
            dbc.Textarea(id="form-comentario", placeholder="Comentario (opcional)", size="sm",
                         style={"fontSize": "0.64rem", "marginTop": "4px"}),
            dbc.Button("Guardar feedback", id="btn-guardar-feedback", size="sm", color="primary",
                       style={"marginTop": "6px", "fontSize": "0.62rem"}, n_clicks=0),
            html.Div(id="div-form-confirmacion",
                     style={"fontSize": "0.6rem", "color": TEXTO_MUTED, "marginTop": "4px"}),
        ], style={"padding": "6px 8px"}),
    ], style={"marginBottom": "6px", "border": f"1px solid {BORDE_CARD}"})
