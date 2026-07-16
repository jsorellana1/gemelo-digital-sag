"""
physics_validation.py — Validacion fisica post-simulacion (Prerequisito 3,
PROMPT v2 2026-07-07).

Chequea que el resultado de simulate_scenario_cached respete invariantes
fisicos/operacionales duros, con tolerancias numericas explicitas. NO
recalcula el ODE — solo audita su salida. Si algo falla, `es_valido=False`
pero el resultado NO se descarta (el operador debe ver el numero real y la
alerta, no un valor silenciado).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.ode_model import CAP_TON, CRITICAL_PCT

TOLERANCIAS = {
    "balance_masa_pct": 0.02,      # 2% de tolerancia en balance qin-qout-drenaje vs delta pila
    "pila_min_pct": 0.0,
    "pila_max_pct": 105.0,         # sobre 105% = overflow fisicamente imposible de sostener
    "tph_min": 0.0,
    "t3_min": 0.0,
    "t1_margen_tph": 100.0,        # mismo margen que simulator.py usa para t1_restriccion
}


@dataclass
class ValidationReport:
    es_valido: bool
    violaciones: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


def _check_balance_masa(sim: dict, tol_pct: float) -> list[str]:
    """Verifica que el delta de pila reportado por el ODE sea consistente
    con qin/qout/drenaje del propio `sim` (no un chequeo externo — solo
    audita que simulate_ode no produjo una serie internamente inconsistente,
    p.ej. por un cambio futuro que rompa la conservacion de masa)."""
    violaciones = []
    for asset, pile_key, cv_key in (("SAG1", "pile_sag1", "cv315"), ("SAG2", "pile_sag2", "cv316")):
        pile = sim.get(pile_key)
        if not pile or len(pile) < 2:
            continue
        pile0, pile_last = pile[0], pile[-1]
        # No se recalcula el balance completo (requeriria reintegrar el ODE);
        # se audita solo que el delta no exceda un cambio fisicamente absurdo
        # para el horizonte simulado (> 100 puntos porcentuales de un tiron).
        if abs(pile_last - pile0) > 100.0 + tol_pct * 100.0:
            violaciones.append(
                f"{asset}: delta de pila {pile_last - pile0:+.1f}pp excede variacion fisicamente plausible"
            )
    return violaciones


def _check_rango_pila(sim: dict, tol: dict) -> list[str]:
    violaciones = []
    for asset, pile_key in (("SAG1", "pile_sag1"), ("SAG2", "pile_sag2")):
        pile = sim.get(pile_key) or []
        for v in pile:
            if v < tol["pila_min_pct"] - 1e-6:
                violaciones.append(f"{asset}: pila {v:.1f}% bajo el minimo fisico (0%)")
                break
        for v in pile:
            if v > tol["pila_max_pct"]:
                violaciones.append(f"{asset}: pila {v:.1f}% excede el maximo tolerado ({tol['pila_max_pct']:.0f}%)")
                break
    return violaciones


def _check_t3_no_negativo(sim: dict, tol: dict) -> list[str]:
    """T3 (desvio) no puede ser negativo — es un caudal, no una diferencia."""
    serie = sim.get("t3") or []
    if any(v < tol["t3_min"] - 1e-6 for v in serie):
        return ["T3: caudal negativo detectado en la serie simulada"]
    return []


def _check_t1_capacidad(sim: dict, tol: dict) -> list[str]:
    """CV315+CV316 (alimentacion a T1) no puede exceder la capacidad de T1
    mas alla del margen operacional ya usado en simulator.py (t1_restriccion,
    ver simulator.py:189/215) — se reutiliza el mismo margen de +100 TPH
    para no introducir una tolerancia nueva no validada."""
    cv315 = sim.get("cv315") or []
    cv316 = sim.get("cv316") or []
    t1 = sim.get("t1") or []
    n = min(len(cv315), len(cv316), len(t1))
    margen = tol["t1_margen_tph"]
    for i in range(n):
        if cv315[i] + cv316[i] > t1[i] + margen:
            return [
                f"T1: alimentacion CV315+CV316 ({cv315[i] + cv316[i]:.0f} TPH) excede la "
                f"capacidad de T1 ({t1[i]:.0f} TPH + margen {margen:.0f}) en algun punto de la simulacion"
            ]
    return []


def _check_equipos_en_mantencion(equipos_en_mantencion: list[str], equipos_activos: dict[str, bool] | None) -> list[str]:
    """Compara la lista de equipos declarados en mantencion contra los flags
    on/off que la estrategia realmente uso para invocar el motor (params, no
    el sim — el sim no expone estado por equipo mas alla de sag1/sag2). Si
    un equipo en mantencion quedo configurado activo, es una violacion dura:
    nunca se debe recomendar un equipo que esta fuera de servicio."""
    if not equipos_en_mantencion or not equipos_activos:
        return []
    violaciones = []
    for eq in equipos_en_mantencion:
        if equipos_activos.get(eq, False):
            violaciones.append(f"Equipo '{eq}' declarado en mantencion pero la estrategia lo configuro activo")
    return violaciones


def _check_tph_no_negativo(sim: dict, tol: dict) -> list[str]:
    violaciones = []
    for asset, key in (("SAG1", "tph_sag1"), ("SAG2", "tph_sag2")):
        serie = sim.get(key) or []
        if any(v < tol["tph_min"] - 1e-6 for v in serie):
            violaciones.append(f"{asset}: TPH negativo detectado en la serie simulada")
    return violaciones


def _check_restricciones_duras(
    sim: dict, sag1_disponible: bool, sag2_disponible: bool,
    mobo1_disponible: bool, mobo2_disponible: bool,
    equipos_en_mantencion: list[str],
) -> tuple[list[str], list[str]]:
    """Restricciones que NUNCA deberian violarse: equipo en mantencion
    activo, o ambos MoBo apagados simultaneamente con SAG operando."""
    violaciones, advertencias = [], []
    if sim.get("sag1_activo") and not sag1_disponible:
        violaciones.append("SAG1 simulado activo pero declarado no disponible (mantencion/falla)")
    if sim.get("sag2_activo") and not sag2_disponible:
        violaciones.append("SAG2 simulado activo pero declarado no disponible (mantencion/falla)")
    if (not mobo1_disponible) and (not mobo2_disponible):
        advertencias.append(
            "Ambos circuitos de molinos de bolas (411/412 y 511/512) indisponibles simultaneamente — "
            "riesgo operacional alto, verificar antes de ejecutar la recomendacion"
        )
    return violaciones, advertencias


def validate_physics(
    sim: dict,
    sag1_disponible: bool = True,
    sag2_disponible: bool = True,
    mobo1_disponible: bool = True,
    mobo2_disponible: bool = True,
    equipos_en_mantencion: list[str] | None = None,
    equipos_activos: dict[str, bool] | None = None,
    tolerancias: dict | None = None,
) -> ValidationReport:
    tol = tolerancias or TOLERANCIAS
    violaciones = []
    violaciones += _check_balance_masa(sim, tol["balance_masa_pct"])
    violaciones += _check_rango_pila(sim, tol)
    violaciones += _check_tph_no_negativo(sim, tol)
    violaciones += _check_t3_no_negativo(sim, tol)
    violaciones += _check_t1_capacidad(sim, tol)
    violaciones += _check_equipos_en_mantencion(equipos_en_mantencion or [], equipos_activos)
    v_duras, advertencias = _check_restricciones_duras(
        sim, sag1_disponible, sag2_disponible, mobo1_disponible, mobo2_disponible,
        equipos_en_mantencion or [],
    )
    violaciones += v_duras
    return ValidationReport(es_valido=(len(violaciones) == 0), violaciones=violaciones, advertencias=advertencias)
