"""test_router_v2.py — QA 2026-07-07: router v2 que decide ANTES de
simular (ScenarioInputs, CriticalityScorer, BaseSimulationStrategy,
MixedRegimeStrategy, StrategyExecutor, physics_validation,
historical_backtesting). Complementa test_simulation_router.py (v1,
clasificador post-hoc), que sigue vigente sin cambios.

Los tests de sintesis (`Test*Sintetico`) usan escenarios controlados —
no dependen de datos historicos. Los tests de backtesting
(`TestBacktestingHistorico`) SI leen los parquet reales de
01_Data/Cache/ y documentan explicitamente el resultado del Prerequisito
0. Actualizado 2026-07-07 (prompt "CIERRE DE BRECHAS POST ROUTER v2"):
t8_corta y los 4 regimenes sin dataset oficial (via deteccion
retrospectiva, regime_event_detector.py) SI tienen backtesting
disponible; t8_larga sigue insuficiente (N=8 < 20) — ver
GAPS_BACKTESTING.md. Ver tests/test_backtesting_*.py para el backtesting
especifico de cada uno de los 4 regimenes proxy.
"""
from datetime import datetime

import pytest

from engine.scenario_inputs import ScenarioInputs, project_pila_lineal, build_scenario_inputs
from engine.criticality_scorer import CriticalityScorer
from engine.physics_validation import validate_physics, TOLERANCIAS
from engine.simulation_strategies import STRATEGIES, MixedRegimeStrategy
from engine.strategy_executor import StrategyExecutor
from engine.historical_backtesting import check_prerequisito_0, run_backtest, N_MINIMO_EVENTOS
from engine.simulation_router import route_and_simulate


def _s(pila_actual=55.0, pila_proyectada=55.0, **kw):
    base = dict(
        pila_actual_pct=pila_actual, pila_proyectada_pct=pila_proyectada,
        qin_actual=1400.0, qout_actual=1400.0,
        t1_disponible=True, cv315_disponible=True, cv316_disponible=True,
        equipos_en_mantencion=[], sag1_disponible=True, sag2_disponible=True,
        mobo1_disponible=True, mobo2_disponible=True,
        t8_activa=False, t8_duracion_h=0.0, timestamp=datetime.now(),
    )
    base.update(kw)
    return ScenarioInputs(**base)


class TestScenarioInputsSintetico:
    def test_rechaza_pila_fuera_de_rango(self):
        with pytest.raises(ValueError):
            _s(pila_actual=200.0)

    def test_proyeccion_lineal_consistente_con_drenaje(self):
        # Consumo neto de 400 TPH durante 2h en SAG1 (CAP_TON=4575) reduce la pila
        p = project_pila_lineal(60.0, qin_actual=1000.0, qout_actual=1400.0, asset="SAG1", horas=2.0)
        assert p < 60.0

    def test_build_scenario_inputs_retorna_par(self):
        s1, s2 = build_scenario_inputs(
            pila1_pct=55, pila2_pct=55, qin1_actual=1400, qin2_actual=2400,
            qout1_actual=1400, qout2_actual=2400,
            t1_disponible=True, cv315_disponible=True, cv316_disponible=True,
            equipos_en_mantencion=[], sag1_disponible=True, sag2_disponible=True,
            mobo1_disponible=True, mobo2_disponible=True,
            t8_activa=False, t8_duracion_h=0,
        )
        assert isinstance(s1, ScenarioInputs) and isinstance(s2, ScenarioInputs)


class TestCriticalityScorerSintetico:
    def test_escenario_normal_score_bajo(self):
        s1, s2 = _s(), _s(pila_actual=60, pila_proyectada=60)
        crits = CriticalityScorer().score(s1, s2)
        assert crits[0].regimen == "normal"

    def test_inventario_critico_domina_sobre_normal(self):
        s1 = _s(pila_actual=8.0, pila_proyectada=5.0)  # bajo CRITICAL_PCT SAG1=15
        s2 = _s(pila_actual=60, pila_proyectada=60)
        crits = CriticalityScorer().score(s1, s2)
        assert crits[0].regimen.startswith("inventario_critico")
        assert crits[0].urgency_score > 50.0

    def test_t8_larga_score_mayor_que_t8_corta(self):
        s_corta = _s(t8_activa=True, t8_duracion_h=2.0)
        s_larga = _s(t8_activa=True, t8_duracion_h=16.0)
        scorer = CriticalityScorer()
        c_corta = scorer._score_t8(s_corta)
        c_larga = scorer._score_t8(s_larga)
        assert c_larga.urgency_score > c_corta.urgency_score

    def test_mantencion_con_equipo_critico_score_alto(self):
        c = CriticalityScorer()._score_mantencion(["411", "SAG2"])
        assert c.urgency_score >= 70.0

    def test_sin_restricciones_retorna_normal_con_score_positivo(self):
        s1, s2 = _s(), _s()
        crits = CriticalityScorer().score(s1, s2)
        assert len(crits) == 1
        assert crits[0].regimen == "normal"
        assert crits[0].urgency_score > 0


