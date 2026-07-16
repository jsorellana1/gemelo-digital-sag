"""
turno_planner.py — Planificador de Turno: cronograma hora a hora de
disponibilidad de equipos (411/412/511/512) y rate recomendado SAG1/SAG2.

No introduce ningun calculo nuevo: reutiliza engine.scheduler
(equipos_en_mantencion, sag_forzado_off) — la disponibilidad de equipos
por mantencion YA es una funcion del reloj (hora), lo unico nuevo es
tabular esa evolucion hora a hora en vez de mostrar solo el estado en
`now_hour` (que es lo que hace el resto del dashboard hoy).
"""
from __future__ import annotations

from engine.scheduler import equipos_en_mantencion, sag_forzado_off

_EQUIPOS_411_412_511_512 = ["411", "412", "511", "512"]


def build_hourly_schedule(
    base_hour: float,
    horizonte_h: float,
    duracion_t8: float,
    maint_windows: dict,
    rate1_tph: float,
    rate2_tph: float,
    bola1_label: str,
    bola2_label: str,
) -> list[dict]:
    """Retorna una fila por hora (0..ceil(horizonte_h)-1) con:
    hora_reloj, sag1_tph, sag2_tph, 411, 412, 511, 512, t8_activo.

    El rate SAG1/SAG2 es el ya recomendado por el optimizador para todo el
    horizonte (V3/V4 no generan un plan hora-a-hora distinto) — lo que
    cambia por hora es la disponibilidad real de equipos por mantencion
    programada, y si esa hora cae dentro de la ventana T8.
    """
    n_horas = int(horizonte_h)
    filas = []
    for h in range(n_horas):
        reloj = (base_hour + h) % 24.0
        en_mant = equipos_en_mantencion(maint_windows, reloj)

        sag1_off = sag_forzado_off("SAG1", en_mant)
        sag2_off = sag_forzado_off("SAG2", en_mant)
        t8_activo = h < duracion_t8

        fila = {
            "hora_reloj": f"{int(reloj):02d}:00",
            "sag1_tph": 0 if sag1_off else round(rate1_tph, 0),
            "sag2_tph": 0 if sag2_off else round(rate2_tph, 0),
            "bolas_sag1": "—" if sag1_off else bola1_label,
            "bolas_sag2": "—" if sag2_off else bola2_label,
            "t8_activo": t8_activo,
        }
        for eq in _EQUIPOS_411_412_511_512:
            fila[eq] = "MANTENCIÓN" if eq in en_mant else "ON"
        filas.append(fila)
    return filas
