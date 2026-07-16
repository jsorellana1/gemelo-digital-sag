"""
rules_engine.py — Determinacion de regimen operacional y recomendaciones
"""

from __future__ import annotations

from engine.circuit_state import (
    AutonomyContext, DRAINING, STABLE, FILLING, AT_CRITICAL_LEVEL,
)

# Bounds (rate_min, rate_max) como fraccion de P90
REGIME_RATE_BOUNDS = {
    "SAG1": {
        "EMERGENCIA":  (0.50, 0.64),
        "CONSERVADOR": (0.58, 0.78),
        "NORMAL":      (0.72, 0.95),
        "AGRESIVO":    (0.87, 1.05),
    },
    "SAG2": {
        "EMERGENCIA":  (0.68, 0.82),
        "CONSERVADOR": (0.76, 0.94),
        "NORMAL":      (0.82, 1.00),
        "AGRESIVO":    (0.90, 1.05),
    },
}

ACTIONS = [
    "OPERACION_NORMAL",
    "MONITOREAR",
    "CONSERVADOR",
    "REDUCIR_CARGA",
    "MINIMO_TECNICO",
    "EVALUAR_DETENCION",
    "EMERGENCIA",
]

# Drain rates para referencia en mensajes (pct/h)
DRAIN_RATE = {"SAG1": 23.76, "SAG2": 6.18}

# Thresholds de autonomia asimetricos por activo
# SAG1 max=3.58h (pile=100%), SAG2 max=13.24h (pile=100%)
AUTONOMY_THRESHOLDS = {
    "SAG1": {"EMERGENCIA": 0.5, "CRITICO": 1.0, "ALERTA": 1.5, "MONITOREAR": 2.5},
    "SAG2": {"EMERGENCIA": 0.5, "CRITICO": 1.0, "ALERTA": 2.5, "MONITOREAR": 4.0},
}

# Riesgo de overflow con SAG detenido (2026-07-15, cierre del gap
# confirmado en Validacion_Motor_Recomendaciones.md / escenarios dorados
# seccion 29 caso 3): si un SAG esta apagado, nada esta drenando su pila
# -- si esta sube hacia el limite, el riesgo es real aunque la autonomia
# de drenaje (que asume consumo activo) no lo capture. Mismo umbral que
# ya usa detectar_overflow_historico (engine/diagnostics/
# regime_event_detector.py::OVERFLOW_PILA_PCT=85.0) para consistencia.
OVERFLOW_RISK_PCT = 85.0
OVERFLOW_IMMINENTE_PCT = 95.0


def _per_sag_status(autonomia_h: float, asset: str) -> str:
    """
    Estado individual del SAG usando thresholds asimetricos.
    SAG1 es estructuralmente mas sensible (max 3.58h a pile=100%).
    SAG2 tiene amplio margen (max 13.24h a pile=100%).
    """
    thr = AUTONOMY_THRESHOLDS[asset]
    if autonomia_h < thr["EMERGENCIA"]:  return "EMERGENCIA"
    if autonomia_h < thr["CRITICO"]:     return "CRITICO"
    if autonomia_h < thr["ALERTA"]:      return "ALERTA"
    if autonomia_h < thr["MONITOREAR"]:  return "MONITOREAR"
    return "NORMAL"


def _fmt_auton(autonomia_h: float, asset: str) -> str:
    """Formatea autonomia: horas para SAG2, minutos para SAG1 cuando es menor a 2h."""
    if asset == "SAG1" and autonomia_h < 2.0:
        return f"{autonomia_h * 60:.0f} min"
    return f"{autonomia_h:.1f}h"


def determine_regime(
    pile_pct: float,
    autonomia_h: float,
    t8_activo: bool,
    asset: str,
) -> tuple[str, tuple[float, float]]:
    """
    Determina regimen operacional para un activo en un instante dado.
    Retorna (regime_str, (rate_min_pct, rate_max_pct)).
    """
    if autonomia_h < 1.0:
        regime = "EMERGENCIA"
    elif autonomia_h < 2.5 or pile_pct < 20.0:
        regime = "CONSERVADOR"
    elif t8_activo and pile_pct > 40.0:
        regime = "AGRESIVO"
    else:
        regime = "NORMAL"

    bounds_frac = REGIME_RATE_BOUNDS.get(asset, {}).get(regime, (0.72, 0.95))
    bounds_pct = (bounds_frac[0] * 100.0, bounds_frac[1] * 100.0)
    return regime, bounds_pct


