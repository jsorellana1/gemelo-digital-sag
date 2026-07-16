"""test_simulator_basic.py — Fase 4 QA: invariantes basicos de simulate_scenario.

No valida numeros exactos del modelo calibrado (eso romperia con cualquier
recalibracion legitima) — valida invariantes estructurales que deben
cumplirse siempre, sin importar la calibracion: rangos fisicos validos,
ausencia de NaN, coherencia entre inputs y outputs.
"""
import math
import numpy as np
import pytest

from engine.simulator import simulate_scenario


def _run(**overrides):
    params = dict(
        pila_sag1_pct=55.0, pila_sag2_pct=55.0,
        rate_sag1_pct=100.0, rate_sag2_pct=100.0,
        bolas_sag1="sin_bola", bolas_sag2="sin_bola",
        sag1_activo=True, sag2_activo=True,
        duracion_t8_h=0.0,
        correa315_estado="activa", correa316_estado="activa",
        horizonte_horas=24.0,
        ch1_on=True, ch2_on=True,
    )
    params.update(overrides)
    return simulate_scenario(**params)


def _assert_valid_scenario(sim):
    for key in ("pile_sag1", "pile_sag2", "tph_sag1", "tph_sag2", "tph_total", "time"):
        arr = np.array(sim[key])
        assert len(arr) > 0, f"{key} vacio"
        assert not np.isnan(arr).any(), f"{key} contiene NaN"
    pile1 = np.array(sim["pile_sag1"])
    pile2 = np.array(sim["pile_sag2"])
    assert (pile1 >= -1e-6).all(), "pile_sag1 no puede ser negativo"
    assert (pile2 >= -1e-6).all(), "pile_sag2 no puede ser negativo"
    assert (pile1 <= 100 + 1e-6).all(), "pile_sag1 no deberia superar 100%"
    assert (pile2 <= 100 + 1e-6).all(), "pile_sag2 no deberia superar 100%"


class TestEscenariosBasicos:
    def test_sin_t8(self):
        sim = _run(duracion_t8_h=0.0)
        _assert_valid_scenario(sim)

    def test_t8_2h(self):
        sim = _run(duracion_t8_h=2.0)
        _assert_valid_scenario(sim)

    def test_t8_12h(self):
        sim = _run(duracion_t8_h=12.0, horizonte_horas=24.0)
        _assert_valid_scenario(sim)
        # T8 mas largo no deberia dejar la pila en mejor estado que sin T8
        sim_sin_t8 = _run(duracion_t8_h=0.0)
        assert min(sim["pile_sag1"]) <= min(sim_sin_t8["pile_sag1"]) + 1e-6, (
            "T8 de 12h deberia consumir la pila SAG1 al menos tanto como sin T8"
        )

    def test_ch2_off(self):
        sim = _run(ch2_on=False)
        _assert_valid_scenario(sim)

    def test_correa315_inactiva(self):
        sim = _run(correa315_estado="inactiva")
        _assert_valid_scenario(sim)

    def test_correa316_inactiva(self):
        sim = _run(correa316_estado="inactiva")
        _assert_valid_scenario(sim)

    def test_sag1_apagado_no_consume_pila_por_produccion(self):
        sim = _run(sag1_activo=False)
        _assert_valid_scenario(sim)
        tph1 = np.array(sim["tph_sag1"])
        assert (tph1 <= 1e-6).all(), "SAG1 apagado no deberia producir TPH"

    def test_duracion_t8_mayor_reduce_o_iguala_autonomia_minima(self):
        a_corta = _run(duracion_t8_h=2.0).get("min_autonomia_sag1", 0)
        a_larga = _run(duracion_t8_h=12.0).get("min_autonomia_sag1", 0)
        assert a_larga <= a_corta + 1e-6


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
