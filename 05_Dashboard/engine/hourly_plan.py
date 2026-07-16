"""
hourly_plan.py — Plan operacional por hora (Fase 7/C del reenfoque
autonomia/armonia): Hora | CV315 | CV316 | SAG1 TPH | SAG2 TPH | MoBos |
Autonomia | Estado.

Deriva la tabla directamente de las series de 5 min que simulate_ode() ya
produce (engine/ode_model.py) — no ejecuta una simulacion nueva ni cambia
el ODE, solo re-muestrea (resample) a bloques horarios.

Prioriza continuidad/factibilidad: el valor de cada hora es el promedio
del bloque (no el pico puntual), consistente con la penalizacion de
transitorios (transient_penalty.py) que castiga decisiones que saltan de
un extremo a otro dentro del mismo bloque.
"""
from __future__ import annotations

import numpy as np

from engine.ode_model import CAP_TON, CRITICAL_PCT
from engine.circuit_state import classify_dynamic_autonomy, classify_historical_vulnerability

UMBRAL_AUTONOMIA_CRITICO_H = 1.0
UMBRAL_AUTONOMIA_ATENCION_H = 3.0


def _estado(min_autonomia_h: float) -> str:
    """Etiqueta semantica cruda (sin color) — components/cards.py mapea a
    semaforo verde/amarillo/rojo, siguiendo la separacion ya usada en el
    proyecto (engine calcula, cards.py colorea)."""
    if min_autonomia_h < UMBRAL_AUTONOMIA_CRITICO_H:
        return "critico"
    elif min_autonomia_h < UMBRAL_AUTONOMIA_ATENCION_H:
        return "atencion"
    return "normal"


def build_hourly_plan(sim_result: dict, block_hours: float = 1.0) -> list[dict]:
    """
    Construye el plan horario a partir del dict retornado por
    simulate_ode(). Cada fila resume un bloque de `block_hours` horas.

    Retorna lista de dicts con: hora (inicio del bloque), cv315_tph,
    cv316_tph, sag1_tph, sag2_tph, mobos_sag1 (0-2, redondeado desde
    bola411+bola412), mobos_sag2, autonomia_sag1_h, autonomia_sag2_h,
    autonomia_min_h, estado.
    """
    time_h = np.asarray(sim_result["time"], dtype=float)
    if time_h.size == 0:
        return []

    bloque = np.floor(time_h / block_hours).astype(int)
    n_bloques = int(bloque.max()) + 1

    cv315 = np.asarray(sim_result["cv315"], dtype=float)
    cv316 = np.asarray(sim_result["cv316"], dtype=float)
    tph1 = np.asarray(sim_result["tph_sag1"], dtype=float)
    tph2 = np.asarray(sim_result["tph_sag2"], dtype=float)
    auton1 = np.asarray(sim_result["autonomia_sag1"], dtype=float)
    auton2 = np.asarray(sim_result["autonomia_sag2"], dtype=float)
    bola411 = np.asarray(sim_result["bola411"], dtype=float)
    bola412 = np.asarray(sim_result["bola412"], dtype=float)
    bola511 = np.asarray(sim_result["bola511"], dtype=float)
    bola512 = np.asarray(sim_result["bola512"], dtype=float)

    # Fase 1.4 del roadmap de cierre (2026-07-15, ver 04_Reports/Technical/
    # 20260715_Roadmap_Cierre_Simulador_Operacional.md): estado dinamico +
    # vulnerabilidad historica POR HORA, reusando los clasificadores de la
    # Etapa 1 sobre las series ya disponibles (sin ejecutar una simulacion
    # nueva ni tocar simulate_ode). Aditivo: si el sim_result no trae
    # pile_sag1/2 (p.ej. un dict sintetico minimo en un test), estas
    # columnas quedan en None por bloque en vez de fallar.
    pile1 = np.asarray(sim_result.get("pile_sag1", []), dtype=float)
    pile2 = np.asarray(sim_result.get("pile_sag2", []), dtype=float)
    _con_pila = pile1.size == time_h.size and pile2.size == time_h.size

    plan = []
    for b in range(n_bloques):
        mask = bloque == b
        if not mask.any():
            continue
        a1_h = float(auton1[mask].mean())
        a2_h = float(auton2[mask].mean())
        f_in1, f_out1 = float(cv315[mask].mean()), float(tph1[mask].mean())
        f_in2, f_out2 = float(cv316[mask].mean()), float(tph2[mask].mean())

        row = {
            "hora": b * block_hours,
            "cv315_tph": round(f_in1, 1),
            "cv316_tph": round(f_in2, 1),
            "sag1_tph": round(f_out1, 1),
            "sag2_tph": round(f_out2, 1),
            "mobos_sag1": round(float((bola411[mask] + bola412[mask]).mean())),
            "mobos_sag2": round(float((bola511[mask] + bola512[mask]).mean())),
            "autonomia_sag1_h": round(a1_h, 2),
            "autonomia_sag2_h": round(a2_h, 2),
            "autonomia_min_h": round(min(a1_h, a2_h), 2),
            "estado": _estado(min(a1_h, a2_h)),
        }

        if _con_pila:
            p1_ton = float(pile1[mask].mean()) / 100.0 * CAP_TON["SAG1"]
            p2_ton = float(pile2[mask].mean()) / 100.0 * CAP_TON["SAG2"]
            min1_ton = CRITICAL_PCT["SAG1"] / 100.0 * CAP_TON["SAG1"]
            min2_ton = CRITICAL_PCT["SAG2"] / 100.0 * CAP_TON["SAG2"]
            dyn1 = classify_dynamic_autonomy(p1_ton, min1_ton, f_in1, f_out1)
            dyn2 = classify_dynamic_autonomy(p2_ton, min2_ton, f_in2, f_out2)
            row.update({
                "dynamic_status_sag1": dyn1.status,
                "dynamic_status_sag2": dyn2.status,
                "net_balance_sag1_tph": round(dyn1.net_drain_rate_tph, 1),
                "net_balance_sag2_tph": round(dyn2.net_drain_rate_tph, 1),
                "dynamic_autonomy_sag1_h": round(dyn1.hours, 2) if dyn1.hours is not None else None,
                "dynamic_autonomy_sag2_h": round(dyn2.hours, 2) if dyn2.hours is not None else None,
                "historical_vulnerability_sag1": classify_historical_vulnerability(a1_h, "SAG1"),
                "historical_vulnerability_sag2": classify_historical_vulnerability(a2_h, "SAG2"),
            })
        else:
            row.update({
                "dynamic_status_sag1": None, "dynamic_status_sag2": None,
                "net_balance_sag1_tph": None, "net_balance_sag2_tph": None,
                "dynamic_autonomy_sag1_h": None, "dynamic_autonomy_sag2_h": None,
                "historical_vulnerability_sag1": None, "historical_vulnerability_sag2": None,
            })

        plan.append(row)
    return plan
