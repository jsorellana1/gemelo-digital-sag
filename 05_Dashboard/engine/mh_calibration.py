"""
mh_calibration.py — Módulo de calibración Bayesiana Metropolis-Hastings

Política de uso:
    - MH se ejecuta MENSUALMENTE (offline), NO en tiempo real.
    - El dashboard CONSUME los posteriors pre-calculados.
    - Los posteriors calibran el MC del dashboard.

Posteriors v1.0 — calculados 2026-06-30 con 70 eventos T8 (ago-2025 → jun-2026).
"""

from __future__ import annotations
import os
import sys
import numpy as np
from scipy import stats
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if getattr(sys, "frozen", False):
    _CACHE = os.path.join(os.path.dirname(sys.executable), "runtime_data", "Cache")
else:
    _CACHE = os.path.join(_ROOT, "01_Data", "Cache")

# ── Posteriors embebidos (v1.0, 2026-06-30) ──────────────────────────────────
# Calculados con MH Random Walk, 3000 iter, burnin=500, N=70 eventos T8.
# Fuente: outputs/excel/metropolis_hastings_results.xlsx hoja 3_MH_Posteriors

MH_META = {
    "version": "v1.0",
    "fecha_calibracion": "2026-06-30",
    "n_eventos": 70,
    "n_iter_mh": 3000,
    "burnin": 500,
    "periodo": "2025-08-01 → 2026-06-21",
    "acceptance_consumo_sag1": 0.704,
    "acceptance_consumo_sag2": 0.644,
    "acceptance_aut_sag1": 0.450,
    "acceptance_aut_sag2": 0.512,
}

# Parámetros posteriores calibrados MH
# consumo_sag1: pp de pila consumidos por hora cuando SAG1 activamente drena
MH_POSTERIOR_PARAMS = {
    "consumo_sag1": {"mu": 1.880, "sigma": 1.774, "p5": 0.27,  "p95": 4.92},
    "consumo_sag2": {"mu": 1.457, "sigma": 1.330, "p5": 0.12,  "p95": 3.71},
    "autonomia_sag1_mu": {"mu": 34.1, "sigma": 5.1, "p5": 26.2, "p95": 42.5},
    "autonomia_sag2_mu": {"mu": 35.1, "sigma": 3.9, "p5": 28.7, "p95": 41.7},
}

# Priors informativos (comparación)
MH_PRIOR_PARAMS = {
    "consumo_sag1": {"mu": 0.50, "sigma": 2.00},
    "consumo_sag2": {"mu": 0.50, "sigma": 2.00},
    "autonomia_sag1_mu": {"mu": 50.0, "sigma": 30.0},
    "autonomia_sag2_mu": {"mu": 50.0, "sigma": 30.0},
}

# Media histórica bruta (sin calibración MH)
HISTORICAL_CRUDE = {
    "consumo_sag1_mean": 0.985,
    "consumo_sag1_std": 2.055,
    "consumo_sag2_mean": 0.902,
    "consumo_sag2_std": 1.484,
}

# Riesgos calibrados (calculados con N=500 simulaciones MC+MH)
MH_RISK_CALIBRATED = {
    "p_critico_sag1_pct":   7.8,   # P(pila SAG1 < 15%)
    "p_critico_sag2_pct":  29.2,   # P(pila SAG2 < 18.2%)
    "p_agotamiento_sag1":   2.0,
    "p_agotamiento_sag2":   2.0,
    "p_emergencia_doble":   2.8,   # P(ambas críticas)
    "tph_sag1_post_mean":   690,
    "tph_sag2_post_mean":  1840,
}

MH_RISK_MC_CLASSIC = {
    "p_critico_sag1_pct":   5.6,
    "p_critico_sag2_pct":  24.0,
    "p_agotamiento_sag1":   1.2,
    "p_agotamiento_sag2":   1.0,
    "p_emergencia_doble":   1.8,
    "tph_sag1_post_mean":   672,
    "tph_sag2_post_mean":  1838,
}

