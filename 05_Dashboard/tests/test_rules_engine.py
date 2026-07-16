"""test_rules_engine.py — Fase 4 QA: reglas operacionales (R16, regimen,
mantenciones, autonomia/vaciado-overflow).
"""
import pytest

from engine.rules_engine import determine_regime, recommend_action
from engine.ode_model import compute_autonomia
from engine.scheduler import (
    equipos_en_mantencion, r16_conflicto_mantencion,
    sag_forzado_off, bola_opts_restringidas,
)
from engine.circuit_state import AutonomyContext


class TestR16MolinosDeBolas:
    def test_r16_conflicto_cuando_411_y_412_en_mantencion(self):
        en_mant = {"411", "412"}
        assert r16_conflicto_mantencion(en_mant, "SAG1") is True

    def test_r16_sin_conflicto_si_solo_uno_en_mantencion(self):
        en_mant = {"411"}
        assert r16_conflicto_mantencion(en_mant, "SAG1") is False

    def test_r16_no_afecta_sag_distinto(self):
        en_mant = {"411", "412"}
        assert r16_conflicto_mantencion(en_mant, "SAG2") is False

    def test_bola_opts_restringidas_excluye_opciones_con_molino_en_mantencion(self):
        base_opts = ["sin_bola", "solo_411", "solo_412", "ambas_411_412"]
        en_mant = {"411"}
        opts = bola_opts_restringidas(base_opts, en_mant, "SAG1")
        assert "solo_411" not in opts
        assert "ambas_411_412" not in opts
        assert "sin_bola" in opts

    def test_sag_forzado_off_si_sag_completo_en_mantencion(self):
        assert sag_forzado_off("SAG1", {"SAG1"}) is True
        assert sag_forzado_off("SAG1", {"SAG2"}) is False


class TestMantencionesSimultaneas:
    def test_equipos_en_mantencion_detecta_ventana_activa(self):
        maint_windows = {"411": (8, 16)}
        activos = equipos_en_mantencion(maint_windows, now_hour=10)
        assert "411" in activos

    def test_equipos_en_mantencion_fuera_de_ventana(self):
        maint_windows = {"411": (8, 16)}
        activos = equipos_en_mantencion(maint_windows, now_hour=20)
        assert "411" not in activos

    def test_equipos_sin_ventana_no_aparecen(self):
        maint_windows = {"411": None}
        activos = equipos_en_mantencion(maint_windows, now_hour=10)
        assert "411" not in activos

    def test_ventana_dia_completo_0_24_se_detecta_activa(self):
        """Regression QA 2026-07-06: [0,24] (RangeSlider a fondo, min=0/max=24)
        representa mantencion todo el dia y NO debe ser tratada como
        'sin ventana' solo porque 24 % 24 == 0 == ini."""
        maint_windows = {"411": (0.0, 24.0)}
        for h in (0, 6, 12, 18, 23.9):
            assert "411" in equipos_en_mantencion(maint_windows, now_hour=h), (
                f"hora {h} deberia estar dentro de la ventana de dia completo"
            )


class TestRegimenOperacional:
    def test_autonomia_baja_fuerza_emergencia(self):
        regime, bounds = determine_regime(pile_pct=25.0, autonomia_h=0.5, t8_activo=False, asset="SAG1")
        assert regime == "EMERGENCIA"

    def test_autonomia_media_pila_baja_fuerza_conservador(self):
        regime, bounds = determine_regime(pile_pct=15.0, autonomia_h=3.0, t8_activo=False, asset="SAG1")
        assert regime == "CONSERVADOR"

    def test_t8_activo_pila_alta_permite_agresivo(self):
        regime, bounds = determine_regime(pile_pct=60.0, autonomia_h=5.0, t8_activo=True, asset="SAG1")
        assert regime == "AGRESIVO"

    def test_bounds_estan_en_rango_0_100(self):
        _, bounds = determine_regime(pile_pct=50.0, autonomia_h=3.0, t8_activo=False, asset="SAG2")
        assert 0.0 <= bounds[0] <= bounds[1] <= 105.0


