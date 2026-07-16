"""test_circuit_state.py — Los 30 casos obligatorios para el kernel de
dominio centralizado (engine/circuit_state.py), ver
04_Reports/Technical/20260714_Logica_Operacional_Pilas_SAG.md.

Cada test ejercita las funciones puras directamente (sin correr el ODE
completo) — rápidos y aislados por diseño.
"""
import pytest

from engine.circuit_state import (
    OperationalWindow, CircuitState,
    resolve_equipment_dependencies, resolve_window_feed_factor,
    calculate_effective_feed, apply_rate_ramp, calculate_effective_sag_rate,
    update_stockpile_mass_balance, calculate_stockpile_autonomy,
    determine_operational_state, determine_pile_trend, redistribute_feed,
    generate_operational_recommendation, validate_mass_conservation,
    OFF, STARTING, RUNNING, RESTRICTED, STARVED, STOPPING,
    FILLING, DRAINING, STABLE,
)

CAP_SAC1 = 4575.0
DT_H = 5.0 / 60.0


# 1-3. Balance positivo / negativo / cero ─────────────────────────────────────

class TestBalanceMasa:
    def test_1_balance_positivo_pila_crece(self):
        m_next, accepted, overflow, rejected, _qout_eff = update_stockpile_mass_balance(
            pile_inventory_ton=1000.0, f_in_requested=1200.0, f_out_requested=1000.0,
            cap_max_ton=CAP_SAC1, delta_t_h=DT_H,
        )
        assert m_next > 1000.0
        assert overflow == 0.0
        assert rejected == 0.0

    def test_2_balance_negativo_pila_drena(self):
        m_next, accepted, overflow, rejected, _qout_eff = update_stockpile_mass_balance(
            pile_inventory_ton=1000.0, f_in_requested=800.0, f_out_requested=1200.0,
            cap_max_ton=CAP_SAC1, delta_t_h=DT_H,
        )
        assert m_next < 1000.0

    def test_3_balance_cero_pila_estable(self):
        m_next, accepted, overflow, rejected, _qout_eff = update_stockpile_mass_balance(
            pile_inventory_ton=1000.0, f_in_requested=1000.0, f_out_requested=1000.0,
            cap_max_ton=CAP_SAC1, delta_t_h=DT_H,
        )
        assert m_next == pytest.approx(1000.0, abs=1e-6)


# 4-5. Ventana con alimentación cero / parcial ────────────────────────────────

class TestVentanaAlimentacion:
    def test_4_ventana_alimentacion_cero(self):
        f_eff = calculate_effective_feed(f_in_normal=1000.0, window_factor=0.0,
                                          elapsed_since_window_end_h=None)
        assert f_eff == 0.0

    def test_5_ventana_alimentacion_parcial(self):
        f_eff = calculate_effective_feed(f_in_normal=1000.0, window_factor=0.25,
                                          elapsed_since_window_end_h=None)
        assert f_eff == pytest.approx(250.0)


# 6-7. Salida de ventana: instantánea vs. con rampa ───────────────────────────

class TestRecuperacionPostVentana:
    def test_6_salida_instantanea_de_ventana(self):
        f_eff = calculate_effective_feed(f_in_normal=1000.0, window_factor=0.0,
                                          elapsed_since_window_end_h=0.0,
                                          feed_recovery_time_min=0.0)
        assert f_eff == pytest.approx(1000.0)

    def test_7_salida_con_rampa_de_recuperacion(self):
        # A mitad del tiempo de recuperacion, debe estar a mitad de camino
        # entre el nivel de ventana (0.3*1000=300) y el normal (1000).
        f_eff = calculate_effective_feed(f_in_normal=1000.0, window_factor=0.3,
                                          elapsed_since_window_end_h=0.5,
                                          feed_recovery_time_min=60.0, recovery_mode="linear")
        assert f_eff == pytest.approx(650.0)
        f_eff_full = calculate_effective_feed(f_in_normal=1000.0, window_factor=0.3,
                                               elapsed_since_window_end_h=1.0,
                                               feed_recovery_time_min=60.0, recovery_mode="linear")
        assert f_eff_full == pytest.approx(1000.0)


# 8-9. SAG OFF con bolas solicitadas ON ───────────────────────────────────────

