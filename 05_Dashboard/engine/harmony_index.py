"""
harmony_index.py — Indice de Armonia Operacional SAG1/SAG2 (0-100).

Formula nueva (sin precedente previo en el codigo), documentada
explicitamente aqui y en el reporte tecnico para que sea auditable/
ajustable, siguiendo el mismo patron de indice compuesto ya usado en el
proyecto para IGI_T8 (08_Skills/skill_machine_learning_operacional.md
seccion 8): penalizaciones ponderadas 0-100, cada una capada, restadas
de 100.

Componentes (peso):
  - diferencia de carga relativa a capacidad propia (P90) SAG1 vs SAG2 (25%)
  - diferencia de autonomia proyectada (20%)
  - diferencia de riesgo de vaciado (20%)
  - variabilidad temporal combinada (CV_TPH promedio) (15%)
  - uso desequilibrado de MoBos relativo a su maximo (10%)
  - desvio de la alimentacion CV315/CV316 respecto al split proporcional
    a demanda (10%) — la "proporcional" existente en ode_model.py se usa
    como referencia neutra, no como unico optimo.

Armonia alta (>=80): ambos SAG sostenibles, autonomias compatibles, rates
estables, sin sobreconsumo de una pila. Armonia baja (<40): un SAG
maximizado mientras el otro esta en crisis, cambios bruscos, uso
desequilibrado de activos.
"""
from __future__ import annotations

PESOS = {
    "carga_relativa": 0.25,
    "autonomia": 0.20,
    "riesgo": 0.20,
    "variabilidad": 0.15,
    "mobos": 0.10,
    "alimentacion": 0.10,
}


def _pct_carga(rate_tph: float, p90: float) -> float:
    if p90 <= 0:
        return 0.0
    return max(0.0, min(rate_tph / p90 * 100.0, 150.0))


def compute_harmony_index(
    rate1_tph: float,
    rate2_tph: float,
    p90_sag1: float,
    p90_sag2: float,
    autonomia1_h: float,
    autonomia2_h: float,
    riesgo1: float,
    riesgo2: float,
    cv_tph1: float | None,
    cv_tph2: float | None,
    n_bolas1: int,
    n_bolas2: int,
    max_bolas: int = 2,
    frac315_actual: float = 0.29,
    frac315_proporcional: float | None = None,
) -> dict:
    """
    Retorna dict con 'harmony_index' (0-100) y 'sub_scores' (penalizacion
    0-100 de cada componente, antes de ponderar) para trazabilidad.

    riesgo1/riesgo2: probabilidad de vaciado/crisis en [0, 1].
    cv_tph1/cv_tph2: coeficiente de variacion (std/mean) de cada linea en
    la ventana relevante; None si no hay suficientes muestras (se trata
    como 0 penalizacion, no se puede penalizar lo que no se pudo medir).
    frac315_proporcional: fraccion "sana" de referencia (demanda SAG1 /
    demanda total); si no se entrega, se usa frac315_actual (sin desvio).
    """
    pct1 = _pct_carga(rate1_tph, p90_sag1)
    pct2 = _pct_carga(rate2_tph, p90_sag2)
    pen_carga = min(abs(pct1 - pct2), 100.0)

    max_auton = max(autonomia1_h, autonomia2_h, 1.0)
    pen_autonomia = min(abs(autonomia1_h - autonomia2_h) / max_auton * 100.0, 100.0)

    pen_riesgo = min(abs(riesgo1 - riesgo2) * 100.0, 100.0)

    cv1 = cv_tph1 if cv_tph1 is not None else 0.0
    cv2 = cv_tph2 if cv_tph2 is not None else 0.0
    pen_variabilidad = min((cv1 + cv2) / 2.0 * 100.0, 100.0)

    frac_b1 = n_bolas1 / max_bolas if max_bolas > 0 else 0.0
    frac_b2 = n_bolas2 / max_bolas if max_bolas > 0 else 0.0
    pen_mobos = min(abs(frac_b1 - frac_b2) * 100.0, 100.0)

    ref = frac315_proporcional if frac315_proporcional is not None else frac315_actual
    pen_alimentacion = min(abs(frac315_actual - ref) * 100.0, 100.0)

    sub_scores = {
        "carga_relativa": round(pen_carga, 2),
        "autonomia": round(pen_autonomia, 2),
        "riesgo": round(pen_riesgo, 2),
        "variabilidad": round(pen_variabilidad, 2),
        "mobos": round(pen_mobos, 2),
        "alimentacion": round(pen_alimentacion, 2),
    }

    penalizacion_total = sum(PESOS[k] * sub_scores[k] for k in PESOS)
    harmony = max(0.0, min(100.0, 100.0 - penalizacion_total))

    return {
        "harmony_index": round(harmony, 1),
        "sub_scores": sub_scores,
        "pesos": PESOS,
    }


def harmony_label(harmony_index: float) -> str:
    """Semaforo cualitativo: alta (>=80) / media (50-79) / baja (<50)."""
    if harmony_index >= 80.0:
        return "alta"
    elif harmony_index >= 50.0:
        return "media"
    return "baja"
