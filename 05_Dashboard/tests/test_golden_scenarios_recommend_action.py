"""
test_golden_scenarios_recommend_action.py — Validacion del motor de
recomendaciones contra escenarios donde la accion correcta es conocida
de antemano (seccion 29 del programa de validacion estadistica pedido,
ver 04_Reports/Technical/Validacion_Motor_Recomendaciones.md).

No modifica rules_engine.py -- solo documenta, con evidencia ejecutable,
que comportamiento tiene HOY recommend_action frente a 5 escenarios
canonicos. 4/5 escenarios coinciden con la accion esperada; el caso 3
(SAG apagado + pila llenando) expone un gap real (sin deteccion de
riesgo de overflow) -- se deja como xfail documentado, no se oculta.
"""
from __future__ import annotations

import re

import pytest

from engine.circuit_state import AutonomyContext, FILLING, DRAINING, STABLE
from engine.rules_engine import recommend_action


def _ctx(status, hours, rate, hist_hours, vuln, div="CONSISTENT") -> AutonomyContext:
    return AutonomyContext(
        dynamic_hours=hours, dynamic_status=status, dynamic_net_rate_tph=rate,
        historical_hours=hist_hours, historical_vulnerability=vuln, divergence_class=div,
    )


_NEUTRO = _ctx(STABLE, 5.0, 0.0, 5.0, "BAJA")


class TestEscenariosDoradosSeccion29:
    """5 escenarios literales de la seccion 29 del prompt de validacion
    estadistica. Cada test documenta la accion ESPERADA segun el
    dominio (no segun el codigo) y compara contra el comportamiento
    real de recommend_action."""

    def test_caso1_pila_baja_llenando_espera_monitorear(self):
        ctx1 = _ctx(FILLING, None, -300.0, 1.2, "ALTA")
        accion, exp = recommend_action(
            autonomia_sag1=1.2, autonomia_sag2=5.0, pile_sag1_pct=15.0, pile_sag2_pct=50.0,
            t8_activo=False, duracion_t8_h=0.0,
            autonomy_context_sag1=ctx1, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "MONITOREAR"

    def test_caso2_pila_alta_drenando_rapido_espera_reducir_carga(self):
        ctx2 = _ctx(DRAINING, 2.0, 800.0, 3.0, "MEDIA")
        accion, exp = recommend_action(
            autonomia_sag1=3.0, autonomia_sag2=5.0, pile_sag1_pct=60.0, pile_sag2_pct=50.0,
            t8_activo=True, duracion_t8_h=4.0,
            autonomy_context_sag1=ctx2, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "REDUCIR_CARGA"

    @pytest.mark.xfail(
        reason="GAP CONFIRMADO (2026-07-15, ver Validacion_Motor_Recomendaciones.md): "
               "recommend_action no detecta riesgo de overflow cuando un SAG esta "
               "apagado y la pila sube hacia el limite. Hoy retorna OPERACION_NORMAL. "
               "No se corrige en esta pasada -- requiere decision de producto sobre "
               "una nueva accion (ej. 'RIESGO_OVERFLOW') fuera del alcance de este test.",
        strict=True,
    )
    def test_caso3_sag_off_alimentacion_activa_espera_riesgo_overflow(self):
        accion, exp = recommend_action(
            autonomia_sag1=3.0, autonomia_sag2=8.0, pile_sag1_pct=96.0, pile_sag2_pct=50.0,
            t8_activo=False, sag1_activo=False, sag2_activo=True,
            rate_sag1_tph=0.0, rate_sag2_tph=2000.0,
        )
        # Comportamiento actual: "OPERACION_NORMAL". Se documenta el
        # comportamiento DESEADO en el assert (falla a proposito).
        assert accion in ("EMERGENCIA", "REDUCIR_CARGA", "EVALUAR_DETENCION"), (
            f"Se esperaba una accion que refleje riesgo de overflow, se obtuvo '{accion}': {exp}"
        )

    def test_caso4_agotamiento_antes_de_fin_ventana_espera_accion_cuantificada(self):
        ctx4 = _ctx(DRAINING, 0.3, 1200.0, 1.0, "CRITICA")
        accion, exp = recommend_action(
            autonomia_sag1=1.0, autonomia_sag2=5.0, pile_sag1_pct=20.0, pile_sag2_pct=50.0,
            t8_activo=True, duracion_t8_h=4.0,
            autonomy_context_sag1=ctx4, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "EMERGENCIA"
        # "Cuantificada": el mensaje debe traer una tasa (t/h) y un tiempo (min/h), no solo texto generico.
        assert re.search(r"\d+\s*t/h", exp), f"Explicacion sin tasa cuantificada: {exp}"
        assert re.search(r"\d+\s*(min|h)\b", exp), f"Explicacion sin tiempo cuantificado: {exp}"

    def test_caso5_ventana_termina_antes_del_critico_espera_mantener_monitorear(self):
        ctx5 = _ctx(DRAINING, 6.0, 150.0, 6.0, "BAJA")
        accion, exp = recommend_action(
            autonomia_sag1=6.0, autonomia_sag2=5.0, pile_sag1_pct=40.0, pile_sag2_pct=50.0,
            t8_activo=True, duracion_t8_h=4.0,
            autonomy_context_sag1=ctx5, autonomy_context_sag2=_NEUTRO,
        )
        assert accion in ("MONITOREAR", "OPERACION_NORMAL")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