# Riesgo por duración T8
MH_RISK_BY_DURATION = {
    2:  {"p_agt_sag1_mc": 0.0, "p_agt_sag1_mh": 0.0,
         "p_crit_sag1_mc": 0.8,  "p_crit_sag1_mh":  0.0},
    4:  {"p_agt_sag1_mc": 0.0, "p_agt_sag1_mh": 0.0,
         "p_crit_sag1_mc": 4.3,  "p_crit_sag1_mh":  5.8},
    8:  {"p_agt_sag1_mc":12.5, "p_agt_sag1_mh":10.0,
         "p_crit_sag1_mc":25.0, "p_crit_sag1_mh": 30.0},
    12: {"p_agt_sag1_mc":14.3, "p_agt_sag1_mh":22.0,
         "p_crit_sag1_mc":31.4, "p_crit_sag1_mh": 41.5},
}

# ── Funciones públicas ─────────────────────────────────────────────────────────

def load_latest_posteriors() -> dict:
    """Carga los posteriors MH más recientes.
    Primero intenta cargar desde archivos .npy en cache;
    si no existen, usa los parámetros embebidos.
    """
    post = {"meta": MH_META, "params": MH_POSTERIOR_PARAMS.copy()}
    try:
        post["samples_c1"] = np.load(os.path.join(_CACHE, "mh_post_c1.npy"))
        post["samples_c2"] = np.load(os.path.join(_CACHE, "mh_post_c2.npy"))
        post["samples_a1"] = np.load(os.path.join(_CACHE, "mh_post_a1.npy"))
        post["samples_a2"] = np.load(os.path.join(_CACHE, "mh_post_a2.npy"))
        post["from_cache"] = True
    except Exception:
        post["from_cache"] = False
    return post


def sample_posterior(variable: str, n: int = 1, rng: np.random.Generator | None = None) -> np.ndarray:
    """Muestrea del posterior MH para una variable dada.

    Args:
        variable: 'consumo_sag1' | 'consumo_sag2' | 'autonomia_sag1_mu' | 'autonomia_sag2_mu'
        n: número de muestras
        rng: generador numpy opcional

    Returns:
        array de n valores muestreados del posterior (todos positivos)
    """
    if rng is None:
        rng = np.random.default_rng()
    p = MH_POSTERIOR_PARAMS[variable]
    samples = rng.normal(p["mu"], p["sigma"], n)
    return np.clip(samples, 0.01, None)


def get_calibrated_consumption(sag: int = 1, rng: np.random.Generator | None = None) -> float:
    """Devuelve una muestra de consumo de pila calibrado MH (pp/h).

    Usar en MC para reemplazar np.random.normal(0.985, 2.055).
    """
    var = f"consumo_sag{sag}"
    return float(sample_posterior(var, n=1, rng=rng)[0])


def get_risk_summary() -> dict:
    """Devuelve el resumen de riesgos calibrados MH vs MC clásico."""
    return {
        "mc_classic": MH_RISK_MC_CLASSIC,
        "mh_calibrated": MH_RISK_CALIBRATED,
        "by_duration": MH_RISK_BY_DURATION,
        "meta": MH_META,
    }


def get_correction_factor(sag: int = 1) -> dict:
    """Factor de corrección MH vs media histórica bruta."""
    crude_mu = HISTORICAL_CRUDE[f"consumo_sag{sag}_mean"]
    mh_mu    = MH_POSTERIOR_PARAMS[f"consumo_sag{sag}"]["mu"]
    factor   = mh_mu / crude_mu if crude_mu > 0 else 1.0
    return {
        "crudo":    crude_mu,
        "calibrado": mh_mu,
        "factor":    factor,
        "delta_pct": (factor - 1) * 100,
    }


def update_posteriors_monthly(new_event_data: "pd.DataFrame | None" = None) -> dict:
    """Stub para actualización mensual de posteriors.

    En producción: corre MH con los nuevos eventos y actualiza data/cache/mh_post_*.npy.
    Actualmente devuelve los posteriors embebidos v1.0.
    """
    return load_latest_posteriors()
