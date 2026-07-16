"""
app.py — Dashboard Operacional Molienda SAG T8
Codelco Division El Teniente

Ejecucion (desarrollo): cd 05_Dashboard && python app.py
Ejecucion (distribucion): ver run_app.py / dist/Gemelo_Digital_Molienda_Portable/
"""

import sys
import os
import time
import logging

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Logging ───────────────────────────────────────────────────────────────────
# sys.frozen: en el .exe empaquetado, _HERE resuelve dentro de _internal/
# (bundle de PyInstaller) — igual que DATA_CACHE_PATH mas abajo y
# utils/perf_logger.py, el log debe ir junto al .exe, no dentro de
# _internal/ (quedaba ahi como artefacto residual, ver QA 2026-07-06).
if getattr(sys, "frozen", False):
    _LOG_DIR = os.path.join(os.path.dirname(sys.executable), "outputs", "logs")
else:
    _LOG_DIR = os.path.join(_HERE, "outputs", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(_LOG_DIR, "app.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("dashboard")

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output, State, callback, ctx

from engine.simulator import simulate_scenario_cached
from utils.perf_logger import timed, log_duration
from engine.ode_model import compute_autonomia, P90
from engine.rules_engine import determine_regime, ACTION_COLORS
from engine.risk_engine import compute_iro
from engine.realtime_loader import load_current_state
from components.graphs import (
    make_pile_chart, make_tph_chart, make_autonomia_chart,
    make_dose_response_chart, make_autonomia_historica,
    make_decision_heatmap,
    make_bola_timeline_chart, make_chancado_cv_chart,
    make_sensitivity_chart, make_whatif_comparison_chart, make_mc_chart,
    make_prior_posterior_chart, make_mh_risk_comparison_chart, make_mh_kpi_delta_chart,
    make_ro_compare_chart,
    make_pareto_scatter, make_bola_impact_chart, make_risk_chart,
)
from engine.mh_calibration import (
    get_risk_summary, get_correction_factor, MH_META, MH_RISK_BY_DURATION,
)
from components.cards import (
    make_kpi_column, make_autonomia_card, make_iro_card,
    make_rate_card, make_action_banner,
    make_chancado_card, make_bolas_rec_card,
    make_top5_card, make_exec_summary_bar, make_compact_compare_table,
)
from engine.ode_model import compute_chancado_cap
from engine.optimizer_v3 import find_optimal_v3          # Optimizer V3 es la fuente oficial
from engine.optimizer_v2 import format_top5_records       # helper de formato sin cambios

# ── Constantes — paleta TDA (2026-07-07) ───────────────────────────────────────
# Ver components/graphs.py para la nota completa del origen (wireframe
# SVG del template, unica parte legible del bundle). AZUL/etc mantienen
# su rol de TEXTO (usado asi en page_riesgo_operacional, definida mas
# abajo en este mismo archivo); el navbar usa NAVBAR_BG por separado
# porque ahi el rol es FONDO, no texto — mismo valor que no puede
# compartir una sola constante sin invertir contraste en alguno de los
# dos usos.
AZUL     = "#F0F4FA"
AZUL_MED = "#4FB0E5"
VERDE    = "#4FCE82"
NARANJA  = "#E8935A"
ROJO     = "#E94A4A"
AMARILLO = "#E5BB3E"
BG       = "#07162F"
NAVBAR_BG = "#0B1E3F"

# En modo desarrollo lee 01_Data/Cache/ (repo completo). Cuando corre
# empaquetado con PyInstaller (sys.frozen=True, ver run_app.py/build_exe.bat)
# usa runtime_data/Cache/ junto al .exe — es el subconjunto de datos
# congelado para distribucion (ver requirements_runtime.txt y
# 04_Reports/Technical/20260702_Construccion_EXE.md).
if getattr(sys, "frozen", False):
    _RUNTIME_BASE = os.path.dirname(sys.executable)
    DATA_CACHE_PATH = os.path.join(_RUNTIME_BASE, "runtime_data", "Cache")
else:
    DATA_CACHE_PATH = os.path.join(_ROOT, "01_Data", "Cache")

# ── Carga de datos al inicio (cache global) ───────────────────────────────────
_t0_load = time.perf_counter()
log.info("Cargando datos historicos...")
try:
    DF_HIST = pd.read_parquet(
        os.path.join(DATA_CACHE_PATH, "advanced_t8_historical_5min.parquet")
    )
    DF_HIST["fecha"] = pd.to_datetime(DF_HIST["fecha"])
    DF_HIST = DF_HIST.sort_values("fecha").reset_index(drop=True)
    log.info(f"Historico cargado: {len(DF_HIST)} filas, {DF_HIST['fecha'].min()} -> {DF_HIST['fecha'].max()}")
    _HIST_OK = True
except Exception as e:
    log.warning(f"No se pudo cargar historico: {e}")
    DF_HIST = None
    _HIST_OK = False
log_duration("startup_carga_datos", (time.perf_counter() - _t0_load) * 1000.0)

# Pre-computar figuras estaticas costosas
_t0_fig = time.perf_counter()
log.info("Pre-computando figuras estaticas...")
FIG_DOSE_SAG1 = make_dose_response_chart("SAG1")
FIG_DOSE_SAG2 = make_dose_response_chart("SAG2")
FIG_DOSE_PMC  = make_dose_response_chart("PMC")
FIG_DOSE_UNIT = make_dose_response_chart("UNITARIO")
FIG_HEATMAP   = make_decision_heatmap()

if _HIST_OK and DF_HIST is not None:
    FIG_AUTON_HIST = make_autonomia_historica(DF_HIST)
else:
    FIG_AUTON_HIST = None

log_duration("startup_figuras_estaticas", (time.perf_counter() - _t0_fig) * 1000.0)
log.info("Figuras estaticas listas.")

# ── Precalentar cache de escenarios frecuentes (Fase 6 performance) ───────────
# Solo simulate_scenario (deterministico, milisegundos) — NO find_optimal_v3 ni
# Monte Carlo: precalentar 20 optimizaciones completas en el arranque violaria
# el propio objetivo de apertura <15s. find_optimal_v3 ya queda razonablemente
# rapido (<8s) gracias al cache de Fase 5 en el primer uso real del usuario.
_t0_warm = time.perf_counter()
try:
    for _t8 in (0, 2, 4, 8, 12):
        for _pila in (20, 40, 60, 80):
            simulate_scenario_cached(
                pila_sag1_pct=float(_pila), pila_sag2_pct=float(_pila),
                rate_sag1_pct=100.0, rate_sag2_pct=100.0,
                bolas_sag1="sin_bola", bolas_sag2="sin_bola",
                sag1_activo=True, sag2_activo=True,
                duracion_t8_h=float(_t8),
                correa315_estado="activa", correa316_estado="activa",
                horizonte_horas=max(24.0, float(_t8) + 8.0),
                ch1_on=True, ch2_on=True,
                cv_mode="auto",
            )
    log_duration("startup_precalentar_cache", (time.perf_counter() - _t0_warm) * 1000.0)
except Exception as e:
    log.warning(f"No se pudo precalentar cache de escenarios: {e}")

# ── App Dash ──────────────────────────────────────────────────────────────────
# Helpers de la pagina Simulador (_bola_label_short, _build_mc_explanation,
# _clone_figure, _mc_frontier_or_placeholder, _parse_rate_band_midpoint,
# _recommended_bola_cfg, _extract_eval_metrics, _action_summary, _fmt_delta)
# se movieron a pages/simulador_operacional.py.

# Dash resuelve assets_folder en base a __file__ del modulo, que bajo
# PyInstaller (--onefile) apunta al directorio temporal de extraccion
# (sys._MEIPASS), no a la carpeta junto al .exe. En modo frozen se fuerza
# explicitamente a la carpeta "assets" hermana del ejecutable (asi la
# distribucion portable puede traer sus propios assets sin re-empaquetar).
if getattr(sys, "frozen", False):
    _ASSETS_FOLDER = os.path.join(os.path.dirname(sys.executable), "assets")
else:
    _ASSETS_FOLDER = "assets"

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="Simulador de Distribución de Moliendas SAG DET",
    suppress_callback_exceptions=True,
    assets_folder=_ASSETS_FOLDER,
)
server = app.server

from pages.simulador_operacional import page_simulador_operacional, register_simulador_callbacks
register_simulador_callbacks(app)


# ── Navbar ────────────────────────────────────────────────────────────────────
# Requisito 4 (Skill UX/UI v3, 2026-07-07): la cabecera debe mostrar,
# ademas de titulo/subtitulo, Version / Modo local / Ultima simulacion /
# Estado del modelo. Se integra como una linea compacta dentro de la
# misma barra oscura (no un banner separado — eso ya se saco del
# encabezado a pedido explicito del usuario en 2026-07-07, sesion
# anterior; "Ultima simulacion" y "Estado del modelo" son datos nuevos
# que no existian en esa version anterior del header).
# Fase 5 (Skill UX/UI — Auditoria de Contraste TDA, 2026-07-07): navbar y
# footer se reconstruyen en una FUNCION (no como valor fijo a nivel de
# modulo) para que la preferencia de tema recien guardada se refleje al
# hacer el reload completo del navegador — un modulo-level `navbar = ...`
# se construye una sola vez al importar app.py y nunca se re-evalua.
def _build_navbar_and_footer():
    try:
        from utils.theme_state import apply_theme_to_module, get_theme
        apply_theme_to_module(globals(), get_theme())
    except Exception:
        pass

    _estado_modelo_txt = "Modelo OK" if _HIST_OK else "Modelo con datos incompletos"
    _estado_modelo_color = "#7fd18a" if _HIST_OK else "#ffb020"
    from utils.version import version_label
    header_status_line = html.Div([
        html.Span(version_label(), style={"marginRight": "10px"}),
        html.Span(id="header-ultima-simulacion", children="· Última simulación: —",
                  style={"marginRight": "10px"}),
        html.Span(f"· {_estado_modelo_txt}", style={"color": _estado_modelo_color, "fontWeight": "600"}),
    ], style={"color": "rgba(255,255,255,0.65)", "fontSize": "0.68rem", "padding": "2px 0 0 0"})

    navbar = dbc.Navbar(
        dbc.Container([
            html.Div([
                dbc.NavbarBrand([
                    html.Strong("Simulador de Distribución de Moliendas SAG DET"),
                ], style={"color": "white"}),
                header_status_line,
            ]),
            dbc.Nav([
                dbc.NavLink("Simulador", href="/", active="exact",
                            style={"color": "rgba(255,255,255,0.9)"}),
                dbc.NavLink("What-If", href="/analisis", active="exact",
                            style={"color": "rgba(255,255,255,0.9)"}),
                dbc.NavLink("Curvas Historicas", href="/historico", active="exact",
                            style={"color": "rgba(255,255,255,0.9)"}),
                dbc.NavLink("¿Qué pasa si...?", href="/riesgo", active="exact",
                            style={"color": "rgba(255,255,255,0.9)"}),
                dbc.NavLink("Desempeño del Gemelo", href="/desempeno_gemelo", active="exact",
                            style={"color": "rgba(255,255,255,0.9)"}),
                dbc.NavLink("Rendimiento", href="/performance", active="exact",
                            style={"color": "rgba(255,255,255,0.9)"}),
            ], navbar=True),
            html.Div([
                # Toggle claro/oscuro. Guarda preferencia
                # (utils/theme_state.py) y recarga la pagina completa —
                # necesario porque las constantes de color de
                # cards.py/controls.py se fijan al construir el layout,
                # no se re-evaluan sin un refresh.
                dbc.Button("🌙/☀️", id="btn-theme-toggle", size="sm", color="link",
                           style={"color": "rgba(255,255,255,0.85)", "textDecoration": "none",
                                  "fontSize": "0.85rem", "padding": "2px 8px"}),
                html.Span("Inteligencia Operacional DET CIO",
                          style={"color": "rgba(255,255,255,0.6)", "fontSize": "0.75rem",
                                 "marginLeft": "8px"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ], fluid=True),
        color=NAVBAR_BG,
        dark=True,
        className="mb-3",
        style={"borderBottom": f"3px solid {AZUL_MED}"},
    )

    # Banner de version/estado QA + aviso de alcance (mejora post-QA
    # 2026-07-06, ver 04_Reports/Technical/20260706_Sync_Portable_
    # Localhost_T3_TPH.md). Puramente informativo/visual.
    from utils.version import APP_VERSION as _APP_VERSION
    version_status_bar = html.Div(
        f"Versión validada: v{_APP_VERSION}  |  Estado: Aprobada para validación operacional  |  Última QA: 2026-07-06",
        style={
            "fontSize": "0.7rem", "color": AZUL_MED, "textAlign": "center",
            "padding": "3px 0", "backgroundColor": NAVBAR_BG,
        },
    )
    return navbar, version_status_bar


# ── Layout ────────────────────────────────────────────────────────────────────
# Funcion (no valor fijo): se evalua en cada request. Precarga page-content con
# la pagina por defecto para que sim-main-view y demas controles existan en el
# layout inicial que valida el dash-renderer, evitando el error
# "nonexistent object... Input".
def serve_layout():
    # Backlog #1 (UX/UI v2 JdS, 2026-07-07): instrumentacion de uso real —
    # ver utils/usage_logger.py. Nunca debe romper la carga de la app si
    # falla (log_event/start_session ya son defensivos internamente).
    try:
        from utils.usage_logger import start_session
        start_session()
    except Exception:
        pass

    # Fase 5: aplica la preferencia de tema a los modulos que construyen
    # el layout INICIAL (sidebar via controls.py) — sin esto, un reload
    # completo mostraria el sidebar en el tema viejo hasta el primer
    # callback (update_simulation ya aplica el tema, pero eso corre
    # DESPUES de que el sidebar ya se construyo aqui).
    _tema_actual = "dark"
    try:
        from utils.theme_state import apply_theme_to_module, get_theme
        import components.controls as _controls_mod
        _tema_actual = get_theme()
        apply_theme_to_module(_controls_mod.__dict__, _tema_actual)
    except Exception:
        pass

    navbar, version_status_bar = _build_navbar_and_footer()

    # Fase 5: data-bs-theme en el Div raiz — las custom properties de
    # assets/styles.css ([data-bs-theme="light"]) heredan a todos los
    # componentes Bootstrap descendientes (form-check, accordion, table)
    # sin esto, el modo claro reproduce el mismo bug de contraste que
    # motivo esta auditoria (ver 20260707_Modo_Claro_Oscuro.md, seccion 8).
    return html.Div([
        dcc.Location(id="url", refresh=False),
        navbar,
        # Fase 5 (toggle claro/oscuro): dispara un reload completo del
        # navegador DESPUES de que el callback de servidor guarde la
        # preferencia (secuenciado via este Store, no una race condition
        # entre guardar y recargar).
        dcc.Store(id="store-theme-trigger"),
        # Store compartido: estado de planta actual (pila + rate + CV) para What-If
        dcc.Store(id="store-plant-state", storage_type="session"),
        # Cache del ultimo resultado Monte Carlo (poblado por 'Simular Monte Carlo').
        # Permite mostrar la pestana "Robustez MC" de Vista principal sin recalcular
        # el optimizador (caro) en cada cambio de slider.
        dcc.Store(id="store-mc-results", storage_type="session"),
        # Validacion Operacional Real (cierre de brechas, 2026-07-07):
        # rec_id de la ultima "GENERAR RECOMENDACION" (para poder enlazar
        # el feedback SI/NO/PARCIAL con esa recomendacion especifica) y el
        # snapshot completo del ultimo escenario simulado (para el modo
        # "Validar escenario real" y el formulario jefe de sala).
        dcc.Store(id="store-ultima-recomendacion-id", storage_type="session"),
        dcc.Store(id="store-ultimo-snapshot-caso", storage_type="session"),
        # Sincronizacion recomendacion/escenario (2026-07-09): hash del
        # escenario en el momento exacto en que "GENERAR RECOMENDACION"
        # termino de escribir los rates, el dict completo (para poder
        # re-simular "Recomendacion vigente" sin depender de que
        # ctrl-rate-sag1/2 sigan intactos), y el texto de contexto
        # congelado ("Calculado para: T8=Xh...") — ver
        # utils/scenario_hash.py.
        dcc.Store(id="store-recommendation-scenario-hash", storage_type="session"),
        dcc.Store(id="store-recommendation-scenario-params", storage_type="session"),
        dcc.Store(id="store-recommendation-contexto", storage_type="session"),
        dbc.Container(id="page-content", fluid=True, children=page_simulador_operacional()),
        # Banner de version/estado QA (feedback 2026-07-07: se movio del
        # encabezado al pie de pagina — el JdS debe ver primero la
        # recomendacion, no el estado de validacion del software).
        version_status_bar,
    ], **{"data-bs-theme": _tema_actual})


# Fase 5 (Skill UX/UI — Auditoria de Contraste TDA, 2026-07-07): toggle
# claro/oscuro. Guarda la preferencia contraria a la actual y dispara un
# reload completo del navegador via el callback clientside de abajo —
# necesario porque las tarjetas/sidebar se construyen con constantes de
# color fijadas al armar el layout (ver utils/theme_state.py).
@app.callback(
    Output("store-theme-trigger", "data"),
    Input("btn-theme-toggle", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_theme(n_clicks):
    from utils.theme_state import get_theme, set_theme
    nuevo = "light" if get_theme() == "dark" else "dark"
    set_theme(nuevo)
    return nuevo


app.clientside_callback(
    "function(theme) { if (theme) { window.location.reload(); } return window.dash_clientside.no_update; }",
    Output("url", "refresh"),
    Input("store-theme-trigger", "data"),
    prevent_initial_call=True,
)

# Hardening operacional (2026-07-09): se intento un guard liviano
# anti-stale-render (contador incrementado client-side + comparacion en
# update_simulation) y se REVIRTIO tras encontrar en QA visual que es
# estructuralmente incorrecto, no un caso limite: Dash despacha los
# callbacks hermanos disparados por el mismo cambio de Input desde una
# UNICA foto (snapshot) consistente del store — el callback clientside
# que incrementa el contador y update_simulation (que lee ese contador
# como State) se disparan desde la MISMA oleada, asi que
# update_simulation SIEMPRE capturaba el contador ANTES de que el
# incremento fuera visible, nunca despues. Resultado observado: el aviso
# "Resultado desactualizado" quedaba pegado para siempre, incluso sin
# ningun cambio rapido de por medio — peor que no tener guard (es
# activamente enganoso). Arreglarlo bien requeriria (a) mover el
# contador fuera del grafo reactivo de Dash (listener JS nativo sobre el
# DOM, fuera de clientside_callback) o (b) encadenar update_simulation
# para que dispare a partir del contador en vez de los controles
# crudos (agrega un round-trip extra) — ninguna de las dos es "liviana",
# quedan documentadas como opciones para una fase futura en
# 04_Reports/Technical/20260709_Performance_Hardening.md.


app.layout = serve_layout





def page_historico():
    # Selector de activo
    tabs_dose = dbc.Tabs([
        dbc.Tab(dcc.Graph(figure=FIG_DOSE_SAG1, config={"displayModeBar": False}),
                label="SAG1", tab_id="t-sag1"),
        dbc.Tab(dcc.Graph(figure=FIG_DOSE_SAG2, config={"displayModeBar": False}),
                label="SAG2", tab_id="t-sag2"),
        dbc.Tab(dcc.Graph(figure=FIG_DOSE_PMC,  config={"displayModeBar": False}),
                label="PMC", tab_id="t-pmc"),
        dbc.Tab(dcc.Graph(figure=FIG_DOSE_UNIT, config={"displayModeBar": False}),
                label="UNITARIO", tab_id="t-unit"),
    ], active_tab="t-sag1")

    auton_chart = (
        dcc.Graph(figure=FIG_AUTON_HIST, config={"displayModeBar": False})
        if FIG_AUTON_HIST is not None
        else dbc.Alert("Datos historicos no disponibles.", color="warning")
    )

    return html.Div([
        dbc.Row([
            dbc.Col(html.H5("Curvas Historicas — Dose-Response T8", className="page-title"), width=12),
        ]),
        dbc.Row([
            dbc.Col([
                dbc.Card(dbc.CardBody([
                    html.P([
                        "Impacto historico de ventanas T8 sobre TPH (% del P90 baseline). ",
                        html.Strong("70 eventos"),
                        " analizados. Puntos en rojo: n < 15 (estadistica limitada).",
                    ], style={"fontSize": "0.78rem", "color": "#555", "marginBottom": "8px"}),
                    tabs_dose,
                ], style={"padding": "12px"})),
            ], width=7),
            dbc.Col([
                dbc.Card(dbc.CardBody([
                    html.P("Dose-response comparativo SAG1 vs SAG2",
                           style={"fontSize": "0.8rem", "fontWeight": "600", "color": AZUL}),
                    _make_comparative_dose_table(),
                ], style={"padding": "12px"})),
            ], width=5),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                dbc.Card(dbc.CardBody([
                    html.P("Autonomia operacional historica (ultimos 30 dias, datos cada 5 min)",
                           style={"fontSize": "0.8rem", "fontWeight": "600", "color": AZUL,
                                  "marginBottom": "8px"}),
                    auton_chart,
                ], style={"padding": "12px"})),
            ], width=12),
        ]),
    ])


def _make_comparative_dose_table():
    """Tabla comparativa dose-response todos los activos."""
    rows = [
        html.Tr([
            html.Th("Activo", style={"fontSize": "0.75rem"}),
            html.Th("P90 (TPH)", style={"fontSize": "0.75rem"}),
            html.Th("2h T8", style={"fontSize": "0.75rem"}),
            html.Th("4h T8", style={"fontSize": "0.75rem"}),
            html.Th("12h T8", style={"fontSize": "0.75rem"}),
        ], className="table-dark")
    ]
    data = [
        ("SAG1",     1454, 108, 69,  44),
        ("SAG2",     2516, 98,  99,  85),
        ("PMC",      1460, 97,  85,  89),
        ("UNITARIO",  834, 96, 100,  95),
    ]
    def _cell_color(v):
        if v >= 90: return VERDE
        if v >= 80: return AMARILLO
        if v >= 70: return NARANJA
        return ROJO

    for name, p90, v2, v4, v12 in data:
        rows.append(html.Tr([
            html.Td(html.Strong(name), style={"fontSize": "0.75rem"}),
            html.Td(f"{p90:,}", style={"fontSize": "0.75rem"}),
            html.Td(f"{v2}%",  style={"fontSize": "0.75rem", "color": _cell_color(v2),  "fontWeight": "700"}),
            html.Td(f"{v4}%",  style={"fontSize": "0.75rem", "color": _cell_color(v4),  "fontWeight": "700"}),
            html.Td(f"{v12}%", style={"fontSize": "0.75rem", "color": _cell_color(v12), "fontWeight": "700"}),
        ]))

    return dbc.Table(rows, bordered=True, size="sm", hover=True, striped=True,
                     style={"marginTop": "8px"})



def page_riesgo_operacional() -> html.Div:
    """Página 5 — Simulador Operacional ¿Qué pasa si...?"""
    return html.Div([
        # ENCABEZADO
        dbc.Row([
            dbc.Col([
                html.H5([
                    "¿Qué pasa si...? ",
                    dbc.Badge("Simulador Operacional", color="primary", pill=True,
                              style={"fontSize": "0.7rem", "verticalAlign": "middle"}),
                ], className="page-title", style={"marginBottom": "2px"}),
                html.Small("Para Jefe de Sala · Jefe de Turno · PAM · Planificación",
                           style={"color": "#888", "fontSize": "0.78rem"}),
            ], width=8),
            dbc.Col(dbc.Alert(
                ["Calibrado con ", html.Strong("70 eventos T8"),
                 " reales (ago-2025 → jun-2026)"],
                color="success",
                style={"padding": "6px 12px", "fontSize": "0.75rem",
                       "marginBottom": "0", "textAlign": "right"},
            ), width=4),
        ], className="mb-2"),

        # BOTONES DE ESCENARIOS RÁPIDOS
        dbc.Row([
            dbc.Col([
                html.Span("Escenario rápido: ",
                          style={"fontSize": "0.78rem", "color": "#555",
                                 "fontWeight": "600", "marginRight": "6px",
                                 "lineHeight": "30px", "verticalAlign": "middle"}),
                dbc.ButtonGroup([
                    dbc.Button("T8 2h",  id="ro-btn-t8-2",  size="sm", active=False,
                               color="outline-secondary", n_clicks=0),
                    dbc.Button("T8 4h",  id="ro-btn-t8-4",  size="sm", active=False,
                               color="outline-primary",   n_clicks=0),
                    dbc.Button("T8 8h",  id="ro-btn-t8-8",  size="sm", active=False,
                               color="outline-warning",   n_clicks=0),
                    dbc.Button("T8 12h", id="ro-btn-t8-12", size="sm", active=False,
                               color="outline-danger",    n_clicks=0),
                ], style={"marginRight": "14px", "verticalAlign": "middle"}),
                dbc.ButtonGroup([
                    dbc.Button("Falla Chancador 2",  id="ro-btn-falla-ch2",
                               size="sm", color="outline-warning", n_clicks=0, active=False),
                    dbc.Button("Operar Conservador", id="ro-btn-conservador",
                               size="sm", color="outline-success", n_clicks=0, active=False),
                    dbc.Button("Maxima Produccion",  id="ro-btn-max-prod",
                               size="sm", color="outline-danger",  n_clicks=0, active=False),
                ], style={"verticalAlign": "middle"}),
            ], width=12),
        ], className="mb-1"),

        # BOTONES OPTIMIZER V2
        dbc.Row([
            dbc.Col([
                html.Span("Optimizador: ",
                          style={"fontSize": "0.78rem", "color": "#555", "fontWeight": "600",
                                 "marginRight": "6px", "lineHeight": "30px",
                                 "verticalAlign": "middle"}),
                dbc.ButtonGroup([
                    dbc.Button("Reset",            id="ro-btn-reset",        size="sm",
                               color="outline-secondary", n_clicks=0, active=False),
                    dbc.Button("Mejor Config",     id="ro-btn-mejor-config", size="sm",
                               color="outline-success",   n_clicks=0, active=False),
                    dbc.Button("Max Produccion",   id="ro-btn-max-prod-opt", size="sm",
                               color="outline-danger",    n_clicks=0, active=False),
                    dbc.Button("Op. Segura",       id="ro-btn-op-segura",    size="sm",
                               color="outline-primary",   n_clicks=0, active=False),
                    dbc.Button("Balance Optimo",   id="ro-btn-balance-opt",  size="sm",
                               color="outline-primary",   n_clicks=0, active=False),
                ], style={"verticalAlign": "middle"}),
            ], width=12),
        ], className="mb-3"),

        # CONTENIDO PRINCIPAL — 2 COLUMNAS
        dbc.Row([
            # ── IZQUIERDA: controles ──────────────────────────────────────────
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.Strong("Configurar escenario",
                                               style={"fontSize": "0.82rem"})),
                    dbc.CardBody([
                        # Pilas
                        html.Div("Inventario pila SAG1 inicial (%)",
                                 style={"fontSize": "0.72rem", "color": "#555",
                                        "fontWeight": "600", "marginBottom": "2px"}),
                        dcc.Slider(
                            id="ro-pila1-ini", min=10, max=90, step=1, value=45,
                            marks={15: {"label": "15% ⚠", "style": {"color": ROJO}},
                                   40: "40%", 65: "65%", 90: "90%"},
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),
                        html.Div("Inventario pila SAG2 inicial (%)",
                                 style={"fontSize": "0.72rem", "color": "#555",
                                        "fontWeight": "600",
                                        "marginTop": "10px", "marginBottom": "2px"}),
                        dcc.Slider(
                            id="ro-pila2-ini", min=10, max=75, step=1, value=40,
                            marks={18: {"label": "18% ⚠", "style": {"color": ROJO}},
                                   40: "40%", 60: "60%"},
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),

                        html.Hr(style={"margin": "12px 0"}),

                        # Rates
                        html.Div("Rate SAG1 (TPH)",
                                 style={"fontSize": "0.72rem", "color": "#555",
                                        "fontWeight": "600", "marginBottom": "2px"}),
                        dcc.Slider(
                            id="ro-rate-sag1", min=700, max=1550, step=50, value=1236,
                            marks={700: "700", 1000: "1000",
                                   1236: {"label": "1236", "style": {"color": AZUL_MED}},
                                   1454: "P90", 1550: "Max"},
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),
                        html.Div("Rate SAG2 (TPH)",
                                 style={"fontSize": "0.72rem", "color": "#555",
                                        "fontWeight": "600",
                                        "marginTop": "10px", "marginBottom": "2px"}),
                        dcc.Slider(
                            id="ro-rate-sag2", min=1200, max=2650, step=50, value=2214,
                            marks={1200: "1200", 1800: "1800",
                                   2214: {"label": "2214", "style": {"color": AZUL_MED}},
                                   2516: "P90", 2650: "Max"},
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),

                        html.Hr(style={"margin": "12px 0"}),

                        # Ventana T8
                        html.Div("Ventana de T8",
                                 style={"fontSize": "0.72rem", "color": "#555",
                                        "fontWeight": "600", "marginBottom": "4px"}),
                        dbc.RadioItems(
                            id="ro-t8-dur",
                            options=[
                                {"label": "Sin T8",  "value": 0},
                                {"label": "T8 2h",   "value": 2},
                                {"label": "T8 4h",   "value": 4},
                                {"label": "T8 8h",   "value": 8},
                                {"label": "T8 12h",  "value": 12},
                            ],
                            value=4, inline=True,
                            style={"fontSize": "0.75rem"},
                        ),

                        html.Hr(style={"margin": "12px 0"}),

                        # Chancado
                        html.Div("Estado del chancado",
                                 style={"fontSize": "0.72rem", "color": "#555",
                                        "fontWeight": "600", "marginBottom": "4px"}),
                        dbc.RadioItems(
                            id="ro-chancado",
                            options=[
                                {"label": "Normal (CH1 + CH2)", "value": "normal"},
                                {"label": "Solo Chancador 1",   "value": "solo_ch1"},
                                {"label": "Sin chancado",       "value": "sin_chancado"},
                            ],
                            value="normal",
                            style={"fontSize": "0.75rem"},
                        ),

                        html.Hr(style={"margin": "12px 0"}),

                        # Bolas
                        dbc.Row([
                            dbc.Col([
                                html.Div("Bolas SAG1",
                                         style={"fontSize": "0.72rem", "color": "#555",
                                                "fontWeight": "600", "marginBottom": "4px"}),
                                dbc.RadioItems(
                                    id="ro-bolas-sag1",
                                    options=[
                                        {"label": "1 MoBo",  "value": "solo_411"},
                                        {"label": "2 MoBos", "value": "ambas_411_412"},
                                    ],
                                    value="solo_411",
                                    style={"fontSize": "0.75rem"},
                                ),
                            ], width=6),
                            dbc.Col([
                                html.Div("Bolas SAG2",
                                         style={"fontSize": "0.72rem", "color": "#555",
                                                "fontWeight": "600", "marginBottom": "4px"}),
                                dbc.RadioItems(
                                    id="ro-bolas-sag2",
                                    options=[
                                        {"label": "1 MoBo",  "value": "solo_511"},
                                        {"label": "2 MoBos", "value": "ambas_511_512"},
                                    ],
                                    value="solo_511",
                                    style={"fontSize": "0.75rem"},
                                ),
                            ], width=6),
                        ]),
                    ], style={"padding": "12px"}),
                ]),
            ], width=4),

            # ── DERECHA: resultados ───────────────────────────────────────────
            dbc.Col([
                # Indicadores principales
                dbc.Row([
                    dbc.Col(dbc.Card(
                        dbc.CardBody(html.Div(id="ro-sobrevive-card",
                                              children=_ro_default_sobrevive())),
                        style={"height": "100%", "borderLeft": f"4px solid {VERDE}"},
                    ), width=6),
                    dbc.Col(dbc.Card(
                        dbc.CardBody(html.Div(id="ro-riesgo-card",
                                              children=_ro_default_riesgo())),
                        style={"height": "100%", "borderLeft": f"4px solid {AZUL_MED}"},
                    ), width=6),
                ], className="mb-2"),

                # Métricas
                html.Div(id="ro-metricas", children=_ro_default_metricas()),
                html.Div(id="ro-r16-badge", className="mb-2"),

                # Gráficos
                dbc.Tabs([
                    dbc.Tab(dbc.Card(dbc.CardBody([
                        dcc.Graph(id="ro-graph-pilas",
                                  config={"displayModeBar": False}),
                    ], style={"padding": "8px"})),
                        label="Evolución Pilas", tab_id="tab-ro-pilas"),
                    dbc.Tab(dbc.Card(dbc.CardBody([
                        dcc.Graph(id="ro-graph-tph",
                                  config={"displayModeBar": False}),
                    ], style={"padding": "8px"})),
                        label="Evolución TPH", tab_id="tab-ro-tph"),
                    dbc.Tab(dbc.Card(dbc.CardBody([
                        html.Small(
                            "Configurado vs Conservador (900/1800 TPH) vs Máx Producción (1500/2600 TPH)",
                            style={"color": "#888", "fontSize": "0.72rem"}),
                        dcc.Graph(id="ro-graph-compare",
                                  config={"displayModeBar": False}),
                    ], style={"padding": "8px"})),
                        label="Comparar escenarios", tab_id="tab-ro-compare"),
                ], id="ro-tabs", active_tab="tab-ro-pilas", className="mb-2"),

                # Top-5 configuraciones (optimizer v2)
                html.Div(id="div-top5-riesgo", className="mb-2"),

                # Graficos optimizer: Pareto + Impacto bolas
                dbc.Row([
                    dbc.Col(dcc.Graph(id="ro-graph-pareto",
                                      config={"displayModeBar": False}), width=7),
                    dbc.Col(dcc.Graph(id="ro-graph-bola-impact",
                                      config={"displayModeBar": False}), width=5),
                ], id="row-ro-optimizer-charts", className="mb-2",
                   style={"display": "none"}),

                # Recomendación
                dbc.Card(
                    html.Div(id="ro-recomendacion", children=_ro_default_rec()),
                    style={"borderLeft": f"4px solid {AZUL}"},
                ),
            ], width=8),
        ]),
    ])


