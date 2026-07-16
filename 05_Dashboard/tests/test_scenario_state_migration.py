"""test_scenario_state_migration.py — Prueba de persistencia antigua
simulada (causa raiz real del bug 'grafico en blanco tras reiniciar/
actualizar', ver 04_Reports/Technical/20260714_Persistencia_Estado_
Obsoleto.md): un outputs/state/last_scenario.json escrito por una version
anterior de la app (sin schema_version, formato "pelado") no debe
precargarse silenciosamente en los controles.
"""
import json
import os

import pytest

import utils.scenario_state as scenario_state


@pytest.fixture
def estado_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(scenario_state, "_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(scenario_state, "_STATE_PATH", str(tmp_path / "last_scenario.json"))
    return tmp_path


class TestScenarioStateMigration:
    def test_sin_archivo_retorna_none(self, estado_dir):
        assert scenario_state.load_last_scenario() is None

    def test_archivo_legacy_sin_schema_version_se_descarta(self, estado_dir):
        # Formato "pelado" tal como lo escribia la version anterior de la
        # app (antes de este cambio) — sin envelope, sin schema_version,
        # con un duracion_t8 que ya no es una de las 5 opciones fijas
        # actuales del control (ver rediseno JdS 2026-07-13).
        legacy = {
            "pila1": 40, "pila2": 62, "duracion_t8": 6,  # 6h ya no es opcion valida
            "rate1_tph": 1300, "rate2_tph": 2100,
            "bolas_sag1": "solo_411", "bolas_sag2": "solo_511", "turno": "B",
            "_timestamp_epoch": 1000.0, "_timestamp_str": "2026-01-01 00:00:00",
        }
        with open(scenario_state._STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(legacy, f)

        resultado = scenario_state.load_last_scenario()
        assert resultado is None, (
            "Un archivo de una version anterior (sin schema_version) se "
            "trato como valido en vez de descartarse — precargaria "
            "duracion_t8=6, que ya no es una de las 5 opciones fijas."
        )

    def test_guardar_y_cargar_estado_vigente_funciona(self, estado_dir):
        scenario_state.save_last_scenario({
            "pila1": 45, "pila2": 58, "duracion_t8": 4,
            "rate1_tph": 1200, "rate2_tph": 2200,
            "bolas_sag1": "solo_412", "bolas_sag2": "solo_512", "turno": "A",
        })
        resultado = scenario_state.load_last_scenario()
        assert resultado is not None
        assert resultado["pila1"] == 45
        assert resultado["duracion_t8"] == 4
        assert "horas_desde" in resultado

    def test_archivo_corrupto_no_lanza_excepcion(self, estado_dir):
        with open(scenario_state._STATE_PATH, "w", encoding="utf-8") as f:
            f.write("{esto no es json valido")
        assert scenario_state.load_last_scenario() is None

    def test_archivo_con_data_faltante_se_descarta(self, estado_dir):
        # schema_version correcto, pero sin 'pila1'/'pila2'/'duracion_t8'
        # requeridos.
        from utils.state_schema import APP_STATE_VERSION
        raw = {"schema_version": APP_STATE_VERSION, "data": {"turno": "A"}}
        with open(scenario_state._STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(raw, f)
        assert scenario_state.load_last_scenario() is None
