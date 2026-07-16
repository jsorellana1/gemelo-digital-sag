"""tests/test_ux_navigation.py — Rediseno de navegacion/UX del Simulador
Operacional (2026-07-14, ver 04_Reports/Technical/
20260714_Rediseno_Navegacion_UX_Simulador.md).

Cubre el subconjunto estructural del pedido original (32 secciones, 20
pruebas) directamente relacionado con el cambio real hecho en esta
pasada: anclas de seccion, adyacencia del selector de vista con
graph-main (el bug raiz reportado), configuracion centralizada, paneles
colapsados por defecto, y ausencia de una re-simulacion fisica al
cambiar de pestana. No reemplaza confirmacion visual en navegador real
(ver seccion "Riesgos residuales" del reporte).
"""
import inspect
import os

from pages.simulador_operacional import page_simulador_operacional
import pages.simulador_operacional as sim_page_module
from components.navigation import (
    NAV_SECTIONS, CHART_TABS, SECTION_SUMMARY, SECTION_STOCKPILES,
    SECTION_CHARTS, SECTION_CONTROLS, SECTION_DIAGNOSTICS,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASSETS_CSS = os.path.join(os.path.dirname(_HERE), "assets", "styles.css")


def _collect_ids(component, found: set) -> None:
    comp_id = getattr(component, "id", None)
    if isinstance(comp_id, str):
        found.add(comp_id)
    children = getattr(component, "children", None)
    if children is None:
        return
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "children") or hasattr(child, "id"):
                _collect_ids(child, found)
    elif hasattr(children, "children") or hasattr(children, "id"):
        _collect_ids(children, found)


def _find_by_id(component, target_id):
    if getattr(component, "id", None) == target_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "children") or hasattr(child, "id"):
                found = _find_by_id(child, target_id)
                if found is not None:
                    return found
    elif hasattr(children, "children") or hasattr(children, "id"):
        return _find_by_id(children, target_id)
    return None


class TestAnclasDeSeccion:
    def test_las_5_secciones_existen_en_el_layout(self):
        layout = page_simulador_operacional()
        found = set()
        _collect_ids(layout, found)
        for section_id in (SECTION_SUMMARY, SECTION_STOCKPILES, SECTION_CHARTS,
                            SECTION_CONTROLS, SECTION_DIAGNOSTICS):
            assert section_id in found, f"Ancla de seccion {section_id!r} no esta en el layout"

    def test_nav_sections_apunta_a_anclas_reales(self):
        layout = page_simulador_operacional()
        found = set()
        _collect_ids(layout, found)
        assert len(NAV_SECTIONS) >= 4
        for section in NAV_SECTIONS:
            assert section["id"] in found, (
                f"NAV_SECTIONS declara la seccion {section['id']!r} pero no existe "
                "ningun componente con ese id en el layout — el enlace de la barra "
                "sticky quedaria roto (#ancla sin destino)."
            )

    def test_barra_de_navegacion_sticky_presente(self):
        layout = page_simulador_operacional()
        nav = _find_by_id(layout, "simulation-section-nav")
        assert nav is not None
        assert "sticky-nav" in nav.className


class TestSelectorAdyacenteAlGrafico:
    """El bug raiz reportado: el selector de vista vivia ~2 pantallas mas
    abajo que graph-main (confirmado en graficos y botones.pdf, paginas
    3 vs 5). Verifica que ahora esten en el mismo subarbol (section-charts)
    y ya NO en el accordion de diagnostico."""

    def test_selector_y_graph_main_estan_en_section_charts(self):
        layout = page_simulador_operacional()
        charts_section = _find_by_id(layout, SECTION_CHARTS)
        assert charts_section is not None
        ids_en_seccion = set()
        _collect_ids(charts_section, ids_en_seccion)
        for required in ("sim-main-view", "graph-main", "btn-expand-main", "btn-reset-zoom"):
            assert required in ids_en_seccion, (
                f"{required!r} deberia estar junto al grafico principal (section-charts)"
            )

    def test_selector_de_vista_ya_no_esta_en_el_panel_de_diagnostico(self):
        layout = page_simulador_operacional()
        diag_section = _find_by_id(layout, SECTION_DIAGNOSTICS)
        assert diag_section is not None
        ids_en_diagnostico = set()
        _collect_ids(diag_section, ids_en_diagnostico)
        assert "sim-main-view" not in ids_en_diagnostico, (
            "sim-main-view sigue duplicado/presente en el panel de diagnostico — "
            "reproduce el patron reportado de seleccionar abajo y volver arriba."
        )
        assert "btn-expand-main" not in ids_en_diagnostico
        assert "btn-reset-zoom" not in ids_en_diagnostico


