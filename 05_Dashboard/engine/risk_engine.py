"""
risk_engine.py — Calculo del Indice de Resiliencia Operacional (IRO)
"""

from __future__ import annotations
import numpy as np

from engine.circuit_state import AutonomyContext, DRAINING, AT_CRITICAL_LEVEL

# ── Fase 1.1 del roadmap de cierre (2026-07-15, ver 04_Reports/Technical/
# 20260715_Roadmap_Cierre_Simulador_Operacional.md): sub-scores dinamico/
# historico aditivos. Sin dato para recalibrar los pesos de WEIGHTS
# (0.30 para "autonomia" ya combina ambos conceptos desde antes de esta
# migracion), asi que NO se reparte ese peso entre dos sub-scores nuevos
# — el IRO total queda exactamente igual (mismo calculo de siempre) y
# estos dos sub-scores se agregan solo como diagnostico aditivo cuando
# el llamador pasa AutonomyContext.
_VULN_SCORE = {"BAJA": 100.0, "MEDIA": 70.0, "ALTA": 40.0, "CRITICA": 10.0}


def _historical_vulnerability_score(ctx1: AutonomyContext, ctx2: AutonomyContext) -> float:
    return min(_VULN_SCORE[ctx1.historical_vulnerability], _VULN_SCORE[ctx2.historical_vulnerability])


def _dynamic_depletion_score(ctx1: AutonomyContext, ctx2: AutonomyContext,
                              norm_h: float) -> float:
    scores = []
    for ctx in (ctx1, ctx2):
        if ctx.dynamic_status == AT_CRITICAL_LEVEL:
            scores.append(0.0)
        elif ctx.dynamic_status == DRAINING:
            scores.append(max(0.0, min(100.0, ctx.dynamic_hours / norm_h * 100.0)))
        else:
            # FILLING / STABLE / SAG_OFF: sin riesgo inmediato de agotamiento.
            scores.append(100.0)
    return min(scores)


# ── Pesos IRO ──────────────────────────────────────────────────────────────────
WEIGHTS = {
    "inventario": 0.25,
    "autonomia":  0.30,
    "rate":       0.20,
    "t8":         0.15,
    "correa":     0.10,
}

AUTONOMIA_NORM_H = 4.0  # referencia para normalizar autonomia a 100

# Bounds recomendados (fraccion P90) para chequear rate
RATE_BOUNDS_NORMAL = {
    "SAG1": (72.0, 95.0),
    "SAG2": (82.0, 100.0),
}


