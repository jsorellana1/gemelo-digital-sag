"""
regime_event_detector.py — Detector retrospectivo de eventos de régimen
en series de tiempo ya disponibles (TAREA 2, prompt "CIERRE DE BRECHAS
POST ROUTER v2", 2026-07-07).

No fabrica eventos: escanea la serie continua de 5 min
`01_Data/Cache/advanced_t8_historical_5min.parquet` (93 612 filas,
2025-08-01 a 2026-06-21) — la MISMA fuente que ya usa Optimizer V3/V4
para sus anclas históricas — y aplica umbrales operacionales explícitos
para identificar períodos donde cada régimen estuvo activo.

Limitación de datos declarada explícitamente (no oculta): esta serie
tiene `pila_sag1/2`, `correa_315/316` (proxy de qin) y `SAG1_tph/SAG2_tph`
(proxy de qout) y `SAG1_operando`/`SAG2_operando`, pero **NO tiene**
columnas de CH1/CH2 (chancadores) ni de T1 (transferencia post-chancado)
ni de estado de molinos de bolas (411/412/511/512). Por lo tanto:
  - `detectar_mantencion_historica` solo puede usar SAG1/SAG2 operando
    como proxy de "equipo crítico fuera de servicio" — NO cubre bolas ni
    chancadores, que no están en ningún dataset disponible.
  - `detectar_alimentacion_restringida_historica` usa una caída fuerte de
    correa_315/316 vs. su propio historial como proxy — NO puede
    verificar CH1/CH2/T1 directamente porque esas series no existen en
    el proyecto.
Esto se documenta en `calidad_datos` y en el reporte de cobertura, no se
disimula.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))
_FREQ_MIN = 5.0

# Umbrales operacionales (documentados, no arbitrarios: CRITICAL_PCT viene
# de engine/ode_model.py; el resto son los del prompt).
OVERFLOW_PILA_PCT = 85.0
INVENTARIO_CRITICO_PCT = 20.0
VENTANA_MIN_DEFAULT = 30.0
GAP_MAX_MIN = 10.0


@dataclass
class EventoHistoricoDetectado:
    regimen: str
    inicio: datetime
    fin: datetime
    duracion_min: float
    estado_inicial: dict
    estado_final: dict
    calidad_datos: str
    gaps_en_ventana: int
    es_valido_para_backtesting: bool
    razon_invalidacion: str | None = None


def _load_serie() -> pd.DataFrame:
    df = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_historical_5min.parquet"))
    df = df.sort_values("fecha").reset_index(drop=True)
    return df


def _runs_from_mask(df: pd.DataFrame, mask: pd.Series) -> list[tuple[int, int]]:
    """Retorna lista de (idx_ini, idx_fin) de tramos contiguos donde mask=True."""
    runs = []
    in_run = False
    start = None
    idx = df.index.to_numpy()
    m = mask.to_numpy()
    for i, val in enumerate(m):
        if val and not in_run:
            in_run = True
            start = i
        elif not val and in_run:
            in_run = False
            runs.append((idx[start], idx[i - 1]))
    if in_run:
        runs.append((idx[start], idx[len(m) - 1]))
    return runs


def _contar_gaps(sub: pd.DataFrame, cols: list[str]) -> int:
    """Cuenta timesteps dentro de la ventana con NaN en cualquiera de `cols`
    Y separacion temporal > GAP_MAX_MIN entre registros consecutivos."""
    gaps = int(sub[cols].isna().any(axis=1).sum())
    if len(sub) > 1:
        deltas_min = sub["fecha"].diff().dt.total_seconds().dropna() / 60.0
        gaps += int((deltas_min > GAP_MAX_MIN).sum())
    return gaps


def _calidad(gaps: int, n_rows: int, cols_criticas_nan_inicio: bool) -> str:
    if cols_criticas_nan_inicio:
        return "baja"
    frac_gaps = gaps / max(n_rows, 1)
    if frac_gaps == 0:
        return "alta"
    elif frac_gaps < 0.05:
        return "media"
    return "baja"


def _construir_evento(
    df: pd.DataFrame, idx_ini: int, idx_fin: int, regimen: str,
    cols_estado: list[str], ventana_min: float,
) -> EventoHistoricoDetectado | None:
    sub = df.loc[idx_ini:idx_fin]
    duracion_min = float((sub["fecha"].iloc[-1] - sub["fecha"].iloc[0]).total_seconds() / 60.0) + _FREQ_MIN
    if duracion_min < ventana_min:
        return None

    fila_ini = sub.iloc[0]
    fila_fin = sub.iloc[-1]
    ini_nan = bool(fila_ini[cols_estado].isna().any())
    gaps = _contar_gaps(sub, cols_estado)
    calidad = _calidad(gaps, len(sub), ini_nan)

    es_valido = True
    razon = None
    if duracion_min < VENTANA_MIN_DEFAULT:
        es_valido, razon = False, f"Duracion {duracion_min:.0f}min < minimo {VENTANA_MIN_DEFAULT:.0f}min"
    elif ini_nan:
        es_valido, razon = False, "Estado inicial tiene NaN (no confirmado, seria interpolado)"
    elif gaps > 0:
        es_valido, razon = False, f"{gaps} gap(s) > {GAP_MAX_MIN:.0f}min o valores NaN dentro de la ventana"

    return EventoHistoricoDetectado(
        regimen=regimen,
        inicio=fila_ini["fecha"].to_pydatetime(),
        fin=fila_fin["fecha"].to_pydatetime(),
        duracion_min=round(duracion_min, 1),
        estado_inicial={c: _safe(fila_ini[c]) for c in cols_estado},
        estado_final={c: _safe(fila_fin[c]) for c in cols_estado},
        calidad_datos=calidad,
        gaps_en_ventana=gaps,
        es_valido_para_backtesting=es_valido,
        razon_invalidacion=razon,
    )


def _safe(v):
    if pd.isna(v):
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return float(v)


def detectar_overflow_historico(df: pd.DataFrame, umbral_pila: float = OVERFLOW_PILA_PCT,
                                 ventana_min: float = VENTANA_MIN_DEFAULT) -> list[EventoHistoricoDetectado]:
    """pila > umbral Y qin > qout sostenido. qin=correa_31x, qout=SAGx_tph."""
    eventos = []
    for asset, pila_col, qin_col, qout_col in (
        ("SAG1", "pila_sag1", "correa_315", "SAG1_tph"),
        ("SAG2", "pila_sag2", "correa_316", "SAG2_tph"),
    ):
        mask = (df[pila_col] > umbral_pila) & (df[qin_col] > df[qout_col])
        mask = mask.fillna(False)
        for idx_ini, idx_fin in _runs_from_mask(df, mask):
            ev = _construir_evento(df, idx_ini, idx_fin, f"overflow_{asset}",
                                    [pila_col, qin_col, qout_col], ventana_min)
            if ev:
                eventos.append(ev)
    return eventos


def detectar_inventario_critico_historico(df: pd.DataFrame, umbral_pct: float = INVENTARIO_CRITICO_PCT,
                                           ventana_min: float = VENTANA_MIN_DEFAULT) -> list[EventoHistoricoDetectado]:
    eventos = []
    for asset, pila_col in (("SAG1", "pila_sag1"), ("SAG2", "pila_sag2")):
        mask = (df[pila_col] < umbral_pct).fillna(False)
        for idx_ini, idx_fin in _runs_from_mask(df, mask):
            ev = _construir_evento(df, idx_ini, idx_fin, f"inventario_critico_{asset}",
                                    [pila_col], ventana_min)
            if ev:
                eventos.append(ev)
    return eventos


def detectar_mantencion_historica(df: pd.DataFrame,
                                   ventana_min: float = VENTANA_MIN_DEFAULT) -> list[EventoHistoricoDetectado]:
    """Proxy con los datos disponibles: SAG1/SAG2 fuera de servicio
    (`*_operando=False`). NO cubre CH1/CH2/bolas — esas series no existen
    en ningun dataset del proyecto (ver docstring del modulo)."""
    eventos = []
    for asset, op_col in (("SAG1", "SAG1_operando"), ("SAG2", "SAG2_operando")):
        mask = (~df[op_col].astype(bool)).fillna(False)
        for idx_ini, idx_fin in _runs_from_mask(df, mask):
            ev = _construir_evento(df, idx_ini, idx_fin, f"mantenimiento_{asset}",
                                    [op_col], ventana_min)
            if ev:
                ev.calidad_datos = "media" if ev.calidad_datos == "alta" else ev.calidad_datos
                ev.razon_invalidacion = (ev.razon_invalidacion or "")
                eventos.append(ev)
    return eventos


def detectar_alimentacion_restringida_historica(
    df: pd.DataFrame, ventana_min: float = VENTANA_MIN_DEFAULT,
) -> list[EventoHistoricoDetectado]:
    """Proxy con los datos disponibles: caida de correa_315/316 a menos del
    30% de su propia mediana movil de 24h (2h*12=288 muestras) sostenida.
    NO puede verificar CH1/CH2/T1 (no existen en el dataset) — se
    documenta como proxy parcial, no como deteccion completa."""
    eventos = []
    for asset, qin_col in (("SAG1", "correa_315"), ("SAG2", "correa_316")):
        mediana_movil = df[qin_col].rolling(window=288, min_periods=50, center=True).median()
        mask = (df[qin_col] < 0.30 * mediana_movil).fillna(False)
        for idx_ini, idx_fin in _runs_from_mask(df, mask):
            ev = _construir_evento(df, idx_ini, idx_fin, f"alimentacion_restringida_{asset}",
                                    [qin_col], ventana_min)
            if ev:
                # Proxy parcial: nunca "alta" calidad aunque no tenga gaps,
                # porque falta CH1/CH2/T1 para confirmar la causa.
                if ev.calidad_datos == "alta":
                    ev.calidad_datos = "media"
                eventos.append(ev)
    return eventos


def _marcar_solapes(todos: list[EventoHistoricoDetectado]) -> None:
    """Marca eventos que solapan temporalmente con uno de OTRO regimen
    base como 'mixto' en calidad_datos (no invalida, solo documenta)."""
    def _base(r: str) -> str:
        for b in ("overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida"):
            if r.startswith(b):
                return b
        return r

    for i, a in enumerate(todos):
        for b in todos[i + 1:]:
            if _base(a.regimen) == _base(b.regimen):
                continue
            if a.inicio <= b.fin and b.inicio <= a.fin:
                a.razon_invalidacion = (a.razon_invalidacion + "; " if a.razon_invalidacion else "") + \
                    f"Solapa con evento de regimen distinto ({b.regimen})"
                b.razon_invalidacion = (b.razon_invalidacion + "; " if b.razon_invalidacion else "") + \
                    f"Solapa con evento de regimen distinto ({a.regimen})"


@lru_cache(maxsize=1)
def detectar_todos_los_regimenes() -> list[EventoHistoricoDetectado]:
    """Cacheada (funcion sin argumentos, serie historica fija dentro del
    proceso): sin esto, cada llamador con su propio @lru_cache separado
    (check_prerequisito_0, run_backtest_proxy por regimen) dispara su
    propia corrida completa de deteccion (~14s medido) porque el cache de
    cada uno no comparte resultados con los demas — ver perf_logger,
    hallazgo 2026-07-10: route_and_simulate llamaba esta funcion 2 veces
    (28s de ~38s totales del callback principal) antes de este cambio.
    Callers tratan el resultado como solo-lectura (filtran/leen campos,
    nunca mutan la lista ni sus elementos) — cachear la lista es seguro."""
    df = _load_serie()
    eventos = []
    eventos += detectar_overflow_historico(df)
    eventos += detectar_inventario_critico_historico(df)
    eventos += detectar_mantencion_historica(df)
    eventos += detectar_alimentacion_restringida_historica(df)
    _marcar_solapes(eventos)
    return eventos


def exportar_csv(eventos: list[EventoHistoricoDetectado], path: str) -> None:
    rows = [{
        "regimen": e.regimen, "inicio": e.inicio, "fin": e.fin,
        "duracion_min": e.duracion_min, "calidad_datos": e.calidad_datos,
        "es_valido": e.es_valido_para_backtesting,
        "razon_invalidacion": e.razon_invalidacion or "",
    } for e in eventos]
    pd.DataFrame(rows).to_csv(path, index=False)


if __name__ == "__main__":
    eventos = detectar_todos_los_regimenes()
    print(f"Total eventos detectados: {len(eventos)}")
    from collections import Counter

    def _base(r):
        for b in ("overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida"):
            if r.startswith(b):
                return b
        return r
    por_regimen = Counter(_base(e.regimen) for e in eventos)
    validos = Counter(_base(e.regimen) for e in eventos if e.es_valido_para_backtesting)
    for regimen in ("overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida"):
        print(f"  {regimen}: detectados={por_regimen.get(regimen, 0)}  validos={validos.get(regimen, 0)}")
