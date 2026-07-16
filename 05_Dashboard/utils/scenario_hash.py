"""
scenario_hash.py — Sincronización recomendación ↔ escenario
(2026-07-09).

Causa raíz del bug corregido: `apply_ideal_params` (callback de
"GENERAR RECOMENDACION") escribe los TPH recomendados en
ctrl-rate-sag1/2 UNA VEZ, al click, leyendo el resto del escenario
(T8, pila, mantenciones...) como `State`. `update_simulation` (el
gráfico) SI es reactivo a esos mismos parámetros. Si el usuario cambia
T8 despues de generar la recomendación, el gráfico se recalcula con el
T8 nuevo pero sigue usando los TPH viejos, sin ninguna señal de que ya
no corresponden al escenario mostrado.

Este módulo da a AMBOS callbacks una única forma de describir "a qué
escenario pertenece este cálculo": un dict plano + un hash corto. Un
solo helper reusado por los dos — nunca se duplica la lista de campos
que definen un escenario.
"""
from __future__ import annotations

import hashlib
import json


def build_scenario_dict(
    *,
    duracion_t8: float, pila1: float, pila2: float,
    rate_sag1_tph: float | None, rate_sag2_tph: float | None,
    bolas_sag1: str, bolas_sag2: str,
    sag1_on: bool, sag2_on: bool, ch1_on: bool, ch2_on: bool,
    c315: str, c316: str, horizonte: float,
    cv_mode: str, cv315_manual: float, cv316_manual: float,
    t1_mode: str, t1_manual: float, t3_frac: float, distribucion_t1: str,
    turno: str, mantenciones: dict, tolerancia_riesgo: str,
) -> dict:
    """Dict plano JSON-serializable con TODO parámetro que afecta
    físicamente la simulación. Deliberadamente SIN timestamp (rompería
    el hash) y SIN controles cosméticos (sim-main-view, btn-reset-zoom,
    modo de vista) — esos no cambian qué se simula, solo qué se
    muestra."""
    return {
        "duracion_t8": round(float(duracion_t8), 2),
        "pila1": round(float(pila1), 2),
        "pila2": round(float(pila2), 2),
        "rate_sag1_tph": round(float(rate_sag1_tph), 1) if rate_sag1_tph is not None else None,
        "rate_sag2_tph": round(float(rate_sag2_tph), 1) if rate_sag2_tph is not None else None,
        "bolas_sag1": bolas_sag1, "bolas_sag2": bolas_sag2,
        "sag1_on": bool(sag1_on), "sag2_on": bool(sag2_on),
        "ch1_on": bool(ch1_on), "ch2_on": bool(ch2_on),
        "c315": c315, "c316": c316,
        "horizonte": round(float(horizonte), 2),
        "cv_mode": cv_mode,
        "cv315_manual": round(float(cv315_manual), 1) if cv315_manual is not None else None,
        "cv316_manual": round(float(cv316_manual), 1) if cv316_manual is not None else None,
        "t1_mode": t1_mode,
        "t1_manual": round(float(t1_manual), 1) if t1_manual is not None else None,
        "t3_frac": round(float(t3_frac), 4) if t3_frac is not None else None,
        "distribucion_t1": distribucion_t1,
        "turno": turno,
        "mantenciones": mantenciones or {},
        "tolerancia_riesgo": tolerancia_riesgo,
    }


def hash_scenario(scenario: dict) -> str:
    """Hash corto y estable — mismo dict siempre produce el mismo hash,
    independiente del orden de construcción (sort_keys=True)."""
    raw = json.dumps(scenario, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