def _accion_por_contexto_dinamico(
    autonomy_context_sag1: AutonomyContext,
    autonomy_context_sag2: AutonomyContext,
    duracion_t8_h: float,
) -> tuple[str | None, str]:
    """Etapa 2 del reencuadre de autonomía (2026-07-15, ver
    04_Reports/Technical/20260715_Migracion_Autonomia_Etapa2.md): orden
    de prioridad pedido — nivel crítico dinámico > DRAINING (emergencia/
    evaluar detención/reducir carga según horas dinámicas) > FILLING con
    vulnerabilidad alta (nunca detención) > STABLE con vulnerabilidad
    crítica. Si ninguna regla dispara, retorna `(None, "")` y el llamador
    cae al fallback legacy (que ya usa la autonomía histórica para
    modular precaución — Regla general del pedido).

    Retorna `(accion_o_None, mensaje_cuantificado)`."""
    contextos = [("SAG1", autonomy_context_sag1), ("SAG2", autonomy_context_sag2)]

    # 2. Pila ya en nivel critico bajo el balance dinamico actual.
    for asset, ctx in contextos:
        if ctx.dynamic_status == AT_CRITICAL_LEVEL:
            return "EMERGENCIA", (
                f"{asset} en nivel crítico ahora (balance neto {ctx.dynamic_net_rate_tph:.0f} t/h). "
                f"Reducir carga al mínimo inmediatamente."
            )

    # 3. Estado dinamico DRAINING -> emergencia/evaluar detencion/reducir carga
    #    segun horas dinamicas, priorizando el activo con menos horas.
    drenando = [(asset, ctx) for asset, ctx in contextos if ctx.dynamic_status == DRAINING]
    if drenando:
        asset, ctx = min(drenando, key=lambda ac: ac[1].dynamic_hours)
        h, rate = ctx.dynamic_hours, ctx.dynamic_net_rate_tph
        diff_txt = (f" Autonomía preventiva histórica: {ctx.historical_hours:.1f}h "
                    f"(diferencia {ctx.historical_hours - h:+.1f}h).")
        if h < 0.5:
            return "EMERGENCIA", (
                f"{asset} drena a {rate:.0f} t/h netas y alcanzará el nivel crítico en "
                f"{h * 60:.0f} min. EMERGENCIA: reducir carga al mínimo inmediatamente."
            ) + diff_txt
        if h < 1.0:
            return "EVALUAR_DETENCION", (
                f"{asset} drena a {rate:.0f} t/h netas: autonomía dinámica {h:.1f}h "
                f"(bajo 1h). Evaluar detención parcial."
            ) + diff_txt
        if duracion_t8_h > 0 and h < duracion_t8_h:
            return "REDUCIR_CARGA", (
                f"{asset} drena a {rate:.0f} t/h netas y alcanzará el nivel crítico en {h:.1f}h. "
                f"La ventana termina en {duracion_t8_h:.1f}h. "
                f"Reducir {asset} en al menos {rate:.0f} t/h."
            ) + diff_txt

    # 4. FILLING con vulnerabilidad historica alta -> monitorear, nunca detencion.
    for asset, ctx in contextos:
        if ctx.dynamic_status == FILLING and ctx.historical_vulnerability in ("CRITICA", "ALTA"):
            return "MONITOREAR", (
                f"{asset} se recupera a {-ctx.dynamic_net_rate_tph:.0f} t/h. No existe riesgo "
                f"inmediato de agotamiento, pero el nivel presenta vulnerabilidad preventiva "
                f"{ctx.historical_vulnerability.lower()}."
            )

    # 5. STABLE con vulnerabilidad historica critica -> poco colchon, sin deterioro actual.
    for asset, ctx in contextos:
        if ctx.dynamic_status == STABLE and ctx.historical_vulnerability == "CRITICA":
            accion = "CONSERVADOR" if duracion_t8_h > 0 else "MONITOREAR"
            return accion, (
                f"{asset} con balance neto estable, sin deterioro actual, pero poco colchón "
                f"preventivo (vulnerabilidad {ctx.historical_vulnerability.lower()})."
            )

    return None, ""


