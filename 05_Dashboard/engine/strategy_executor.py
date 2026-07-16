"""
strategy_executor.py — Ejecutor con fallback (Prerequisito 5, PROMPT v2
2026-07-07). Envuelve `strategy.simulate()` en try/except: ante cualquier
excepcion (no-convergencia, division por cero, parametro fuera de rango),
delega en `strategy.on_failure()`, que por contrato NUNCA lanza y siempre
retorna un `SimulationResult(es_factible=False)`. Esto evita que un
escenario invalido rompa el callback de Dash.
"""
from __future__ import annotations

from engine.physics_validation import ValidationReport
from engine.simulation_strategies import BaseSimulationStrategy, SimulationResult


class StrategyExecutor:
    def run(self, strategy: BaseSimulationStrategy, params: dict) -> tuple[SimulationResult, ValidationReport]:
        try:
            result = strategy.simulate(params)
        except Exception as e:  # noqa: BLE001 - fallback deliberado, ver docstring
            result = strategy.on_failure(params, e)
            return result, ValidationReport(es_valido=False, violaciones=[f"Excepcion durante simulacion: {e}"])

        if not result.es_factible:
            return result, ValidationReport(es_valido=False, violaciones=[result.error or "Escenario no factible"])

        try:
            validation = strategy.validate_physics(result, params)
        except Exception as e:  # noqa: BLE001
            validation = ValidationReport(es_valido=False, violaciones=[f"Excepcion en validacion fisica: {e}"])

        return result, validation