class TestAutonomiaVaciadoOverflow:
    def test_autonomia_cero_en_zona_critica_o_bajo(self):
        auton = compute_autonomia(pile_pct=5.0, asset="SAG1")
        assert auton == 0.0, "pila bajo el umbral critico debe dar autonomia 0 (vaciado), nunca negativa"

    def test_autonomia_positiva_sobre_umbral_critico(self):
        auton = compute_autonomia(pile_pct=80.0, asset="SAG1")
        assert auton > 0.0

    def test_autonomia_mayor_con_mas_pila(self):
        a_baja = compute_autonomia(pile_pct=30.0, asset="SAG2")
        a_alta = compute_autonomia(pile_pct=80.0, asset="SAG2")
        assert a_alta > a_baja, "mas inventario en pila debe dar mas autonomia, nunca menos"


def _ctx(status, hours, rate, hist_hours, vuln, div="CONSISTENT"):
    return AutonomyContext(
        dynamic_hours=hours, dynamic_status=status, dynamic_net_rate_tph=rate,
        historical_hours=hist_hours, historical_vulnerability=vuln, divergence_class=div,
    )


# Contexto "neutro" para el SAG que no es el foco del caso de prueba:
# STABLE, vulnerabilidad BAJA — no dispara ninguna regla nueva por si solo.
_NEUTRO = _ctx("STABLE", None, 0.0, 8.0, "BAJA", "EXPECTED_CONTEXT_DIFFERENCE")


