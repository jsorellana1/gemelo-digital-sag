"""tests/test_decision_hierarchy.py — Segunda iteración UX/UI del
Simulador Operacional (2026-07-14, ver 04_Reports/Technical/
20260714_Rediseno_Navegacion_UX_Simulador.md, sección "Segunda
iteración"). Cubre el subconjunto estructural declarado en el plan
aprobado: bloque de decisión principal, selector de circuito (visual,
no re-simula), agrupación de vistas por categoría, semáforo de 5
niveles, y navegación renombrada.
"""
import inspect

import pages.simulador_operacional as sim_page_module
from pages.simulador_operacional import page_simulador_operacional
from components.cards import (
    make_decision_banner, make_circuit_chip, make_confianza_card,
    OPERATIONAL_STATE_SEMAFORO, RESTRICTION_REASON_LABEL_JDS,
)
from components.graphs import apply_circuit_filter, make_master_pile_chart
from components.navigation import NAV_SECTIONS, CHART_TABS, CHART_CATEGORIES
from engine.simulator import simulate_scenario_cached
from engine import circuit_state as cs

from test_ux_navigation import _find_by_id, _collect_ids


class TestDecisionBanner:
    def test_banner_trae_los_7_campos_requeridos(self):
        banner = make_decision_banner(
            estado="Atención", circuito_afectado="SAG2", molino_afectado="Molino 501",
            horizonte_txt="1.7 h hasta nivel crítico", causa="inventario bajo",
            accion_txt="Reducir SAG2 150 TPH por 2 horas", severidad="Medio", confianza="MEDIA",
        )
        # make_decision_banner muestra el estado en mayusculas en el
        # titular grande (estado.upper()) — se verifica esa forma, no la
        # forma original pasada como argumento.
        rendered = str(banner.to_plotly_json())
        for campo_esperado in ("ATENCIÓN", "SAG2", "Molino 501", "1.7 h hasta nivel crítico",
                                "inventario bajo", "Reducir SAG2 150 TPH por 2 horas",
                                "Medio", "Media"):
            assert campo_esperado in rendered, f"Campo {campo_esperado!r} ausente del banner renderizado"

    def test_banner_tiene_botones_aplicar_y_ver_detalle(self):
        banner = make_decision_banner(
            estado="Sostenible", circuito_afectado="SAG1", molino_afectado="Molino 401",
            horizonte_txt="—", causa="operación normal", accion_txt="Mantener configuración",
            severidad="Bajo", confianza="ALTA",
        )
        ids_en_banner = set()
        _collect_ids(banner, ids_en_banner)
        assert "btn-aplicar-recomendacion" in ids_en_banner
        assert "btn-ver-detalle-decision" in ids_en_banner

    def test_banner_esta_en_section_summary_antes_del_resto(self):
        layout = page_simulador_operacional()
        from components.navigation import SECTION_SUMMARY
        summary_section = _find_by_id(layout, SECTION_SUMMARY)
        assert summary_section is not None
        ids_en_resumen = set()
        _collect_ids(summary_section, ids_en_resumen)
        assert "div-decision-banner" in ids_en_resumen

    def test_div_confianza_card_presente_en_layout(self):
        layout = page_simulador_operacional()
        assert _find_by_id(layout, "div-confianza-card") is not None


class TestChipDeCircuito:
    def test_chip_incluye_nombre_corto_y_molino(self):
        chip = make_circuit_chip("SAG1", "Molino 401")
        rendered = str(chip.to_plotly_json())
        assert "SAG1" in rendered
        assert "Molino 401" in rendered


class TestSemaforoOperacional:
    def test_semaforo_cubre_los_6_estados_reales_del_kernel(self):
        estados_kernel = {cs.OFF, cs.STARTING, cs.RUNNING, cs.RESTRICTED, cs.STARVED, cs.STOPPING}
        assert estados_kernel <= set(OPERATIONAL_STATE_SEMAFORO.keys()), (
            "OPERATIONAL_STATE_SEMAFORO no cubre todos los operational_state "
            "reales de engine/circuit_state.py"
        )

    def test_cada_entrada_del_semaforo_no_depende_solo_del_color(self):
        for estado, info in OPERATIONAL_STATE_SEMAFORO.items():
            assert info.get("nivel"), f"{estado} no tiene texto de nivel (dependeria solo del color)"
            assert info.get("icono"), f"{estado} no tiene icono (dependeria solo del color)"
            assert info.get("color")


