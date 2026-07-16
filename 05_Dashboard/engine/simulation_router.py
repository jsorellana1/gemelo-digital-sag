"""
simulation_router.py — Clasificador + capa de explicabilidad del escenario
operacional.

Decision de diseno (2026-07-06, ver 04_Reports/Technical/*_Arquitectura_
Simulacion_Adaptativa.md): este modulo NO despacha a motores fisicos
distintos por tipo de escenario. El ODE (engine.ode_model/simulator), el
Optimizer V3/V4 y el Monte Carlo adaptativo son EL MISMO motor validado
para todo escenario — y ya son adaptativos internamente:

  - get_regime(duracion_t8) (optimizer_v2.py) ya ajusta pesos de
    produccion/riesgo/inventario/autonomia y min_auton por regimen T8.
  - adaptive_mc_eval ya corre Monte Carlo con parada adaptativa SIEMPRE,
    no solo "cuando el riesgo es alto".
  - detect_bottleneck/full_bottleneck_map (bottleneck.py) ya diagnostican
    que activo limita.

Construir un "selector de heuristicas" que despache a modelos DISTINTOS
por escenario habria significado mantener 2+ implementaciones paralelas
del mismo fenomeno fisico — el riesgo real que Regla obligatoria #5
(no modificar logica matematica validada) busca evitar, y una fuente
de inconsistencia silenciosa entre escenarios "similares pero no
identicos" a los que el clasificador tipifico distinto.

Lo que SI aporta valor real: clasificar el escenario (para explicarlo al
usuario) y calcular, con datos YA producidos por simulate_scenario +
find_optimal_v3 + detect_bottleneck, que "heuristicas" (etiquetas
explicativas) aplican y en que orden de prioridad — sin re-simular nada.

---

ACTUALIZACION v2 (2026-07-07, PROMPT v2 — "el router debe decidir antes
de simular, no describir despues"): lo de arriba (v1) sigue vigente para
la clasificacion/explicacion de un `sim` YA calculado. Se agrega debajo
`route_and_simulate()`, que SI decide antes de simular: construye
`ScenarioInputs`, usa `CriticalityScorer` para rankear regimenes por
urgencia (no una prioridad fija), selecciona la `BaseSimulationStrategy`
correspondiente (o `MixedRegimeStrategy` si hay 2+ regimenes con score
relevante) y la ejecuta via `StrategyExecutor` — el motor real
(simulate_scenario_cached + find_optimal_v3/v4) se invoca DENTRO de la
estrategia elegida, no antes. Ver PREREQUISITO 0 documentado en
`engine/historical_backtesting.py`: el backtesting historico solo es
valido para t8_corta (N=64); t8_larga tiene N=8 (insuficiente) y
overflow/inventario_critico/mantenimiento/alimentacion_restringida no
tienen ningun dataset de eventos etiquetados — para esos casos el router
v2 continua solo con `validate_physics` (fisica), sin backtesting.
"""
from __future__ import annotations

from datetime import datetime

from engine.optimizer_v2 import get_regime
from engine.bottleneck import (
    detect_bottleneck, full_bottleneck_map,
    MIN_AUTON_ALERTA_H, AUTON_ALERTA_SAG2_H,
)
from engine.scheduler import equipos_en_mantencion
from engine.scenario_inputs import ScenarioInputs, build_scenario_inputs
from engine.criticality_scorer import CriticalityScorer, RegimeCriticality
from engine.simulation_strategies import STRATEGIES, MixedRegimeStrategy, SimulationResult
from engine.strategy_executor import StrategyExecutor
from engine.physics_validation import ValidationReport
from engine.historical_backtesting import check_prerequisito_0, run_backtest, BacktestResult
from engine.event_logger import event_logger
from utils.perf_logger import timed

# ---- Tipos de escenario (Paso 2) --------------------------------------------
SCENARIO_TYPES = [
    "overflow",
    "inventario_critico",
    "mantenimiento",
    "alimentacion_restringida",
    "t8_larga",
    "t8_corta",
    "normal",
]

