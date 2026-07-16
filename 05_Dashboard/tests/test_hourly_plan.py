"""test_hourly_plan.py — Fase C del reenfoque autonomia/armonia: plan
operacional por hora derivado de las series de simulate_ode() (resample,
sin nueva simulacion).
"""
import numpy as np

from engine.hourly_plan import build_hourly_plan


def _synthetic_sim_result(n_hours=4, dt_min=5):
    n = int(n_hours * 60 / dt_min) + 1
    time_h = np.linspace(0, n_hours, n)
    return {
        "time": time_h.tolist(),
        "cv315": [1200.0] * n,
        "cv316": [2500.0] * n,
        "tph_sag1": [1150.0] * n,
        "tph_sag2": [2400.0] * n,
        "autonomia_sag1": np.linspace(4.0, 0.5, n).tolist(),
        "autonomia_sag2": [8.0] * n,
        "bola411": [1.0] * n,
        "bola412": [0.0] * n,
        "bola511": [1.0] * n,
        "bola512": [1.0] * n,
    }


class TestBuildHourlyPlan:
    def test_retorna_una_fila_por_bloque_horario(self):
        # time_h = linspace(0,4,n) incluye el extremo 4.0h exacto, que cae
        # en su propio bloque floor(4.0/1.0)=4 (bloque final de 1 muestra) —
        # por eso son 5 bloques (0..4), no 4.
        sim = _synthetic_sim_result(n_hours=4)
        plan = build_hourly_plan(sim, block_hours=1.0)
        assert len(plan) == 5
        assert [row["hora"] for row in plan] == [0.0, 1.0, 2.0, 3.0, 4.0]

    def test_mobos_sag2_es_2_y_sag1_es_1(self):
        sim = _synthetic_sim_result(n_hours=2)
        plan = build_hourly_plan(sim, block_hours=1.0)
        assert plan[0]["mobos_sag1"] == 1
        assert plan[0]["mobos_sag2"] == 2

    def test_estado_critico_cuando_autonomia_cae_bajo_1h(self):
        sim = _synthetic_sim_result(n_hours=4)
        plan = build_hourly_plan(sim, block_hours=1.0)
        # autonomia_sag1 decrece linealmente de 4.0 a 0.5h en 4h -> ultimo bloque critico
        assert plan[-1]["estado"] == "critico"
        assert plan[0]["estado"] == "normal"

    def test_serie_vacia_retorna_lista_vacia(self):
        assert build_hourly_plan({"time": []}) == []

    def test_columnas_esperadas_presentes(self):
        sim = _synthetic_sim_result(n_hours=1)
        plan = build_hourly_plan(sim, block_hours=1.0)
        esperadas = {
            "hora", "cv315_tph", "cv316_tph", "sag1_tph", "sag2_tph",
            "mobos_sag1", "mobos_sag2", "autonomia_sag1_h", "autonomia_sag2_h",
            "autonomia_min_h", "estado",
        }
        assert esperadas.issubset(plan[0].keys())

    def test_sin_pile_sag_columnas_dinamicas_quedan_en_none(self):
        """Fase 1.4: sin pile_sag1/2 (dict sintetico minimo) las columnas
        nuevas existen pero en None — nunca lanzan excepción."""
        sim = _synthetic_sim_result(n_hours=1)
        plan = build_hourly_plan(sim, block_hours=1.0)
        assert plan[0]["dynamic_status_sag1"] is None
        assert plan[0]["historical_vulnerability_sag1"] is None

    def test_con_pile_sag_calcula_estado_dinamico_por_bloque(self):
        """Fase 1.4 (2026-07-15): con pile_sag1/2 disponibles, cada
        bloque horario expone estado dinámico + vulnerabilidad histórica
        reusando los clasificadores de la Etapa 1 — pila llenando (cv315 >
        tph_sag1) debe dar FILLING, nunca confundirse con agotamiento."""
        sim = _synthetic_sim_result(n_hours=2)
        n = len(sim["time"])
        sim["pile_sag1"] = [40.0] * n  # cv315=1200 > tph_sag1=1150 -> llenando
        sim["pile_sag2"] = [40.0] * n
        plan = build_hourly_plan(sim, block_hours=1.0)
        assert plan[0]["dynamic_status_sag1"] == "FILLING"
        assert plan[0]["historical_vulnerability_sag1"] in ("CRITICA", "ALTA", "MEDIA", "BAJA")
        assert plan[0]["dynamic_autonomy_sag1_h"] is None  # FILLING -> sin horas, no cero
