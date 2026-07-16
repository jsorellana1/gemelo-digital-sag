"""
ode_model.py — Balance de masa ODE para sistema SAG molienda T8
Paso de tiempo: DT = 5/60 h (5 minutos)

Nomenclatura de activos:
  SAG1 = Molino 401, bolas: 411 y 412
  SAG2 = Molino 501, bolas: 511 y 512
"""

import json
import os
import sys

import numpy as np

from engine import circuit_state as _cs
from engine import stockpile_multicell as _smc

# Factor de reduccion de alimentacion por estado de correa durante una
# ventana operacional (Regla 1 del kernel de dominio) — UNA sola fuente de
# verdad, referenciada tanto por compute_qin() como por simulate_ode() (antes
# duplicada literalmente en ambos lugares).
VENTANA_FACTOR_ESTADO = {"activa": 1.0, "reducida": 0.4, "inactiva": 0.0}

# Factor de capacidad aguas abajo con 1 sola bola activa (Regla 9).
# ONE_BALL_CAPACITY_FACTOR (generico, legado): sin dato calibrado
# confirmado — supuesto documentado en 04_Reports/Technical/
# 20260714_Logica_Operacional_Pilas_SAG.md; se mantiene como fallback
# compartido para callers que no distinguen por activo.
ONE_BALL_CAPACITY_FACTOR = 0.55

# Calibrados por activo (2026-07-15, roadmap de cierre Fase 4.2): razon
# mediana rate(n_bolas=1)/rate(n_bolas=2), estratificada por banda de feed
# de chancado, T8-activo excluido (02_Analytics/Scripts/
# calibrar_one_ball_capacity_factor.py, N1=8.870/N2=29.733 para SAG1,
# N1=2.741/N2=36.228 para SAG2 — naive y controlado-por-banda casi
# identicos, poca evidencia de sesgo de seleccion). Usados como default
# de one_ball_capacity_factor_sag1/sag2 en simulate_ode/simulate_scenario
# — solo tienen efecto si enforce_downstream_ball_capacity=True (apagado
# por default, mecanismo opt-in sin consumidores de produccion hoy).
ONE_BALL_CAPACITY_FACTOR_SAG1 = 0.72
ONE_BALL_CAPACITY_FACTOR_SAG2 = 0.59

# ── Parametros calibrados ──────────────────────────────────────────────────────
P90 = {"SAG1": 1454.0, "SAG2": 2516.0, "PMC": 1460.0, "UNITARIO": 834.0}
CRITICAL_PCT = {"SAG1": 15.0, "SAG2": 18.2}
WARNING_PCT  = {"SAG1": 18.0, "SAG2": 21.2}   # banda "Monitorear": crit + 3pp
DRAIN_PCT_H = {"SAG1": 23.76, "SAG2": 6.18}
CAP_TON = {"SAG1": 4575.0, "SAG2": 32009.0}
BOLA_BONUS_LEGACY = 0.08   # referencia modelo de ingenieria anterior (+8%/bola)
BOLA_BONUS = BOLA_BONUS_LEGACY  # alias de compatibilidad

# ── Deltas calibrados de bolas (cargados desde cache) ─────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))          # .../engine
_ROOT = os.path.dirname(os.path.dirname(_HERE))             # .../07_Rendimientos
if getattr(sys, "frozen", False):
    _BOLA_CACHE = os.path.join(os.path.dirname(sys.executable), "runtime_data", "Cache", "bola_delta_tph.json")
else:
    _BOLA_CACHE = os.path.join(_ROOT, "01_Data", "Cache", "bola_delta_tph.json")


def _load_bola_deltas() -> dict:
    """Carga DELTA_TPH historico por bola. Fallback al modelo de ingenieria legacy."""
    try:
        with open(_BOLA_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "SAG1": {1: float(data["SAG1"]["delta_tph_1bola"]),
                     2: float(data["SAG1"]["delta_tph_2bola"])},
            "SAG2": {1: float(data["SAG2"]["delta_tph_1bola"]),
                     2: float(data["SAG2"]["delta_tph_2bola"])},
        }
    except Exception:
        return {
            "SAG1": {1: P90["SAG1"] * BOLA_BONUS_LEGACY,
                     2: P90["SAG1"] * BOLA_BONUS_LEGACY * 2},
            "SAG2": {1: P90["SAG2"] * BOLA_BONUS_LEGACY,
                     2: P90["SAG2"] * BOLA_BONUS_LEGACY * 2},
        }


BOLA_DELTA_TPH = _load_bola_deltas()

# Nombres de activos y sus bolas
ASSET_NAMES = {"SAG1": "Molino 401", "SAG2": "Molino 501"}
BOLA_NAMES = {"SAG1": ("411", "412"), "SAG2": ("511", "512")}

# Capacidad chancado
CHANCADO_CAP = {
    "ambos": 4000.0,    # Ch1 + Ch2
    "ch1":   1500.0,    # Solo Ch1
    "ch2":   2500.0,    # Solo Ch2
    "ninguno": 0.0,     # Ambos OFF
}

# T1: estadisticas historicas del flujo post-chancado (P50 por estado)
# Calibradas con tonelaje_v2.xlsx: 93600 filas, 2025-08-01 → 2026-06-21
T1_HIST_TPH = {
    "ambos":   4002.0,  # P50 historico cuando ambos chancadores corren
    "ch2":     2500.0,  # Solo CH2
    "ch1":     1500.0,  # Solo CH1
    "ninguno":    0.0,
}
# Fraccion historica de (CV315+CV316) que va a CV315: 29%, CV316: 71%
T1_FRAC_CV315 = 0.29

# Umbral de rate en TPH para regla de molinos de bola
BOLA_THRESHOLD_TPH = {"SAG1": 1000.0, "SAG2": 1600.0}

DT = 5.0 / 60.0  # horas por paso


def compute_chancado_cap(ch1_on: bool, ch2_on: bool) -> float:
    """Capacidad de chancado segun estado de chancadores."""
    if ch1_on and ch2_on:
        return CHANCADO_CAP["ambos"]
    elif ch1_on:
        return CHANCADO_CAP["ch1"]
    elif ch2_on:
        return CHANCADO_CAP["ch2"]
    else:
        return CHANCADO_CAP["ninguno"]


def compute_t1_tph(
    t1_mode: str,
    t1_manual_tph: float,
    chancado_cap_tph: float,
    ch1_on: bool = True,
    ch2_on: bool = True,
) -> float:
    """
    TPH disponible en transferencia T1 segun modo:
      'chancado'  → T1 = cap chancado (sin perdidas; comportamiento original)
      'historico' → T1 = P50 historico para estado actual de chancadores
      'manual'    → T1 = t1_manual_tph (usuario fija directamente)
    """
    if t1_mode == "manual":
        return max(0.0, float(t1_manual_tph))
    elif t1_mode == "historico":
        if ch1_on and ch2_on:
            return T1_HIST_TPH["ambos"]
        elif ch2_on:
            return T1_HIST_TPH["ch2"]
        elif ch1_on:
            return T1_HIST_TPH["ch1"]
        return 0.0
    else:  # "chancado" — copia directa de la capacidad
        return chancado_cap_tph