# ---- Heuristicas (Paso 3) ----------------------------------------------------
HEURISTICS = {
    "H1": "Producción máxima",
    "H2": "Conservación de inventario",
    "H3": "Balance alimentación-procesamiento",
    "H4": "Control de overflow",
    "H5": "Planificación por turno",
    "H6": "Mantenimiento",
    "H7": "Robustez probabilística",
}

# Prioridad operacional (Paso 6) — usada solo para ordenar la explicacion,
# no para decidir que motor ejecutar (el motor es unico, ver docstring).
PRIORITY_ORDER = ["H4", "H6", "H2", "H5", "H3", "H7", "H1"]


def parse_user_scenario(
    pila1: float, pila2: float, duracion_t8: float,
    ch1_on: bool, ch2_on: bool,
    correa315_estado: str, correa316_estado: str,
    maint_windows: dict | None, now_hour: float,
    horizonte: float,
) -> dict:
    """Normaliza los parametros del usuario a un `state` dict consistente.
    No valida logica de negocio (eso lo sigue haciendo simulate_scenario) —
    solo tipa/clampa para que classify_scenario reciba tipos previsibles."""
    return {
        "pila1": float(pila1), "pila2": float(pila2),
        "duracion_t8": max(0.0, float(duracion_t8)),
        "ch1_on": bool(ch1_on), "ch2_on": bool(ch2_on),
        "correa315_estado": correa315_estado or "activa",
        "correa316_estado": correa316_estado or "activa",
        "en_mantencion": equipos_en_mantencion(maint_windows or {}, now_hour),
        "horizonte": float(horizonte),
    }


def _detecta_overflow(sim: dict) -> bool:
    """Reutiliza la misma logica de deteccion que el marcador de overflow
    del grafico de pila (components/graphs.py::make_pile_chart) — pila
    llega a >=98% en algun punto del horizonte simulado."""
    import numpy as np
    p1 = np.array(sim.get("pile_sag1", []))
    p2 = np.array(sim.get("pile_sag2", []))
    return bool((p1 >= 98.0).any() or (p2 >= 98.0).any())


def classify_scenario(state: dict, sim: dict) -> dict:
    """Clasifica el escenario. Retorna {'tipos': [...], 'principal': str}.

    'principal' es el de mayor prioridad operacional (Paso 6). 'tipos'
    incluye TODOS los que aplican — si hay 2+, el escenario es 'mixto'
    aunque 'principal' siga siendo el de mayor prioridad."""
    tipos = []

    if _detecta_overflow(sim):
        tipos.append("overflow")

    a1 = sim.get("min_autonomia_sag1", 999)
    a2 = sim.get("min_autonomia_sag2", 999)
    if a1 < MIN_AUTON_ALERTA_H or a2 < AUTON_ALERTA_SAG2_H or state["pila1"] < 20.0 or state["pila2"] < 20.0:
        tipos.append("inventario_critico")

    if state["en_mantencion"]:
        tipos.append("mantenimiento")

    if (not state["ch1_on"]) or (not state["ch2_on"]) \
       or state["correa315_estado"] != "activa" or state["correa316_estado"] != "activa":
        tipos.append("alimentacion_restringida")

    regime_name, _ = get_regime(state["duracion_t8"])
    if regime_name == "t8_larga":
        tipos.append("t8_larga")
    elif regime_name == "t8_corta":
        tipos.append("t8_corta")

    if not tipos:
        tipos.append("normal")

    principal = next((t for t in SCENARIO_TYPES if t in tipos), "normal")
    return {
        "tipos": tipos,
        "principal": principal,
        "mixto": len(tipos) > 1,
    }


