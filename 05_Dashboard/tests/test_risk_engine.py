"""test_risk_engine.py — Fase 1.1 del roadmap de cierre (2026-07-15, ver
04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md):
sub-scores dinámico/histórico aditivos en compute_iro, sin cambiar el
IRO total.
"""
import pytest

from engine.risk_engine import compute_iro
from engine.circuit_state import AutonomyContext


def _ctx(status, hours, rate, hist_hours, vuln):
    return AutonomyContext(
        dynamic_hours=hours, dynamic_status=status, dynamic_net_rate_tph=rate,
        historical_hours=hist_hours, historical_vulnerability=vuln, divergence_class="CONSISTENT",
    )


_BASE_KWARGS = dict(
    pile_sag1_pct=25.0, pile_sag2_pct=55.0, autonomia_sag1_h=0.42, autonomia_sag2_h=5.0,
    rate_sag1_pct=40.0, rate_sag2_pct=100.0, duracion_t8_h=0.0,
    correa315_estado="activa", correa316_estado="activa",
)


class TestComputeIroSubScoresAditivos:
    def test_sin_contexto_no_agrega_claves_nuevas(self):
        """Compatibilidad: sin autonomy_context_sag1/2, el dict de retorno
        es exactamente el legacy (mismas 7 claves, sin las 2 nuevas)."""
        r = compute_iro(**_BASE_KWARGS)
        assert set(r.keys()) == {"iro", "inventario_score", "autonomia_score",
                                  "rate_score", "t8_score", "correa_score", "color"}

    def test_con_contexto_iro_total_no_cambia(self):
        """El iro total (y todos los sub-scores legacy) debe ser idéntico
        con o sin AutonomyContext — la migración es puramente aditiva."""
        sin_ctx = compute_iro(**_BASE_KWARGS)
        ctx1 = _ctx("FILLING", None, -100.0, 0.42, "CRITICA")
        ctx2 = _ctx("STABLE", None, 0.0, 5.0, "BAJA")
        con_ctx = compute_iro(**_BASE_KWARGS, autonomy_context_sag1=ctx1, autonomy_context_sag2=ctx2)
        for key in ("iro", "inventario_score", "autonomia_score", "rate_score",
                    "t8_score", "correa_score", "color"):
            assert sin_ctx[key] == con_ctx[key]

    def test_pila_llenando_da_dynamic_depletion_score_alto_pese_a_historica_baja(self):
        """Caso central de la Fase 1.1: pila con vulnerabilidad histórica
        crítica pero llenándose ahora -> dynamic_depletion_score alto
        (sin riesgo inmediato), aunque autonomia_score (legacy) siga bajo."""
        ctx1 = _ctx("FILLING", None, -100.0, 0.42, "CRITICA")
        ctx2 = _ctx("STABLE", None, 0.0, 5.0, "BAJA")
        r = compute_iro(**_BASE_KWARGS, autonomy_context_sag1=ctx1, autonomy_context_sag2=ctx2)
        assert r["dynamic_depletion_score"] == 100.0
        assert r["autonomia_score"] < 20.0  # legacy sigue penalizando fuerte
        assert r["historical_vulnerability_score"] == 10.0  # CRITICA

    def test_draining_con_pocas_horas_da_dynamic_depletion_score_bajo(self):
        ctx1 = _ctx("DRAINING", 0.5, 500.0, 0.42, "CRITICA")
        ctx2 = _ctx("STABLE", None, 0.0, 5.0, "BAJA")
        r = compute_iro(**_BASE_KWARGS, autonomy_context_sag1=ctx1, autonomy_context_sag2=ctx2)
        assert r["dynamic_depletion_score"] < 20.0

    def test_at_critical_level_da_dynamic_depletion_score_cero(self):
        ctx1 = _ctx("AT_CRITICAL_LEVEL", 0.0, 900.0, 0.1, "CRITICA")
        ctx2 = _ctx("STABLE", None, 0.0, 5.0, "BAJA")
        r = compute_iro(**_BASE_KWARGS, autonomy_context_sag1=ctx1, autonomy_context_sag2=ctx2)
        assert r["dynamic_depletion_score"] == 0.0

    def test_sag_off_no_penaliza_dynamic_depletion_score(self):
        ctx1 = _ctx("SAG_OFF", None, 0.0, 5.0, "BAJA")
        ctx2 = _ctx("STABLE", None, 0.0, 5.0, "BAJA")
        r = compute_iro(**_BASE_KWARGS, autonomy_context_sag1=ctx1, autonomy_context_sag2=ctx2)
        assert r["dynamic_depletion_score"] == 100.0

    def test_historical_vulnerability_score_usa_el_peor_de_los_dos_sag(self):
        ctx1 = _ctx("STABLE", None, 0.0, 5.0, "BAJA")
        ctx2 = _ctx("STABLE", None, 0.0, 0.3, "CRITICA")
        r = compute_iro(**_BASE_KWARGS, autonomy_context_sag1=ctx1, autonomy_context_sag2=ctx2)
        assert r["historical_vulnerability_score"] == 10.0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