def _ro_default_sobrevive():
    return [
        html.Div("¿SOBREVIVE LA OPERACIÓN?",
                 style={"fontSize": "0.7rem", "fontWeight": "700", "color": "#555",
                        "letterSpacing": "0.5px", "marginBottom": "4px"}),
        html.Div("—", style={"fontSize": "3rem", "fontWeight": "900", "color": "#CCC",
                              "lineHeight": "1"}),
        html.Small("Ajusta los controles de la izquierda.",
                   style={"color": "#aaa", "fontSize": "0.7rem"}),
    ]


def _ro_default_riesgo():
    return [
        html.Div("¿RIESGO DE QUEDAR CRÍTICO?",
                 style={"fontSize": "0.7rem", "fontWeight": "700", "color": "#555",
                        "letterSpacing": "0.5px", "marginBottom": "4px"}),
        html.Div("—", style={"fontSize": "3rem", "fontWeight": "900", "color": "#CCC",
                              "lineHeight": "1"}),
        html.Small("Basado en 70 eventos T8 reales.",
                   style={"color": "#aaa", "fontSize": "0.7rem"}),
    ]


def _ro_default_metricas():
    def _empty(label):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(label, style={"fontSize": "0.62rem", "color": "#AAA"}),
            html.Div("—",   style={"fontSize": "1.1rem",  "color": "#CCC",
                                   "fontWeight": "700"}),
        ], style={"padding": "8px"})), width=2)
    return dbc.Row([
        _empty("TPH SAG1"), _empty("TPH SAG2"), _empty("TPH Total"),
        _empty("Pila SAG1 fin"), _empty("Pila SAG2 fin"), _empty("Autonomía mín."),
    ], className="mb-2")


