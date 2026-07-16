"""test_operational_validation.py — cierre de brechas "Validación
Operacional Real" (2026-07-07): usage_logger (adopción/NO REGISTRADA),
operational_case_logger (biblioteca de casos, nunca sobreescribe) y
decisions_log (dataset de decisiones + seguimiento posterior).

Todos los paths de escritura se redirigen a tmp_path via monkeypatch —
no deben tocar los logs/datos reales del proyecto."""
import json

import pytest


class TestUsageLoggerAdopcion:
    def _log_path(self, tmp_path, monkeypatch):
        import utils.usage_logger as ul
        path = tmp_path / "usage.jsonl"
        monkeypatch.setattr(ul, "_LOG_PATH", str(path))
        monkeypatch.setattr(ul, "_session_id", None)
        monkeypatch.setattr(ul, "_session_start", None)
        return ul

    def test_recomendacion_sin_feedback_es_no_registrada(self, tmp_path, monkeypatch):
        ul = self._log_path(tmp_path, monkeypatch)
        ul.log_event("recomendacion_generada", regimen_activo="t8_corta", rec_id="r1", usuario="juan")
        sesiones = ul.read_sessions()
        assert len(sesiones) == 1
        assert sesiones[0]["recomendaciones_aceptadas"] == ["NO REGISTRADA"]

    def test_recomendacion_con_feedback_se_empareja_por_rec_id(self, tmp_path, monkeypatch):
        ul = self._log_path(tmp_path, monkeypatch)
        ul.log_event("recomendacion_generada", regimen_activo="t8_corta", rec_id="r1", usuario="juan")
        ul.log_event("recomendacion_feedback", rec_id="r1", recomendacion_aceptada="SI", usuario="juan")
        sesiones = ul.read_sessions()
        assert sesiones[0]["recomendaciones_aceptadas"] == ["SI"]

    def test_adopcion_global_sin_datos_no_inventa_porcentaje(self, tmp_path, monkeypatch):
        ul = self._log_path(tmp_path, monkeypatch)
        resumen = ul.adopcion_global()
        assert resumen["total"] == 0
        assert resumen["pct_aceptacion"] is None

    def test_adopcion_global_calcula_pct_real(self, tmp_path, monkeypatch):
        ul = self._log_path(tmp_path, monkeypatch)
        ul.log_event("recomendacion_generada", rec_id="r1", usuario="juan")
        ul.log_event("recomendacion_feedback", rec_id="r1", recomendacion_aceptada="SI", usuario="juan")
        ul.log_event("recomendacion_generada", rec_id="r2", usuario="juan")
        ul.log_event("recomendacion_feedback", rec_id="r2", recomendacion_aceptada="NO", usuario="juan")
        resumen = ul.adopcion_global()
        assert resumen["total"] == 2
        assert resumen["pct_aceptacion"] == 50.0

    def test_usuario_se_registra_en_la_sesion(self, tmp_path, monkeypatch):
        ul = self._log_path(tmp_path, monkeypatch)
        ul.log_event("simulacion_disparada", usuario="maria", vista_activa="simulador_operacional")
        sesiones = ul.read_sessions()
        assert sesiones[0]["usuario"] == "maria"


class TestOperationalCaseLogger:
    def _cases_dir(self, tmp_path, monkeypatch):
        import utils.operational_case_logger as ocl
        monkeypatch.setattr(ocl, "_CASES_DIR", str(tmp_path / "operational_cases"))
        return ocl

    def test_guardar_caso_retorna_case_id(self, tmp_path, monkeypatch):
        ocl = self._cases_dir(tmp_path, monkeypatch)
        case_id = ocl.save_operational_case({"pila_sag1_pct": 55, "regimen": "t8_corta"})
        assert case_id is not None
        assert len(case_id) == 8

    def test_dos_casos_no_se_sobreescriben(self, tmp_path, monkeypatch):
        ocl = self._cases_dir(tmp_path, monkeypatch)
        id1 = ocl.save_operational_case({"regimen": "t8_corta"})
        id2 = ocl.save_operational_case({"regimen": "overflow"})
        casos = ocl.list_operational_cases()
        assert len(casos) == 2
        assert {c["case_id"] for c in casos} == {id1, id2}

    def test_snapshot_persistido_conserva_los_datos(self, tmp_path, monkeypatch):
        ocl = self._cases_dir(tmp_path, monkeypatch)
        ocl.save_operational_case({"regimen": "inventario_critico", "pila_sag1_pct": 18.0})
        casos = ocl.list_operational_cases()
        assert casos[0]["pila_sag1_pct"] == 18.0
        assert casos[0]["regimen"] == "inventario_critico"


class TestDecisionsLog:
    def _decisions_paths(self, tmp_path, monkeypatch):
        import utils.decisions_log as dl
        monkeypatch.setattr(dl, "_DECISIONS_DIR", str(tmp_path / "Operational_Decisions"))
        monkeypatch.setattr(dl, "_DECISIONS_PATH", str(tmp_path / "Operational_Decisions" / "decisions_log.csv"))
        return dl

    def test_append_decision_crea_fila_con_seguimiento_vacio(self, tmp_path, monkeypatch):
        dl = self._decisions_paths(tmp_path, monkeypatch)
        dl.append_decision("c1", "2026-07-07 10:00:00", "t8_corta", "recomendacion X")
        df = dl.read_decisions()
        assert len(df) == 1
        assert df.iloc[0]["case_id"] == "c1"
        assert df.iloc[0]["accion_tomada"] == ""

    def test_update_followup_sobre_case_id_inexistente_retorna_false(self, tmp_path, monkeypatch):
        dl = self._decisions_paths(tmp_path, monkeypatch)
        dl.append_decision("c1", "2026-07-07 10:00:00", "t8_corta", "recomendacion X")
        assert dl.update_decision_followup("no_existe", "accion", "resultado") is False

    def test_update_followup_completa_seguimiento_real(self, tmp_path, monkeypatch):
        """Regresion del bug real encontrado 2026-07-07: pandas 3.0+
        lanzaba TypeError al asignar texto sobre una columna float64
        (todo NaN) via .loc — ver feedback_technical.md."""
        dl = self._decisions_paths(tmp_path, monkeypatch)
        dl.append_decision("c1", "2026-07-07 10:00:00", "t8_corta", "recomendacion X")
        ok = dl.update_decision_followup("c1", "siguio la recomendacion", "sin overflow")
        assert ok is True
        df = dl.read_decisions()
        assert df.iloc[0]["accion_tomada"] == "siguio la recomendacion"
        assert df.iloc[0]["resultado_observado"] == "sin overflow"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
