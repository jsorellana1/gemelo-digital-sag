"""test_post_t8_balance_logic.py — cierre "Sincronizacion recomendacion/
escenario" (2026-07-09), Fase 14. Casos A/B/C con `sim` sinteticos
(series de cv315/cv316/tph_sag1/tph_sag2/time construidas a mano) —
mismo patron que los tests sinteticos de physics_validation en
test_router_v2.py."""
import pytest

from engine.balance_diagnostics import compute_post_t8_balance, explain_post_t8, UMBRAL_BALANCE_TPH


def _sim_con_balance(qin1: float, qout1: float, qin2: float, qout2: float, duracion_t8: float = 4.0) -> dict:
    """sim sintetico de 2 puntos: uno DURANTE T8 (irrelevante para el
    diagnostico) y uno justo al terminar T8 (el que se audita)."""
    return {
        "time": [0.0, duracion_t8],
        "cv315": [0.0, qin1],
        "cv316": [0.0, qin2],
        "tph_sag1": [qout1 * 0.5, qout1],
        "tph_sag2": [qout2 * 0.5, qout2],
    }


class TestPostT8BalanceLogic:
    def test_caso_a_recuperacion_qin_mayor_qout(self):
        sim = _sim_con_balance(qin1=1500, qout1=1200, qin2=2600, qout2=2400)
        balance = compute_post_t8_balance(sim, duracion_t8_h=4.0)
        assert balance["SAG1"].estado == "recupera"
        assert balance["SAG2"].estado == "recupera"
        assert balance["SAG1"].balance_tph == pytest.approx(300.0)

    def test_caso_b_plano_qin_casi_igual_qout(self):
        sim = _sim_con_balance(qin1=1300, qout1=1309, qin2=2600, qout2=2610)
        balance = compute_post_t8_balance(sim, duracion_t8_h=4.0)
        assert balance["SAG1"].estado == "plana"
        assert balance["SAG2"].estado == "plana"
        assert abs(balance["SAG1"].balance_tph) <= UMBRAL_BALANCE_TPH

    def test_caso_c_drenaje_qin_menor_qout(self):
        sim = _sim_con_balance(qin1=1000, qout1=1400, qin2=2000, qout2=2600)
        balance = compute_post_t8_balance(sim, duracion_t8_h=4.0)
        assert balance["SAG1"].estado == "drena"
        assert balance["SAG2"].estado == "drena"
        assert balance["SAG1"].balance_tph < 0

    def test_sin_t8_no_hay_diagnostico(self):
        sim = _sim_con_balance(qin1=1500, qout1=1200, qin2=2600, qout2=2400)
        assert compute_post_t8_balance(sim, duracion_t8_h=0.0) is None

    def test_horizonte_insuficiente_retorna_none(self):
        """Si el horizonte simulado no llega hasta duracion_t8_h, no se
        fabrica un balance con datos que no existen."""
        sim = {"time": [0.0, 1.0], "cv315": [0.0, 1500.0], "cv316": [0.0, 2600.0],
               "tph_sag1": [600.0, 1200.0], "tph_sag2": [1200.0, 2400.0]}
        assert compute_post_t8_balance(sim, duracion_t8_h=8.0) is None

    def test_explain_post_t8_menciona_superavit_positivo(self):
        sim = _sim_con_balance(qin1=1500, qout1=1200, qin2=2600, qout2=2400)
        balance = compute_post_t8_balance(sim, duracion_t8_h=4.0)
        texto = explain_post_t8(balance)
        assert "recupera" in texto
        assert "+300" in texto

    def test_explain_post_t8_menciona_drenaje_con_signo_negativo(self):
        sim = _sim_con_balance(qin1=1000, qout1=1400, qin2=2000, qout2=2600)
        balance = compute_post_t8_balance(sim, duracion_t8_h=4.0)
        texto = explain_post_t8(balance)
        assert "drena" in texto
        assert "-400" in texto


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