def _ro_default_rec():
    return dbc.CardBody([
        html.Div("Recomendación operacional",
                 style={"fontWeight": "700", "color": AZUL,
                        "fontSize": "0.82rem", "marginBottom": "4px"}),
        html.Div("Configura un escenario para obtener la recomendación.",
                 style={"color": "#888", "fontSize": "0.8rem"}),
    ], style={"padding": "10px"})



# ── Riesgo Operacional — callback principal ────────────────────────────────────
@app.callback(
    Output("ro-graph-pilas",    "figure"),
    Output("ro-graph-tph",      "figure"),
    Output("ro-graph-compare",  "figure"),
    Output("ro-sobrevive-card", "children"),
    Output("ro-riesgo-card",    "children"),
    Output("ro-metricas",       "children"),
    Output("ro-recomendacion",  "children"),
    Output("ro-r16-badge",      "children"),
    Input("ro-pila1-ini",  "value"),
    Input("ro-pila2-ini",  "value"),
    Input("ro-rate-sag1",  "value"),
    Input("ro-rate-sag2",  "value"),
    Input("ro-t8-dur",     "value"),
    Input("ro-chancado",   "value"),
    Input("ro-bolas-sag1", "value"),
    Input("ro-bolas-sag2", "value"),
)
@timed("callback_update_riesgo_sim")
def update_riesgo_sim(pila1, pila2, rate1, rate2, t8_dur, chancado, bolas1, bolas2):
    # Defaults
    pila1    = float(pila1   or 45)
    pila2    = float(pila2   or 40)
    rate1    = float(rate1   or 1236)
    rate2    = float(rate2   or 2214)
    t8_dur   = int(t8_dur    or 4)
    chancado = chancado       or "normal"
    bolas1   = bolas1         or "solo_411"
    bolas2   = bolas2         or "solo_511"

    ch1_on   = (chancado != "sin_chancado")
    ch2_on   = (chancado == "normal")
    horizonte = max(24.0, float(t8_dur) + 8.0)

    # Simulación principal (cacheada por escenario: repetir un valor de
    # slider ya visto en esta sesión no recalcula, ver engine/scenario_cache.py)
    sim = simulate_scenario_cached(
        pila_sag1_pct=pila1, pila_sag2_pct=pila2,
        rate_sag1_pct=100.0, rate_sag2_pct=100.0,
        bolas_sag1=bolas1, bolas_sag2=bolas2,
        sag1_activo=True,  sag2_activo=True,
        duracion_t8_h=float(t8_dur),
        correa315_estado="activa", correa316_estado="activa",
        horizonte_horas=horizonte,
        ch1_on=ch1_on, ch2_on=ch2_on,
        cv_mode="auto",
        rate_sag1_tph=rate1, rate_sag2_tph=rate2,
    )

    time_arr  = np.array(sim["time"])
    pile1_arr = np.array(sim["pile_sag1"])
    pile2_arr = np.array(sim["pile_sag2"])
    tph1_arr  = np.array(sim["tph_sag1"])
    tph2_arr  = np.array(sim["tph_sag2"])
    tph_arr   = np.array(sim["tph_total"])

    # Métricas durante ventana T8
    if t8_dur > 0:
        idx_t8 = min(int(np.searchsorted(time_arr, float(t8_dur))), len(time_arr) - 1)
    else:
        idx_t8 = len(time_arr) - 1

    pile1_min = float(pile1_arr[:idx_t8 + 1].min())
    pile2_min = float(pile2_arr[:idx_t8 + 1].min())
    pile1_end = float(pile1_arr[idx_t8])
    pile2_end = float(pile2_arr[idx_t8])
    tph1_mean = float(tph1_arr[:idx_t8 + 1].mean())
    tph2_mean = float(tph2_arr[:idx_t8 + 1].mean())
    tph_mean  = float(tph_arr[:idx_t8 + 1].mean())

    auton1_min = float(sim.get("min_autonomia_sag1", 999))
    auton2_min = float(sim.get("min_autonomia_sag2", 999))
    auton_min  = min(auton1_min, auton2_min)
    t_crit1    = sim.get("t_critico_sag1_h")
    t_crit2    = sim.get("t_critico_sag2_h")

    # ¿Sobrevive? — ambas pilas sobre nivel crítico durante T8
    survives = (pile1_min >= 15.0) and (pile2_min >= 18.2)

    # P(crítico) — tabla MH calibrada, ajustada por margen de pila real
    _p_base = {0: 0.5, 2: 0.8, 4: 5.8, 8: 30.0, 12: 41.5}.get(t8_dur, 5.8)
    if survives:
        m1 = (pile1_min - 15.0) / max(5.0, pila1 - 15.0)
        m2 = (pile2_min - 18.2) / max(5.0, pila2 - 18.2)
        p_crit = _p_base * max(0.1, 1.0 - min(1.0, min(m1, m2)) * 0.7)
    else:
        deficit = (max(0.0, 15.0 - pile1_min) / 15.0
                   + max(0.0, 18.2 - pile2_min) / 18.2)
        p_crit = min(90.0, _p_base + deficit * 40.0)

    p_crit   = max(0.5, min(99.0, p_crit))
    p_surv   = max(1.0, 100.0 - p_crit)

    # Gráficos principales (reusa funciones existentes)
    fig_pilas = make_pile_chart(sim, horizonte_h=horizonte,
                                duracion_t8_h=float(t8_dur))
    fig_tph   = make_tph_chart(sim,  horizonte_h=horizonte,
                               duracion_t8_h=float(t8_dur))

    # Simulaciones de comparación: conservador y máxima producción
    def _sim_cmp(r1, r2, b1, b2):
        return simulate_scenario_cached(
            pila_sag1_pct=pila1, pila_sag2_pct=pila2,
            rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            bolas_sag1=b1, bolas_sag2=b2,
            sag1_activo=True, sag2_activo=True,
            duracion_t8_h=float(t8_dur),
            correa315_estado="activa", correa316_estado="activa",
            horizonte_horas=horizonte,
            ch1_on=True, ch2_on=True,
            cv_mode="auto",
            rate_sag1_tph=r1, rate_sag2_tph=r2,
        )

    sim_cons = _sim_cmp(900.0, 1800.0, "solo_411",       "solo_511")
    sim_max  = _sim_cmp(1500.0, 2600.0, "ambas_411_412", "ambas_511_512")

    def _esc(s, label):
        ta = np.array(s["time"])
        p1 = np.array(s["pile_sag1"])
        p2 = np.array(s["pile_sag2"])
        tp = np.array(s["tph_total"])
        ix = min(int(np.searchsorted(ta, float(t8_dur))), len(ta) - 1) if t8_dur > 0 else len(ta) - 1
        return {
            "nombre":    label,
            "tph":       float(tp[:ix + 1].mean()),
            "pile1_min": float(p1[:ix + 1].min()),
            "pile2_min": float(p2[:ix + 1].min()),
            "auton_min": min(float(s.get("min_autonomia_sag1", 999)),
                             float(s.get("min_autonomia_sag2", 999))),
        }

    fig_compare = make_ro_compare_chart([
        _esc(sim,      "Configurado"),
        _esc(sim_cons, "Conservador"),
        _esc(sim_max,  "Máx Producción"),
    ])

    # ── Indicador ¿SOBREVIVE? ─────────────────────────────────────────────────
    sv_color = VERDE if p_surv >= 70 else (AMARILLO if p_surv >= 40 else ROJO)
    sv_label = "SÍ" if survives else "NO"
    sobrevive = [
        html.Div("¿SOBREVIVE LA OPERACIÓN?",
                 style={"fontSize": "0.7rem", "fontWeight": "700", "color": "#555",
                        "letterSpacing": "0.5px", "marginBottom": "4px"}),
        dbc.Row([
            dbc.Col([
                html.Div(sv_label,
                         style={"fontSize": "2.8rem", "fontWeight": "900", "color": sv_color,
                                "lineHeight": "1", "border": f"3px solid {sv_color}",
                                "borderRadius": "6px", "textAlign": "center",
                                "padding": "6px 0"}),
            ], width=5),
            dbc.Col([
                html.Div(f"{p_surv:.0f}%",
                         style={"fontSize": "1.9rem", "fontWeight": "800", "color": sv_color}),
                html.Div("sin incidentes",    style={"fontSize": "0.68rem", "color": "#888"}),
                html.Div(f"T8 de {t8_dur}h" if t8_dur else "sin T8",
                         style={"fontSize": "0.68rem", "color": "#888"}),
            ], width=7, style={"paddingLeft": "6px"}),
        ]),
    ]

    # ── Indicador ¿Riesgo crítico? ────────────────────────────────────────────
    rc_color = VERDE if p_crit < 10 else (NARANJA if p_crit < 30 else ROJO)
    riesgo = [
        html.Div("¿RIESGO DE QUEDAR CRÍTICO?",
                 style={"fontSize": "0.7rem", "fontWeight": "700", "color": "#555",
                        "letterSpacing": "0.5px", "marginBottom": "4px"}),
        html.Div(f"{p_crit:.0f}%",
                 style={"fontSize": "2.6rem", "fontWeight": "900", "color": rc_color,
                        "lineHeight": "1", "marginBottom": "4px"}),
        html.Div([
            "SAG1 mín: ",
            html.Strong(f"{pile1_min:.1f}%",
                        style={"color": VERDE if pile1_min >= 25 else
                               (NARANJA if pile1_min >= 15 else ROJO)}),
            "  |  SAG2 mín: ",
            html.Strong(f"{pile2_min:.1f}%",
                        style={"color": VERDE if pile2_min >= 30 else
                               (NARANJA if pile2_min >= 18.2 else ROJO)}),
        ], style={"fontSize": "0.72rem", "color": "#555"}),
    ]

    # ── Métricas ──────────────────────────────────────────────────────────────
    def _kpi(label, val, unit, color):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(label, style={"fontSize": "0.62rem", "color": "#888",
                                   "marginBottom": "2px"}),
            html.Div([
                html.Strong(val, style={"fontSize": "1.1rem", "color": color}),
                html.Span(" " + unit, style={"fontSize": "0.62rem", "color": "#AAA"}),
            ]),
        ], style={"padding": "8px"}), style={"marginBottom": "4px"}), width=2)

    p1e_c = VERDE if pile1_end >= 25 else (NARANJA if pile1_end >= 15   else ROJO)
    p2e_c = VERDE if pile2_end >= 30 else (NARANJA if pile2_end >= 18.2 else ROJO)
    a_c   = VERDE if auton_min >= 4  else (NARANJA if auton_min >= 1.5  else ROJO)
    metricas = dbc.Row([
        _kpi("TPH SAG1",      f"{tph1_mean:.0f}", "TPH", AZUL_MED),
        _kpi("TPH SAG2",      f"{tph2_mean:.0f}", "TPH", NARANJA),
        _kpi("TPH Total",     f"{tph_mean:.0f}",  "TPH", AZUL),
        _kpi("Pila SAG1 fin", f"{pile1_end:.1f}", "%",   p1e_c),
        _kpi("Pila SAG2 fin", f"{pile2_end:.1f}", "%",   p2e_c),
        _kpi("Autonomía mín", f"{auton_min:.1f}", "h",   a_c),
    ], className="mb-2")

    # ── Recomendación ─────────────────────────────────────────────────────────
    if not survives:
        problems, actions = [], []
        if pile1_min < 15.0:
            p_txt = f"SAG1 llega a {pile1_min:.1f}% (crítico: <15%)"
            if t_crit1:
                p_txt += f" a las {t_crit1:.1f}h"
            problems.append(p_txt)
            actions.append("reducir rate SAG1 bajo 1000 TPH")
        if pile2_min < 18.2:
            p_txt = f"SAG2 llega a {pile2_min:.1f}% (crítico: <18.2%)"
            if t_crit2:
                p_txt += f" a las {t_crit2:.1f}h"
            problems.append(p_txt)
            actions.append("activar bolas SAG2 o bajar rate")
        nivel_txt, nivel_col = "ALTO", ROJO
        prob_txt = " | ".join(problems)
        rec_txt  = "Acción: " + " · ".join(actions) + "."
        icon = "✗"
    elif pile1_end < 25.0 or pile2_end < 30.0:
        nivel_txt, nivel_col = "MODERADO", NARANJA
        prob_txt = (f"Pila SAG1 queda en {pile1_end:.1f}% y SAG2 en {pile2_end:.1f}% "
                    "al terminar T8 — márgenes ajustados.")
        rec_txt  = ("Operación viable. Considerar aumentar inventario antes del T8 "
                    "o activar bolas para mayor margen de seguridad.")
        icon = "⚠"
    else:
        nivel_txt, nivel_col = "BAJO", VERDE
        prob_txt = (f"Pilas se mantienen seguras: SAG1 {pile1_end:.1f}%, "
                    f"SAG2 {pile2_end:.1f}% al término del T8.")
        rec_txt  = "Configuración segura. Puede operar con la configuración actual."
        icon = "✓"

    rec = dbc.CardBody([
        dbc.Row([
            dbc.Col([
                html.Div("Recomendación operacional",
                         style={"fontSize": "0.7rem", "color": "#888",
                                "fontWeight": "600", "marginBottom": "2px"}),
                html.Div([
                    html.Span(icon + " ", style={"fontSize": "1.1rem"}),
                    html.Strong(f"Riesgo {nivel_txt}",
                                style={"color": nivel_col, "fontSize": "0.88rem"}),
                ]),
            ], width=3),
            dbc.Col([
                html.Div(prob_txt, style={"fontSize": "0.78rem", "color": "#444",
                                          "marginBottom": "3px"}),
                html.Div(rec_txt,  style={"fontSize": "0.78rem", "color": AZUL,
                                          "fontWeight": "600"}),
            ], width=9),
        ]),
    ], style={"padding": "10px"})

    # R16 — al menos 1 molino de bolas activo por SAG (esta pagina asume
    # ambos SAG activos; no tiene switch de sag*_on).
    r16_violacion = (bolas1 == "sin_bola") or (bolas2 == "sin_bola")
    r16_badge = dbc.Badge(
        "R16 ✗ Violación regla" if r16_violacion else "R16 ✓ Cumple",
        color="danger" if r16_violacion else "success",
        style={"fontSize": "0.68rem"},
        title="Al menos 1 molino de bolas activo por SAG",
    )

    return fig_pilas, fig_tph, fig_compare, sobrevive, riesgo, metricas, rec, r16_badge


