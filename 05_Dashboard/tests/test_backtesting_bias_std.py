"""test_backtesting_bias_std.py — Fase 4.3 del roadmap de cierre
(2026-07-15, ver 04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md): bias (error CON
signo) y desviación estándar del error, extendidos como campo aditivo a
TODOS los regímenes con datos disponibles (antes solo t8_corta lo tenía,
documentado en 04_Reports/Technical/DIAGNOSTICO_MAE_t8_corta.md).

Mismo criterio que test_backtesting_overflow.py: NO se ajusta nada para
hacer pasar el test — se reporta el resultado real, sea cual sea.
"""
import pytest

from engine.historical_backtesting import run_backtest, run_backtest_proxy


class TestBiasStdT8Corta:
    def test_bias_std_poblados_y_consistentes_con_mae(self):
        r = run_backtest("t8_corta")
        assert r.historica_disponible is True
        assert r.pila_bias_sag1_pp is not None
        assert r.pila_std_sag1_pp is not None
        # |bias| <= MAE siempre se cumple por definicion (MAE = E[|e|],
        # bias = |E[e]|, y |E[e]| <= E[|e|] por la desigualdad de Jensen).
        assert abs(r.pila_bias_sag1_pp) <= r.pila_mae_sag1_pp + 1e-6

    def test_bias_negativo_confirma_subestimacion_ya_diagnosticada(self):
        """Hallazgo ya documentado en DIAGNOSTICO_MAE_t8_corta.md
        (2026-07-07): el motor SUBESTIMA la pila final en t8_corta
        (bias negativo) — esta prueba confirma que sigue siendo cierto,
        no que deba serlo."""
        r = run_backtest("t8_corta")
        assert r.pila_bias_sag1_pp < 0


class TestBiasStdRegimenesProxy:
    """overflow/inventario_critico/mantenimiento/alimentacion_restringida."""

    @pytest.mark.parametrize("regimen", [
        "overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida",
    ])
    def test_bias_std_poblados_si_hay_datos(self, regimen):
        r = run_backtest_proxy(regimen)
        if not r.historica_disponible:
            pytest.skip(f"{regimen}: sin datos suficientes, nada que verificar")
        assert r.pila_bias_sag1_pp is not None
        assert r.pila_std_sag1_pp is not None
        assert abs(r.pila_bias_sag1_pp) <= r.pila_mae_sag1_pp + 1e-6


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
