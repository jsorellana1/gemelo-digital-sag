"""
components/navigation.py — Navegación interna del Simulador Operacional
(rediseño 2026-07-14, ver 04_Reports/Technical/
20260714_Rediseno_Navegacion_UX_Simulador.md).

Centraliza lo que el pedido llama NAV_SECTIONS/CHART_TABS: los ids de
sección (anclas) y la barra sticky que navega entre ellas, en un solo
lugar en vez de strings dispersos en pages/simulador_operacional.py.

Lección ya documentada en assets/styles.css (2026-07-07): un
`position: sticky` mal aislado en `#sim-summary-bar` superponia/recortaba
contenido inferior. Esta barra es un componente NUEVO y separado
(`.simulation-section-nav`), con su propio fondo opaco y z-index, para no
repetir ese bug — nunca se reutiliza la clase de sim-summary-bar.
"""

from dash import html
import dash_bootstrap_components as dbc

# ── Ids de seccion (anclas) — unica fuente de verdad ──────────────────────
SECTION_SUMMARY = "section-summary"
SECTION_STOCKPILES = "section-stockpiles"
SECTION_CHARTS = "section-charts"
SECTION_CONTROLS = "section-controls"
SECTION_DIAGNOSTICS = "section-diagnostics"

# Segunda iteración UX/UI (2026-07-14, Fase 6 sec.16 del pedido):
# "Operación" -> "Decisión" (ahora aloja el Decision Banner, coherente
# con el nombre) y "Escenario" -> "Simulación" (es donde se configura la
# simulación) — mismos ids/anclas, solo el rótulo visible cambia.
NAV_SECTIONS = [
    {"id": SECTION_SUMMARY, "label": "Resumen"},
    {"id": SECTION_STOCKPILES, "label": "Decisión"},
    {"id": SECTION_CHARTS, "label": "Gráficos"},
    {"id": SECTION_CONTROLS, "label": "Simulación"},
    {"id": SECTION_DIAGNOSTICS, "label": "Diagnóstico"},
]

# CHART_TABS: mismas 10 opciones de sim-main-view, extraidas de
# pages/simulador_operacional.py para que exista una unica fuente (el
# layout las importa en vez de declararlas inline).
CHART_TABS = [
    {"label": "Inventario", "value": "pilas"},
    {"label": "TPH", "value": "tph"},
    {"label": "Riesgo", "value": "riesgo"},
    {"label": "T1 / CV", "value": "alimentacion"},
    {"label": "Balance T1/T3", "value": "balance_t1t3"},
    {"label": "Cuellos de Botella", "value": "cuellos_botella"},
    {"label": "Planificador de Turno", "value": "planificador_turno"},
    {"label": "Cumplimiento PAM", "value": "cumplimiento_pam"},
    {"label": "Sensibilidad", "value": "sensibilidad"},
    {"label": "Robustez MC", "value": "robustez_mc"},
]

# Segunda iteración UX/UI (2026-07-14, Fase 5 sec.11 del pedido):
# agrupa las 10 vistas planas de CHART_TABS en categorías para que
# sim-main-view no muestre 10 botones simultaneos en pantallas chicas —
# mismos valores de CHART_TABS, solo se filtra cuáles se muestran segun
# la categoria activa. "Equipos" (disponibilidad/molinos de bolas) no
# tiene valores propios aca: esas vistas ya viven en los tabs de
# Diagnóstico (graph-gantt-operacional/graph-bolas), no se duplican.
CHART_CATEGORIES = [
    {"id": "operacion", "label": "Operación", "vistas": ["pilas", "tph", "alimentacion"]},
    {"id": "riesgo", "label": "Riesgo", "vistas": ["riesgo", "cumplimiento_pam", "robustez_mc"]},
    {"id": "analisis", "label": "Análisis", "vistas": ["balance_t1t3", "cuellos_botella", "sensibilidad", "planificador_turno"]},
]
CHART_CATEGORY_DEFAULT = "operacion"


def build_section_nav() -> html.Nav:
    """Barra sticky con anclas a cada seccion (Fase 2, secciones 4-5 del
    pedido). Usa <a href="#id"> con scroll-behavior:smooth (CSS global) —
    no dispara ningun callback ni recarga la pagina."""
    return html.Nav(
        [
            html.A(
                s["label"],
                href=f"#{s['id']}",
                className="simulation-section-nav-link",
            )
            for s in NAV_SECTIONS
        ],
        id="simulation-section-nav",
        className="simulation-section-nav sticky-nav",
    )


def build_back_to_top_button() -> html.Div:
    """Boton flotante 'Volver arriba' (Fase 6, seccion 18). Aparece solo
    tras cierto scroll — controlado por un clientside_callback en
    pages/simulador_operacional.py (no requiere libreria nueva)."""
    return html.Div(
        dbc.Button(
            "↑",
            id="btn-back-to-top",
            className="sim-back-to-top",
            title="Volver arriba",
        ),
        id="sim-back-to-top-wrapper",
        className="sim-back-to-top-wrapper d-none",
    )


def build_back_to_chart_link() -> html.A:
    """Enlace 'Volver al gráfico' (Fase 6, seccion 17) para usar dentro de
    secciones inferiores (ej. el panel de diagnostico), sin recargar ni
    reiniciar la simulacion."""
    return html.A(
        "↑ Volver al gráfico",
        href=f"#{SECTION_CHARTS}",
        className="sim-back-to-chart-link",
    )


def build_circuit_selector() -> dbc.RadioItems:
    """Selector [Ambos] [SAG1 · 401] [SAG2 · 501] (Fase 4, sec.10 del
    pedido 2026-07-14) — filtra SOLO visibilidad de trazas ya calculadas
    (ver components.graphs.apply_circuit_filter), nunca vuelve a simular."""
    return dbc.RadioItems(
        id="ctrl-circuito",
        options=[
            {"label": "Ambos", "value": "ambos"},
            {"label": "SAG1 · 401", "value": "sag1"},
            {"label": "SAG2 · 501", "value": "sag2"},
        ],
        value="ambos",
        inline=True,
        className="sim-circuit-selector",
        inputStyle={"marginRight": "4px"},
        labelStyle={"fontSize": "0.74rem", "marginRight": "10px"},
    )


def build_chart_category_selector() -> dbc.RadioItems:
    """Selector de categoría (Fase 5, sec.11) — filtra qué subconjunto de
    CHART_TABS se ofrece en sim-main-view. Cambiar de categoría es
    puramente visual (no dispara simulate_scenario_cached)."""
    return dbc.RadioItems(
        id="sim-chart-category",
        options=[{"label": c["label"], "value": c["id"]} for c in CHART_CATEGORIES],
        value=CHART_CATEGORY_DEFAULT,
        inline=True,
        className="sim-chart-category-selector",
        inputStyle={"marginRight": "4px"},
        labelStyle={"fontSize": "0.72rem", "marginRight": "10px", "textTransform": "uppercase",
                    "letterSpacing": "0.03em", "fontWeight": "700"},
    )