# ── Riesgo Operacional — presets de escenarios rápidos ───────────────────────
@app.callback(
    Output("ro-pila1-ini",   "value", allow_duplicate=True),
    Output("ro-pila2-ini",   "value", allow_duplicate=True),
    Output("ro-rate-sag1",   "value", allow_duplicate=True),
    Output("ro-rate-sag2",   "value", allow_duplicate=True),
    Output("ro-t8-dur",      "value", allow_duplicate=True),
    Output("ro-chancado",    "value", allow_duplicate=True),
    Output("ro-bolas-sag1",  "value", allow_duplicate=True),
    Output("ro-bolas-sag2",  "value", allow_duplicate=True),
    Output("ro-btn-t8-2",        "active"),
    Output("ro-btn-t8-4",        "active"),
    Output("ro-btn-t8-8",        "active"),
    Output("ro-btn-t8-12",       "active"),
    Output("ro-btn-falla-ch2",   "active"),
    Output("ro-btn-conservador", "active"),
    Output("ro-btn-max-prod",    "active"),
    Input("ro-btn-t8-2",        "n_clicks"),
    Input("ro-btn-t8-4",        "n_clicks"),
    Input("ro-btn-t8-8",        "n_clicks"),
    Input("ro-btn-t8-12",       "n_clicks"),
    Input("ro-btn-falla-ch2",   "n_clicks"),
    Input("ro-btn-conservador", "n_clicks"),
    Input("ro-btn-max-prod",    "n_clicks"),
    State("ro-pila1-ini",  "value"),
    State("ro-pila2-ini",  "value"),
    State("ro-rate-sag1",  "value"),
    State("ro-rate-sag2",  "value"),
    State("ro-chancado",   "value"),
    State("ro-bolas-sag1", "value"),
    State("ro-bolas-sag2", "value"),
    prevent_initial_call=True,
)
def preset_riesgo_scenario(
    _b2, _b4, _b8, _b12, _bch2, _bcons, _bmax,
    p1, p2, r1, r2, ch, b1, b2s,
):
    from dash import ctx
    tid = ctx.triggered_id

    p1  = p1  or 45;   p2  = p2  or 40
    r1  = r1  or 1236; r2  = r2  or 2214
    ch  = ch  or "normal"
    b1  = b1  or "solo_411"; b2s = b2s or "solo_511"

    _preset_ids = ["ro-btn-t8-2", "ro-btn-t8-4", "ro-btn-t8-8", "ro-btn-t8-12",
                   "ro-btn-falla-ch2", "ro-btn-conservador", "ro-btn-max-prod"]
    active = tuple(pid == tid for pid in _preset_ids)

    if   tid == "ro-btn-t8-2":        return (p1, p2, r1, r2, 2,  ch,         b1,              b2s,  *active)
    elif tid == "ro-btn-t8-4":        return (p1, p2, r1, r2, 4,  ch,         b1,              b2s,  *active)
    elif tid == "ro-btn-t8-8":        return (p1, p2, r1, r2, 8,  ch,         b1,              b2s,  *active)
    elif tid == "ro-btn-t8-12":       return (p1, p2, r1, r2, 12, ch,         b1,              b2s,  *active)
    elif tid == "ro-btn-falla-ch2":   return (p1, p2, r1, r2, 4,  "solo_ch1", b1,              b2s,  *active)
    elif tid == "ro-btn-conservador": return (p1, p2, 900, 1800, 4, ch,    "solo_411",    "solo_511", *active)
    elif tid == "ro-btn-max-prod":    return (p1, p2, 1500, 2600, 4, ch, "ambas_411_412", "ambas_511_512", *active)
    return (p1, p2, r1, r2, 4, ch, b1, b2s, *active)