class TestPhysicsValidationSintetico:
    def test_sim_valido_pasa_validacion(self):
        sim = {
            "pile_sag1": [55.0, 56.0], "pile_sag2": [55.0, 54.0],
            "tph_sag1": [1400.0, 1400.0], "tph_sag2": [2400.0, 2400.0],
            "sag1_activo": True, "sag2_activo": True,
        }
        report = validate_physics(sim)
        assert report.es_valido
        assert report.violaciones == []

    def test_pila_sobre_maximo_marca_violacion(self):
        sim = {"pile_sag1": [55.0, 110.0], "pile_sag2": [55.0], "tph_sag1": [1400.0], "tph_sag2": [2400.0]}
        report = validate_physics(sim)
        assert not report.es_valido
        assert any("excede el maximo" in v for v in report.violaciones)

    def test_tph_negativo_marca_violacion(self):
        sim = {"pile_sag1": [55.0], "pile_sag2": [55.0], "tph_sag1": [-10.0], "tph_sag2": [2400.0]}
        report = validate_physics(sim)
        assert not report.es_valido

    def test_sag_activo_sin_disponibilidad_marca_violacion(self):
        sim = {"pile_sag1": [55.0], "pile_sag2": [55.0], "tph_sag1": [1400.0], "tph_sag2": [2400.0],
               "sag1_activo": True}
        report = validate_physics(sim, sag1_disponible=False)
        assert not report.es_valido

    def test_ambos_mobo_indisponibles_es_advertencia_no_violacion(self):
        sim = {"pile_sag1": [55.0], "pile_sag2": [55.0], "tph_sag1": [1400.0], "tph_sag2": [2400.0]}
        report = validate_physics(sim, mobo1_disponible=False, mobo2_disponible=False)
        assert report.es_valido  # es advertencia, no viola nada duro
        assert len(report.advertencias) == 1

    def test_tolerancias_definidas_y_no_vacias(self):
        assert TOLERANCIAS["balance_masa_pct"] > 0
        assert TOLERANCIAS["pila_max_pct"] > 100.0

    def test_t3_negativo_marca_violacion(self):
        sim = {"pile_sag1": [55.0], "pile_sag2": [55.0], "tph_sag1": [1400.0], "tph_sag2": [2400.0],
               "t3": [10.0, -5.0]}
        report = validate_physics(sim)
        assert not report.es_valido
        assert any("T3" in v and "negativo" in v for v in report.violaciones)

    def test_cv315_cv316_excede_t1_marca_violacion(self):
        sim = {"pile_sag1": [55.0], "pile_sag2": [55.0], "tph_sag1": [1400.0], "tph_sag2": [2400.0],
               "cv315": [1000.0], "cv316": [1000.0], "t1": [1500.0]}
        report = validate_physics(sim)
        assert not report.es_valido
        assert any("T1" in v and "excede" in v for v in report.violaciones)

    def test_equipo_en_mantencion_activo_marca_violacion(self):
        sim = {"pile_sag1": [55.0], "pile_sag2": [55.0], "tph_sag1": [1400.0], "tph_sag2": [2400.0]}
        report = validate_physics(
            sim, equipos_en_mantencion=["ch1"],
            equipos_activos={"sag1": True, "sag2": True, "ch1": True, "ch2": False},
        )
        assert not report.es_valido
        assert any("ch1" in v and "mantencion" in v for v in report.violaciones)

    def test_equipo_en_mantencion_inactivo_no_marca_violacion(self):
        sim = {"pile_sag1": [55.0], "pile_sag2": [55.0], "tph_sag1": [1400.0], "tph_sag2": [2400.0]}
        report = validate_physics(
            sim, equipos_en_mantencion=["ch1"],
            equipos_activos={"sag1": True, "sag2": True, "ch1": False, "ch2": True},
        )
        assert report.es_valido


