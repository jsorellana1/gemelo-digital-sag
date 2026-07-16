"""test_quick_wins.py — Fase 1.3 del roadmap de cierre (2026-07-15, ver
04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md):
QuickWin.delta_autonomia_h (ambiguo) se separó en delta_historical_
buffer_h (colchón preventivo, criterio de filtro/orden sin cambios) y
delta_dynamic_autonomy_h (mejora real en balance neto), ambos nombrados
explícitamente.
"""
import pytest

from engine.quick_wins import evaluate_quick_wins, QuickWin, _dynamic_autonomia_min, _SIN_RIESGO_DINAMICO_H


class TestQuickWinCamposRenombrados:
    def test_quickwin_tiene_los_dos_campos_nuevos_no_el_viejo(self):
        qw = QuickWin(titulo="t", descripcion="d", delta_historical_buffer_h=1.0,
                       delta_dynamic_autonomy_h=2.0, delta_riesgo_vaciado_pp=-1.0,
                       impacto_produccion_pct=-0.5, tiempo_requerido_h=1.0)
        assert not hasattr(qw, "delta_autonomia_h")
        assert qw.delta_historical_buffer_h == 1.0
        assert qw.delta_dynamic_autonomy_h == 2.0

    def test_beneficio_costo_usa_colchon_preventivo(self):
        """El criterio de ranking no cambia en esta fase — sigue anclado
        a delta_historical_buffer_h, no a la nueva métrica dinámica."""
        qw = QuickWin(titulo="t", descripcion="d", delta_historical_buffer_h=4.0,
                       delta_dynamic_autonomy_h=0.0, delta_riesgo_vaciado_pp=0.0,
                       impacto_produccion_pct=-2.0, tiempo_requerido_h=1.0)
        assert qw.beneficio_costo == pytest.approx(4.0 / 2.0)

    def test_dynamic_autonomia_min_trata_none_como_sin_riesgo(self):
        sim = {"dynamic_net_autonomy_sag1_h": None, "dynamic_net_autonomy_sag2_h": None}
        assert _dynamic_autonomia_min(sim) == _SIN_RIESGO_DINAMICO_H

    def test_dynamic_autonomia_min_usa_el_peor_de_los_dos_sag(self):
        sim = {"dynamic_net_autonomy_sag1_h": 0.5, "dynamic_net_autonomy_sag2_h": None}
        assert _dynamic_autonomia_min(sim) == 0.5

    def test_evaluate_quick_wins_no_falla_y_expone_ambos_deltas(self):
        params = dict(pila_sag1_pct=20.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
                      sag1_activo=True, sag2_activo=True, duracion_t8_h=0.0,
                      correa315_estado="activa", correa316_estado="activa", horizonte_horas=6.0)
        qws = evaluate_quick_wins(params)
        for qw in qws:
            assert isinstance(qw.delta_historical_buffer_h, float)
            assert isinstance(qw.delta_dynamic_autonomy_h, float)
            assert qw.delta_dynamic_autonomy_h <= _SIN_RIESGO_DINAMICO_H


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
