"""
bottleneck.py — Detector de cuello de botella operacional.

NO introduce relaciones causales nuevas: es una capa de diagnostico basada
100% en campos que engine.simulator.simulate_scenario ya calcula
(t1_restriccion, chancado_cap_tph, alertas de bolas, autonomia minima,
estado de correas). Responde "que activo esta limitando la produccion hoy"
con la misma logica que ya usan las tarjetas/IRO, solo consolidada en un
unico diagnostico priorizado.
"""
from __future__ import annotations

MIN_AUTON_ALERTA_H = 1.5
MIN_AUTON_CRITICO_H = 1.0
AUTON_ALERTA_SAG2_H = 2.5
AUTON_CRITICO_SAG2_H = 1.0

# Factores de correa durante T8 (mismos valores que engine/ode_model.py::
# simulate_ode — no se duplica logica de calculo, solo se referencia para
# estimar el TPH perdido de forma aproximada).
_FACTOR_CORREA = {"activa": 1.0, "reducida": 0.4, "inactiva": 0.0}

# ── Categorias de cuello de botella (Fase 1.2 del roadmap de cierre,
# 2026-07-15, ver 04_Reports/Technical/
# 20260715_Roadmap_Cierre_Simulador_Operacional.md) — campo aditivo
# "categoria" en cada candidato, NO reemplaza severidad/motivo/color ya
# testeados (esos siguen basados en min_autonomia_sagX, la vulnerabilidad
# de TRAYECTORIA completa del escenario — "hubo un momento critico" es
# una senal legitima aunque la pila termine recuperandose, no un error a
# corregir). STOCKPILE_DYNAMIC_DEPLETION vs STOCKPILE_LOW_BUFFER solo
# distingue si, en el ESTADO FINAL de la simulacion, la pila sigue
# drenando activamente o ya esta recuperandose/estable.
STOCKPILE_DYNAMIC_DEPLETION = "STOCKPILE_DYNAMIC_DEPLETION"
STOCKPILE_LOW_BUFFER = "STOCKPILE_LOW_BUFFER"
BALL_MILL_CAPACITY = "BALL_MILL_CAPACITY"
FEED_RESTRICTION = "FEED_RESTRICTION"
CHANCADO_LIMIT = "CHANCADO_LIMIT"
SAG_OFF = "SAG_OFF"

_ESTADOS_DRENANDO = ("DRAINING", "AT_CRITICAL_LEVEL")


def _categoria_pila(sim: dict, asset: str) -> str:
    """STOCKPILE_DYNAMIC_DEPLETION si el estado dinamico final sigue
    drenando; STOCKPILE_LOW_BUFFER si ya se recupera/estable/SAG_OFF.
    Si el `sim` no trae las claves de la Etapa 1 (dict minimo en algun
    test/caller antiguo), cae a DYNAMIC_DEPLETION — el mismo
    comportamiento de severidad que existia antes de esta fase."""
    status = sim.get(f"dynamic_net_autonomy_{asset.lower()}_status")
    if status is None:
        return STOCKPILE_DYNAMIC_DEPLETION
    return STOCKPILE_DYNAMIC_DEPLETION if status in _ESTADOS_DRENANDO else STOCKPILE_LOW_BUFFER


