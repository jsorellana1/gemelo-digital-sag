"""test_transient_penalty.py — Fase C del reenfoque autonomia/armonia:
penalizacion de cambios bruscos de rate (>10% P90) y de redecisiones
dentro del mismo bloque horario.
"""
import numpy as np

from engine.transient_penalty import compute_transient_penalty, combined_transient_penalty

P90_SAG1 = 1450.0


class TestComputeTransientPenalty:
    def test_serie_constante_penalizacion_cero(self):
        serie = [1300.0] * 20
        time_h = list(np.linspace(0, 4, 20))
        r = compute_transient_penalty(serie, time_h, P90_SAG1)
        assert r["penalty_score"] == 0.0
        assert r["n_cambios_bruscos"] == 0

    def test_saltos_bruscos_1450_1100_1500_1200_penalizan(self):
        serie = [1450.0, 1100.0, 1500.0, 1200.0]
        time_h = [0.0, 1.0, 2.0, 3.0]
        r = compute_transient_penalty(serie, time_h, P90_SAG1, block_hours=1.0)
        assert r["n_cambios_bruscos"] == 3
        assert r["penalty_score"] > 0.0

    def test_cambio_pequeno_bajo_umbral_no_penaliza(self):
        # 5% de P90 = 72.5 TPH, bajo el umbral de 10%
        serie = [1400.0, 1400.0 + 0.05 * P90_SAG1, 1400.0]
        time_h = [0.0, 1.0, 2.0]
        r = compute_transient_penalty(serie, time_h, P90_SAG1)
        assert r["n_cambios_bruscos"] == 0
        assert r["penalty_score"] == 0.0

    def test_cambio_brusco_mismo_bloque_penaliza_mas_que_entre_bloques(self):
        # Serie larga con un unico salto brusco, para que el termino de
        # "mismo bloque" se note sin toparse con el cap de 100.
        salto = 1450.0 * 0.30
        base = [1000.0] * 10
        serie = base + [1000.0 + salto] + base

        time_intra = list(np.linspace(0.0, 0.9, 10)) + [0.95] + list(np.linspace(1.05, 3.0, 10))
        time_inter = list(np.linspace(0.0, 0.9, 10)) + [1.95] + list(np.linspace(2.05, 4.0, 10))

        r_intra = compute_transient_penalty(serie, time_intra, P90_SAG1, block_hours=1.0)
        r_inter = compute_transient_penalty(serie, time_inter, P90_SAG1, block_hours=1.0)
        assert r_intra["penalty_score"] > r_inter["penalty_score"]

    def test_serie_insuficiente_retorna_cero_con_razon(self):
        r = compute_transient_penalty([1300.0], [0.0], P90_SAG1)
        assert r["penalty_score"] == 0.0
        assert r["razon"]

    def test_penalizacion_nunca_supera_100(self):
        serie = [1000.0, 2000.0] * 10
        time_h = list(range(20))
        r = compute_transient_penalty(serie, time_h, P90_SAG1, block_hours=1.0)
        assert r["penalty_score"] <= 100.0


class TestCombinedTransientPenalty:
    def test_promedio_de_ambos_sag(self):
        constante = [1300.0] * 10
        time_h = list(np.linspace(0, 4, 10))
        val = combined_transient_penalty(constante, constante, time_h, P90_SAG1, 2516.0)
        assert val == 0.0