def _scenario_card(
    idx: int, titulo: str, *,
    t8_default: int = 0, ch2_default: bool = True,
    sag_default: str = "ambos",
    bolas1_default: str = "solo_411",
    bolas2_default: str = "solo_511",
) -> dbc.Card:
    """Tarjeta de configuración de un escenario para el comparador What-If."""
    _lbl = {"fontSize": "0.7rem", "color": "#555", "fontWeight": "600",
            "marginBottom": "2px"}
    return dbc.Card([
        dbc.CardHeader(html.Strong(titulo, style={"fontSize": "0.8rem"})),
        dbc.CardBody([
            html.Div("Pila SAG1 inicial (%)", style=_lbl),
            dcc.Slider(id=f"wif-pila1-{idx}", min=10, max=90, step=1, value=55,
                       marks={10: "10%", 50: "50%", 90: "90%"},
                       tooltip={"placement": "bottom", "always_visible": False}),
            html.Div("Pila SAG2 inicial (%)", style={**_lbl, "marginTop": "8px"}),
            dcc.Slider(id=f"wif-pila2-{idx}", min=10, max=90, step=1, value=55,
                       marks={10: "10%", 50: "50%", 90: "90%"},
                       tooltip={"placement": "bottom", "always_visible": False}),

            html.Hr(style={"margin": "10px 0"}),

            html.Div("SAG activos", style=_lbl),
            dbc.RadioItems(
                id=f"wif-sag-{idx}",
                options=[
                    {"label": "Ambos", "value": "ambos"},
                    {"label": "Solo SAG1", "value": "sag1"},
                    {"label": "Solo SAG2", "value": "sag2"},
                ],
                value=sag_default, inline=True, style={"fontSize": "0.72rem"},
            ),

            html.Div("Ventana de T8", style={**_lbl, "marginTop": "8px"}),
            dbc.RadioItems(
                id=f"wif-t8-{idx}",
                options=[
                    {"label": "Sin T8", "value": 0},
                    {"label": "2h", "value": 2},
                    {"label": "4h", "value": 4},
                    {"label": "8h", "value": 8},
                    {"label": "12h", "value": 12},
                ],
                value=t8_default, inline=True, style={"fontSize": "0.72rem"},
            ),

            dbc.Switch(id=f"wif-ch2-{idx}", label="Chancador 2 activo",
                       value=ch2_default, className="mt-2",
                       style={"fontSize": "0.75rem"}),

            html.Hr(style={"margin": "10px 0"}),

            dbc.Row([
                dbc.Col([
                    html.Div("Bolas SAG1", style=_lbl),
                    dbc.RadioItems(
                        id=f"wif-bolas1-{idx}",
                        options=[
                            {"label": "1 MoBo", "value": "solo_411"},
                            {"label": "2 MoBos", "value": "ambas_411_412"},
                        ],
                        value=bolas1_default, style={"fontSize": "0.72rem"},
                    ),
                ], width=6),
                dbc.Col([
                    html.Div("Bolas SAG2", style=_lbl),
                    dbc.RadioItems(
                        id=f"wif-bolas2-{idx}",
                        options=[
                            {"label": "1 MoBo", "value": "solo_511"},
                            {"label": "2 MoBos", "value": "ambas_511_512"},
                        ],
                        value=bolas2_default, style={"fontSize": "0.72rem"},
                    ),
                ], width=6),
            ]),
        ], style={"padding": "10px"}),
    ])


