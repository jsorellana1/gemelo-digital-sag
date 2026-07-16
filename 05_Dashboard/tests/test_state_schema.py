"""test_state_schema.py — normalizacion/versionado de estado persistido
(dcc.Store de sesion y outputs/state/*.json), ver utils/state_schema.py y
04_Reports/Technical/20260714_Persistencia_Estado_Obsoleto.md.
"""
import math

import numpy as np
import pytest

from utils.state_schema import (
    APP_STATE_VERSION, make_envelope, make_json_safe, normalize_persisted_state, get_data,
)

_DEFAULT = {"a": 1, "b": "x"}


class TestNormalizePersistedState:
    def test_none_retorna_default(self):
        out = normalize_persisted_state(None, _DEFAULT, kind="t")
        assert out == {"schema_version": APP_STATE_VERSION, "data": _DEFAULT}

    def test_diccionario_vacio_es_incompatible_por_falta_de_version(self):
        out = normalize_persisted_state({}, _DEFAULT, kind="t")
        assert out["data"] == _DEFAULT

    def test_lista_en_vez_de_diccionario_se_descarta(self):
        out = normalize_persisted_state([1, 2, 3], _DEFAULT, kind="t")
        assert out["data"] == _DEFAULT

    def test_string_se_descarta(self):
        out = normalize_persisted_state("no soy un dict", _DEFAULT, kind="t")
        assert out["data"] == _DEFAULT

    def test_estado_sin_version_se_descarta(self):
        raw = {"data": {"a": 99}}
        out = normalize_persisted_state(raw, _DEFAULT, kind="t")
        assert out["data"] == _DEFAULT

    def test_estado_con_version_antigua_se_descarta(self):
        raw = {"schema_version": APP_STATE_VERSION - 1 if isinstance(APP_STATE_VERSION, int) else "0.0.1",
               "data": {"a": 99}}
        out = normalize_persisted_state(raw, _DEFAULT, kind="t")
        assert out["data"] == _DEFAULT

    def test_estado_con_version_actual_se_conserva(self):
        raw = make_envelope({"a": 99, "b": "y"})
        out = normalize_persisted_state(raw, _DEFAULT, kind="t")
        assert out["data"] == {"a": 99, "b": "y"}

    def test_campos_obligatorios_faltantes_se_descarta(self):
        raw = {"schema_version": APP_STATE_VERSION, "data": {"a": 99}}
        out = normalize_persisted_state(raw, _DEFAULT, required_keys=("a", "b"), kind="t")
        assert out["data"] == _DEFAULT

    def test_campos_opcionales_faltantes_se_completan_con_default(self):
        raw = {"schema_version": APP_STATE_VERSION, "data": {"a": 99}}
        out = normalize_persisted_state(raw, _DEFAULT, kind="t")
        assert out["data"] == {"a": 99, "b": "x"}

    def test_data_no_es_diccionario_se_descarta(self):
        raw = {"schema_version": APP_STATE_VERSION, "data": "no soy un dict"}
        out = normalize_persisted_state(raw, _DEFAULT, kind="t")
        assert out["data"] == _DEFAULT

    def test_nunca_lanza_excepcion(self):
        for corrupto in (None, {}, [], "x", 123, {"schema_version": object()}):
            normalize_persisted_state(corrupto, _DEFAULT, kind="t")  # no debe lanzar

    def test_copia_profunda_no_muta_el_default_compartido(self):
        default = {"lista": [1, 2, 3]}
        out1 = normalize_persisted_state(None, default, kind="t")
        out1["data"]["lista"].append(4)
        out2 = normalize_persisted_state(None, default, kind="t")
        assert out2["data"]["lista"] == [1, 2, 3]

    def test_get_data_devuelve_directamente_el_data(self):
        raw = make_envelope({"a": 5, "b": "z"})
        assert get_data(raw, _DEFAULT, kind="t") == {"a": 5, "b": "z"}

    def test_estado_valido_despues_de_reiniciar_la_app(self):
        # Simula: escribir con make_envelope, "reiniciar" (nueva llamada),
        # volver a leer con normalize_persisted_state — debe sobrevivir.
        persisted = make_envelope({"a": 7, "b": "q"})
        reloaded = normalize_persisted_state(persisted, _DEFAULT, kind="t")
        assert reloaded["data"]["a"] == 7


class TestMakeJsonSafe:
    def test_numpy_float_a_float_nativo(self):
        out = make_json_safe(np.float64(3.5))
        assert out == 3.5
        assert isinstance(out, float)

    def test_numpy_int_a_int_nativo(self):
        out = make_json_safe(np.int64(7))
        assert out == 7
        assert isinstance(out, int)

    def test_nan_se_convierte_a_none(self):
        assert make_json_safe(float("nan")) is None

    def test_inf_se_convierte_a_none(self):
        assert make_json_safe(float("inf")) is None
        assert make_json_safe(float("-inf")) is None

    def test_numpy_array_a_lista(self):
        out = make_json_safe(np.array([1.0, 2.0, 3.0]))
        assert out == [1.0, 2.0, 3.0]
        assert isinstance(out, list)

    def test_dict_anidado_recursivo(self):
        out = make_json_safe({"x": np.float64(1.5), "y": {"z": np.array([1, 2])}})
        assert out == {"x": 1.5, "y": {"z": [1, 2]}}

    def test_datetime_a_iso(self):
        from datetime import datetime
        out = make_json_safe(datetime(2026, 7, 14, 10, 30))
        assert out == "2026-07-14T10:30:00"

    def test_make_envelope_sanitiza_automaticamente(self):
        env = make_envelope({"tph": np.float64(1234.5), "serie": np.array([1.0, float("nan")])})
        assert env["data"]["tph"] == 1234.5
        assert env["data"]["serie"] == [1.0, None]