def compute_iro(
    pile_sag1_pct: float,
    pile_sag2_pct: float,
    autonomia_sag1_h: float,
    autonomia_sag2_h: float,
    rate_sag1_pct: float,
    rate_sag2_pct: float,
    duracion_t8_h: float,
    correa315_estado: str,
    correa316_estado: str,
    chancado_cap_tph: float = 4000.0,
    sag1_activo: bool = True,
    sag2_activo: bool = True,
    t1_restriccion: bool = False,
    # Fase 1.1 del roadmap de cierre (2026-07-15) — opcionales, no cambian
    # el calculo del IRO total. Si ambos vienen informados, se agregan
    # dynamic_depletion_score/historical_vulnerability_score al dict de
    # retorno como diagnostico adicional (ver comentario junto a
    # _dynamic_depletion_score arriba).
    autonomy_context_sag1: AutonomyContext | None = None,
    autonomy_context_sag2: AutonomyContext | None = None,
) -> dict:
    """
    Calcula IRO y sub-scores individuales.
    Retorna dict con: iro, inventario_score, autonomia_score, rate_score,
                      t8_score, correa_score, color, y (si se pasan
                      autonomy_context_sag1/2) dynamic_depletion_score/
                      historical_vulnerability_score como diagnostico
                      aditivo — no alteran el iro total.
    """
    # 1. Inventario: min de ambas pilas normalizado
    inventario_score = min(pile_sag1_pct, pile_sag2_pct)
    inventario_score = max(0.0, min(100.0, inventario_score))

    # 2. Autonomia: min autonomia normalizado a AUTONOMIA_NORM_H
    min_auton = min(autonomia_sag1_h, autonomia_sag2_h)
    autonomia_score = min(100.0, min_auton / AUTONOMIA_NORM_H * 100.0)

    # 3. Rate: SAG inactivo = 0 TPH efectivo (capacidad perdida)
    eff_r1 = rate_sag1_pct if sag1_activo else 0.0
    eff_r2 = rate_sag2_pct if sag2_activo else 0.0
    rate_score = _rate_score(eff_r1, "SAG1") * 0.5 + _rate_score(eff_r2, "SAG2") * 0.5

    # 4. T8: penalizar por duracion
    if duracion_t8_h <= 0:
        t8_score = 100.0
    else:
        t8_score = max(0.0, 100.0 - duracion_t8_h * 8.0)

    # 5. Correa: 100 si ambas activas, 50 si una reducida/inactiva, 0 si ambas fuera
    correa_score = _correa_score(correa315_estado, correa316_estado)

    iro = (
        WEIGHTS["inventario"] * inventario_score
        + WEIGHTS["autonomia"] * autonomia_score
        + WEIGHTS["rate"] * rate_score
        + WEIGHTS["t8"] * t8_score
        + WEIGHTS["correa"] * correa_score
    )

    # Capacidad de molienda reducida: 1 SAG activo = tope 60, 0 SAGs = tope 15
    n_sags = int(sag1_activo) + int(sag2_activo)
    if n_sags == 0:
        iro = min(iro, 15.0)
    elif n_sags == 1:
        iro = min(iro, 60.0)

    # T1 restringido: CV demanda > T1 disponible → penalizar -15 puntos
    if t1_restriccion:
        iro = max(0.0, iro - 15.0)

    # Chancado detenido = sin alimentacion al circuito: IRO tope en 30 (CRITICO)
    if chancado_cap_tph <= 0.0:
        iro = min(iro, 30.0)
    elif chancado_cap_tph < 2000.0:
        penalty = (1.0 - chancado_cap_tph / 2000.0) * 25.0
        iro = max(0.0, iro - penalty)

    result = {
        "iro": round(iro, 1),
        "inventario_score": round(inventario_score, 1),
        "autonomia_score": round(autonomia_score, 1),
        "rate_score": round(rate_score, 1),
        "t8_score": round(t8_score, 1),
        "correa_score": round(correa_score, 1),
        "color": iro_color(iro),
    }
    if autonomy_context_sag1 is not None and autonomy_context_sag2 is not None:
        result["dynamic_depletion_score"] = round(
            _dynamic_depletion_score(autonomy_context_sag1, autonomy_context_sag2, AUTONOMIA_NORM_H), 1)
        result["historical_vulnerability_score"] = round(
            _historical_vulnerability_score(autonomy_context_sag1, autonomy_context_sag2), 1)
    return result


def _rate_score(rate_pct: float, asset: str) -> float:
    lo, hi = RATE_BOUNDS_NORMAL.get(asset, (72.0, 95.0))
    if lo <= rate_pct <= hi:
        return 100.0
    # Penalizacion proporcional a la desviacion
    if rate_pct < lo:
        penalty = (lo - rate_pct) * 2.5
    else:
        penalty = (rate_pct - hi) * 3.0
    return max(0.0, 100.0 - penalty)


def _correa_score(c315: str, c316: str) -> float:
    score_map = {"activa": 1.0, "reducida": 0.5, "inactiva": 0.0}
    s315 = score_map.get(c315, 1.0)
    s316 = score_map.get(c316, 1.0)
    return (s315 + s316) / 2.0 * 100.0


def iro_color(iro: float) -> str:
    if iro > 80:
        return "#27AE60"   # verde
    if iro > 60:
        return "#F39C12"   # amarillo
    if iro > 40:
        return "#E67E22"   # naranja
    return "#C0392B"        # rojo


def compute_iro_series(sim_result: dict) -> list[float]:
    """
    Calcula serie temporal del IRO a partir del resultado de simulate_ode.
    Usa rate constante (el del primer paso) y correa constante (simplificacion).
    """
    n = len(sim_result["time"])
    iro_series = []
    for i in range(n):
        iro_i = simple_iro(
            pile_sag1_pct=sim_result["pile_sag1"][i],
            pile_sag2_pct=sim_result["pile_sag2"][i],
            autonomia_sag1_h=sim_result["autonomia_sag1"][i],
            autonomia_sag2_h=sim_result["autonomia_sag2"][i],
        )
        iro_series.append(iro_i)
    return iro_series


def simple_iro(
    pile_sag1_pct: float,
    pile_sag2_pct: float,
    autonomia_sag1_h: float,
    autonomia_sag2_h: float,
) -> float:
    """IRO simplificado solo con inventario y autonomia (para series temporales)."""
    inv = min(pile_sag1_pct, pile_sag2_pct)
    auton = min(min(autonomia_sag1_h, autonomia_sag2_h) / AUTONOMIA_NORM_H * 100.0, 100.0)
    return round(WEIGHTS["inventario"] / (WEIGHTS["inventario"] + WEIGHTS["autonomia"]) * inv
                 + WEIGHTS["autonomia"] / (WEIGHTS["inventario"] + WEIGHTS["autonomia"]) * auton, 1)
