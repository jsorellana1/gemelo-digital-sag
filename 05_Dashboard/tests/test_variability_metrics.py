"""test_variability_metrics.py — Fase A del reenfoque autonomia/armonia:
metricas de variabilidad de TPH (CV, std, IQR, saltos, cambios de setpoint)
sobre series ya producidas por simulate_ode(), sin tocar el ODE.
"""
import numpy as np

from engine.variability_metrics import compute_tph_variability, compute_variability_report


class TestComputeTphVariability:
    def test_serie_constante_cv_cero(self):
        tph = [1500.0] * 20
        time_h = list(np.linspace(0, 4, 20))
        r = compute_tph_variability(tph, time_h)
        assert r["cv"] == 0.0
        assert r["std"] == 0.0
        assert r["max_salto"] == 0.0
        assert r["n_cambios_setpoint"] == 0

    def test_serie_variable_cv_mayor_que_cero(self):
        tph = [1200, 1500, 1100, 1600, 1000, 1550] * 4
        time_h = list(np.linspace(0, 4, len(tph)))
        r = compute_tph_variability(tph, time_h)
        assert r["cv"] > 0.05
        assert r["n_cambios_setpoint"] > 0

    def test_menos_de_2_muestras_operando_retorna_none(self):
        tph = [0.0, 10.0, 5.0]  # todo bajo el umbral de 50 TPH
        time_h = [0.0, 1.0, 2.0]
        r = compute_tph_variability(tph, time_h)
        assert r["cv"] is None
        assert r["n_muestras"] == 0
        assert "razon" in r and r["razon"]

    def test_ventana_durante_filtra_solo_esos_tiempos(self):
        time_h = list(np.linspace(0, 10, 40))
        tph = [1500.0 if t < 4 else 1500.0 + 200 * (t - 4) for t in time_h]
        r_durante = compute_tph_variability(tph, time_h, duracion_t8_h=4.0, window="durante")
        r_post = compute_tph_variability(tph, time_h, duracion_t8_h=4.0, window="post")
        assert r_durante["std"] == 0.0
        assert r_post["std"] > 0.0

    def test_max_salto_detecta_escalon(self):
        tph = [1000.0] * 10 + [1600.0] * 10
        time_h = list(np.linspace(0, 4, 20))
        r = compute_tph_variability(tph, time_h)
        assert r["max_salto"] == 600.0


class TestComputeVariabilityReport:
    def test_reporte_sin_ventana_incluye_los_3_activos(self):
        n = 30
        sim_result = {
            "time": list(np.linspace(0, 4, n)),
            "tph_sag1": [1300.0] * n,
            "tph_sag2": [2300.0] * n,
            "tph_total": [3600.0] * n,
            "duracion_t8_h": 0.0,
        }
        report = compute_variability_report(sim_result)
        assert set(report.keys()) == {"SAG1", "SAG2", "TOTAL"}
        assert "sin_ventana" in report["SAG1"]
        assert report["SAG1"]["sin_ventana"]["cv"] == 0.0

    def test_reporte_con_t8_usa_ventanas_durante_y_post(self):
        n = 40
        sim_result = {
            "time": list(np.linspace(0, 10, n)),
            "tph_sag1": [1300.0] * n,
            "tph_sag2": [2300.0] * n,
            "tph_total": [3600.0] * n,
            "duracion_t8_h": 4.0,
        }
        report = compute_variability_report(sim_result)
        assert set(report["SAG1"].keys()) == {"durante", "post"}
