"""test_ui_response_time.py — SLA de 3 segundos (Requisito 5/7, Skill
UX/UI v3, 2026-07-07).

Hallazgo real de esta sesion (medido, no supuesto): existen DOS rutas
de computo detras de la UI, con presupuestos de tiempo muy distintos:

  1. "Vista rapida" (KPI strip, Actual vs Recomendado con heuristica,
     grafico principal) — corre sobre simulate_scenario_cached, una
     integracion ODE determinista SIN busqueda en grilla. Medido:
     ~300-800ms en frio, <5ms si el escenario ya se vio en la sesion.
     CUMPLE el SLA de 3s con margen.

  2. "Optimo segun pila" / find_optimal_v3 (grilla determinista +
     Monte Carlo adaptativo + re-ranking V4) — es lo que corre el boton
     "GENERAR RECOMENDACION" (encadenado). Medido: 4.0-9.5s en frio por
     escenario nuevo, incluso con el cache de escenarios ya activo.
     NO CUMPLE el SLA de 3s. Esto es un hallazgo arquitectonico real,
     no un bug puntual — la busqueda de grilla + MC adaptativo (30-500
     muestras, ver engine/optimizer_v2.py) es inherentemente mas cara
     que una integracion ODE unica.

Por eso el Requisito 9 (Vista rapida vs avanzada) del skill separa
ambas rutas explicitamente. Esta suite refleja esa separacion: valida
el SLA de 3s SOLO sobre la ruta que el propio skill define como
"Vista rapida" (Requisito 9), y DOCUMENTA (sin asserts falsos) el
tiempo real de la ruta de optimizacion completa, que queda fuera del
SLA por diseño hasta que se implemente el fallback progresivo
(Requisito 8, backlog — NO implementado en esta sesion, ver
20260707_Template_TDA_Mapping.md).
"""
from __future__ import annotations

import time

import pytest

from engine.simulator import simulate_scenario_cached
from engine.optimizer_v3 import find_optimal_v3

SLA_MS = 3000.0

CASOS = {
    "caso1_normal": dict(pila1=80, pila2=80, duracion_t8=0, ch1_on=True, ch2_on=True,
                          c315="activa", c316="activa"),
    "caso2_t8_corta": dict(pila1=50, pila2=50, duracion_t8=4, ch1_on=True, ch2_on=True,
                            c315="activa", c316="activa"),
    "caso3_t8_larga": dict(pila1=25, pila2=25, duracion_t8=12, ch1_on=True, ch2_on=True,
                            c315="activa", c316="activa"),
    "caso4_mantencion": dict(pila1=55, pila2=55, duracion_t8=0, ch1_on=True, ch2_on=False,
                              c315="reducida", c316="activa"),
}


def _time_ms(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000.0


class TestVistaRapidaSLA:
    """SLA de 3s — ruta real detras de KPI strip / Actual vs Recomendado
    (heuristica) / grafico principal en pages/simulador_operacional.py
    ::update_simulation. Escenario NUEVO por caso (sin cache tibio) —
    peor caso real, no el mejor caso."""

    @pytest.mark.parametrize("nombre,params", list(CASOS.items()))
    def test_simulate_scenario_bajo_sla(self, nombre, params):
        dt = _time_ms(lambda: simulate_scenario_cached(
            pila_sag1_pct=params["pila1"] + 0.001,  # +0.001 evita cache de otros tests
            pila_sag2_pct=params["pila2"],
            rate_sag1_pct=100, rate_sag2_pct=100,
            duracion_t8_h=params["duracion_t8"], horizonte_horas=24,
            ch1_on=params["ch1_on"], ch2_on=params["ch2_on"],
            correa315_estado=params["c315"], correa316_estado=params["c316"],
        ))
        assert dt < SLA_MS, (
            f"{nombre}: simulate_scenario_cached tardo {dt:.0f}ms, excede el SLA de {SLA_MS:.0f}ms "
            f"para la ruta 'Vista rapida'"
        )


class TestOptimizadorCompletoDocumentado:
    """NO es parte del SLA de 3s (Requisito 9: la busqueda de grilla +
    Monte Carlo pertenece a 'Vista avanzada'). Se documenta el tiempo
    real con un techo de sanidad generoso (20s) para detectar
    regresiones severas, sin fingir que cumple un SLA que
    arquitectonicamente no puede cumplir hoy."""

    TECHO_SANIDAD_MS = 20000.0

    @pytest.mark.parametrize("nombre,params", list(CASOS.items()))
    def test_find_optimal_v3_documentado(self, nombre, params, capsys):
        dt = _time_ms(lambda: find_optimal_v3(
            pila1=params["pila1"] + 0.002, pila2=params["pila2"], duracion_t8=params["duracion_t8"],
            sag1_on=True, sag2_on=True,
            ch1_on=params["ch1_on"], ch2_on=params["ch2_on"],
            c315=params["c315"], c316=params["c316"],
            t1_mode="chancado", t1_manual=4000, t3_frac=0, distribucion_t1="proporcional",
            horizonte=24,
        ))
        with capsys.disabled():
            print(f"\n  [DOCUMENTADO] {nombre}: find_optimal_v3 = {dt:.0f}ms "
                  f"(SLA 3s NO aplica, ver Requisito 9 — 'Vista avanzada')")
        assert dt < self.TECHO_SANIDAD_MS, (
            f"{nombre}: find_optimal_v3 tardo {dt:.0f}ms — supera incluso el techo de sanidad "
            f"de {self.TECHO_SANIDAD_MS:.0f}ms, posible regresion severa (no solo el gap de SLA ya conocido)"
        )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
