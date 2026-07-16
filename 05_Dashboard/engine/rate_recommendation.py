"""
rate_recommendation.py — Ranking de candidatos por prioridad estricta
(lexicografica), no por score ponderado.

Re-rankea los candidatos ya evaluados por optimizer_v3.find_optimal_v3
(mismo patron de "solo re-rankear, no recalcular" que optimizer_v4.py y
optimizer_v5.py) aplicando el orden de prioridad pedido por el Jefe de Sala
para la vista principal simplificada:

  1. Evitar vaciado.
  2. Evitar overflow.
  3. Proteger autonomia minima.
  4. Mantener operacion continua (regla de bolas ya validada por V3/R16).
  5. Favorecer recuperacion post-evento.
  6. Minimizar cambios bruscos de rate.
  7. Maximizar produccion sostenible.

Esto es deliberadamente distinto de V5 (score_v5_candidate en
optimizer_v5.py), que combina todo en una suma ponderada — aqui cada nivel
de prioridad solo desempata dentro de los candidatos que sobrevivieron el
nivel anterior, nunca se compensan entre si (un candidato con mejor
produccion NUNCA le gana a uno con autonomia insegura). V3/V4/V5 siguen
intactos para quien los use desde el panel de detalle tecnico.
"""
from __future__ import annotations

OVERFLOW_PCT_THRESHOLD = 20.0  # pct_overflow_sagX por encima de esto se descarta
AUTONOMIA_SEGURA_H = {"SAG1": 1.0, "SAG2": 1.5}  # umbral "autonomia minima protegida"


def _vacio(cand: dict) -> bool:
    return float(cand.get("a1_min", 0.0)) <= 0.0 or float(cand.get("a2_min", 0.0)) <= 0.0


def _tiempo_a_vaciado(cand: dict) -> float:
    """Menor a1_min/a2_min como proxy de que tan rapido vacia (para
    desempatar cuando TODOS los candidatos vacian, ver nivel 1)."""
    return min(float(cand.get("a1_min", 0.0)), float(cand.get("a2_min", 0.0)))


def _overflow(cand: dict) -> bool:
    return (float(cand.get("pct_overflow_sag1", 0.0)) > OVERFLOW_PCT_THRESHOLD
            or float(cand.get("pct_overflow_sag2", 0.0)) > OVERFLOW_PCT_THRESHOLD)


def _autonomia_segura(cand: dict) -> bool:
    return (float(cand.get("a1_min", 0.0)) >= AUTONOMIA_SEGURA_H["SAG1"]
            and float(cand.get("a2_min", 0.0)) >= AUTONOMIA_SEGURA_H["SAG2"])


def _cambio_rate(cand: dict, rate_actual_sag1_tph: float, rate_actual_sag2_tph: float) -> float:
    return abs(float(cand.get("r1", 0.0)) - rate_actual_sag1_tph) + \
           abs(float(cand.get("r2", 0.0)) - rate_actual_sag2_tph)


def _balance_post_evento(cand: dict, balance_por_candidato: dict | None, idx: int) -> float:
    """Suma del balance Qin-Qout (TPH) post-T8/mantencion, si se entrego
    (ver engine/balance_diagnostics.py::compute_post_t8_balance corrido
    sobre la simulacion de este candidato). Mayor es mejor (mas
    superavit = mejor recuperacion). Neutro (0.0) si no se calculo."""
    if not balance_por_candidato:
        return 0.0
    balance = balance_por_candidato.get(idx)
    if not balance:
        return 0.0
    total = 0.0
    for asset in ("SAG1", "SAG2"):
        b = balance.get(asset)
        if b is not None:
            total += b.balance_tph
    return total


def rank_candidates(
    all_results: list[dict],
    rate_actual_sag1_tph: float,
    rate_actual_sag2_tph: float,
    balance_por_candidato: dict[int, dict] | None = None,
) -> list[dict]:
    """Ordena all_results (candidatos de find_optimal_v3) de mejor a peor
    segun el orden de prioridad lexicografico de la seccion 10 del brief.

    Retorna una lista nueva (no muta all_results); cada elemento conserva
    todos los campos originales del candidato V3.
    """
    if not all_results:
        return []

    indexed = list(enumerate(all_results))
    todos_vacian = all(_vacio(c) for _, c in indexed)

    if todos_vacian:
        # Nivel 1 (caso degenerado): minimizar que tan rapido vacia, nada
        # mas importa si absolutamente todos los candidatos vacian la pila.
        indexed.sort(key=lambda ic: -_tiempo_a_vaciado(ic[1]))
        return [c for _, c in indexed]

    # Nivel 1: descartar los que vacian.
    sobrevive_1 = [(i, c) for i, c in indexed if not _vacio(c)]

    # Nivel 2: descartar los que hacen overflow (si eso deja la lista vacia,
    # se ignora el filtro — mejor recomendar algo con riesgo de overflow
    # que no recomendar nada).
    sobrevive_2 = [(i, c) for i, c in sobrevive_1 if not _overflow(c)]
    if not sobrevive_2:
        sobrevive_2 = sobrevive_1

    # Nivel 3: separar los que protegen autonomia minima segura de los que no.
    seguros = [(i, c) for i, c in sobrevive_2 if _autonomia_segura(c)]
    resto = [(i, c) for i, c in sobrevive_2 if not _autonomia_segura(c)]

    def _orden_final(grupo: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
        # Nivel 4 (continuidad) ya esta garantizada: V3 solo genera
        # candidatos que pasan check_bola_rule/R16 (ver optimizer_v2.py
        # run_deterministic_grid) — no hay nada que filtrar aqui.
        # Nivel 5: mayor balance post-evento (recuperacion) primero.
        # Nivel 6: menor cambio de rate respecto al actual.
        # Nivel 7: mayor produccion sostenible (tph_mean), ultimo criterio.
        return sorted(
            grupo,
            key=lambda ic: (
                -_balance_post_evento(ic[1], balance_por_candidato, ic[0]),
                _cambio_rate(ic[1], rate_actual_sag1_tph, rate_actual_sag2_tph),
                -float(ic[1].get("tph_mean", 0.0)),
            ),
        )

    ordenado = _orden_final(seguros) + _orden_final(resto)
    return [c for _, c in ordenado]
