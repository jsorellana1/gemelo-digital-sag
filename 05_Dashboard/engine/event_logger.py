"""
event_logger.py — Captura prospectiva de eventos de régimen (TAREA 4,
prompt "CIERRE DE BRECHAS POST ROUTER v2", 2026-07-07).

Los 4 regímenes sin dataset oficial (overflow/inventario_critico/
mantenimiento/alimentacion_restringida) hoy solo tienen cobertura via
detección retrospectiva (proxy, ver regime_event_detector.py). Este
módulo registra en tiempo real cuándo `route_and_simulate()` cambia de
régimen dominante, generando — desde hoy hacia adelante — el dataset
histórico ETIQUETADO que hoy no existe. Con suficientes meses de
operación, este log reemplazará al detector proxy como fuente de
backtesting (fuente="oficial_logueado" en vez de "proxy_detectado").
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PATH = os.path.normpath(os.path.join(_HERE, "..", "data", "regime_events_log.parquet"))


@dataclass
class _OpenEvent:
    regimen: str
    inicio: datetime
    estado_inicial: dict


class RegimeEventLogger:
    """Registra en tiempo real cuando el sistema entra y sale de cada
    regimen. Genera el dataset historico que hoy no existe. Un evento
    queda "abierto" hasta que ocurre el siguiente cambio de regimen
    (on_regime_change) o se cierra explicitamente (close_event)."""

    def __init__(self, path: str | None = None):
        self.path = path or _DEFAULT_PATH
        self._open: _OpenEvent | None = None

    def on_regime_change(self, anterior: str, nuevo: str, scenario_state: dict, timestamp: datetime) -> None:
        if anterior == nuevo:
            return
        if self._open is not None:
            self.close_event(self._open.regimen, timestamp, scenario_state)
        self._open = _OpenEvent(regimen=nuevo, inicio=timestamp, estado_inicial=dict(scenario_state))

    def close_event(self, regimen: str, fin: datetime, resultado_real: dict) -> None:
        if self._open is None or self._open.regimen != regimen:
            return
        row = {"regimen": regimen, "inicio": self._open.inicio, "fin": fin}
        row.update({f"inicial_{k}": v for k, v in self._open.estado_inicial.items()})
        row.update({f"final_{k}": v for k, v in resultado_real.items()})
        self._append_row(row)
        self._open = None

    def _append_row(self, row: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        df_new = pd.DataFrame([row])
        if os.path.exists(self.path):
            try:
                df_old = pd.read_parquet(self.path)
                df = pd.concat([df_old, df_new], ignore_index=True)
            except Exception:
                df = df_new
        else:
            df = df_new
        df.to_parquet(self.path, index=False)


# Instancia unica de proceso (Dash corre en un solo proceso, use_reloader=False
# — ver CLAUDE.md) para mantener el estado del "evento abierto" entre
# llamadas sucesivas del callback.
event_logger = RegimeEventLogger()
