"""
quick_wins.py — Catalogo fijo de acciones operacionales simples (seccion 13
del brief de rediseno JdS) evaluadas contra el escenario base ya simulado.

Cada accion es una perturbacion pequena y explicable del escenario actual
(reducir rate un tiempo, mover CV315/CV316, reducir T3, cambiar bolas) — se
reutiliza engine.simulator.simulate_scenario_cached (misma funcion que usa
toda la pagina) para simular escenario_actual vs escenario_actual+accion, y
se compara. No hay optimizacion nueva: es una evaluacion directa de un
catalogo fijo, ordenada por beneficio/costo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from engine.simulator import simulate_scenario_cached
from engine.ode_model import P90


@dataclass
class QuickWin:
    titulo: str
    descripcion: str
    # Fase 1.3 del roadmap de cierre (2026-07-15, ver 04_Reports/Technical/
    # 20260715_Roadmap_Cierre_Simulador_Operacional.md): "delta_autonomia_h"
    # era ambiguo — en realidad medía la mejora del mínimo de la
    # TRAYECTORIA de autonomía preventiva histórica (compute_autonomia),
    # nunca balance neto real. Se renombra explícitamente a
    # delta_historical_buffer_h y se agrega delta_dynamic_autonomy_h como
    # métrica nueva y genuinamente distinta (mejora en la autonomía
    # dinámica del ESTADO FINAL, balance neto real).
    delta_historical_buffer_h: float
    delta_dynamic_autonomy_h: float
    delta_riesgo_vaciado_pp: float  # puntos porcentuales, negativo = mejora
    impacto_produccion_pct: float   # negativo = pierde produccion
    tiempo_requerido_h: float
    beneficio_costo: float = field(init=False)

    def __post_init__(self):
        costo = max(abs(self.impacto_produccion_pct), 0.1)
        # El ranking beneficio/costo sigue anclado al colchón preventivo
        # (misma base que antes de esta fase, sin recalibrar sin datos) —
        # delta_dynamic_autonomy_h se expone como información adicional,
        # no reemplaza el criterio de orden existente.
        self.beneficio_costo = self.delta_historical_buffer_h / costo


_SIN_RIESGO_DINAMICO_H = 999.0  # sentinel: mismo criterio que bottleneck.py


def _autonomia_min(sim: dict) -> float:
    a1 = np.array(sim.get("autonomia_sag1") or [0.0])
    a2 = np.array(sim.get("autonomia_sag2") or [0.0])
    return float(min(a1.min(), a2.min()))


def _dynamic_autonomia_min(sim: dict) -> float:
    """Mínimo de la autonomía dinámica (balance neto real) del estado
    final entre ambos SAG. `None` (FILLING/STABLE/SAG_OFF — sin riesgo de
    agotamiento bajo el balance actual) se trata como un valor alto
    (sin restricción), nunca como 0 — mismo criterio que ya usa
    `engine/bottleneck.py` para su sentinel de "sin dato/sin riesgo"."""
    h1 = sim.get("dynamic_net_autonomy_sag1_h")
    h2 = sim.get("dynamic_net_autonomy_sag2_h")
    v1 = h1 if h1 is not None else _SIN_RIESGO_DINAMICO_H
    v2 = h2 if h2 is not None else _SIN_RIESGO_DINAMICO_H
    return float(min(v1, v2))


def _riesgo_vaciado_pct(sim: dict) -> float:
    """Proxy simple: fraccion del horizonte con autonomia<=0 en cualquiera
    de las dos pilas (sin Monte Carlo — es una evaluacion determinista
    rapida para ranking de quick wins, no un reemplazo de adaptive_mc_eval)."""
    a1 = np.array(sim.get("autonomia_sag1") or [1.0])
    a2 = np.array(sim.get("autonomia_sag2") or [1.0])
    n = max(len(a1), 1)
    vacio = np.logical_or(a1 <= 0.0, a2 <= 0.0) if len(a1) == len(a2) else (a1 <= 0.0)
    return float(vacio.sum()) / n * 100.0


def _tph_mean(sim: dict) -> float:
    return float(np.mean(sim.get("tph_total") or [0.0]))


def _build_candidatas(base: dict) -> list[dict]:
    """base: dict de kwargs de simulate_scenario_cached del escenario
    actual. Devuelve lista de (titulo, descripcion, tiempo_h, overrides)."""
    r1_tph = base.get("rate_sag1_tph") or (P90["SAG1"] * base.get("rate_sag1_pct", 100.0) / 100.0)
    r2_tph = base.get("rate_sag2_tph") or (P90["SAG2"] * base.get("rate_sag2_pct", 100.0) / 100.0)
    cv315 = base.get("cv315_manual_tph", 0.0)
    cv316 = base.get("cv316_manual_tph", 0.0)
    t3_frac = base.get("t3_frac", 0.0)

    candidatas = [
        {
            "titulo": "Reducir SAG1 100 TPH por 2 horas",
            "descripcion": "Reduce el consumo de la Pila SAG1 temporalmente para ganar autonomía.",
            "tiempo_h": 2.0,
            "overrides": {"rate_sag1_tph": max(r1_tph - 100.0, 0.0)},
        },
        {
            "titulo": "Reducir SAG1 120 TPH por 3 horas",
            "descripcion": "Reducción algo mayor, sostenida 3 horas, para escenarios más críticos.",
            "tiempo_h": 3.0,
            "overrides": {"rate_sag1_tph": max(r1_tph - 120.0, 0.0)},
        },
        {
            "titulo": "Aumentar CV315 150 TPH",
            "descripcion": "Prioriza alimentación hacia la Pila SAG1 vía CV315.",
            "tiempo_h": 1.0,
            "overrides": {"cv315_manual_tph": cv315 + 150.0, "cv_mode": "manual"},
        },
        {
            "titulo": "Reducir T3",
            "descripcion": "Disminuye el desvío a T3 para dejar más alimentación disponible a CV315/CV316.",
            "tiempo_h": 1.0,
            "overrides": {"t3_frac": max(t3_frac - 0.1, 0.0)},
        },
        {
            "titulo": "Priorizar CV316",
            "descripcion": "Redistribuye alimentación hacia la Pila SAG2 vía CV316.",
            "tiempo_h": 1.0,
            "overrides": {"cv316_manual_tph": cv316 + 150.0, "cv_mode": "manual"},
        },
        {
            "titulo": "Mantener ambos MoBos en SAG2",
            "descripcion": "Asegura 511+512 activos para sostener el rate de SAG2.",
            "tiempo_h": 0.0,
            "overrides": {"bolas_sag2": "ambas_511_512"},
        },
        {
            "titulo": "Operar un solo MoBo en SAG1 durante fase crítica",
            "descripcion": "Reduce consumo de bolas en SAG1 mientras dura la restricción.",
            "tiempo_h": 0.0,
            "overrides": {"bolas_sag1": "solo_411"},
        },
        {
            "titulo": "Reducir SAG2 150 TPH por 2 horas",
            "descripcion": "Reduce el consumo de la Pila SAG2 temporalmente para ganar autonomía.",
            "tiempo_h": 2.0,
            "overrides": {"rate_sag2_tph": max(r2_tph - 150.0, 0.0)},
        },
    ]
    return candidatas


def evaluate_quick_wins(base_params: dict, sim_base: dict | None = None) -> list[QuickWin]:
    """base_params: mismos kwargs que simulate_scenario_cached para el
    escenario actual (ver pages/simulador_operacional.py). sim_base: si ya
    se corrió la simulación del escenario actual en este callback, se pasa
    para no recalcularla.

    Retorna la lista de QuickWin ordenada por beneficio/costo descendente
    (el [0] es el quick win principal, ver components/cards.py::make_quick_win_card)."""
    if sim_base is None:
        sim_base = simulate_scenario_cached(**base_params)

    auton_base = _autonomia_min(sim_base)
    dyn_auton_base = _dynamic_autonomia_min(sim_base)
    riesgo_base = _riesgo_vaciado_pct(sim_base)
    tph_base = _tph_mean(sim_base)

    resultados = []
    for cand in _build_candidatas(base_params):
        params = dict(base_params)
        params.update(cand["overrides"])
        try:
            sim = simulate_scenario_cached(**params)
        except Exception:
            continue

        delta_auton = _autonomia_min(sim) - auton_base
        delta_dyn_auton = _dynamic_autonomia_min(sim) - dyn_auton_base
        delta_riesgo = _riesgo_vaciado_pct(sim) - riesgo_base
        tph = _tph_mean(sim)
        impacto_pct = ((tph - tph_base) / tph_base * 100.0) if tph_base > 0 else 0.0

        if delta_auton <= 0.0:
            # No aporta colchon preventivo -> no es un quick win util para
            # esta pantalla. Criterio de filtro sin cambios en esta fase
            # (delta_historical_buffer_h, no delta_dynamic_autonomy_h) —
            # cambiar el criterio de filtro es una decision de producto
            # que no se toma silenciosamente en esta migracion aditiva.
            continue

        resultados.append(QuickWin(
            titulo=cand["titulo"],
            descripcion=cand["descripcion"],
            delta_historical_buffer_h=round(delta_auton, 2),
            delta_dynamic_autonomy_h=round(min(delta_dyn_auton, _SIN_RIESGO_DINAMICO_H), 2),
            delta_riesgo_vaciado_pp=round(delta_riesgo, 1),
            impacto_produccion_pct=round(impacto_pct, 2),
            tiempo_requerido_h=cand["tiempo_h"],
        ))

    resultados.sort(key=lambda qw: qw.beneficio_costo, reverse=True)
    return resultados
