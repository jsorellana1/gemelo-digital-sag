"""test_circuit_state_phase2.py — Segunda fase (2026-07-14): semántica
temporal por ventana, autonomía unificada, motivos de restricción,
recuperación exponencial, y su integración end-to-end en simulate_ode.
Ver 04_Reports/Technical/20260714_Segunda_Fase_Logica_Operacional.md.
"""
import math

import pytest

from engine.circuit_state import (
    OperationalWindow, analyze_window_episode, determine_restriction_reason,
    compare_autonomy_sources, evaluate_simulation_quality, calculate_effective_feed,
    SAG_OFF, BALL_MILLS_OFF, ONE_BALL_MILL_AVAILABLE, DOWNSTREAM_CAPACITY,
    STARVED_REASON, WINDOW_FEED_REDUCTION, NORMAL_OPERATION,
    FILLING, DRAINING, STABLE, AT_CRITICAL_LEVEL,
    DynamicAutonomyResult, classify_dynamic_autonomy,
    classify_historical_vulnerability, classify_autonomy_divergence,
)
from engine.ode_model import simulate_ode, CAP_TON, CRITICAL_PCT
from engine.simulator import simulate_scenario


class TestAnalisisEpisodioVentana:
    def test_distingue_drenado_durante_de_tendencia_final(self):
        """Construye una serie sintetica: drena durante la ventana [0,4h),
        luego recupera con creces -> trend_during_window debe ser DRAINING
        aunque la tendencia final sea FILLING (exactamente la
        inconsistencia 1.1 diagnosticada en la validacion de fase 1)."""
        dt = 5 / 60
        n = int(24 / dt) + 1
        time_h = [i * dt for i in range(n)]
        pile = []
        qin, qout = [], []
        p = 55.0
        for t in time_h:
            if t < 4.0:
                fin, fout = 200.0, 1200.0  # drena fuerte
            else:
                fin, fout = 1500.0, 1000.0  # recupera fuerte
            qin.append(fin); qout.append(fout)
            p = max(0.0, min(100.0, p + (fin - fout) * dt / CAP_TON["SAG1"] * 100.0))
            pile.append(p)

        ep = analyze_window_episode(time_h, pile, qin, qout, 0.0, 4.0,
                                     CAP_TON["SAG1"], CRITICAL_PCT["SAG1"])
        assert ep is not None
        assert ep.trend_during_window == DRAINING
        assert ep.trend_after_window == FILLING
        assert ep.inventory_minimum_pct < ep.inventory_at_window_start_pct
        assert ep.drained_tons_during_window > 0

    def test_minimo_y_tiempo_del_minimo(self):
        time_h = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        pile = [55.0, 40.0, 25.0, 20.0, 35.0, 50.0]
        qin = [0.0] * 6
        qout = [0.0] * 6
        ep = analyze_window_episode(time_h, pile, qin, qout, 0.0, 4.0,
                                     CAP_TON["SAG1"], CRITICAL_PCT["SAG1"])
        assert ep.inventory_minimum_pct == 20.0
        assert ep.time_of_minimum_h == 3.0

    def test_recovery_time_hasta_nivel_preventana(self):
        time_h = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        pile = [55.0, 40.0, 30.0, 30.0, 45.0, 55.0, 60.0]
        qin = [0.0] * 7
        qout = [0.0] * 7
        ep = analyze_window_episode(time_h, pile, qin, qout, 0.0, 3.0,
                                     CAP_TON["SAG1"], CRITICAL_PCT["SAG1"])
        # vuelve a 55% (nivel de inicio de ventana) en t=5.0h -> 2h despues del fin de ventana (t=3)
        assert ep.recovery_time_hours == pytest.approx(2.0)

    def test_reached_starved_true_si_toca_el_critico(self):
        time_h = [0.0, 1.0, 2.0]
        pile = [20.0, 14.0, 16.0]  # 14 < CRITICAL_PCT["SAG1"]=15.0
        ep = analyze_window_episode(time_h, pile, [0, 0, 0], [0, 0, 0], 0.0, 2.0,
                                     CAP_TON["SAG1"], CRITICAL_PCT["SAG1"])
        assert ep.reached_starved is True

    def test_ventana_fuera_del_horizonte_retorna_none(self):
        time_h = [0.0, 1.0, 2.0]
        ep = analyze_window_episode(time_h, [55, 55, 55], [0, 0, 0], [0, 0, 0],
                                     100.0, 108.0, CAP_TON["SAG1"], CRITICAL_PCT["SAG1"])
        assert ep is None


