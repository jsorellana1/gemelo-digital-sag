"""test_optimizer_v2_dual_score.py — Fase 3.2-3.4 del roadmap de cierre
(2026-07-15, ver 04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md): dual score aditivo
(dynamic_safety_score/historical_buffer_score) en optimizer_v2.py, sin
tocar compute_multi_criteria_score ni el det_score que decide la
selección real de run_deterministic_grid.
"""
import pytest

from engine.optimizer_v2 import (
    run_deterministic_grid, compute_dual_score, compare_rankings,
    adaptive_mc_eval, REF_AUTON_SAG1, REF_AUTON_SAG2,
)


def _cand(**overrides):
    base = dict(det_score=0.5, label_short="c1",
                dynamic_status_sag1="STABLE", dynamic_status_sag2="STABLE",
                dynamic_autonomy_sag1_h=None, dynamic_autonomy_sag2_h=None,
                historical_vulnerability_sag1="BAJA", historical_vulnerability_sag2="BAJA")
    base.update(overrides)
    return base


class TestComputeDualScore:
    def test_filling_stable_sag_off_dan_seguridad_dinamica_maxima(self):
        for status in ("FILLING", "STABLE", "SAG_OFF"):
            c = _cand(dynamic_status_sag1=status, dynamic_status_sag2=status)
            ds = compute_dual_score(c)
            assert ds["dynamic_safety_score"] == 1.0

    def test_at_critical_level_da_seguridad_dinamica_cero(self):
        c = _cand(dynamic_status_sag1="AT_CRITICAL_LEVEL")
        ds = compute_dual_score(c)
        assert ds["dynamic_safety_score"] == 0.0

    def test_draining_escala_con_horas_sobre_ref_auton(self):
        c = _cand(dynamic_status_sag1="DRAINING", dynamic_autonomy_sag1_h=REF_AUTON_SAG1 / 2.0)
        ds = compute_dual_score(c)
        assert ds["dynamic_safety_score"] == pytest.approx(0.5, abs=0.01)

    def test_usa_el_peor_de_los_dos_sag(self):
        c = _cand(dynamic_status_sag1="STABLE", dynamic_status_sag2="AT_CRITICAL_LEVEL")
        ds = compute_dual_score(c)
        assert ds["dynamic_safety_score"] == 0.0

    def test_sin_claves_dinamicas_retorna_none_no_cero(self):
        """Un candidato legacy (sin las claves nuevas) no debe interpretarse
        como 'sin seguridad' (0.0) — debe distinguirse explícitamente
        como 'sin dato' (None)."""
        c = {"det_score": 0.5, "label_short": "legacy"}
        ds = compute_dual_score(c)
        assert ds["dynamic_safety_score"] is None
        assert ds["historical_buffer_score"] is None

    def test_vulnerabilidad_historica_usa_el_peor_de_los_dos_sag(self):
        c = _cand(historical_vulnerability_sag1="BAJA", historical_vulnerability_sag2="CRITICA")
        ds = compute_dual_score(c)
        assert ds["historical_buffer_score"] == 0.1


