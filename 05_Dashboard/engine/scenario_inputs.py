"""
scenario_inputs.py — Contrato de entrada del router v2 (Prerequisito 1,
PROMPT v2 2026-07-07).

`ScenarioInputs` es el UNICO objeto que el router necesita para decidir que
estrategia aplicar ANTES de correr el motor fisico (ode_model/simulator).
Se construye a partir de datos "actuales" (no de una simulacion de 24h ya
corrida) — de ahi campos como `pila_proyectada_pct`, que es una proyeccion
lineal de corto plazo (2h), NO el resultado del ODE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from engine.ode_model import CAP_TON, DRAIN_PCT_H


@dataclass
class ScenarioInputs:
    pila_actual_pct: float
    pila_proyectada_pct: float
    qin_actual: float          # TPH entrando a la pila (CV315/CV316 actual)
    qout_actual: float         # TPH saliendo (rate SAG actual)
    t1_disponible: bool
    cv315_disponible: bool
    cv316_disponible: bool
    equipos_en_mantencion: list[str]
    sag1_disponible: bool
    sag2_disponible: bool
    mobo1_disponible: bool
    mobo2_disponible: bool
    t8_activa: bool
    t8_duracion_h: float
    timestamp: datetime
    fuente_datos: str = "usuario"      # "usuario" | "realtime" | "sintetico"
    latencia_datos_s: float = 0.0

    def __post_init__(self):
        if not (0.0 <= self.pila_actual_pct <= 120.0):
            raise ValueError(f"pila_actual_pct fuera de rango: {self.pila_actual_pct}")
        if self.mobo1_disponible is False and self.mobo2_disponible is False and (
            self.sag1_disponible or self.sag2_disponible
        ):
            # No es un error fatal (puede ser un escenario real de doble falla),
            # pero se marca para que validate_physics lo detecte como violacion.
            pass


def project_pila_lineal(pila_actual_pct: float, qin_actual: float, qout_actual: float,
                         asset: str, horas: float = 2.0) -> float:
    """Proyeccion LINEAL de corto plazo (2h por defecto) usada SOLO para
    clasificar/priorizar el escenario antes de simular — NO reemplaza el
    ODE (engine.ode_model.simulate_ode), que sigue siendo la unica fuente
    de la trayectoria real de 24h. Usa la misma capacidad en toneladas
    (CAP_TON) que el ODE, sin duplicar su logica de drenaje no-lineal."""
    cap = CAP_TON[asset]
    delta_ton = (qin_actual - qout_actual) * horas
    delta_pct = delta_ton / cap * 100.0
    return max(0.0, min(120.0, pila_actual_pct + delta_pct))


def build_scenario_inputs(
    pila1_pct: float, pila2_pct: float,
    qin1_actual: float, qin2_actual: float,
    qout1_actual: float, qout2_actual: float,
    t1_disponible: bool, cv315_disponible: bool, cv316_disponible: bool,
    equipos_en_mantencion: list[str],
    sag1_disponible: bool, sag2_disponible: bool,
    mobo1_disponible: bool, mobo2_disponible: bool,
    t8_activa: bool, t8_duracion_h: float,
    fuente_datos: str = "usuario", latencia_datos_s: float = 0.0,
) -> tuple[ScenarioInputs, ScenarioInputs]:
    """Construye un par (SAG1, SAG2) de ScenarioInputs — el router evalua
    ambas lineas y el escenario combinado."""
    now = datetime.now()
    s1 = ScenarioInputs(
        pila_actual_pct=pila1_pct,
        pila_proyectada_pct=project_pila_lineal(pila1_pct, qin1_actual, qout1_actual, "SAG1"),
        qin_actual=qin1_actual, qout_actual=qout1_actual,
        t1_disponible=t1_disponible, cv315_disponible=cv315_disponible,
        cv316_disponible=cv316_disponible, equipos_en_mantencion=equipos_en_mantencion,
        sag1_disponible=sag1_disponible, sag2_disponible=sag2_disponible,
        mobo1_disponible=mobo1_disponible, mobo2_disponible=mobo2_disponible,
        t8_activa=t8_activa, t8_duracion_h=t8_duracion_h,
        timestamp=now, fuente_datos=fuente_datos, latencia_datos_s=latencia_datos_s,
    )
    s2 = ScenarioInputs(
        pila_actual_pct=pila2_pct,
        pila_proyectada_pct=project_pila_lineal(pila2_pct, qin2_actual, qout2_actual, "SAG2"),
        qin_actual=qin2_actual, qout_actual=qout2_actual,
        t1_disponible=t1_disponible, cv315_disponible=cv315_disponible,
        cv316_disponible=cv316_disponible, equipos_en_mantencion=equipos_en_mantencion,
        sag1_disponible=sag1_disponible, sag2_disponible=sag2_disponible,
        mobo1_disponible=mobo1_disponible, mobo2_disponible=mobo2_disponible,
        t8_activa=t8_activa, t8_duracion_h=t8_duracion_h,
        timestamp=now, fuente_datos=fuente_datos, latencia_datos_s=latencia_datos_s,
    )
    return s1, s2