class TestMotivoRestriccion:
    def test_sag_off_es_el_motivo_principal_sin_secundarios(self):
        reason, sec = determine_restriction_reason(
            sag_effective_on=False, n_balls_effective=0, n_balls_requested=2,
            pile_pct=55.0, critical_pct=15.0, warning_pct=18.0, window_factor=1.0,
            is_ramping_up=False, is_ramping_down=False, rate_effective=0.0, rate_target=1236.0,
            overflow_ton=0.0, rejected_feed_tph=0.0,
        )
        assert reason == SAG_OFF
        assert sec == []

    def test_ball_mills_off_con_sag_on(self):
        reason, sec = determine_restriction_reason(
            sag_effective_on=True, n_balls_effective=0, n_balls_requested=2,
            pile_pct=55.0, critical_pct=15.0, warning_pct=18.0, window_factor=1.0,
            is_ramping_up=False, is_ramping_down=False, rate_effective=0.0, rate_target=1236.0,
            overflow_ton=0.0, rejected_feed_tph=0.0,
        )
        assert reason == BALL_MILLS_OFF

    def test_una_bola_disponible(self):
        reason, sec = determine_restriction_reason(
            sag_effective_on=True, n_balls_effective=1, n_balls_requested=2,
            pile_pct=55.0, critical_pct=15.0, warning_pct=18.0, window_factor=1.0,
            is_ramping_up=False, is_ramping_down=False, rate_effective=800.0, rate_target=1236.0,
            overflow_ton=0.0, rejected_feed_tph=0.0,
        )
        assert reason == ONE_BALL_MILL_AVAILABLE

    def test_starved_tiene_prioridad_sobre_ventana(self):
        reason, sec = determine_restriction_reason(
            sag_effective_on=True, n_balls_effective=2, n_balls_requested=2,
            pile_pct=10.0, critical_pct=15.0, warning_pct=18.0, window_factor=0.4,
            is_ramping_up=False, is_ramping_down=False, rate_effective=800.0, rate_target=1236.0,
            overflow_ton=0.0, rejected_feed_tph=0.0,
        )
        assert reason == STARVED_REASON
        assert WINDOW_FEED_REDUCTION in sec

    def test_normal_operation_sin_restricciones(self):
        reason, sec = determine_restriction_reason(
            sag_effective_on=True, n_balls_effective=2, n_balls_requested=2,
            pile_pct=55.0, critical_pct=15.0, warning_pct=18.0, window_factor=1.0,
            is_ramping_up=False, is_ramping_down=False, rate_effective=1236.0, rate_target=1236.0,
            overflow_ton=0.0, rejected_feed_tph=0.0,
        )
        assert reason == NORMAL_OPERATION
        assert sec == []


class TestAutonomiaUnificada:
    def test_diferencia_pequena_no_diverge(self):
        diff, diverge = compare_autonomy_sources(3.0, 2.5, threshold_h=1.0)
        assert diverge is False

    def test_diferencia_grande_diverge(self):
        diff, diverge = compare_autonomy_sources(5.0, 1.0, threshold_h=1.0)
        assert diverge is True
        assert diff == pytest.approx(4.0)

    def test_legacy_bajo_pero_neto_sin_riesgo_diverge(self):
        # legacy dice "poca autonomia" pero el balance neto dice "sin riesgo"
        diff, diverge = compare_autonomy_sources(0.5, None, threshold_h=1.0)
        assert diverge is True

    def test_legacy_alto_y_neto_sin_riesgo_no_diverge(self):
        diff, diverge = compare_autonomy_sources(10.0, None, threshold_h=1.0)
        assert diverge is False


