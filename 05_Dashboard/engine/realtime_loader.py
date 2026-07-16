"""
realtime_loader.py — Carga estado operacional desde archivos PI Historian.

Fuentes:
  data/raw/tonelaje_v2.xlsx   — CV315, CV316, pilas SAG1/2, rates, T1
  data/raw/estados_activos.xlsx — CH1/CH2, SAG1/SAG2, bolas 411/412/511/512

T8 detection: derivado de caida de CV315+CV316 respecto al baseline reciente.
Ventanas canonicas:
  12h → inicia 08:00
   8h → inicia 08:00  (se distingue de 12h por duracion transcurrida)
   4h → inicia 12:00
   2h → inicia 14:00
"""

from __future__ import annotations
import os
from datetime import timedelta

import numpy as np
import pandas as pd

_HERE    = os.path.dirname(os.path.abspath(__file__))   # .../engine
_APP_DIR = os.path.dirname(_HERE)                        # .../05_Dashboard
_ROOT    = os.path.dirname(_APP_DIR)                     # .../07_Rendimientos
DATA_RAW = os.path.join(_ROOT, "01_Data", "Raw")

TONELAJE_PATH = os.path.join(DATA_RAW, "tonelaje_v2.xlsx")
ESTADOS_PATH  = os.path.join(DATA_RAW, "estados_activos.xlsx")

# Horas canonicas de inicio de ventana T8
_T8_HOURS = [8, 12, 14]          # 8am, 12pm, 2pm
_T8_WINDOW = {8: [12, 8], 12: [4], 14: [2]}  # hora → posibles tipos de ventana


# ── Carga de datos ─────────────────────────────────────────────────────────────

def _load_tonelaje() -> pd.DataFrame:
    df = pd.read_excel(TONELAJE_PATH)
    df["Fecha"]    = pd.to_datetime(df["Fecha"], errors="coerce")
    df             = df.dropna(subset=["Fecha"]).sort_values("Fecha").reset_index(drop=True)
    df["cv315"]    = pd.to_numeric(df["CV_315(tmh/h)"],  errors="coerce").clip(lower=0).fillna(0)
    df["cv316"]    = pd.to_numeric(df["CV_316(tmh/h)"],  errors="coerce").clip(lower=0).fillna(0)
    df["pila_sag1"]= pd.to_numeric(df["SAG:Nivel_Pila"], errors="coerce")
    df["pila_sag2"]= pd.to_numeric(df["SAG2:Nivel_Pila"],errors="coerce")
    df["rate_sag1"]= pd.to_numeric(df["REND_TMS_SAG1_PI"],errors="coerce").clip(lower=0)
    df["rate_sag2"]= pd.to_numeric(df["REND_TMS_SAG2_PI"],errors="coerce").clip(lower=0)
    df["t1"]       = pd.to_numeric(df["T1"],              errors="coerce").clip(lower=0).fillna(0)
    return df


def _load_estados() -> pd.DataFrame:
    df = pd.read_excel(ESTADOS_PATH, header=1)
    df.columns = ["Fecha","CH1","CH2","SAG2","mobo511","mobo512","SAG1","mobo411","mobo412"]
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"]).sort_values("Fecha").reset_index(drop=True)
    for col in ["CH1","CH2","SAG1","SAG2","mobo411","mobo412","mobo511","mobo512"]:
        df[col] = df[col].map(lambda x: str(x).strip().upper() == "PARTIR")
    return df


# ── Deteccion T8 ───────────────────────────────────────────────────────────────