class TestDependenciaSagBolas:
    def test_8_sag1_off_bolas_411_412_quedan_off(self):
        balls_eff, msg = resolve_equipment_dependencies(
            sag_effective_on=False, balls_requested={"411": True, "412": True})
        assert balls_eff == {"411": False, "412": False}
        assert "411" in msg and "412" in msg
        assert "OFF" in msg

    def test_9_sag2_off_bolas_511_512_quedan_off(self):
        balls_eff, msg = resolve_equipment_dependencies(
            sag_effective_on=False, balls_requested={"511": True, "512": False})
        assert balls_eff == {"511": False, "512": False}
        assert "511" in msg
        assert "512" not in msg  # 512 no estaba solicitado ON, no hay nada que informar de el

    def test_sag_on_respeta_seleccion_del_usuario(self):
        balls_eff, msg = resolve_equipment_dependencies(
            sag_effective_on=True, balls_requested={"411": True, "412": False})
        assert balls_eff == {"411": True, "412": False}
        assert msg == ""


# 10-11. Molinos de bolas activos ─────────────────────────────────────────────

class TestCapacidadAguasAbajo:
    def test_10_un_molino_de_bolas_activo_restringe_rate(self):
        rate = calculate_effective_sag_rate(
            rate_requested=1454.0, sag_effective_on=True, n_balls_effective=1,
            one_ball_capacity_factor=0.55, pile_inventory_ton=4000.0,
            f_in_effective=1500.0, delta_t_h=DT_H,
        )
        assert rate == pytest.approx(1454.0 * 0.55)

    def test_11_ningun_molino_de_bolas_rate_efectivo_cero(self):
        rate = calculate_effective_sag_rate(
            rate_requested=1454.0, sag_effective_on=True, n_balls_effective=0,
            one_ball_capacity_factor=0.55, pile_inventory_ton=4000.0,
            f_in_effective=1500.0, delta_t_h=DT_H,
        )
        assert rate == 0.0

    def test_dos_molinos_sin_restriccion_downstream(self):
        rate = calculate_effective_sag_rate(
            rate_requested=1454.0, sag_effective_on=True, n_balls_effective=2,
            one_ball_capacity_factor=0.55, pile_inventory_ton=4000.0,
            f_in_effective=1500.0, delta_t_h=DT_H,
        )
        assert rate == pytest.approx(1454.0)


# 12-13. Inventario insuficiente / cero ───────────────────────────────────────

class TestInventarioInsuficiente:
    def test_12_inventario_insuficiente_limita_rate(self):
        # Poco inventario, poca alimentacion -> available_rate bajo.
        rate = calculate_effective_sag_rate(
            rate_requested=1454.0, sag_effective_on=True, n_balls_effective=2,
            one_ball_capacity_factor=0.55, pile_inventory_ton=10.0,
            f_in_effective=0.0, delta_t_h=DT_H,
        )
        available = 10.0 / DT_H
        assert rate == pytest.approx(available)
        assert rate < 1454.0

    def test_13_inventario_cero_rate_limitado_a_feed(self):
        rate = calculate_effective_sag_rate(
            rate_requested=1454.0, sag_effective_on=True, n_balls_effective=2,
            one_ball_capacity_factor=0.55, pile_inventory_ton=0.0,
            f_in_effective=500.0, delta_t_h=DT_H,
        )
        assert rate == pytest.approx(500.0)


# 14-15. Capacidad máxima / alimentación rechazada ────────────────────────────

class TestCapacidadMaximaOverflow:
    def test_14_capacidad_maxima_no_se_supera(self):
        m_next, accepted, overflow, rejected, _qout_eff = update_stockpile_mass_balance(
            pile_inventory_ton=CAP_SAC1 - 10.0, f_in_requested=5000.0, f_out_requested=0.0,
            cap_max_ton=CAP_SAC1, delta_t_h=DT_H,
        )
        assert m_next <= CAP_SAC1 + 1e-6
        assert m_next == pytest.approx(CAP_SAC1, abs=1.0)

    def test_15_alimentacion_rechazada_se_contabiliza(self):
        m_next, accepted, overflow, rejected, _qout_eff = update_stockpile_mass_balance(
            pile_inventory_ton=CAP_SAC1 - 10.0, f_in_requested=5000.0, f_out_requested=0.0,
            cap_max_ton=CAP_SAC1, delta_t_h=DT_H,
        )
        assert rejected > 0.0
        assert accepted + rejected == pytest.approx(5000.0)


# 16. Redistribución entre pilas ──────────────────────────────────────────────

