"""test_t3_tph_balance.py — QA 2026-07-06: balance de masa T1 = CV315 + CV316 + T3,
todo en TPH (nunca %). Valida engine.ode_model.compute_t1_distribution en
modo manual (CV315/CV316 fijados por el usuario, T3 = residual).
"""
import pytest

from engine.ode_model import compute_t1_distribution


def _manual(t1_tph, cv315, cv316):
    return compute_t1_distribution(
        t1_tph=t1_tph, t3_frac=0.0, distribucion_t1="balanceado",
        sag1_demand_tph=cv315, sag2_demand_tph=cv316,
        cv_mode="manual", cv315_manual=cv315, cv316_manual=cv316,
    )


class TestBalanceT1T3:
    def test_caso1_t1_4000_cv315_1200_cv316_2500(self):
        cv315, cv316, t3, alerta = _manual(4000, 1200, 2500)
        assert t3 == pytest.approx(300.0)
        assert alerta is False
        assert cv315 == pytest.approx(1200.0)
        assert cv316 == pytest.approx(2500.0)

    def test_caso2_t1_1500_cv315_800_cv316_600(self):
        cv315, cv316, t3, alerta = _manual(1500, 800, 600)
        assert t3 == pytest.approx(100.0)
        assert alerta is False

    def test_caso3_t1_2500_cv315_1000_cv316_1500(self):
        cv315, cv316, t3, alerta = _manual(2500, 1000, 1500)
        assert t3 == pytest.approx(0.0)
        assert alerta is False

    def test_caso4_invalido_cv315_1000_cv316_800_supera_t1_1500(self):
        """CV315+CV316=1800 > T1=1500 -> debe marcar alerta (asignacion
        invalida) y NUNCA devolver T3 negativo."""
        cv315, cv316, t3, alerta = _manual(1500, 1000, 800)
        assert alerta is True
        assert t3 >= 0.0
        # Reescala proporcionalmente en vez de bloquear la app (no exception).
        assert (cv315 + cv316) <= 1500.0 + 1e-6

    def test_balance_de_masa_siempre_se_cumple(self):
        """Invariante T1 = CV315 + CV316 + T3 para cualquier combinacion,
        valida o invalida."""
        casos = [
            (4000, 1200, 2500), (1500, 800, 600), (2500, 1000, 1500),
            (1500, 1000, 800), (0, 0, 0), (3000, 3000, 3000),
        ]
        for t1, c315_in, c316_in in casos:
            cv315, cv316, t3, _ = _manual(t1, c315_in, c316_in)
            assert cv315 + cv316 + t3 == pytest.approx(t1, abs=1e-6)

    def test_t3_nunca_negativo(self):
        for t1, c315_in, c316_in in [(0, 500, 500), (100, 1000, 1000)]:
            _, _, t3, _ = _manual(t1, c315_in, c316_in)
            assert t3 >= 0.0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
