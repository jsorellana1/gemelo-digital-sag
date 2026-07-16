"""test_optimizer_v4.py — QA 2026-07-06: extension Optimizer V4
(penalizacion de estabilidad aditiva sobre V3, basada en CV real medido).

No valida ninguna relacion TPH-ley/recuperacion (descartada por falta de
evidencia, ver 20260706_Reenfoque_Simulador_Basado_Evidencia.md) — solo
la logica de re-ranking por estabilidad real de SAG1/SAG2.
"""
import pytest

from engine.optimizer_v3 import find_optimal_v3
from engine.optimizer_v4 import (
    find_optimal_v4, compute_stability_penalty, score_v4, TOLERANCIA_PRESETS,
)

_BASE = dict(
    pila1=55.0, pila2=55.0, duracion_t8=0.0,
    sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
    c315="activa", c316="activa",
    t1_mode="chancado", t1_manual=4000.0,
    t3_frac=0.0, distribucion_t1="proporcional",
    horizonte=24.0, mode="balanced",
)


class TestStabilityPenalty:
    def test_penalizacion_mayor_si_todo_va_a_sag1(self):
        """SAG1 es mas variable (CV real medido mayor) — concentrar toda
        la produccion ahi debe penalizar mas que concentrarla en SAG2."""
        pen_sag1 = compute_stability_penalty(r1_tph=2000, r2_tph=0)
        pen_sag2 = compute_stability_penalty(r1_tph=0, r2_tph=2000)
        assert pen_sag1 > pen_sag2

    def test_penalizacion_cero_sin_produccion(self):
        assert compute_stability_penalty(0, 0) == 0.0

    def test_penalizacion_entre_extremos_si_se_reparte(self):
        pen_split = compute_stability_penalty(r1_tph=1000, r2_tph=1000)
        pen_sag1_full = compute_stability_penalty(r1_tph=2000, r2_tph=0)
        pen_sag2_full = compute_stability_penalty(r1_tph=0, r2_tph=2000)
        assert pen_sag2_full < pen_split < pen_sag1_full


class TestFindOptimalV4:
    def test_peso_cero_coincide_con_v3(self):
        best_v3, all_results = find_optimal_v3(**_BASE)
        best_v4 = find_optimal_v4(all_results, peso_estabilidad=0.0)
        assert best_v4["r1"] == best_v3["r1"]
        assert best_v4["r2"] == best_v3["r2"]

    def test_presets_de_tolerancia_existen(self):
        assert TOLERANCIA_PRESETS["conservador"] > TOLERANCIA_PRESETS["balanceado"] > TOLERANCIA_PRESETS["agresivo"]
        assert TOLERANCIA_PRESETS["agresivo"] == 0.0

    def test_no_ejecuta_simulaciones_nuevas(self):
        """find_optimal_v4 debe operar solo sobre all_results ya calculado
        por V3 — no debe requerir ni disparar ninguna simulacion nueva."""
        _, all_results = find_optimal_v3(**_BASE)
        import time
        t0 = time.perf_counter()
        find_optimal_v4(all_results, tolerancia="conservador")
        dt = time.perf_counter() - t0
        assert dt < 0.05, f"find_optimal_v4 tardo {dt*1000:.1f}ms — deberia ser re-ranking puro, no simulacion"

    def test_lista_vacia_retorna_vacio(self):
        assert find_optimal_v4([]) == {}

    def test_score_v4_penaliza_menos_con_peso_menor(self):
        cand = {"multi_criteria_score": 0.9, "r1": 2000, "r2": 0}
        s_alto = score_v4(cand, peso_estabilidad=0.30)
        s_bajo = score_v4(cand, peso_estabilidad=0.0)
        assert s_bajo > s_alto


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