class TestSelectorDeCircuitoVisualNoFisico:
    def test_ctrl_circuito_wireado_una_sola_vez(self):
        source = inspect.getsource(sim_page_module)
        ocurrencias = source.count('Input("ctrl-circuito"')
        assert ocurrencias == 1, (
            f'Input("ctrl-circuito", ...) aparece {ocurrencias} veces — deberia '
            "aparecer una sola vez, como Input visual de update_simulation, sin "
            "un segundo callback que dispare simulate_scenario_cached."
        )

    def test_apply_circuit_filter_solo_oculta_el_circuito_contrario(self):
        sim = simulate_scenario_cached(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            bolas_sag1="solo_411", bolas_sag2="solo_511", sag1_activo=True, sag2_activo=True,
            duracion_t8_h=0.0, correa315_estado="activa", correa316_estado="activa",
            horizonte_horas=24.0,
        )
        fig = make_master_pile_chart(sim, 24.0, 0.0)
        n_trazas_antes = len(fig.data)

        fig_sag1 = apply_circuit_filter(fig, "sag1")
        assert len(fig_sag1.data) == n_trazas_antes, "El filtro no debe eliminar trazas, solo ocultarlas"
        for trace in fig_sag1.data:
            if "SAG2" in (trace.name or "") and "SAG1" not in (trace.name or ""):
                assert trace.visible == "legendonly"
            else:
                assert trace.visible in (None, True)

    def test_apply_circuit_filter_ambos_no_modifica_visibilidad(self):
        sim = simulate_scenario_cached(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            bolas_sag1="solo_411", bolas_sag2="solo_511", sag1_activo=True, sag2_activo=True,
            duracion_t8_h=0.0, correa315_estado="activa", correa316_estado="activa",
            horizonte_horas=24.0,
        )
        fig = make_master_pile_chart(sim, 24.0, 0.0)
        fig_ambos = apply_circuit_filter(fig, "ambos")
        for trace in fig_ambos.data:
            assert trace.visible in (None, True)


class TestChartCategorias:
    def test_todas_las_vistas_de_chart_tabs_estan_categorizadas(self):
        valores_categorizados = {v for cat in CHART_CATEGORIES for v in cat["vistas"]}
        valores_chart_tabs = {t["value"] for t in CHART_TABS}
        huerfanas = valores_chart_tabs - valores_categorizados
        assert not huerfanas, f"Vistas de CHART_TABS sin categoria: {huerfanas}"

    def test_categorias_no_repiten_vistas(self):
        vistas_vistas = []
        for cat in CHART_CATEGORIES:
            vistas_vistas.extend(cat["vistas"])
        assert len(vistas_vistas) == len(set(vistas_vistas)), "Una vista aparece en mas de una categoria"


class TestNavegacionRenombrada:
    def test_nav_sections_incluye_decision_y_simulacion(self):
        labels = {s["label"] for s in NAV_SECTIONS}
        assert "Decisión" in labels
        assert "Simulación" in labels

    def test_nav_sections_resuelve_a_anclas_reales(self):
        layout = page_simulador_operacional()
        found = set()
        _collect_ids(layout, found)
        for section in NAV_SECTIONS:
            assert section["id"] in found


class TestRestrictionReasonLabels:
    def test_catalogo_cubre_todos_los_motivos_del_kernel(self):
        motivos_kernel = {
            cs.SAG_OFF, cs.BALL_MILLS_OFF, cs.ONE_BALL_MILL_AVAILABLE, cs.LOW_STOCKPILE,
            cs.STARVED_REASON, cs.WINDOW_FEED_REDUCTION, cs.RATE_RAMP_UP, cs.RATE_RAMP_DOWN,
            cs.DOWNSTREAM_CAPACITY, cs.PILE_FULL, cs.FEED_REJECTED, cs.NORMAL_OPERATION,
        }
        assert motivos_kernel <= set(RESTRICTION_REASON_LABEL_JDS.keys())
