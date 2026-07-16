"""
circuit_state.py — Kernel de dominio centralizado para la lógica
operacional de pilas, ventanas y molinos SAG–bolas (Reglas 1-18, ver
04_Reports/Technical/20260714_Logica_Operacional_Pilas_SAG.md).

Nomenclatura obligatoria:
  SAG1 = Molino 401, bolas 411 y 412 (pila asociada: SAC1).
  SAG2 = Molino 501, bolas 511 y 512 (pila asociada: SAC2).

Principio de diseño: funciones puras, sin estado global, sin dependencia de
Dash/componentes de UI. `engine/ode_model.py::simulate_ode` es el único
integrador que llama a estas funciones dentro de su loop; este módulo no
importa nada de ode_model.py para evitar un ciclo de imports — los
factores de ventana, umbrales, etc. se pasan como argumentos numéricos ya
resueltos por el llamador (ode_model.py mapea sus conceptos propios,
como el estado de correa "activa"/"reducida"/"inactiva", a un factor
0.0-1.0 antes de invocar estas funciones).

Balance de masa — única fuente de verdad (Regla fundamental):
    dM_i/dt = F_in_i - F_out_i
    M_i[t+1] = M_i[t] + (F_in_i[t] - F_out_i[t]) * delta_t

Ninguna función de este módulo modifica el nivel de una pila de forma
"visual" o artificial — todo crecimiento/drenado emerge exclusivamente de
`update_stockpile_mass_balance`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Estados operacionales explícitos (Regla 11) ───────────────────────────────
OFF = "OFF"
STARTING = "STARTING"
RUNNING = "RUNNING"
RESTRICTED = "RESTRICTED"
STARVED = "STARVED"
STOPPING = "STOPPING"

FILLING = "FILLING"
DRAINING = "DRAINING"
AT_CRITICAL_LEVEL = "AT_CRITICAL_LEVEL"  # reencuadre autonomía 2026-07-14 (ver más abajo)

# ── Catálogo de motivos de restricción (Fase 2, Regla 7 del pedido de
# 2026-07-14 "Segunda fase") — un `operational_state=RESTRICTED` por si
# solo no explica NADA; esto le da al JdS el motivo real. ─────────────────────
SAG_OFF = "SAG_OFF"
BALL_MILLS_OFF = "BALL_MILLS_OFF"
ONE_BALL_MILL_AVAILABLE = "ONE_BALL_MILL_AVAILABLE"
LOW_STOCKPILE = "LOW_STOCKPILE"
STARVED_REASON = "STARVED"
WINDOW_FEED_REDUCTION = "WINDOW_FEED_REDUCTION"
RATE_RAMP_UP = "RATE_RAMP_UP"
RATE_RAMP_DOWN = "RATE_RAMP_DOWN"
DOWNSTREAM_CAPACITY = "DOWNSTREAM_CAPACITY"
PILE_FULL = "PILE_FULL"
FEED_REJECTED = "FEED_REJECTED"
NORMAL_OPERATION = "NORMAL_OPERATION"
STABLE = "STABLE"

_PILE_TREND_TOLERANCE_TPH = 1.0  # |F_in - F_out| bajo esto se considera "estable"


# ── Dataclasses de dominio ─────────────────────────────────────────────────────

@dataclass
class OperationalWindow:
    """Ventana operacional del sistema alimentador (Reglas 13-14).

    start_time/end_time en horas relativas al inicio del horizonte simulado
    (pueden ser negativas o mayores que el horizonte — una ventana que
    empezó antes de t=0 o que termina después del horizonte se maneja
    naturalmente por el chequeo start<=t<end, sin lógica especial).

    feed_factor_sac1/sac2 en [0.0, 1.0]: 0.0 = interrupción total,
    1.0 = sin reducción. Independientes entre sí (Regla 13) — una ventana
    puede afectar solo SAC1, solo SAC2, o ambos con factores distintos.
    """
    start_time: float
    end_time: float
    feed_factor_sac1: float = 0.0
    feed_factor_sac2: float = 0.0
    reason: str = ""

    def is_active_at(self, t: float) -> bool:
        return self.start_time <= t < self.end_time


@dataclass
class CircuitState:
    """Estado de un circuito SAG+pila en un instante dado."""
    asset: str  # "SAG1" | "SAG2"
    pile_inventory: float  # toneladas
    sag_requested_on: bool
    sag_effective_on: bool
    sag_requested_rate: float  # TPH
    sag_effective_rate: float  # TPH
    ball_mills_requested: dict = field(default_factory=dict)  # {"411": True, "412": False}
    ball_mills_effective: dict = field(default_factory=dict)
    operational_state: str = OFF
    pile_trend: str = STABLE


# ── Regla 4: dependencia SAG → molinos de bolas ───────────────────────────────

def resolve_equipment_dependencies(sag_effective_on: bool, balls_requested: dict) -> tuple[dict, str]:
    """Un molino de bolas nunca puede estar efectivamente encendido si su
    SAG asociado está apagado, sin importar lo que el usuario haya
    seleccionado.

        ball_effective = ball_requested and sag_effective_on

    Retorna (balls_effective, mensaje). El mensaje queda vacío si no hay
    ninguna discrepancia entre lo solicitado y lo efectivo (nada que
    informar); si el SAG está OFF y había al menos un molino solicitado
    ON, el mensaje describe la dependencia explícitamente (nunca se
    silencia el cambio)."""
    balls_effective = {k: bool(v) and sag_effective_on for k, v in balls_requested.items()}
    apagados_por_dependencia = [k for k, v in balls_requested.items() if v and not sag_effective_on]
    if apagados_por_dependencia:
        nombres = " y ".join(apagados_por_dependencia)
        plural = "s" if len(apagados_por_dependencia) > 1 else ""
        verbo = "quedan" if len(apagados_por_dependencia) > 1 else "queda"
        mensaje = (f"Molino{plural} {nombres} solicitado{plural} ON, pero {verbo} "
                   f"inactivo{plural} porque el SAG asociado está OFF.")
    else:
        mensaje = ""
    return balls_effective, mensaje


# ── Reglas 1-3: alimentación efectiva (ventana + recuperación) ───────────────

def resolve_window_feed_factor(windows: list[OperationalWindow], t: float, asset_key: str) -> tuple[float, str]:
    """Evalúa todas las ventanas activas en el instante t y retorna el
    factor combinado (Regla 14: en ventanas superpuestas se aplica la
    restricción más severa, `min(factores activos)`) y la razón de la
    ventana más restrictiva (para mensajes). Si ninguna ventana está
    activa, retorna (1.0, "")."""
    activos = [w for w in windows if w.is_active_at(t)]
    if not activos:
        return 1.0, ""
    factores = [(getattr(w, f"feed_factor_{asset_key}"), w.reason) for w in activos]
    factor_min, razon = min(factores, key=lambda fr: fr[0])
    return factor_min, razon


def calculate_effective_feed(
    f_in_normal: float,
    window_factor: float,
    elapsed_since_window_end_h: float | None,
    feed_recovery_time_min: float = 0.0,
    recovery_mode: str = "linear",
    feed_recovery_tau_min: float | None = None,
) -> float:
    """Alimentación efectiva hacia una pila.

    Durante ventana activa (window_factor < 1.0, `elapsed_since_window_end_h`
    es None): F_in_effective = F_in_normal * window_factor (Regla 1).

    Después de la ventana (`elapsed_since_window_end_h` >= 0): rampa de
    recuperación (Regla 3/Fase 2 sección 6). Con feed_recovery_time_min<=0
    la recuperación es instantánea (recovery_fraction=1.0 de inmediato) —
    comportamiento por defecto, igual al del motor original antes de este
    cambio.

    recovery_mode:
      "instant"     — recovery_fraction = 1.0 siempre (ignora recovery_time).
      "linear"      — recovery_fraction = min(1, elapsed/recovery_time) (default).
      "stepped"     — recovery_fraction = 0.0 hasta cumplir recovery_time, luego 1.0.
      "exponential" — F_in(t) = F_normal - (F_normal-F_window)*exp(-t/tau),
                      con tau = `feed_recovery_tau_min` (si no se entrega,
                      se usa `feed_recovery_time_min` como tau — supuesto
                      documentado, sin dato calibrado confirmado).
    """
    import math

    f_in_window = f_in_normal * window_factor

    if elapsed_since_window_end_h is None:
        # Ventana todavia activa (o nunca hubo ventana y window_factor=1.0,
        # en cuyo caso f_in_window == f_in_normal de todas formas).
        return f_in_window

    if recovery_mode == "exponential":
        tau_min = feed_recovery_tau_min if feed_recovery_tau_min is not None else feed_recovery_time_min
        if tau_min <= 0:
            return f_in_normal
        tau_h = tau_min / 60.0
        elapsed_h = max(0.0, elapsed_since_window_end_h)
        return f_in_normal - (f_in_normal - f_in_window) * math.exp(-elapsed_h / tau_h)

    if feed_recovery_time_min <= 0 or recovery_mode == "instant":
        return f_in_normal

    recovery_time_h = feed_recovery_time_min / 60.0
    elapsed_h = max(0.0, elapsed_since_window_end_h)

    if recovery_mode == "stepped":
        recovery_fraction = 1.0 if elapsed_h >= recovery_time_h else 0.0
    else:  # "linear"
        recovery_fraction = min(1.0, elapsed_h / recovery_time_h) if recovery_time_h > 0 else 1.0

    return f_in_window + recovery_fraction * (f_in_normal - f_in_window)


# ── Regla 10: rampas de arranque/detención ────────────────────────────────────

def apply_rate_ramp(
    rate_target: float,
    previous_rate: float,
    ramp_up_time_min: float,
    ramp_down_time_min: float,
    delta_t_h: float,
    rate_ceiling: float,
) -> float:
    """Limita el cambio de rate por paso según una rampa de tiempo
    configurable. Con ramp_time<=0 (default) el rate salta directo al
    target — comportamiento instantáneo, igual al motor original.

    ramp_up_time_min/ramp_down_time_min: minutos para ir de 0 al rate
    techo (`rate_ceiling`, ej. P90 del activo) — se usa para derivar una
    velocidad de cambio en TPH/h, no un tiempo absoluto por escalón."""
    if rate_target >= previous_rate:
        if ramp_up_time_min <= 0:
            return rate_target
        ramp_rate_tph_h = rate_ceiling / (ramp_up_time_min / 60.0)
        return min(rate_target, previous_rate + ramp_rate_tph_h * delta_t_h)
    else:
        if ramp_down_time_min <= 0:
            return rate_target
        ramp_rate_tph_h = rate_ceiling / (ramp_down_time_min / 60.0)
        return max(rate_target, previous_rate - ramp_rate_tph_h * delta_t_h)


# ── Reglas 5, 8, 9: rate efectivo del SAG ─────────────────────────────────────

def calculate_effective_sag_rate(
    rate_requested: float,
    sag_effective_on: bool,
    n_balls_effective: int,
    one_ball_capacity_factor: float,
    pile_inventory_ton: float,
    f_in_effective: float,
    delta_t_h: float,
    previous_rate: float = 0.0,
    ramp_up_time_min: float = 0.0,
    ramp_down_time_min: float = 0.0,
    rate_ceiling: float | None = None,
) -> float:
    """Rate efectivo final del SAG, considerando en orden (Regla 8):
      1. sag_effective_on (si False, 0 de inmediato — Regla 5).
      2. Capacidad aguas abajo por Nº de molinos de bolas activos (Regla 9):
           2 bolas -> factor 1.0
           1 bola  -> factor `one_ball_capacity_factor` (parametrizable,
                      sin dato calibrado confirmado se documenta como
                      supuesto — ver reporte técnico)
           0 bolas -> factor 0.0 (sin ruta de descarga valida, decision
                      por defecto documentada en Regla 9 del pedido)
      3. Inventario disponible (Regla 6): nunca se consume mineral
         inexistente — `available_rate = M/delta_t + F_in_effective`.
      4. Rampa de arranque/detención (Regla 10, opcional).
    """
    if not sag_effective_on:
        return 0.0

    if n_balls_effective >= 2:
        downstream_factor = 1.0
    elif n_balls_effective == 1:
        downstream_factor = one_ball_capacity_factor
    else:
        downstream_factor = 0.0

    rate_by_downstream = rate_requested * downstream_factor

    available_rate = max(0.0, pile_inventory_ton / delta_t_h + f_in_effective) if delta_t_h > 0 else rate_by_downstream
    rate_by_stockpile = available_rate

    rate_target = max(0.0, min(rate_by_downstream, rate_by_stockpile))

    if ramp_up_time_min <= 0 and ramp_down_time_min <= 0:
        return rate_target

    ceiling = rate_ceiling if rate_ceiling is not None else max(rate_requested, previous_rate, 1.0)
    return apply_rate_ramp(rate_target, previous_rate, ramp_up_time_min, ramp_down_time_min, delta_t_h, ceiling)


# ── Reglas 6-7: balance de masa con overflow/rechazo explícitos ──────────────

def update_stockpile_mass_balance(
    pile_inventory_ton: float,
    f_in_requested: float,
    f_out_requested: float,
    cap_max_ton: float,
    delta_t_h: float,
) -> tuple[float, float, float, float, float]:
    """Avanza un paso del balance de masa, SIN descartar en silencio lo
    que no cabe/no existe, y SIN consumir mineral inexistente (Reglas 6-7).

    Retorna (M_next_ton, f_in_accepted, overflow_ton, rejected_feed_tph,
    f_out_effective_tph):
      - f_out_effective_tph: consumo REALMENTE posible en este paso
        (Regla 6: `available_rate = M/delta_t + F_in`; nunca se consume
        mas mineral del que existe mas lo que entra en el mismo paso).
        Igual a `f_out_requested` salvo que la pila este cerca de
        agotarse (STARVED).
      - f_in_accepted: TPH de alimentación efectivamente aceptada por la
        pila en este paso (puede ser menor a f_in_requested si la pila
        está llena).
      - overflow_ton: toneladas que habrían excedido la capacidad máxima
        en este paso (0.0 si no hubo overflow).
      - rejected_feed_tph: `f_in_requested - f_in_accepted` (Regla 7).

    El inventario nunca es negativo (Regla 6, garantizado ahora por el
    limite de `f_out_effective_tph`, no solo por un clip posterior) y
    nunca supera `cap_max_ton` (`min(cap, ...)`, Regla 7) — a diferencia
    del clip silencioso original, aquí ambos casos quedan registrados.
    """
    if delta_t_h <= 0:
        return pile_inventory_ton, f_in_requested, 0.0, 0.0, f_out_requested

    # Regla 6: limitar el consumo a lo realmente disponible ANTES de
    # calcular el balance — recortar M a 0 despues del hecho no basta,
    # el SAG no puede haber consumido mineral que nunca existio.
    available_rate = max(0.0, pile_inventory_ton / delta_t_h + f_in_requested)
    f_out_effective = min(max(0.0, f_out_requested), available_rate)

    available_storage_ton = max(0.0, cap_max_ton - pile_inventory_ton)
    accepted_feed = min(f_in_requested, available_storage_ton / delta_t_h + f_out_effective)
    accepted_feed = max(0.0, accepted_feed)
    rejected_feed = max(0.0, f_in_requested - accepted_feed)

    pile_ton_calculated = pile_inventory_ton + (accepted_feed - f_out_effective) * delta_t_h

    overflow_ton = max(0.0, pile_ton_calculated - cap_max_ton)
    pile_ton_next = max(0.0, min(cap_max_ton, pile_ton_calculated))

    return pile_ton_next, accepted_feed, overflow_ton, rejected_feed, f_out_effective


# ── Regla 17: autonomía con consumo neto ──────────────────────────────────────

def calculate_stockpile_autonomy(
    pile_inventory_ton: float,
    m_min_operational_ton: float,
    f_in_effective: float,
    f_out_effective: float,
) -> tuple[float | None, str]:
    """Autonomía en horas usando el DRENAJE NETO (Regla 17), no el consumo
    bruto. Retorna (horas_o_None, mensaje):
      - Si f_out <= f_in: la pila no se agota -> (None, "Sin riesgo de
        agotamiento con las condiciones actuales").
      - Si f_out == 0 (SAG apagado): (None, "Autonomía no restrictiva:
        consumo SAG igual a cero.")
      - Si f_out > f_in: autonomia = (M - M_min) / net_drain_rate, en
        horas, nunca negativa.
    """
    if f_out_effective <= 0.0:
        return None, "Autonomía no restrictiva: consumo SAG igual a cero."
    if f_out_effective <= f_in_effective:
        return None, "Sin riesgo de agotamiento con las condiciones actuales."

    net_drain_rate = f_out_effective - f_in_effective
    horas = max(0.0, (pile_inventory_ton - m_min_operational_ton) / net_drain_rate)
    return horas, f"Autonomía estimada: {horas:.1f} h al ritmo de drenaje neto actual."


# ── Regla 11: estados operacionales y tendencia de pila ───────────────────────

# Fase 1.5 del roadmap de cierre (2026-07-15, ver 04_Reports/Technical/
# 20260715_Roadmap_Cierre_Simulador_Operacional.md): tolerancias
# explícitas para la comparación RESTRICTED, en vez de una comparación
# exacta de punto flotante. Default = comportamiento IDÉNTICO al previo
# a esta fase (1e-6, solo para evitar falsos positivos por precisión de
# punto flotante) — NO se fija un valor operacional definitivo sin datos
# (instrucción explícita del pedido: "no fijes valores definitivos sin
# sensibilidad"). El estudio de sensibilidad de
# `04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md`
# documenta el impacto de 6 combinaciones candidatas en el % de pasos
# clasificados RESTRICTED — la elección de un valor de producción queda
# pendiente de decisión explícita del usuario/producto.
RATE_RESTRICTION_TOLERANCE_TPH_DEFAULT = 1e-6
RATE_RESTRICTION_TOLERANCE_PCT_DEFAULT = 0.0


def determine_operational_state(
    sag_requested_on: bool,
    sag_effective_on: bool,
    rate_effective: float,
    rate_target: float,
    is_starved: bool,
    is_restricted_by_balls: bool,
    is_ramping_up: bool = False,
    is_ramping_down: bool = False,
    rate_restriction_tolerance_tph: float = RATE_RESTRICTION_TOLERANCE_TPH_DEFAULT,
    rate_restriction_tolerance_pct: float = RATE_RESTRICTION_TOLERANCE_PCT_DEFAULT,
) -> str:
    """Máquina de estados simple (Regla 11) — precedencia explícita:
    OFF > STARTING/STOPPING (transición) > STARVED > RESTRICTED > RUNNING.

    `rate_restriction_tolerance_tph`/`_pct` (Fase 1.5, 2026-07-15):
    tolerancia explícita para la comparación RESTRICTED — se usa
    `max(tolerance_tph, rate_target * tolerance_pct)`, igual que el
    ejemplo del pedido. Defaults preservan el comportamiento previo
    (comparación exacta salvo precisión de punto flotante)."""
    if not sag_requested_on and not sag_effective_on:
        return OFF
    if sag_requested_on and not sag_effective_on:
        return OFF  # apagado por dependencia/restriccion dura, no es un estado transitorio
    if is_ramping_down:
        return STOPPING
    if is_ramping_up:
        return STARTING
    if is_starved:
        return STARVED
    tolerancia = max(rate_restriction_tolerance_tph, rate_target * rate_restriction_tolerance_pct)
    if is_restricted_by_balls or (rate_target - rate_effective) > tolerancia:
        return RESTRICTED
    return RUNNING


def determine_pile_trend(f_in_effective: float, f_out_effective: float,
                          tolerance_tph: float = _PILE_TREND_TOLERANCE_TPH) -> str:
    """FILLING/DRAINING/STABLE según el signo del balance neto (Regla 11)."""
    d = f_in_effective - f_out_effective
    if d > tolerance_tph:
        return FILLING
    if d < -tolerance_tph:
        return DRAINING
    return STABLE


def determine_restriction_reason(
    sag_effective_on: bool,
    n_balls_effective: int,
    n_balls_requested: int,
    pile_pct: float,
    critical_pct: float,
    warning_pct: float,
    window_factor: float,
    is_ramping_up: bool,
    is_ramping_down: bool,
    rate_effective: float,
    rate_target: float,
    overflow_ton: float,
    rejected_feed_tph: float,
) -> tuple[str, list[str]]:
    """Motivo PRINCIPAL de restricción + motivos secundarios (Fase 2,
    sección 7 del pedido 2026-07-14). `operational_state=RESTRICTED` por
    si solo no dice nada — esto identifica la causa real, con la misma
    precedencia que `determine_operational_state` (Regla 15: SAG_OFF >
    BALL_MILLS_OFF > STARVED > capacidad aguas abajo > inventario bajo >
    ventana > rampas > pila llena > alimentacion rechazada > normal)."""
    activos: list[str] = []

    if not sag_effective_on:
        return SAG_OFF, []
    if n_balls_effective == 0 and n_balls_requested > 0:
        return BALL_MILLS_OFF, []
    if pile_pct <= critical_pct:
        activos.append(STARVED_REASON)
    if n_balls_effective == 1:
        activos.append(ONE_BALL_MILL_AVAILABLE)
    elif n_balls_effective == 0:
        activos.append(DOWNSTREAM_CAPACITY)
    if critical_pct < pile_pct <= warning_pct:
        activos.append(LOW_STOCKPILE)
    if window_factor < 1.0:
        activos.append(WINDOW_FEED_REDUCTION)
    if is_ramping_up:
        activos.append(RATE_RAMP_UP)
    if is_ramping_down:
        activos.append(RATE_RAMP_DOWN)
    if overflow_ton > 0:
        activos.append(PILE_FULL)
    if rejected_feed_tph > 0 and PILE_FULL not in activos:
        activos.append(FEED_REJECTED)

    if not activos:
        return NORMAL_OPERATION, []

    return activos[0], activos[1:]


# ── Reglas 12-13: distribución/redistribución entre SAC1 y SAC2 ──────────────

def redistribute_feed(
    f_in_sac1: float,
    f_in_sac2: float,
    circuit1_available: bool,
    circuit2_available: bool,
    capacity_sac1_tph: float,
    capacity_sac2_tph: float,
    enabled: bool = False,
) -> tuple[float, float, float]:
    """Si un circuito está detenido o sin capacidad de recepción
    disponible, redistribuye su alimentación hacia el otro circuito
    (Reglas 12-13), respetando el límite de capacidad del receptor. No
    duplica tonelaje: el total redistribuido nunca excede
    `f_in_sac1 + f_in_sac2`.

    Retorna (f_in_sac1_final, f_in_sac2_final, rejected_tph). Si
    `enabled=False` (default), retorna los valores originales sin
    modificar — comportamiento por defecto, sin redistribución."""
    if not enabled:
        return f_in_sac1, f_in_sac2, 0.0

    out1, out2 = f_in_sac1, f_in_sac2
    rejected = 0.0

    if not circuit1_available and circuit2_available:
        # Circuito 1 detenido: NADA de su feed puede quedarse asignado a
        # el (no lo puede recibir) — se transfiere lo que quepa en el
        # espacio disponible de circuito 2, el resto se rechaza.
        espacio_sac2 = max(0.0, capacity_sac2_tph - f_in_sac2)
        transferible = min(f_in_sac1, espacio_sac2)
        out1 = 0.0
        out2 = f_in_sac2 + transferible
        rejected = f_in_sac1 - transferible
    elif not circuit2_available and circuit1_available:
        espacio_sac1 = max(0.0, capacity_sac1_tph - f_in_sac1)
        transferible = min(f_in_sac2, espacio_sac1)
        out2 = 0.0
        out1 = f_in_sac1 + transferible
        rejected = f_in_sac2 - transferible

    return out1, out2, rejected


# ── Regla 16: recomendaciones operacionales ───────────────────────────────────

def generate_operational_recommendation(
    asset: str,
    pile_trend: str,
    window_active: bool,
    window_just_ended: bool,
    f_in_effective: float,
    f_out_effective: float,
    autonomy_hours: float | None,
    sag_effective_on: bool,
    dependency_message: str = "",
    ball_restricted: bool = False,
    window_time_remaining_h: float | None = None,
    rate_reduction_suggestion_tph: float | None = None,
) -> str:
    """Texto de recomendación derivado ÚNICAMENTE del estado real
    calculado (Regla 16) — nunca contradice los rates/estados efectivos
    porque se construye a partir de ellos, no de reglas independientes.

    Cuantifica la recomendación cuando hay datos suficientes (Fase 2,
    sección 8 del pedido 2026-07-14): si la autonomía restante es MENOR
    que el tiempo que falta de ventana, el mensaje advierte
    explícitamente en cuántos minutos se alcanzaría el mínimo antes de
    que termine la ventana."""
    if dependency_message:
        return dependency_message

    if not sag_effective_on:
        return f"{asset} está OFF; no consume inventario de su pila asociada."

    if window_active and pile_trend == DRAINING:
        base = (f"{asset} se encuentra drenando a "
                f"{f_out_effective - f_in_effective:.0f} t/h netas "
                f"(alimentación {f_in_effective:.0f} TPH vs consumo {f_out_effective:.0f} TPH).")
        if autonomy_hours is not None and window_time_remaining_h is not None:
            if autonomy_hours < window_time_remaining_h:
                faltante_min = (window_time_remaining_h - autonomy_hours) * 60.0
                sugerencia = ""
                if rate_reduction_suggestion_tph:
                    sugerencia = f" Reducir {asset} en aproximadamente {rate_reduction_suggestion_tph:.0f} t/h o redistribuir alimentación."
                return (f"{base} Alcanzará su mínimo operacional {faltante_min:.0f} minutos "
                        f"antes de finalizar la ventana.{sugerencia}")
            return (f"{base} Con el inventario actual, la autonomía hasta el mínimo "
                    f"operacional es de {autonomy_hours:.1f} horas, superior a las "
                    f"{window_time_remaining_h:.1f} horas restantes de ventana. "
                    f"Mantener el rate actual.")
        return base

    if window_just_ended:
        if pile_trend == FILLING:
            return (f"La alimentación fue restablecida y supera el consumo de {asset} "
                    f"({f_in_effective:.0f} TPH vs {f_out_effective:.0f} TPH); la pila "
                    f"comienza su recuperación.")
        if pile_trend == DRAINING:
            return (f"La alimentación fue restablecida, pero {asset} continúa drenando "
                    f"porque el consumo supera la alimentación en "
                    f"{f_out_effective - f_in_effective:.0f} t/h. Reducir rate o "
                    f"incrementar el split hacia {asset}.")

    if ball_restricted:
        return (f"{asset} se encuentra limitado por disponibilidad de molinos de bolas. "
                f"El rate efectivo máximo estimado es {f_out_effective:.0f} TPH.")

    if autonomy_hours is not None:
        return (f"Con el rate actual de {asset}, su pila alcanzará el nivel mínimo "
                f"operacional en aproximadamente {autonomy_hours:.1f} horas.")

    return "Sin riesgo de agotamiento con las condiciones actuales."


# ── Regla 18: conservación de masa ────────────────────────────────────────────

def validate_mass_conservation(
    initial_inventory_ton: float,
    cumulative_accepted_feed_ton: float,
    cumulative_sag_consumption_ton: float,
    final_inventory_ton: float,
    cumulative_overflow_ton: float = 0.0,
) -> float:
    """Error de conservación de masa (Regla 18), en toneladas. Debe ser
    ~0 (dentro de tolerancia numérica) para cualquier escenario:

        error = initial + accepted_feed - consumption - final - overflow
    """
    return (
        initial_inventory_ton
        + cumulative_accepted_feed_ton
        - cumulative_sag_consumption_ton
        - final_inventory_ton
        - cumulative_overflow_ton
    )


# ── Semántica temporal por episodio de ventana (Fase 2, secciones 1/4/5 del
# pedido 2026-07-14) — un único "FILLING"/"DRAINING" final no distingue
# drenado durante la ventana de recuperación después de ella; esto sí. ────────

@dataclass
class WindowEpisodeAnalysis:
    window_start_h: float
    window_end_h: float
    inventory_initial_pct: float
    inventory_at_window_start_pct: float
    inventory_minimum_pct: float
    time_of_minimum_h: float
    inventory_at_window_end_pct: float
    inventory_final_pct: float
    trend_during_window: str
    trend_after_window: str
    trend_final: str
    drained_tons_during_window: float
    recovered_tons_after_window: float
    recovery_fraction: float  # 0-1: cuanto del drawdown se recupero (1.0 = volvio al nivel de inicio de ventana)
    recovery_time_hours: float | None  # tiempo desde fin de ventana hasta recuperar inventory_at_window_start
    unrecovered_inventory_tons: float
    reached_starved: bool


def analyze_window_episode(
    time_h: list[float],
    pile_pct: list[float],
    qin_tph: list[float],
    qout_tph: list[float],
    window_start_h: float,
    window_end_h: float,
    cap_ton: float,
    critical_pct: float,
    trend_tolerance_tph: float = _PILE_TREND_TOLERANCE_TPH,
) -> WindowEpisodeAnalysis | None:
    """Analiza un episodio de ventana completo (preventana → ventana →
    recuperación → nuevo equilibrio, Fase 2 sección 5) sobre una serie ya
    simulada. Retorna None si `window_start_h`/`window_end_h` no caen
    dentro del horizonte simulado."""
    if not time_h or window_end_h <= 0 or window_start_h >= time_h[-1]:
        return None

    def _idx_at_or_after(t):
        for i, tt in enumerate(time_h):
            if tt >= t:
                return i
        return len(time_h) - 1

    i_start = _idx_at_or_after(max(0.0, window_start_h))
    i_end = _idx_at_or_after(window_end_h)

    tramo_ventana = pile_pct[i_start:i_end + 1] or [pile_pct[i_start]]
    idx_min_rel = min(range(len(tramo_ventana)), key=lambda k: tramo_ventana[k])
    inventory_minimum_pct = tramo_ventana[idx_min_rel]
    time_of_minimum_h = time_h[i_start + idx_min_rel]

    # El minimo real del episodio puede seguir bajando un poco DESPUES del
    # fin de ventana si el consumo sigue superando la alimentacion — se
    # busca el minimo global desde el inicio de ventana hasta que la
    # tendencia se vuelve sostenidamente positiva o se acaba la serie.
    tramo_completo = pile_pct[i_start:]
    if tramo_completo:
        idx_min_glob = min(range(len(tramo_completo)), key=lambda k: tramo_completo[k])
        if tramo_completo[idx_min_glob] < inventory_minimum_pct:
            inventory_minimum_pct = tramo_completo[idx_min_glob]
            time_of_minimum_h = time_h[i_start + idx_min_glob]

    def _avg_trend(i0, i1):
        if i1 <= i0:
            return STABLE
        qin_avg = sum(qin_tph[i0:i1]) / (i1 - i0)
        qout_avg = sum(qout_tph[i0:i1]) / (i1 - i0)
        return determine_pile_trend(qin_avg, qout_avg, trend_tolerance_tph)

    trend_during_window = _avg_trend(i_start, i_end)
    trend_after_window = _avg_trend(i_end, len(time_h) - 1)
    trend_final = _avg_trend(max(0, len(time_h) - 4), len(time_h) - 1)

    inv_at_window_start_pct = pile_pct[i_start]
    inv_at_window_end_pct = pile_pct[i_end]
    inv_final_pct = pile_pct[-1]

    drained_tons = max(0.0, (inv_at_window_start_pct - inventory_minimum_pct) / 100.0 * cap_ton)
    recovered_tons = max(0.0, (inv_final_pct - inventory_minimum_pct) / 100.0 * cap_ton)
    unrecovered_tons = max(0.0, drained_tons - recovered_tons)
    recovery_fraction = min(1.0, recovered_tons / drained_tons) if drained_tons > 1e-6 else 1.0

    recovery_time_h = None
    if inv_final_pct >= inv_at_window_start_pct:
        for i in range(i_end, len(time_h)):
            if pile_pct[i] >= inv_at_window_start_pct:
                recovery_time_h = time_h[i] - window_end_h
                break

    return WindowEpisodeAnalysis(
        window_start_h=window_start_h, window_end_h=window_end_h,
        inventory_initial_pct=pile_pct[0], inventory_at_window_start_pct=inv_at_window_start_pct,
        inventory_minimum_pct=inventory_minimum_pct, time_of_minimum_h=time_of_minimum_h,
        inventory_at_window_end_pct=inv_at_window_end_pct, inventory_final_pct=inv_final_pct,
        trend_during_window=trend_during_window, trend_after_window=trend_after_window,
        trend_final=trend_final, drained_tons_during_window=drained_tons,
        recovered_tons_after_window=recovered_tons, recovery_fraction=recovery_fraction,
        recovery_time_hours=recovery_time_h, unrecovered_inventory_tons=unrecovered_tons,
        reached_starved=(inventory_minimum_pct <= critical_pct),
    )


# ── Autonomía unificada (Fase 2, sección 3 del pedido 2026-07-14) ────────────

def compare_autonomy_sources(legacy_autonomy_h: float, net_balance_autonomy_h: float | None,
                              threshold_h: float = 1.0) -> tuple[float | None, bool]:
    """Compara la autonomía legacy (`ode_model.compute_autonomia`, formula
    simple `(pct-crit)/drain_pct_h`, usada por ~15 archivos fuera de este
    modulo) contra la autonomia de balance neto (`calculate_stockpile_
    autonomy`, la fuente unica de verdad para lo que se MUESTRA al JdS,
    Regla 17). No reemplaza la legacy (sigue viva para sus consumidores
    actuales) — solo señala si divergen mas de `threshold_h`, para dejarlo
    visible en logs de desarrollo en vez de mostrar dos numeros
    contradictorios sin explicacion.

    Retorna (diferencia_horas_o_None, diverge_bool). `net_balance_autonomy_h`
    None (pila sin riesgo de agotamiento) se trata como "diverge" solo si
    la legacy SI reporta un valor finito bajo (i.e. la legacy cree que hay
    riesgo y el balance neto dice que no)."""
    if net_balance_autonomy_h is None:
        diverge = legacy_autonomy_h < threshold_h * 3  # legacy "cree" que hay riesgo cercano
        return None, diverge
    diff = legacy_autonomy_h - net_balance_autonomy_h
    return diff, abs(diff) > threshold_h


# ── Reencuadre semántico de autonomía — Etapa 1 (2026-07-14, ver
# 04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md,
# 'Cuarta/Quinta pasada'). `compute_autonomia` (legacy) y
# `calculate_stockpile_autonomy` (arriba) no son "una correcta y otra
# incorrecta": la primera es una alerta de vulnerabilidad preventiva
# (tasa histórica fija `DRAIN_PCT_H`, calibrada sobre 27 episodios reales
# de drenaje), la segunda es una proyección de balance neto instantáneo.
# Lo que sigue NO reemplaza ninguna de las dos — les da un vocabulario
# categórico explícito para que la UI deje de presentarlas como si
# respondieran la misma pregunta. ──────────────────────────────────────

@dataclass(frozen=True)
class DynamicAutonomyResult:
    """Autonomía dinámica actual, con el motivo de cada `None` explícito
    en `status` en vez de un solo mensaje genérico. `hours` coincide
    numéricamente con `calculate_stockpile_autonomy` cuando la pila
    realmente está drenando — no es un cálculo alternativo, es la misma
    fórmula con una envoltura categórica."""
    hours: float | None
    status: str  # DRAINING | STABLE | FILLING | SAG_OFF | AT_CRITICAL_LEVEL
    net_drain_rate_tph: float  # positivo = drenando, negativo = llenando
    message: str


def classify_dynamic_autonomy(
    pile_inventory_ton: float,
    m_min_operational_ton: float,
    f_in_effective: float,
    f_out_effective: float,
    tolerance_tph: float = _PILE_TREND_TOLERANCE_TPH,
) -> DynamicAutonomyResult:
    """Clasificación categórica de la autonomía de balance neto. Reusa
    `determine_pile_trend` para la tolerancia FILLING/DRAINING/STABLE
    (misma tolerancia que ya usa `pile_trend_sagX` en `simulate_ode`),
    y la misma fórmula de horas que `calculate_stockpile_autonomy` — solo
    agrega el estado categórico que hoy se pierde al colapsar todo en
    `None`."""
    net_rate = f_out_effective - f_in_effective  # positivo = drenando

    if f_out_effective <= 0.0:
        return DynamicAutonomyResult(
            hours=None, status=SAG_OFF, net_drain_rate_tph=net_rate,
            message="No restrictiva: SAG detenido, consumo igual a cero.")

    trend = determine_pile_trend(f_in_effective, f_out_effective, tolerance_tph)
    if trend == FILLING:
        return DynamicAutonomyResult(
            hours=None, status=FILLING, net_drain_rate_tph=net_rate,
            message=f"Sin riesgo actual: la pila se recupera a {-net_rate:.0f} t/h netas.")
    if trend == STABLE:
        return DynamicAutonomyResult(
            hours=None, status=STABLE, net_drain_rate_tph=net_rate,
            message="Balance neto estable, sin agotamiento proyectado.")

    # trend == DRAINING (f_out > f_in + tolerance) de aquí en adelante
    if pile_inventory_ton <= m_min_operational_ton:
        return DynamicAutonomyResult(
            hours=0.0, status=AT_CRITICAL_LEVEL, net_drain_rate_tph=net_rate,
            message="Nivel crítico ahora, drenando bajo el balance actual.")

    horas = max(0.0, (pile_inventory_ton - m_min_operational_ton) / net_rate)
    return DynamicAutonomyResult(
        hours=horas, status=DRAINING, net_drain_rate_tph=net_rate,
        message=f"Drenando a {net_rate:.0f} t/h netas: autonomía estimada {horas:.1f} h.")


def classify_historical_vulnerability(hours: float, asset: str) -> str:
    """Traduce la autonomía preventiva histórica (`compute_autonomia`) a
    un semáforo categórico, reusando los umbrales YA calibrados y
    asimétricos por activo de `engine.rules_engine.AUTONOMY_THRESHOLDS`
    — no se inventan umbrales nuevos. Retorna 'CRITICA'|'ALTA'|'MEDIA'|
    'BAJA'. Import diferido: rules_engine.py no depende de este módulo,
    pero se evita el import a nivel de módulo para no crear un
    acoplamiento nuevo en el grafo de imports."""
    from engine.rules_engine import AUTONOMY_THRESHOLDS
    t = AUTONOMY_THRESHOLDS[asset]
    if hours < t["EMERGENCIA"]:
        return "CRITICA"
    if hours < t["CRITICO"]:
        return "ALTA"
    if hours < t["ALERTA"]:
        return "MEDIA"
    return "BAJA"


def classify_autonomy_divergence(legacy_autonomy_h: float, dynamic_result: DynamicAutonomyResult,
                                  threshold_h: float = 1.0) -> str:
    """Reemplaza la lectura binaria de `compare_autonomy_sources` (que
    sigue existiendo sin cambios) por una clasificación que reconoce que
    ambas métricas responden preguntas distintas por diseño — no toda
    divergencia es un conflicto.

    'EXPECTED_CONTEXT_DIFFERENCE': la pila no está drenando ahora
    (FILLING/STABLE/SAG_OFF) — la divergencia es la consecuencia esperada
    de comparar una alerta de peor-caso contra el estado actual, no un
    error. 'CONSISTENT': ambas describen la misma condición y coinciden
    dentro del umbral. 'POTENTIAL_UI_CONFLICT': ambas describen la MISMA
    condición (pila drenando ahora) pero difieren más del umbral — aquí
    sí es información operacional genuina. 'UNEXPECTED_MODEL_DIFFERENCE':
    caso no cubierto por los anteriores (p.ej. nivel crítico dinámico con
    vulnerabilidad histórica baja) — señal de revisar el modelo."""
    if dynamic_result.status in (FILLING, STABLE, SAG_OFF):
        return "EXPECTED_CONTEXT_DIFFERENCE"
    if dynamic_result.status == AT_CRITICAL_LEVEL:
        return "CONSISTENT" if legacy_autonomy_h < threshold_h * 3 else "UNEXPECTED_MODEL_DIFFERENCE"
    diff = legacy_autonomy_h - dynamic_result.hours
    return "CONSISTENT" if abs(diff) <= threshold_h else "POTENTIAL_UI_CONFLICT"


@dataclass(frozen=True)
class AutonomyContext:
    """Empaqueta ambas métricas de autonomía en un solo objeto — Etapa 2
    del reencuadre semántico (2026-07-15, ver 04_Reports/Technical/
    20260715_Migracion_Autonomia_Etapa2.md). Pensado para pasarse a
    consumidores de decisión (`rules_engine.py::recommend_action` y, en
    sesiones futuras, `risk_engine.py`/`optimizer_v2.py`/etc.) en vez de
    parámetros sueltos ambiguos."""
    dynamic_hours: float | None
    dynamic_status: str
    dynamic_net_rate_tph: float
    historical_hours: float
    historical_vulnerability: str
    divergence_class: str


def build_autonomy_context(
    pile_inventory_ton: float,
    m_min_operational_ton: float,
    f_in_effective: float,
    f_out_effective: float,
    historical_hours: float,
    asset: str,
) -> AutonomyContext:
    """Construye un `AutonomyContext` aplicando los clasificadores YA
    existentes (`classify_dynamic_autonomy`, `classify_historical_
    vulnerability`, `classify_autonomy_divergence`) — no recalcula
    ninguna fórmula nueva, solo empaqueta resultados de la única fuente
    de cálculo (Fase 12 del pedido 2026-07-15: evitar recomputaciones)."""
    dyn = classify_dynamic_autonomy(pile_inventory_ton, m_min_operational_ton,
                                     f_in_effective, f_out_effective)
    vuln = classify_historical_vulnerability(historical_hours, asset)
    div = classify_autonomy_divergence(historical_hours, dyn)
    return AutonomyContext(
        dynamic_hours=dyn.hours, dynamic_status=dyn.status,
        dynamic_net_rate_tph=dyn.net_drain_rate_tph,
        historical_hours=historical_hours, historical_vulnerability=vuln,
        divergence_class=div,
    )


# ── Bloque de calidad de simulación (Fase 2, sección 10 del pedido 2026-07-14) ─

def evaluate_simulation_quality(
    mass_balance_error_ton: float,
    mass_balance_tolerance_ton: float,
    pile_pct_series: list[float],
    rate_series: list[float],
) -> tuple[bool, list[str]]:
    """'Simulación físicamente consistente' — solo True si TODOS los
    invariantes se cumplen. Retorna (consistente_bool, advertencias)."""
    advertencias = []
    if abs(mass_balance_error_ton) > mass_balance_tolerance_ton:
        advertencias.append(
            f"Error de conservación de masa fuera de tolerancia: "
            f"{mass_balance_error_ton:.2f} t (tolerancia {mass_balance_tolerance_ton:.2f} t)")
    if any(p < -1e-6 for p in pile_pct_series):
        advertencias.append("Se detectó inventario de pila negativo.")
    if any(p > 100.0 + 1e-6 for p in pile_pct_series):
        advertencias.append("Se detectó inventario de pila sobre el 100%.")
    if any(r < -1e-6 for r in rate_series):
        advertencias.append("Se detectó un rate de consumo negativo.")
    return (len(advertencias) == 0), advertencias
