"""
simulator.py — Punto de entrada unico para ejecutar simulacion completa
y calcular metricas derivadas.
"""

from __future__ import annotations
import numpy as np

from engine.ode_model import (
    simulate_ode, compute_autonomia, P90, CAP_TON, CRITICAL_PCT,
    compute_chancado_cap, compute_t1_tph, check_bola_rule, BOLA_THRESHOLD_TPH,
    BOLA_CONFIG_SAG1, BOLA_CONFIG_SAG2, ONE_BALL_CAPACITY_FACTOR,
)
from engine.rules_engine import recommend_action, determine_regime
from engine import circuit_state as _cs
from engine.risk_engine import compute_iro


def simulate_scenario(
    pila_sag1_pct: float,
    pila_sag2_pct: float,
    rate_sag1_pct: float,
    rate_sag2_pct: float,
    bolas_sag1: str = "sin_bola",
    bolas_sag2: str = "sin_bola",
    sag1_activo: bool = True,
    sag2_activo: bool = True,
    duracion_t8_h: float = 0.0,
    correa315_estado: str = "activa",
    correa316_estado: str = "activa",
    horizonte_horas: float = 24.0,
    # Parametros opcionales
    ch1_on: bool = True,
    ch2_on: bool = True,
    cv_mode: str = "auto",
    cv315_manual_tph: float = 0.0,
    cv316_manual_tph: float = 0.0,
    rate_sag1_tph: float = None,
    rate_sag2_tph: float = None,
    # Compatibilidad legada (ignorados, se usan bolas_sag1/2)
    estado_bola_1: bool = None,
    estado_bola_2: bool = None,
    # Capa T1 / T3 (transferencia post-chancado)
    t1_mode: str = "chancado",
    t1_manual_tph: float = 4000.0,
    t3_frac: float = 0.0,
    distribucion_t1: str = "proporcional",
    # Lógica operacional centralizada (2026-07-14, ver engine/circuit_state.py) —
    # todos opcionales, default = comportamiento identico al previo a este cambio.
    windows: list | None = None,
    sag_ramp_up_time_min: float = 0.0,
    sag_ramp_down_time_min: float = 0.0,
    feed_recovery_time_min: float = 0.0,
    feed_recovery_mode: str = "linear",
    feed_recovery_tau_min: float | None = None,
    one_ball_capacity_factor: float = ONE_BALL_CAPACITY_FACTOR,
    redistribution_enabled: bool = False,
    enforce_downstream_ball_capacity: bool = False,
    one_ball_capacity_factor_sag1: float | None = None,
    one_ball_capacity_factor_sag2: float | None = None,
    # Fase 1 multi-celda (opcional, apagada por default)
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
    """
    Ejecuta simulacion ODE completa y retorna dict con todas las series y metricas.

    Claves del resultado:
      time, pile_sag1, pile_sag2, tph_sag1, tph_sag2, tph_total,
      autonomia_sag1, autonomia_sag2, riesgo_sag1, riesgo_sag2,
      cv315, cv316, chancado_cap, bola411, bola412, bola511, bola512,
      accion_recomendada, explicacion, iro_result,
      regime_sag1_final, regime_sag2_final,
      rate_recomendado_sag1, rate_recomendado_sag2,
      chancado_cap_tph, alerta_bola_sag1, alerta_bola_sag2,
      bolas_recomendadas_sag1, bolas_recomendadas_sag2
    """
    # Resolver rates en TPH
    if rate_sag1_tph is not None:
        _r1_tph = float(rate_sag1_tph)
        _r1_pct = _r1_tph / P90["SAG1"] * 100.0
    else:
        _r1_pct = rate_sag1_pct
        _r1_tph = P90["SAG1"] * rate_sag1_pct / 100.0

    if rate_sag2_tph is not None:
        _r2_tph = float(rate_sag2_tph)
        _r2_pct = _r2_tph / P90["SAG2"] * 100.0
    else:
        _r2_pct = rate_sag2_pct
        _r2_tph = P90["SAG2"] * rate_sag2_pct / 100.0

    # Capacidad chancado
    cap_chanc = compute_chancado_cap(ch1_on, ch2_on)

    # Extraer n_bolas desde config granular
    _cfg1 = BOLA_CONFIG_SAG1.get(bolas_sag1, BOLA_CONFIG_SAG1["sin_bola"])
    _cfg2 = BOLA_CONFIG_SAG2.get(bolas_sag2, BOLA_CONFIG_SAG2["sin_bola"])
    n_bolas_sag1 = _cfg1["n"]
    n_bolas_sag2 = _cfg2["n"]

    _, alerta_bola_sag1, msg_bola1 = check_bola_rule(_r1_tph, "SAG1", n_bolas_sag1)
    _, alerta_bola_sag2, msg_bola2 = check_bola_rule(_r2_tph, "SAG2", n_bolas_sag2)

    bolas_rec_sag1 = 1 if _r1_tph < BOLA_THRESHOLD_TPH["SAG1"] else 2
    bolas_rec_sag2 = 1 if _r2_tph < BOLA_THRESHOLD_TPH["SAG2"] else 2

    raw = simulate_ode(
        pila_sag1_pct=pila_sag1_pct,
        pila_sag2_pct=pila_sag2_pct,
        rate_sag1_pct=_r1_pct,
        rate_sag2_pct=_r2_pct,
        bolas_sag1=bolas_sag1,
        bolas_sag2=bolas_sag2,
        sag1_activo=sag1_activo,
        sag2_activo=sag2_activo,
        duracion_t8_h=duracion_t8_h,
        correa315_estado=correa315_estado,
        correa316_estado=correa316_estado,
        horizonte_horas=horizonte_horas,
        ch1_on=ch1_on,
        ch2_on=ch2_on,
        cv_mode=cv_mode,
        cv315_manual_tph=cv315_manual_tph,
        cv316_manual_tph=cv316_manual_tph,
        rate_sag1_tph=_r1_tph,
        rate_sag2_tph=_r2_tph,
        t1_mode=t1_mode,
        t1_manual_tph=t1_manual_tph,
        t3_frac=t3_frac,
        distribucion_t1=distribucion_t1,
        windows=windows,
        sag_ramp_up_time_min=sag_ramp_up_time_min,
        sag_ramp_down_time_min=sag_ramp_down_time_min,
        feed_recovery_time_min=feed_recovery_time_min,
        feed_recovery_mode=feed_recovery_mode,
        feed_recovery_tau_min=feed_recovery_tau_min,
        one_ball_capacity_factor=one_ball_capacity_factor,
        redistribution_enabled=redistribution_enabled,
        enforce_downstream_ball_capacity=enforce_downstream_ball_capacity,
        one_ball_capacity_factor_sag1=one_ball_capacity_factor_sag1,
        one_ball_capacity_factor_sag2=one_ball_capacity_factor_sag2,
        multicell_enabled=multicell_enabled,
        initial_channel_levels_sag1=initial_channel_levels_sag1,
        initial_channel_levels_sag2=initial_channel_levels_sag2,
        multicell_rate_table_sag1=multicell_rate_table_sag1,
        multicell_rate_table_sag2=multicell_rate_table_sag2,
        multicell_feed_weights_sag1=multicell_feed_weights_sag1,
        multicell_feed_weights_sag2=multicell_feed_weights_sag2,
        multicell_active_threshold_pct=multicell_active_threshold_pct,
        multicell_lateral_transfer_coeff_sag1=multicell_lateral_transfer_coeff_sag1,
        multicell_lateral_transfer_coeff_sag2=multicell_lateral_transfer_coeff_sag2,
        multicell_spatial_capacity_mode_sag1=multicell_spatial_capacity_mode_sag1,
        multicell_spatial_capacity_mode_sag2=multicell_spatial_capacity_mode_sag2,
        multicell_spatial_capacity_params_sag1=multicell_spatial_capacity_params_sag1,
        multicell_spatial_capacity_params_sag2=multicell_spatial_capacity_params_sag2,
    )

    # Condiciones al final de la simulacion
    pile1_final = raw["pile_sag1"][-1]
    pile2_final = raw["pile_sag2"][-1]
    auton1_final = raw["autonomia_sag1"][-1]
    auton2_final = raw["autonomia_sag2"][-1]

    # Condicion T8 al final del horizonte
    t8_activo_final = (duracion_t8_h > 0) and (horizonte_horas < duracion_t8_h)

    # Regimen final
    regime1, bounds1 = determine_regime(pile1_final, auton1_final, t8_activo_final, "SAG1")
    regime2, bounds2 = determine_regime(pile2_final, auton2_final, t8_activo_final, "SAG2")

    # Autonomia minima encontrada en la simulacion
    arr1 = np.array(raw["autonomia_sag1"])
    arr2 = np.array(raw["autonomia_sag2"])
    min_auton1 = float(arr1.min())
    min_auton2 = float(arr2.min())

    # Tiempo hasta autonomia critica
    time_arr = np.array(raw["time"])
    idx1_crit = np.where(arr1 < 1.0)[0]
    idx2_crit = np.where(arr2 < 1.0)[0]
    t_crit1 = float(time_arr[idx1_crit[0]]) if len(idx1_crit) else None
    t_crit2 = float(time_arr[idx2_crit[0]]) if len(idx2_crit) else None

    # CV valores iniciales para recomendacion
    cv315_init = raw["cv315"][0] if raw["cv315"] else 0.0
    cv316_init = raw["cv316"][0] if raw["cv316"] else 0.0
    t1_init    = raw["t1"][0]  if raw.get("t1") else cap_chanc
    t3_init    = raw["t3"][0]  if raw.get("t3") else 0.0

    # Accion recomendada (condicion inicial)
    _hist_h_sag1 = compute_autonomia(pila_sag1_pct, "SAG1")
    _hist_h_sag2 = compute_autonomia(pila_sag2_pct, "SAG2")

    # Contexto de autonomia (Etapa 2 del reencuadre semantico, 2026-07-15,
    # ver 04_Reports/Technical/20260715_Migracion_Autonomia_Etapa2.md):
    # evaluado sobre el MISMO estado inicial que ya usa compute_autonomia
    # arriba (pila_sagX_pct, cv315_init/cv316_init como f_in, tph_sagX[0]
    # como f_out) -- no es un calculo nuevo, es aplicar los clasificadores
    # de circuit_state.py (Etapa 1) sobre el paso 0 de la trayectoria en
    # vez del paso final (que es donde simulate_ode ya los aplica).
    _tph1_init = raw["tph_sag1"][0] if raw.get("tph_sag1") else 0.0
    _tph2_init = raw["tph_sag2"][0] if raw.get("tph_sag2") else 0.0
    autonomy_context_sag1 = _cs.build_autonomy_context(
        pila_sag1_pct / 100.0 * CAP_TON["SAG1"], CRITICAL_PCT["SAG1"] / 100.0 * CAP_TON["SAG1"],
        cv315_init, _tph1_init, _hist_h_sag1, "SAG1")
    autonomy_context_sag2 = _cs.build_autonomy_context(
        pila_sag2_pct / 100.0 * CAP_TON["SAG2"], CRITICAL_PCT["SAG2"] / 100.0 * CAP_TON["SAG2"],
        cv316_init, _tph2_init, _hist_h_sag2, "SAG2")

    accion, explicacion = recommend_action(
        autonomia_sag1=_hist_h_sag1,
        autonomia_sag2=_hist_h_sag2,
        pile_sag1_pct=pila_sag1_pct,
        pile_sag2_pct=pila_sag2_pct,
        t8_activo=(duracion_t8_h > 0),
        chancado_cap_tph=cap_chanc,
        cv315_tph=cv315_init,
        cv316_tph=cv316_init,
        rate_sag1_tph=_r1_tph,
        rate_sag2_tph=_r2_tph,
        n_bolas_sag1=n_bolas_sag1,
        n_bolas_sag2=n_bolas_sag2,
        sag1_activo=sag1_activo,
        sag2_activo=sag2_activo,
        t1_tph=t1_init,
        t3_tph=t3_init,
        duracion_t8_h=duracion_t8_h,
        autonomy_context_sag1=autonomy_context_sag1,
        autonomy_context_sag2=autonomy_context_sag2,
    )

    # Enriquecer explicacion con tiempo a critico si aplica
    if t_crit1 is not None:
        explicacion += f" | SAG1 autonomia critica en {t_crit1*60:.0f} min"
    if t_crit2 is not None:
        explicacion += f" | SAG2 autonomia critica en {t_crit2*60:.0f} min"

    # Recomendacion del kernel de dominio (Regla 16, engine/circuit_state.py) —
    # se AGREGA a la explicacion existente, no reemplaza rules_engine.py.
    if raw.get("dependency_message_sag1") or raw.get("dependency_message_sag2"):
        dep_txt = " ".join(m for m in (raw.get("dependency_message_sag1"), raw.get("dependency_message_sag2")) if m)
        explicacion += f" | {dep_txt}"

    # IRO inicial. Reusa _hist_h_sag1/2 y autonomy_context_sag1/2 ya
    # construidos arriba para recommend_action (Fase 12 del pedido de
    # Etapa 2: no recomputar autonomia) — Fase 1.1 del roadmap de cierre
    # (2026-07-15): agrega sub-scores dinamico/historico como diagnostico
    # aditivo, el iro total no cambia.
    iro_result = compute_iro(
        pile_sag1_pct=pila_sag1_pct,
        pile_sag2_pct=pila_sag2_pct,
        autonomia_sag1_h=_hist_h_sag1,
        autonomia_sag2_h=_hist_h_sag2,
        rate_sag1_pct=_r1_pct,
        rate_sag2_pct=_r2_pct,
        duracion_t8_h=duracion_t8_h,
        correa315_estado=correa315_estado,
        correa316_estado=correa316_estado,
        chancado_cap_tph=cap_chanc,
        sag1_activo=sag1_activo,
        sag2_activo=sag2_activo,
        t1_restriccion=(cv315_init + cv316_init) > (t1_init + 100.0),
        autonomy_context_sag1=autonomy_context_sag1,
        autonomy_context_sag2=autonomy_context_sag2,
    )

    raw.update({
        "accion_recomendada": accion,
        "explicacion": explicacion,
        "iro_result": iro_result,
        "regime_sag1_final": regime1,
        "regime_sag2_final": regime2,
        "rate_recomendado_sag1": f"{bounds1[0]:.0f}-{bounds1[1]:.0f}%",
        "rate_recomendado_sag2": f"{bounds2[0]:.0f}-{bounds2[1]:.0f}%",
        "min_autonomia_sag1": round(min_auton1, 2),
        "min_autonomia_sag2": round(min_auton2, 2),
        "t_critico_sag1_h": t_crit1,
        "t_critico_sag2_h": t_crit2,
        "chancado_cap_tph": cap_chanc,
        "alerta_bola_sag1": alerta_bola_sag1,
        "alerta_bola_sag2": alerta_bola_sag2,
        "bolas_recomendadas_sag1": bolas_rec_sag1,
        "bolas_recomendadas_sag2": bolas_rec_sag2,
        "rate_sag1_tph_actual": _r1_tph,
        "rate_sag2_tph_actual": _r2_tph,
        "sag1_activo": sag1_activo,
        "sag2_activo": sag2_activo,
        "t1_tph": t1_init,
        "t3_tph": t3_init,
        "t1_restriccion": (cv315_init + cv316_init) > (t1_init + 100.0),
    })

    return raw


# Cache por escenario (Fase 5): usar SOLO para llamadas deterministicas de un
# unico escenario "en vivo" (callbacks reactivos con los parametros del
# usuario). NO usar dentro de Monte Carlo / adaptive_mc_eval: ahi cada
# muestra usa parametros perturbados aleatoriamente y casi nunca se repiten,
# por lo que cachear solo agrega overhead y desplaza del cache entradas
# deterministicas reutilizables (ver engine/scenario_cache.py).
from engine.scenario_cache import simulation_cache  # noqa: E402

simulate_scenario_cached = simulation_cache.wrap("simulate_scenario")(simulate_scenario)
