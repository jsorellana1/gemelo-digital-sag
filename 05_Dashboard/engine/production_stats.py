"""
production_stats.py — Estadisticas historicas reales de produccion diaria
(SAG1/SAG2/MCONV/MUN), desde 01_Data/Cache/produccion_diaria_gpta.parquet
(ver 02_Analytics/Scripts/ingestion/load_produccion_diaria.py).

Uso exclusivo: percentiles (P10/P50/P90) y coeficiente de variacion (CV)
por activo, calculados sobre datos reales — NO se usa para modelar ley ni
recuperacion (ver 04_Reports/Technical/20260706_Analisis_Integracion_
Metalurgica* — sin evidencia de relacion TPH-ley, se descarto esa linea).
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if getattr(sys, "frozen", False):
    _CACHE = os.path.join(os.path.dirname(sys.executable), "runtime_data", "Cache")
else:
    _CACHE = os.path.join(_ROOT, "01_Data", "Cache")

_PARQUET = os.path.join(_CACHE, "produccion_diaria_gpta.parquet")

ASSET_COLUMNS = {
    "SAG1": "real_sag1",
    "SAG2": "real_sag2",
    "MCONV": "real_mconv",
    "MUN": "real_mun",
}
PAM_COLUMNS = {
    "SAG1": ("pam_sag1", "real_sag1"),
    "SAG2": ("pam_sag2", "real_sag2"),
    "MCONV": ("pam_mconv", "real_mconv"),
    "MUN": ("pam_mun", "real_mun"),
}

_df_cache: pd.DataFrame | None = None


def _load() -> pd.DataFrame | None:
    global _df_cache
    if _df_cache is not None:
        return _df_cache
    try:
        df = pd.read_parquet(_PARQUET)
        df = df[(~df["es_pronostico"]) & (~df["parada_total"])]
        _df_cache = df
    except Exception:
        _df_cache = pd.DataFrame()
    return _df_cache


@lru_cache(maxsize=8)
def get_asset_stats(asset: str) -> dict:
    """Stats reales (943 dias, 2024-01-01 -> hoy, excluye pronostico PAM y
    dias de parada total) para un activo: mean, std, cv (=std/mean),
    p10/p50/p90 diarios en toneladas/dia."""
    df = _load()
    col = ASSET_COLUMNS.get(asset)
    if df is None or df.empty or col not in df.columns:
        return {}
    s = df[col].dropna()
    if len(s) < 10:
        return {}
    mean = float(s.mean())
    std = float(s.std())
    return {
        "n_dias": int(len(s)),
        "mean_ton_dia": round(mean, 0),
        "std_ton_dia": round(std, 0),
        "cv": round(std / mean, 3) if mean > 0 else None,
        "p10_ton_dia": round(float(s.quantile(0.10)), 0),
        "p50_ton_dia": round(float(s.quantile(0.50)), 0),
        "p90_ton_dia": round(float(s.quantile(0.90)), 0),
    }


def get_all_stats() -> dict[str, dict]:
    return {asset: get_asset_stats(asset) for asset in ASSET_COLUMNS}


def cv_estabilidad_relativa(asset: str) -> float | None:
    """CV normalizado 0-1 (aprox) usable como penalizacion de estabilidad
    en el scoring del optimizador. None si no hay datos."""
    stats = get_asset_stats(asset)
    return stats.get("cv")


@lru_cache(maxsize=8)
def pam_compliance_stats(asset: str) -> dict:
    """Cumplimiento historico de PAM (plan) para un activo, sobre los
    dias reales disponibles (excluye pronostico y paradas totales).

    Responde con evidencia real (no supuesto): '¿cumplire el PAM?',
    '¿cual es la probabilidad de cumplir el PAM?', '¿cual es el deficit
    esperado?' — como frecuencia historica, no como prediccion del
    escenario simulado puntual (eso requeriria conectar el rate
    recomendado con el mes en curso, fuera de alcance de esta iteracion)."""
    df = _load()
    cols = PAM_COLUMNS.get(asset)
    if df is None or df.empty or cols is None:
        return {}
    pam_col, real_col = cols
    sub = df[[pam_col, real_col]].dropna()
    # Umbral > 1000 t/dia (no > 0): se encontro un registro con
    # pam_sag2=1.36e-13 (artefacto de redondeo de formula en la fuente,
    # no un plan real de "casi cero") que hacia explotar el ratio
    # real/pam a ~10^16% — un > 0 ingenuo no lo filtra.
    sub = sub[sub[pam_col] > 1000]
    if len(sub) < 10:
        return {}

    cumplimiento_pct = (sub[real_col] / sub[pam_col]) * 100.0
    deficit_ton = (sub[pam_col] - sub[real_col]).clip(lower=0)
    p_cumple = float((sub[real_col] >= sub[pam_col]).mean())

    return {
        "n_dias": int(len(sub)),
        "p_cumple_historico": round(p_cumple, 3),
        "cumplimiento_medio_pct": round(float(cumplimiento_pct.mean()), 1),
        "cumplimiento_p10_pct": round(float(cumplimiento_pct.quantile(0.10)), 1),
        "cumplimiento_p90_pct": round(float(cumplimiento_pct.quantile(0.90)), 1),
        "deficit_medio_ton_dia": round(float(deficit_ton.mean()), 0),
        "deficit_p90_ton_dia": round(float(deficit_ton.quantile(0.90)), 0),
    }


@lru_cache(maxsize=16)
def get_pam_monthly_projection(asset: str, dias_mes: int = 30) -> dict:
    """Proyeccion de cumplimiento mensual (CAMBIO 7, UX/UI v2 JdS,
    2026-07-07): convierte PAM mensual -> meta diaria -> banda P10/P50/P90
    de produccion acumulada usando la distribucion diaria REAL (mean/std
    de get_asset_stats) y el teorema central del limite (suma de N dias
    ~ Normal(N*mu, sqrt(N)*sigma) — aproximacion estandar, N=30 es
    suficientemente grande). Responde '¿voy a cumplir el mes?' con
    evidencia historica, no con el escenario puntual simulado.

    No usa la fecha real del mes en curso (no hay una fuente de "dia de
    hoy dentro del mes de PAM" en el proyecto) — proyecta el mes completo
    de `dias_mes` dias desde cero, como referencia de capacidad, no como
    seguimiento intra-mes en tiempo real."""
    import math

    stats = get_asset_stats(asset)
    pam = pam_compliance_stats(asset)
    if not stats or not pam:
        return {}

    mu = stats["mean_ton_dia"]
    sigma = stats["std_ton_dia"]
    df = _load()
    pam_col, _ = PAM_COLUMNS[asset]
    meta_diaria = float(df[df[pam_col] > 1000][pam_col].mean())
    meta_mensual = meta_diaria * dias_mes

    dias = np.arange(1, dias_mes + 1)
    p50_cum = mu * dias
    p10_cum = mu * dias - 1.2816 * sigma * np.sqrt(dias)   # z(0.10)
    p90_cum = mu * dias + 1.2816 * sigma * np.sqrt(dias)

    sigma_total = sigma * np.sqrt(dias_mes)
    if sigma_total > 0:
        z = (meta_mensual - mu * dias_mes) / sigma_total
        prob_cumple = 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
    else:
        prob_cumple = 1.0 if mu * dias_mes >= meta_mensual else 0.0

    return {
        "dias": dias.tolist(),
        "p10_cum": p10_cum.tolist(),
        "p50_cum": p50_cum.tolist(),
        "p90_cum": p90_cum.tolist(),
        "meta_diaria": round(meta_diaria, 0),
        "meta_mensual": round(meta_mensual, 0),
        "prob_cumple_mes": round(max(0.0, min(1.0, prob_cumple)), 3),
    }