def _kpi_mini_card(titulo: str, valor: str, detalle: str = "") -> dbc.Card:
    return dbc.Card(dbc.CardBody([
        html.Div(titulo, style={"fontSize": "0.62rem", "color": "#8896AF", "textTransform": "uppercase",
                                 "letterSpacing": "0.05em"}),
        html.Div(valor, style={"fontSize": "1.3rem", "fontWeight": "800", "color": AZUL}),
        html.Div(detalle, style={"fontSize": "0.62rem", "color": "#8896AF"}) if detalle else None,
    ], style={"padding": "8px 10px"}), style={"border": "1px solid #1a3a6c", "backgroundColor": "#0F2647"})


def page_desempeno_gemelo() -> html.Div:
    """Fase 8 (parcial), cierre de brechas "Validacion Operacional
    Real" (2026-07-07): pagina de solo lectura, sin callbacks propios
    (se recalcula en cada render, mismo patron que page_historico/
    page_analisis). Uso y Adopcion son reales desde el dia 1 (fuente:
    utils/usage_logger.py). Calidad reusa el backtesting YA construido
    (engine/historical_backtesting.py, sin tocar). Valor se muestra
    explicitamente como pendiente — no se fabrica un numero de
    toneladas/PAM sin datos reales acumulados en
    01_Data/Operational_Decisions/ (ver Fase 4 del roadmap,
    04_Reports/Technical/20260707_Operational_Validation_Plan.md)."""
    from utils.usage_logger import read_sessions, adopcion_global
    from utils.operational_case_logger import list_operational_cases

    try:
        sesiones = read_sessions()
    except Exception:
        sesiones = []
    try:
        adopcion = adopcion_global()
    except Exception:
        adopcion = {"total": 0, "si": 0, "no": 0, "parcial": 0, "no_registrada": 0, "pct_aceptacion": None}
    try:
        n_casos = len(list_operational_cases())
    except Exception:
        n_casos = 0

    n_simulaciones = sum(s.get("n_simulaciones", 0) for s in sesiones)
    n_recomendaciones = sum(s.get("n_recomendaciones", 0) for s in sesiones)
    usuarios = sorted({s["usuario"] for s in sesiones if s.get("usuario")})

    uso_row = dbc.Row([
        dbc.Col(_kpi_mini_card("Sesiones registradas", str(len(sesiones))), md=3),
        dbc.Col(_kpi_mini_card("Simulaciones", str(n_simulaciones)), md=3),
        dbc.Col(_kpi_mini_card("Recomendaciones generadas", str(n_recomendaciones)), md=3),
        dbc.Col(_kpi_mini_card("Usuarios distintos", str(len(usuarios)),
                                ", ".join(usuarios) if usuarios else "sin datos"), md=3),
    ], className="mb-3 g-2")

    adopcion_txt = f"{adopcion['pct_aceptacion']:.0f}%" if adopcion["pct_aceptacion"] is not None else "Sin datos aún"
    adopcion_detalle = (
        f"{adopcion['si']} SI · {adopcion['no']} NO · {adopcion['parcial']} PARCIAL · "
        f"{adopcion['no_registrada']} sin registrar"
        if adopcion["total"] else "Ninguna recomendación con feedback todavía"
    )
    adopcion_row = dbc.Row([
        dbc.Col(_kpi_mini_card("Adopción (% recomendaciones aceptadas)", adopcion_txt, adopcion_detalle), md=6),
        dbc.Col(_kpi_mini_card("Casos operacionales validados", str(n_casos),
                                "runtime_data/operational_cases/"), md=6),
    ], className="mb-3 g-2")

    # Calidad: reusa run_backtest/run_backtest_proxy YA construidos —
    # esto SI tiene datos reales desde hoy, no depende de acumular uso.
    from engine.historical_backtesting import run_backtest
    regimenes_calidad = ["t8_corta", "t8_larga", "overflow", "inventario_critico",
                          "mantenimiento", "alimentacion_restringida"]
    filas_calidad = []
    for r in regimenes_calidad:
        try:
            bt = run_backtest(r)
        except Exception:
            continue
        filas_calidad.append(html.Tr([
            html.Td(r),
            html.Td(str(bt.n_eventos)),
            html.Td(f"{bt.pila_mae_sag1_pp:.1f}" if bt.pila_mae_sag1_pp is not None else "—"),
            html.Td(f"{bt.error_tiempo_critico_h:.2f}" if bt.error_tiempo_critico_h is not None else "—"),
            html.Td("Disponible" if bt.historica_disponible else "No disponible",
                     style={"color": "#4FCE82" if bt.historica_disponible else "#8896AF"}),
        ]))
    calidad_table = dbc.Table(
        [html.Thead(html.Tr([html.Th("Régimen"), html.Th("N eventos"), html.Th("MAE pila (pp)"),
                              html.Th("Error hasta crítico (h)"), html.Th("Estado")])),
         html.Tbody(filas_calidad)],
        bordered=False, hover=True, size="sm", className="mb-3",
        style={"fontSize": "0.72rem", "color": AZUL},
    )

    return html.Div([
        html.H5("Desempeño del Gemelo Digital", className="page-title"),
        html.Div(
            "Uso y adopción son datos reales desde hoy. Calidad reusa el backtesting histórico ya "
            "validado. Valor operacional (toneladas recuperadas, cumplimiento PAM) requiere acumular "
            "casos reales en 01_Data/Operational_Decisions/ — ver roadmap.",
            style={"fontSize": "0.7rem", "color": "#8896AF", "marginBottom": "10px"},
        ),
        html.Div("Uso", className="section-header"),
        uso_row,
        html.Div("Adopción", className="section-header"),
        adopcion_row,
        html.Div("Calidad (backtesting por régimen)", className="section-header"),
        calidad_table,
        html.Div("Valor operacional", className="section-header"),
        dbc.Alert(
            "Pendiente — requiere acumular casos en 01_Data/Operational_Decisions/ con "
            "resultado_observado registrado (Fase 4 del roadmap, ver "
            "04_Reports/Technical/20260707_Operational_Validation_Plan.md). No se muestra un número "
            "estimado para evitar reportar valor que todavía no se midió.",
            color="secondary", style={"fontSize": "0.74rem"},
        ),
    ])


_SLA_MS = {
    "update_simulation_total": ("Vista principal", 3000.0),
    "route_and_simulate": ("Vista riesgo (router v2)", 5000.0),
    "adaptive_mc_eval": ("Monte Carlo avanzado", 10000.0),
}