class TestStrategyExecutorSintetico:
    def test_normal_strategy_produce_resultado_factible(self):
        params = {"pila1": 60, "pila2": 60, "duracion_t8": 0, "sag1_on": True, "sag2_on": True,
                   "ch1_on": True, "ch2_on": True, "c315": "activa", "c316": "activa",
                   "t1_mode": "chancado", "t1_manual": 4000.0, "t3_frac": 0.0,
                   "distribucion_t1": "proporcional", "horizonte": 24.0,
                   "mobo1_disponible": True, "mobo2_disponible": True, "equipos_en_mantencion": []}
        executor = StrategyExecutor()
        result, validation = executor.run(STRATEGIES["normal"], params)
        assert result.es_factible
        assert result.best is not None

    def test_on_failure_nunca_lanza_y_marca_no_factible(self):
        strategy = STRATEGIES["normal"]

        def _boom(params):
            raise RuntimeError("fallo simulado deliberado")
        strategy.simulate = _boom  # monkeypatch puntual
        executor = StrategyExecutor()
        result, validation = executor.run(strategy, {})
        assert result.es_factible is False
        assert not validation.es_valido
        # restaurar
        del strategy.simulate


class TestMixedRegimeStrategySintetico:
    def test_conflicto_de_direccion_detectado_y_documentado(self):
        from engine.criticality_scorer import RegimeCriticality
        crits = [
            RegimeCriticality("overflow_SAG1", 80.0, ["test"]),
            RegimeCriticality("inventario_critico_SAG2", 60.0, ["test"]),
        ]
        mixed = MixedRegimeStrategy(crits)
        params = {"pila1": 90, "pila2": 12, "duracion_t8": 0, "sag1_on": True, "sag2_on": True,
                   "ch1_on": True, "ch2_on": True, "c315": "activa", "c316": "activa",
                   "t1_mode": "chancado", "t1_manual": 4000.0, "t3_frac": 0.0,
                   "distribucion_t1": "proporcional", "horizonte": 24.0,
                   "tolerancia_riesgo": "balanceado",
                   "mobo1_disponible": True, "mobo2_disponible": True, "equipos_en_mantencion": []}
        result = mixed.simulate(params)
        assert result.meta["conflicto"] is not None
        assert "Conflicto de direccion" in result.meta["conflicto"]


class TestBacktestingHistorico:
    """Verifica el gate de Prerequisito 0 contra los datos REALES del
    proyecto (no mockeados) — documenta que solo t8_corta tiene N
    suficiente; el resto reporta el gap explicitamente."""

    def test_t8_corta_tiene_datos_suficientes(self):
        pre = check_prerequisito_0()
        assert pre["t8_corta"].disponible is True
        assert pre["t8_corta"].n_eventos >= N_MINIMO_EVENTOS["t8_corta"]

    def test_t8_larga_insuficiente_documentado(self):
        pre = check_prerequisito_0()
        assert pre["t8_larga"].disponible is False
        assert pre["t8_larga"].n_eventos < N_MINIMO_EVENTOS["t8_larga"]
        assert "insuficiente" in pre["t8_larga"].razon

    @pytest.mark.parametrize("regimen", ["overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida"])
    def test_regimenes_cubiertos_por_deteccion_retrospectiva(self, regimen):
        """Actualizado 2026-07-07 (prompt 'CIERRE DE BRECHAS POST ROUTER
        v2', TAREA 2): estos 4 regimenes NO tienen un dataset de eventos
        OFICIAL, pero el detector retrospectivo (regime_event_detector.py)
        SI encuentra N suficiente sobre la serie continua de 5 min — no
        se fabrico nada, se documenta la fuente como proxy."""
        pre = check_prerequisito_0()
        assert pre[regimen].disponible is True
        assert pre[regimen].n_eventos > 0
        assert "proxy" in pre[regimen].razon.lower() or "retrospectiva" in pre[regimen].razon.lower()

    def test_backtest_t8_corta_ejecuta_sin_excepcion(self):
        result = run_backtest("t8_corta")
        assert result.historica_disponible is True
        assert result.n_eventos > 0
        assert result.pila_mae_sag1_pp is not None

    def test_backtest_overflow_ejecuta_con_deteccion_retrospectiva(self):
        result = run_backtest("overflow")
        assert result.historica_disponible is True
        assert result.n_eventos > 0
        assert result.pila_mae_sag1_pp is not None


