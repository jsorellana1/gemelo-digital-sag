"""test_backtesting_mantenimiento.py — QA 2026-07-07: backtesting real
(proxy detectado retrospectivamente sobre SAG1_operando/SAG2_operando —
no cubre CH1/CH2/bolas, ver docstring de regime_event_detector.py) para
'mantenimiento'. NO se ajusta la tolerancia para hacer pasar el test."""
import pytest

from engine.historical_backtesting import run_backtest_proxy, N_MINIMO_EVENTOS, TOLERANCIAS_BACKTESTING


class TestBacktestingMantenimiento:
    def test_n_eventos_alcanza_minimo(self):
        r = run_backtest_proxy("mantenimiento")
        assert r.historica_disponible is True
        assert r.n_eventos >= N_MINIMO_EVENTOS["mantenimiento"]

    def test_reporta_mae_real_sin_ajustar_tolerancia(self):
        r = run_backtest_proxy("mantenimiento")
        assert r.pila_mae_sag1_pp is not None
        assert r.dentro_tolerancia == (r.pila_mae_sag1_pp <= TOLERANCIAS_BACKTESTING["pila_mae_pct"])


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