class TestRedistribucion:
    def test_16_redistribucion_sac1_detenido_hacia_sac2(self):
        out1, out2, rejected = redistribute_feed(
            f_in_sac1=500.0, f_in_sac2=1000.0,
            circuit1_available=False, circuit2_available=True,
            capacity_sac1_tph=2000.0, capacity_sac2_tph=3000.0, enabled=True,
        )
        assert out1 == 0.0
        assert out2 == pytest.approx(1500.0)
        assert rejected == 0.0

    def test_redistribucion_desactivada_no_cambia_nada(self):
        out1, out2, rejected = redistribute_feed(
            f_in_sac1=500.0, f_in_sac2=1000.0,
            circuit1_available=False, circuit2_available=True,
            capacity_sac1_tph=2000.0, capacity_sac2_tph=3000.0, enabled=False,
        )
        assert (out1, out2, rejected) == (500.0, 1000.0, 0.0)

    def test_redistribucion_respeta_capacidad_receptor(self):
        out1, out2, rejected = redistribute_feed(
            f_in_sac1=500.0, f_in_sac2=2900.0,
            circuit1_available=False, circuit2_available=True,
            capacity_sac1_tph=2000.0, capacity_sac2_tph=3000.0, enabled=True,
        )
        assert out2 <= 3000.0
        assert rejected == pytest.approx(400.0)


# 17-18. Ventanas superpuestas / que cruzan medianoche ────────────────────────

class TestVentanasMultiples:
    def test_17_ventanas_superpuestas_aplica_mas_severa(self):
        windows = [
            OperationalWindow(0.0, 8.0, feed_factor_sac1=0.5, feed_factor_sac2=1.0),
            OperationalWindow(2.0, 6.0, feed_factor_sac1=0.0, feed_factor_sac2=1.0),
        ]
        factor, razon = resolve_window_feed_factor(windows, t=4.0, asset_key="sac1")
        assert factor == 0.0

    def test_18_ventana_cruza_medianoche_horizonte_relativo(self):
        # Turno empieza a las 20:00, ventana de 8h -> [20,24) + [0,4) en
        # reloj real, pero en horas RELATIVAS al horizonte simulado
        # (0..N) es una sola ventana continua [start, start+8).
        windows = [OperationalWindow(20.0, 28.0, feed_factor_sac1=0.0, feed_factor_sac2=0.0)]
        f1, _ = resolve_window_feed_factor(windows, t=23.5, asset_key="sac1")
        f2, _ = resolve_window_feed_factor(windows, t=26.0, asset_key="sac1")  # "02:00" del dia siguiente
        f3, _ = resolve_window_feed_factor(windows, t=29.0, asset_key="sac1")  # ya termino
        assert f1 == 0.0 and f2 == 0.0
        assert f3 == 1.0

    def test_ventana_que_empieza_antes_del_horizonte(self):
        windows = [OperationalWindow(-2.0, 2.0, feed_factor_sac1=0.0, feed_factor_sac2=1.0)]
        factor, _ = resolve_window_feed_factor(windows, t=0.5, asset_key="sac1")
        assert factor == 0.0

    def test_ventana_que_termina_despues_del_horizonte(self):
        windows = [OperationalWindow(20.0, 100.0, feed_factor_sac1=0.0, feed_factor_sac2=1.0)]
        factor, _ = resolve_window_feed_factor(windows, t=23.9, asset_key="sac1")
        assert factor == 0.0


# 19-20. Ramp-up / ramp-down ───────────────────────────────────────────────────

class TestRampas:
    def test_19_ramp_up_limita_incremento(self):
        # Ceiling 1454, 30 min de rampa -> 1454/0.5h = 2908 TPH/h de subida.
        rate = apply_rate_ramp(rate_target=1454.0, previous_rate=0.0,
                                ramp_up_time_min=30.0, ramp_down_time_min=0.0,
                                delta_t_h=DT_H, rate_ceiling=1454.0)
        assert 0.0 < rate < 1454.0

    def test_19b_sin_rampa_salta_directo(self):
        rate = apply_rate_ramp(rate_target=1454.0, previous_rate=0.0,
                                ramp_up_time_min=0.0, ramp_down_time_min=0.0,
                                delta_t_h=DT_H, rate_ceiling=1454.0)
        assert rate == 1454.0

    def test_20_ramp_down_limita_decremento(self):
        rate = apply_rate_ramp(rate_target=0.0, previous_rate=1454.0,
                                ramp_up_time_min=0.0, ramp_down_time_min=30.0,
                                delta_t_h=DT_H, rate_ceiling=1454.0)
        assert 0.0 < rate < 1454.0


# 21-22. Autonomía con / sin drenado ──────────────────────────────────────────

