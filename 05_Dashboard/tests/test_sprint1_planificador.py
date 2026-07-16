"""test_sprint1_planificador.py — QA 2026-07-06: Sprint 1 de la propuesta
v4.1 (Planificador de Turno, Explicabilidad, Mapa de Cuellos de Botella).
Todas las piezas reusan campos ya calculados por el motor validado — no
introducen relaciones causales nuevas."""
import pytest

from engine.simulator import simulate_scenario
from engine.optimizer_v3 import find_optimal_v3
from engine.explicabilidad import explain_recommendation
from engine.bottleneck import full_bottleneck_map
from engine.turno_planner import build_hourly_schedule

_BASE = dict(
    pila1=55.0, pila2=55.0, duracion_t8=0.0,
    sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
    c315="activa", c316="activa",
    t1_mode="chancado", t1_manual=4000.0,
    t3_frac=0.0, distribucion_t1="proporcional",
    horizonte=24.0, mode="balanced",
)


class TestExplicabilidad:
    def test_incluye_pila_autonomia_t8_y_riesgo(self):
        best, _ = find_optimal_v3(**_BASE)
        bullets = explain_recommendation(best, pila1=55, pila2=55, duracion_t8=0, asset="SAG1")
        texto = " ".join(bullets)
        assert "Pila SAG1" in texto
        assert "Autonomía" in texto
        assert "T8" in texto
        assert "Riesgo de vaciado" in texto

    def test_sag2_usa_campos_de_sag2(self):
        best, _ = find_optimal_v3(**_BASE)
        bullets = explain_recommendation(best, pila1=55, pila2=55, duracion_t8=0, asset="SAG2")
        assert any("SAG2 recomendado" in b for b in bullets)

    def test_sin_t8_indica_sin_ventana(self):
        best, _ = find_optimal_v3(**_BASE)
        bullets = explain_recommendation(best, pila1=55, pila2=55, duracion_t8=0, asset="SAG1")
        assert any("Sin ventana T8" in b for b in bullets)


class TestBottleneckMap:
    def _sim(self, **overrides):
        params = dict(
            pila_sag1_pct=55.0, pila_sag2_pct=55.0,
            rate_sag1_pct=100.0, rate_sag2_pct=100.0,
            duracion_t8_h=0.0,
            correa315_estado="activa", correa316_estado="activa",
            horizonte_horas=24.0, ch1_on=True, ch2_on=True,
        )
        params.update(overrides)
        return simulate_scenario(**params)

    def test_10_componentes_presentes(self):
        sim = self._sim()
        mapa = full_bottleneck_map(sim, ch1_on=True, ch2_on=True,
                                    correa315_estado="activa", correa316_estado="activa")
        nombres = {m["activo"] for m in mapa}
        assert nombres == {"CH1", "CH2", "T1", "CV315", "CV316", "Pila SAG1",
                            "Pila SAG2", "SAG1", "SAG2", "Molinos de bolas"}

    def test_todo_verde_sin_restricciones(self):
        sim = self._sim(pila_sag1_pct=80, pila_sag2_pct=80)
        mapa = full_bottleneck_map(sim, ch1_on=True, ch2_on=True,
                                    correa315_estado="activa", correa316_estado="activa")
        colores = {m["activo"]: m["color"] for m in mapa}
        assert colores["CH1"] == "verde"
        assert colores["CH2"] == "verde"
        assert colores["CV315"] == "verde"
        assert colores["CV316"] == "verde"

    def test_ch2_fuera_es_rojo_con_impacto_estimado(self):
        sim = self._sim(ch2_on=False)
        mapa = full_bottleneck_map(sim, ch1_on=True, ch2_on=False,
                                    correa315_estado="activa", correa316_estado="activa")
        ch2 = next(m for m in mapa if m["activo"] == "CH2")
        assert ch2["color"] == "rojo"
        assert ch2["impacto_tph"] is not None and ch2["impacto_tph"] > 0

    def test_correa_inactiva_es_rojo(self):
        sim = self._sim(correa315_estado="inactiva")
        mapa = full_bottleneck_map(sim, ch1_on=True, ch2_on=True,
                                    correa315_estado="inactiva", correa316_estado="activa")
        cv315 = next(m for m in mapa if m["activo"] == "CV315")
        assert cv315["color"] == "rojo"


class TestTurnoPlanner:
    def test_filas_igual_a_horizonte(self):
        rows = build_hourly_schedule(
            base_hour=8, horizonte_h=12, duracion_t8=0, maint_windows={},
            rate1_tph=1400, rate2_tph=2200, bola1_label="sin_bola", bola2_label="sin_bola",
        )
        assert len(rows) == 12

    def test_mantencion_se_refleja_solo_en_horas_de_ventana(self):
        maint = {"411": (10, 14)}
        rows = build_hourly_schedule(
            base_hour=8, horizonte_h=12, duracion_t8=0, maint_windows=maint,
            rate1_tph=1400, rate2_tph=2200, bola1_label="sin_bola", bola2_label="sin_bola",
        )
        estados = {r["hora_reloj"]: r["411"] for r in rows}
        assert estados["10:00"] == "MANTENCIÓN"
        assert estados["13:00"] == "MANTENCIÓN"
        assert estados["14:00"] == "ON"
        assert estados["08:00"] == "ON"

    def test_sag_completo_en_mantencion_apaga_rate(self):
        maint = {"SAG1": (0, 24)}
        rows = build_hourly_schedule(
            base_hour=0, horizonte_h=4, duracion_t8=0, maint_windows=maint,
            rate1_tph=1400, rate2_tph=2200, bola1_label="sin_bola", bola2_label="sin_bola",
        )
        assert all(r["sag1_tph"] == 0 for r in rows)

    def test_t8_activo_solo_primeras_horas(self):
        rows = build_hourly_schedule(
            base_hour=0, horizonte_h=8, duracion_t8=4, maint_windows={},
            rate1_tph=1400, rate2_tph=2200, bola1_label="sin_bola", bola2_label="sin_bola",
        )
        assert sum(1 for r in rows if r["t8_activo"]) == 4


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
