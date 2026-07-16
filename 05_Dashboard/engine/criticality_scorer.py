"""
criticality_scorer.py — Scoring numerico de urgencia por regimen
(Prerequisito 2, PROMPT v2 2026-07-07).

Reemplaza el PRIORITY_ORDER fijo (H4>H6>H2>H5>H3>H7>H1) de
simulation_router v1 por un score de urgencia [0-100] calculado ANTES de
simular, a partir unicamente de campos ya presentes en `ScenarioInputs`
(pila actual/proyectada, disponibilidad de equipos, T8). El score fijo
seguia siendo correcto en la mayoria de los casos observados, pero no
distinguia "inventario critico leve" de "inventario critico severo" — dos
escenarios con el mismo tipo pero urgencia muy distinta.

No introduce fisica nueva: los umbrales de severidad reutilizan las
mismas constantes que engine/bottleneck.py (MIN_AUTON_ALERTA_H, etc.) y
engine/ode_model.py (CRITICAL_PCT).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.ode_model import CRITICAL_PCT
from engine.scenario_inputs import ScenarioInputs

OVERFLOW_ALERTA_PCT = 95.0
OVERFLOW_CRITICO_PCT = 98.0


@dataclass
class RegimeCriticality:
    regimen: str
    urgency_score: float          # 0-100, mayor = mas urgente
    razones: list[str] = field(default_factory=list)


class CriticalityScorer:
    """score(scenario_inputs_sag1, scenario_inputs_sag2, mantencion_activa,
    alimentacion_restringida) -> list[RegimeCriticality] ordenado desc por
    urgency_score. El router usa el primer elemento (o combina via
    MixedRegimeStrategy si hay 2+ con score > MIXTO_THRESHOLD)."""

    MIXTO_THRESHOLD = 30.0   # bajo este score, un regimen secundario se ignora

    def _score_overflow(self, s: ScenarioInputs, asset: str) -> RegimeCriticality:
        p = max(s.pila_actual_pct, s.pila_proyectada_pct)
        if p < OVERFLOW_ALERTA_PCT:
            return RegimeCriticality(f"overflow_{asset}", 0.0, [])
        # Escala 0-100 entre alerta (95%) y critico+margen (105%)
        score = min(100.0, (p - OVERFLOW_ALERTA_PCT) / (105.0 - OVERFLOW_ALERTA_PCT) * 100.0)
        razon = f"{asset}: pila proyectada {p:.1f}% (umbral alerta {OVERFLOW_ALERTA_PCT:.0f}%)"
        return RegimeCriticality(f"overflow_{asset}", score, [razon])

    def _score_inventario_critico(self, s: ScenarioInputs, asset: str) -> RegimeCriticality:
        crit = CRITICAL_PCT[asset]
        alerta = crit * 1.5  # margen de alerta = 1.5x el nivel critico (mismo criterio que bottleneck.py)
        p = min(s.pila_actual_pct, s.pila_proyectada_pct)
        if p >= alerta:
            return RegimeCriticality(f"inventario_critico_{asset}", 0.0, [])
        score = min(100.0, max(0.0, (alerta - p) / alerta * 100.0))
        razon = (f"{asset}: pila actual {s.pila_actual_pct:.1f}%, proyectada (2h) {s.pila_proyectada_pct:.1f}% "
                 f"— bajo umbral de alerta {alerta:.1f}% (critico={crit:.1f}%)")
        return RegimeCriticality(f"inventario_critico_{asset}", score, [razon])

    def _score_t8(self, s: ScenarioInputs) -> RegimeCriticality:
        if not s.t8_activa or s.t8_duracion_h <= 0:
            return RegimeCriticality("t8", 0.0, [])
        # 0h->0, 4h->50 (limite corta/larga), 16h+ -> 100
        score = min(100.0, s.t8_duracion_h / 16.0 * 100.0)
        tipo = "t8_larga" if s.t8_duracion_h > 4.0 else "t8_corta"
        razon = f"T8 activa {s.t8_duracion_h:.0f}h ({tipo})"
        return RegimeCriticality(tipo, score, [razon])

    def _score_mantencion(self, equipos_en_mantencion: list[str]) -> RegimeCriticality:
        if not equipos_en_mantencion:
            return RegimeCriticality("mantenimiento", 0.0, [])
        # Doble MoBo o SAG completo en mantencion pesa mas que un equipo menor
        criticos = {"411", "412", "511", "512", "SAG1", "SAG2"}
        n_criticos = sum(1 for e in equipos_en_mantencion if e in criticos)
        score = min(100.0, 40.0 + n_criticos * 30.0)
        razon = f"Equipos en mantencion: {', '.join(equipos_en_mantencion)}"
        return RegimeCriticality("mantenimiento", score, [razon])

    def _score_alimentacion_restringida(self, s1: ScenarioInputs, s2: ScenarioInputs) -> RegimeCriticality:
        restricciones = []
        if not s1.cv315_disponible:
            restricciones.append("CV315")
        if not s2.cv316_disponible:
            restricciones.append("CV316")
        if not s1.t1_disponible:
            restricciones.append("T1")
        if not restricciones:
            return RegimeCriticality("alimentacion_restringida", 0.0, [])
        score = min(100.0, 35.0 * len(restricciones))
        razon = f"Restriccion de alimentacion: {', '.join(restricciones)}"
        return RegimeCriticality("alimentacion_restringida", score, [razon])

    def score(self, s1: ScenarioInputs, s2: ScenarioInputs) -> list[RegimeCriticality]:
        candidatos = [
            self._score_overflow(s1, "SAG1"),
            self._score_overflow(s2, "SAG2"),
            self._score_inventario_critico(s1, "SAG1"),
            self._score_inventario_critico(s2, "SAG2"),
            self._score_t8(s1 if s1.t8_activa else s2),
            self._score_mantencion(s1.equipos_en_mantencion),
            self._score_alimentacion_restringida(s1, s2),
        ]
        activos = [c for c in candidatos if c.urgency_score > 0.0]
        if not activos:
            activos = [RegimeCriticality("normal", 10.0, ["Sin restricciones activas detectadas"])]
        activos.sort(key=lambda c: c.urgency_score, reverse=True)
        return activos