class TestAutonomia:
    def test_21_autonomia_con_drenado(self):
        horas, msg = calculate_stockpile_autonomy(
            pile_inventory_ton=2000.0, m_min_operational_ton=500.0,
            f_in_effective=500.0, f_out_effective=1000.0,
        )
        assert horas == pytest.approx((2000.0 - 500.0) / 500.0)
        assert "Autonomía estimada" in msg

    def test_22_autonomia_sin_drenado(self):
        horas, msg = calculate_stockpile_autonomy(
            pile_inventory_ton=2000.0, m_min_operational_ton=500.0,
            f_in_effective=1200.0, f_out_effective=1000.0,
        )
        assert horas is None
        assert "Sin riesgo" in msg

    def test_autonomia_sag_apagado(self):
        horas, msg = calculate_stockpile_autonomy(
            pile_inventory_ton=2000.0, m_min_operational_ton=500.0,
            f_in_effective=0.0, f_out_effective=0.0,
        )
        assert horas is None
        assert "cero" in msg.lower()


# 23. Conservación de masa ────────────────────────────────────────────────────

class TestConservacionMasa:
    def test_23_conservacion_de_masa_error_cercano_a_cero(self):
        error = validate_mass_conservation(
            initial_inventory_ton=1000.0, cumulative_accepted_feed_ton=5000.0,
            cumulative_sag_consumption_ton=4500.0, final_inventory_ton=1500.0,
            cumulative_overflow_ton=0.0,
        )
        assert error == pytest.approx(0.0, abs=1e-6)

    def test_conservacion_de_masa_con_overflow_registrado(self):
        error = validate_mass_conservation(
            initial_inventory_ton=1000.0, cumulative_accepted_feed_ton=5000.0,
            cumulative_sag_consumption_ton=3000.0, final_inventory_ton=CAP_SAC1,
            cumulative_overflow_ton=1000.0 + 5000.0 - 3000.0 - CAP_SAC1,
        )
        assert error == pytest.approx(0.0, abs=1e-6)


# 24-25. Ausencia de inventarios/rates negativos ──────────────────────────────

class TestNoNegativos:
    def test_24_inventario_nunca_negativo(self):
        m_next, *_ = update_stockpile_mass_balance(
            pile_inventory_ton=5.0, f_in_requested=0.0, f_out_requested=5000.0,
            cap_max_ton=CAP_SAC1, delta_t_h=DT_H,
        )
        assert m_next >= 0.0

    def test_25_rate_nunca_negativo(self):
        rate = calculate_effective_sag_rate(
            rate_requested=-100.0, sag_effective_on=True, n_balls_effective=2,
            one_ball_capacity_factor=0.55, pile_inventory_ton=0.0,
            f_in_effective=0.0, delta_t_h=DT_H,
        )
        assert rate >= 0.0


# 26-28. Transiciones de estado ───────────────────────────────────────────────

class TestTransicionesEstado:
    def test_26_running_a_starved(self):
        estado = determine_operational_state(
            sag_requested_on=True, sag_effective_on=True,
            rate_effective=200.0, rate_target=1454.0,
            is_starved=True, is_restricted_by_balls=False,
        )
        assert estado == STARVED

    def test_27_off_a_starting_a_running(self):
        off = determine_operational_state(True, False, 0.0, 1454.0, False, False)
        assert off == OFF
        starting = determine_operational_state(True, True, 500.0, 1454.0, False, False, is_ramping_up=True)
        assert starting == STARTING
        running = determine_operational_state(True, True, 1454.0, 1454.0, False, False)
        assert running == RUNNING

    def test_28_running_a_stopping_a_off(self):
        stopping = determine_operational_state(False, True, 700.0, 0.0, False, False, is_ramping_down=True)
        assert stopping == STOPPING
        off_final = determine_operational_state(False, False, 0.0, 0.0, False, False)
        assert off_final == OFF

    def test_restricted_por_bolas(self):
        estado = determine_operational_state(
            sag_requested_on=True, sag_effective_on=True,
            rate_effective=800.0, rate_target=1454.0,
            is_starved=False, is_restricted_by_balls=True,
        )
        assert estado == RESTRICTED


