"""
scenario_cache.py — Cache en memoria por escenario para el Gemelo Digital.

No cambia la reactividad del simulador (Monte Carlo/Optimizer V3 siguen
disparandose en cada cambio de slider, ver decision documentada en
04_Reports/Technical/20260702_UX_UI_Operational_Control_Center.md y
skill_token_optimization_loop.md Regla 21). Lo que evita es RECALCULAR
cuando el usuario vuelve a un escenario ya visto en esta sesion (arrastra
el slider de vuelta a un valor anterior, cambia de pestana y regresa,
Dash re-dispara el callback al re-montar, etc.) — un caso muy comun con
sliders continuos.

Cache LRU acotada en memoria de proceso (la app corre single-user /
single-process, no requiere Redis ni disco).
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Callable

from utils.perf_logger import log_duration


_HASH_DECIMALS = 2  # ver normalize_for_hash() — redondeo SOLO para la clave de cache


def normalize_for_hash(value: Any, decimals: int = _HASH_DECIMALS) -> Any:
    """Redondea floats a `decimals` — SOLO para efectos de la clave de
    cache/hash. Nunca se usa el valor redondeado para el calculo fisico
    real: ScenarioCache.wrap() pasa los args ORIGINALES (sin redondear)
    a la funcion envuelta; `normalize_for_hash` solo alimenta
    `scenario_hash()`. Aplica a pilas, rates, TPH, T1/CV315/CV316/T3,
    autonomias — cualquier float que llegue como argumento.

    2026-07-09 (profiling): sin este redondeo, `scenario_hash()` distinguia
    escenarios que solo difieren en ruido de punto flotante (ej. arrastrar
    un slider deja pila1=55.00001 en vez de 55.0), causando cache-miss
    para escenarios operacionalmente identicos — cache hit medido en
    44.7%. Ver 04_Reports/Technical/20260709_Optimizer_V3_Deep_Profiling.md."""
    if isinstance(value, float):
        return round(value, decimals)
    if isinstance(value, dict):
        return {k: normalize_for_hash(v, decimals) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple, set)):
        return tuple(normalize_for_hash(v, decimals) for v in value)
    return value


def _to_hashable(value: Any) -> Any:
    value = normalize_for_hash(value)
    if isinstance(value, (list, set)):
        return tuple(_to_hashable(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _to_hashable(v)) for k, v in value.items()))
    return value


def scenario_hash(*args, **kwargs) -> str:
    """Hash estable de los parametros de un escenario (orden-independiente en kwargs)."""
    payload = {
        "args": [_to_hashable(a) for a in args],
        "kwargs": {k: _to_hashable(v) for k, v in sorted(kwargs.items())},
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


class ScenarioCache:
    """LRU simple keyed por scenario_hash, con instrumentacion perf_logger integrada."""

    def __init__(self, maxsize: int = 256):
        self.maxsize = maxsize
        self._store: OrderedDict[str, Any] = OrderedDict()

    def wrap(self, label: str):
        def deco(fn: Callable):
            def wrapper(*args, **kwargs):
                h = scenario_hash(*args, **kwargs)
                if h in self._store:
                    self._store.move_to_end(h)
                    log_duration(label, 0.0, scenario_hash=h, cache_hit=True)
                    return self._store[h]

                t0 = time.perf_counter()
                result = fn(*args, **kwargs)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                log_duration(label, dt_ms, scenario_hash=h, cache_hit=False)

                self._store[h] = result
                self._store.move_to_end(h)
                if len(self._store) > self.maxsize:
                    self._store.popitem(last=False)
                return result
            wrapper.cache = self
            return wrapper
        return deco

    def clear(self):
        self._store.clear()


# Caches independientes por motor: escenarios identicos de simulacion vs.
# de optimizacion no comparten espacio de claves (mismos kwargs de pila no
# implican mismo resultado si uno cachea simulate_scenario y otro find_optimal_v3).
simulation_cache = ScenarioCache(maxsize=512)
optimizer_cache = ScenarioCache(maxsize=128)
montecarlo_cache = ScenarioCache(maxsize=128)
