"""test_bottleneck_and_stats.py — QA 2026-07-06: detector de cuello de
botella (engine.bottleneck) y estadisticas historicas reales
(engine.production_stats), parte del reenfoque hacia produccion sostenible
(sin relaciones causales TPH-ley no demostradas)."""
import pytest

from engine.simulator import simulate_scenario
from engine.bottleneck import (
    detect_bottleneck, full_bottleneck_map,
    STOCKPILE_DYNAMIC_DEPLETION, STOCKPILE_LOW_BUFFER, SAG_OFF, BALL_MILL_CAPACITY,
)
from engine.production_stats import get_asset_stats, get_all_stats


class TestProductionStats:
    def test_sag1_sag2_tienen_stats_reales(self):
        stats = get_all_stats()
        assert "SAG1" in stats and "SAG2" in stats
        assert stats["SAG1"]["n_dias"] > 100
        assert stats["SAG2"]["n_dias"] > 100

    def test_sag1_mas_variable_que_sag2(self):
        """Hallazgo real (2026-07-06): SAG1 es estructuralmente mas
        variable que SAG2, consistente con drain_pct_h asimetrico ya
        calibrado (23.76%/h vs 6.18%/h)."""
        s1 = get_asset_stats("SAG1")
        s2 = get_asset_stats("SAG2")
        assert s1["cv"] > s2["cv"]

    def test_percentiles_ordenados(self):
        for asset in ("SAG1", "SAG2", "MCONV", "MUN"):
            s = get_asset_stats(asset)
            assert s["p10_ton_dia"] <= s["p50_ton_dia"] <= s["p90_ton_dia"]

    def test_asset_desconocido_retorna_vacio(self):
        assert get_asset_stats("NO_EXISTE") == {}


class TestBottleneckDetector:
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

    def test_sin_restriccion_no_detecta_cuello_de_botella(self):
        sim = self._sim(pila_sag1_pct=80, pila_sag2_pct=80)
        r = detect_bottleneck(sim, ch1_on=True, ch2_on=True,
                               correa315_estado="activa", correa316_estado="activa")
        assert r["activo"] is None

    def test_ch2_fuera_detecta_chancado_como_restriccion(self):
        sim = self._sim(ch2_on=False)
        r = detect_bottleneck(sim, ch1_on=True, ch2_on=False,
                               correa315_estado="activa", correa316_estado="activa")
        # puede haber autonomia critica tambien, pero el chancado debe aparecer
        activos = [r["activo"]] + [c["activo"] for c in r.get("otros", [])]
        assert any("Chancado" in a for a in activos)

    def test_correa315_inactiva_detecta_cv315(self):
        sim = self._sim(correa315_estado="inactiva")
        r = detect_bottleneck(sim, ch1_on=True, ch2_on=True,
                               correa315_estado="inactiva", correa316_estado="activa")
        activos = [r["activo"]] + [c["activo"] for c in r.get("otros", [])]
        assert any("CV315" in a for a in activos)
        assert r["severidad"] in ("alta", "media")

    def test_pila_baja_detecta_autonomia_como_prioritaria(self):
        sim = self._sim(pila_sag1_pct=16, duracion_t8_h=8)
        r = detect_bottleneck(sim, ch1_on=True, ch2_on=True,
                               correa315_estado="activa", correa316_estado="activa")
        assert "Pila SAG1" in r["activo"]
        assert r["severidad"] == "alta"


class TestBottleneckCategoria:
    """Fase 1.2 del roadmap de cierre (2026-07-15): distinguir
    STOCKPILE_DYNAMIC_DEPLETION (drenando ahora) de STOCKPILE_LOW_BUFFER
    (vulnerable pero recuperándose/estable), sin cambiar severidad ni
    color ya testeados — es un campo aditivo."""

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

    def test_pila_con_momento_critico_pero_recuperada_es_low_buffer(self):
        """El escenario ya cubierto por test_pila_baja_detecta_autonomia_
        como_prioritaria (pila_sag1_pct=16, duracion_t8_h=8) termina con
        dynamic_status=FILLING pese al mínimo crítico durante el
        trayecto — severidad se mantiene 'alta' (riesgo real que
        ocurrió), pero la categoría debe reflejar que ya no está
        drenando activamente."""
        sim = self._sim(pila_sag1_pct=16, duracion_t8_h=8)
        assert sim["dynamic_net_autonomy_sag1_status"] == "FILLING"
        r = detect_bottleneck(sim, ch1_on=True, ch2_on=True,
                               correa315_estado="activa", correa316_estado="activa")
        assert r["activo"] == "Pila SAG1 (inventario)"
        assert r["severidad"] == "alta"
        assert r["categoria"] == STOCKPILE_LOW_BUFFER
        assert "recuperándose" in r["motivo"]

    def test_pila_drenando_activamente_es_dynamic_depletion(self):
        sim = self._sim(pila_sag1_pct=45.0, pila_sag2_pct=45.0, duracion_t8_h=4, horizonte_horas=4,
                         correa315_estado="inactiva", correa316_estado="inactiva")
        assert sim["dynamic_net_autonomy_sag2_status"] == "DRAINING"
        r = detect_bottleneck(sim, ch1_on=True, ch2_on=True,
                               correa315_estado="inactiva", correa316_estado="inactiva")
        activos = {c.get("activo"): c for c in [r] + r.get("otros", [])}
        assert activos["Pila SAG2 (inventario)"]["categoria"] == STOCKPILE_DYNAMIC_DEPLETION

    def test_full_bottleneck_map_incluye_categoria_en_todos_los_activos(self):
        sim = self._sim()
        mapa = full_bottleneck_map(sim, ch1_on=True, ch2_on=True,
                                    correa315_estado="activa", correa316_estado="activa")
        assert all("categoria" in item for item in mapa)

    def test_sag_apagado_categoria_sag_off(self):
        sim = self._sim(sag1_activo=False)
        mapa = full_bottleneck_map(sim, ch1_on=True, ch2_on=True,
                                    correa315_estado="activa", correa316_estado="activa")
        sag1_item = next(item for item in mapa if item["activo"] == "SAG1")
        assert sag1_item["categoria"] == SAG_OFF


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
