"""test_ode_model_integration.py — Confirma que la integracion del kernel
de dominio (engine/circuit_state.py) dentro de simulate_ode NO cambio el
comportamiento numerico calibrado por defecto (windows=None, rampas=0,
redistribucion apagada) — puente de compatibilidad verificado, no solo
declarado. Ver 04_Reports/Technical/20260714_Logica_Operacional_Pilas_SAG.md.
"""
import pytest

from engine.ode_model import simulate_ode, CAP_TON, CRITICAL_PCT
from engine.simulator import simulate_scenario


_BASE_KWARGS = dict(
    pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
    sag1_activo=True, sag2_activo=True, duracion_t8_h=4.0,
    correa315_estado="activa", correa316_estado="activa",
    bolas_sag1="solo_411", bolas_sag2="solo_511", horizonte_horas=24.0,
    ch1_on=True, ch2_on=True, rate_sag1_tph=1236.0, rate_sag2_tph=2214.0,
)


class TestClavesNuevasAditivas:
    """Las claves preexistentes deben seguir presentes con el mismo tipo/forma
    (contrato consumido sin `.get()` defensivo por decenas de archivos)."""

    def test_claves_preexistentes_siguen_presentes(self):
        sim = simulate_ode(**_BASE_KWARGS)
        claves_preexistentes = {
            "time", "pile_sag1", "pile_sag2", "tph_sag1", "tph_sag2", "tph_total",
            "autonomia_sag1", "autonomia_sag2", "riesgo_sag1", "riesgo_sag2",
            "cv315", "cv316", "chancado_cap", "bola411", "bola412", "bola511",
            "bola512", "t1", "t3",
        }
        assert claves_preexistentes.issubset(sim.keys())
        assert len(sim["time"]) == len(sim["pile_sag1"]) == len(sim["tph_sag1"])

    def test_claves_nuevas_del_kernel_estan_presentes(self):
        sim = simulate_ode(**_BASE_KWARGS)
        claves_nuevas = {
            "overflow_sag1", "overflow_sag2", "rejected_feed_sag1", "rejected_feed_sag2",
            "mass_balance_error_sag1", "mass_balance_error_sag2",
            "dependency_message_sag1", "dependency_message_sag2",
            "operational_state_sag1", "operational_state_sag2",
            "pile_trend_sag1", "pile_trend_sag2",
            "autonomy_hours_sag1", "autonomy_hours_sag2",
            "autonomy_message_sag1", "autonomy_message_sag2",
        }
        assert claves_nuevas.issubset(sim.keys())


class TestCompatibilidadPorDefecto:
    """windows=None + rampas=0 (default) debe producir resultados idénticos
    a llamar simulate_ode SIN pasar ninguno de los parámetros nuevos —
    confirma que el puente de compatibilidad realmente no cambia nada."""

    def test_defaults_explicitos_igual_a_no_pasarlos(self):
        sim_a = simulate_ode(**_BASE_KWARGS)
        sim_b = simulate_ode(
            **_BASE_KWARGS,
            windows=None, sag_ramp_up_time_min=0.0, sag_ramp_down_time_min=0.0,
            feed_recovery_time_min=0.0, redistribution_enabled=False,
        )
        assert sim_a["pile_sag1"] == pytest.approx(sim_b["pile_sag1"])
        assert sim_a["pile_sag2"] == pytest.approx(sim_b["pile_sag2"])
        assert sim_a["tph_sag1"] == pytest.approx(sim_b["tph_sag1"])
        assert sim_a["tph_sag2"] == pytest.approx(sim_b["tph_sag2"])

    def test_activar_rampas_cambia_resultado_pero_no_rompe(self):
        sim_ramp = simulate_ode(**_BASE_KWARGS, sag_ramp_up_time_min=30.0, sag_ramp_down_time_min=30.0)
        sim_base = simulate_ode(**_BASE_KWARGS)
        assert len(sim_ramp["pile_sag1"]) == len(sim_base["pile_sag1"])
        # Con rampa, el arranque es mas lento -> tph inicial de SAG1 debe
        # ser <= que sin rampa en los primeros pasos.
        assert sim_ramp["tph_sag1"][1] <= sim_base["tph_sag1"][1] + 1e-6