def detect_bottleneck(
    sim: dict,
    ch1_on: bool,
    ch2_on: bool,
    correa315_estado: str,
    correa316_estado: str,
) -> dict:
    """Retorna {'activo': str, 'motivo': str, 'severidad': 'alta'|'media'|'baja'}
    para el factor mas limitante detectado, o activo=None si no hay
    restriccion relevante."""
    candidatos = []

    if sim.get("t1_restriccion"):
        candidatos.append({
            "activo": "T1 (transferencia post-chancado)",
            "motivo": "CV315 + CV316 solicitados superan el T1 disponible — asignacion se reescala automaticamente",
            "severidad": "alta",
            "categoria": FEED_RESTRICTION,
        })

    cap = sim.get("chancado_cap_tph", 0.0)
    if not ch1_on and not ch2_on:
        candidatos.append({
            "activo": "Chancado (CH1 + CH2)",
            "motivo": "Ambos chancadores fuera de servicio — sin alimentacion nueva al circuito",
            "severidad": "alta",
            "categoria": CHANCADO_LIMIT,
        })
    elif not ch1_on or not ch2_on:
        candidatos.append({
            "activo": f"Chancado ({'CH2' if ch1_on else 'CH1'} fuera)",
            "motivo": f"Capacidad de chancado reducida a {cap:,.0f} TPH",
            "severidad": "media",
            "categoria": CHANCADO_LIMIT,
        })

    if correa315_estado != "activa":
        candidatos.append({
            "activo": "CV315 (alimentacion SAG1)",
            "motivo": f"Correa 315 en estado '{correa315_estado}'",
            "severidad": "alta" if correa315_estado == "inactiva" else "media",
            "categoria": FEED_RESTRICTION,
        })
    if correa316_estado != "activa":
        candidatos.append({
            "activo": "CV316 (alimentacion SAG2)",
            "motivo": f"Correa 316 en estado '{correa316_estado}'",
            "severidad": "alta" if correa316_estado == "inactiva" else "media",
            "categoria": FEED_RESTRICTION,
        })

    a1 = sim.get("min_autonomia_sag1", 999)
    a2 = sim.get("min_autonomia_sag2", 999)
    if a1 < MIN_AUTON_ALERTA_H:
        cat1 = _categoria_pila(sim, "SAG1")
        _sufijo1 = "" if cat1 == STOCKPILE_DYNAMIC_DEPLETION else " (el escenario termina recuperándose/estable)"
        candidatos.append({
            "activo": "Pila SAG1 (inventario)",
            "motivo": f"Autonomia minima proyectada {a1:.1f}h — riesgo de vaciado antes que restriccion de equipos{_sufijo1}",
            "severidad": "alta" if a1 < 1.0 else "media",
            "categoria": cat1,
        })
    if a2 < MIN_AUTON_ALERTA_H:
        cat2 = _categoria_pila(sim, "SAG2")
        _sufijo2 = "" if cat2 == STOCKPILE_DYNAMIC_DEPLETION else " (el escenario termina recuperándose/estable)"
        candidatos.append({
            "activo": "Pila SAG2 (inventario)",
            "motivo": f"Autonomia minima proyectada {a2:.1f}h — riesgo de vaciado antes que restriccion de equipos{_sufijo2}",
            "severidad": "alta" if a2 < 1.0 else "media",
            "categoria": cat2,
        })

    if sim.get("alerta_bola_sag1"):
        candidatos.append({
            "activo": "Molinos de bolas SAG1 (411/412)",
            "motivo": "Rate actual excede lo permitido por la configuracion de bolas activa",
            "severidad": "media",
            "categoria": BALL_MILL_CAPACITY,
        })
    if sim.get("alerta_bola_sag2"):
        candidatos.append({
            "activo": "Molinos de bolas SAG2 (511/512)",
            "motivo": "Rate actual excede lo permitido por la configuracion de bolas activa",
            "severidad": "media",
            "categoria": BALL_MILL_CAPACITY,
        })

    if not candidatos:
        return {"activo": None, "motivo": "Sin restriccion dominante detectada", "severidad": "baja"}

    orden = {"alta": 0, "media": 1, "baja": 2}
    candidatos.sort(key=lambda c: orden[c["severidad"]])
    principal = candidatos[0]
    principal["otros"] = candidatos[1:]
    return principal


def _autonomia_color(autonomia_h: float, critico: float, alerta: float) -> str:
    if autonomia_h < critico:
        return "rojo"
    if autonomia_h < alerta:
        return "amarillo"
    return "verde"


