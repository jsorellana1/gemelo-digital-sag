"""
scenario_state.py — Persistencia del ultimo escenario simulado
(Backlog #4, Skill UX/UI v2 JdS, 2026-07-07).

El ejecutable tarda ~20s en abrir (restriccion de infraestructura, no
resoluble con diseño — ver skill). Lo que SI se puede resolver: que el
operador no parta de cero cada vez que abre el .exe. Este modulo guarda
los parametros del ultimo escenario simulado en un archivo local junto
al .exe (o en outputs/state/ en modo dev) y los recupera al abrir, junto
con hace cuanto tiempo fue esa simulacion.

Versionado de esquema (2026-07-14, ver 04_Reports/Technical/
20260714_Persistencia_Estado_Obsoleto.md): este archivo sobrevive a
reinicios del servidor Y a actualizaciones de version de la app (a
diferencia de un dcc.Store de sesion, que al menos se pierde si el
usuario abre una pestana nueva). Sin version explicita, un
last_scenario.json escrito por una version anterior de la app (ej. con
duracion_t8 fuera de las 5 opciones fijas actuales, o sin algun campo que
el codigo actual espera) se precargaba silenciosamente en los controles y
podia dejar la simulacion en un estado inconsistente. Ahora se envuelve
con utils.state_schema y cualquier archivo de una version distinta (o sin
schema_version, como todos los escritos antes de este cambio) se
descarta automaticamente.
"""
from __future__ import annotations

import os
import sys
import json
import time

from utils.state_schema import make_envelope, normalize_persisted_state, LAST_SCENARIO_DEFAULT

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if getattr(sys, "frozen", False):
    _STATE_DIR = os.path.join(os.path.dirname(sys.executable), "outputs", "state")
else:
    _STATE_DIR = os.path.join(_ROOT, "outputs", "state")

_STATE_PATH = os.path.join(_STATE_DIR, "last_scenario.json")


def save_last_scenario(params: dict) -> None:
    """Sobreescribe el ultimo escenario (no historico — solo el mas
    reciente). Nunca lanza: un fallo de guardado no debe romper la app."""
    entry = dict(params)
    entry["_timestamp_epoch"] = time.time()
    entry["_timestamp_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
    envelope = make_envelope(entry)
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(envelope, f, ensure_ascii=False)
    except Exception:
        pass


def load_last_scenario() -> dict | None:
    """Retorna el ultimo escenario guardado + 'horas_desde' calculado, o
    None si nunca se guardo nada (primera vez que se abre el ejecutable) o
    si el archivo es de una version de esquema distinta/incompatible
    (tratado igual que 'nunca se guardo nada', no como un error)."""
    if not os.path.exists(_STATE_PATH):
        return None
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None

    normalized = normalize_persisted_state(
        raw, LAST_SCENARIO_DEFAULT,
        required_keys=("pila1", "pila2", "duracion_t8"),
        kind="last_scenario",
    )
    entry = normalized["data"]
    if "_timestamp_epoch" not in entry:
        # Estado descartado (version distinta/corrupto) -> equivalente a
        # "nunca se guardo nada", no a un escenario real con timestamp 0.
        return None
    entry["horas_desde"] = (time.time() - entry.get("_timestamp_epoch", time.time())) / 3600.0
    return entry