class TestCalidadSimulacion:
    def test_consistente_sin_advertencias(self):
        ok, warns = evaluate_simulation_quality(0.0001, 1.0, [10, 50, 90], [100, 200, 300])
        assert ok is True
        assert warns == []

    def test_detecta_error_de_masa_fuera_de_tolerancia(self):
        ok, warns = evaluate_simulation_quality(500.0, 1.0, [10, 50, 90], [100, 200, 300])
        assert ok is False
        assert any("conservación de masa" in w for w in warns)

    def test_detecta_inventario_negativo(self):
        ok, warns = evaluate_simulation_quality(0.0, 1.0, [10, -5, 90], [100, 200, 300])
        assert ok is False
        assert any("negativo" in w for w in warns)

    def test_detecta_rate_negativo(self):
        ok, warns = evaluate_simulation_quality(0.0, 1.0, [10, 50, 90], [100, -1, 300])
        assert ok is False


class TestRecuperacionExponencial:
    def test_exponencial_tiende_a_normal_con_t_grande(self):
        f = calculate_effective_feed(1000.0, 0.3, elapsed_since_window_end_h=100.0,
                                      recovery_mode="exponential", feed_recovery_tau_min=30.0)
        assert f == pytest.approx(1000.0, abs=0.5)

    def test_exponencial_en_t_cero_igual_al_nivel_de_ventana(self):
        f = calculate_effective_feed(1000.0, 0.3, elapsed_since_window_end_h=0.0,
                                      recovery_mode="exponential", feed_recovery_tau_min=30.0)
        assert f == pytest.approx(300.0, abs=1.0)

    def test_exponencial_sin_tau_usa_recovery_time_min(self):
        f = calculate_effective_feed(1000.0, 0.3, elapsed_since_window_end_h=0.5,
                                      recovery_mode="exponential", feed_recovery_time_min=30.0)
        assert 300.0 < f < 1000.0


class TestIntegracionEndToEnd:
    """motor -> resultados -> indicadores, verificados juntos (no solo
    funciones aisladas) — seccion 16 del pedido."""

    def test_restriction_reason_consistente_con_operational_state(self):
        sim = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=False, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
        )
        assert sim["operational_state_sag1"] == "OFF"
        assert sim["restriction_reason_sag1"] == SAG_OFF

    def test_episodio_de_ventana_presente_solo_si_hay_t8(self):
        sim_sin_t8 = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
        )
        assert sim_sin_t8["window_episode_sag1"] is None

        sim_con_t8 = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=4.0,
            correa315_estado="inactiva", correa316_estado="inactiva", horizonte_horas=24.0,
        )
        assert sim_con_t8["window_episode_sag1"] is not None

    def test_simulation_consistent_flag_en_escenario_normal(self):
        sim = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=8.0,
            correa315_estado="reducida", correa316_estado="reducida", horizonte_horas=24.0,
        )
        assert sim["simulation_consistent_sag1"] is True
        assert sim["simulation_consistent_sag2"] is True

    def test_capacidad_bolas_activa_reduce_rate_maximo(self):
        sim_base = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
            bolas_sag1="solo_411", rate_sag1_tph=1400.0,
        )
        sim_tope = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
            bolas_sag1="solo_411", rate_sag1_tph=1400.0,
            enforce_downstream_ball_capacity=True, one_ball_capacity_factor_sag1=0.55,
        )
        assert max(sim_tope["tph_sag1"]) <= max(sim_base["tph_sag1"])

    def test_recuperacion_exponencial_end_to_end_no_rompe(self):
        sim = simulate_scenario(
            pila_sag1_pct=30.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=4.0,
            correa315_estado="inactiva", correa316_estado="activa", horizonte_horas=24.0,
            feed_recovery_mode="exponential", feed_recovery_tau_min=45.0,
        )
        assert len(sim["pile_sag1"]) > 0
        assert sim["mass_balance_error_sag1"] == pytest.approx(0.0, abs=10.0)

    def test_redistribucion_on_vs_off_conserva_masa_global(self):
        base = dict(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=False, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
            distribucion_t1="balanceado",
        )
        sim_off = simulate_scenario(**base, redistribution_enabled=False)
        sim_on = simulate_scenario(**base, redistribution_enabled=True)
        # ambos deben seguir conservando masa dentro de tolerancia, con o sin redistribucion
        assert abs(sim_off["mass_balance_error_sag2"]) < 10.0
        assert abs(sim_on["mass_balance_error_sag2"]) < 10.0


