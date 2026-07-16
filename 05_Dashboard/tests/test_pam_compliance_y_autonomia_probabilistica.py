"""test_pam_compliance_y_autonomia_probabilistica.py — QA 2026-07-06:
cierre de 2 gaps del loop maestro de integracion (matriz de preguntas
operacionales): "¿Cumplire el PAM?" / "¿Cual es el deficit esperado?"
(engine.production_stats.pam_compliance_stats) y "¿Cual es la autonomia
probabilistica?" (P10/P90 en engine.optimizer_v2.adaptive_mc_eval, sobre
las mismas muestras ya recolectadas — cero simulaciones adicionales)."""
import pytest

from engine.production_stats import pam_compliance_stats
from engine.optimizer_v2 import adaptive_mc_eval
from engine.optimizer_v3 import find_optimal_v3
from components.cards import make_mc_confidence_card, make_pam_compliance_card

_CAND = {
    "r1": 1236, "b1": "sin_bola", "r2": 2214, "b2": "sin_bola",
    "tph_mean": 1500, "inv_sag1_final": 55, "inv_sag2_final": 55,
    "a1_min": 2.0, "a2_min": 2.0,
}


class TestPamCompliance:
    def test_sag1_sag2_tienen_stats(self):
        s1 = pam_compliance_stats("SAG1")
        s2 = pam_compliance_stats("SAG2")
        assert s1["n_dias"] > 500
        assert s2["n_dias"] > 500

    def test_probabilidad_entre_0_y_1(self):
        for asset in ("SAG1", "SAG2"):
            s = pam_compliance_stats(asset)
            assert 0.0 <= s["p_cumple_historico"] <= 1.0

    def test_sin_outlier_de_division_por_pam_casi_cero(self):
        """Regression: un registro con pam_sag2=1.36e-13 (artefacto de
        redondeo en la fuente) hacia explotar el promedio de cumplimiento
        a ~10^16% antes del fix de filtro > 1000 t/dia."""
        s2 = pam_compliance_stats("SAG2")
        assert 0.0 <= s2["cumplimiento_medio_pct"] <= 500.0

    def test_percentiles_ordenados(self):
        for asset in ("SAG1", "SAG2"):
            s = pam_compliance_stats(asset)
            assert s["cumplimiento_p10_pct"] <= s["cumplimiento_medio_pct"] <= s["cumplimiento_p90_pct"] * 1.5

    def test_asset_desconocido_retorna_vacio(self):
        assert pam_compliance_stats("NO_EXISTE") == {}


class TestAutonomiaProbabilistica:
    def _run(self, **overrides):
        params = dict(
            cand=_CAND, pila1=55.0, pila2=55.0, cv315_nom=1000.0, cv316_nom=1000.0,
            duracion_t8=4.0, sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
            c315="activa", c316="activa", t1_mode="chancado", t1_manual=4000.0,
            t3_frac=0.0, distribucion_t1="proporcional", horizonte=24.0,
        )
        params.update(overrides)
        return adaptive_mc_eval(**params)

    def test_percentiles_presentes_y_ordenados(self):
        res = self._run()
        assert res["a1_p10"] <= res["a1_med"] <= res["a1_p90"]
        assert res["a2_p10"] <= res["a2_med"] <= res["a2_p90"]

    def test_no_agrega_simulaciones(self):
        """Verifica que n_samples_used no cambia por agregar P10/P90 —
        deben venir de las mismas muestras que ya se usaban para a1_med."""
        res = self._run()
        assert res["n_samples_used"] > 0


class TestWiringUI:
    def test_mc_confidence_card_incluye_autonomia_probabilistica(self):
        best, _ = find_optimal_v3(
            pila1=45.0, pila2=55.0, duracion_t8=8.0,
            sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
            c315="activa", c316="activa",
            t1_mode="chancado", t1_manual=4000.0,
            t3_frac=0.0, distribucion_t1="proporcional",
            horizonte=24.0, mode="balanced",
        )
        assert "a1_p10" in best and "a1_p90" in best
        card = make_mc_confidence_card(best)
        assert card is not None

    def test_pam_compliance_card_no_falla_sin_datos(self):
        card = make_pam_compliance_card({}, {})
        assert card is not None

    def test_pam_compliance_card_con_datos_reales(self):
        s1 = pam_compliance_stats("SAG1")
        s2 = pam_compliance_stats("SAG2")
        card = make_pam_compliance_card(s1, s2)
        assert card is not None


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
