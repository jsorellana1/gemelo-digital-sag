"""
optimizer_v5.py — Extension aditiva V5: "Supervivencia y Armonia
Operacional". NO reemplaza ni recalcula V3 (find_optimal_v3 sigue siendo
la fuente oficial de TPH/autonomia/riesgo por candidato, igual que V4) —
re-rankea los candidatos ya evaluados por V3 (Top-20 con Monte Carlo ya
corrido, adaptive_mc_eval) con un score multiobjetivo nuevo que agrega
armonia (harmony_index.py) y estabilidad de TPH (variability_metrics.py +
transient_penalty.py), con 3 perfiles de peso configurables.

Cambio de filosofia respecto a V3/V4: V3 es explicitamente MAS agresivo en
produccion que V2 ("V3 es mas agresivo que V2 en produccion; menos
restrictivo en autonomia" — ver optimizer_v3.py). V5 invierte esa
prioridad por defecto (perfil "balanceado") SIN romper V3 — quien siga
llamando find_optimal_v3/v4 directamente obtiene el comportamiento de
siempre; V5 es una capa de re-ranking adicional, no un reemplazo.

Score (todos los terminos en escala 0-100 para que los pesos sean
comparables entre si):

  score_v5 = w_prod * prod_score
           + w_aut  * autonomia_score
           + w_arm  * harmony_index
           + w_est  * estabilidad_score
           - w_risk * riesgo_malo_score   (p_crisis * 100)
           - w_trans* transient_penalty_score

Nota: los pesos de un perfil suman 1.0 incluyendo w_risk/w_trans aunque
estos se restan — el score maximo teorico es por lo tanto < 100 cuando
riesgo/transitorios son > 0; es una metrica de RANKING comparativo, no un
porcentaje absoluto.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from engine.optimizer_v2 import TPH_REF_MAX, REF_AUTON_SAG1, REF_AUTON_SAG2  # noqa: E402
from engine.optimizer_v3 import SAG1_P90, SAG2_P90  # noqa: E402
from engine.harmony_index import compute_harmony_index  # noqa: E402

# ---- Perfiles de peso (suman 1.0 cada uno) ------------------------------------
PERFILES_V5: dict[str, dict[str, float]] = {
    # Prioriza autonomia, riesgo, estabilidad — proteger las pilas ante todo.
    "conservador": {
        "w_prod": 0.15, "w_aut": 0.35, "w_arm": 0.15,
        "w_est": 0.15, "w_risk": 0.15, "w_trans": 0.05,
    },
    # Prioriza produccion, autonomia, armonia — el default recomendado.
    "balanceado": {
        "w_prod": 0.30, "w_aut": 0.25, "w_arm": 0.20,
        "w_est": 0.10, "w_risk": 0.10, "w_trans": 0.05,
    },
    # Prioriza produccion y cumplimiento PAM, respetando restricciones fisicas
    # (las restricciones fisicas — R16, mantencion, T1 — nunca se relajan;
    # ver engine/optimizer_v3.py::check_bola_rule y ode_model.py::compute_t1_distribution).
    "productivo": {
        "w_prod": 0.55, "w_aut": 0.15, "w_arm": 0.05,
        "w_est": 0.05, "w_risk": 0.15, "w_trans": 0.05,
    },
}

_BOLA_COUNT = {"sin_bola": 0, "solo_411": 1, "solo_412": 1, "solo_511": 1, "solo_512": 1,
               "ambas_411_412": 2, "ambas_511_512": 2}


def _n_bolas(bola_str: str) -> int:
    return _BOLA_COUNT.get(bola_str, 0)


def score_v5_candidate(
    candidate: dict,
    perfil: str = "balanceado",
    cv_tph1: float | None = None,
    cv_tph2: float | None = None,
    transient_penalty_score: float = 0.0,
    frac315_actual: float = 0.29,
    frac315_proporcional: float | None = None,
    max_bolas: int = 2,
) -> dict:
    """
    Calcula el score V5 de un candidato ya evaluado por find_optimal_v3
    (debe traer r1, r2, b1, b2, tph_mean, a1_min, a2_min, p_safe, p_crisis).

    Retorna una copia del candidato con 'score_v5', 'harmony_index' y
    'harmony_sub_scores' agregados — no muta el candidato original.
    """
    pesos = PERFILES_V5.get(perfil, PERFILES_V5["balanceado"])

    r1 = float(candidate.get("r1", 0.0))
    r2 = float(candidate.get("r2", 0.0))
    a1_min = float(candidate.get("a1_min", 0.0))
    a2_min = float(candidate.get("a2_min", 0.0))
    p_safe = float(candidate.get("p_safe", 0.0))
    p_crisis = float(candidate.get("p_crisis", 1.0 - p_safe))

    harmony = compute_harmony_index(
        rate1_tph=r1, rate2_tph=r2,
        p90_sag1=SAG1_P90, p90_sag2=SAG2_P90,
        autonomia1_h=a1_min, autonomia2_h=a2_min,
        riesgo1=1.0 - p_safe, riesgo2=1.0 - p_safe,
        cv_tph1=cv_tph1, cv_tph2=cv_tph2,
        n_bolas1=_n_bolas(candidate.get("b1", "sin_bola")),
        n_bolas2=_n_bolas(candidate.get("b2", "sin_bola")),
        max_bolas=max_bolas,
        frac315_actual=frac315_actual,
        frac315_proporcional=frac315_proporcional,
    )

    prod_score = min(float(candidate.get("tph_mean", 0.0)) / TPH_REF_MAX, 1.0) * 100.0
    autonomia_score = min(
        (a1_min / REF_AUTON_SAG1 + a2_min / REF_AUTON_SAG2) / 2.0, 1.0
    ) * 100.0
    cv1 = cv_tph1 if cv_tph1 is not None else 0.0
    cv2 = cv_tph2 if cv_tph2 is not None else 0.0
    estabilidad_score = max(0.0, 100.0 - min((cv1 + cv2) / 2.0 * 100.0, 100.0))
    riesgo_malo_score = p_crisis * 100.0

    score = (
        pesos["w_prod"] * prod_score
        + pesos["w_aut"] * autonomia_score
        + pesos["w_arm"] * harmony["harmony_index"]
        + pesos["w_est"] * estabilidad_score
        - pesos["w_risk"] * riesgo_malo_score
        - pesos["w_trans"] * transient_penalty_score
    )

    out = dict(candidate)
    out["score_v5"] = round(score, 4)
    out["harmony_index"] = harmony["harmony_index"]
    out["harmony_sub_scores"] = harmony["sub_scores"]
    out["perfil_v5"] = perfil
    return out


def find_optimal_v5(
    all_results: list[dict],
    perfil: str = "balanceado",
    cv_tph_by_candidate: dict[int, tuple[float | None, float | None]] | None = None,
    transient_penalty_by_candidate: dict[int, float] | None = None,
    **kwargs,
) -> tuple[dict, list[dict]]:
    """
    Re-rankea los candidatos ya evaluados por find_optimal_v3 (mismo
    patron que optimizer_v4.py::find_optimal_v4) usando el score V5. No
    ejecuta ninguna simulacion nueva.

    cv_tph_by_candidate / transient_penalty_by_candidate: dict opcional
    {indice_en_all_results: valor} para inyectar variabilidad/penalizacion
    de transitorios ya calculada (Fase A/C) por candidato. Si no se
    entrega, se asume neutro (sin penalizacion) — un candidato sin
    variabilidad medida no puede ser penalizado por algo que no se pudo
    calcular.
    """
    if not all_results:
        return {}, []

    scored = []
    for i, cand in enumerate(all_results):
        cv1, cv2 = (cv_tph_by_candidate or {}).get(i, (None, None))
        trans_pen = (transient_penalty_by_candidate or {}).get(i, 0.0)
        scored.append(score_v5_candidate(
            cand, perfil=perfil, cv_tph1=cv1, cv_tph2=cv2,
            transient_penalty_score=trans_pen, **kwargs,
        ))

    scored.sort(key=lambda c: c["score_v5"], reverse=True)
    return scored[0], scored
