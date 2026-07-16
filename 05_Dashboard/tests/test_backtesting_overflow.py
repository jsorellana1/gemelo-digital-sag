"""test_backtesting_overflow.py — QA 2026-07-07: backtesting real (proxy
detectado retrospectivamente, ver engine/diagnostics/regime_event_detector.py)
para el regimen 'overflow'. Igual criterio que test_router_v2.py: NO se
ajusta la tolerancia para hacer pasar el test — se reporta el resultado
real, sea cual sea."""
import pytest

from engine.historical_backtesting import run_backtest_proxy, N_MINIMO_EVENTOS, TOLERANCIAS_BACKTESTING


class TestBacktestingOverflow:
    def test_n_eventos_alcanza_minimo(self):
        r = run_backtest_proxy("overflow")
        assert r.historica_disponible is True
        assert r.n_eventos >= N_MINIMO_EVENTOS["overflow"]

    def test_reporta_mae_real_sin_ajustar_tolerancia(self):
        r = run_backtest_proxy("overflow")
        assert r.pila_mae_sag1_pp is not None
        # Se reporta el resultado real de dentro_tolerancia contra
        # TOLERANCIAS_BACKTESTING sin modificar — puede ser True o False.
        assert r.dentro_tolerancia == (r.pila_mae_sag1_pp <= TOLERANCIAS_BACKTESTING["pila_mae_pct"])

    def test_metricas_extendidas_mae_tph_y_tiempo_critico(self):
        """Cierre de brechas post router v2 (TAREA de auditoria): overflow
        tiene umbral de tiempo bien definido (cruce de pila >= 95%, ver
        DIRECCION_CRITICIDAD), asi que error_tiempo_critico_h debe venir
        poblado con datos reales, no None."""
        r = run_backtest_proxy("overflow")
        assert r.tph_mae_sag1_pct is not None
        assert r.error_tiempo_critico_h is not None
        assert r.error_tiempo_razon != ""


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
