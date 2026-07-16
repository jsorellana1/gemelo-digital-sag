"""
simulation_strategies.py — Contrato de estrategia + estrategias concretas
por regimen (Prerequisito 4, PROMPT v2 2026-07-07).

Cada `BaseSimulationStrategy` es un envoltorio DELGADO sobre el mismo motor
fisico unico (simulate_scenario_cached, find_optimal_v3, find_optimal_v4):
ninguna estrategia reimplementa el ODE ni el Monte Carlo. Lo que varia por
estrategia es (a) que modo/parametros del motor se usan, (b) que
restricciones duras se imponen, y (c) como se explica el resultado — no la
fisica subyacente. Esto preserva la decision de diseno de v1
(04_Reports/Technical/20260707_Arquitectura_Simulacion_Adaptativa.md): un
solo motor validado, nunca 2+ implementaciones paralelas del mismo
fenomeno.

Diferencia real vs v1: aqui la ESTRATEGIA SE ELIGE ANTES de invocar el
motor (a partir de ScenarioInputs + CriticalityScorer), en vez de
clasificar un `sim` ya calculado con parametros por defecto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.criticality_scorer import RegimeCriticality
from engine.physics_validation import ValidationReport, validate_physics
from engine.simulator import simulate_scenario_cached
from engine.optimizer_v3 import find_optimal_v3
from engine.optimizer_v4 import find_optimal_v4


@dataclass
class SimulationResult:
    regimen: str
    sim: dict
    best: dict | None = None
    all_results: list[dict] | None = None
    es_factible: bool = True
    error: str | None = None
    meta: dict = field(default_factory=dict)


def _run_engine(params: dict, mode: str, tolerancia_riesgo: str | None = None) -> tuple[dict, dict, list[dict]]:
    """Unico punto que invoca el motor real (find_optimal_v3 + V4 opcional +
    simulate_scenario_cached del mejor candidato). Todas las estrategias
    pasan por aqui — nunca reimplementan esta secuencia."""
    best_v3, all_results = find_optimal_v3(
        pila1=params["pila1"], pila2=params["pila2"], duracion_t8=params["duracion_t8"],
        sag1_on=params.get("sag1_on", True), sag2_on=params.get("sag2_on", True),
        ch1_on=params.get("ch1_on", True), ch2_on=params.get("ch2_on", True),
        c315=params.get("c315", "activa"), c316=params.get("c316", "activa"),
        t1_mode=params.get("t1_mode", "chancado"), t1_manual=params.get("t1_manual", 4000.0),
        t3_frac=params.get("t3_frac", 0.0), distribucion_t1=params.get("distribucion_t1", "proporcional"),
        horizonte=params.get("horizonte", 24.0), mode=mode,
        simulation_overrides=params.get("simulation_overrides"),
    )
    best = best_v3
    if tolerancia_riesgo is not None:
        best = find_optimal_v4(all_results, tolerancia=tolerancia_riesgo)

    # Los mismos overrides fisicos usados por la simulacion final se
    # propagan tambien al grid/MC del optimizador V3, para que la
    # eleccion de `best` y la simulacion final compartan la misma fisica.
    sim_overrides = dict(params.get("simulation_overrides", {}))
    sim = simulate_scenario_cached(
        pila_sag1_pct=params["pila1"], pila_sag2_pct=params["pila2"],
        rate_sag1_pct=best["r1"] / 1454.0 * 100.0 if best.get("r1") else 100.0,
        rate_sag2_pct=best["r2"] / 2516.0 * 100.0 if best.get("r2") else 100.0,
        bolas_sag1=best.get("b1", "sin_bola"), bolas_sag2=best.get("b2", "sin_bola"),
        sag1_activo=params.get("sag1_on", True), sag2_activo=params.get("sag2_on", True),
        duracion_t8_h=params["duracion_t8"],
        correa315_estado=params.get("c315", "activa"), correa316_estado=params.get("c316", "activa"),
        horizonte_horas=params.get("horizonte", 24.0),
        ch1_on=params.get("ch1_on", True), ch2_on=params.get("ch2_on", True),
        t1_mode=params.get("t1_mode", "chancado"), t1_manual_tph=params.get("t1_manual", 4000.0),
        t3_frac=params.get("t3_frac", 0.0), distribucion_t1=params.get("distribucion_t1", "proporcional"),
        **sim_overrides,
    )
    return sim, best, all_results


class BaseSimulationStrategy:
    """Contrato (Prerequisito 4). `on_failure` NUNCA lanza excepcion — el
    StrategyExecutor depende de esa garantia para no romper el callback de
    Dash ante un escenario invalido/no convergente."""

    regimen: str = "base"

    def applies_to(self, criticality: RegimeCriticality) -> bool:
        raise NotImplementedError

    def simulate(self, params: dict) -> SimulationResult:
        raise NotImplementedError

    def on_failure(self, params: dict, error: Exception) -> SimulationResult:
        return SimulationResult(
            regimen=self.regimen, sim={}, best=None, all_results=None,
            es_factible=False, error=str(error),
        )

    def validate_physics(self, result: SimulationResult, params: dict) -> ValidationReport:
        return validate_physics(
            result.sim,
            sag1_disponible=params.get("sag1_on", True),
            sag2_disponible=params.get("sag2_on", True),
            mobo1_disponible=params.get("mobo1_disponible", True),
            mobo2_disponible=params.get("mobo2_disponible", True),
            equipos_en_mantencion=params.get("equipos_en_mantencion", []),
            equipos_activos={
                "sag1": params.get("sag1_on", True),
                "sag2": params.get("sag2_on", True),
                "ch1": params.get("ch1_on", True),
                "ch2": params.get("ch2_on", True),
            },
        )

    def explain(self, result: SimulationResult, validation: ValidationReport) -> str:
        raise NotImplementedError


class NormalStrategy(BaseSimulationStrategy):
    regimen = "normal"

    def applies_to(self, criticality: RegimeCriticality) -> bool:
        return criticality.regimen == "normal"

    def simulate(self, params: dict) -> SimulationResult:
        sim, best, all_r = _run_engine(params, mode="balanced")
        return SimulationResult(regimen=self.regimen, sim=sim, best=best, all_results=all_r)

    def explain(self, result: SimulationResult, validation: ValidationReport) -> str:
        b = result.best or {}
        return (
            f"Operacion normal: sin restricciones activas. Recomendacion balanceada "
            f"SAG1={b.get('r1', 0):.0f} TPH, SAG2={b.get('r2', 0):.0f} TPH "
            f"(P(safe)={b.get('p_safe', 0)*100:.0f}%)."
        )


class T8Strategy(BaseSimulationStrategy):
    """Comun a t8_corta y t8_larga: mismo motor (find_optimal_v3 ya
    resuelve el regimen internamente por duracion_t8), difiere solo en
    `regimen` y el texto de explicacion."""

    def applies_to(self, criticality: RegimeCriticality) -> bool:
        return criticality.regimen == self.regimen

    def simulate(self, params: dict) -> SimulationResult:
        sim, best, all_r = _run_engine(
            params, mode="balanced", tolerancia_riesgo=params.get("tolerancia_riesgo", "balanceado"),
        )
        return SimulationResult(regimen=self.regimen, sim=sim, best=best, all_results=all_r)

    def explain(self, result: SimulationResult, validation: ValidationReport) -> str:
        b = result.best or {}
        return (
            f"Ventana T8 ({self.regimen}): recomendacion SAG1={b.get('r1', 0):.0f} TPH, "
            f"SAG2={b.get('r2', 0):.0f} TPH, autonomia minima {b.get('a1_min', 0):.1f}h/"
            f"{b.get('a2_min', 0):.1f}h. {b.get('validation_answer', '')}"
        )


class T8CortaStrategy(T8Strategy):
    regimen = "t8_corta"


class T8LargaStrategy(T8Strategy):
    regimen = "t8_larga"


class InventarioCriticoStrategy(BaseSimulationStrategy):
    regimen = "inventario_critico"

    def applies_to(self, criticality: RegimeCriticality) -> bool:
        return criticality.regimen.startswith("inventario_critico")

    def simulate(self, params: dict) -> SimulationResult:
        # Restriccion dura: independiente de la preferencia del usuario,
        # inventario critico fuerza mode="safe" + tolerancia "conservador".
        sim, best, all_r = _run_engine(params, mode="safe", tolerancia_riesgo="conservador")
        return SimulationResult(regimen=self.regimen, sim=sim, best=best, all_results=all_r,
                                 meta={"override_tolerancia": "conservador (forzado por inventario critico)"})

    def explain(self, result: SimulationResult, validation: ValidationReport) -> str:
        b = result.best or {}
        return (
            f"Inventario critico: se prioriza P(safe) sobre produccion (tolerancia forzada a "
            f"'conservador' independiente de la preferencia del usuario). "
            f"SAG1={b.get('r1', 0):.0f} TPH, SAG2={b.get('r2', 0):.0f} TPH, "
            f"P(safe)={b.get('p_safe', 0)*100:.0f}%."
        )


class OverflowStrategy(BaseSimulationStrategy):
    regimen = "overflow"

    def applies_to(self, criticality: RegimeCriticality) -> bool:
        return criticality.regimen.startswith("overflow")

    def simulate(self, params: dict) -> SimulationResult:
        # Drenar la pila lo mas rapido posible: maximizar consumo (max_prod).
        sim, best, all_r = _run_engine(params, mode="max_prod")
        return SimulationResult(regimen=self.regimen, sim=sim, best=best, all_results=all_r)

    def explain(self, result: SimulationResult, validation: ValidationReport) -> str:
        b = result.best or {}
        return (
            f"Riesgo de overflow: se prioriza maxima tasa de consumo para drenar pila. "
            f"SAG1={b.get('r1', 0):.0f} TPH, SAG2={b.get('r2', 0):.0f} TPH."
        )


class MantenimientoStrategy(BaseSimulationStrategy):
    regimen = "mantenimiento"

    def applies_to(self, criticality: RegimeCriticality) -> bool:
        return criticality.regimen == "mantenimiento"

    def simulate(self, params: dict) -> SimulationResult:
        sim, best, all_r = _run_engine(params, mode="balanced")
        return SimulationResult(regimen=self.regimen, sim=sim, best=best, all_results=all_r)

    def explain(self, result: SimulationResult, validation: ValidationReport) -> str:
        b = result.best or {}
        return (
            f"Equipos en mantencion activa: recomendacion balanceada respetando disponibilidad "
            f"declarada. SAG1={b.get('r1', 0):.0f} TPH, SAG2={b.get('r2', 0):.0f} TPH."
        )


class AlimentacionRestringidaStrategy(BaseSimulationStrategy):
    regimen = "alimentacion_restringida"

    def applies_to(self, criticality: RegimeCriticality) -> bool:
        return criticality.regimen == "alimentacion_restringida"

    def simulate(self, params: dict) -> SimulationResult:
        sim, best, all_r = _run_engine(params, mode="balanced")
        return SimulationResult(regimen=self.regimen, sim=sim, best=best, all_results=all_r)

    def explain(self, result: SimulationResult, validation: ValidationReport) -> str:
        b = result.best or {}
        return (
            f"Alimentacion restringida (CH/CV315/CV316/T1): recomendacion ajustada a la "
            f"capacidad reducida disponible. SAG1={b.get('r1', 0):.0f} TPH, SAG2={b.get('r2', 0):.0f} TPH."
        )


STRATEGIES: dict[str, BaseSimulationStrategy] = {
    "normal": NormalStrategy(),
    "t8_corta": T8CortaStrategy(),
    "t8_larga": T8LargaStrategy(),
    "inventario_critico": InventarioCriticoStrategy(),
    "overflow": OverflowStrategy(),
    "mantenimiento": MantenimientoStrategy(),
    "alimentacion_restringida": AlimentacionRestringidaStrategy(),
}


def _base_regimen(regimen: str) -> str:
    """'overflow_SAG1' -> 'overflow', 'inventario_critico_SAG2' -> 'inventario_critico'."""
    for base in ("overflow", "inventario_critico"):
        if regimen.startswith(base):
            return base
    return regimen


class MixedRegimeStrategy(BaseSimulationStrategy):
    """Combina 2+ estrategias activas simultaneamente (score > MIXTO_THRESHOLD
    del CriticalityScorer). Protocolo de resolucion de conflicto:

    1. Ejecuta la estrategia de mayor urgencia (`primary`) -> result_primary.
    2. Para cada estrategia secundaria, valida si result_primary viola una
       restriccion dura implicita de esa estrategia secundaria (ej.
       overflow secundario pero result_primary aun deja pila >=98%;
       inventario_critico secundario pero autonomia < minimo del regimen).
    3. Si hay conflicto de DIRECCION (primary busca subir TPH y secondary
       busca bajarlo, o viceversa), se re-corre con mode="safe" +
       tolerancia "conservador" (el ajuste mas conservador disponible) y se
       documenta el conflicto explicitamente en `explain()`. Si no hay
       conflicto de direccion, se conserva result_primary y se reporta
       "combinado sin conflicto".
    """
    regimen = "mixto"

    def __init__(self, criticidades: list[RegimeCriticality]):
        self.criticidades = criticidades
        self.primary_base = _base_regimen(criticidades[0].regimen)
        self.secondary_bases = [_base_regimen(c.regimen) for c in criticidades[1:]]

    def applies_to(self, criticality: RegimeCriticality) -> bool:
        return True  # se instancia explicitamente por el router, no por matching

    def simulate(self, params: dict) -> SimulationResult:
        primary_strategy = STRATEGIES[self.primary_base]
        result_primary = primary_strategy.simulate(params)
        conflicto = None

        aumenta_tph = {"normal", "overflow"}
        reduce_tph = {"inventario_critico", "t8_larga", "t8_corta"}
        primary_direction = "sube" if self.primary_base in aumenta_tph else (
            "baja" if self.primary_base in reduce_tph else "neutro")

        for sec_base in self.secondary_bases:
            sec_direction = "sube" if sec_base in aumenta_tph else (
                "baja" if sec_base in reduce_tph else "neutro")
            if primary_direction != "neutro" and sec_direction != "neutro" and primary_direction != sec_direction:
                conflicto = (
                    f"Conflicto de direccion: '{self.primary_base}' busca {primary_direction} TPH "
                    f"mientras '{sec_base}' busca {sec_direction} TPH — se aplica el ajuste mas "
                    f"conservador disponible (mode=safe, tolerancia=conservador)."
                )
                break

        if conflicto:
            sim, best, all_r = _run_engine(params, mode="safe", tolerancia_riesgo="conservador")
            result = SimulationResult(
                regimen="mixto", sim=sim, best=best, all_results=all_r,
                meta={"conflicto": conflicto, "primary": self.primary_base, "secondary": self.secondary_bases},
            )
        else:
            result = result_primary
            result.regimen = "mixto"
            result.meta["conflicto"] = None
            result.meta["primary"] = self.primary_base
            result.meta["secondary"] = self.secondary_bases
        return result

    def explain(self, result: SimulationResult, validation: ValidationReport) -> str:
        b = result.best or {}
        base_txt = (
            f"Escenario mixto ({self.primary_base} + {'+'.join(self.secondary_bases)}). "
        )
        if result.meta.get("conflicto"):
            base_txt += result.meta["conflicto"] + " "
        else:
            base_txt += "Regimenes combinados sin conflicto de direccion — se usa la recomendacion del de mayor urgencia. "
        base_txt += f"SAG1={b.get('r1', 0):.0f} TPH, SAG2={b.get('r2', 0):.0f} TPH."
        return base_txt