class TestRecommendActionAutonomyContext:
    """Etapa 2 del reencuadre de autonomía (2026-07-15). Ver
    04_Reports/Technical/20260715_Migracion_Autonomia_Etapa2.md."""

    def test_filling_con_vulnerabilidad_critica_no_produce_detencion(self):
        """Caso 1: pila baja pero llenándose ahora -> MONITOREAR, nunca
        EVALUAR_DETENCION/EMERGENCIA solo por la histórica baja."""
        ctx1 = _ctx("FILLING", None, -163.0, 0.3, "CRITICA", "EXPECTED_CONTEXT_DIFFERENCE")
        accion, exp = recommend_action(
            autonomia_sag1=0.3, autonomia_sag2=8.0, pile_sag1_pct=25.0, pile_sag2_pct=55.0,
            t8_activo=False, sag1_activo=True, sag2_activo=True,
            autonomy_context_sag1=ctx1, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "MONITOREAR"
        assert "vulnerabilidad preventiva critica" in exp.lower()

    def test_draining_con_autonomia_dinamica_critica_produce_emergencia(self):
        """Caso 2."""
        ctx1 = _ctx("DRAINING", 0.3, 1200.0, 0.36, "CRITICA")
        accion, exp = recommend_action(
            autonomia_sag1=0.36, autonomia_sag2=8.0, pile_sag1_pct=20.0, pile_sag2_pct=55.0,
            t8_activo=False, sag1_activo=True, sag2_activo=True,
            autonomy_context_sag1=ctx1, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "EMERGENCIA"
        assert "1200" in exp

    def test_draining_con_tiempo_menor_a_ventana_restante_reduce_carga(self):
        """Caso 3: horas dinamicas >= 1.0h pero menores a la ventana T8
        restante -> REDUCIR_CARGA, cuantificado."""
        ctx1 = _ctx("DRAINING", 2.4, 1454.0, 3.2, "MEDIA")
        accion, exp = recommend_action(
            autonomia_sag1=3.2, autonomia_sag2=8.0, pile_sag1_pct=70.0, pile_sag2_pct=70.0,
            t8_activo=True, sag1_activo=True, sag2_activo=True, duracion_t8_h=6.0,
            autonomy_context_sag1=ctx1, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "REDUCIR_CARGA"
        assert "1454" in exp and "6.0h" in exp

    def test_stable_con_vulnerabilidad_critica(self):
        """Caso 4."""
        ctx1 = _ctx("STABLE", None, 0.5, 0.4, "CRITICA", "EXPECTED_CONTEXT_DIFFERENCE")
        accion, exp = recommend_action(
            autonomia_sag1=0.4, autonomia_sag2=8.0, pile_sag1_pct=18.0, pile_sag2_pct=55.0,
            t8_activo=False, sag1_activo=True, sag2_activo=True,
            autonomy_context_sag1=ctx1, autonomy_context_sag2=_NEUTRO,
        )
        assert accion in ("MONITOREAR", "CONSERVADOR")
        assert "colchon" in exp.lower() or "colchón" in exp.lower()

    def test_sag_off_no_dispara_reglas_dinamicas_nuevas(self):
        """Caso 5: SAG_OFF no coincide con ninguna de las reglas nuevas
        (crítico/DRAINING/FILLING+vuln/STABLE+vuln) -> cae al fallback
        legacy sin romper."""
        ctx1 = _ctx("SAG_OFF", None, 0.0, 5.0, "BAJA", "EXPECTED_CONTEXT_DIFFERENCE")
        accion, exp = recommend_action(
            autonomia_sag1=5.0, autonomia_sag2=8.0, pile_sag1_pct=60.0, pile_sag2_pct=70.0,
            t8_activo=False, sag1_activo=True, sag2_activo=True,
            autonomy_context_sag1=ctx1, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "OPERACION_NORMAL"

    def test_pila_ya_bajo_critico_dinamico_produce_emergencia(self):
        """Caso 6."""
        ctx1 = _ctx("AT_CRITICAL_LEVEL", 0.0, 900.0, 0.2, "CRITICA")
        accion, exp = recommend_action(
            autonomia_sag1=0.2, autonomia_sag2=8.0, pile_sag1_pct=14.0, pile_sag2_pct=55.0,
            t8_activo=False, sag1_activo=True, sag2_activo=True,
            autonomy_context_sag1=ctx1, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "EMERGENCIA"
        assert "nivel crítico ahora" in exp.lower() or "nivel critico ahora" in exp.lower()

    def test_recomendacion_cuantificada_incluye_balance_y_horas(self):
        """Caso 7: el mensaje para DRAINING trae balance neto, horas
        dinámicas y la comparación con la histórica, no solo un texto
        genérico."""
        ctx1 = _ctx("DRAINING", 0.7, 500.0, 0.5, "ALTA")
        accion, exp = recommend_action(
            autonomia_sag1=0.5, autonomia_sag2=8.0, pile_sag1_pct=30.0, pile_sag2_pct=60.0,
            t8_activo=False, sag1_activo=True, sag2_activo=True,
            autonomy_context_sag1=ctx1, autonomy_context_sag2=_NEUTRO,
        )
        assert accion == "EVALUAR_DETENCION"
        assert "500" in exp
        assert "histórica" in exp or "historica" in exp

    def test_compatibilidad_sin_autonomy_context_es_identica_a_legacy(self):
        """Caso 15: sin `autonomy_context_sag1/2`, el resultado es
        exactamente el mismo que antes de la Etapa 2 (comportamiento
        legacy congelado, comparado explícitamente)."""
        casos_y_esperado = [
            (dict(autonomia_sag1=0.3, autonomia_sag2=5.0, pile_sag1_pct=20.0, pile_sag2_pct=50.0,
                  t8_activo=False),
             ("EMERGENCIA", "[!!] SAG1 = 18 min: EMERGENCIA. Reducir carga al minimo inmediatamente.")),
            (dict(autonomia_sag1=0.8, autonomia_sag2=5.0, pile_sag1_pct=25.0, pile_sag2_pct=50.0,
                  t8_activo=False),
             ("EVALUAR_DETENCION", "SAG1 bajo 1h (48 min). Evaluar detencion parcial.")),
            (dict(autonomia_sag1=3.0, autonomia_sag2=10.0, pile_sag1_pct=70.0, pile_sag2_pct=70.0,
                  t8_activo=False),
             ("OPERACION_NORMAL", "Condiciones normales. SAG1(70%): 3.0h OK | SAG2(70%): 10.0h OK")),
        ]
        for kwargs, esperado in casos_y_esperado:
            assert recommend_action(**kwargs) == esperado

    def test_suite_no_regresiona_en_casos_legacy_existentes(self):
        """Caso 18 (parcial, a nivel de este módulo): los tests legacy de
        TestRegimenOperacional/TestAutonomiaVaciadoOverflow siguen
        cubiertos por la suite completa (`pytest tests -q`) — este test
        solo confirma que `recommend_action` sigue siendo importable y
        ejecutable con la firma extendida sin argumentos nuevos."""
        accion, exp = recommend_action(
            autonomia_sag1=3.0, autonomia_sag2=10.0, pile_sag1_pct=70.0, pile_sag2_pct=70.0,
            t8_activo=False)
        assert accion == "OPERACION_NORMAL"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