def compute_t1_distribution(
    t1_tph: float,
    t3_frac: float,
    distribucion_t1: str,
    sag1_demand_tph: float,
    sag2_demand_tph: float,
    cv_mode: str = "auto",
    cv315_manual: float = 0.0,
    cv316_manual: float = 0.0,
) -> tuple:
    """
    Distribuye T1 entre CV315, CV316 y T3 respetando la conservacion de masa:
      T1 = CV315 + CV316 + T3

    t3_frac: fraccion de T1 que va a T3 (desvio; 0.0 = sin T3, 0.20 = 20% a T3).
    distribucion_t1: 'balanceado' | 'priorizar_sag1' | 'priorizar_sag2' | 'proporcional'
    cv_mode: si 'manual', usa cv315_manual/cv316_manual directamente.

    Retorna (cv315_tph, cv316_tph, t3_tph, alerta_restriccion).
    alerta_restriccion = True cuando cv315+cv316 > T1 disponible.
    """
    t3_tph = t1_tph * max(0.0, min(1.0, t3_frac))
    disponible = max(0.0, t1_tph - t3_tph)
    alerta = False

    if cv_mode == "manual":
        cv315 = max(0.0, float(cv315_manual))
        cv316 = max(0.0, float(cv316_manual))
        if cv315 + cv316 > disponible + 0.1:
            alerta = True
            total = cv315 + cv316
            if total > 0:
                cv315 = cv315 / total * disponible
                cv316 = cv316 / total * disponible
        t3_actual = max(0.0, t1_tph - cv315 - cv316)
        return cv315, cv316, t3_actual, alerta

    # Distribucion automatica
    if distribucion_t1 == "priorizar_sag1":
        frac315 = 0.50
    elif distribucion_t1 == "priorizar_sag2":
        frac315 = 0.10
    elif distribucion_t1 == "balanceado":
        frac315 = T1_FRAC_CV315
    else:  # "proporcional" a demanda SAG
        total_d = sag1_demand_tph + sag2_demand_tph
        frac315 = (sag1_demand_tph / total_d) if total_d > 0 else T1_FRAC_CV315

    cv315 = disponible * frac315
    cv316 = disponible * (1.0 - frac315)
    return cv315, cv316, t3_tph, alerta


def check_bola_rule(rate_sag_tph: float, asset: str, n_bolas: int) -> tuple:
    """
    Verifica regla de molinos de bola.
    Si rate_sag_tph < umbral, maximo 1 bola permitida.
    Retorna (n_bolas_recomendado, violacion_bool, mensaje).
    """
    umbral = BOLA_THRESHOLD_TPH[asset]
    if rate_sag_tph < umbral and n_bolas > 1:
        return 1, True, f"{asset}: rate {rate_sag_tph:.0f} TPH < {umbral:.0f} TPH, max 1 bola"
    return n_bolas, False, ""


def compute_qin(asset: str, correa_estado: str, normal_feed_tph: float, t8_activo: bool,
                cv_tph: float = None) -> float:
    """
    Calcula flujo de entrada a la pila segun estado de la correa y si hay T8 activo.
    Si cv_tph se proporciona (modo chancado+correa), lo usa directamente.

    correa_estado: 'activa' | 'reducida' | 'inactiva'
    """
    if cv_tph is not None:
        # Modo con chancado explicitamente modelado; aplicar factor correa durante T8
        if not t8_activo:
            return cv_tph
        f = VENTANA_FACTOR_ESTADO.get(correa_estado, 1.0)
        return f * cv_tph

    if not t8_activo:
        return normal_feed_tph

    f = VENTANA_FACTOR_ESTADO.get(correa_estado, 1.0)
    return f * normal_feed_tph


def compute_autonomia(pile_pct: float, asset: str) -> float:
    """
    Autonomia restante en horas = (pile_pct - critical_pct) / drain_pct_h
    Devuelve 0 si ya esta en zona critica o debajo.
    """
    crit = CRITICAL_PCT[asset]
    drain = DRAIN_PCT_H[asset]
    raw = (pile_pct - crit) / drain
    return max(0.0, raw)


def step_pile(pile_pct: float, qin_tph: float, qout_tph: float, asset: str) -> float:
    """
    Avanza un paso DT del balance de masa.
    S[t+1] = S[t] + (Qin - Qout) * DT  (en toneladas)
    Luego convierte a %: pile_pct_new = pile_ton_new / cap_ton * 100
    Retorna pile_pct acotado en [0, 100].
    """
    cap = CAP_TON[asset]
    pile_ton = pile_pct / 100.0 * cap
    pile_ton_new = pile_ton + (qin_tph - qout_tph) * DT
    pile_ton_new = max(0.0, min(cap, pile_ton_new))
    return pile_ton_new / cap * 100.0


def effective_rate(p90_tph: float, rate_pct: float, n_bolas: int,
                   asset: str = "SAG2") -> float:
    """
    TPH efectivo = P90 * rate_pct/100 + DELTA_TPH_calibrado(n_bolas, asset)
    DELTA es aditivo (no multiplicativo) para ser consistente con la calibracion.
    asset: 'SAG1' | 'SAG2'. Default 'SAG2' para compatibilidad con llamadas legacy.
    n_bolas: 0 = sin bola, 1 = una bola, 2 = ambas bolas.
    """
    base = p90_tph * rate_pct / 100.0
    n = max(0, min(int(n_bolas), 2))
    if n == 0:
        return base
    deltas = BOLA_DELTA_TPH.get(asset, BOLA_DELTA_TPH["SAG2"])
    return base + deltas.get(n, 0.0)


# Mapeo de configuracion de bola a estados individuales
BOLA_CONFIG_SAG1 = {
    "sin_bola":      {"n": 0, "b411": 0, "b412": 0},
    "solo_411":      {"n": 1, "b411": 1, "b412": 0},
    "solo_412":      {"n": 1, "b411": 0, "b412": 1},
    "ambas_411_412": {"n": 2, "b411": 1, "b412": 1},
}
BOLA_CONFIG_SAG2 = {
    "sin_bola":      {"n": 0, "b511": 0, "b512": 0},
    "solo_511":      {"n": 1, "b511": 1, "b512": 0},
    "solo_512":      {"n": 1, "b511": 0, "b512": 1},
    "ambas_511_512": {"n": 2, "b511": 1, "b512": 1},
}


def _t8_factor_sag1(t_elapsed_h: float) -> float:
    """
    Multiplicador de rate SAG1 segun tiempo transcurrido dentro de ventana T8.
    Calibrado con datos historicos de 70 eventos: 2h=+8%, 4h=-31%, 12h=-56%.
    Interpolacion lineal entre puntos de control.
    """
    knots = [(0.0, 1.00), (2.0, 1.08), (4.0, 0.69), (12.0, 0.44)]
    if t_elapsed_h <= 0.0:
        return 1.0
    if t_elapsed_h >= knots[-1][0]:
        return knots[-1][1]
    for k in range(len(knots) - 1):
        t0, f0 = knots[k]
        t1, f1 = knots[k + 1]
        if t0 <= t_elapsed_h <= t1:
            return f0 + (f1 - f0) * (t_elapsed_h - t0) / (t1 - t0)
    return 1.0


def _t8_factor_sag2(t_elapsed_h: float) -> float:
    """
    Multiplicador de rate SAG2 segun tiempo en T8.
    SAG2 es mas robusto: 2h=2%, 4h=1%, 12h=-15%.
    """
    knots = [(0.0, 1.00), (2.0, 0.98), (4.0, 0.99), (12.0, 0.85)]
    if t_elapsed_h <= 0.0:
        return 1.0
    if t_elapsed_h >= knots[-1][0]:
        return knots[-1][1]
    for k in range(len(knots) - 1):
        t0, f0 = knots[k]
        t1, f1 = knots[k + 1]
        if t0 <= t_elapsed_h <= t1:
            return f0 + (f1 - f0) * (t_elapsed_h - t0) / (t1 - t0)
    return 1.0


def _pile_feedback_factor(pile_pct: float, asset: str) -> float:
    """
    Factor de reduccion de rate segun nivel de pila actual.
    Simula la respuesta operacional automatica cuando el inventario baja:
      >= 35%: operacion normal
      25-35%: conservador (-15%)
      crit+5 a 25%: minimo tecnico (-30%)
      < crit+5%: emergencia (-50%)
    Transicion suavizada con interpolacion lineal entre umbrales.
    """
    crit = CRITICAL_PCT[asset]
    p = pile_pct
    if p >= 35.0:
        return 1.00
    elif p >= 25.0:
        # Lineal 1.0 -> 0.85 entre 35% y 25%
        return 1.00 - 0.15 * (35.0 - p) / 10.0
    elif p >= crit + 5.0:
        # Lineal 0.85 -> 0.70 entre 25% y (crit+5)
        span = 25.0 - (crit + 5.0)
        if span <= 0:
            return 0.70
        return 0.85 - 0.15 * (25.0 - p) / span
    else:
        # Lineal 0.70 -> 0.50 entre (crit+5) y crit
        span = 5.0
        return 0.70 - 0.20 * max(0.0, (crit + 5.0 - p)) / span


