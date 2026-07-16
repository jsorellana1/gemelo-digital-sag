"""test_optimizer_v3.py — Fase 4 QA: invariantes de find_optimal_v3.

No fija numeros exactos del tuning calibrado (grid, pesos) — valida
contratos que el resto de la app asume: respeta restricciones de R16,
siempre devuelve brecha P90 y top-N, y recomienda algo productivo cuando
no hay restricciones activas.
"""
import pytest

from engine.optimizer_v3 import find_optimal_v3

_BASE = dict(
    pila1=55.0, pila2=55.0, duracion_t8=0.0,
    sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
    c315="activa", c316="activa",
    t1_mode="chancado", t1_manual=4000.0,
    t3_frac=0.0, distribucion_t1="proporcional",
    horizonte=24.0, mode="balanced",
)


def _optimize(**overrides):
    params = dict(_BASE)
    params.update(overrides)
    return find_optimal_v3(**params)


class TestOptimizerV3:
    def test_respeta_r16_restriccion_bola1(self):
        """Simula 411+412 en mantencion (bola1_opts=['sin_bola']): el
        optimizador no debe recomendar ni evaluar 'ambas_411_412'."""
        best, results = _optimize(bola1_opts=["sin_bola"])
        assert best["b1"] == "sin_bola"
        assert all(r["b1"] == "sin_bola" for r in results)

    def test_respeta_r16_restriccion_bola2(self):
        best, results = _optimize(bola2_opts=["sin_bola"])
        assert best["b2"] == "sin_bola"
        assert all(r["b2"] == "sin_bola" for r in results)

    def test_sag1_productivo_sin_t8_sin_restricciones(self):
        """Sin T8 y sin restricciones de mantencion, SAG1 deberia recibir
        una recomendacion productiva (no forzado a minimo)."""
        best, _ = _optimize(duracion_t8=0.0)
        assert best["r1"] > 0
        assert best["tph_mean"] > 0

    def test_retorna_brecha_p90(self):
        best, _ = _optimize()
        assert "brecha_p90" in best
        brecha = best["brecha_p90"]
        assert "brecha_tph_sag1" in brecha
        assert "zona" in brecha

    def test_retorna_top_soluciones(self):
        best, results = _optimize()
        assert len(results) > 0
        assert all("r1" in r and "r2" in r for r in results)

    def test_validation_answer_presente(self):
        best, _ = _optimize()
        assert isinstance(best.get("validation_answer"), str)
        assert len(best["validation_answer"]) > 0

    def test_mc_no_bloquea_marca_convergencia(self):
        """Fase 8: el resultado siempre debe traer las banderas de
        convergencia/timeout, sin importar si convergio o no."""
        best, _ = _optimize()
        assert "converged" in best
        assert "mc_timed_out" in best
        assert "mc_warning" in best

    def test_t8_largo_no_recomienda_sag1_agresivo(self):
        """En regimen T8 largo (12h) el regimen V3 es mas conservador con
        la autonomia — la recomendacion no deberia ser mas agresiva en
        rate que el escenario sin T8."""
        best_sin_t8, _ = _optimize(duracion_t8=0.0)
        best_t8_12, _ = _optimize(duracion_t8=12.0)
        assert best_t8_12["r1"] <= best_sin_t8["r1"]


    def test_find_optimal_v3_acepta_overrides_multicelda(self):
        best_agg, _ = _optimize(
            sag2_on=False,
            bola1_opts=["solo_411"],
            bola2_opts=["sin_bola"],
        )
        best_mc, _ = _optimize(
            sag2_on=False,
            bola1_opts=["solo_411"],
            bola2_opts=["sin_bola"],
            simulation_overrides={
                "multicell_enabled": True,
                "initial_channel_levels_sag1": [100.0, 80.0, 0.0],
                "multicell_rate_table_sag1": {0: 0.0, 1: 600.0, 2: 900.0, 3: 1454.0},
            },
        )
        assert best_agg["tph_mean"] >= best_mc["tph_mean"]

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