class TestToleranciaRestricted:
    """Fase 1.5 del roadmap de cierre (2026-07-15, ver 04_Reports/Technical/
    20260715_Roadmap_Cierre_Simulador_Operacional.md): tolerancia
    explícita para RESTRICTED, sin cambiar el comportamiento por
    defecto."""

    def test_default_preserva_comparacion_exacta_previa(self):
        """Sin pasar tolerancia, una diferencia de 5 TPH (bajo el umbral
        anterior de 1e-6 solo por precisión) sigue clasificando RESTRICTED
        — comportamiento idéntico al que existía antes de esta fase."""
        estado = determine_operational_state(
            sag_requested_on=True, sag_effective_on=True,
            rate_effective=1449.0, rate_target=1454.0,
            is_starved=False, is_restricted_by_balls=False,
        )
        assert estado == RESTRICTED

    def test_tolerancia_tph_explicita_evita_restricted_por_diferencia_pequena(self):
        estado = determine_operational_state(
            sag_requested_on=True, sag_effective_on=True,
            rate_effective=1449.0, rate_target=1454.0,
            is_starved=False, is_restricted_by_balls=False,
            rate_restriction_tolerance_tph=10.0,
        )
        assert estado == RUNNING

    def test_tolerancia_pct_se_escala_con_rate_target(self):
        # 2% de 1454 = 29.1 TPH > diferencia de 20 TPH -> no restringido
        estado = determine_operational_state(
            sag_requested_on=True, sag_effective_on=True,
            rate_effective=1434.0, rate_target=1454.0,
            is_starved=False, is_restricted_by_balls=False,
            rate_restriction_tolerance_pct=0.02,
        )
        assert estado == RUNNING

    def test_diferencia_grande_sigue_restricted_con_cualquier_tolerancia_razonable(self):
        estado = determine_operational_state(
            sag_requested_on=True, sag_effective_on=True,
            rate_effective=800.0, rate_target=1454.0,
            is_starved=False, is_restricted_by_balls=False,
            rate_restriction_tolerance_tph=50.0, rate_restriction_tolerance_pct=0.05,
        )
        assert estado == RESTRICTED


# 29. Recomendaciones consistentes con el estado ──────────────────────────────

class TestRecomendaciones:
    def test_29_recomendacion_sag_off_coincide_con_estado(self):
        texto = generate_operational_recommendation(
            asset="SAG1", pile_trend=STABLE, window_active=False, window_just_ended=False,
            f_in_effective=500.0, f_out_effective=0.0, autonomy_hours=None,
            sag_effective_on=False,
        )
        assert "OFF" in texto and "SAG1" in texto

    def test_recomendacion_drenando_en_ventana(self):
        texto = generate_operational_recommendation(
            asset="SAG1", pile_trend=DRAINING, window_active=True, window_just_ended=False,
            f_in_effective=0.0, f_out_effective=1000.0, autonomy_hours=2.0,
            sag_effective_on=True,
        )
        assert "drenando" in texto.lower()

    def test_recomendacion_dependencia_tiene_prioridad(self):
        texto = generate_operational_recommendation(
            asset="SAG1", pile_trend=STABLE, window_active=False, window_just_ended=False,
            f_in_effective=500.0, f_out_effective=0.0, autonomy_hours=None,
            sag_effective_on=False, dependency_message="Molino 411 solicitado ON, pero queda inactivo...",
        )
        assert texto.startswith("Molino 411")


# 30. Coherencia temporal durante todo el horizonte ───────────────────────────

class TestCoherenciaTemporal:
    def test_30_secuencia_ventana_luego_recuperacion_es_coherente(self):
        """Simula 'a mano' 3 horas: 1h de ventana (factor 0), luego 2h de
        recuperacion lineal (30 min) — la pila debe drenar durante la
        ventana y crecer/estabilizarse despues, sin saltos artificiales."""
        pile = 2000.0  # ton
        cap = CAP_SAC1
        f_out = 1000.0
        f_normal = 1200.0
        trayectoria = []
        t = 0.0
        window_end = 1.0
        while t < 3.0:
            if t < window_end:
                f_in = calculate_effective_feed(f_normal, window_factor=0.0,
                                                  elapsed_since_window_end_h=None)
            else:
                f_in = calculate_effective_feed(f_normal, window_factor=0.0,
                                                  elapsed_since_window_end_h=t - window_end,
                                                  feed_recovery_time_min=30.0)
            pile, *_ = update_stockpile_mass_balance(pile, f_in, f_out, cap, DT_H)
            trayectoria.append(pile)
            t += DT_H

        # Durante la ventana (primeros 12 pasos de 5min = 1h) la pila solo baja.
        primeros_12 = trayectoria[:12]
        assert all(b <= a + 1e-9 for a, b in zip(primeros_12, primeros_12[1:]))
        # Despues de la recuperacion completa (t>=1.5h), f_in=1200 > f_out=1000
        # -> la pila debe terminar mayor que su minimo durante la ventana.
        assert trayectoria[-1] > min(trayectoria)