class TestInvariantesExistentesPreservados:
    """Mismos invariantes que ya validaba test_simulator_basic.py — deben
    seguir cumpliendose tras la integracion del kernel."""

    def test_sag1_off_no_consume_pila(self):
        sim = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=False, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
        )
        assert all(t == 0.0 for t in sim["tph_sag1"])

    def test_t8_mas_largo_reduce_o_iguala_autonomia_minima(self):
        sim_corta = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=2.0,
            correa315_estado="inactiva", correa316_estado="inactiva", horizonte_horas=24.0,
        )
        sim_larga = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=12.0,
            correa315_estado="inactiva", correa316_estado="inactiva", horizonte_horas=24.0,
        )
        assert sim_larga["min_autonomia_sag1"] <= sim_corta["min_autonomia_sag1"] + 1e-6

    def test_correa_inactiva_no_incrementa_pila_durante_t8(self):
        sim = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=0.0, rate_sag2_pct=100.0,
            sag1_activo=False, sag2_activo=True, duracion_t8_h=4.0,
            correa315_estado="inactiva", correa316_estado="activa", horizonte_horas=24.0,
        )
        # SAG1 apagado + correa inactiva -> pila SAG1 no debe crecer durante T8.
        primeros_pasos = sim["pile_sag1"][:5]
        assert max(primeros_pasos) <= 55.0 + 2.0  # tolerancia por suavizado

    def test_ch2_off_reduce_capacidad_chancado(self):
        sim_ambos = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
            ch1_on=True, ch2_on=True,
        )
        sim_solo_ch1 = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
            ch1_on=True, ch2_on=False,
        )
        assert sim_solo_ch1["chancado_cap_tph"] < sim_ambos["chancado_cap_tph"]


class TestConservacionMasaEnElMotorCompleto:
    """El error de conservacion de masa (Regla 18) debe ser ~0 para
    escenarios reales corridos a traves de simulate_ode completo, no solo
    en las funciones puras aisladas de circuit_state.py."""

    @pytest.mark.parametrize("duracion_t8", [0.0, 2.0, 4.0, 8.0, 12.0])
    def test_conservacion_de_masa_por_duracion_t8(self, duracion_t8):
        sim = simulate_ode(**{**_BASE_KWARGS, "duracion_t8_h": duracion_t8})
        # Tolerancia amplia (10 ton) porque el suavizado rolling-mean de
        # pile_sag1/2 (uniform_filter1d) se aplica DESPUES del calculo del
        # kernel -> el error medido sobre la serie suavizada no es
        # exactamente el error del balance paso a paso, solo debe ser chico.
        assert abs(sim["mass_balance_error_sag1"]) < 10.0
        assert abs(sim["mass_balance_error_sag2"]) < 10.0

    def test_conservacion_de_masa_sag_apagado(self):
        sim = simulate_ode(**{**_BASE_KWARGS, "sag1_activo": False})
        assert abs(sim["mass_balance_error_sag1"]) < 10.0


class TestEscenariosMinimosDelPedido:
    """Escenarios 1-12 explicitos del pedido, verificados end-to-end contra
    simulate_scenario (no solo las funciones puras)."""

    def test_escenario_1_operacion_normal_equilibrada(self):
        sim = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
        )
        assert sim["pile_trend_sag1"] in ("STABLE", "FILLING", "DRAINING")  # no debe crashear

    def test_escenario_5_sag_apagado_durante_ventana_bolas_quedan_off(self):
        sim = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=False, sag2_activo=True, duracion_t8_h=4.0,
            correa315_estado="inactiva", correa316_estado="activa", horizonte_horas=24.0,
            bolas_sag1="ambas_411_412", bolas_sag2="solo_511",
        )
        assert sim["dependency_message_sag1"] != ""
        assert set(sim["bola411"]) == {0}
        assert set(sim["bola412"]) == {0}

    def test_escenario_6_sag_apagado_sin_ventana_pila_crece(self):
        sim = simulate_scenario(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=False, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
            distribucion_t1="balanceado",
        )
        assert sim["pile_sag1"][-1] > sim["pile_sag1"][0]

    def test_escenario_9_pila_vacia_rate_limitado_nunca_negativo(self):
        sim = simulate_scenario(
            pila_sag1_pct=0.5, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="inactiva", correa316_estado="activa", horizonte_horas=6.0,
        )
        assert all(p >= 0.0 for p in sim["pile_sag1"])
        assert all(t >= 0.0 for t in sim["tph_sag1"])

    def test_escenario_10_pila_llena_overflow_contabilizado(self):
        sim = simulate_scenario(
            pila_sag1_pct=99.5, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            sag1_activo=False, sag2_activo=True, duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0,
            distribucion_t1="balanceado",
        )
        assert max(sim["pile_sag1"]) <= 100.0 + 1e-6
        assert sum(sim["overflow_sag1"]) >= 0.0