class TestConfiguracionCentralizada:
    def test_chart_tabs_tiene_las_10_vistas_sin_duplicados(self):
        assert len(CHART_TABS) == 10
        valores = [t["value"] for t in CHART_TABS]
        assert len(valores) == len(set(valores)), "CHART_TABS tiene valores duplicados"

    def test_sim_main_view_usa_chart_tabs_centralizado(self):
        # El layout debe construir sus opciones desde CHART_TABS (no una
        # lista inline duplicada) — se verifica comparando el componente
        # real contra la constante.
        layout = page_simulador_operacional()
        selector = _find_by_id(layout, "sim-main-view")
        assert selector is not None
        assert selector.options == CHART_TABS


class TestPanelesColapsadosPorDefecto:
    def test_accordion_detalle_tecnico_colapsado(self):
        layout = page_simulador_operacional()
        diag_section = _find_by_id(layout, SECTION_DIAGNOSTICS)
        assert diag_section is not None
        # Buscar el Accordion directamente por su className distintivo.
        found = []

        def _walk(comp):
            if getattr(comp, "className", None) == "sim-detail-accordion":
                found.append(comp)
                return
            children = getattr(comp, "children", None)
            if isinstance(children, (list, tuple)):
                for c in children:
                    if hasattr(c, "children") or hasattr(c, "className"):
                        _walk(c)
            elif hasattr(children, "children") or hasattr(children, "className"):
                _walk(children)

        _walk(diag_section)
        assert found, "No se encontro el Accordion 'sim-detail-accordion'"
        acc = found[0]
        assert acc.start_collapsed is True
        assert acc.active_item is None


class TestNavegacionContextual:
    def test_boton_volver_arriba_presente(self):
        layout = page_simulador_operacional()
        btn = _find_by_id(layout, "btn-back-to-top")
        assert btn is not None

    def test_enlace_volver_al_grafico_apunta_a_section_charts(self):
        layout = page_simulador_operacional()
        found = []

        def _walk(comp):
            href = getattr(comp, "href", None)
            if href == f"#{SECTION_CHARTS}":
                found.append(comp)
            children = getattr(comp, "children", None)
            if isinstance(children, (list, tuple)):
                for c in children:
                    if hasattr(c, "children") or hasattr(c, "href"):
                        _walk(c)
            elif hasattr(children, "children") or hasattr(children, "href"):
                _walk(children)

        _walk(layout)
        assert found, "No se encontro un enlace 'Volver al gráfico' apuntando a #section-charts"


class TestSinRecimulacionFisicaAlCambiarPestana:
    """Cambiar sim-main-view debe seguir operando sobre el resultado ya
    calculado (Fase 11, secciones 31-32 del pedido) — se verifica que
    sim-main-view solo se wireo como Input UNA vez en el archivo (el
    callback grande update_simulation ya existente), no una segunda vez
    en un callback nuevo que dispare simulate_scenario_cached."""

    def test_sim_main_view_input_wireado_una_sola_vez(self):
        source = inspect.getsource(sim_page_module)
        ocurrencias = source.count('Input("sim-main-view"')
        assert ocurrencias == 1, (
            f"Input(\"sim-main-view\", ...) aparece {ocurrencias} veces — "
            "deberia aparecer una sola vez (el callback update_simulation ya "
            "existente). Una segunda aparicion sugeriria un callback nuevo que "
            "podria estar re-simulando solo por cambiar de pestana."
        )


class TestCSSResponsivo:
    def test_reglas_css_de_navegacion_existen(self):
        with open(_ASSETS_CSS, encoding="utf-8") as f:
            css = f.read()
        for regla in (".simulation-section-nav.sticky-nav", ".sim-chart-tabs",
                      ".sim-back-to-top", "scroll-behavior: smooth",
                      "scroll-margin-top"):
            assert regla in css, f"Regla CSS {regla!r} no encontrada en assets/styles.css"
