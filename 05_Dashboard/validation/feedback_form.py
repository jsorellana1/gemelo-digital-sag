"""
feedback_form.py — Persistencia del formulario jefe de sala (Fase 10,
cierre de brechas "Validacion Operacional Real", 2026-07-07).

El componente UI (3 preguntas 1-5 + comentario) vive en
components/controls.py::build_feedback_panel (mismo panel que el
checkbox "Validar escenario real" y el feedback SI/NO/PARCIAL — un
solo panel, no tres separados). Este modulo solo persiste la
respuesta, con el mismo patron defensivo (nunca lanza) del resto de
utils/*_logger.py.

Se enlaza por `case_id` cuando el operador tambien marco "Validar
escenario real" (Fase 2); si no, se guarda igual con `case_id` vacio —
el feedback cualitativo del jefe de sala tiene valor por si solo, no
depende de que el caso completo se haya guardado.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD_ROOT = os.path.dirname(_HERE)

if getattr(sys, "frozen", False):
    _FEEDBACK_DIR = os.path.join(os.path.dirname(sys.executable), "operational_decisions")
else:
    _FEEDBACK_DIR = os.path.normpath(os.path.join(_DASHBOARD_ROOT, "..", "01_Data", "Operational_Decisions"))

_FEEDBACK_PATH = os.path.join(_FEEDBACK_DIR, "jefe_sala_feedback.csv")

_COLUMNS = ["case_id", "fecha", "util_1_5", "razonable_1_5", "decision_distinta_1_5", "comentario"]


def append_jefe_sala_feedback(
    case_id: str | None, fecha: str,
    util_1_5: int | None, razonable_1_5: int | None, decision_distinta_1_5: int | None,
    comentario: str = "",
) -> None:
    """Agrega una fila. Nunca lanza. Escalas 1-5 pueden venir en None si
    el jefe de sala dejo alguna pregunta sin responder — no se fuerza
    un valor por default."""
    row = {
        "case_id": case_id or "", "fecha": fecha,
        "util_1_5": util_1_5, "razonable_1_5": razonable_1_5,
        "decision_distinta_1_5": decision_distinta_1_5, "comentario": comentario,
    }
    try:
        os.makedirs(_FEEDBACK_DIR, exist_ok=True)
        df_new = pd.DataFrame([row], columns=_COLUMNS)
        if os.path.exists(_FEEDBACK_PATH):
            df_new.to_csv(_FEEDBACK_PATH, mode="a", header=False, index=False, encoding="utf-8")
        else:
            df_new.to_csv(_FEEDBACK_PATH, mode="w", header=True, index=False, encoding="utf-8")
    except Exception:
        pass