def select_heuristics(scenario: dict, state: dict) -> list[str]:
    """Retorna las etiquetas de heuristica (H1-H7) activas, en orden de
    prioridad — puramente explicativo, no cambia que se simula."""
    tipos = set(scenario["tipos"])
    activas = set()

    if "overflow" in tipos:
        activas.add("H4")
    if "inventario_critico" in tipos or "t8_larga" in tipos:
        activas.add("H2")
    if "alimentacion_restringida" in tipos:
        activas.add("H3")
    if "mantenimiento" in tipos:
        activas.add("H6")
    if state["horizonte"] >= 8.0:
        activas.add("H5")
    if "inventario_critico" in tipos or "overflow" in tipos or "t8_larga" in tipos or scenario["mixto"]:
        activas.add("H7")
    if tipos == {"normal"}:
        activas.add("H1")

    return [h for h in PRIORITY_ORDER if h in activas]


def explain_simulation_path(scenario: dict, heuristics: list[str], state: dict) -> str:
    """Texto simple explicando la clasificacion — Paso 7."""
    labels = {
        "overflow": "riesgo de overflow",
        "inventario_critico": "inventario crítico",
        "mantenimiento": "equipos en mantención",
        "alimentacion_restringida": "alimentación restringida",
        "t8_larga": f"ventana T8 larga ({state['duracion_t8']:.0f}h)",
        "t8_corta": f"ventana T8 corta ({state['duracion_t8']:.0f}h)",
        "normal": "operación normal sin restricciones activas",
    }
    razones = ", ".join(labels[t] for t in scenario["tipos"])
    heur_txt = ", ".join(f"{h} ({HEURISTICS[h]})" for h in heuristics)
    tipo_txt = "mixto" if scenario["mixto"] else scenario["principal"]
    return (
        f"Escenario clasificado como '{tipo_txt}' — se detectó: {razones}. "
        f"Heurísticas activas: {heur_txt}."
    )


def run_adaptive_simulation(
    pila1: float, pila2: float, duracion_t8: float,
    ch1_on: bool, ch2_on: bool,
    correa315_estado: str, correa316_estado: str,
    maint_windows: dict | None, now_hour: float,
    horizonte: float,
    sim: dict,
) -> dict:
    """Orquestador (Paso 4/5): NO re-simula ni redespacha a otro motor —
    coordina classify_scenario + select_heuristics + detect_bottleneck
    sobre un `sim` ya calculado por simulate_scenario_cached (el llamador
    es responsable de correr la simulacion real, este modulo solo
    clasifica y explica su resultado)."""
    state = parse_user_scenario(
        pila1, pila2, duracion_t8, ch1_on, ch2_on,
        correa315_estado, correa316_estado, maint_windows, now_hour, horizonte,
    )
    scenario = classify_scenario(state, sim)
    heuristics = select_heuristics(scenario, state)
    bottleneck = detect_bottleneck(sim, ch1_on=ch1_on, ch2_on=ch2_on,
                                    correa315_estado=correa315_estado,
                                    correa316_estado=correa316_estado)
    explicacion = explain_simulation_path(scenario, heuristics, state)

    return {
        "scenario": scenario,
        "heuristics": heuristics,
        "heuristics_labels": [HEURISTICS[h] for h in heuristics],
        "bottleneck": bottleneck,
        "explicacion": explicacion,
    }


# ==============================================================================
# v2 — Router que decide ANTES de simular (PROMPT v2, 2026-07-07)
# ==============================================================================

_executor = StrategyExecutor()
_last_regimen: str = "normal"


def _calcular_confianza(regimen_backtest: str, backtest_info: dict, validation: ValidationReport) -> str:
    """Nivel de confianza de la recomendacion (TAREA 5, prompt "CIERRE DE
    BRECHAS POST ROUTER v2"). NUNCA reporta ALTA si la validacion fisica
    fallo, ni si el backtesting historico esta fuera de tolerancia o no
    disponible — evita mostrar "OK" antes de que el MAE de t8_corta este
    diagnosticado, tal como exige el prompt."""
    if not validation.es_valido:
        return "BAJA"
    if regimen_backtest == "normal":
        return "ALTA"
    if not backtest_info.get("historica_disponible"):
        return "BAJA"
    # Se recalcula dentro_tolerancia real (no se asume OK) contra el
    # backtest ya ejecutado en check_prerequisito_0/run_backtest.
    bt = run_backtest(regimen_backtest)
    if bt.dentro_tolerancia:
        return "ALTA"
    return "MEDIA"


