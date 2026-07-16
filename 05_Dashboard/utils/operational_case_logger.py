"""
operational_case_logger.py — Biblioteca de casos operacionales reales
(Fase 2, cierre de brechas "Validacion Operacional Real", 2026-07-07).

Mismo patron defensivo que utils/scenario_state.py (nunca lanza, un
fallo de guardado no debe romper la app) pero NO sobreescribe: cada
caso queda como su propio archivo en runtime_data/operational_cases/,
porque el objetivo es construir una biblioteca de casos reales, no
recordar solo "el ultimo".

Se activa solo cuando el operador marca el checkbox "Validar escenario
real" — no todos los escenarios simulados son casos de validacion (la
mayoria son exploracion de what-if), asi que no se guarda todo por
defecto.
"""
from __future__ import annotations

import os
import sys
import json
import time
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if getattr(sys, "frozen", False):
    _CASES_DIR = os.path.join(os.path.dirname(sys.executable), "runtime_data", "operational_cases")
else:
    _CASES_DIR = os.path.join(_ROOT, "runtime_data", "operational_cases")


def save_operational_case(snapshot: dict) -> str | None:
    """Guarda `snapshot` como un caso nuevo (no sobreescribe casos
    previos). Retorna el `case_id` generado, o None si el guardado
    fallo (nunca lanza)."""
    case_id = str(uuid.uuid4())[:8]
    entry = dict(snapshot)
    entry["case_id"] = case_id
    entry["_timestamp_epoch"] = time.time()
    entry["_timestamp_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
    ts_compacto = time.strftime("%Y%m%d_%H%M%S")
    try:
        os.makedirs(_CASES_DIR, exist_ok=True)
        path = os.path.join(_CASES_DIR, f"{ts_compacto}_{case_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        return case_id
    except Exception:
        return None


def list_operational_cases() -> list[dict]:
    """Lee todos los casos guardados. Usado por el script de reporte
    (Fase 5) y por la pagina /desempeno_gemelo (Fase 8, conteo de
    casos validados por regimen)."""
    if not os.path.isdir(_CASES_DIR):
        return []
    casos = []
    for fname in sorted(os.listdir(_CASES_DIR)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_CASES_DIR, fname), "r", encoding="utf-8") as f:
                casos.append(json.load(f))
        except Exception:
            continue
    return casos