def page_performance() -> html.Div:
    """Fase 8, "Hardening operacional del simulador" (2026-07-09):
    pagina de solo lectura (mismo patron que /desempeno_gemelo, sin
    callbacks propios) sobre runtime_data/performance_log.csv — ya
    poblado por utils/perf_logger.py (usado desde antes de esta fase
    por engine/scenario_cache.py) + los 3 timers nuevos agregados en
    este cierre (route_and_simulate, render_figuras,
    update_simulation_total). No se fabrica ningun numero: si el CSV
    no existe todavia (instalacion nueva, sin uso previo), se muestra
    un aviso en vez de un valor inventado."""
    import os
    import pandas as pd

    _here = os.path.dirname(os.path.abspath(__file__))
    _csv_path = os.path.join(_here, "runtime_data", "performance_log.csv")

    if not os.path.exists(_csv_path):
        return html.Div([
            html.H5("Desempeño del Simulador", className="page-title"),
            dbc.Alert("Sin datos todavía — runtime_data/performance_log.csv se genera con el uso normal "
                      "del dashboard (engine/scenario_cache.py + utils/perf_logger.py).", color="secondary"),
        ])

    try:
        df = pd.read_csv(_csv_path)
    except Exception:
        return html.Div([
            html.H5("Desempeño del Simulador", className="page-title"),
            dbc.Alert("No se pudo leer runtime_data/performance_log.csv.", color="danger"),
        ])

    # 2026-07-09: performance_log.csv acumula filas de multiples
    # procesos (ej. dos `python app.py` corriendo a la vez por error de
    # higiene de procesos) — un lock de threading (utils/perf_logger.py)
    # protege contra escrituras concurrentes DENTRO de un proceso, pero
    # no entre procesos distintos, lo que puede dejar alguna fila
    # intercalada/corrupta (ej. accion='False', duracion_ms='ok'). Una
    # sola fila asi basta para que pandas 3.0 infiera toda la columna
    # como dtype 'str' en vez de float64 y reviente en .mean()/.agg().
    # Se descartan filas no numericas en vez de asumir el CSV limpio.
    n_total = len(df)
    df["duracion_ms"] = pd.to_numeric(df["duracion_ms"], errors="coerce")
    df = df.dropna(subset=["duracion_ms", "accion"])
    n_descartadas = n_total - len(df)

    g = df.groupby("accion")["duracion_ms"].agg(["count", "mean", "median", "max"])
    g = g.sort_values("mean", ascending=False)
    # pandas 3.0+ (ver feedback_technical.md): filas de acciones sin
    # cache_hit (ej. startup_*) quedan NaN, lo que fuerza la columna a
    # dtype 'object'/'str' — .mean() directo revienta con
    # "dtype 'str' does not support operation 'mean'". Normalizar a bool
    # explicito (NaN -> False, "sin cache" no es "cache hit") antes de
    # agregar.
    hit_ratio = df.assign(cache_hit=df["cache_hit"].fillna(False).astype(bool)).groupby("accion")["cache_hit"].mean()

    filas_top = []
    for accion, row in g.head(20).iterrows():
        hr = hit_ratio.get(accion, 0.0)
        filas_top.append(html.Tr([
            html.Td(accion),
            html.Td(f"{int(row['count']):,}"),
            html.Td(f"{row['mean']:.0f}"),
            html.Td(f"{row['median']:.0f}"),
            html.Td(f"{row['max']:.0f}"),
            html.Td(f"{hr*100:.0f}%"),
        ]))
    top20_table = dbc.Table(
        [html.Thead(html.Tr([html.Th("Acción"), html.Th("N"), html.Th("Media (ms)"),
                              html.Th("Mediana (ms)"), html.Th("Máx (ms)"), html.Th("Cache hit")])),
         html.Tbody(filas_top)],
        bordered=False, hover=True, size="sm", className="mb-3",
        style={"fontSize": "0.72rem", "color": AZUL},
    )

    filas_sla = []
    for accion, (label, umbral_ms) in _SLA_MS.items():
        if accion not in g.index:
            filas_sla.append(html.Tr([html.Td(label), html.Td(f"< {umbral_ms/1000:.0f}s"),
                                       html.Td("Sin datos"), html.Td("—")]))
            continue
        media = g.loc[accion, "mean"]
        cumple = media < umbral_ms
        filas_sla.append(html.Tr([
            html.Td(label), html.Td(f"< {umbral_ms/1000:.0f}s"),
            html.Td(f"{media/1000:.1f}s (media real)"),
            html.Td("✓ Cumple" if cumple else "✗ No cumple",
                     style={"color": "#4FCE82" if cumple else "#E94A4A", "fontWeight": "700"}),
        ]))
    sla_table = dbc.Table(
        [html.Thead(html.Tr([html.Th("SLA"), html.Th("Objetivo"), html.Th("Medido"), html.Th("Estado")])),
         html.Tbody(filas_sla)],
        bordered=False, hover=True, size="sm", className="mb-3",
        style={"fontSize": "0.72rem", "color": AZUL},
    )

    return html.Div([
        html.H5("Desempeño del Simulador", className="page-title"),
        html.Div(
            f"Basado en {len(df):,} eventos reales registrados en runtime_data/performance_log.csv "
            "(engine/scenario_cache.py + utils/perf_logger.py). Detalle completo en "
            "04_Reports/Technical/20260709_Performance_Hardening.md."
            + (f" ({n_descartadas} fila(s) descartada(s) por formato inválido — probable escritura "
               "concurrente de más de un proceso de la app a la vez.)" if n_descartadas else ""),
            style={"fontSize": "0.7rem", "color": "#8896AF", "marginBottom": "10px"},
        ),
        html.Div("SLA operacional", className="section-header"),
        sla_table,
        html.Div("Top 20 acciones por duración media", className="section-header"),
        top20_table,
        dbc.Alert(
            "El guard anti-resultado-desactualizado (banner amarillo en el simulador cuando una "
            "respuesta llega vieja) corre 100% client-side y no persiste un contador histórico en "
            "esta versión — se ve en vivo en /  , no acumulado acá.",
            color="secondary", style={"fontSize": "0.7rem"},
        ),
    ])


def page_analisis() -> html.Div:
    return html.Div([
        dbc.Row([
            dbc.Col(html.H5("Análisis de Escenarios What-If",
                            className="page-title"), width=12),
        ]),
        dbc.Row([
            dbc.Col(dbc.Alert([
                html.Strong("Gemelo Digital — ¿Qué pasa si...? "),
                "Configura hasta 3 escenarios y compara IRO, autonomía y TPH en un click.",
            ], color="info", style={"padding": "6px 12px", "fontSize": "0.82rem"}), width=12),
        ], className="mb-2"),

        # ── Tarjetas de escenarios ────────────────────────────────────────────
        dbc.Row([
            dbc.Col(_scenario_card(1, "Operación Normal",
                                   t8_default=0,  ch2_default=True,
                                   sag_default="ambos",
                                   bolas1_default="ambas_411_412",
                                   bolas2_default="ambas_511_512"), width=4),
            dbc.Col(_scenario_card(2, "T8 8h + CH2 fuera",
                                   t8_default=8,  ch2_default=False,
                                   sag_default="ambos",
                                   bolas1_default="ambas_411_412",
                                   bolas2_default="ambas_511_512"), width=4),
            dbc.Col(_scenario_card(3, "Contingencia máxima",
                                   t8_default=12, ch2_default=False,
                                   sag_default="sag2",
                                   bolas1_default="solo_411",
                                   bolas2_default="solo_511"), width=4),
        ], className="mb-2"),

        dbc.Row([
            dbc.Col(
                dbc.Button("Simular y Comparar escenarios",
                           id="btn-comparar-whatif",
                           color="primary", size="md",
                           style={"width": "100%", "fontWeight": "700",
                                  "fontSize": "0.9rem"}),
                width={"size": 4, "offset": 4},
            ),
        ], className="mb-3"),

        # ── Resultados ────────────────────────────────────────────────────────
        html.Div(id="whatif-result-cards", className="mb-2"),
        dbc.Card(dbc.CardBody([
            dcc.Graph(id="graph-whatif-comparison",
                      config={"displayModeBar": False}),
        ], style={"padding": "8px"}),
        style={"display": "none"}, id="card-whatif-chart"),
    ])


# ── Router ────────────────────────────────────────────────────────────────────
@app.callback(Output("page-content", "children"), Input("url", "pathname"))
def render_page(pathname):
    if pathname == "/historico":
        return page_historico()
    if pathname == "/analisis":
        return page_analisis()
    if pathname == "/riesgo":
        return page_riesgo_operacional()
    if pathname == "/desempeno_gemelo":
        return page_desempeno_gemelo()
    if pathname == "/performance":
        return page_performance()
    return page_simulador_operacional()



