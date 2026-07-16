"""
optimizer_v4.py — Extension aditiva de Optimizer V3: "Maxima Produccion
Sostenible". NO reemplaza ni recalcula V3 (find_optimal_v3 sigue siendo la
fuente oficial de TPH/autonomia/riesgo) — re-rankea los candidatos que V3
ya evaluo, agregando una penalizacion de estabilidad basada en CV real
medido (engine/production_stats.py, 2.6 anos de datos diarios oficiales).

Por que no hay una "Capa 2: optimizacion metalurgica" (ley/recuperacion):
el analisis de 2026-07-06 encontro correlacion nula-a-debil entre TPH y
ley/recuperacion (r=0.02 y r=-0.15 respectivamente, tras excluir dias de
parada total) — no hay evidencia de que el rate SAG controle la
metalurgia. Ver 04_Reports/Technical/20260706_Reenfoque_Simulador_
Basado_Evidencia.md. V4 se reenfoca en lo que SI tiene evidencia:
SAG1 es estructuralmente mas variable que SAG2 (CV=0.44 vs 0.31, medido).
"""
from __future__ import annotations

from engine.production_stats import get_asset_stats

# Presets de tolerancia de riesgo -> peso de la penalizacion de estabilidad
# (0 = ignora estabilidad, como V3; mayor = prioriza mas la linea estable)
TOLERANCIA_PRESETS = {
    "conservador": 0.30,
    "balanceado": 0.15,
    "agresivo": 0.0,
}

_DEFAULT_CV1 = 0.444  # fallback si no hay cache disponible (frozen sin runtime_data)
_DEFAULT_CV2 = 0.310


def _cv_sag(asset: str, default: float) -> float:
    stats = get_asset_stats(asset)
    cv = stats.get("cv")
    return cv if cv is not None else default


def compute_stability_penalty(r1_tph: float, r2_tph: float) -> float:
    """Penalizacion [0, ~0.44] = promedio de CV real ponderado por la
    fraccion de TPH que cada candidato asigna a SAG1 vs SAG2. Un candidato
    que concentra produccion en SAG1 (linea mas variable) recibe una
    penalizacion mayor que uno que reparte hacia SAG2 (mas estable)."""
    total = r1_tph + r2_tph
    if total <= 0:
        return 0.0
    cv1 = _cv_sag("SAG1", _DEFAULT_CV1)
    cv2 = _cv_sag("SAG2", _DEFAULT_CV2)
    share1 = r1_tph / total
    share2 = r2_tph / total
    return share1 * cv1 + share2 * cv2


def score_v4(candidate: dict, peso_estabilidad: float) -> float:
    """Score V4 = score V3 (produccion+riesgo+inventario+autonomia, ya
    calculado por find_optimal_v3) - peso_estabilidad * penalizacion de
    estabilidad. peso_estabilidad=0 => identico a V3."""
    base = float(candidate.get("multi_criteria_score", 0.0))
    penal = compute_stability_penalty(candidate.get("r1", 0), candidate.get("r2", 0))
    return base - peso_estabilidad * penal


def find_optimal_v4(
    all_results: list[dict],
    tolerancia: str = "balanceado",
    peso_estabilidad: float | None = None,
) -> dict:
    """Re-rankea los candidatos ya evaluados por find_optimal_v3 (Top-20,
    con Monte Carlo ya corrido) usando el score V4. No ejecuta ninguna
    simulacion nueva — es re-ranking puro, costo despreciable.

    peso_estabilidad: si se especifica (0-1), tiene prioridad sobre
    `tolerancia`. Si no, se usa el preset de `tolerancia`.
    """
    if not all_results:
        return {}
    w = peso_estabilidad if peso_estabilidad is not None else TOLERANCIA_PRESETS.get(tolerancia, 0.15)

    scored = [(score_v4(c, w), c) for c in all_results]
    scored.sort(key=lambda x: x[0], reverse=True)
    best = dict(scored[0][1])
    best["score_v4"] = round(scored[0][0], 4)
    best["peso_estabilidad_usado"] = w
    best["penalizacion_estabilidad"] = round(
        compute_stability_penalty(best.get("r1", 0), best.get("r2", 0)), 4
    )
    return best
