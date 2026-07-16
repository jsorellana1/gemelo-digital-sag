"""
variability_metrics.py — Metricas de variabilidad de TPH para SAG1/SAG2.

Opera sobre las series ya producidas por engine/ode_model.py::simulate_ode()
(tph_sag1, tph_sag2, time) — no requiere cambios al ODE ni nueva simulacion.

Variabilidad = std(TPH) cuando operando (ver 08_Skills/skill_molienda_sag.md
seccion 3). CV = std/mean, mismo formula que engine/production_stats.py
(ahi calculado sobre produccion diaria historica; aqui sobre la serie
simulada de un escenario).
"""
from __future__ import annotations

import numpy as np

TPH_OPERANDO_THRESHOLD = 50.0  # ver skill_molienda_sag.md: TPH <= 50 = detenido/dato invalido


def _operando(tph: np.ndarray) -> np.ndarray:
    return tph > TPH_OPERANDO_THRESHOLD


def _window_mask(time_h: np.ndarray, duracion_t8_h: float, window: str) -> np.ndarray:
    """
    window: 'pre' | 'durante' | 'post' | 'sin_ventana'
    'sin_ventana' = toda la serie cuando duracion_t8_h <= 0.
    """
    if duracion_t8_h <= 0 or window == "sin_ventana":
        return np.ones_like(time_h, dtype=bool)
    if window == "durante":
        return (time_h >= 0) & (time_h < duracion_t8_h)
    if window == "post":
        return time_h >= duracion_t8_h
    # 'pre': no existe pre-ventana dentro de un horizonte que arranca en t=0
    # con T8 ya activo desde el inicio (ver ode_model.py::simulate_ode) —
    # se retorna mascara vacia en vez de asumir datos que no existen.
    return np.zeros_like(time_h, dtype=bool)


def compute_tph_variability(
    tph: list[float] | np.ndarray,
    time_h: list[float] | np.ndarray,
    duracion_t8_h: float = 0.0,
    window: str = "sin_ventana",
) -> dict:
    """
    Calcula variabilidad de una serie TPH (SAG1, SAG2 o total) para la
    ventana temporal indicada.

    Retorna dict con: cv, std, mean, iqr, max_salto (maximo cambio absoluto
    entre pasos consecutivos), n_cambios_setpoint (cambios > 1% del valor
    medio, proxy de "cambio de setpoint" sobre una serie de 5 min), n_muestras.
    Si no hay muestras "operando" (TPH > 50) en la ventana, retorna None en
    los campos numericos y explicita la razon.
    """
    tph_arr = np.asarray(tph, dtype=float)
    time_arr = np.asarray(time_h, dtype=float)

    mask_window = _window_mask(time_arr, duracion_t8_h, window)
    mask_op = _operando(tph_arr)
    mask = mask_window & mask_op

    if mask.sum() < 2:
        return {
            "cv": None, "std": None, "mean": None, "iqr": None,
            "max_salto": None, "n_cambios_setpoint": None,
            "n_muestras": int(mask.sum()),
            "razon": f"Menos de 2 muestras 'operando' (TPH>{TPH_OPERANDO_THRESHOLD:.0f}) en ventana '{window}'",
        }

    serie = tph_arr[mask]
    mean = float(serie.mean())
    std = float(serie.std())
    q75, q25 = np.percentile(serie, [75, 25])
    iqr = float(q75 - q25)
    saltos = np.abs(np.diff(serie))
    max_salto = float(saltos.max()) if saltos.size > 0 else 0.0
    umbral_cambio = max(mean * 0.01, 1e-6)
    n_cambios = int((saltos > umbral_cambio).sum())

    return {
        "cv": round(std / mean, 4) if mean > 0 else None,
        "std": round(std, 2),
        "mean": round(mean, 2),
        "iqr": round(iqr, 2),
        "max_salto": round(max_salto, 2),
        "n_cambios_setpoint": n_cambios,
        "n_muestras": int(mask.sum()),
        "razon": "",
    }


def compute_variability_report(sim_result: dict) -> dict:
    """
    Construye el reporte completo pedido (Fase 3): CV_TPH_SAG1/SAG2/TOTAL
    para pre/durante/post/sin_ventana, a partir del dict que retorna
    simulate_ode() (debe incluir 'time', 'tph_sag1', 'tph_sag2', 'tph_total').

    'duracion_t8_h' se toma de sim_result si esta presente (0.0 si no).
    """
    time_h = sim_result["time"]
    duracion_t8_h = float(sim_result.get("duracion_t8_h", 0.0))
    windows = ["sin_ventana"] if duracion_t8_h <= 0 else ["durante", "post"]

    series = {
        "SAG1": sim_result["tph_sag1"],
        "SAG2": sim_result["tph_sag2"],
        "TOTAL": sim_result["tph_total"],
    }

    report = {}
    for asset, serie in series.items():
        report[asset] = {
            w: compute_tph_variability(serie, time_h, duracion_t8_h, w)
            for w in windows
        }
    return report
