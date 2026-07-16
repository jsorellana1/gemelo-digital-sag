"""
explicabilidad.py — Explicabilidad operacional de la recomendacion del
optimizador (V3/V4). Traduce campos ya calculados (pila, autonomia,
duracion T8, p_safe, regimen) a un listado de razones en lenguaje simple,
sin agregar ningun calculo ni relacion causal nueva.
"""
from __future__ import annotations


def explain_recommendation(
    best: dict,
    pila1: float,
    pila2: float,
    duracion_t8: float,
    asset: str = "SAG1",
) -> list[str]:
    """Genera bullets explicando por que se recomienda el rate de `asset`
    ('SAG1' o 'SAG2'), usando solo campos ya presentes en `best` (salida
    de find_optimal_v3/v4) y los parametros de escenario del usuario."""
    is_sag1 = asset.upper() == "SAG1"
    pila = pila1 if is_sag1 else pila2
    a_med = best.get("a1_med" if is_sag1 else "a2_med", 0.0)
    rate = best.get("r1" if is_sag1 else "r2", 0)
    p_safe = float(best.get("p_safe", 0.0))
    p_crisis = round((1.0 - p_safe) * 100.0, 0)
    regime = best.get("regime", best.get("regime_label", ""))

    razones = [f"Pila {asset} = {pila:.0f}%"]
    razones.append(f"Autonomía estimada = {a_med:.1f} h")
    razones.append(f"Ventana T8 = {duracion_t8:.0f} h" if duracion_t8 > 0 else "Sin ventana T8 activa")
    if regime:
        razones.append(f"Régimen operacional: {regime}")
    razones.append(f"Riesgo de vaciado estimado = {p_crisis:.0f}%")

    brecha = best.get("brecha_p90", {})
    if brecha and brecha.get("brecha_tph_sag1", 0) not in (0, None) and is_sag1:
        razones.append(
            f"Brecha vs P90 histórico: {brecha['brecha_tph_sag1']:.0f} TPH no capturados"
        )

    return [f"{asset} recomendado = {rate:.0f} TPH"] + [f"• {r}" for r in razones]
