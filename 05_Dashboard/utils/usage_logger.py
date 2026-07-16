"""
usage_logger.py — Instrumentacion de uso real del Gemelo Digital
(Backlog #1, Skill UX/UI v2 JdS, 2026-07-07).

Sin esto, ninguna decision de rediseño de Vista 1 tiene forma de
validarse: el skill exige saber si el Jefe de Sala realmente llega a
usar el sistema durante un evento T8 real, dentro de los primeros 5
minutos, y si la recomendacion cambia su decision — nada de eso se
puede medir sin datos de uso.

Registra en JSON-lines (una linea = un evento), en
outputs/logs/usage.jsonl (o junto al .exe en modo frozen, mismo patron
que utils/perf_logger.py):

    sesion_iniciada        — al cargar la app
    simulacion_disparada   — cada vez que corre el callback principal
                              (funciona tambien como heartbeat: el
                              ultimo evento antes de cerrar aproxima
                              "vista activa al cerrar" — no hay hook
                              real de cierre en un Dash local, ver
                              limitacion documentada abajo)
    recomendacion_generada — cada click en "GENERAR RECOMENDACION".
                              Trae un `rec_id` propio (uuid corto) para
                              poder enlazarla con su feedback, si llega.
    recomendacion_feedback — Fase 1 (cierre de brechas "Validacion
                              Operacional Real", 2026-07-07): el
                              operador marca SI/NO/PARCIAL sobre la
                              ULTIMA recomendacion generada (mismo
                              `rec_id`). Si nunca se marca nada, esa
                              recomendacion cuenta como "NO REGISTRADA"
                              — nunca se asume aceptacion por default.

Limitacion conocida: no existe un evento de "sesion cerrada" real —
Dash corriendo como app local (via .exe) no tiene un hook de servidor
para "el usuario cerro la pestaña/proceso". El heartbeat de
"simulacion_disparada" es la aproximacion practica: la duracion de
sesion y la vista activa se leen del ULTIMO evento de cada session_id.
"""
from __future__ import annotations

import os
import sys
import time
import json
import uuid
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if getattr(sys, "frozen", False):
    _LOG_DIR = os.path.join(os.path.dirname(sys.executable), "outputs", "logs")
else:
    _LOG_DIR = os.path.join(_ROOT, "outputs", "logs")

_LOG_PATH = os.path.join(_LOG_DIR, "usage.jsonl")
_lock = threading.Lock()

_session_id: str | None = None
_session_start: float | None = None


def start_session() -> str:
    """Genera un nuevo session_id y registra 'sesion_iniciada'. Se llama
    una vez al cargar el layout (ver app.py::serve_layout)."""
    global _session_id, _session_start
    _session_id = str(uuid.uuid4())[:8]
    _session_start = time.time()
    log_event("sesion_iniciada")
    return _session_id


def log_event(event_type: str, **fields) -> None:
    """Registra un evento. NUNCA lanza — un fallo de logging no debe
    romper la app. Si no hay sesion activa, la abre implicitamente."""
    global _session_id, _session_start
    if _session_id is None:
        _session_id = str(uuid.uuid4())[:8]
        _session_start = time.time()

    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "session_id": _session_id,
        "evento": event_type,
        "duracion_sesion_seg": round(time.time() - _session_start, 1) if _session_start else 0.0,
    }
    entry.update(fields)

    try:
        with _lock:
            os.makedirs(_LOG_DIR, exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_sessions() -> list[dict]:
    """Lee todo el log y retorna un resumen por sesion (duracion final,
    ultima vista activa, ultimo regimen activo, N simulaciones, usuario,
    y adopcion de recomendaciones). Usado para el analisis de uso real
    que decide si procede el Backlog #5 (rediseño completo de Vista 1)
    — ver skill UX/UI v2, seccion 'Despues de 2 semanas de datos de
    usage_logger' — y para la pagina /desempeno_gemelo (Fase 8 parcial,
    cierre de brechas 'Validacion Operacional Real', 2026-07-07).

    Adopcion (`recomendacion_aceptada`): se empareja cada evento
    `recomendacion_generada` (trae su propio `rec_id`) con el evento
    `recomendacion_feedback` mas reciente que comparta ese `rec_id`, si
    existe. Una recomendacion sin feedback asociado cuenta como
    'NO REGISTRADA' — nunca se asume SI/NO por default."""
    if not os.path.exists(_LOG_PATH):
        return []
    sesiones: dict[str, dict] = {}
    eventos: list[dict] = []
    with open(_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("session_id") is not None:
                eventos.append(e)

    feedback_por_rec_id: dict[str, str] = {}
    for e in eventos:
        if e.get("evento") == "recomendacion_feedback" and e.get("rec_id"):
            feedback_por_rec_id[e["rec_id"]] = e.get("recomendacion_aceptada", "NO REGISTRADA")

    for e in eventos:
        sid = e["session_id"]
        s = sesiones.setdefault(sid, {
            "session_id": sid, "n_simulaciones": 0, "n_recomendaciones": 0,
            "primera_ts": e["timestamp"], "ultima_ts": e["timestamp"],
            "duracion_sesion_seg": 0.0, "ultima_vista": None, "ultimo_regimen": None,
            "usuario": None, "recomendaciones_aceptadas": [],
        })
        s["ultima_ts"] = e["timestamp"]
        s["duracion_sesion_seg"] = max(s["duracion_sesion_seg"], e.get("duracion_sesion_seg", 0.0))
        if e.get("usuario"):
            s["usuario"] = e["usuario"]
        if e.get("evento") == "simulacion_disparada":
            s["n_simulaciones"] += 1
            s["ultima_vista"] = e.get("vista_activa", s["ultima_vista"])
            s["ultimo_regimen"] = e.get("regimen_activo", s["ultimo_regimen"])
        elif e.get("evento") == "recomendacion_generada":
            s["n_recomendaciones"] += 1
            rec_id = e.get("rec_id")
            aceptada = feedback_por_rec_id.get(rec_id, "NO REGISTRADA") if rec_id else "NO REGISTRADA"
            s["recomendaciones_aceptadas"].append(aceptada)
    return list(sesiones.values())


def adopcion_global() -> dict:
    """Resumen de adopcion (% recomendaciones seguidas) sobre TODAS las
    sesiones — insumo real para la tarjeta 'Adopcion' de
    /desempeno_gemelo. Retorna conteos, nunca un porcentaje inventado
    cuando no hay recomendaciones registradas todavia."""
    sesiones = read_sessions()
    todas = [a for s in sesiones for a in s.get("recomendaciones_aceptadas", [])]
    total = len(todas)
    if total == 0:
        return {"total": 0, "si": 0, "no": 0, "parcial": 0, "no_registrada": 0, "pct_aceptacion": None}
    si = todas.count("SI")
    no = todas.count("NO")
    parcial = todas.count("PARCIAL")
    no_reg = todas.count("NO REGISTRADA")
    return {
        "total": total, "si": si, "no": no, "parcial": parcial, "no_registrada": no_reg,
        "pct_aceptacion": round(si / total * 100.0, 1),
    }
