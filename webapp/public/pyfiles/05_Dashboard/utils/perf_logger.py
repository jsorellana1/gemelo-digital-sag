"""
perf_logger.py — Instrumentacion de tiempos para el Gemelo Digital de Molienda.

Registra duracion de callbacks/funciones costosas.

Actualizacion 2026-07-07 (Requisito 6, Skill UX/UI v3 — SLA de 3s):
formato CSV en runtime_data/performance_log.csv (antes: texto plano en
outputs/logs/performance.log, que se mantiene tambien por compatibilidad
con quien ya lea ese archivo). Columnas nuevas: vista, estado — para
poder cruzar "que vista estaba activa" y "paso/fallo el SLA de 3s" sin
tener que re-derivarlo del duracion_ms en cada analisis.

NOTA de empaquetado: runtime_data/ es tambien la carpeta de datos
congelados que se distribuye con el .exe portable (ver
scripts/build_portable.py / sync_portable_to_dev.py). Escribir un log
de ejecucion ahi mezcla estado "vivo" con datos "congelados para
distribucion" — si sync_portable_to_dev.py hace diff de esa carpeta,
puede marcar performance_log.csv como divergencia falsa. Se sigue la
ruta pedida explicitamente por el Requisito 6 del prompt, pero se deja
esta nota para quien mantenga el empaquetado.

Columnas: timestamp, accion, duracion_ms, vista, escenario_hash,
cache_hit, estado

Uso:
    from utils.perf_logger import timed

    @timed("simulate_scenario")
    def simulate_scenario(...): ...

o directamente:
    from utils.perf_logger import log_duration
    log_duration("run_monte_carlo", duracion_ms=123.4, scenario_hash="ab12",
                  cache_hit=False, vista="pilas", estado="ok")
"""
import os
import sys
import csv
import time
import logging
import functools
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if getattr(sys, "frozen", False):
    _LOG_DIR = os.path.join(os.path.dirname(sys.executable), "outputs", "logs")
    _RUNTIME_DATA_DIR = os.path.join(os.path.dirname(sys.executable), "runtime_data")
else:
    _LOG_DIR = os.path.join(_ROOT, "outputs", "logs")
    _RUNTIME_DATA_DIR = os.path.join(_ROOT, "runtime_data")
os.makedirs(_LOG_DIR, exist_ok=True)

_perf_log = logging.getLogger("perf")
_perf_log.setLevel(logging.INFO)
_perf_log.propagate = False
if not _perf_log.handlers:
    _handler = logging.FileHandler(
        os.path.join(_LOG_DIR, "performance.log"), encoding="utf-8"
    )
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _perf_log.addHandler(_handler)

SLA_MS = 3000.0
_CSV_PATH = os.path.join(_RUNTIME_DATA_DIR, "performance_log.csv")
_CSV_HEADER = ["timestamp", "accion", "duracion_ms", "vista", "escenario_hash", "cache_hit", "estado"]
_csv_lock = threading.Lock()


def _append_csv_row(row: dict) -> None:
    try:
        with _csv_lock:
            os.makedirs(_RUNTIME_DATA_DIR, exist_ok=True)
            escribir_header = not os.path.exists(_CSV_PATH)
            with open(_CSV_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_CSV_HEADER)
                if escribir_header:
                    writer.writeheader()
                writer.writerow(row)
    except Exception:
        pass  # logging nunca debe romper la app


def log_duration(callback_name: str, duracion_ms: float,
                  scenario_hash: str = "-", cache_hit: bool = False,
                  vista: str = "-", estado: str | None = None) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    _perf_log.info(
        f"{ts} | {callback_name} | {duracion_ms:.1f} | {scenario_hash} | {cache_hit}"
    )
    if estado is None:
        estado = "ok" if duracion_ms < SLA_MS else "fuera_sla_3s"
    _append_csv_row({
        "timestamp": ts, "accion": callback_name, "duracion_ms": round(duracion_ms, 1),
        "vista": vista, "escenario_hash": scenario_hash, "cache_hit": cache_hit, "estado": estado,
    })


def timed(name: str | None = None, vista: str = "-"):
    """Decorador: mide duracion de la funcion y la registra (performance.log
    + runtime_data/performance_log.csv).

    Si la funcion devuelve un dict con clave '_cache_hit' (usado por
    engine.scenario_cache), se propaga a la columna cache_hit del log y se
    remueve del dict antes de retornarlo al llamador.
    """
    def deco(fn):
        label = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            result = fn(*args, **kwargs)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            cache_hit = False
            if isinstance(result, dict) and "_cache_hit" in result:
                cache_hit = result.pop("_cache_hit")
            scenario_hash = kwargs.get("_scenario_hash", "-")
            log_duration(label, dt_ms, scenario_hash=scenario_hash, cache_hit=cache_hit, vista=vista)
            return result
        return wrapper
    return deco
