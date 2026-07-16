"""test_backtesting_inventario_critico.py — QA 2026-07-07: backtesting
real (proxy detectado retrospectivamente) para 'inventario_critico'. NO
se ajusta la tolerancia para hacer pasar el test."""
import pytest

from engine.historical_backtesting import run_backtest_proxy, N_MINIMO_EVENTOS, TOLERANCIAS_BACKTESTING


class TestBacktestingInventarioCritico:
    def test_n_eventos_alcanza_minimo(self):
        r = run_backtest_proxy("inventario_critico")
        assert r.historica_disponible is True
        assert r.n_eventos >= N_MINIMO_EVENTOS["inventario_critico"]

    def test_reporta_mae_real_sin_ajustar_tolerancia(self):
        r = run_backtest_proxy("inventario_critico")
        assert r.pila_mae_sag1_pp is not None
        assert r.dentro_tolerancia == (r.pila_mae_sag1_pp <= TOLERANCIAS_BACKTESTING["pila_mae_pct"])


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
