"""test_optimizer_v5.py — Fase B del reenfoque autonomia/armonia: score
multiobjetivo (produccion+autonomia+armonia+estabilidad-riesgo-transitorios)
con 3 perfiles de peso, re-rankeando candidatos ya evaluados por V3 (mismo
patron que optimizer_v4.py, sin ejecutar nueva simulacion).
"""
from engine.optimizer_v5 import PERFILES_V5, score_v5_candidate, find_optimal_v5

_CAND_BALANCEADO = {
    "r1": 1160.0, "b1": "solo_411", "r2": 2010.0, "b2": "solo_511",
    "tph_mean": 3170.0, "a1_min": 3.0, "a2_min": 3.5,
    "p_safe": 0.92, "p_crisis": 0.08,
    "multi_criteria_score": 0.75,
}
_CAND_SAG1_MAXIMIZADO = {
    "r1": 1516.0, "b1": "ambas_411_412", "r2": 800.0, "b2": "sin_bola",
    "tph_mean": 2316.0, "a1_min": 0.4, "a2_min": 12.0,
    "p_safe": 0.55, "p_crisis": 0.45,
    "multi_criteria_score": 0.60,
}


class TestPerfilesV5:
    def test_pesos_suman_uno(self):
        for nombre, pesos in PERFILES_V5.items():
            assert abs(sum(pesos.values()) - 1.0) < 1e-9, nombre

    def test_conservador_prioriza_autonomia_sobre_produccion(self):
        assert PERFILES_V5["conservador"]["w_aut"] > PERFILES_V5["conservador"]["w_prod"]

    def test_productivo_prioriza_produccion(self):
        p = PERFILES_V5["productivo"]
        assert p["w_prod"] > p["w_aut"]
        assert p["w_prod"] > p["w_arm"]


class TestScoreV5Candidate:
    def test_no_muta_el_candidato_original(self):
        original = dict(_CAND_BALANCEADO)
        score_v5_candidate(_CAND_BALANCEADO, perfil="balanceado")
        assert _CAND_BALANCEADO == original

    def test_agrega_campos_esperados(self):
        r = score_v5_candidate(_CAND_BALANCEADO, perfil="balanceado")
        assert "score_v5" in r
        assert "harmony_index" in r
        assert 0.0 <= r["harmony_index"] <= 100.0

    def test_candidato_balanceado_supera_a_sag1_maximizado_en_conservador(self):
        """Con perfil conservador, un candidato con autonomia pareja y alta
        (a1_min=3.0/a2_min=3.5) debe rankear por sobre uno que maximiza SAG1
        dejando SAG2 con autonomia mucho mayor pero SAG1 casi vacio
        (a1_min=0.4h) y menor p_safe."""
        bal = score_v5_candidate(_CAND_BALANCEADO, perfil="conservador")
        sag1_max = score_v5_candidate(_CAND_SAG1_MAXIMIZADO, perfil="conservador")
        assert bal["score_v5"] > sag1_max["score_v5"]

    def test_variabilidad_alta_penaliza_estabilidad(self):
        sin_var = score_v5_candidate(_CAND_BALANCEADO, perfil="balanceado", cv_tph1=0.0, cv_tph2=0.0)
        con_var = score_v5_candidate(_CAND_BALANCEADO, perfil="balanceado", cv_tph1=0.5, cv_tph2=0.5)
        assert con_var["score_v5"] < sin_var["score_v5"]

    def test_penalizacion_transitorios_reduce_score(self):
        sin_pen = score_v5_candidate(_CAND_BALANCEADO, perfil="balanceado", transient_penalty_score=0.0)
        con_pen = score_v5_candidate(_CAND_BALANCEADO, perfil="balanceado", transient_penalty_score=80.0)
        assert con_pen["score_v5"] < sin_pen["score_v5"]


class TestFindOptimalV5:
    def test_reordena_y_retorna_mejor_y_lista_completa(self):
        all_results = [_CAND_SAG1_MAXIMIZADO, _CAND_BALANCEADO]
        best, scored = find_optimal_v5(all_results, perfil="conservador")
        assert len(scored) == 2
        assert best["r1"] == _CAND_BALANCEADO["r1"]
        assert scored[0]["score_v5"] >= scored[1]["score_v5"]

    def test_lista_vacia_retorna_vacio(self):
        best, scored = find_optimal_v5([], perfil="balanceado")
        assert best == {}
        assert scored == []

    def test_perfil_desconocido_cae_a_balanceado(self):
        best, _ = find_optimal_v5([_CAND_BALANCEADO], perfil="no_existe")
        assert best["perfil_v5"] == "no_existe"  # se registra el perfil pedido...
        # ...pero los pesos usados son los de "balanceado" (fallback silencioso
        # documentado en score_v5_candidate via PERFILES_V5.get(perfil, ...))