def recommend_action(
    autonomia_sag1: float,
    autonomia_sag2: float,
    pile_sag1_pct: float,
    pile_sag2_pct: float,
    t8_activo: bool,
    # Nuevos parametros opcionales
    chancado_cap_tph: float = 4000.0,
    cv315_tph: float = None,
    cv316_tph: float = None,
    rate_sag1_tph: float = None,
    rate_sag2_tph: float = None,
    n_bolas_sag1: int = 0,
    n_bolas_sag2: int = 0,
    sag1_activo: bool = True,
    sag2_activo: bool = True,
    t1_tph: float = None,
    t3_tph: float = None,
    # Etapa 2 del reencuadre de autonomia (2026-07-15) — opcionales,
    # default None preserva EXACTAMENTE el comportamiento legacy previo.
    duracion_t8_h: float = 0.0,
    autonomy_context_sag1: AutonomyContext | None = None,
    autonomy_context_sag2: AutonomyContext | None = None,
) -> tuple[str, str]:
    """
    Recomienda accion global basada en el estado del sistema.
    Factores: autonomia, pila, T8, chancado, restriccion CV, regla de bolas.
    Retorna (accion, explicacion).

    `autonomy_context_sag1`/`autonomy_context_sag2` (Etapa 2, ver
    04_Reports/Technical/20260715_Migracion_Autonomia_Etapa2.md): si
    ambos vienen informados, la autonomía DINÁMICA actual gobierna la
    acción principal (vía `_accion_por_contexto_dinamico`) y la
    vulnerabilidad histórica pasa a modular precaución; si alguno falta,
    se preserva el comportamiento legacy completo (autonomía preventiva
    histórica gobernando, tal como antes de esta migración).
    """
    from engine.ode_model import BOLA_THRESHOLD_TPH

    min_auton = min(autonomia_sag1, autonomia_sag2)
    min_pile = min(pile_sag1_pct, pile_sag2_pct)

    # Identificar activo mas critico
    critico = "SAG1" if autonomia_sag1 <= autonomia_sag2 else "SAG2"
    critico_auton = autonomia_sag1 if critico == "SAG1" else autonomia_sag2

    # Riesgo de overflow con SAG detenido: nada esta drenando esa pila, asi
    # que autonomia_sagX (que asume consumo activo) no captura este riesgo.
    # Si hay mas de un activo en riesgo, se prioriza el de pila mas alta.
    _riesgo_overflow = sorted(
        [(a, p) for a, activo, p in
         (("SAG1", sag1_activo, pile_sag1_pct), ("SAG2", sag2_activo, pile_sag2_pct))
         if not activo and p >= OVERFLOW_RISK_PCT],
        key=lambda ap: ap[1], reverse=True,
    )

    # Verificar restricciones adicionales
    extras = []

    # Restriccion chancado
    if chancado_cap_tph == 0.0:
        extras.append("CHANCADO DETENIDO: sin alimentacion a circuito")
    elif chancado_cap_tph < 2000.0:
        extras.append(f"Chancado limitado: {chancado_cap_tph:.0f} TPH")

    # Restriccion CV
    if cv315_tph is not None and cv316_tph is not None:
        total_cv = cv315_tph + cv316_tph
        if total_cv > chancado_cap_tph + 0.1:
            extras.append(f"CV315+CV316 ({total_cv:.0f}) excede chancado ({chancado_cap_tph:.0f} TPH)")

    # Restriccion T1
    if t1_tph is not None and rate_sag1_tph is not None and rate_sag2_tph is not None:
        cv_demand = ((rate_sag1_tph if sag1_activo else 0.0)
                     + (rate_sag2_tph if sag2_activo else 0.0))
        if t1_tph > 0 and cv_demand > t1_tph + 100.0:
            extras.append(
                f"RESTRICCION T1: disponible {t1_tph:.0f} TPH < demanda SAG {cv_demand:.0f} TPH"
            )
    if t3_tph is not None and t1_tph is not None and t1_tph > 500:
        t3_pct = t3_tph / t1_tph * 100
        if t3_pct > 25:
            extras.append(f"T3 alto: {t3_pct:.0f}% de T1 desviado a T3 ({t3_tph:.0f} TPH)")

    # Regla de bolas SAG1
    if rate_sag1_tph is not None and n_bolas_sag1 > 1:
        if rate_sag1_tph < BOLA_THRESHOLD_TPH["SAG1"]:
            extras.append(f"SAG1 (Molino 401): rate {rate_sag1_tph:.0f} TPH < 1000, max 1 bola")

    # Regla de bolas SAG2
    if rate_sag2_tph is not None and n_bolas_sag2 > 1:
        if rate_sag2_tph < BOLA_THRESHOLD_TPH["SAG2"]:
            extras.append(f"SAG2 (Molino 501): rate {rate_sag2_tph:.0f} TPH < 1600, max 1 bola")

    # Evaluar estado individual de cada SAG con thresholds asimetricos
    st1 = _per_sag_status(autonomia_sag1, "SAG1")
    st2 = _per_sag_status(autonomia_sag2, "SAG2")
    STATUS_ORDER = ["NORMAL", "MONITOREAR", "ALERTA", "CRITICO", "EMERGENCIA"]
    worst = max(st1, st2, key=lambda s: STATUS_ORDER.index(s))

    # Linea de estado compacta por SAG (para usar en explicaciones)
    def _sag_line(asset, pile_pct, auton_h, st):
        mins = int(auton_h * 60)
        drain = DRAIN_RATE[asset]
        if st == "NORMAL":
            return f"{asset}({pile_pct:.0f}%): {auton_h:.1f}h OK"
        elif st in ("MONITOREAR", "ALERTA"):
            if asset == "SAG1":
                return f"SAG1({pile_pct:.0f}%): {mins} min — alta sensibilidad {drain:.0f}%/h"
            else:
                return f"SAG2({pile_pct:.0f}%): {auton_h:.1f}h — revisar cada 30 min"
        else:
            return f"{asset}({pile_pct:.0f}%): {_fmt_auton(auton_h, asset)} [{st}]"

    s1_line = _sag_line("SAG1", pile_sag1_pct, autonomia_sag1, st1)
    s2_line = _sag_line("SAG2", pile_sag2_pct, autonomia_sag2, st2)

    # SAGs inactivos: determinar situacion de capacidad
    n_sags_act = int(sag1_activo) + int(sag2_activo)
    if n_sags_act == 0:
        accion = "EMERGENCIA"
        exp = "Ambos SAGs detenidos: circuito sin molienda. Evaluar reactivacion inmediata."
        if extras:
            exp += " | " + " | ".join(extras)
        return accion, exp
    elif not sag1_activo:
        extras.insert(0, "SAG1 (Molino 401) DETENIDO: operando solo con SAG2")
    elif not sag2_activo:
        extras.insert(0, "SAG2 (Molino 501) DETENIDO: operando solo con SAG1 — alta fragilidad")

    # Etapa 2 del reencuadre de autonomia (2026-07-15): si ambos contextos
    # dinamicos vienen informados, la autonomia dinamica actual gobierna
    # la accion principal (orden de prioridad: nivel critico dinamico >
    # DRAINING > FILLING+vulnerabilidad alta > STABLE+vulnerabilidad
    # critica). Si no disparan ninguna regla, cae al fallback legacy de
    # abajo (que ya usa la autonomia historica para modular precaucion).
    if autonomy_context_sag1 is not None and autonomy_context_sag2 is not None:
        _accion_dinamica, _exp_dinamica = _accion_por_contexto_dinamico(
            autonomy_context_sag1, autonomy_context_sag2, duracion_t8_h)
        if _accion_dinamica is not None:
            if extras:
                _exp_dinamica += " | " + " | ".join(extras)
            return _accion_dinamica, _exp_dinamica

    if min_auton < 0.5:
        accion = "EMERGENCIA"
        exp = f"[!!] {critico} = {_fmt_auton(critico_auton, critico)}: EMERGENCIA. Reducir carga al minimo inmediatamente."
    elif min_auton < 1.0:
        accion = "EVALUAR_DETENCION"
        exp = f"{critico} bajo 1h ({_fmt_auton(critico_auton, critico)}). Evaluar detencion parcial."
    elif _riesgo_overflow and _riesgo_overflow[0][1] >= OVERFLOW_IMMINENTE_PCT:
        activo_riesgo, pile_riesgo = _riesgo_overflow[0]
        accion = "EMERGENCIA"
        exp = (f"[!!] {activo_riesgo} detenido con pila en {pile_riesgo:.0f}% "
               f"(>= {OVERFLOW_IMMINENTE_PCT:.0f}%): riesgo de overflow inminente, "
               f"nada esta drenando la pila. Reactivar {activo_riesgo} o cortar "
               f"alimentacion de inmediato.")
    elif _riesgo_overflow:
        activo_riesgo, pile_riesgo = _riesgo_overflow[0]
        accion = "REDUCIR_CARGA"
        exp = (f"{activo_riesgo} detenido con pila en {pile_riesgo:.0f}% "
               f"(>= {OVERFLOW_RISK_PCT:.0f}%): riesgo de overflow si continua el feed. "
               f"Reducir alimentacion o evaluar reactivar {activo_riesgo}.")
    elif chancado_cap_tph == 0.0:
        accion = "EMERGENCIA"
        exp = "Chancado detenido: sin alimentacion. Evaluar autonomia de pilas."
        extras = [e for e in extras if "CHANCADO DETENIDO" not in e]
    elif worst in ("CRITICO",) and min_auton < 1.5:
        accion = "MINIMO_TECNICO"
        exp = f"{s1_line} | {s2_line}. Operar en minimo tecnico."
    elif min_pile < 20.0:
        accion = "REDUCIR_CARGA"
        exp = f"Pila bajo 20% en {critico}. {s1_line} | {s2_line}"
    elif t8_activo and min_pile < 30.0:
        accion = "CONSERVADOR"
        exp = f"T8 activo con pila moderada ({min_pile:.0f}%). {s1_line} | {s2_line}"
    elif t8_activo and min_pile >= 30.0 and st1 not in ("EMERGENCIA","CRITICO","ALERTA"):
        accion = "MONITOREAR"
        exp = f"T8 activo. {s1_line} | {s2_line}"
    elif t8_activo:
        accion = "CONSERVADOR"
        exp = f"T8 activo. {s1_line} | {s2_line}"
    elif worst == "NORMAL":
        accion = "OPERACION_NORMAL"
        exp = f"Condiciones normales. {s1_line} | {s2_line}"
    elif worst == "MONITOREAR":
        # Diferencia clave SAG1 vs SAG2 en MONITOREAR
        if st1 in ("MONITOREAR", "ALERTA") and st2 == "NORMAL":
            accion = "MONITOREAR"
            exp = (f"SAG1 requiere atencion (drenaje {DRAIN_RATE['SAG1']:.0f}%/h): "
                   f"pile {pile_sag1_pct:.0f}% = {int(autonomia_sag1*60)} min. "
                   f"SAG2 estable: {autonomia_sag2:.1f}h. "
                   f"Revisar SAG1 cada 10 min.")
        elif st1 == "NORMAL" and st2 in ("MONITOREAR",):
            accion = "MONITOREAR"
            exp = f"SAG2 en vigilancia ({autonomia_sag2:.1f}h). SAG1 OK ({int(autonomia_sag1*60)} min). Revisar cada 30 min."
        else:
            accion = "MONITOREAR"
            exp = f"{s1_line} | {s2_line}"
    elif worst == "ALERTA":
        if st1 in ("ALERTA", "CRITICO"):
            accion = "CONSERVADOR"
            exp = (f"SAG1 en alerta: pile {pile_sag1_pct:.0f}% = {int(autonomia_sag1*60)} min "
                   f"(drenaje {DRAIN_RATE['SAG1']:.0f}%/h). Reducir rate SAG1 al menos 15%. {s2_line}")
        else:
            accion = "CONSERVADOR"
            exp = f"{s1_line} | {s2_line}"
    else:
        accion = "CONSERVADOR"
        exp = f"Autonomia baja. {s1_line} | {s2_line}"

    if extras:
        exp += " | " + " | ".join(extras)

    return accion, exp


ACTION_COLORS = {
    "OPERACION_NORMAL": "#27AE60",
    "MONITOREAR": "#F39C12",
    "CONSERVADOR": "#E67E22",
    "REDUCIR_CARGA": "#E67E22",
    "MINIMO_TECNICO": "#C0392B",
    "EVALUAR_DETENCION": "#C0392B",
    "EMERGENCIA": "#8B0000",
}