def simulate_ode(
    pila_sag1_pct: float,
    pila_sag2_pct: float,
    rate_sag1_pct: float,
    rate_sag2_pct: float,
    sag1_activo: bool,
    sag2_activo: bool,
    duracion_t8_h: float,
    correa315_estado: str,
    correa316_estado: str,
    bolas_sag1: str = "sin_bola",
    bolas_sag2: str = "sin_bola",
    horizonte_horas: float = 24.0,
    regime_fn=None,
    ch1_on: bool = True,
    ch2_on: bool = True,
    cv_mode: str = "auto",
    cv315_manual_tph: float = 0.0,
    cv316_manual_tph: float = 0.0,
    rate_sag1_tph: float = None,
    rate_sag2_tph: float = None,
    # Parametros T1 / T3 (capa de transferencia post-chancado)
    t1_mode: str = "chancado",
    t1_manual_tph: float = 4000.0,
    t3_frac: float = 0.0,
    distribucion_t1: str = "proporcional",
    # ── Lógica operacional centralizada (2026-07-14, ver engine/circuit_state.py
    # y 04_Reports/Technical/20260714_Logica_Operacional_Pilas_SAG.md) ──────────
    # Todos con default = comportamiento identico al motor previo a este
    # cambio (puente de compatibilidad explicito, no cambia ningun resultado
    # numerico existente salvo que se activen explicitamente).
    windows: list | None = None,
    sag_ramp_up_time_min: float = 0.0,
    sag_ramp_down_time_min: float = 0.0,
    feed_recovery_time_min: float = 0.0,
    feed_recovery_mode: str = "linear",
    feed_recovery_tau_min: float | None = None,
    one_ball_capacity_factor: float = ONE_BALL_CAPACITY_FACTOR,
    redistribution_enabled: bool = False,
    # Fase 2 (2026-07-14, ver 04_Reports/Technical/
    # 20260714_Segunda_Fase_Logica_Operacional.md seccion 2): tope fisico
    # de capacidad aguas abajo por Nº de molinos de bolas, aplicado como
    # min() sobre el rate YA calibrado (dose-response + retroalimentacion
    # de pila), NO como reemplazo — evita doble penalizacion. Apagado por
    # default (`enforce_downstream_ball_capacity=False`): el mecanismo
    # calibrado existente (delta aditivo por Nº de bolas, ya presente en
    # effective_rate()) sigue siendo la unica fuente de verdad salvo que
    # se active explicitamente.
    enforce_downstream_ball_capacity: bool = False,
    one_ball_capacity_factor_sag1: float | None = ONE_BALL_CAPACITY_FACTOR_SAG1,
    one_ball_capacity_factor_sag2: float | None = ONE_BALL_CAPACITY_FACTOR_SAG2,
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
    Integra el balance de masa ODE para ambos SAG durante horizonte_horas.

    ODE:
      dS1/dt = CV315_tph - rate_SAG1_tph
      dS2/dt = CV316_tph - rate_SAG2_tph

    regime_fn(pile_pct, autonomia_h, t8_activo, asset) -> (rate_pct_adj, regime_str)
    Si es None, usa el rate fijo proporcionado.

    Retorna dict con listas time, pile_sag1, pile_sag2, tph_sag1, tph_sag2,
    tph_total, autonomia_sag1, autonomia_sag2, riesgo_sag1, riesgo_sag2,
    cv315_arr, cv316_arr, chancado_cap_arr, bola411_arr, bola412_arr, bola511_arr, bola512_arr,
    mas las claves aditivas nuevas del kernel de dominio: overflow_sag1/2,
    rejected_feed_sag1/2, mass_balance_error_sag1/2, dependency_message_sag1/2,
    operational_state_sag1/2, pile_trend_sag1/2, autonomy_message_sag1/2.

    `windows`: lista opcional de engine.circuit_state.OperationalWindow. Si es
    None (default), se construye automaticamente UNA sola ventana
    [0, duracion_t8_h) con los factores de correa315/316_estado — exactamente
    el comportamiento previo. Pasar una lista explicita habilita ventanas
    multiples/superpuestas/con inicio distinto de 0 (Reglas 13-14).
    """
    # Convertir rates: si se dan en TPH usar directamente; si en % convertir
    if rate_sag1_tph is not None:
        _rate1_tph_base = float(rate_sag1_tph)
        _rate1_pct = _rate1_tph_base / P90["SAG1"] * 100.0
    else:
        _rate1_pct = rate_sag1_pct
        _rate1_tph_base = P90["SAG1"] * rate_sag1_pct / 100.0

    if rate_sag2_tph is not None:
        _rate2_tph_base = float(rate_sag2_tph)
        _rate2_pct = _rate2_tph_base / P90["SAG2"] * 100.0
    else:
        _rate2_pct = rate_sag2_pct
        _rate2_tph_base = P90["SAG2"] * rate_sag2_pct / 100.0

    n_steps = int(horizonte_horas / DT)

    time_arr = np.zeros(n_steps + 1)
    pile1 = np.zeros(n_steps + 1)
    pile2 = np.zeros(n_steps + 1)
    tph1 = np.zeros(n_steps + 1)
    tph2 = np.zeros(n_steps + 1)
    auton1 = np.zeros(n_steps + 1)
    auton2 = np.zeros(n_steps + 1)
    risk1 = np.zeros(n_steps + 1, dtype=int)   # 0=ok, 1=warn, 2=crit
    risk2 = np.zeros(n_steps + 1, dtype=int)
    cv315_arr = np.zeros(n_steps + 1)
    cv316_arr = np.zeros(n_steps + 1)
    chancado_arr = np.zeros(n_steps + 1)

    # Estado bolas (series para el grafico de timeline)
    bola411_arr = np.zeros(n_steps + 1, dtype=int)
    bola412_arr = np.zeros(n_steps + 1, dtype=int)
    bola511_arr = np.zeros(n_steps + 1, dtype=int)
    bola512_arr = np.zeros(n_steps + 1, dtype=int)

    # Configuracion de bolas
    cfg1 = BOLA_CONFIG_SAG1.get(bolas_sag1, BOLA_CONFIG_SAG1["sin_bola"])
    cfg2 = BOLA_CONFIG_SAG2.get(bolas_sag2, BOLA_CONFIG_SAG2["sin_bola"])
    _n_bolas1 = cfg1["n"]
    _n_bolas2 = cfg2["n"]
    _b411 = cfg1["b411"]; _b412 = cfg1["b412"]
    _b511 = cfg2["b511"]; _b512 = cfg2["b512"]

    # Condiciones iniciales
    pile1[0] = pila_sag1_pct
    pile2[0] = pila_sag2_pct

    # Capacidad chancado y capa T1
    cap_chanc = compute_chancado_cap(ch1_on, ch2_on)
    t1_eff = compute_t1_tph(t1_mode, t1_manual_tph, cap_chanc, ch1_on, ch2_on)

    # Feed normal ~ 80% P90 (operacion tipica de alimentacion; se usa si chancado no activo)
    normal_feed1 = 0.80 * P90["SAG1"]
    normal_feed2 = 0.80 * P90["SAG2"]

    t1_arr_out = np.full(n_steps + 1, t1_eff)
    t3_arr = np.zeros(n_steps + 1)

    multicell_channels1 = None
    multicell_channels2 = None
    active_channels1_arr = None
    active_channels2_arr = None
    rate_cap1_arr = None
    rate_cap2_arr = None
    pile1_channels_arr = None
    pile2_channels_arr = None
    lateral_moved1_arr = None
    lateral_moved2_arr = None
    spatial_cap_factor1_arr = None
    spatial_cap_factor2_arr = None
    base_rate_cap1_arr = None
    base_rate_cap2_arr = None
    _mcfg1 = None
    _mcfg2 = None
    if multicell_enabled:
        _mcfg1 = _smc.build_multicell_config(
            asset="SAG1",
            max_rate_tph=_rate1_tph_base,
            rate_table_tph=multicell_rate_table_sag1,
            active_threshold_pct=multicell_active_threshold_pct,
            feed_weights=multicell_feed_weights_sag1,
            spatial_capacity_mode=multicell_spatial_capacity_mode_sag1,
            spatial_capacity_params=multicell_spatial_capacity_params_sag1,
        )
        _mcfg2 = _smc.build_multicell_config(
            asset="SAG2",
            max_rate_tph=_rate2_tph_base,
            rate_table_tph=multicell_rate_table_sag2,
            active_threshold_pct=multicell_active_threshold_pct,
            feed_weights=multicell_feed_weights_sag2,
            spatial_capacity_mode=multicell_spatial_capacity_mode_sag2,
            spatial_capacity_params=multicell_spatial_capacity_params_sag2,
        )
        multicell_channels1 = _smc.initialize_channel_tons(
            total_pile_pct=pila_sag1_pct,
            cap_total_ton=CAP_TON["SAG1"],
            config=_mcfg1,
            channel_levels_pct=initial_channel_levels_sag1,
        )
        multicell_channels2 = _smc.initialize_channel_tons(
            total_pile_pct=pila_sag2_pct,
            cap_total_ton=CAP_TON["SAG2"],
            config=_mcfg2,
            channel_levels_pct=initial_channel_levels_sag2,
        )
        pile1_channels_arr = np.zeros((len(multicell_channels1), n_steps + 1))
        pile2_channels_arr = np.zeros((len(multicell_channels2), n_steps + 1))
        pile1_channels_arr[:, 0] = np.asarray(
            _smc.channel_levels_pct(multicell_channels1, CAP_TON["SAG1"]), dtype=float
        )
        pile2_channels_arr[:, 0] = np.asarray(
            _smc.channel_levels_pct(multicell_channels2, CAP_TON["SAG2"]), dtype=float
        )
        active_channels1_arr = np.zeros(n_steps + 1, dtype=int)
        active_channels2_arr = np.zeros(n_steps + 1, dtype=int)
        rate_cap1_arr = np.zeros(n_steps + 1)
        rate_cap2_arr = np.zeros(n_steps + 1)
        lateral_moved1_arr = np.zeros(n_steps + 1)
        lateral_moved2_arr = np.zeros(n_steps + 1)
        spatial_cap_factor1_arr = np.ones(n_steps + 1)
        spatial_cap_factor2_arr = np.ones(n_steps + 1)
        base_rate_cap1_arr = np.zeros(n_steps + 1)
        base_rate_cap2_arr = np.zeros(n_steps + 1)
        active_channels1_arr[0] = _smc.count_active_channels(
            multicell_channels1, CAP_TON["SAG1"], _mcfg1.active_threshold_pct
        )
        active_channels2_arr[0] = _smc.count_active_channels(
            multicell_channels2, CAP_TON["SAG2"], _mcfg2.active_threshold_pct
        )
        rate_cap1_arr[0] = _smc.calibrated_rate_cap_tph(
            _rate1_tph_base, multicell_channels1, CAP_TON["SAG1"], _mcfg1
        )
        rate_cap2_arr[0] = _smc.calibrated_rate_cap_tph(
            _rate2_tph_base, multicell_channels2, CAP_TON["SAG2"], _mcfg2
        )
        base_rate_cap1_arr[0] = rate_cap1_arr[0]
        base_rate_cap2_arr[0] = rate_cap2_arr[0]
        spatial_cap_factor1_arr[0] = _smc.spatial_capacity_factor(multicell_channels1, CAP_TON["SAG1"], _mcfg1)
        spatial_cap_factor2_arr[0] = _smc.spatial_capacity_factor(multicell_channels2, CAP_TON["SAG2"], _mcfg2)
        rate_cap1_arr[0] *= spatial_cap_factor1_arr[0]
        rate_cap2_arr[0] *= spatial_cap_factor2_arr[0]

    # ── Lógica operacional centralizada: ventanas, rampas, overflow ──────────
    # Puente de compatibilidad: sin `windows` explicito, se construye UNA
    # sola ventana [0, duracion_t8_h) con los factores de correa315/316 —
    # exactamente equivalente al `factors_correa` inline que existia antes
    # (Regla 1, ver engine/circuit_state.py).
    if windows is None:
        _windows = [_cs.OperationalWindow(
            start_time=0.0, end_time=duracion_t8_h,
            feed_factor_sac1=VENTANA_FACTOR_ESTADO.get(correa315_estado, 1.0),
            feed_factor_sac2=VENTANA_FACTOR_ESTADO.get(correa316_estado, 1.0),
            reason="T8",
        )]
    else:
        _windows = windows

    overflow1_arr = np.zeros(n_steps + 1)
    overflow2_arr = np.zeros(n_steps + 1)
    rejected1_arr = np.zeros(n_steps + 1)
    rejected2_arr = np.zeros(n_steps + 1)

    _prev_qout1 = 0.0
    _prev_qout2 = 0.0
    dependency_message_sag1 = ""
    dependency_message_sag2 = ""
    _cum_in1_ton = 0.0
    _cum_out1_ton = 0.0
    _cum_overflow1_ton = 0.0
    _cum_in2_ton = 0.0
    _cum_out2_ton = 0.0
    _cum_overflow2_ton = 0.0

    for i in range(n_steps):
        t_h = i * DT
        time_arr[i] = t_h

        t8_activo = (duracion_t8_h > 0) and (t_h < duracion_t8_h)
        t_in_t8   = t_h if t8_activo else 0.0

        # ── Factores dinamicos ────────────────────────────────────────────
        # A: dose-response T8 (historico calibrado 70 eventos)
        t8f1 = _t8_factor_sag1(t_in_t8)
        t8f2 = _t8_factor_sag2(t_in_t8)
        # B: retroalimentacion de pila (respuesta operacional automatica)
        pf1 = _pile_feedback_factor(pile1[i], "SAG1")
        pf2 = _pile_feedback_factor(pile2[i], "SAG2")
        # Factor combinado (min 0.30 para no llegar a 0 por combinacion)
        dyn1 = max(0.30, t8f1 * pf1)
        dyn2 = max(0.30, t8f2 * pf2)

        # ── SAG1 ─────────────────────────────────────────────────────────
        a1 = compute_autonomia(pile1[i], "SAG1")
        auton1[i] = a1
        if regime_fn is not None:
            r1_pct_adj, _ = regime_fn(pile1[i], a1, t8_activo, "SAG1")
            qout1 = effective_rate(P90["SAG1"], r1_pct_adj * dyn1, _n_bolas1, "SAG1") if sag1_activo else 0.0
        else:
            r1_pct_dyn = _rate1_pct * dyn1
            # Auto-reducir bolas si rate base baja del umbral
            _nb1_eff = min(_n_bolas1, 1) if (_rate1_tph_base * pf1 * t8f1 < BOLA_THRESHOLD_TPH["SAG1"]) else _n_bolas1
            qout1 = effective_rate(P90["SAG1"], r1_pct_dyn, _nb1_eff, "SAG1") if sag1_activo else 0.0

        # ── SAG2 ─────────────────────────────────────────────────────────
        a2 = compute_autonomia(pile2[i], "SAG2")
        auton2[i] = a2
        if regime_fn is not None:
            r2_pct_adj, _ = regime_fn(pile2[i], a2, t8_activo, "SAG2")
            qout2 = effective_rate(P90["SAG2"], r2_pct_adj * dyn2, _n_bolas2, "SAG2") if sag2_activo else 0.0
        else:
            r2_pct_dyn = _rate2_pct * dyn2
            _nb2_eff = min(_n_bolas2, 1) if (_rate2_tph_base * pf2 * t8f2 < BOLA_THRESHOLD_TPH["SAG2"]) else _n_bolas2
            qout2 = effective_rate(P90["SAG2"], r2_pct_dyn, _nb2_eff, "SAG2") if sag2_activo else 0.0

        if regime_fn is not None:
            # _nb1_eff/_nb2_eff solo se calculan en la rama regime_fn is
            # None (auto-downgrade por umbral) — con regime_fn activo se
            # usa el conteo solicitado tal cual, sin auto-downgrade.
            _nb1_eff = _n_bolas1
            _nb2_eff = _n_bolas2

        # Estado efectivo de bolas — Regla 4 (engine/circuit_state.py::
        # resolve_equipment_dependencies): un molino de bolas NUNCA puede
        # figurar efectivamente encendido si su SAG esta apagado, sin
        # importar la configuracion solicitada. Antes de este cambio la
        # condicion inline (`not sag1_activo or ...`) hacia exactamente lo
        # opuesto para b411/b511 (mostraba "on" cuando el SAG estaba OFF) —
        # bug de visualizacion puro: no afecta qout1/qout2 (ya calculados
        # arriba solo con sag*_activo/_nb*_eff), solo las series
        # bola411_arr/etc. usadas por el grafico de timeline de bolas.
        _balls1_req = {"411": bool(_b411), "412": bool(_b412 and _nb1_eff >= 2)} if regime_fn is None else \
                      {"411": bool(_b411), "412": bool(_b412)}
        _balls2_req = {"511": bool(_b511), "512": bool(_b512 and _nb2_eff >= 2)} if regime_fn is None else \
                      {"511": bool(_b511), "512": bool(_b512)}
        _balls1_eff, _dep_msg1 = _cs.resolve_equipment_dependencies(sag1_activo, _balls1_req)
        _balls2_eff, _dep_msg2 = _cs.resolve_equipment_dependencies(sag2_activo, _balls2_req)
        b411_eff = int(_balls1_eff["411"])
        b412_eff = int(_balls1_eff["412"])
        b511_eff = int(_balls2_eff["511"])
        b512_eff = int(_balls2_eff["512"])
        if i == 0:
            dependency_message_sag1 = _dep_msg1
            dependency_message_sag2 = _dep_msg2

        # Distribucion T1 → CV315 / CV316 / T3
        cv315, cv316, t3_i, _ = compute_t1_distribution(
            t1_eff, t3_frac, distribucion_t1, qout1, qout2,
            cv_mode, cv315_manual_tph, cv316_manual_tph
        )

        # Reduccion de alimentacion por ventana operacional + recuperacion
        # gradual post-ventana — Reglas 1-3 / Fase 2 seccion 6
        # (engine/circuit_state.py::calculate_effective_feed). Con
        # `windows=None` y `feed_recovery_time_min=0` (defaults) esto es
        # exactamente equivalente al `factors_correa` inline que existia
        # antes (recuperacion instantanea, una sola ventana
        # [0,duracion_t8_h) con el mismo factor por estado de correa).
        cv315 = _feed_con_recuperacion(_windows, t_h, "sac1", cv315,
                                        feed_recovery_time_min, feed_recovery_mode, feed_recovery_tau_min)
        cv316 = _feed_con_recuperacion(_windows, t_h, "sac2", cv316,
                                        feed_recovery_time_min, feed_recovery_mode, feed_recovery_tau_min)

        # Si no hay chancado modelado explicitamente, caer al feed normal
        if cap_chanc == 0.0:
            qin1 = compute_qin("SAG1", correa315_estado, normal_feed1, t8_activo)
            qin2 = compute_qin("SAG2", correa316_estado, normal_feed2, t8_activo)
        else:
            qin1 = cv315
            qin2 = cv316

        # Redistribucion entre SAC1/SAC2 cuando un circuito esta detenido —
        # Reglas 12-13, apagada por default (`redistribution_enabled=False`
        # -> retorna qin1/qin2 sin modificar, cero cambio de comportamiento).
        if redistribution_enabled:
            qin1, qin2, _ = _cs.redistribute_feed(
                qin1, qin2, circuit1_available=sag1_activo, circuit2_available=sag2_activo,
                capacity_sac1_tph=P90["SAG1"] * 1.5, capacity_sac2_tph=P90["SAG2"] * 1.5,
                enabled=True,
            )

        # Rampas de arranque/detencion — Regla 10. Con
        # sag_ramp_up/down_time_min=0 (default) retorna el rate objetivo
        # sin modificar (comportamiento instantaneo previo, identico).
        qout1 = _cs.apply_rate_ramp(qout1, _prev_qout1, sag_ramp_up_time_min,
                                     sag_ramp_down_time_min, DT, P90["SAG1"])
        qout2 = _cs.apply_rate_ramp(qout2, _prev_qout2, sag_ramp_up_time_min,
                                     sag_ramp_down_time_min, DT, P90["SAG2"])

        # Tope fisico de capacidad aguas abajo por Nº de bolas — Regla 8/9,
        # Fase 2 seccion 2. Aplicado como min() SOBRE el rate ya calibrado
        # (no lo reemplaza, evita doble penalizacion). Apagado por default
        # (enforce_downstream_ball_capacity=False): el mecanismo calibrado
        # existente (delta aditivo por Nº de bolas dentro de
        # effective_rate()) sigue siendo la unica fuente de verdad salvo
        # que se active explicitamente.
        if enforce_downstream_ball_capacity:
            _f1 = one_ball_capacity_factor_sag1 if one_ball_capacity_factor_sag1 is not None else one_ball_capacity_factor
            _f2 = one_ball_capacity_factor_sag2 if one_ball_capacity_factor_sag2 is not None else one_ball_capacity_factor
            _ceil1 = P90["SAG1"] * (1.0 if _nb1_eff >= 2 else (_f1 if _nb1_eff == 1 else 0.0))
            _ceil2 = P90["SAG2"] * (1.0 if _nb2_eff >= 2 else (_f2 if _nb2_eff == 1 else 0.0))
            qout1 = min(qout1, _ceil1) if sag1_activo else 0.0
            qout2 = min(qout2, _ceil2) if sag2_activo else 0.0

        cv315_arr[i] = cv315
        cv316_arr[i] = cv316
        chancado_arr[i] = cap_chanc
        t3_arr[i] = t3_i

        # Balance de masa con overflow/rechazo explicitos — Reglas 6-7.
        # Si multicell_enabled=False, preserva el comportamiento agregado
        # original. Si True, aplica el mismo kernel por canal y luego
        # re-agrega a nivel de pila total.
        if multicell_enabled:
            _step1 = _smc.advance_multicell_stockpile(
                channel_tons=multicell_channels1,
                qin_requested_tph=qin1,
                qout_requested_tph=qout1,
                cap_total_ton=CAP_TON["SAG1"],
                delta_t_h=DT,
                config=_mcfg1,
                lateral_transfer_coeff_h=multicell_lateral_transfer_coeff_sag1,
            )
            _step2 = _smc.advance_multicell_stockpile(
                channel_tons=multicell_channels2,
                qin_requested_tph=qin2,
                qout_requested_tph=qout2,
                cap_total_ton=CAP_TON["SAG2"],
                delta_t_h=DT,
                config=_mcfg2,
                lateral_transfer_coeff_h=multicell_lateral_transfer_coeff_sag2,
            )
            multicell_channels1 = _step1["channel_tons_next"]
            multicell_channels2 = _step2["channel_tons_next"]
            qout1 = _step1["qout_effective_tph"]
            qout2 = _step2["qout_effective_tph"]
            _acc1 = _step1["accepted_feed_tph"]
            _acc2 = _step2["accepted_feed_tph"]
            _ovf1 = _step1["overflow_ton"]
            _ovf2 = _step2["overflow_ton"]
            _rej1 = _step1["rejected_feed_tph"]
            _rej2 = _step2["rejected_feed_tph"]
            pile1[i + 1] = _smc.aggregate_pile_pct(multicell_channels1, CAP_TON["SAG1"])
            pile2[i + 1] = _smc.aggregate_pile_pct(multicell_channels2, CAP_TON["SAG2"])
            pile1_channels_arr[:, i + 1] = np.asarray(
                _smc.channel_levels_pct(multicell_channels1, CAP_TON["SAG1"]), dtype=float
            )
            pile2_channels_arr[:, i + 1] = np.asarray(
                _smc.channel_levels_pct(multicell_channels2, CAP_TON["SAG2"]), dtype=float
            )
            active_channels1_arr[i] = int(_step1["active_channels"])
            active_channels2_arr[i] = int(_step2["active_channels"])
            rate_cap1_arr[i] = float(_step1["rate_cap_tph"])
            rate_cap2_arr[i] = float(_step2["rate_cap_tph"])
            base_rate_cap1_arr[i] = float(_step1.get("base_rate_cap_tph", _step1["rate_cap_tph"]))
            base_rate_cap2_arr[i] = float(_step2.get("base_rate_cap_tph", _step2["rate_cap_tph"]))
            spatial_cap_factor1_arr[i] = float(_step1.get("spatial_capacity_factor", 1.0))
            spatial_cap_factor2_arr[i] = float(_step2.get("spatial_capacity_factor", 1.0))
            lateral_moved1_arr[i] = float(_step1.get("lateral_moved_ton", 0.0))
            lateral_moved2_arr[i] = float(_step2.get("lateral_moved_ton", 0.0))
        else:
            _pile1_ton = pile1[i] / 100.0 * CAP_TON["SAG1"]
            _pile2_ton = pile2[i] / 100.0 * CAP_TON["SAG2"]
            _pile1_ton_next, _acc1, _ovf1, _rej1, _qout1_eff = _cs.update_stockpile_mass_balance(
                _pile1_ton, qin1, qout1, CAP_TON["SAG1"], DT)
            _pile2_ton_next, _acc2, _ovf2, _rej2, _qout2_eff = _cs.update_stockpile_mass_balance(
                _pile2_ton, qin2, qout2, CAP_TON["SAG2"], DT)
            qout1, qout2 = _qout1_eff, _qout2_eff
            pile1[i + 1] = _pile1_ton_next / CAP_TON["SAG1"] * 100.0
            pile2[i + 1] = _pile2_ton_next / CAP_TON["SAG2"] * 100.0

        # Regla 6: si la pila no alcanzaba para sostener el rate
        # solicitado, el consumo REAL (tph1/tph2, lo que se reporta y se
        # grafica) queda limitado a lo disponible — nunca se muestra un
        # SAG consumiendo mineral que la pila no tenia.
        tph1[i], tph2[i] = qout1, qout2
        _prev_qout1, _prev_qout2 = qout1, qout2
        overflow1_arr[i] = _ovf1
        overflow2_arr[i] = _ovf2
        rejected1_arr[i] = _rej1
        rejected2_arr[i] = _rej2
        _cum_in1_ton += _acc1 * DT; _cum_out1_ton += qout1 * DT; _cum_overflow1_ton += _ovf1
        _cum_in2_ton += _acc2 * DT; _cum_out2_ton += qout2 * DT; _cum_overflow2_ton += _ovf2

        # Riesgo de pila
        risk1[i] = _pile_risk(pile1[i], "SAG1")
        risk2[i] = _pile_risk(pile2[i], "SAG2")

        bola411_arr[i] = b411_eff
        bola412_arr[i] = b412_eff
        bola511_arr[i] = b511_eff
        bola512_arr[i] = b512_eff

    # Ultimo paso
    time_arr[n_steps] = n_steps * DT
    auton1[n_steps] = compute_autonomia(pile1[n_steps], "SAG1")
    auton2[n_steps] = compute_autonomia(pile2[n_steps], "SAG2")
    risk1[n_steps] = _pile_risk(pile1[n_steps], "SAG1")
    risk2[n_steps] = _pile_risk(pile2[n_steps], "SAG2")
    # TPH final (replica ultimo paso)
    tph1[n_steps] = tph1[n_steps - 1]
    tph2[n_steps] = tph2[n_steps - 1]
    cv315_arr[n_steps] = cv315_arr[n_steps - 1]
    cv316_arr[n_steps] = cv316_arr[n_steps - 1]
    chancado_arr[n_steps] = cap_chanc
    t3_arr[n_steps] = t3_arr[n_steps - 1]
    bola411_arr[n_steps] = bola411_arr[n_steps - 1]
    bola412_arr[n_steps] = bola412_arr[n_steps - 1]
    bola511_arr[n_steps] = bola511_arr[n_steps - 1]
    bola512_arr[n_steps] = bola512_arr[n_steps - 1]
    overflow1_arr[n_steps] = overflow1_arr[n_steps - 1]
    overflow2_arr[n_steps] = overflow2_arr[n_steps - 1]
    rejected1_arr[n_steps] = rejected1_arr[n_steps - 1]
    rejected2_arr[n_steps] = rejected2_arr[n_steps - 1]
    if multicell_enabled:
        active_channels1_arr[n_steps] = active_channels1_arr[n_steps - 1]
        active_channels2_arr[n_steps] = active_channels2_arr[n_steps - 1]
        rate_cap1_arr[n_steps] = rate_cap1_arr[n_steps - 1]
        rate_cap2_arr[n_steps] = rate_cap2_arr[n_steps - 1]
        base_rate_cap1_arr[n_steps] = base_rate_cap1_arr[n_steps - 1]
        base_rate_cap2_arr[n_steps] = base_rate_cap2_arr[n_steps - 1]
        spatial_cap_factor1_arr[n_steps] = spatial_cap_factor1_arr[n_steps - 1]
        spatial_cap_factor2_arr[n_steps] = spatial_cap_factor2_arr[n_steps - 1]
        lateral_moved1_arr[n_steps] = lateral_moved1_arr[n_steps - 1]
        lateral_moved2_arr[n_steps] = lateral_moved2_arr[n_steps - 1]

    # ── Diagnosticos del kernel de dominio (claves aditivas) ─────────────────
    mass_balance_error_sag1 = _cs.validate_mass_conservation(
        pila_sag1_pct / 100.0 * CAP_TON["SAG1"], _cum_in1_ton, _cum_out1_ton,
        pile1[n_steps] / 100.0 * CAP_TON["SAG1"], _cum_overflow1_ton)
    mass_balance_error_sag2 = _cs.validate_mass_conservation(
        pila_sag2_pct / 100.0 * CAP_TON["SAG2"], _cum_in2_ton, _cum_out2_ton,
        pile2[n_steps] / 100.0 * CAP_TON["SAG2"], _cum_overflow2_ton)

    autonomy_hours_sag1, autonomy_message_sag1 = _cs.calculate_stockpile_autonomy(
        pile1[n_steps] / 100.0 * CAP_TON["SAG1"],
        CRITICAL_PCT["SAG1"] / 100.0 * CAP_TON["SAG1"],
        cv315_arr[n_steps], tph1[n_steps])
    autonomy_hours_sag2, autonomy_message_sag2 = _cs.calculate_stockpile_autonomy(
        pile2[n_steps] / 100.0 * CAP_TON["SAG2"],
        CRITICAL_PCT["SAG2"] / 100.0 * CAP_TON["SAG2"],
        cv316_arr[n_steps], tph2[n_steps])

    pile_trend_sag1 = _cs.determine_pile_trend(cv315_arr[n_steps], tph1[n_steps])
    pile_trend_sag2 = _cs.determine_pile_trend(cv316_arr[n_steps], tph2[n_steps])
    operational_state_sag1 = _cs.determine_operational_state(
        sag_requested_on=sag1_activo, sag_effective_on=sag1_activo,
        rate_effective=tph1[n_steps], rate_target=_rate1_tph_base,
        is_starved=(pile1[n_steps] <= CRITICAL_PCT["SAG1"]),
        is_restricted_by_balls=(bool(_b411) or bool(_b412)) and not (b411_eff and b412_eff),
    )
    operational_state_sag2 = _cs.determine_operational_state(
        sag_requested_on=sag2_activo, sag_effective_on=sag2_activo,
        rate_effective=tph2[n_steps], rate_target=_rate2_tph_base,
        is_starved=(pile2[n_steps] <= CRITICAL_PCT["SAG2"]),
        is_restricted_by_balls=(bool(_b511) or bool(_b512)) and not (b511_eff and b512_eff),
    )

    # ── Fase 2 (2026-07-14): motivo de restricción explícito ─────────────────
    # (Regla 15 del pedido — "RESTRICTED" solo no dice nada al JdS).
    restriction_reason_sag1, secondary_restrictions_sag1 = _cs.determine_restriction_reason(
        sag_effective_on=sag1_activo, n_balls_effective=_nb1_eff, n_balls_requested=_n_bolas1,
        pile_pct=pile1[n_steps], critical_pct=CRITICAL_PCT["SAG1"], warning_pct=WARNING_PCT["SAG1"],
        window_factor=_cs.resolve_window_feed_factor(_windows, n_steps * DT, "sac1")[0],
        is_ramping_up=(tph1[n_steps] > tph1[max(0, n_steps - 1)] + 1.0 if sag_ramp_up_time_min > 0 else False),
        is_ramping_down=(tph1[n_steps] < tph1[max(0, n_steps - 1)] - 1.0 if sag_ramp_down_time_min > 0 else False),
        rate_effective=tph1[n_steps], rate_target=_rate1_tph_base,
        overflow_ton=overflow1_arr[n_steps], rejected_feed_tph=rejected1_arr[n_steps],
    )
    restriction_reason_sag2, secondary_restrictions_sag2 = _cs.determine_restriction_reason(
        sag_effective_on=sag2_activo, n_balls_effective=_nb2_eff, n_balls_requested=_n_bolas2,
        pile_pct=pile2[n_steps], critical_pct=CRITICAL_PCT["SAG2"], warning_pct=WARNING_PCT["SAG2"],
        window_factor=_cs.resolve_window_feed_factor(_windows, n_steps * DT, "sac2")[0],
        is_ramping_up=(tph2[n_steps] > tph2[max(0, n_steps - 1)] + 1.0 if sag_ramp_up_time_min > 0 else False),
        is_ramping_down=(tph2[n_steps] < tph2[max(0, n_steps - 1)] - 1.0 if sag_ramp_down_time_min > 0 else False),
        rate_effective=tph2[n_steps], rate_target=_rate2_tph_base,
        overflow_ton=overflow2_arr[n_steps], rejected_feed_tph=rejected2_arr[n_steps],
    )

    # ── Fase 2: autonomía unificada — comparación legacy vs. balance neto ────
    # (Regla 3 del pedido: `compute_autonomia` sigue viva para sus ~15
    # consumidores existentes, marcada legacy; `autonomy_hours_sagX`
    # (balance neto, ya calculado arriba) es la ÚNICA fuente para lo que se
    # MUESTRA al JdS. Si divergen mucho, queda registrado, no oculto.)
    _legacy_autonomia_sag1 = compute_autonomia(pile1[n_steps], "SAG1")
    _legacy_autonomia_sag2 = compute_autonomia(pile2[n_steps], "SAG2")
    autonomy_diff_sag1, autonomy_diverges_sag1 = _cs.compare_autonomy_sources(
        _legacy_autonomia_sag1, autonomy_hours_sag1)
    autonomy_diff_sag2, autonomy_diverges_sag2 = _cs.compare_autonomy_sources(
        _legacy_autonomia_sag2, autonomy_hours_sag2)
    if autonomy_diverges_sag1 or autonomy_diverges_sag2:
        import logging
        logging.getLogger("dashboard.ode_model").debug(
            "Autonomia legacy vs balance neto diverge >1h: SAG1 legacy=%.2f neto=%s diff=%s | "
            "SAG2 legacy=%.2f neto=%s diff=%s",
            _legacy_autonomia_sag1, autonomy_hours_sag1, autonomy_diff_sag1,
            _legacy_autonomia_sag2, autonomy_hours_sag2, autonomy_diff_sag2,
        )

    # ── Reencuadre semántico de autonomía — Etapa 1 (2026-07-14, ver
    # 04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md,
    # 'Quinta pasada'). Claves puramente aditivas: ninguna clave/cálculo
    # previo de este bloque cambia. `compute_autonomia`/
    # `calculate_stockpile_autonomy` siguen siendo la fuente numérica —
    # esto solo agrega el estado categórico y el semáforo de
    # vulnerabilidad que hoy no existen. ─────────────────────────────────
    _dyn_autonomy_sag1 = _cs.classify_dynamic_autonomy(
        pile1[n_steps] / 100.0 * CAP_TON["SAG1"], CRITICAL_PCT["SAG1"] / 100.0 * CAP_TON["SAG1"],
        cv315_arr[n_steps], tph1[n_steps])
    _dyn_autonomy_sag2 = _cs.classify_dynamic_autonomy(
        pile2[n_steps] / 100.0 * CAP_TON["SAG2"], CRITICAL_PCT["SAG2"] / 100.0 * CAP_TON["SAG2"],
        cv316_arr[n_steps], tph2[n_steps])
    _vulnerability_sag1 = _cs.classify_historical_vulnerability(_legacy_autonomia_sag1, "SAG1")
    _vulnerability_sag2 = _cs.classify_historical_vulnerability(_legacy_autonomia_sag2, "SAG2")
    _divergence_class_sag1 = _cs.classify_autonomy_divergence(_legacy_autonomia_sag1, _dyn_autonomy_sag1)
    _divergence_class_sag2 = _cs.classify_autonomy_divergence(_legacy_autonomia_sag2, _dyn_autonomy_sag2)

    # ── Fase 2: episodio de ventana (semántica temporal, secciones 1/4/5) ────
    episodio_sag1 = None
    episodio_sag2 = None
    if duracion_t8_h > 0:
        _w0 = _windows[0]
        episodio_sag1 = _cs.analyze_window_episode(
            time_arr.tolist(), pile1.tolist(), cv315_arr.tolist(), tph1.tolist(),
            _w0.start_time, _w0.end_time, CAP_TON["SAG1"], CRITICAL_PCT["SAG1"])
        episodio_sag2 = _cs.analyze_window_episode(
            time_arr.tolist(), pile2.tolist(), cv316_arr.tolist(), tph2.tolist(),
            _w0.start_time, _w0.end_time, CAP_TON["SAG2"], CRITICAL_PCT["SAG2"])

    # ── Fase 2: bloque de calidad de simulación (sección 10) ─────────────────
    _mass_tol_ton = max(1.0, 0.001 * CAP_TON["SAG1"])
    consistente_sag1, advertencias_sag1 = _cs.evaluate_simulation_quality(
        mass_balance_error_sag1, _mass_tol_ton, pile1.tolist(), tph1.tolist())
    consistente_sag2, advertencias_sag2 = _cs.evaluate_simulation_quality(
        mass_balance_error_sag2, max(1.0, 0.001 * CAP_TON["SAG2"]), pile2.tolist(), tph2.tolist())

    # Suavizado de trayectoria de pila (rolling mean 3 pasos = 15 min)
    # Preserva valores extremos en bordes usando modo "nearest"
    from scipy.ndimage import uniform_filter1d
    _w = 3
    pile1_s = uniform_filter1d(pile1, size=_w, mode="nearest")
    pile2_s = uniform_filter1d(pile2, size=_w, mode="nearest")
    auton1_s = uniform_filter1d(auton1, size=_w, mode="nearest")
    auton2_s = uniform_filter1d(auton2, size=_w, mode="nearest")

    return {
        "time": time_arr.tolist(),
        "pile_sag1": pile1_s.tolist(),
        "pile_sag2": pile2_s.tolist(),
        "tph_sag1": tph1.tolist(),
        "tph_sag2": tph2.tolist(),
        "tph_total": (tph1 + tph2).tolist(),
        "autonomia_sag1": auton1_s.tolist(),
        "autonomia_sag2": auton2_s.tolist(),
        "riesgo_sag1": risk1.tolist(),
        "riesgo_sag2": risk2.tolist(),
        "cv315": cv315_arr.tolist(),
        "cv316": cv316_arr.tolist(),
        "chancado_cap": chancado_arr.tolist(),
        "bola411": bola411_arr.tolist(),
        "bola412": bola412_arr.tolist(),
        "bola511": bola511_arr.tolist(),
        "bola512": bola512_arr.tolist(),
        "t1": t1_arr_out.tolist(),
        "t3": t3_arr.tolist(),
        # ── Claves aditivas del kernel de dominio (2026-07-14) ────────────────
        "overflow_sag1": overflow1_arr.tolist(),
        "overflow_sag2": overflow2_arr.tolist(),
        "rejected_feed_sag1": rejected1_arr.tolist(),
        "rejected_feed_sag2": rejected2_arr.tolist(),
        "mass_balance_error_sag1": mass_balance_error_sag1,
        "mass_balance_error_sag2": mass_balance_error_sag2,
        "dependency_message_sag1": dependency_message_sag1,
        "dependency_message_sag2": dependency_message_sag2,
        "operational_state_sag1": operational_state_sag1,
        "operational_state_sag2": operational_state_sag2,
        "pile_trend_sag1": pile_trend_sag1,
        "pile_trend_sag2": pile_trend_sag2,
        "autonomy_hours_sag1": autonomy_hours_sag1,
        "autonomy_hours_sag2": autonomy_hours_sag2,
        "autonomy_message_sag1": autonomy_message_sag1,
        "autonomy_message_sag2": autonomy_message_sag2,
        # ── Claves aditivas Fase 2 (2026-07-14, segunda fase) ──────────────────
        "legacy_autonomia_sag1": _legacy_autonomia_sag1,
        "legacy_autonomia_sag2": _legacy_autonomia_sag2,
        "autonomy_diff_sag1_h": autonomy_diff_sag1,
        "autonomy_diff_sag2_h": autonomy_diff_sag2,
        "autonomy_diverges_sag1": autonomy_diverges_sag1,
        "autonomy_diverges_sag2": autonomy_diverges_sag2,
        # ── Claves semánticas nuevas — reencuadre Etapa 1 (2026-07-14) ────────
        "historical_preventive_autonomy_sag1_h": _legacy_autonomia_sag1,
        "historical_preventive_autonomy_sag2_h": _legacy_autonomia_sag2,
        "historical_vulnerability_sag1": _vulnerability_sag1,
        "historical_vulnerability_sag2": _vulnerability_sag2,
        "dynamic_net_autonomy_sag1_h": _dyn_autonomy_sag1.hours,
        "dynamic_net_autonomy_sag2_h": _dyn_autonomy_sag2.hours,
        "dynamic_net_autonomy_sag1_status": _dyn_autonomy_sag1.status,
        "dynamic_net_autonomy_sag2_status": _dyn_autonomy_sag2.status,
        "dynamic_net_autonomy_sag1_rate_tph": _dyn_autonomy_sag1.net_drain_rate_tph,
        "dynamic_net_autonomy_sag2_rate_tph": _dyn_autonomy_sag2.net_drain_rate_tph,
        "dynamic_net_autonomy_sag1_message": _dyn_autonomy_sag1.message,
        "dynamic_net_autonomy_sag2_message": _dyn_autonomy_sag2.message,
        "autonomy_divergence_class_sag1": _divergence_class_sag1,
        "autonomy_divergence_class_sag2": _divergence_class_sag2,
        "restriction_reason_sag1": restriction_reason_sag1,
        "restriction_reason_sag2": restriction_reason_sag2,
        "secondary_restrictions_sag1": secondary_restrictions_sag1,
        "secondary_restrictions_sag2": secondary_restrictions_sag2,
        "window_episode_sag1": episodio_sag1,
        "window_episode_sag2": episodio_sag2,
        "simulation_consistent_sag1": consistente_sag1,
        "simulation_consistent_sag2": consistente_sag2,
        "simulation_warnings_sag1": advertencias_sag1,
        "simulation_warnings_sag2": advertencias_sag2,
        # ── Fase 1 multi-celda (aditivo, apagado por default) ───────────────
        "multicell_enabled": multicell_enabled,
        "pile_sag1_channels_pct": pile1_channels_arr.tolist() if multicell_enabled else None,
        "pile_sag2_channels_pct": pile2_channels_arr.tolist() if multicell_enabled else None,
        "active_channels_sag1": active_channels1_arr.tolist() if multicell_enabled else None,
        "active_channels_sag2": active_channels2_arr.tolist() if multicell_enabled else None,
        "multicell_base_rate_cap_sag1_tph": base_rate_cap1_arr.tolist() if multicell_enabled else None,
        "multicell_base_rate_cap_sag2_tph": base_rate_cap2_arr.tolist() if multicell_enabled else None,
        "multicell_rate_cap_sag1_tph": rate_cap1_arr.tolist() if multicell_enabled else None,
        "multicell_rate_cap_sag2_tph": rate_cap2_arr.tolist() if multicell_enabled else None,
        "multicell_spatial_capacity_factor_sag1": spatial_cap_factor1_arr.tolist() if multicell_enabled else None,
        "multicell_spatial_capacity_factor_sag2": spatial_cap_factor2_arr.tolist() if multicell_enabled else None,
        "multicell_lateral_moved_sag1_ton": lateral_moved1_arr.tolist() if multicell_enabled else None,
        "multicell_lateral_moved_sag2_ton": lateral_moved2_arr.tolist() if multicell_enabled else None,
        "multicell_channel_labels_sag1": list(_mcfg1.channel_labels) if multicell_enabled else None,
        "multicell_channel_labels_sag2": list(_mcfg2.channel_labels) if multicell_enabled else None,
        "multicell_ignored_channels_sag1": list(_mcfg1.ignored_channels) if multicell_enabled else None,
        "multicell_ignored_channels_sag2": list(_mcfg2.ignored_channels) if multicell_enabled else None,
        "multicell_lateral_transfer_coeff_sag1": float(multicell_lateral_transfer_coeff_sag1) if multicell_enabled else 0.0,
        "multicell_lateral_transfer_coeff_sag2": float(multicell_lateral_transfer_coeff_sag2) if multicell_enabled else 0.0,
        "multicell_spatial_capacity_mode_sag1": str(multicell_spatial_capacity_mode_sag1) if multicell_enabled else "none",
        "multicell_spatial_capacity_mode_sag2": str(multicell_spatial_capacity_mode_sag2) if multicell_enabled else "none",
    }


def _feed_con_recuperacion(windows, t_h: float, asset_key: str, f_in_normal: float,
                            feed_recovery_time_min: float, feed_recovery_mode: str,
                            feed_recovery_tau_min) -> float:
    """Alimentacion efectiva en el instante t_h, incluyendo recuperacion
    gradual tras la ventana mas reciente que afecto a este activo (Fase 2
    seccion 6). Con feed_recovery_time_min=0 (default) es equivalente a
    multiplicar por el factor de ventana actual (recuperacion instantanea,
    comportamiento previo)."""
    factor_ahora, _ = _cs.resolve_window_feed_factor(windows, t_h, asset_key)
    if factor_ahora < 1.0:
        return _cs.calculate_effective_feed(f_in_normal, factor_ahora, None)

    ventanas_relevantes = [w for w in windows if w.end_time <= t_h
                           and getattr(w, f"feed_factor_{asset_key}") < 1.0]
    if not ventanas_relevantes:
        return f_in_normal

    w = max(ventanas_relevantes, key=lambda w: w.end_time)
    elapsed_h = t_h - w.end_time
    factor_window = getattr(w, f"feed_factor_{asset_key}")
    return _cs.calculate_effective_feed(
        f_in_normal, factor_window, elapsed_h,
        feed_recovery_time_min, feed_recovery_mode, feed_recovery_tau_min,
    )


def _pile_risk(pile_pct: float, asset: str) -> int:
    """0=ok (verde), 1=warning (naranja), 2=critico (rojo)"""
    crit = CRITICAL_PCT[asset]
    if pile_pct <= crit:
        return 2
    if pile_pct <= WARNING_PCT[asset]:
        return 1
    return 0
