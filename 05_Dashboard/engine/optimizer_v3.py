"""
optimizer_v3.py — Optimizador V3 basado en evidencia operacional.

Corrige el sesgo sistemático contra SAG1 identificado en el diagnostico 2026-07-01.
Mantiene V2 como respaldo; V3 solo EXTIENDE su infraestructura.

Cambios clave vs V2
-------------------
1. Anclas historicas calibradas: P50/P75/P90/MAX para SAG1 y SAG2.
2. Grid anclado a percentiles historicos (no rangos arbitrarios).
3. Pesos por regimen mas agresivos en produccion, menos restrictivos en autonomia.
4. min_auton reducido en Normal: SAG1=0.30h (vs 0.50h en V2) — el CV315 alimenta.
5. ROI_Bolas: Δ toneladas / Δ inventario consumido (%).
6. Brecha P90: produccion potencial no capturada en cada resultado.
7. Texto de validacion operacional generado automaticamente por regimen.
8. find_optimal_v3: misma interfaz que V2 + campos enriquecidos en resultados.

Compatibilidad
--------------
  from engine.optimizer_v3 import find_optimal_v3
  best, results = find_optimal_v3(...)     # mismos kwargs que find_optimal_v2
  best["brecha_p90"]                       # nuevo campo
  best["roi_bolas_sag1"]                   # nuevo campo
  best["validation_answer"]                # nuevo campo
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from engine.scenario_cache import optimizer_cache  # noqa: E402
from engine.optimizer_v2 import (  # noqa: E402
    run_deterministic_grid,
    adaptive_mc_eval,
    compute_multi_criteria_score,
    build_pareto_front,
    format_top5_records,
    TPH_REF_MAX,
    REF_AUTON_SAG1,
    REF_AUTON_SAG2,
    INV_REF_FULL,
    P_SAFE_THRESHOLD,
    TOP_CANDS_FOR_MC,
    BOLA1_OPTS,
    BOLA2_OPTS,
)

# ---- Anclas historicas SAG1 ---------------------------------------------------
# Datos: 2025-08-01 a 2026-06-21, n=93 612 registros 5-min, solo SAG1 operando.
SAG1_P50  = 1136.0   # media real
SAG1_P75  = 1309.0   # aprox (usado en CONFIGS "balanceado")
SAG1_P90  = 1450.0   # confirmado por datos historicos
SAG1_MAX  = 1516.0   # maximo historico observado
SAG1_CRITICAL = 15.0 # nivel critico de pila (%)

# Anclas historicas SAG2 (estimadas por rango operacional documentado)
SAG2_P50  = 2214.0
SAG2_P75  = 2365.0
SAG2_P90  = 2516.0
SAG2_MAX  = 2642.0

# Numero de eventos historicos de alta produccion SAG1 (>= P75 por >= 2h)
SAG1_HIGH_EVENTS = 197

# ---- Grid V3: candidatos anclados a percentiles historicos -------------------
R1_CANDS_V3 = [int(SAG1_P50), 1200, int(SAG1_P75), 1400, int(SAG1_P90), int(SAG1_MAX)]
R2_CANDS_V3 = [1888, int(SAG2_P50), int(SAG2_P75), int(SAG2_P90), int(SAG2_MAX)]

# ---- Regimenes V3 ------------------------------------------------------------
# V3 es mas agresivo que V2 en produccion; menos restrictivo en autonomia.
# Logica: la autonomia solo importa cuando hay riesgo de T8. Sin T8 activo,
# el CV315 alimenta continuamente y no existe riesgo de crisis de inventario.
REGIMES_V3: dict[str, dict] = {
    "normal": {
        "label":     "Operacion Normal (sin T8)",
        "t8_max":    0.0,
        "weights": {
            "produccion":  0.70,   # V2: 0.65 — explotar capacidad historica
            "riesgo":      0.15,   # V2: 0.20 — menos penalizado sin T8
            "inventario":  0.10,
            "autonomia":   0.05,
        },
        "min_auton": {"SAG1": 0.30, "SAG2": 0.50},   # V2: 0.50/0.75
        "ref_tph_sag1": SAG1_P90,   # referencia: P90 historico
        "question":  "¿Por que SAG1 no opera cerca de P90 ({p90:.0f} TPH)?",
    },
    "t8_corta": {
        "label":     "Ventana T8 Corta (<=4h)",
        "t8_max":    4.0,
        "weights": {
            "produccion":  0.52,   # V2: 0.48
            "riesgo":      0.28,   # V2: 0.32
            "inventario":  0.12,
            "autonomia":   0.08,
        },
        "min_auton": {"SAG1": 0.75, "SAG2": 1.25},   # V2: 1.0/1.5
        "ref_tph_sag1": SAG1_P75,
        "question":  "¿Realmente necesito restringir SAG1 con T8 de {t8:.0f}h?",
    },
    "t8_larga": {
        "label":     "Ventana T8 Larga (>4h)",
        "t8_max":    999.0,
        "weights": {
            "produccion":  0.40,   # V2: 0.35 — mayor peso produccion
            "riesgo":      0.30,   # V2: 0.35
            "inventario":  0.20,
            "autonomia":   0.10,
        },
        "min_auton": {"SAG1": 1.25, "SAG2": 1.75},   # V2: 1.5/2.0
        "ref_tph_sag1": SAG1_P50,
        "question":  "¿Cual es el costo productivo de proteger inventario en T8 de {t8:.0f}h?",
    },
}

# Alias retrocompatibilidad
SCORE_WEIGHTS_V3  = REGIMES_V3["t8_larga"]["weights"]
MIN_AUTON_SAG1_V3 = REGIMES_V3["t8_larga"]["min_auton"]["SAG1"]
MIN_AUTON_SAG2_V3 = REGIMES_V3["t8_larga"]["min_auton"]["SAG2"]


def get_regime_v3(duracion_t8: float) -> tuple[str, dict]:
    """Retorna (nombre_regimen, dict_regimen_v3) segun duracion T8."""
    if duracion_t8 <= 0:
        return "normal", REGIMES_V3["normal"]
    elif duracion_t8 <= 4.0:
        return "t8_corta", REGIMES_V3["t8_corta"]
    else:
        return "t8_larga", REGIMES_V3["t8_larga"]


# ---- KPIs nuevos de V3 -------------------------------------------------------

def compute_brecha(tph_sag1: float, tph_sag2: float = 0.0, horizonte: float = 24.0) -> dict:
    """
    Brecha de produccion vs referencia historica P90.

    Retorna dict con:
      brecha_tph_sag1:  TPH que se dejan de procesar vs P90 SAG1
      brecha_ton_dia:   Toneladas/dia no capturadas (solo SAG1)
      pct_p50:          TPH actual / P50 * 100
      pct_p90:          TPH actual / P90 * 100
      zona:             "optima" | "buena" | "mejorable" | "restringida"
    """
    brecha = max(SAG1_P90 - tph_sag1, 0.0)
    pct_p90 = tph_sag1 / SAG1_P90 * 100
    if pct_p90 >= 97:
        zona = "optima"
    elif pct_p90 >= 90:
        zona = "buena"
    elif pct_p90 >= 80:
        zona = "mejorable"
    else:
        zona = "restringida"

    return {
        "brecha_tph_sag1":   round(brecha, 0),
        "brecha_ton_dia":    round(brecha * horizonte, 0),
        "pct_p50":           round(tph_sag1 / SAG1_P50 * 100, 1),
        "pct_p90":           round(pct_p90, 1),
        "zona":              zona,
        "sag1_p50":          SAG1_P50,
        "sag1_p75":          SAG1_P75,
        "sag1_p90":          SAG1_P90,
        "sag1_max":          SAG1_MAX,
        "tph_sag1_actual":   round(tph_sag1, 1),
    }


def compute_roi_bolas(
    tph_sin_bolas: float,
    tph_con_bolas: float,
    inv_fin_sin: float,
    inv_fin_con: float,
    inv_ini: float,
    horizonte: float = 24.0,
) -> dict:
    """
    ROI de bolas de molienda.

    ROI_Bolas = (ΔTPH * horizonte) / max(Δinv_consumido, 0.01)
    Unidad: toneladas adicionales por % adicional de pila consumida.

    Un ROI > 300 indica que el beneficio de activar bolas supera ampliamente
    el costo en inventario.
    """
    delta_tph = max(tph_con_bolas - tph_sin_bolas, 0.0)
    inv_consumida_sin = inv_ini - inv_fin_sin
    inv_consumida_con = inv_ini - inv_fin_con
    delta_inv = max(inv_consumida_con - inv_consumida_sin, 0.0)

    if delta_tph <= 0:
        roi = 0.0
        conveniente = False
    elif delta_inv < 0.01:
        roi = delta_tph * horizonte / 0.01   # limite alto: inventario no se drena mas
        conveniente = True
    else:
        roi = delta_tph * horizonte / delta_inv
        conveniente = roi > 100.0   # umbral operacional: > 100 t/% es conveniente

    return {
        "roi_bolas":          round(roi, 0),
        "delta_tph":          round(delta_tph, 1),
        "delta_inv_consumida": round(delta_inv, 2),
        "ton_adicionales_24h": round(delta_tph * horizonte, 0),
        "conveniente":        conveniente,
        "label": ("Beneficioso" if roi > 300
                  else "Moderado" if roi > 100
                  else "Marginal" if roi > 0
                  else "No beneficioso"),
    }


def get_validation_answer(
    regime_key: str,
    duracion_t8: float,
    best_r1: float,
    best_b1: str,
    tph_mean: float,
    p_safe: float,
    a1_min: float,
    brecha: dict,
    roi_bolas: dict | None = None,
) -> str:
    """
    Responde automaticamente la pregunta operacional de validacion segun regimen.
    Respuestas en lenguaje operacional, sin jerga estadistica.
    """
    r = REGIMES_V3[regime_key]
    min_a = r["min_auton"]["SAG1"]
    b1_txt = "con bolas B411+412" if "ambas" in best_b1 else "sin bolas"
    zona = brecha["zona"]
    brecha_tph = brecha["brecha_tph_sag1"]
    brecha_ton = brecha["brecha_ton_dia"]

    if regime_key == "normal":
        if zona == "optima":
            return (
                f"SAG1 operando en zona optima ({best_r1:.0f} TPH = {brecha['pct_p90']:.0f}% de P90). "
                f"Sin T8 activo, el CV315 alimenta continuamente — no existe restriccion de inventario. "
                f"Configuracion {b1_txt} es correcta."
            )
        else:
            return (
                f"SAG1 operando a {best_r1:.0f} TPH ({brecha['pct_p90']:.0f}% de P90 historico={SAG1_P90:.0f} TPH). "
                f"Brecha: {brecha_tph:.0f} TPH = {brecha_ton:.0f} t/dia no capturadas. "
                f"Sin T8 activo, el CV315 alimenta sin interrupcion: subir a P90 es viable. "
                f"Evidencia: {SAG1_HIGH_EVENTS} eventos historicos de operacion sostenida a esta tasa."
            )

    elif regime_key == "t8_corta":
        if p_safe >= 0.90:
            return (
                f"T8 {duracion_t8:.0f}h: SAG1 puede operar a {best_r1:.0f} TPH {b1_txt} "
                f"con P(safe)={p_safe*100:.0f}% y autonomia {a1_min:.1f}h > minimo {min_a:.1f}h. "
                f"Restriccion innecesaria en T8 corta. Brecha evitable: {brecha_ton:.0f} t/dia."
            )
        else:
            return (
                f"T8 {duracion_t8:.0f}h: P(safe)={p_safe*100:.0f}%. SAG1 a {best_r1:.0f} TPH "
                f"es el balance optimo produccion-riesgo. "
                f"Bajar a P50 ({SAG1_P50:.0f} TPH) solo agrega {brecha_ton:.0f} t/dia de cobertura "
                f"a costa de {brecha_tph:.0f} TPH menos."
            )

    else:  # t8_larga
        costo_txt = f"{brecha_tph:.0f} TPH = {brecha_ton:.0f} t/dia"
        risk_note = ""
        if p_safe < 0.60:
            risk_note = (
                f" ALERTA: P(safe)={p_safe*100:.0f}% — con este nivel de pila y T8={duracion_t8:.0f}h, "
                f"la restriccion dominante es la duracion del T8, no la tasa SAG1. "
                f"Para alcanzar P(safe)>95%% se recomienda pila inicial > 65%%."
            )
        return (
            f"T8 {duracion_t8:.0f}h: proteccion de inventario justificada. "
            f"SAG1 recomendado a {best_r1:.0f} TPH {b1_txt} — P(safe)={p_safe*100:.0f}%, "
            f"autonomia {a1_min:.1f}h (minimo {min_a:.1f}h). "
            f"Costo productivo de T8: {costo_txt} vs operacion sin T8.{risk_note}"
        )


# ---- Funcion principal V3 ----------------------------------------------------

@optimizer_cache.wrap("find_optimal_v3")
def find_optimal_v3(
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
    simulation_overrides: dict | None = None,
) -> tuple[dict, list[dict]]:
    """
    Optimizador operacional V3.

    Misma interfaz que find_optimal_v2; los resultados incluyen campos adicionales:
      brecha_p90          — dict con brecha vs P90 historico SAG1
      roi_bolas_sag1      — dict con ROI de activar bolas en SAG1
      validation_answer   — texto de validacion operacional por regimen

    Flujo:
      1. Regimen V3 por duracion_t8 (pesos y min_auton mas agresivos que V2)
      2. Grid determinístico con R1_CANDS_V3 (anclados a P50/P75/P90/MAX)
      3. Top-20 candidatos → MC adaptativo (heredado de V2)
      4. Pareto front
      5. Enriquecimiento de resultados con KPIs V3
      6. Seleccion por modo
    """
    # ---- Regimen V3 ----------------------------------------------------------
    regime_key, regime = get_regime_v3(duracion_t8)
    w    = regime["weights"]
    min_a1 = regime["min_auton"]["SAG1"]
    min_a2 = regime["min_auton"]["SAG2"]

    # ---- Paso 1: Grid determinístico V3 --------------------------------------
    r1_cands = R1_CANDS_V3 if sag1_on else [int(SAG1_P50)]
    r2_cands = R2_CANDS_V3 if sag2_on else [int(SAG2_P50)]

    det_results = run_deterministic_grid(
        pila1, pila2, duracion_t8,
        sag1_on, sag2_on, ch1_on, ch2_on,
        c315, c316, t1_mode, t1_manual, t3_frac, distribucion_t1, horizonte,
        min_auton_sag1=min_a1, min_auton_sag2=min_a2,
        weights=w,
        r1_cands=r1_cands,
        r2_cands=r2_cands,
        bola1_opts=bola1_opts,
        bola2_opts=bola2_opts,
        simulation_overrides=simulation_overrides,
    )

    if not det_results:
        dummy = _make_dummy(pila1, pila2, regime_key, regime)
        return dummy, [dummy]

    candidates = det_results[:TOP_CANDS_FOR_MC]

    # ---- Paso 2: CV nominal --------------------------------------------------
    from engine.ode_model import compute_chancado_cap
    cap_chanc = compute_chancado_cap(ch1_on, ch2_on)
    if cv315_nom <= 0 or cv316_nom <= 0:
        cv315_nom = cap_chanc * 0.40
        cv316_nom = cap_chanc * 0.60

    # ---- Paso 3: MC adaptativo -----------------------------------------------
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
            simulation_overrides=simulation_overrides,
        )
        mc_results.append(mc)

    # ---- Paso 4: Pareto ------------------------------------------------------
    mc_results = build_pareto_front(mc_results)

    # ---- Paso 5: KPIs V3 por resultado --------------------------------------
    # Calcular ROI_Bolas: comparar cada config con-bolas vs sin-bola del mismo r1/r2
    _sin_bola_map = _build_sin_bola_map(mc_results, pila1)
    for r in mc_results:
        _enrich_v3(r, _sin_bola_map, pila1, pila2, regime_key, duracion_t8, horizonte)
        r.setdefault("p_crisis", round(1.0 - r["p_safe"], 4))
        r["regime"]       = regime_key
        r["regime_label"] = regime["label"]
        r["version"]      = "v3"

    # ---- Paso 6: Seleccion por modo ------------------------------------------
    mc_results.sort(key=lambda x: x["multi_criteria_score"], reverse=True)

    if mode == "max_prod":
        mc_results.sort(key=lambda x: x["tph_mean"], reverse=True)
        best = mc_results[0]
        mc_results.sort(key=lambda x: x["multi_criteria_score"], reverse=True)

    elif mode == "safe":
        safe_cands = [r for r in mc_results if r["p_safe"] >= P_SAFE_THRESHOLD]
        if safe_cands:
            safe_cands.sort(key=lambda x: x["tph_mean"], reverse=True)
            best = safe_cands[0]
        else:
            best = max(mc_results, key=lambda x: x["p_safe"])

    elif mode == "pareto":
        pareto_only = [r for r in mc_results if r.get("pareto")]
        best = pareto_only[0] if pareto_only else mc_results[0]

    else:  # "balanced"
        best = mc_results[0]

    return best, mc_results


# ---- Helpers internos --------------------------------------------------------

def _make_dummy(pila1, pila2, regime_key, regime):
    brecha = compute_brecha(SAG1_P50, 0.0)
    return {
        "r1": int(SAG1_P50), "b1": "sin_bola",
        "r2": int(SAG2_P50), "b2": "sin_bola",
        "tph_mean": SAG1_P50 + SAG2_P50,
        "p_safe": 0.5, "p_crisis": 0.5,
        "inv_sag1_final": pila1, "inv_sag2_final": pila2,
        "a1_min": 0.5, "a2_min": 1.0, "a1_med": 0.5, "a2_med": 1.0,
        "n_samples_used": 0, "converged": False, "convergence_n": None,
        "multi_criteria_score": 0.0, "det_score": 0.0,
        "pareto": True, "inv_mean": (pila1 + pila2) / 2,
        "label_short": "Sin datos",
        "regime": regime_key, "regime_label": regime["label"], "version": "v3",
        "brecha_p90": brecha, "roi_bolas_sag1": None,
        "validation_answer": "Sin resultados para este escenario.",
    }


def _build_sin_bola_map(mc_results: list[dict], pila_ini: float) -> dict:
    """Mapa (r1, r2) -> result para configs sin bolas (referencia para ROI_Bolas)."""
    m = {}
    for r in mc_results:
        if r["b1"] == "sin_bola" and r["b2"] == "sin_bola":
            m[(r["r1"], r["r2"])] = r
    return m


def _enrich_v3(
    r: dict,
    sin_bola_map: dict,
    pila_ini1: float,
    pila_ini2: float,
    regime_key: str,
    duracion_t8: float,
    horizonte: float,
) -> None:
    """Agrega campos V3 al resultado in-place."""
    # Brecha P90 basada en tph estimada de SAG1
    tph_sag1_est = float(r.get("r1", SAG1_P50))
    brecha = compute_brecha(tph_sag1_est, float(r.get("r2", SAG2_P50)), horizonte)
    r["brecha_p90"] = brecha

    # ROI Bolas SAG1: comparar con config sin bola del mismo r2
    roi = None
    ref_key = (r["r1"], r["r2"])
    ref_sin_bola = sin_bola_map.get(ref_key)

    if r.get("b1") != "sin_bola" and ref_sin_bola is not None:
        roi = compute_roi_bolas(
            tph_sin_bolas=ref_sin_bola["tph_mean"],
            tph_con_bolas=r["tph_mean"],
            inv_fin_sin=ref_sin_bola["inv_sag1_final"],
            inv_fin_con=r["inv_sag1_final"],
            inv_ini=pila_ini1,
            horizonte=horizonte,
        )
    r["roi_bolas_sag1"] = roi

    # Texto de validacion
    r["validation_answer"] = get_validation_answer(
        regime_key=regime_key,
        duracion_t8=duracion_t8,
        best_r1=float(r.get("r1", SAG1_P50)),
        best_b1=r.get("b1", "sin_bola"),
        tph_mean=float(r.get("tph_mean", 0)),
        p_safe=float(r.get("p_safe", 0)),
        a1_min=float(r.get("a1_med", r.get("a1_min", 0))),
        brecha=brecha,
        roi_bolas=roi,
    )


# ---- Utilidades de reporte ---------------------------------------------------

def compare_v2_v3_weights() -> dict:
    """Retorna tabla comparativa de pesos V2 vs V3 para cada regimen."""
    from engine.optimizer_v2 import REGIMES as REGIMES_V2
    rows = []
    for rk in ["normal", "t8_corta", "t8_larga"]:
        r2 = REGIMES_V2[rk]
        r3 = REGIMES_V3[rk]
        for comp in ["produccion", "riesgo", "inventario", "autonomia"]:
            rows.append({
                "regimen": rk,
                "componente": comp,
                "v2": r2["weights"][comp],
                "v3": r3["weights"][comp],
                "delta": round(r3["weights"][comp] - r2["weights"][comp], 3),
            })
        rows.append({
            "regimen": rk,
            "componente": "min_auton_SAG1",
            "v2": r2["min_auton"]["SAG1"],
            "v3": r3["min_auton"]["SAG1"],
            "delta": round(r3["min_auton"]["SAG1"] - r2["min_auton"]["SAG1"], 2),
        })
    return rows
