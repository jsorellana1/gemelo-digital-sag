"""
scheduler.py — Fundacion temporal (turno/hora real) y mantenciones por equipo.

Usado por pages/simulador_operacional.py para:
  1. Mapear el turno seleccionado a una hora de reloj de inicio del horizonte.
  2. Re-etiquetar los ejes de horas relativas de los graficos existentes a
     hora del dia real.
  3. Determinar que equipos estan en mantencion al inicio del horizonte y
     restringir la grilla del optimizador (restriccion dura).
"""

TURNO_START_HOUR = {"C": 0, "A": 8, "B": 16}

EQUIPOS_MANTENCION = [
    "SAG1", "SAG2", "411", "412", "511", "512",
    "CH1", "CH2", "CV315", "CV316", "T1", "T3",
]

# Equipos que participan de cada opcion de bola por SAG (para saber que
# opciones quedan invalidadas si un molino especifico esta en mantencion).
_BOLA1_REQUIRES = {
    "sin_bola": set(),
    "solo_411": {"411"},
    "solo_412": {"412"},
    "ambas_411_412": {"411", "412"},
}
_BOLA2_REQUIRES = {
    "sin_bola": set(),
    "solo_511": {"511"},
    "solo_512": {"512"},
    "ambas_511_512": {"511", "512"},
}


def hour_in_window(hour: float, ini: float, fin: float) -> bool:
    """True si `hour` (0-24) cae dentro de [ini, fin). Soporta ventanas que
    cruzan medianoche (ej. 22-02) cuando fin < ini.

    Bug fix QA 2026-07-06: una ventana de mantencion de dia completo
    ([0, 24], alcanzable arrastrando el RangeSlider ctrl-mant-* a fondo,
    min=0/max=24) quedaba silenciosamente ignorada — `24 % 24 == 0 == ini`
    hacia que el chequeo `ini == fin` la tratara como "sin ventana". Se
    verifica el largo ANTES de aplicar modulo 24."""
    if (fin - ini) >= 24.0:
        return True
    hour = hour % 24.0
    ini = ini % 24.0
    fin = fin % 24.0
    if ini == fin:
        return False
    if ini < fin:
        return ini <= hour < fin
    return hour >= ini or hour < fin


def equipos_en_mantencion(maint_windows: dict, now_hour: float) -> set:
    """maint_windows: {equipo: (ini, fin) o None}. now_hour: hora de reloj
    (0-24) del inicio del horizonte (TURNO_START_HOUR[turno])."""
    activos = set()
    for equipo, ventana in (maint_windows or {}).items():
        if not ventana:
            continue
        ini, fin = ventana
        if ini is None or fin is None or ini == fin:
            continue
        if hour_in_window(now_hour, ini, fin):
            activos.add(equipo)
    return activos


def bola_opts_restringidas(base_opts: list, en_mantencion: set, sag: str) -> list:
    """Filtra opciones de bola (ej. BOLA1_OPTS_FULL) que requieran un molino
    presente en `en_mantencion`. `sag` = 'SAG1' o 'SAG2'."""
    requires = _BOLA1_REQUIRES if sag == "SAG1" else _BOLA2_REQUIRES
    return [
        opt for opt in base_opts
        if not (requires.get(opt, set()) & en_mantencion)
    ]


def sag_forzado_off(sag_id: str, en_mantencion: set) -> bool:
    return sag_id in en_mantencion


def r16_conflicto_mantencion(en_mantencion: set, sag: str) -> bool:
    """R16: cada SAG debe tener al menos 1 molino de bolas operativo. True si
    AMBOS molinos de `sag` ('SAG1' o 'SAG2') estan en mantencion
    simultaneamente, dejando al SAG sin ninguna opcion valida bajo R16."""
    pares = {"411", "412"} if sag == "SAG1" else {"511", "512"}
    return pares.issubset(en_mantencion)


def hour_of_day_ticks(base_hour: float, horizonte_h: float, step: float = 2.0):
    """Devuelve (tickvals, ticktext) para re-etiquetar un eje de horas
    relativas [0, horizonte_h] con hora de reloj real 'HH:MM', partiendo de
    `base_hour` (hora de inicio del turno)."""
    tickvals = []
    ticktext = []
    t = 0.0
    while t <= horizonte_h + 1e-9:
        clock_h = (base_hour + t) % 24.0
        hh = int(clock_h)
        mm = int(round((clock_h - hh) * 60))
        if mm == 60:
            mm = 0
            hh = (hh + 1) % 24
        tickvals.append(t)
        ticktext.append(f"{hh:02d}:{mm:02d}")
        t += step
    return tickvals, ticktext