class TestCompareRankings:
    def test_lista_vacia_no_diverge(self):
        assert compare_rankings([]) == {"ranking_diverges": False, "top_legacy": None, "top_dynamic": None}

    def test_top_legacy_y_dinamico_coinciden_cuando_el_mejor_score_es_el_mismo(self):
        results = [
            _cand(det_score=0.9, label_short="mejor", dynamic_status_sag1="STABLE"),
            _cand(det_score=0.3, label_short="peor", dynamic_status_sag1="AT_CRITICAL_LEVEL"),
        ]
        cmp = compare_rankings(results)
        assert cmp["ranking_diverges"] is False
        assert cmp["top_legacy"] == cmp["top_dynamic"] == "mejor"

    def test_deteccion_de_divergencia_real(self):
        """El candidato #1 por det_score puede estar drenando activamente
        mientras otro candidato, con menor det_score, está en un estado
        dinámico más seguro — exactamente el caso que motiva esta fase."""
        results = [
            _cand(det_score=0.9, label_short="alto_score_pero_critico",
                  dynamic_status_sag1="AT_CRITICAL_LEVEL"),
            _cand(det_score=0.5, label_short="menor_score_pero_seguro",
                  dynamic_status_sag1="STABLE"),
        ]
        cmp = compare_rankings(results)
        assert cmp["ranking_diverges"] is True
        assert cmp["top_legacy"] == "alto_score_pero_critico"
        assert cmp["top_dynamic"] == "menor_score_pero_seguro"

    def test_run_deterministic_grid_no_cambia_su_orden_de_seleccion(self):
        """La migracion es puramente aditiva: run_deterministic_grid sigue
        ordenando por det_score, exactamente como antes de esta fase."""
        results = run_deterministic_grid(
            pila1=55.0, pila2=55.0, duracion_t8=0.0, sag1_on=True, sag2_on=True,
            ch1_on=True, ch2_on=True, c315="activa", c316="activa",
            t1_mode="chancado", t1_manual=4000.0, t3_frac=0.0, distribucion_t1="proporcional",
            horizonte=4.0, r1_cands=[1018, 1454], r2_cands=[2214, 2516],
            bola1_opts=["solo_411"], bola2_opts=["solo_511"],
        )
        scores = [r["det_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_run_deterministic_grid_acepta_simulation_overrides_multicelda(self):
        aggregate = run_deterministic_grid(
            pila1=60.0, pila2=55.0, duracion_t8=0.0, sag1_on=True, sag2_on=False,
            ch1_on=True, ch2_on=True, c315="activa", c316="activa",
            t1_mode="chancado", t1_manual=4000.0, t3_frac=0.0, distribucion_t1="proporcional",
            horizonte=4.0, r1_cands=[1454], r2_cands=[1888],
            bola1_opts=["solo_411"], bola2_opts=["sin_bola"],
        )
        multicell = run_deterministic_grid(
            pila1=60.0, pila2=55.0, duracion_t8=0.0, sag1_on=True, sag2_on=False,
            ch1_on=True, ch2_on=True, c315="activa", c316="activa",
            t1_mode="chancado", t1_manual=4000.0, t3_frac=0.0, distribucion_t1="proporcional",
            horizonte=4.0, r1_cands=[1454], r2_cands=[1888],
            bola1_opts=["solo_411"], bola2_opts=["sin_bola"],
            simulation_overrides={
                "multicell_enabled": True,
                "initial_channel_levels_sag1": [100.0, 80.0, 0.0],
                "multicell_rate_table_sag1": {0: 0.0, 1: 600.0, 2: 900.0, 3: 1454.0},
            },
        )
        assert aggregate[0]["tph_mean"] > multicell[0]["tph_mean"]


class TestAdaptiveMcEvalDualScore:
    """Fase 3 (completa Monte Carlo, 2026-07-15): p_dynamic_safe/pct_
    draining_sagX/pct_at_critical_sagX aditivos en adaptive_mc_eval, sin
    tocar p_safe ni multi_criteria_score."""

    _CAND = dict(r1=1454.0, b1="solo_411", r2=2214.0, b2="solo_511", tph_mean=3000.0,
                 a1_min=3.0, a2_min=5.0, inv_sag1_final=55.0, inv_sag2_final=55.0, label_short="test")

    def test_expone_campos_dinamicos_sin_cambiar_p_safe(self):
        res = adaptive_mc_eval(
            dict(self._CAND), pila1=55.0, pila2=55.0, cv315_nom=1200.0, cv316_nom=2200.0,
            duracion_t8=4.0, sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
            c315="reducida", c316="reducida", t1_mode="chancado", t1_manual=4000.0,
            t3_frac=0.0, distribucion_t1="proporcional", horizonte=6.0, seed=1,
        )
        for key in ("p_dynamic_safe", "pct_draining_sag1", "pct_draining_sag2",
                    "pct_at_critical_sag1", "pct_at_critical_sag2"):
            assert key in res
        assert 0.0 <= res["p_dynamic_safe"] <= 1.0
        assert 0.0 <= res["p_safe"] <= 1.0

    def test_p_dynamic_safe_puede_divergir_de_p_safe(self):
        """Caso real observado: p_safe (legacy, autonomía histórica) y
        p_dynamic_safe (balance neto por muestra) miden cosas distintas y
        pueden dar valores muy diferentes para el mismo candidato — esto
        es evidencia, no un bug a corregir."""
        res = adaptive_mc_eval(
            dict(self._CAND), pila1=55.0, pila2=55.0, cv315_nom=1200.0, cv316_nom=2200.0,
            duracion_t8=4.0, sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
            c315="reducida", c316="reducida", t1_mode="chancado", t1_manual=4000.0,
            t3_frac=0.0, distribucion_t1="proporcional", horizonte=6.0, seed=1,
        )
        assert res["p_safe"] != res["p_dynamic_safe"]

    def test_score_y_orden_no_cambian(self):
        """multi_criteria_score sigue calculado igual que antes de esta
        fase — el dual score es puramente informativo."""
        from engine.optimizer_v2 import compute_multi_criteria_score
        res = adaptive_mc_eval(
            dict(self._CAND), pila1=55.0, pila2=55.0, cv315_nom=1200.0, cv316_nom=2200.0,
            duracion_t8=0.0, sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
            c315="activa", c316="activa", t1_mode="chancado", t1_manual=4000.0,
            t3_frac=0.0, distribucion_t1="proporcional", horizonte=4.0, seed=1,
        )
        expected = compute_multi_criteria_score(
            res["tph_mean"], res["p_safe"], res["inv_sag1_final"], res["inv_sag2_final"],
            res["a1_med"], res["a2_med"],
        )
        assert res["multi_criteria_score"] == pytest.approx(expected, abs=0.01)


class TestOptimizerV3HeredaDualScore:
    """Fase 3 (cierre, 2026-07-15): confirma que find_optimal_v3 NO
    necesita migracion propia -- no calcula ningun score nuevo, solo
    reordena resultados de run_deterministic_grid/adaptive_mc_eval (ya
    instrumentados), asi que hereda el dual score sin cambios de codigo."""

    def test_find_optimal_v3_expone_campos_dual_score(self):
        from engine.optimizer_v3 import find_optimal_v3

        best, results = find_optimal_v3(
            pila1=55.0, pila2=55.0, duracion_t8=4.0, sag1_on=True, sag2_on=True,
            ch1_on=True, ch2_on=True, c315="reducida", c316="reducida",
            t1_mode="chancado", t1_manual=4000.0, t3_frac=0.0, distribucion_t1="proporcional",
            horizonte=8.0, mode="balanced", seed=1,
        )
        claves_dual_score = (
            "p_dynamic_safe", "pct_draining_sag1", "pct_draining_sag2",
            "pct_at_critical_sag1", "pct_at_critical_sag2",
            "dynamic_status_sag1", "dynamic_status_sag2",
            "historical_vulnerability_sag1", "historical_vulnerability_sag2",
        )
        for key in claves_dual_score:
            assert key in best, f"falta '{key}' en el resultado de find_optimal_v3"
        assert 0.0 <= best["p_dynamic_safe"] <= 1.0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
