"""
optimizer_v2.py — Optimizador operacional multicriterio v2.

Funcion objetivo ponderada por regimen operacional:

  Regimen NORMAL (sin T8):
    Produccion 65% / Riesgo 20% / Inventario 10% / Autonomia 5%
    MIN_AUTON: SAG1=0.5h, SAG2=0.75h
    Razon: el CV315 alimenta continuamente; la pila existe para ser consumida.

  Regimen T8 CORTA (<=4h):
    Produccion 48% / Riesgo 32% / Inventario 12% / Autonomia 8%
    MIN_AUTON: SAG1=1.0h, SAG2=1.5h

  Regimen T8 LARGA (>4h):
    Produccion 35% / Riesgo 35% / Inventario 20% / Autonomia 10%
    MIN_AUTON: SAG1=1.5h, SAG2=2.0h

Modos de seleccion:
  "balanced"  — maximiza score multicriterio del regimen activo
  "max_prod"  — maximiza TPH (riesgo ignorado)
  "safe"      — filtra P(safe)>=0.95, luego maximiza TPH
  "pareto"    — top del frente Pareto (tph_mean, p_safe, inv_mean)
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from engine.simulator import simulate_scenario  # noqa: E402
from utils.perf_logger import timed  # noqa: E402

# ---- Candidatos del grid ----------------------------------------------------
# Regla operacional (UX/UI v2 JdS, 2026-07-07, CAMBIO 10): no existe
# escenario operacional valido con 0 MoBos activos por SAG — "sin_bola"
# se elimina de los candidatos que el optimizador puede RECOMENDAR (grid,
# Monte Carlo, constraint solver). Sigue existiendo como valor interno en
# engine/simulator.py (parametro por defecto de simulate_scenario cuando
# el SAG esta apagado) y en optimizer_v3.compute_roi_bolas (baseline de
# comparacion "sin bolas vs con bolas" para calcular el ROI incremental)
# — ninguno de esos dos usos es una recomendacion operacional al usuario.
R1_CANDS = [727, 1018, 1309, 1454, 1527]
R2_CANDS = [1888, 2214, 2365, 2516, 2642]
BOLA1_OPTS = ["solo_411", "ambas_411_412"]
BOLA2_OPTS = ["solo_511", "ambas_511_512"]

# Grilla per-mill (411/412/511/512 independientes) — usada solo cuando el
# llamador pasa `bola1_opts`/`bola2_opts` explicitos a run_deterministic_grid
# / find_optimal_v2 / find_optimal_v3 (ej. pages/simulador_operacional.py).
# Los demas llamadores (pagina /riesgo, boton "Simular Monte Carlo") no pasan
# estos parametros y siguen usando BOLA1_OPTS/BOLA2_OPTS sin cambios.
BOLA1_OPTS_FULL = ["solo_411", "solo_412", "ambas_411_412"]
BOLA2_OPTS_FULL = ["solo_511", "solo_512", "ambas_511_512"]

# ---- Normalizacion ----------------------------------------------------------
REF_AUTON_SAG1 = 6.0
REF_AUTON_SAG2 = 8.0
TPH_REF_MAX    = 1454.0 + 2516.0   # 3970 TPH
INV_REF_FULL   = 70.0

P_SAFE_THRESHOLD = 0.95

MC_MAX_N       = 500
MC_BATCH       = 10
MC_CONV_TOL    = 0.01
MC_CONV_CONSEC = 3
MC_MIN_N       = 30
TOP_CANDS_FOR_MC = 20

# Limite de seguridad adicional (Fase 8 performance, 2026-07-06): NO cambia
# el tuning matematico validado de arriba (MC_MAX_N/MC_BATCH/MC_CONV_TOL/
# MC_CONV_CONSEC/MC_MIN_N siguen intactos). Es un techo de tiempo real que
# corta el loop si por algun motivo (maquina lenta del usuario final, .exe
# empaquetado) el criterio de convergencia tarda demasiado — la app nunca
# debe congelarse esperando Monte Carlo. Si se activa, el resultado usa la
# ultima estimacion valida y queda marcado como no convergente.
MC_MAX_SECONDS = 8.0

# ---- Regimenes operacionales -------------------------------------------------
# La pila no es un activo para conservar; es un activo para consumir cuando
# genera valor. La autonomia solo es critica cuando hay riesgo real de T8.

REGIMES: dict[str, dict] = {
    "normal": {
        "label":      "Operacion Normal (sin T8)",
        "t8_max":     0.0,
        "weights":    {"produccion": 0.65, "riesgo": 0.20, "inventario": 0.10, "autonomia": 0.05},
        "min_auton":  {"SAG1": 0.5,  "SAG2": 0.75},
    },
    "t8_corta": {
        "label":      "Ventana T8 Corta (<=4h)",
        "t8_max":     4.0,
        "weights":    {"produccion": 0.48, "riesgo": 0.32, "inventario": 0.12, "autonomia": 0.08},
        "min_auton":  {"SAG1": 1.0,  "SAG2": 1.5},
    },
    "t8_larga": {
        "label":      "Ventana T8 Larga (>4h)",
        "t8_max":     999.0,
        "weights":    {"produccion": 0.35, "riesgo": 0.35, "inventario": 0.20, "autonomia": 0.10},
        "min_auton":  {"SAG1": 1.5,  "SAG2": 2.0},
    },
}

# Alias retrocompatibilidad
SCORE_WEIGHTS  = REGIMES["t8_larga"]["weights"]
MIN_AUTON_SAG1 = REGIMES["t8_larga"]["min_auton"]["SAG1"]
MIN_AUTON_SAG2 = REGIMES["t8_larga"]["min_auton"]["SAG2"]


def get_regime(duracion_t8: float) -> tuple[str, dict]:
    """Retorna (nombre_regimen, dict_regimen) segun duracion T8."""
    if duracion_t8 <= 0:
        return "normal", REGIMES["normal"]
    elif duracion_t8 <= 4.0:
        return "t8_corta", REGIMES["t8_corta"]
    else:
        return "t8_larga", REGIMES["t8_larga"]


# ---- Funcion objetivo ponderada ----------------------------------------------

def compute_multi_criteria_score(
    tph_mean: float,
    p_safe: float,
    inv_sag1_final: float,
    inv_sag2_final: float,
    a1_min: float,
    a2_min: float,
    weights: dict | None = None,
) -> float:
    """Score operacional normalizado [0,1] con pesos ajustables por regimen.

    Duplicación documentada (Fase 3.2 del roadmap de cierre, 2026-07-15,
    ver 04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_
    Operacional.md): `inv_norm` (inventario final de pila, % directo) y
    `auton_norm` (autonomía histórica mínima, que a su vez es
    `compute_autonomia(pile_pct)` — una función DIRECTA y monótona del
    mismo % de pila) están correlacionadas algebraicamente. Los pesos
    `w["inventario"]` + `w["autonomia"]` (12-20% + 5-10% según régimen,
    ver docstring del módulo) penalizan dos veces, con distinta
    intensidad, la misma señal subyacente ("¿qué tan baja termina la
    pila?"). No se recalibran los pesos aquí sin datos que lo respalden
    — se documenta y se agrega `compute_dual_score` como comparación
    aditiva (Fase 3.3-3.4), sin tocar esta función ni el score que
    decide la selección real."""
    w = weights or SCORE_WEIGHTS
    prod_norm  = min(tph_mean / TPH_REF_MAX, 1.0)
    risk_norm  = float(p_safe)
    inv_norm   = min((inv_sag1_final + inv_sag2_final) / 2.0 / INV_REF_FULL, 1.0)
    auton_norm = min((a1_min / REF_AUTON_SAG1 + a2_min / REF_AUTON_SAG2) / 2.0, 1.0)
    return (
        w["produccion"]  * prod_norm
        + w["riesgo"]    * risk_norm
        + w["inventario"] * inv_norm
        + w["autonomia"] * auton_norm
    )


# ---- Dual score (Fase 3.3-3.4 del roadmap de cierre, 2026-07-15) ------------
# Puramente informativo/comparativo: NO reemplaza compute_multi_criteria_score
# ni el det_score que ordena run_deterministic_grid/adaptive_mc_eval — "antes
# de reemplazar la selección oficial" (instrucción explícita del pedido) hace
# falta comparar rankings con datos reales, no solo con la lógica aquí.

_VULN_BUFFER_SCORE = {"BAJA": 1.0, "MEDIA": 0.7, "ALTA": 0.4, "CRITICA": 0.1}


def compute_dual_score(candidate: dict) -> dict:
    """Calcula `dynamic_safety_score`/`historical_buffer_score` a partir
    de los campos dinámicos ya agregados a cada candidato en
    `run_deterministic_grid` (Etapa 1, sin recomputar nada — `simulate_
    scenario` ya los produce por candidato). Retorna un dict con
    `score_legacy` (alias de `det_score`), los 2 sub-scores nuevos, y
    `ranking_diverges` reservado para uso agregado (ver `compare_
    rankings`)."""
    dyn_status1 = candidate.get("dynamic_status_sag1")
    dyn_status2 = candidate.get("dynamic_status_sag2")
    dyn_h1 = candidate.get("dynamic_autonomy_sag1_h")
    dyn_h2 = candidate.get("dynamic_autonomy_sag2_h")

    def _safety(status, hours, ref):
        if status in ("FILLING", "STABLE", "SAG_OFF"):
            return 1.0
        if status == "AT_CRITICAL_LEVEL":
            return 0.0
        if status == "DRAINING" and hours is not None:
            return max(0.0, min(1.0, hours / ref))
        return None  # sin dato (candidato sin claves dinamicas, p.ej. legacy)

    s1 = _safety(dyn_status1, dyn_h1, REF_AUTON_SAG1)
    s2 = _safety(dyn_status2, dyn_h2, REF_AUTON_SAG2)
    dynamic_safety_score = None if (s1 is None or s2 is None) else min(s1, s2)

    vuln1 = candidate.get("historical_vulnerability_sag1")
    vuln2 = candidate.get("historical_vulnerability_sag2")
    b1 = _VULN_BUFFER_SCORE.get(vuln1)
    b2 = _VULN_BUFFER_SCORE.get(vuln2)
    historical_buffer_score = None if (b1 is None or b2 is None) else min(b1, b2)

    return {
        "score_legacy": candidate.get("det_score"),
        "dynamic_safety_score": dynamic_safety_score,
        "historical_buffer_score": historical_buffer_score,
    }


def compare_rankings(results: list[dict]) -> dict:
    """Fase 3.4: compara el top-1 por `det_score` (legacy, el que
    realmente selecciona `run_deterministic_grid` hoy) contra el top-1
    que resultaría de ordenar solo por `dynamic_safety_score`. No
    modifica `results` ni decide una nueva selección — es evidencia para
    decidir, no una decisión tomada en silencio."""
    if not results:
        return {"ranking_diverges": False, "top_legacy": None, "top_dynamic": None}
    con_score = [r for r in results if compute_dual_score(r)["dynamic_safety_score"] is not None]
    if not con_score:
        return {"ranking_diverges": False, "top_legacy": results[0].get("label_short"), "top_dynamic": None}
    top_legacy = results[0]
    top_dynamic = max(con_score, key=lambda r: compute_dual_score(r)["dynamic_safety_score"])
    return {
        "ranking_diverges": top_legacy.get("label_short") != top_dynamic.get("label_short"),
        "top_legacy": top_legacy.get("label_short"),
        "top_dynamic": top_dynamic.get("label_short"),
    }


# ---- Grid determinístico -----------------------------------------------------

def run_deterministic_grid(
    pila1: float, pila2: float, duracion_t8: float,
    sag1_on: bool, sag2_on: bool,
    ch1_on: bool, ch2_on: bool,
    c315: str, c316: str,
    t1_mode: str, t1_manual: float,
    t3_frac: float, distribucion_t1: str,
    horizonte: float = 24.0,
    min_auton_sag1: float = MIN_AUTON_SAG1,
    min_auton_sag2: float = MIN_AUTON_SAG2,
    weights: dict | None = None,
    r1_cands: list | None = None,
    r2_cands: list | None = None,
    bola1_opts: list | None = None,
    bola2_opts: list | None = None,
    simulation_overrides: dict | None = None,
) -> list[dict]:
    """Grid configs. min_auton, weights y candidatos de tasa ajustables por regimen.

    `bola1_opts`/`bola2_opts`: lista de opciones de bola a usar en vez de los
    defaults BOLA1_OPTS/BOLA2_OPTS (ej. BOLA1_OPTS_FULL filtrada por
    mantenciones activas). Si None, comportamiento identico al anterior.

    `simulation_overrides`: kwargs opcionales que se propagan a
    simulate_scenario() (ej. modo multi-celda). Apagado por default para
    preservar comportamiento historico.
    """
    r1_list = (r1_cands or R1_CANDS) if sag1_on else [727]
    r2_list = (r2_cands or R2_CANDS) if sag2_on else [1888]
    b1_list = (bola1_opts or BOLA1_OPTS) if sag1_on else ["sin_bola"]
    b2_list = (bola2_opts or BOLA2_OPTS) if sag2_on else ["sin_bola"]

    # R16 — al menos 1 molino de bolas activo por SAG (restriccion dura).
    # Si sag*_on es False el SAG completo esta detenido; R16 no aplica en ese
    # caso (no hay molienda que sostener). El fallback `or ["sin_bola"]`
    # cubre el caso borde donde, tras restringir por mantencion, no queda
    # ninguna opcion valida (ambos molinos del SAG en mantencion) — se
    # señaliza aparte en la UI en vez de dejar la grilla vacia.
    if sag1_on:
        b1_list = [b for b in b1_list if b != "sin_bola"] or ["sin_bola"]
    if sag2_on:
        b2_list = [b for b in b2_list if b != "sin_bola"] or ["sin_bola"]

    sim_overrides = dict(simulation_overrides or {})
    results = []
    for r1 in r1_list:
        for b1 in b1_list:
            for r2 in r2_list:
                for b2 in b2_list:
                    try:
                        sim = simulate_scenario(
                            pila_sag1_pct=pila1, pila_sag2_pct=pila2,
                            rate_sag1_pct=100.0, rate_sag2_pct=100.0,
                            bolas_sag1=b1, bolas_sag2=b2,
                            sag1_activo=sag1_on, sag2_activo=sag2_on,
                            duracion_t8_h=duracion_t8,
                            correa315_estado=c315, correa316_estado=c316,
                            horizonte_horas=horizonte,
                            ch1_on=ch1_on, ch2_on=ch2_on,
                            cv_mode="auto",
                            rate_sag1_tph=r1, rate_sag2_tph=r2,
                            t1_mode=t1_mode, t1_manual_tph=t1_manual,
                            t3_frac=t3_frac, distribucion_t1=distribucion_t1,
                            **sim_overrides,
                        )
                    except Exception:
                        continue

                    a1  = float(sim.get("min_autonomia_sag1", 0))
                    a2  = float(sim.get("min_autonomia_sag2", 0))
                    tph = float(np.array(sim.get("tph_total", [0])).mean())

                    p1_arr = sim.get("pile_sag1", [pila1])
                    p2_arr = sim.get("pile_sag2", [pila2])
                    inv_f1 = float(p1_arr[-1]) if p1_arr else pila1
                    inv_f2 = float(p2_arr[-1]) if p2_arr else pila2

                    safe1 = (a1 >= min_auton_sag1) or not sag1_on
                    safe2 = (a2 >= min_auton_sag2) or not sag2_on
                    p_safe_det = 1.0 if (safe1 and safe2) else 0.0

                    det_score = compute_multi_criteria_score(
                        tph, p_safe_det, inv_f1, inv_f2, a1, a2, weights=weights
                    )

                    results.append({
                        "r1": r1, "b1": b1, "r2": r2, "b2": b2,
                        "tph_mean": tph,
                        "a1_min": a1, "a2_min": a2,
                        "inv_sag1_final": inv_f1,
                        "inv_sag2_final": inv_f2,
                        "p_safe_det": p_safe_det,
                        "det_score": det_score,
                        "p_safe": p_safe_det,
                        "tph_p10": tph, "tph_p90": tph,
                        "a1_med": a1, "a2_med": a2,
                        "n_samples_used": 0,
                        "converged": False,
                        "convergence_n": None,
                        "multi_criteria_score": det_score,
                        "pareto": False,
                        "label_short": _label(r1, b1, r2, b2),
                        # Fase 3.3 del roadmap de cierre (2026-07-15): campos
                        # aditivos, ya calculados por simulate_scenario -> no
                        # se ejecuta ninguna simulacion extra. Alimentan
                        # compute_dual_score/compare_rankings sin afectar
                        # det_score ni el orden de seleccion real.
                        "dynamic_status_sag1": sim.get("dynamic_net_autonomy_sag1_status"),
                        "dynamic_status_sag2": sim.get("dynamic_net_autonomy_sag2_status"),
                        "dynamic_autonomy_sag1_h": sim.get("dynamic_net_autonomy_sag1_h"),
                        "dynamic_autonomy_sag2_h": sim.get("dynamic_net_autonomy_sag2_h"),
                        "historical_vulnerability_sag1": sim.get("historical_vulnerability_sag1"),
                        "historical_vulnerability_sag2": sim.get("historical_vulnerability_sag2"),
                    })

    results.sort(key=lambda x: x["det_score"], reverse=True)
    return results


def _label(r1, b1, r2, b2) -> str:
    b1s = "B411+412" if "ambas" in b1 else ("B411" if "411" in b1 else ("B412" if "412" in b1 else "SinB"))
    b2s = "B511+512" if "ambas" in b2 else ("B511" if "511" in b2 else ("B512" if "512" in b2 else "SinB"))
    return f"S1:{r1}TPH/{b1s} | S2:{r2}TPH/{b2s}"


# ---- Monte Carlo adaptativo --------------------------------------------------

@timed("adaptive_mc_eval")
def adaptive_mc_eval(
    cand: dict,
    pila1: float, pila2: float,
    cv315_nom: float, cv316_nom: float,
    duracion_t8: float,
    sag1_on: bool, sag2_on: bool,
    ch1_on: bool, ch2_on: bool,
    c315: str, c316: str,
    t1_mode: str, t1_manual: float,
    t3_frac: float, distribucion_t1: str,
    horizonte: float = 24.0,
    seed: int = 42,
    min_auton_sag1: float = MIN_AUTON_SAG1,
    min_auton_sag2: float = MIN_AUTON_SAG2,
    weights: dict | None = None,
    simulation_overrides: dict | None = None,
) -> dict:
    """
    MC con parada adaptativa.
    Incertidumbres: pilas +-2.5%, CV feed +-12%, duracion T8 +-1h.
    Para cuando |Delta p_safe| < MC_CONV_TOL por MC_CONV_CONSEC checks consecutivos.

    Ademas de las metricas escalares historicas, acumula (sin simulaciones
    adicionales — reusa el `sim` que ya se calcula por muestra) datos para
    el fan chart / card "por que confiar" y el grafico de riesgo por hora:
    TPH por SAG, % de muestras que vacian/hacen overflow cada pila, y la
    probabilidad de vaciado/overflow por hora del horizonte.
    """
    rng = np.random.default_rng(seed)
    sim_overrides = dict(simulation_overrides or {})

    CRIT_SAG1, CRIT_SAG2 = 15.0, 18.2   # % pila critico (mismo umbral que el resto del sistema)
    OVERFLOW_PCT = 95.0

    safe_count = 0
    tph_samples: list[float] = []
    tph1_samples: list[float] = []
    tph2_samples: list[float] = []
    inv1_samples: list[float] = []
    inv2_samples: list[float] = []
    a1_samples: list[float] = []
    a2_samples: list[float] = []
    vacia1_count = 0
    vacia2_count = 0
    overflow1_count = 0
    overflow2_count = 0
    cumple_prod_count = 0
    # Fase 3 del roadmap de cierre (2026-07-15, completa dual score a
    # Monte Carlo, ver 04_Reports/Technical/
    # 20260715_Roadmap_Cierre_Simulador_Operacional.md): cuenta cuantas
    # muestras terminan DRAINING/AT_CRITICAL_LEVEL segun los campos que
    # simulate_ode ya calcula por muestra (Etapa 1) -- cero simulaciones
    # extra, mismo patron que run_deterministic_grid.
    draining_count1 = 0
    draining_count2 = 0
    at_critical_count1 = 0
    at_critical_count2 = 0

    hours = list(range(0, int(np.ceil(horizonte)) + 1))
    hourly_vacia1 = np.zeros(len(hours))
    hourly_vacia2 = np.zeros(len(hours))
    hourly_overflow1 = np.zeros(len(hours))
    hourly_overflow2 = np.zeros(len(hours))

    p_safe_history: list[float] = []
    conv_streak = 0
    converged = False
    convergence_n = None
    n = 0

    tph_target = float(cand.get("tph_mean", 0.0)) or None
    timed_out = False
    _t_start = time.perf_counter()

    while n < MC_MAX_N:
        if (time.perf_counter() - _t_start) > MC_MAX_SECONDS:
            timed_out = True
            break
        # Batch de simulaciones
        for _ in range(MC_BATCH):
            p1  = float(np.clip(rng.normal(pila1,  2.5), 5, 95))
            p2  = float(np.clip(rng.normal(pila2,  2.5), 5, 95))
            ff  = float(np.clip(rng.normal(1.0, 0.12), 0.55, 1.50))
            dt8 = float(np.clip(rng.normal(duracion_t8, 1.0), 0, duracion_t8 + 3))

            c315v = cv315_nom * ff
            c316v = cv316_nom * ff

            try:
                sim = simulate_scenario(
                    pila_sag1_pct=p1, pila_sag2_pct=p2,
                    rate_sag1_pct=100.0, rate_sag2_pct=100.0,
                    bolas_sag1=cand["b1"], bolas_sag2=cand["b2"],
                    sag1_activo=sag1_on, sag2_activo=sag2_on,
                    duracion_t8_h=dt8,
                    correa315_estado=c315, correa316_estado=c316,
                    horizonte_horas=horizonte,
                    ch1_on=ch1_on, ch2_on=ch2_on,
                    cv_mode="manual",
                    cv315_manual_tph=c315v, cv316_manual_tph=c316v,
                    rate_sag1_tph=cand["r1"], rate_sag2_tph=cand["r2"],
                    t1_mode=t1_mode, t1_manual_tph=t1_manual,
                    t3_frac=t3_frac, distribucion_t1=distribucion_t1,
                    **sim_overrides,
                )
            except Exception:
                continue

            a1 = float(sim.get("min_autonomia_sag1", 0))
            a2 = float(sim.get("min_autonomia_sag2", 0))
            tph = float(np.array(sim.get("tph_total", [0])).mean())
            tph1 = float(np.array(sim.get("tph_sag1", [0])).mean())
            tph2 = float(np.array(sim.get("tph_sag2", [0])).mean())

            time_arr = np.array(sim.get("time", [0.0]))
            pile1_arr = np.array(sim.get("pile_sag1", [p1]))
            pile2_arr = np.array(sim.get("pile_sag2", [p2]))

            p1f = float(pile1_arr[-1]) if len(pile1_arr) else p1
            p2f = float(pile2_arr[-1]) if len(pile2_arr) else p2

            ok1 = (a1 >= min_auton_sag1) or not sag1_on
            ok2 = (a2 >= min_auton_sag2) or not sag2_on
            if ok1 and ok2:
                safe_count += 1

            if sag1_on and float(pile1_arr.min()) < CRIT_SAG1:
                vacia1_count += 1
            if sag2_on and float(pile2_arr.min()) < CRIT_SAG2:
                vacia2_count += 1
            if float(pile1_arr.max()) > OVERFLOW_PCT:
                overflow1_count += 1
            if float(pile2_arr.max()) > OVERFLOW_PCT:
                overflow2_count += 1
            if tph_target is None or tph >= 0.9 * tph_target:
                cumple_prod_count += 1

            status1 = sim.get("dynamic_net_autonomy_sag1_status")
            status2 = sim.get("dynamic_net_autonomy_sag2_status")
            if status1 == "DRAINING":
                draining_count1 += 1
            elif status1 == "AT_CRITICAL_LEVEL":
                at_critical_count1 += 1
            if status2 == "DRAINING":
                draining_count2 += 1
            elif status2 == "AT_CRITICAL_LEVEL":
                at_critical_count2 += 1

            # Probabilidad por hora (interpola la trayectoria de esta muestra
            # en cada checkpoint horario; no cuesta simulaciones extra).
            if len(time_arr) > 1:
                for hi, h in enumerate(hours):
                    if h > time_arr[-1]:
                        continue
                    pv1 = float(np.interp(h, time_arr, pile1_arr))
                    pv2 = float(np.interp(h, time_arr, pile2_arr))
                    if sag1_on and pv1 < CRIT_SAG1:
                        hourly_vacia1[hi] += 1
                    if sag2_on and pv2 < CRIT_SAG2:
                        hourly_vacia2[hi] += 1
                    if pv1 > OVERFLOW_PCT:
                        hourly_overflow1[hi] += 1
                    if pv2 > OVERFLOW_PCT:
                        hourly_overflow2[hi] += 1

            tph_samples.append(tph)
            tph1_samples.append(tph1)
            tph2_samples.append(tph2)
            inv1_samples.append(p1f)
            inv2_samples.append(p2f)
            a1_samples.append(a1)
            a2_samples.append(a2)
            n += 1

        if n == 0:
            break

        # Check de convergencia cada batch
        p_safe_now = safe_count / n
        p_safe_history.append(p_safe_now)

        if n >= MC_MIN_N and len(p_safe_history) >= 2:
            delta = abs(p_safe_history[-1] - p_safe_history[-2])
            if delta < MC_CONV_TOL:
                conv_streak += 1
                if conv_streak >= MC_CONV_CONSEC:
                    converged = True
                    convergence_n = n
                    break
            else:
                conv_streak = 0

    # Estadísticas finales
    p_safe = safe_count / n if n > 0 else 0.0
    tph_arr = np.array(tph_samples) if tph_samples else np.array([cand["tph_mean"]])
    tph1_arr = np.array(tph1_samples) if tph1_samples else np.array([cand["r1"]])
    tph2_arr = np.array(tph2_samples) if tph2_samples else np.array([cand["r2"]])
    inv1_arr = np.array(inv1_samples) if inv1_samples else np.array([cand["inv_sag1_final"]])
    inv2_arr = np.array(inv2_samples) if inv2_samples else np.array([cand["inv_sag2_final"]])

    tph_mean = float(tph_arr.mean())
    a1_med   = float(np.median(a1_samples)) if a1_samples else cand["a1_min"]
    a2_med   = float(np.median(a2_samples)) if a2_samples else cand["a2_min"]
    # Autonomia probabilistica (2026-07-06): P10/P90 sobre las MISMAS
    # muestras ya recolectadas para a1_med/a2_med — cero simulaciones
    # adicionales (Regla 1 de skill_token_optimization_loop.md).
    a1_arr = np.array(a1_samples) if a1_samples else np.array([cand["a1_min"]])
    a2_arr = np.array(a2_samples) if a2_samples else np.array([cand["a2_min"]])
    a1_p10 = float(np.percentile(a1_arr, 10))
    a1_p90 = float(np.percentile(a1_arr, 90))
    a2_p10 = float(np.percentile(a2_arr, 10))
    a2_p90 = float(np.percentile(a2_arr, 90))
    inv_f1   = float(inv1_arr.mean())
    inv_f2   = float(inv2_arr.mean())

    score = compute_multi_criteria_score(tph_mean, p_safe, inv_f1, inv_f2, a1_med, a2_med, weights=weights)

    result = dict(cand)  # hereda r1,b1,r2,b2,label_short etc.
    result.update({
        "p_safe":           round(p_safe, 4),
        "p_crisis":         round(1.0 - p_safe, 4),
        "tph_mean":         round(tph_mean, 1),
        "tph_p10":          round(float(np.percentile(tph_arr, 10)), 1),
        "tph_p90":          round(float(np.percentile(tph_arr, 90)), 1),
        "tph1_p10":         round(float(np.percentile(tph1_arr, 10)), 1),
        "tph1_p50":         round(float(np.percentile(tph1_arr, 50)), 1),
        "tph1_p90":         round(float(np.percentile(tph1_arr, 90)), 1),
        "tph2_p10":         round(float(np.percentile(tph2_arr, 10)), 1),
        "tph2_p50":         round(float(np.percentile(tph2_arr, 50)), 1),
        "tph2_p90":         round(float(np.percentile(tph2_arr, 90)), 1),
        "a1_med":           round(a1_med, 2),
        "a2_med":           round(a2_med, 2),
        "a1_p10":           round(a1_p10, 2),
        "a1_p90":           round(a1_p90, 2),
        "a2_p10":           round(a2_p10, 2),
        "a2_p90":           round(a2_p90, 2),
        "inv_sag1_final":   round(inv_f1, 1),
        "inv_sag2_final":   round(inv_f2, 1),
        "n_samples_used":   n,
        "converged":        converged,
        "convergence_n":    convergence_n,
        "mc_timed_out":     timed_out,
        "mc_warning":       ("No convergente, usar con cautela" if (timed_out or not converged) else None),
        "multi_criteria_score": round(score, 4),
        "robust_score":         round(p_safe * tph_mean, 1),
        # "¿Por que confiar?" — Cambio 4
        "pct_cumple_produccion": round(100.0 * cumple_prod_count / n, 1) if n else 0.0,
        "pct_vacia_sag1":        round(100.0 * vacia1_count / n, 1) if n else 0.0,
        "pct_vacia_sag2":        round(100.0 * vacia2_count / n, 1) if n else 0.0,
        "pct_overflow_sag1":     round(100.0 * overflow1_count / n, 1) if n else 0.0,
        "pct_overflow_sag2":     round(100.0 * overflow2_count / n, 1) if n else 0.0,
        "pct_cumple_autonomia":  round(p_safe * 100.0, 1),
        # Fase 3 del roadmap de cierre (2026-07-15): dual score aditivo
        # para Monte Carlo -- p_dynamic_safe es la fraccion de muestras
        # donde NINGUN circuito esta DRAINING/AT_CRITICAL_LEVEL, analogo
        # en interpretacion a p_safe pero basado en balance neto real por
        # muestra en vez de la autonomia historica minima. No reemplaza
        # p_safe ni el score/orden de seleccion.
        "pct_draining_sag1":     round(100.0 * draining_count1 / n, 1) if n else 0.0,
        "pct_draining_sag2":     round(100.0 * draining_count2 / n, 1) if n else 0.0,
        "pct_at_critical_sag1":  round(100.0 * at_critical_count1 / n, 1) if n else 0.0,
        "pct_at_critical_sag2":  round(100.0 * at_critical_count2 / n, 1) if n else 0.0,
        "p_dynamic_safe":        round(1.0 - (draining_count1 + at_critical_count1
                                               + draining_count2 + at_critical_count2) / (2.0 * n), 4) if n else None,
        # Riesgo por hora — Cambio 7
        "hourly_risk": {
            "hours": hours,
            "p_vacia_sag1":    (hourly_vacia1 / n * 100.0).round(1).tolist() if n else [],
            "p_vacia_sag2":    (hourly_vacia2 / n * 100.0).round(1).tolist() if n else [],
            "p_overflow_sag1": (hourly_overflow1 / n * 100.0).round(1).tolist() if n else [],
            "p_overflow_sag2": (hourly_overflow2 / n * 100.0).round(1).tolist() if n else [],
        },
    })
    return result


# ---- Pareto front ------------------------------------------------------------

def build_pareto_front(results: list[dict]) -> list[dict]:
    """
    Marca configuraciones Pareto-optimas en 3 objetivos:
      maximize tph_mean, maximize p_safe, maximize inv_mean.
    O(N^2) — N <= 100 configs, trivial.
    """
    n = len(results)
    for i, r in enumerate(results):
        r["inv_mean"] = (r.get("inv_sag1_final", 0) + r.get("inv_sag2_final", 0)) / 2.0

    dominated = [False] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            ri, rj = results[i], results[j]
            # rj domina ri si es >= en todo y > en al menos uno
            if (rj["tph_mean"] >= ri["tph_mean"]
                    and rj["p_safe"] >= ri["p_safe"]
                    and rj["inv_mean"] >= ri["inv_mean"]
                    and (rj["tph_mean"] > ri["tph_mean"]
                         or rj["p_safe"] > ri["p_safe"]
                         or rj["inv_mean"] > ri["inv_mean"])):
                dominated[i] = True
                break

    for i, r in enumerate(results):
        r["pareto"] = not dominated[i]

    return results


# ---- Formateo Top-5 ----------------------------------------------------------

def format_top5_records(mc_results: list[dict]) -> list[dict]:
    """Formatea los 5 mejores por multi_criteria_score para la tabla del dashboard."""
    top5 = mc_results[:5]
    out = []
    for i, r in enumerate(top5):
        b1_label = ("B411+412" if "ambas" in r["b1"]
                    else ("B411" if "411" in r["b1"]
                          else ("B412" if "412" in r["b1"] else "Sin bola")))
        b2_label = ("B511+512" if "ambas" in r["b2"]
                    else ("B511" if "511" in r["b2"]
                          else ("B512" if "512" in r["b2"] else "Sin bola")))
        out.append({
            "rank":         i + 1,
            "config_label": f"SAG1: {r['r1']} TPH / {b1_label}  |  SAG2: {r['r2']} TPH / {b2_label}",
            # CAMBIO 8 (UX/UI v2 JdS, 2026-07-07): columnas SAG1/SAG2
            # separadas para la tabla horizontal Rank|SAG1|SAG2|Riesgo|
            # Cumplimiento|Score — reusan los mismos labels que config_label.
            "sag1_label":   f"{r['r1']} TPH / {b1_label}",
            "sag2_label":   f"{r['r2']} TPH / {b2_label}",
            "tph":          f"{r['tph_mean']:.0f} TPH",
            "riesgo":       f"P(crisis)={r.get('p_crisis', 1-r['p_safe'])*100:.0f}%",
            "cumplimiento": f"{r.get('p_safe', 0.0)*100:.0f}%",
            "inventario":   f"S1:{r['inv_sag1_final']:.0f}%  S2:{r['inv_sag2_final']:.0f}%",
            "autonomia":    f"S1:{r['a1_med']:.1f}h  S2:{r['a2_med']:.1f}h",
            "multi_score":  f"{r['multi_criteria_score']:.3f}",
            "pareto":       r.get("pareto", False),
            "converged":    r.get("converged", False),
            "n_sim":        r.get("n_samples_used", 0),
            # Valores raw para callback de actualizacion de sliders
            "r1": r["r1"], "b1": r["b1"],
            "r2": r["r2"], "b2": r["b2"],
        })
    return out


# ---- Funcion principal -------------------------------------------------------

def find_optimal_v2(
    pila1: float,
    pila2: float,
    duracion_t8: float,
    sag1_on: bool,
    sag2_on: bool,
    ch1_on: bool,
    ch2_on: bool,
    c315: str,
    c316: str,
    t1_mode: str,
    t1_manual: float,
    t3_frac: float,
    distribucion_t1: str,
    horizonte: float = 24.0,
    cv315_nom: float = 2000.0,
    cv316_nom: float = 2000.0,
    mode: str = "balanced",
    seed: int = 42,
    bola1_opts: list | None = None,
    bola2_opts: list | None = None,
) -> tuple[dict, list[dict]]:
    """
    Optimizador operacional v2.

    Flujo:
      1. Grid determinístico 100 configs -> det_score
      2. Top TOP_CANDS_FOR_MC candidatos -> MC adaptativo
      3. Pareto front
      4. Seleccion segun modo

    Modos:
      "balanced"  — max score multicriterio (Mejor Configuracion)
      "max_prod"  — max tph_mean (Maxima Produccion)
      "safe"      — P(safe)>=0.95 y max tph (Operacion Segura)
      "pareto"    — top del frente Pareto (Balance Optimo)

    Retorna (best_config_dict, all_mc_results_sorted_by_score).
    """
    # ---- Regimen operacional --------------------------------------------------
    regime_key, regime = get_regime(duracion_t8)
    w  = regime["weights"]
    ma = regime["min_auton"]
    min_a1 = ma["SAG1"]
    min_a2 = ma["SAG2"]

    # ---- Paso 1: Grid determinístico -----------------------------------------
    det_results = run_deterministic_grid(
        pila1, pila2, duracion_t8,
        sag1_on, sag2_on, ch1_on, ch2_on,
        c315, c316, t1_mode, t1_manual, t3_frac, distribucion_t1, horizonte,
        min_auton_sag1=min_a1, min_auton_sag2=min_a2, weights=w,
        bola1_opts=bola1_opts, bola2_opts=bola2_opts,
    )
    if not det_results:
        # Fallback: retorna config por defecto si no hay resultados
        dummy = {"r1": 1236, "b1": "sin_bola", "r2": 2214, "b2": "sin_bola",
                 "tph_mean": 0, "p_safe": 0, "p_crisis": 1,
                 "inv_sag1_final": pila1, "inv_sag2_final": pila2,
                 "a1_min": 0, "a2_min": 0, "a1_med": 0, "a2_med": 0,
                 "n_samples_used": 0, "converged": False, "convergence_n": None,
                 "multi_criteria_score": 0, "pareto": True, "det_score": 0,
                 "label_short": "Sin datos", "inv_mean": 0}
        return dummy, [dummy]

    candidates = det_results[:TOP_CANDS_FOR_MC]

    # ---- Paso 2: MC adaptativo -----------------------------------------------
    # CV nominal: si no se pasan, estimar de chancado
    from engine.ode_model import compute_chancado_cap
    cap_chanc = compute_chancado_cap(ch1_on, ch2_on)
    if cv315_nom <= 0 or cv316_nom <= 0:
        cv315_nom = cap_chanc * 0.40
        cv316_nom = cap_chanc * 0.60

    mc_results = []
    for i, cand in enumerate(candidates):
        mc = adaptive_mc_eval(
            cand=cand,
            pila1=pila1, pila2=pila2,
            cv315_nom=cv315_nom, cv316_nom=cv316_nom,
            duracion_t8=duracion_t8,
            sag1_on=sag1_on, sag2_on=sag2_on,
            ch1_on=ch1_on, ch2_on=ch2_on,
            c315=c315, c316=c316,
            t1_mode=t1_mode, t1_manual=t1_manual,
            t3_frac=t3_frac, distribucion_t1=distribucion_t1,
            horizonte=horizonte,
            seed=seed + i,
            min_auton_sag1=min_a1,
            min_auton_sag2=min_a2,
            weights=w,
        )
        mc_results.append(mc)

    # ---- Paso 3: Pareto ------------------------------------------------------
    mc_results = build_pareto_front(mc_results)

    # ---- Paso 4: Ordenar y seleccionar ---------------------------------------
    mc_results.sort(key=lambda x: x["multi_criteria_score"], reverse=True)

    if mode == "max_prod":
        mc_results.sort(key=lambda x: x["tph_mean"], reverse=True)
        best = mc_results[0]

    elif mode == "safe":
        safe_cands = [r for r in mc_results if r["p_safe"] >= P_SAFE_THRESHOLD]
        if safe_cands:
            safe_cands.sort(key=lambda x: x["tph_mean"], reverse=True)
            best = safe_cands[0]
        else:
            # Fallback: mayor p_safe disponible
            best = max(mc_results, key=lambda x: x["p_safe"])
        mc_results.sort(key=lambda x: x["multi_criteria_score"], reverse=True)

    elif mode == "pareto":
        pareto_only = [r for r in mc_results if r["pareto"]]
        if not pareto_only:
            pareto_only = mc_results[:1]
        best = pareto_only[0]

    else:  # "balanced"
        best = mc_results[0]

    # Asegurar p_crisis y metadatos de regimen
    for r in mc_results:
        r.setdefault("p_crisis", round(1.0 - r["p_safe"], 4))
        r["regime"] = regime_key
        r["regime_label"] = regime["label"]

    return best, mc_results
