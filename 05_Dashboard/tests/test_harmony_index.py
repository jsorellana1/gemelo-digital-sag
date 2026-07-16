"""test_harmony_index.py — Fase A del reenfoque autonomia/armonia:
Indice de Armonia Operacional (0-100), formula nueva documentada en
engine/harmony_index.py.
"""
from engine.harmony_index import compute_harmony_index, harmony_label

_BASE = dict(
    p90_sag1=1450.0, p90_sag2=2516.0,
    n_bolas1=1, n_bolas2=1, max_bolas=2,
    frac315_actual=0.29, frac315_proporcional=0.29,
)


class TestComputeHarmonyIndex:
    def test_escenario_balanceado_da_armonia_alta(self):
        r = compute_harmony_index(
            rate1_tph=1450.0 * 0.8, rate2_tph=2516.0 * 0.8,
            autonomia1_h=4.0, autonomia2_h=4.2,
            riesgo1=0.05, riesgo2=0.06,
            cv_tph1=0.05, cv_tph2=0.05,
            **_BASE,
        )
        assert r["harmony_index"] >= 80.0
        assert harmony_label(r["harmony_index"]) == "alta"

    def test_un_sag_maximizado_otro_en_crisis_da_armonia_baja(self):
        r = compute_harmony_index(
            rate1_tph=1450.0, rate2_tph=500.0,
            autonomia1_h=0.5, autonomia2_h=10.0,
            riesgo1=0.60, riesgo2=0.02,
            cv_tph1=0.30, cv_tph2=0.05,
            **_BASE,
        )
        assert r["harmony_index"] < 50.0
        assert harmony_label(r["harmony_index"]) == "baja"

    def test_sub_scores_suman_coherentemente_a_la_penalizacion(self):
        r = compute_harmony_index(
            rate1_tph=1000.0, rate2_tph=2000.0,
            autonomia1_h=2.0, autonomia2_h=6.0,
            riesgo1=0.10, riesgo2=0.10,
            cv_tph1=0.10, cv_tph2=0.10,
            **_BASE,
        )
        penalizacion = sum(r["pesos"][k] * r["sub_scores"][k] for k in r["pesos"])
        assert abs((100.0 - penalizacion) - r["harmony_index"]) < 0.15

    def test_cv_none_no_penaliza_variabilidad(self):
        r = compute_harmony_index(
            rate1_tph=1200.0, rate2_tph=2200.0,
            autonomia1_h=3.0, autonomia2_h=3.0,
            riesgo1=0.05, riesgo2=0.05,
            cv_tph1=None, cv_tph2=None,
            **_BASE,
        )
        assert r["sub_scores"]["variabilidad"] == 0.0

    def test_armonia_nunca_sale_de_0_100(self):
        r = compute_harmony_index(
            rate1_tph=1450.0, rate2_tph=0.0,
            autonomia1_h=0.0, autonomia2_h=24.0,
            riesgo1=1.0, riesgo2=0.0,
            cv_tph1=2.0, cv_tph2=0.0,
            n_bolas1=2, n_bolas2=0, max_bolas=2,
            frac315_actual=1.0, frac315_proporcional=0.0,
            p90_sag1=1450.0, p90_sag2=2516.0,
        )
        assert 0.0 <= r["harmony_index"] <= 100.0


class TestHarmonyLabel:
    def test_umbrales(self):
        assert harmony_label(85.0) == "alta"
        assert harmony_label(60.0) == "media"
        assert harmony_label(30.0) == "baja"
