"""
decisions_log.py — Dataset de decisiones operacionales (Fase 3, cierre
de brechas "Validacion Operacional Real", 2026-07-07).

Una fila por caso guardado via operational_case_logger.save_operational_case
(Fase 2): `regimen`/`recomendacion`/`fecha` quedan llenos desde el
momento en que se guarda el caso; `accion_tomada`/`resultado_observado`
quedan VACIOS a proposito — recien se conocen despues del turno, y no se
fabrican. Se llenan a mano o via el formulario jefe de sala (Fase 10,
que localiza la fila por `case_id`).

Path en 01_Data/Operational_Decisions/ (mismo patron PascalCase que
01_Data/Cache/, 01_Data/Processed/) en modo dev; junto al .exe en modo
frozen (01_Data no viaja necesariamente dentro del bundle empaquetado).
"""
from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD_ROOT = os.path.dirname(_HERE)

if getattr(sys, "frozen", False):
    _DECISIONS_DIR = os.path.join(os.path.dirname(sys.executable), "operational_decisions")
else:
    _DECISIONS_DIR = os.path.normpath(os.path.join(_DASHBOARD_ROOT, "..", "01_Data", "Operational_Decisions"))

_DECISIONS_PATH = os.path.join(_DECISIONS_DIR, "decisions_log.csv")

_COLUMNS = ["case_id", "fecha", "regimen", "recomendacion", "accion_tomada", "resultado_observado"]


def append_decision(case_id: str, fecha: str, regimen: str, recomendacion: str) -> None:
    """Agrega una fila nueva. Nunca lanza — un fallo de escritura no debe
    romper la app. `accion_tomada`/`resultado_observado` quedan vacios."""
    row = {"case_id": case_id, "fecha": fecha, "regimen": regimen, "recomendacion": recomendacion,
           "accion_tomada": "", "resultado_observado": ""}
    try:
        os.makedirs(_DECISIONS_DIR, exist_ok=True)
        df_new = pd.DataFrame([row], columns=_COLUMNS)
        if os.path.exists(_DECISIONS_PATH):
            df_new.to_csv(_DECISIONS_PATH, mode="a", header=False, index=False, encoding="utf-8")
        else:
            df_new.to_csv(_DECISIONS_PATH, mode="w", header=True, index=False, encoding="utf-8")
    except Exception:
        pass


def read_decisions() -> pd.DataFrame:
    """Lee el dataset completo. DataFrame vacio (columnas correctas) si
    todavia no existe ningun caso.

    `dtype=str`: `accion_tomada`/`resultado_observado` empiezan vacios
    en todas las filas hasta que hay seguimiento — sin forzar el tipo,
    pandas los infiere como float64 (todo NaN) y una asignacion
    posterior de texto via update_decision_followup() revienta con
    TypeError en pandas 3.0+ (antes solo hacia upcast silencioso a
    object). Ver feedback_technical.md."""
    if not os.path.exists(_DECISIONS_PATH):
        return pd.DataFrame(columns=_COLUMNS)
    try:
        return pd.read_csv(_DECISIONS_PATH, encoding="utf-8", dtype=str, keep_default_na=False)
    except Exception:
        return pd.DataFrame(columns=_COLUMNS)


def update_decision_followup(case_id: str, accion_tomada: str, resultado_observado: str) -> bool:
    """Localiza la fila por `case_id` y completa el seguimiento
    (llamado desde el formulario jefe de sala, Fase 10, en una sesion
    posterior a cuando se guardo el caso). Retorna False si el case_id
    no existe — no crea una fila nueva desde aca."""
    df = read_decisions()
    # pandas 3.0+ (feedback_technical.md): con el nuevo dtype "str" por
    # defecto, `case_id not in df["case_id"].values` es poco fiable —
    # usar comparacion booleana vectorizada explicita.
    if df.empty or not (df["case_id"] == case_id).any():
        return False
    try:
        df.loc[df["case_id"] == case_id, "accion_tomada"] = accion_tomada
        df.loc[df["case_id"] == case_id, "resultado_observado"] = resultado_observado
        df.to_csv(_DECISIONS_PATH, mode="w", header=True, index=False, encoding="utf-8")
        return True
    except Exception:
        return False
