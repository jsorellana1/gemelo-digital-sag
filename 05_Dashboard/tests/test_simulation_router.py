"""test_simulation_router.py — QA 2026-07-07: clasificador de escenario +
capa de explicabilidad (engine/simulation_router.py).

Usa dicts `sim` sintéticos (en vez de correr simulate_scenario end-to-end)
para aislar deterministicamente cada rama de clasificacion — la
interaccion real del ODE con parametros arbitrarios puede producir
overflow/inventario-critico simultaneos (ver hallazgo documentado en
04_Reports/Technical/20260707_Arquitectura_Simulacion_Adaptativa.md), lo
cual es correcto pero no aisla la rama que cada test quiere verificar.
Un test de integracion real (TestIntegracionReal) cubre el camino
end-to-end con simulate_scenario de verdad.
"""
import numpy as np
import pytest

from engine.simulation_router import (
    parse_user_scenario, classify_scenario, select_heuristics,
    explain_simulation_path, run_adaptive_simulation,
)
from engine.simulator import simulate_scenario


def _sim(pile1=(55, 55), pile2=(55, 55), a1=6.0, a2=8.0, **extra):
    base = {
        "pile_sag1": list(pile1),
        "pile_sag2": list(pile2),
        "min_autonomia_sag1": a1,
        "min_autonomia_sag2": a2,
        "t1_restriccion": False,
        "alerta_bola_sag1": False,
        "alerta_bola_sag2": False,
        "chancado_cap_tph": 4000.0,
        "sag1_activo": True,
        "sag2_activo": True,
    }
    base.update(extra)
    return base


def _state(**overrides):
    base = dict(
        pila1=55.0, pila2=55.0, duracion_t8=0.0,
        ch1_on=True, ch2_on=True,
        correa315_estado="activa", correa316_estado="activa",
        maint_windows=None, now_hour=8.0, horizonte=24.0,
    )
    base.update(overrides)
    return parse_user_scenario(**base)


class TestCasoNormal:
    def test_activa_h1_produccion_maxima(self):
        state = _state()
        sim = _sim(pile1=(70, 70), pile2=(70, 70))
        scenario = classify_scenario(state, sim)
        heur = select_heuristics(scenario, state)
        assert scenario["principal"] == "normal"
        assert "H1" in heur


class TestCasoT8Larga:
    def test_activa_h2_conservacion_y_h7_robustez(self):
        state = _state(duracion_t8=12.0)
        sim = _sim(pile1=(50, 60), pile2=(50, 60))  # sin cruzar overflow/critico
        scenario = classify_scenario(state, sim)
        heur = select_heuristics(scenario, state)
        assert "t8_larga" in scenario["tipos"]
        assert "H2" in heur
        assert "H7" in heur


class TestCasoCH2Off:
    def test_activa_h3_balance_alimentacion(self):
        state = _state(ch2_on=False)
        sim = _sim(pile1=(55, 55), pile2=(55, 50))
        scenario = classify_scenario(state, sim)
        heur = select_heuristics(scenario, state)
        assert "alimentacion_restringida" in scenario["tipos"]
        assert "H3" in heur


class TestCasoOverflowSAG2:
    def test_activa_h4_control_overflow(self):
        state = _state()
        sim = _sim(pile1=(55, 55), pile2=(85, 99.0))  # SAG2 sube hacia 100%
        scenario = classify_scenario(state, sim)
        heur = select_heuristics(scenario, state)
        assert "overflow" in scenario["tipos"]
        assert "H4" in heur


class TestCasoMantencionMoBo:
    def test_activa_h6_mantenimiento(self):
        state = _state(maint_windows={"411": (0, 24)}, now_hour=10.0)
        sim = _sim()
        scenario = classify_scenario(state, sim)
        heur = select_heuristics(scenario, state)
        assert "mantenimiento" in scenario["tipos"]
        assert "H6" in heur


class TestExplicacion:
    def test_texto_incluye_tipo_y_heuristicas(self):
        state = _state(duracion_t8=8.0)
        sim = _sim(pile1=(45, 50), pile2=(55, 55))
        scenario = classify_scenario(state, sim)
        heur = select_heuristics(scenario, state)
        texto = explain_simulation_path(scenario, heur, state)
        assert "Escenario clasificado" in texto
        assert "Heurísticas activas" in texto


class TestMixto:
    def test_multiples_tipos_marca_mixto(self):
        state = _state(duracion_t8=12.0, ch2_on=False)
        sim = _sim(pile1=(15, 20), pile2=(55, 55))  # inventario critico + T8 larga + alimentacion
        scenario = classify_scenario(state, sim)
        assert scenario["mixto"] is True
        assert len(scenario["tipos"]) >= 2


class TestIntegracionReal:
    def test_run_adaptive_simulation_end_to_end(self):
        """Con el motor real (simulate_scenario), sin mockear — confirma
        que el orquestador no rompe con datos reales del ODE."""
        sim = simulate_scenario(
            pila_sag1_pct=55, pila_sag2_pct=55, rate_sag1_pct=100, rate_sag2_pct=100,
            duracion_t8_h=4, correa315_estado="activa", correa316_estado="activa",
            horizonte_horas=24, ch1_on=True, ch2_on=True,
        )
        r = run_adaptive_simulation(55, 55, 4, True, True, "activa", "activa", {}, 8, 24, sim)
        assert r["scenario"]["principal"] in [
            "overflow", "inventario_critico", "mantenimiento",
            "alimentacion_restringida", "t8_larga", "t8_corta", "normal",
        ]
        assert len(r["heuristics"]) > 0
        assert isinstance(r["explicacion"], str) and len(r["explicacion"]) > 0
        assert r["bottleneck"] is not None


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