# ── What-If comparador ────────────────────────────────────────────────────────
@app.callback(
    Output("whatif-result-cards",     "children"),
    Output("graph-whatif-comparison", "figure"),
    Output("card-whatif-chart",       "style"),
    Input("btn-comparar-whatif", "n_clicks"),
    # Escenario 1
    State("wif-t8-1",     "value"), State("wif-pila1-1", "value"),
    State("wif-pila2-1",  "value"), State("wif-sag-1",   "value"),
    State("wif-ch2-1",    "value"), State("wif-bolas1-1","value"),
    State("wif-bolas2-1", "value"),
    # Escenario 2
    State("wif-t8-2",     "value"), State("wif-pila1-2", "value"),
    State("wif-pila2-2",  "value"), State("wif-sag-2",   "value"),
    State("wif-ch2-2",    "value"), State("wif-bolas1-2","value"),
    State("wif-bolas2-2", "value"),
    # Escenario 3
    State("wif-t8-3",     "value"), State("wif-pila1-3", "value"),
    State("wif-pila2-3",  "value"), State("wif-sag-3",   "value"),
    State("wif-ch2-3",    "value"), State("wif-bolas1-3","value"),
    State("wif-bolas2-3", "value"),
    prevent_initial_call=True,
)
def comparar_whatif(
    _clicks,
    t8_1, p1_1, p2_1, sag_1, ch2_1, b1_1, b2_1,
    t8_2, p1_2, p2_2, sag_2, ch2_2, b1_2, b2_2,
    t8_3, p1_3, p2_3, sag_3, ch2_3, b1_3, b2_3,
):
    from engine.simulator import simulate_scenario_cached
    from engine.risk_engine import compute_iro

    nombres = ["Escenario 1", "Escenario 2", "Escenario 3"]
    configs = [
        (t8_1 or 0, p1_1 or 55, p2_1 or 55, sag_1 or "ambos",
         bool(ch2_1), b1_1 or "solo_411", b2_1 or "solo_511"),
        (t8_2 or 0, p1_2 or 55, p2_2 or 55, sag_2 or "ambos",
         bool(ch2_2), b1_2 or "solo_411", b2_2 or "solo_511"),
        (t8_3 or 0, p1_3 or 55, p2_3 or 55, sag_3 or "ambos",
         bool(ch2_3), b1_3 or "solo_411", b2_3 or "solo_511"),
    ]

    resultados = []
    for nombre, (t8, p1, p2, sag, ch2_on, bolas1, bolas2) in zip(nombres, configs):
        sag1_on = sag in ("ambos", "sag1")
        sag2_on = sag in ("ambos", "sag2")
        sim = simulate_scenario_cached(
            pila_sag1_pct=p1, pila_sag2_pct=p2,
            rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            bolas_sag1=bolas1, bolas_sag2=bolas2,
            sag1_activo=sag1_on, sag2_activo=sag2_on,
            duracion_t8_h=t8,
            correa315_estado="activa", correa316_estado="activa",
            horizonte_horas=24,
            ch1_on=True, ch2_on=ch2_on,
        )
        iro = sim.get("iro_result", {}).get("iro", 0)
        a1  = float(sim.get("min_autonomia_sag1", 0))
        a2  = float(sim.get("min_autonomia_sag2", 0))
        accion = sim.get("accion_recomendada", "DESCONOCIDO")
        tph_total = float(np.array(sim.get("tph_total", [0])).mean())
        resultados.append(dict(nombre=nombre, iro=iro, auton_sag1=a1,
                               auton_sag2=a2, tph_total=tph_total, accion=accion))

    # Tarjetas de resultado
    _sev_color = lambda v, t1, t2: (VERDE if v >= t2 else (AMARILLO if v >= t1 else ROJO))
    cards = []
    for r in resultados:
        iro_c = _sev_color(r["iro"], 40, 70)
        a1_c  = _sev_color(r["auton_sag1"], 1.0, 2.5)
        a2_c  = _sev_color(r["auton_sag2"], 2.5, 4.0)
        ac_color = {"EMERGENCIA": "danger", "EVALUAR_DETENCION": "warning",
                    "MINIMO_TECNICO": "warning"}.get(r["accion"], "success")
        cards.append(dbc.Col([
            dbc.Card(dbc.CardBody([
                html.Div(r["nombre"],
                         style={"fontWeight": "700", "color": AZUL,
                                "fontSize": "0.82rem", "marginBottom": "6px"}),
                dbc.Row([
                    dbc.Col([
                        html.Div("IRO", style={"fontSize": "0.7rem", "color": "#888"}),
                        html.Div(f"{r['iro']:.0f}",
                                 style={"fontSize": "1.6rem", "fontWeight": "800",
                                        "color": iro_c, "lineHeight": "1.1"}),
                    ], width=4),
                    dbc.Col([
                        html.Div("SAG1 mín.",
                                 style={"fontSize": "0.7rem", "color": "#888"}),
                        html.Div(f"{r['auton_sag1']:.1f}h",
                                 style={"fontSize": "1.2rem", "fontWeight": "700",
                                        "color": a1_c}),
                        html.Div("SAG2 mín.",
                                 style={"fontSize": "0.7rem", "color": "#888",
                                        "marginTop": "4px"}),
                        html.Div(f"{r['auton_sag2']:.1f}h",
                                 style={"fontSize": "1.2rem", "fontWeight": "700",
                                        "color": a2_c}),
                    ], width=4),
                    dbc.Col([
                        html.Div("TPH prom.",
                                 style={"fontSize": "0.7rem", "color": "#888"}),
                        html.Div(f"{r['tph_total']:.0f}",
                                 style={"fontSize": "1.1rem", "fontWeight": "700",
                                        "color": AZUL}),
                        html.Div(className="mt-2"),
                        dbc.Badge(r["accion"], color=ac_color,
                                  style={"fontSize": "0.65rem"}),
                    ], width=4),
                ]),
            ], style={"padding": "10px"}),
            style={"border": f"2px solid {iro_c}", "borderRadius": "6px"}),
        ], width=4))

    fig = make_whatif_comparison_chart(resultados)
    return dbc.Row(cards), fig, {"display": "block"}



# ── Callback Reset Escenario (riesgo) ─────────────────────────────────────────
@app.callback(
    Output("ro-pila1-ini",  "value", allow_duplicate=True),
    Output("ro-pila2-ini",  "value", allow_duplicate=True),
    Output("ro-rate-sag1",  "value", allow_duplicate=True),
    Output("ro-rate-sag2",  "value", allow_duplicate=True),
    Output("ro-t8-dur",     "value", allow_duplicate=True),
    Output("ro-chancado",   "value", allow_duplicate=True),
    Output("ro-bolas-sag1", "value", allow_duplicate=True),
    Output("ro-bolas-sag2", "value", allow_duplicate=True),
    Output("ro-btn-t8-2",        "active", allow_duplicate=True),
    Output("ro-btn-t8-4",        "active", allow_duplicate=True),
    Output("ro-btn-t8-8",        "active", allow_duplicate=True),
    Output("ro-btn-t8-12",       "active", allow_duplicate=True),
    Output("ro-btn-falla-ch2",   "active", allow_duplicate=True),
    Output("ro-btn-conservador", "active", allow_duplicate=True),
    Output("ro-btn-max-prod",    "active", allow_duplicate=True),
    Output("ro-btn-mejor-config", "active", allow_duplicate=True),
    Output("ro-btn-max-prod-opt", "active", allow_duplicate=True),
    Output("ro-btn-op-segura",    "active", allow_duplicate=True),
    Output("ro-btn-balance-opt",  "active", allow_duplicate=True),
    Input("ro-btn-reset",   "n_clicks"),
    prevent_initial_call=True,
)
def reset_riesgo_scenario(_clicks):
    try:
        state   = load_current_state()
        pila1   = float(state.get("pila_sag1", 45))
        pila2   = float(state.get("pila_sag2", 40))
        rate1   = float(state.get("rate_sag1_tph", 1236))
        rate2   = float(state.get("rate_sag2_tph", 2214))
        t8_dur  = int(state.get("t8_duracion_selector", 0))
        ch1_on  = state.get("ch1_on", True)
        ch2_on  = state.get("ch2_on", True)
        bolas1  = state.get("bolas_sag1", "solo_411")
        bolas2  = state.get("bolas_sag2", "solo_511")
        if ch1_on and ch2_on:
            chancado = "normal"
        elif ch1_on:
            chancado = "solo_ch1"
        else:
            chancado = "sin_chancado"
    except Exception:
        pila1, pila2, rate1, rate2 = 45, 40, 1236, 2214
        t8_dur, chancado = 0, "normal"
        bolas1, bolas2 = "solo_411", "solo_511"
    return (pila1, pila2, rate1, rate2, t8_dur, chancado, bolas1, bolas2,
            False, False, False, False, False, False, False,
            False, False, False, False)


# ── Callback Optimizer Buttons (riesgo) ───────────────────────────────────────
@app.callback(
    Output("ro-rate-sag1",            "value",    allow_duplicate=True),
    Output("ro-rate-sag2",            "value",    allow_duplicate=True),
    Output("ro-bolas-sag1",           "value",    allow_duplicate=True),
    Output("ro-bolas-sag2",           "value",    allow_duplicate=True),
    Output("div-top5-riesgo",         "children"),
    Output("ro-graph-pareto",         "figure"),
    Output("ro-graph-bola-impact",    "figure"),
    Output("row-ro-optimizer-charts", "style"),
    Output("ro-btn-mejor-config",     "active"),
    Output("ro-btn-max-prod-opt",     "active"),
    Output("ro-btn-op-segura",        "active"),
    Output("ro-btn-balance-opt",      "active"),
    Input("ro-btn-mejor-config",      "n_clicks"),
    Input("ro-btn-max-prod-opt",      "n_clicks"),
    Input("ro-btn-op-segura",         "n_clicks"),
    Input("ro-btn-balance-opt",       "n_clicks"),
    State("ro-pila1-ini",  "value"),
    State("ro-pila2-ini",  "value"),
    State("ro-t8-dur",     "value"),
    State("ro-chancado",   "value"),
    prevent_initial_call=True,
)
def run_riesgo_optimizer(_c1, _c2, _c3, _c4, pila1, pila2, t8_dur, chancado):
    _mode_map = {
        "ro-btn-mejor-config": "balanced",
        "ro-btn-max-prod-opt": "max_prod",
        "ro-btn-op-segura":    "safe",
        "ro-btn-balance-opt":  "pareto",
    }
    _mode_labels = {
        "balanced": "Mejor Configuracion",
        "max_prod": "Maxima Produccion",
        "safe":     "Operacion Segura",
        "pareto":   "Balance Optimo",
    }
    tid  = ctx.triggered_id
    mode = _mode_map.get(tid, "balanced")
    _opt_ids = ["ro-btn-mejor-config", "ro-btn-max-prod-opt",
                "ro-btn-op-segura", "ro-btn-balance-opt"]
    active = tuple(oid == tid for oid in _opt_ids)

    pila1  = float(pila1  or 45)
    pila2  = float(pila2  or 40)
    t8_dur = float(t8_dur or 0)
    ch1_on = chancado in ("normal", "solo_ch1")
    ch2_on = chancado == "normal"

    best, all_results = find_optimal_v3(
        pila1=pila1, pila2=pila2, duracion_t8=t8_dur,
        sag1_on=True, sag2_on=True,
        ch1_on=ch1_on, ch2_on=ch2_on,
        c315="activa", c316="activa",
        t1_mode="chancado", t1_manual=4000.0,
        t3_frac=0.0, distribucion_t1="proporcional",
        horizonte=24.0,
        mode=mode,
    )

    top5_card  = make_top5_card(format_top5_records(all_results[:5]), _mode_labels[mode])
    fig_pareto = make_pareto_scatter(all_results)
    fig_bola   = make_bola_impact_chart(all_results)

    return (
        best["r1"], best["r2"],
        best["b1"], best["b2"],
        top5_card,
        fig_pareto,
        fig_bola,
        {"display": "flex"},
        *active,
    )


if __name__ == "__main__":
    log.info("Iniciando Dashboard Molienda SAG T8...")
    log.info(f"ROOT: {_ROOT}")
    # threaded=True: necesario porque un solo cambio de slider dispara en
    # paralelo update_simulation (rapido) y run_monte_carlo (hasta 500
    # simulaciones, ahora reactivo). Sin threading, el servidor dev de
    # Flask es single-threaded y serializa las peticiones -> la rapida
    # queda bloqueada detras de la lenta -> "Callback failed: the server
    # did not respond" en el navegador.
    app.run(debug=True, port=8050, use_reloader=False, threaded=True)