def detect_t8(
    df_ton: pd.DataFrame,
    lookback_stable: int = 60,   # filas de 5min = 5h para baseline estable
    lookback_exclude: int = 48,  # excluir ultimas 4h del baseline (evita incluir T8 activo)
    drop_threshold: float = 0.55,
) -> dict:
    """
    Detecta ventana T8 activa a partir de la caida de CV315+CV316.

    Algoritmo:
    1. Baseline = mediana de CV315+CV316 en ventana estable previa (excluye ultimas 4h).
    2. Si cv_actual < drop_threshold * baseline → T8 activo.
    3. Retrocede en el tiempo para encontrar el inicio real de la caida.
    4. Mapea inicio a hora canonica (8:00 / 12:00 / 14:00).
    5. Calcula duracion transcurrida y tipo de ventana (2/4/8/12h).
    6. Retorna duracion RESTANTE (para inicializar el simulador).
    """
    df = df_ton.copy()
    df["cv_total"] = df["cv315"] + df["cv316"]

    last     = df.iloc[-1]
    ts_now   = pd.Timestamp(last["Fecha"])
    cv_now   = float(last["cv_total"])

    # Baseline: mediana de periodo estable antes del posible T8
    baseline_slice = df.iloc[-(lookback_stable + lookback_exclude):-lookback_exclude]["cv_total"]
    if len(baseline_slice) < 10:
        baseline_slice = df["cv_total"]
    baseline = float(baseline_slice.median())

    if baseline < 200:
        return _no_t8(cv_now, baseline)

    t8_activo = cv_now < drop_threshold * baseline
    if not t8_activo:
        return _no_t8(cv_now, baseline)

    # Encontrar inicio de caida: primera fila (desde atras) que cae bajo umbral
    drop_mask = df["cv_total"] < drop_threshold * baseline
    # Buscar el inicio del bloque continuo actual
    idx_end   = len(df) - 1
    idx_start = idx_end
    for i in range(idx_end, max(0, idx_end - lookback_stable * 2), -1):
        if drop_mask.iloc[i]:
            idx_start = i
        else:
            break
    t8_inicio_detected = pd.Timestamp(df.iloc[idx_start]["Fecha"])

    # Mapear a hora canonica mas cercana antes del inicio detectado
    canonical_start = _canonical_start(ts_now, t8_inicio_detected)
    elapsed_h = (ts_now - canonical_start).total_seconds() / 3600.0
    elapsed_h = max(0.0, elapsed_h)

    # Tipo de ventana segun hora canonica y duracion transcurrida
    tipo_ventana = _infer_window_type(canonical_start, elapsed_h)

    # Duracion restante = tipo_ventana - elapsed (para el simulador)
    restante_h = max(0.0, tipo_ventana - elapsed_h)
    # Redondear al RadioItem mas cercano disponible (0/2/4/8/12)
    opciones = [0, 2, 4, 8, 12]
    duracion_selector = min(opciones, key=lambda x: abs(x - restante_h)) if restante_h > 0.5 else 0

    drop_pct  = (1.0 - cv_now / baseline) * 100
    confianza = round(min(1.0, drop_pct / 50.0), 2)

    return {
        "t8_activo":        True,
        "elapsed_h":        round(elapsed_h, 1),
        "tipo_ventana":     tipo_ventana,
        "restante_h":       round(restante_h, 1),
        "duracion_selector": duracion_selector,
        "inicio":           canonical_start,
        "cv_actual":        round(cv_now, 0),
        "baseline":         round(baseline, 0),
        "drop_pct":         round(drop_pct, 1),
        "confianza":        confianza,
    }


def _no_t8(cv_now: float, baseline: float) -> dict:
    return {
        "t8_activo": False,
        "elapsed_h": 0.0, "tipo_ventana": 0, "restante_h": 0.0,
        "duracion_selector": 0,
        "inicio": None,
        "cv_actual": round(cv_now, 0),
        "baseline": round(baseline, 0),
        "drop_pct": 0.0,
        "confianza": 0.0,
    }


def _canonical_start(ts_now: pd.Timestamp, detected_start: pd.Timestamp) -> pd.Timestamp:
    """Hora canonica (8h/12h/14h) mas reciente que precede al inicio detectado."""
    for h in sorted(_T8_HOURS, reverse=True):
        candidate = ts_now.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate <= detected_start + timedelta(minutes=30):
            return candidate
    # Fallback: misma hora redondeada hacia abajo
    return detected_start.replace(minute=0, second=0, microsecond=0)


def _infer_window_type(start: pd.Timestamp, elapsed_h: float) -> int:
    """Infiere tipo de ventana (2/4/8/12h) segun hora de inicio y duracion."""
    h = start.hour
    if h == 8:
        return 12 if elapsed_h >= 8 else 8
    elif h == 12:
        return 4
    elif h == 14:
        return 2
    return 8  # fallback


# ── Cargador principal ─────────────────────────────────────────────────────────

