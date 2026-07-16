"""
balance_diagnostics.py — Diagnostico fisico de recuperacion post-T8
(Fase 10/11/12, cierre "Sincronizacion recomendacion/escenario",
2026-07-09).

Cuando termina una ventana T8, Qin (alimentacion) vuelve a la pila,
pero eso NO garantiza que la pila suba: solo sube si Qin > Qout en ese
momento. Si Qin ~= Qout, queda plana. Si Qin < Qout, sigue drenando.
Este modulo NO recalcula el ODE — solo audita los Qin/Qout que
`simulate_scenario_cached` ya devolvio (sim["cv315"]/["cv316"] son las
series de Qin post-distribucion T1, sim["tph_sag1"]/["tph_sag2"] son
las series de Qout), en el instante inmediatamente posterior al fin de
T8, mismo principio de "auditar la salida, no reimplementar la fisica"
que engine/physics_validation.py.
"""
from __future__ import annotations

from dataclasses import dataclass

UMBRAL_BALANCE_TPH = 20.0  # |balance| <= esto se considera "plana" (ruido de discretizacion)


@dataclass
class BalanceAsset:
    asset: str
    qin_tph: float
    qout_tph: float
    balance_tph: float
    estado: str  # "recupera" | "plana" | "drena"


def _clasificar(balance: float, umbral: float) -> str:
    if balance > umbral:
        return "recupera"
    if balance < -umbral:
        return "drena"
    return "plana"


def _indice_post_t8(tiempos: list[float], duracion_t8_h: float) -> int | None:
    """Primer indice con tiempo >= duracion_t8_h (justo despues de que
    termina T8). None si la serie no llega tan lejos."""
    for i, t in enumerate(tiempos):
        if t >= duracion_t8_h:
            return i
    return None


def compute_post_t8_balance(sim: dict, duracion_t8_h: float, umbral_tph: float = UMBRAL_BALANCE_TPH) -> dict | None:
    """Retorna {'SAG1': BalanceAsset, 'SAG2': BalanceAsset} evaluado en
    el instante inmediatamente posterior al fin de T8, o None si
    duracion_t8_h<=0 o la serie no alcanza ese instante (horizonte
    demasiado corto)."""
    if duracion_t8_h <= 0:
        return None
    tiempos = sim.get("time") or []
    idx = _indice_post_t8(list(tiempos), duracion_t8_h)
    if idx is None:
        return None

    resultado = {}
    mapeo = (("SAG1", "cv315", "tph_sag1"), ("SAG2", "cv316", "tph_sag2"))
    for asset, qin_key, qout_key in mapeo:
        qin_serie = sim.get(qin_key) or []
        qout_serie = sim.get(qout_key) or []
        if idx >= len(qin_serie) or idx >= len(qout_serie):
            continue
        qin = float(qin_serie[idx])
        qout = float(qout_serie[idx])
        balance = qin - qout
        resultado[asset] = BalanceAsset(
            asset=asset, qin_tph=qin, qout_tph=qout, balance_tph=balance,
            estado=_clasificar(balance, umbral_tph),
        )
    return resultado or None


_ESTADO_TXT = {
    "recupera": "recupera porque la alimentación disponible supera el consumo",
    "plana": "no recupera porque alimentación y consumo están casi equilibrados",
    "drena": "sigue drenando porque el consumo todavía supera a la alimentación disponible",
}


@dataclass
class RecoveryResult:
    asset: str
    estado: str            # "recupera" | "plana" | "drena"
    target_pct: float
    hora_recuperacion_h: float | None  # horas desde el inicio del horizonte, None si no aplica/no se alcanza
    pila_min_pct: float
    hora_pila_min_h: float


def compute_recovery_time(sim: dict, duracion_t8_h: float, target_pct: dict | None = None) -> dict | None:
    """Para cada asset, encuentra la primera hora posterior al fin de
    T8/mantencion (duracion_t8_h) en que la pila cruza target_pct (default:
    WARNING_PCT del propio activo, mismo umbral ya calibrado en
    ode_model.py, no uno nuevo inventado).

    Solo se proyecta recuperacion si Qin>Qout en ese tramo (mismo criterio
    que compute_post_t8_balance); si Qin<=Qout, hora_recuperacion_h queda en
    None y el estado queda en "drena"/"plana" — la pila no llegara al
    objetivo con la configuracion actual, no se extrapola.

    Retorna {'SAG1': RecoveryResult, 'SAG2': RecoveryResult} o None si
    duracion_t8_h<=0 o la serie no alcanza ese instante.
    """
    from engine.ode_model import WARNING_PCT

    if duracion_t8_h <= 0:
        return None
    tiempos = list(sim.get("time") or [])
    idx0 = _indice_post_t8(tiempos, duracion_t8_h)
    if idx0 is None:
        return None

    target_pct = target_pct or WARNING_PCT
    balance = compute_post_t8_balance(sim, duracion_t8_h)
    if balance is None:
        return None

    resultado = {}
    mapeo = (("SAG1", "pile_sag1"), ("SAG2", "pile_sag2"))
    for asset, pile_key in mapeo:
        serie = list(sim.get(pile_key) or [])
        if idx0 >= len(serie):
            continue
        tramo = serie[idx0:]
        tramo_tiempos = tiempos[idx0:]
        pila_min = min(tramo)
        hora_min = tramo_tiempos[tramo.index(pila_min)]

        b = balance.get(asset)
        estado = b.estado if b is not None else "plana"
        objetivo = float(target_pct.get(asset, 100.0))

        hora_rec = None
        if estado == "recupera":
            for t, pct in zip(tramo_tiempos, tramo):
                if pct >= objetivo:
                    hora_rec = t
                    break

        resultado[asset] = RecoveryResult(
            asset=asset, estado=estado, target_pct=objetivo,
            hora_recuperacion_h=hora_rec, pila_min_pct=pila_min, hora_pila_min_h=hora_min,
        )
    return resultado or None


_RECOVERY_TXT = {
    "recupera": "comenzará a recuperarse",
    "plana": "quedará prácticamente estable",
    "drena": "seguirá drenando con la configuración actual",
}


def explain_recovery(recovery: dict) -> str:
    """Texto tipo 'SAG1 comenzara a recuperarse, vuelve a 30% en 3.2h.'"""
    frases = []
    for asset in ("SAG1", "SAG2"):
        r = recovery.get(asset)
        if r is None:
            continue
        frase = f"{asset} {_RECOVERY_TXT[r.estado]}"
        if r.estado == "recupera" and r.hora_recuperacion_h is not None:
            frase += f", vuelve a {r.target_pct:.0f}% en {r.hora_recuperacion_h:.1f}h"
        frases.append(frase + ".")
    return " ".join(frases)


def explain_post_t8(balance: dict) -> str:
    """Texto tipo 'Post T8: SAG1 no recupera porque... Superávit
    estimado: +49 TPH.' — una frase por activo, concatenadas."""
    frases = []
    for asset in ("SAG1", "SAG2"):
        b = balance.get(asset)
        if b is None:
            continue
        signo = "+" if b.balance_tph >= 0 else ""
        frases.append(
            f"Post T8: {asset} {_ESTADO_TXT[b.estado]}. "
            f"Balance estimado: {signo}{b.balance_tph:.0f} TPH (Qin {b.qin_tph:.0f} - Qout {b.qout_tph:.0f})."
        )
    return " ".join(frases)