@timed("route_and_simulate")
def route_and_simulate(
    pila1: float, pila2: float, duracion_t8: float,
    qin1_actual: float, qin2_actual: float,
    qout1_actual: float, qout2_actual: float,
    ch1_on: bool, ch2_on: bool,
    correa315_estado: str, correa316_estado: str,
    maint_windows: dict | None, now_hour: float,
    horizonte: float,
    sag1_on: bool = True, sag2_on: bool = True,
    mobo1_disponible: bool = True, mobo2_disponible: bool = True,
    tolerancia_riesgo: str = "balanceado",
    t1_mode: str = "chancado", t1_manual: float = 4000.0,
    t3_frac: float = 0.0, distribucion_t1: str = "proporcional",
    multicell_enabled: bool = False,
    initial_channel_levels_sag1: list[float] | None = None,
    initial_channel_levels_sag2: list[float] | None = None,
    multicell_rate_table_sag1: dict[int, float] | None = None,
    multicell_rate_table_sag2: dict[int, float] | None = None,
    multicell_feed_weights_sag1: list[float] | None = None,
    multicell_feed_weights_sag2: list[float] | None = None,
    multicell_active_threshold_pct: float = 5.0,
    multicell_lateral_transfer_coeff_sag1: float = 0.0,
    multicell_lateral_transfer_coeff_sag2: float = 0.0,
    multicell_spatial_capacity_mode_sag1: str = "none",
    multicell_spatial_capacity_mode_sag2: str = "none",
    multicell_spatial_capacity_params_sag1: dict | None = None,
    multicell_spatial_capacity_params_sag2: dict | None = None,
) -> dict:
    """Orquestador v2: decide la estrategia ANTES de invocar el motor.

    Flujo: ScenarioInputs -> CriticalityScorer -> seleccion de estrategia
    (unica o Mixed) -> StrategyExecutor (invoca el motor real DENTRO de la
    estrategia) -> validate_physics -> chequeo de backtesting disponible
    (Prerequisito 0) -> explicacion con acceso a resultado + validacion.
    """
    equipos_mant = list((maint_windows or {}).keys()) if maint_windows else []
    en_mantencion_ahora = equipos_en_mantencion(maint_windows or {}, now_hour)

    s1, s2 = build_scenario_inputs(
        pila1_pct=pila1, pila2_pct=pila2,
        qin1_actual=qin1_actual, qin2_actual=qin2_actual,
        qout1_actual=qout1_actual, qout2_actual=qout2_actual,
        t1_disponible=not en_mantencion_ahora, cv315_disponible=(correa315_estado == "activa"),
        cv316_disponible=(correa316_estado == "activa"),
        equipos_en_mantencion=list(en_mantencion_ahora),
        sag1_disponible=sag1_on, sag2_disponible=sag2_on,
        mobo1_disponible=mobo1_disponible, mobo2_disponible=mobo2_disponible,
        t8_activa=duracion_t8 > 0, t8_duracion_h=duracion_t8,
    )

    scorer = CriticalityScorer()
    criticidades = scorer.score(s1, s2)
    top = criticidades[0]
    top_base = top.regimen.split("_SAG")[0] if "_SAG" in top.regimen else top.regimen
    # normaliza 'overflow_SAG1' -> 'overflow', 'inventario_critico_SAG1' -> 'inventario_critico'
    for base in ("overflow", "inventario_critico"):
        if top.regimen.startswith(base):
            top_base = base

    activos_relevantes = [c for c in criticidades if c.urgency_score > scorer.MIXTO_THRESHOLD]
    es_mixto = len(activos_relevantes) > 1

    params = {
        "pila1": pila1, "pila2": pila2, "duracion_t8": duracion_t8,
        "sag1_on": sag1_on, "sag2_on": sag2_on,
        "ch1_on": ch1_on, "ch2_on": ch2_on,
        "c315": correa315_estado, "c316": correa316_estado,
        "t1_mode": t1_mode, "t1_manual": t1_manual,
        "t3_frac": t3_frac, "distribucion_t1": distribucion_t1,
        "horizonte": horizonte,
        "tolerancia_riesgo": tolerancia_riesgo,
        "mobo1_disponible": mobo1_disponible, "mobo2_disponible": mobo2_disponible,
        "equipos_en_mantencion": equipos_mant,
        "simulation_overrides": {
            "multicell_enabled": multicell_enabled,
            "initial_channel_levels_sag1": initial_channel_levels_sag1,
            "initial_channel_levels_sag2": initial_channel_levels_sag2,
            "multicell_rate_table_sag1": multicell_rate_table_sag1,
            "multicell_rate_table_sag2": multicell_rate_table_sag2,
            "multicell_feed_weights_sag1": multicell_feed_weights_sag1,
            "multicell_feed_weights_sag2": multicell_feed_weights_sag2,
            "multicell_active_threshold_pct": multicell_active_threshold_pct,
            "multicell_lateral_transfer_coeff_sag1": multicell_lateral_transfer_coeff_sag1,
            "multicell_lateral_transfer_coeff_sag2": multicell_lateral_transfer_coeff_sag2,
            "multicell_spatial_capacity_mode_sag1": multicell_spatial_capacity_mode_sag1,
            "multicell_spatial_capacity_mode_sag2": multicell_spatial_capacity_mode_sag2,
            "multicell_spatial_capacity_params_sag1": multicell_spatial_capacity_params_sag1,
            "multicell_spatial_capacity_params_sag2": multicell_spatial_capacity_params_sag2,
        },
    }

    if es_mixto:
        strategy = MixedRegimeStrategy(activos_relevantes)
    else:
        strategy = STRATEGIES.get(top_base, STRATEGIES["normal"])

    result, validation = _executor.run(strategy, params)

    regimen_backtest = top_base if not es_mixto else activos_relevantes[0].regimen.split("_SAG")[0]
    prereq = check_prerequisito_0().get(regimen_backtest)
    backtest_info = {
        "regimen": regimen_backtest,
        "historica_disponible": prereq.disponible if prereq else False,
        "razon": prereq.razon if prereq else "Operacion normal: no aplica backtesting de eventos de riesgo",
        "n_eventos": prereq.n_eventos if prereq else 0,
    }

    explicacion = strategy.explain(result, validation) if result.es_factible else (
        f"Escenario no factible: {result.error}"
    )

    confianza = _calcular_confianza(regimen_backtest, backtest_info, validation)

    # TAREA 4 (event_logger): registra el cambio de regimen dominante
    # para construir, desde hoy, el dataset historico etiquetado que hoy
    # no existe para los 4 regimenes sin cobertura oficial.
    global _last_regimen
    regimen_actual = "mixto" if es_mixto else top_base
    if regimen_actual != _last_regimen:
        estado_snapshot = {
            "pila1": pila1, "pila2": pila2, "duracion_t8": duracion_t8,
            "urgency_score": round(top.urgency_score, 1),
        }
        event_logger.on_regime_change(_last_regimen, regimen_actual, estado_snapshot, datetime.now())
        _last_regimen = regimen_actual

    return {
        "criticidades": [{"regimen": c.regimen, "urgency_score": round(c.urgency_score, 1), "razones": c.razones}
                          for c in criticidades],
        "regimen_elegido": regimen_actual,
        "result": result,
        "validation": validation,
        "backtest_info": backtest_info,
        "confianza": confianza,
        "explicacion": explicacion,
    }