def load_current_state() -> dict:
    """
    Lee el ultimo registro de ambos archivos PI y devuelve
    el estado operacional actual listo para inicializar el simulador.

    Retorna dict con:
      timestamp, pila_sag1, pila_sag2, rate_sag1_tph, rate_sag2_tph,
      ch1_on, ch2_on, sag_activos, bolas_sag1, bolas_sag2,
      cv315_tph, cv316_tph, t1_tph, t8_activo, t8_duracion_selector,
      t8_info (dict completo de deteccion T8).
    """
    df_ton = _load_tonelaje()
    df_est = _load_estados()

    last_ton = df_ton.iloc[-1]

    # Alinear estados al registro de tonelaje mas reciente
    if not df_est.empty:
        idx = (df_est["Fecha"] - pd.Timestamp(last_ton["Fecha"])).abs().idxmin()
        last_est = df_est.loc[idx]
    else:
        # Fallback a estados por defecto
        last_est = pd.Series({
            "CH1": True, "CH2": True, "SAG1": True, "SAG2": True,
            "mobo411": False, "mobo412": False, "mobo511": False, "mobo512": False,
        })

    # ── Bolas ──────────────────────────────────────────────────────────────────
    b411 = bool(last_est["mobo411"])
    b412 = bool(last_est["mobo412"])
    b511 = bool(last_est["mobo511"])
    b512 = bool(last_est["mobo512"])

    if b411 and b412:   bolas_sag1 = "ambas_411_412"
    elif b411:           bolas_sag1 = "solo_411"
    elif b412:           bolas_sag1 = "solo_412"
    else:                bolas_sag1 = "sin_bola"

    if b511 and b512:   bolas_sag2 = "ambas_511_512"
    elif b511:           bolas_sag2 = "solo_511"
    elif b512:           bolas_sag2 = "solo_512"
    else:                bolas_sag2 = "sin_bola"

    # ── SAG activos ────────────────────────────────────────────────────────────
    sag1_on = bool(last_est["SAG1"])
    sag2_on = bool(last_est["SAG2"])
    if sag1_on and sag2_on:  sag_activos = "ambos"
    elif sag1_on:             sag_activos = "sag1"
    elif sag2_on:             sag_activos = "sag2"
    else:                     sag_activos = "ambos"

    # ── Valores numericos (con fallback) ─────────────────────────────────────
    def _safe(val, default):
        try:
            v = float(val)
            return v if not np.isnan(v) else default
        except Exception:
            return default

    pila_sag1    = round(_safe(last_ton["pila_sag1"], 55.0), 1)
    pila_sag2    = round(_safe(last_ton["pila_sag2"], 55.0), 1)
    rate_sag1    = round(_safe(last_ton["rate_sag1"], 1236.0))
    rate_sag2    = round(_safe(last_ton["rate_sag2"], 2214.0))
    cv315_tph    = round(_safe(last_ton["cv315"], 1000.0))
    cv316_tph    = round(_safe(last_ton["cv316"], 2000.0))
    t1_raw       = _safe(last_ton["t1"], 0.0)
    t1_tph       = round(t1_raw if t1_raw > 100 else (cv315_tph + cv316_tph))

    # ── T8 ────────────────────────────────────────────────────────────────────
    t8_info = detect_t8(df_ton)

    # Clamp pilas a [0, 100]
    pila_sag1 = max(0.0, min(100.0, pila_sag1))
    pila_sag2 = max(0.0, min(100.0, pila_sag2))

    return {
        "timestamp":           last_ton["Fecha"],
        "pila_sag1":           pila_sag1,
        "pila_sag2":           pila_sag2,
        "rate_sag1_tph":       int(np.clip(rate_sag1, 500, 1600)),
        "rate_sag2_tph":       int(np.clip(rate_sag2, 1000, 2642)),
        "ch1_on":              bool(last_est["CH1"]),
        "ch2_on":              bool(last_est["CH2"]),
        "sag_activos":         sag_activos,
        "bolas_sag1":          bolas_sag1,
        "bolas_sag2":          bolas_sag2,
        "cv315_tph":           cv315_tph,
        "cv316_tph":           cv316_tph,
        "t1_tph":              t1_tph,
        "t8_activo":           t8_info["t8_activo"],
        "t8_duracion_selector": t8_info["duracion_selector"],
        "t8_info":             t8_info,
    }