class TestReencuadreAutonomiaEtapa1:
    """Reencuadre semántico de autonomía — Etapa 1 (2026-07-14). Ver
    04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md,
    'Quinta pasada'. Casos 1-9 y 12-14 de la Fase 13 del pedido."""

    CAP1 = CAP_TON["SAG1"]
    MIN1 = CRITICAL_PCT["SAG1"] / 100.0 * CAP1

    def test_pila_llenando_con_vulnerabilidad_historica_critica(self):
        """Caso 1: pila baja (vulnerabilidad crítica) pero llenándose ahora
        -> dinámica FILLING (sin horas), no debe leerse como agotamiento."""
        result = classify_dynamic_autonomy(self.MIN1 + 500.0, self.MIN1,
                                            f_in_effective=1500.0, f_out_effective=800.0)
        assert result.status == FILLING
        assert result.hours is None
        vuln = classify_historical_vulnerability(0.3, "SAG1")
        assert vuln == "CRITICA"

    def test_pila_estable_con_vulnerabilidad_historica_baja(self):
        """Caso 2."""
        result = classify_dynamic_autonomy(self.MIN1 + 3000.0, self.MIN1,
                                            f_in_effective=1000.0, f_out_effective=1000.3)
        assert result.status == STABLE
        assert result.hours is None
        assert classify_historical_vulnerability(5.0, "SAG1") == "BAJA"

    def test_pila_drenando_lentamente(self):
        """Caso 3: drenaje neto pequeño pero por sobre la tolerancia ->
        DRAINING con horas grandes."""
        result = classify_dynamic_autonomy(self.MIN1 + 200.0, self.MIN1,
                                            f_in_effective=1000.0, f_out_effective=1005.0)
        assert result.status == DRAINING
        assert result.hours == pytest.approx(200.0 / 5.0, rel=1e-6)

    def test_pila_drenando_rapido(self):
        """Caso 4."""
        result = classify_dynamic_autonomy(self.MIN1 + 200.0, self.MIN1,
                                            f_in_effective=200.0, f_out_effective=1200.0)
        assert result.status == DRAINING
        assert result.hours == pytest.approx(200.0 / 1000.0, rel=1e-6)

    def test_sag_apagado(self):
        """Caso 5: consumo cero -> SAG_OFF, no restrictiva."""
        result = classify_dynamic_autonomy(self.MIN1 + 100.0, self.MIN1,
                                            f_in_effective=300.0, f_out_effective=0.0)
        assert result.status == SAG_OFF
        assert result.hours is None

    def test_pila_en_nivel_critico_drenando(self):
        """Caso 6: ya al mínimo operacional y drenando -> AT_CRITICAL_LEVEL,
        horas=0.0 (no None, no negativo)."""
        result = classify_dynamic_autonomy(self.MIN1 - 5.0, self.MIN1,
                                            f_in_effective=200.0, f_out_effective=1200.0)
        assert result.status == AT_CRITICAL_LEVEL
        assert result.hours == 0.0

    def test_diferencia_grande_con_balance_casi_nulo_es_esperada(self):
        """Caso 7: el escenario medido en la investigación previa
        (legacy=0.36h vs balance neto=143.05h) corresponde a un balance
        neto casi nulo (por debajo de la tolerancia de STABLE) — bajo el
        clasificador nuevo cae en STABLE, no en un DRAINING con horas
        gigantes, y la divergencia se clasifica como esperada, no como
        conflicto."""
        dyn = classify_dynamic_autonomy(self.MIN1 + 1000.0, self.MIN1,
                                         f_in_effective=1000.0, f_out_effective=1000.5)
        assert dyn.status == STABLE
        divergence = classify_autonomy_divergence(0.36, dyn)
        assert divergence == "EXPECTED_CONTEXT_DIFFERENCE"

    def test_badge_dinamico_nunca_expone_none_crudo(self):
        """Caso 8: para todo estado sin horas, `message` siempre trae texto
        explicativo — nunca se deja `None` sin explicación para la UI."""
        for f_in, f_out in [(1500.0, 800.0), (1000.0, 1000.3), (300.0, 0.0)]:
            result = classify_dynamic_autonomy(self.MIN1 + 500.0, self.MIN1, f_in, f_out)
            assert result.hours is None
            assert isinstance(result.message, str) and len(result.message) > 0

    def test_badge_preventivo_explica_supuesto_historico(self):
        """Caso 9: la vulnerabilidad histórica es una de 4 categorías
        explícitas, nunca un valor crudo sin interpretación."""
        for h in (0.1, 0.8, 1.2, 3.0):
            assert classify_historical_vulnerability(h, "SAG1") in (
                "CRITICA", "ALTA", "MEDIA", "BAJA")

    def test_claves_legacy_siguen_presentes(self):
        """Caso 12: simulate_ode sigue exponiendo las claves previas a esta
        Etapa 1 sin cambios."""
        sim = simulate_ode(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
        )
        for key in ("autonomia_sag1", "autonomia_sag2", "legacy_autonomia_sag1",
                    "legacy_autonomia_sag2", "autonomy_hours_sag1", "autonomy_hours_sag2",
                    "autonomy_diverges_sag1", "autonomy_diverges_sag2"):
            assert key in sim

    def test_claves_semanticas_nuevas_existen(self):
        """Caso 13."""
        sim = simulate_ode(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
        )
        for key in (
            "historical_preventive_autonomy_sag1_h", "historical_preventive_autonomy_sag2_h",
            "historical_vulnerability_sag1", "historical_vulnerability_sag2",
            "dynamic_net_autonomy_sag1_h", "dynamic_net_autonomy_sag2_h",
            "dynamic_net_autonomy_sag1_status", "dynamic_net_autonomy_sag2_status",
            "dynamic_net_autonomy_sag1_rate_tph", "dynamic_net_autonomy_sag2_rate_tph",
            "dynamic_net_autonomy_sag1_message", "dynamic_net_autonomy_sag2_message",
            "autonomy_divergence_class_sag1", "autonomy_divergence_class_sag2",
        ):
            assert key in sim
        assert sim["dynamic_net_autonomy_sag1_status"] in (
            "DRAINING", "STABLE", "FILLING", "SAG_OFF", "AT_CRITICAL_LEVEL")
        assert sim["historical_vulnerability_sag1"] in ("CRITICA", "ALTA", "MEDIA", "BAJA")
        # Aditivo puro: el valor legacy no cambia de fuente.
        assert sim["historical_preventive_autonomy_sag1_h"] == sim["legacy_autonomia_sag1"]

    def test_backtesting_mantiene_comportamiento_previo(self):
        """Caso 11 (mencionado junto a los de Fase 13): el renombrado de
        comentario en _tiempo_hasta_umbral no cambia el umbral usado."""
        from engine.historical_backtesting import _tiempo_hasta_umbral
        pila_vals = [50.0, 40.0, 30.0, 10.0]
        tiempos = [0.0, 1.0, 2.0, 3.0]
        t = _tiempo_hasta_umbral(pila_vals, tiempos, "SAG1", "baja")
        # Umbral equivalente: pila < CRITICAL_PCT["SAG1"] + DRAIN_PCT_H["SAG1"] = 15.0+23.76=38.76
        assert t == 2.0