class TestRouteAndSimulateIntegracionReal:
    """Con el motor real (route_and_simulate end-to-end, sin mockear)."""

    def test_escenario_normal(self):
        r = route_and_simulate(
            pila1=60, pila2=60, duracion_t8=0,
            qin1_actual=1400, qin2_actual=2400, qout1_actual=1400, qout2_actual=2400,
            ch1_on=True, ch2_on=True, correa315_estado="activa", correa316_estado="activa",
            maint_windows=None, now_hour=8, horizonte=24,
        )
        assert r["regimen_elegido"] == "normal"
        assert r["result"].es_factible
        assert r["validation"].es_valido
        assert isinstance(r["explicacion"], str) and len(r["explicacion"]) > 0

    def test_escenario_inventario_critico(self):
        r = route_and_simulate(
            pila1=8, pila2=60, duracion_t8=0,
            qin1_actual=900, qin2_actual=2400, qout1_actual=1400, qout2_actual=2400,
            ch1_on=True, ch2_on=True, correa315_estado="activa", correa316_estado="activa",
            maint_windows=None, now_hour=8, horizonte=24,
        )
        assert r["regimen_elegido"] == "inventario_critico"
        assert r["backtest_info"]["regimen"] == "inventario_critico"
        # Actualizado 2026-07-07: deteccion retrospectiva SI cubre este regimen.
        assert r["backtest_info"]["historica_disponible"] is True

    def test_escenario_t8_larga_backtest_marca_insuficiente(self):
        r = route_and_simulate(
            pila1=55, pila2=55, duracion_t8=10,
            qin1_actual=1400, qin2_actual=2400, qout1_actual=1400, qout2_actual=2400,
            ch1_on=True, ch2_on=True, correa315_estado="activa", correa316_estado="activa",
            maint_windows=None, now_hour=8, horizonte=24,
        )
        assert r["regimen_elegido"] == "t8_larga"
        assert r["backtest_info"]["historica_disponible"] is False
        assert "insuficiente" in r["backtest_info"]["razon"]

    def test_escenario_mixto_documenta_conflicto_o_combinacion(self):
        r = route_and_simulate(
            pila1=9, pila2=60, duracion_t8=10,
            qin1_actual=900, qin2_actual=2400, qout1_actual=1400, qout2_actual=2400,
            ch1_on=True, ch2_on=True, correa315_estado="activa", correa316_estado="activa",
            maint_windows=None, now_hour=8, horizonte=24,
        )
        assert r["regimen_elegido"] == "mixto"
        assert r["result"].meta.get("primary") is not None

    def test_route_and_simulate_acepta_overrides_multicelda(self):
        r = route_and_simulate(
            pila1=60, pila2=55, duracion_t8=0,
            qin1_actual=1400, qin2_actual=2400, qout1_actual=1400, qout2_actual=2400,
            ch1_on=True, ch2_on=True, correa315_estado="activa", correa316_estado="activa",
            maint_windows=None, now_hour=8, horizonte=4,
            multicell_enabled=True,
            initial_channel_levels_sag1=[100.0, 80.0, 0.0],
            initial_channel_levels_sag2=[100.0, 90.0, 70.0, 50.0, 10.0],
            multicell_lateral_transfer_coeff_sag2=0.4,
            multicell_spatial_capacity_mode_sag2="min_range_linear",
        )
        sim = r["result"].sim
        assert sim["multicell_enabled"] is True
        assert sim["pile_sag1_channels_pct"] is not None
        assert sim["pile_sag2_channels_pct"] is not None
        assert sim["multicell_channel_labels_sag1"] == ["D", "B", "A"]
        assert sim["multicell_channel_labels_sag2"] == ["1", "2", "4", "5", "6"]
        assert sim["multicell_lateral_transfer_coeff_sag2"] == pytest.approx(0.4)
        assert sim["multicell_spatial_capacity_mode_sag2"] == "min_range_linear"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