def full_bottleneck_map(
    sim: dict,
    ch1_on: bool,
    ch2_on: bool,
    correa315_estado: str,
    correa316_estado: str,
) -> list[dict]:
    """Mapa completo de estado por componente (10 activos), cada uno con
    color verde/amarillo/rojo e impacto estimado en TPH cuando es
    cuantificable directamente (chancado/correas). Para pilas/molinos de
    bolas el impacto es de riesgo, no de capacidad instantanea, y se deja
    en None — no se fuerza un numero sin base.

    100% derivado de campos que simulate_scenario ya calcula + las
    formulas de capacidad ya existentes en engine.ode_model (no se
    duplica ni reinterpreta esa logica, solo se referencia)."""
    from engine.ode_model import compute_chancado_cap

    mapa = []

    cap_actual = sim.get("chancado_cap_tph", compute_chancado_cap(ch1_on, ch2_on))
    cap_full = compute_chancado_cap(True, True)
    mapa.append({
        "activo": "CH1", "color": "verde" if ch1_on else "rojo",
        "impacto_tph": None if ch1_on else round((cap_full - compute_chancado_cap(False, ch2_on)), 0),
        "categoria": CHANCADO_LIMIT,
    })
    mapa.append({
        "activo": "CH2", "color": "verde" if ch2_on else "rojo",
        "impacto_tph": None if ch2_on else round((cap_full - compute_chancado_cap(ch1_on, False)), 0),
        "categoria": CHANCADO_LIMIT,
    })

    t1_rest = bool(sim.get("t1_restriccion"))
    mapa.append({
        "activo": "T1", "color": "rojo" if t1_rest else "verde",
        "impacto_tph": None, "categoria": FEED_RESTRICTION,
    })

    for nombre, estado in (("CV315", correa315_estado), ("CV316", correa316_estado)):
        factor = _FACTOR_CORREA.get(estado, 1.0)
        color = "verde" if estado == "activa" else ("rojo" if estado == "inactiva" else "amarillo")
        valor_actual = float(sim.get(nombre.lower(), [0])[0]) if sim.get(nombre.lower()) else 0.0
        impacto = None
        if factor < 1.0 and factor > 0:
            impacto = round(valor_actual / factor - valor_actual, 0)
        elif factor == 0.0:
            impacto = round(valor_actual, 0) if valor_actual else None
        mapa.append({"activo": nombre, "color": color, "impacto_tph": impacto, "categoria": FEED_RESTRICTION})

    a1 = sim.get("min_autonomia_sag1", 999)
    a2 = sim.get("min_autonomia_sag2", 999)
    mapa.append({"activo": "Pila SAG1", "color": _autonomia_color(a1, MIN_AUTON_CRITICO_H, MIN_AUTON_ALERTA_H),
                 "impacto_tph": None, "categoria": _categoria_pila(sim, "SAG1")})
    mapa.append({"activo": "Pila SAG2", "color": _autonomia_color(a2, AUTON_CRITICO_SAG2_H, AUTON_ALERTA_SAG2_H),
                 "impacto_tph": None, "categoria": _categoria_pila(sim, "SAG2")})

    sag1_act = sim.get("sag1_activo", True)
    sag2_act = sim.get("sag2_activo", True)
    mapa.append({"activo": "SAG1", "color": "verde" if sag1_act else "rojo", "impacto_tph": None,
                 "categoria": None if sag1_act else SAG_OFF})
    mapa.append({"activo": "SAG2", "color": "verde" if sag2_act else "rojo", "impacto_tph": None,
                 "categoria": None if sag2_act else SAG_OFF})

    alerta_bolas = bool(sim.get("alerta_bola_sag1")) or bool(sim.get("alerta_bola_sag2"))
    mapa.append({"activo": "Molinos de bolas", "color": "amarillo" if alerta_bolas else "verde",
                 "impacto_tph": None, "categoria": BALL_MILL_CAPACITY})

    return mapa
