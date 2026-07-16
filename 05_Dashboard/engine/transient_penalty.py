"""
transient_penalty.py — Penalizacion por transitorios (Fase 4/C del
reenfoque autonomia/armonia): evita planes con saltos de rate como
1450 -> 1100 -> 1500 -> 1200 TPH.

Regla operacional (dada por el usuario): cambio maximo recomendado por
bloque horario = +-10% del P90 historico, salvo emergencia. Reusa
SAG1_P90/SAG2_P90 ya definidos en engine/optimizer_v3.py — no se
reinventan anclas historicas nuevas.
"""
from __future__ import annotations

import numpy as np

UMBRAL_CAMBIO_BRUSCO_PCT_P90 = 0.10


def compute_transient_penalty(
    rate_series_tph: list[float] | np.ndarray,
    time_h: list[float] | np.ndarray,
    p90_ref: float,
    block_hours: float = 1.0,
) -> dict:
    """
    Calcula penalizacion de transitorios [0, 100] para una serie de rate
    (TPH) de un SAG durante la simulacion.

    Un "cambio brusco" es |delta rate| entre pasos consecutivos > 10% del
    P90 de referencia. Se penaliza mas fuerte cuando el cambio brusco
    ocurre dentro del mismo bloque horario (mismo turno/hora de decision)
    que el paso anterior, ya que ahi no deberia haber redecisiones.

    Retorna: penalty_score (0-100), n_cambios_bruscos, n_cambios_mismo_bloque,
    max_salto_pct_p90, n_pasos.
    """
    serie = np.asarray(rate_series_tph, dtype=float)
    tiempo = np.asarray(time_h, dtype=float)

    if serie.size < 2 or p90_ref <= 0:
        return {
            "penalty_score": 0.0, "n_cambios_bruscos": 0,
            "n_cambios_mismo_bloque": 0, "max_salto_pct_p90": 0.0,
            "n_pasos": max(serie.size - 1, 0),
            "razon": "Serie insuficiente o P90 de referencia invalido" if serie.size < 2 else "",
        }

    deltas = np.diff(serie)
    umbral_abs = UMBRAL_CAMBIO_BRUSCO_PCT_P90 * p90_ref
    es_brusco = np.abs(deltas) > umbral_abs

    bloque = np.floor(tiempo / block_hours).astype(int)
    mismo_bloque = bloque[1:] == bloque[:-1]
    bruscos_intra_bloque = es_brusco & mismo_bloque

    n_pasos = int(deltas.size)
    n_bruscos = int(es_brusco.sum())
    n_bruscos_bloque = int(bruscos_intra_bloque.sum())
    max_salto_pct_p90 = float(np.abs(deltas).max() / p90_ref * 100.0) if n_pasos > 0 else 0.0

    frac_bruscos = n_bruscos / n_pasos if n_pasos > 0 else 0.0
    # Un cambio brusco dentro del mismo bloque horario pesa el doble que uno
    # entre bloques (redecidir dentro del turno es peor que ajustar al
    # cambiar de bloque de planificacion).
    penalty_raw = frac_bruscos * 100.0 + (n_bruscos_bloque / n_pasos * 100.0 if n_pasos > 0 else 0.0)
    penalty_score = min(100.0, penalty_raw)

    return {
        "penalty_score": round(penalty_score, 2),
        "n_cambios_bruscos": n_bruscos,
        "n_cambios_mismo_bloque": n_bruscos_bloque,
        "max_salto_pct_p90": round(max_salto_pct_p90, 1),
        "n_pasos": n_pasos,
        "razon": "",
    }


def combined_transient_penalty(
    rate1_tph: list[float] | np.ndarray,
    rate2_tph: list[float] | np.ndarray,
    time_h: list[float] | np.ndarray,
    p90_sag1: float,
    p90_sag2: float,
    block_hours: float = 1.0,
) -> float:
    """Promedio simple de la penalizacion de SAG1 y SAG2 — valor unico
    (0-100) listo para inyectar en optimizer_v5.score_v5_candidate como
    'transient_penalty_score'."""
    p1 = compute_transient_penalty(rate1_tph, time_h, p90_sag1, block_hours)
    p2 = compute_transient_penalty(rate2_tph, time_h, p90_sag2, block_hours)
    return round((p1["penalty_score"] + p2["penalty_score"]) / 2.0, 2)
