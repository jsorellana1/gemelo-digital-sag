"""
validate_circuit_state.py — Validacion grafica del kernel de dominio
centralizado (engine/circuit_state.py + su integracion en
engine/ode_model.py::simulate_ode), Fases 1 y 2.

Corrige las inconsistencias diagnosticadas sobre la version anterior de
este script (ver 04_Reports/Technical/20260714_Segunda_Fase_Logica_
Operacional.md seccion 1):
  1.1 — reporta tendencia DURANTE la ventana por separado de la tendencia
        FINAL (antes todo colapsaba a un solo "FILLING").
  1.2 — reporta SAC1 y SAC2 por separado y completos en TODOS los
        escenarios (antes el resumen solo mostraba "Pila SAG1" incluso en
        el escenario SAG2 OFF).
  1.3 — el escenario "09_agotamiento_pila" se renombra a
        "09_recuperacion_desde_nivel_bajo" (lo que realmente hace: parte
        bajo pero el balance neto es positivo) y se agrega
        "13_agotamiento_efectivo", que SI fuerza un balance neto negativo
        sostenido hasta STARVED.

Uso:
    python 05_Dashboard/scripts/validate_circuit_state.py
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASH_DIR = os.path.dirname(_HERE)
if _DASH_DIR not in sys.path:
    sys.path.insert(0, _DASH_DIR)

import plotly.graph_objects as go

from engine.simulator import simulate_scenario

OUT_DIR = os.path.join(_DASH_DIR, "outputs", "validation", "circuit_state")
os.makedirs(OUT_DIR, exist_ok=True)

_BASE = dict(
    pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
    sag1_activo=True, sag2_activo=True, correa315_estado="reducida", correa316_estado="reducida",
    bolas_sag1="solo_411", bolas_sag2="solo_511", horizonte_horas=24.0,
    rate_sag1_tph=1236.0, rate_sag2_tph=2214.0,
)
_ACTIVA = {"correa315_estado": "activa", "correa316_estado": "activa"}

ESCENARIOS = [
    ("01_ventana_2h_drenado_y_recuperacion", {**_BASE, "duracion_t8_h": 2.0}),
    ("02_ventana_4h_sin_recuperacion_completa", {**_BASE, "duracion_t8_h": 4.0}),
    ("03_ventana_8h_riesgo_de_minimo", {**_BASE, "duracion_t8_h": 8.0}),
    ("04_ventana_12h_entra_a_starved", {**_BASE, "duracion_t8_h": 12.0, "pila_sag1_pct": 25.0}),
    ("05_sin_ventana_balance_estable", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0,
                                         "rate_sag1_tph": 645.0}),  # ~igual al Qin tipico -> estable
    ("06_sin_ventana_pila_creciendo", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0}),
    ("07_sin_ventana_pila_drenando", {**_BASE, "duracion_t8_h": 0.0, "correa315_estado": "inactiva",
                                       "correa316_estado": "inactiva"}),
    ("08_sag1_off_sac1_llenandose", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0, "sag1_activo": False,
                                      "distribucion_t1": "balanceado", "bolas_sag1": "ambas_411_412"}),
    ("09_sag2_off_sac2_estable", {**_BASE, "duracion_t8_h": 0.0, "sag2_activo": False,
                                   "correa316_estado": "inactiva", "bolas_sag2": "ambas_511_512"}),
    ("10_una_bola_sag1", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0, "bolas_sag1": "solo_411",
                           "enforce_downstream_ball_capacity": True, "one_ball_capacity_factor_sag1": 0.55}),
    ("11_una_bola_sag2", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0, "bolas_sag2": "solo_511",
                           "enforce_downstream_ball_capacity": True, "one_ball_capacity_factor_sag2": 0.55}),
    ("12_cero_bolas_sag1", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0, "bolas_sag1": "sin_bola"}),
    ("13_agotamiento_efectivo", {**_BASE, "duracion_t8_h": 12.0, "pila_sag1_pct": 18.0,
                                  "correa315_estado": "inactiva", "rate_sag1_tph": 1400.0}),
    ("14_recuperacion_desde_nivel_bajo", {**_BASE, "duracion_t8_h": 8.0, "pila_sag1_pct": 19.4}),
    ("15_pila_llena_con_rechazo", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0, "sag1_activo": False,
                                    "pila_sag1_pct": 99.5, "distribucion_t1": "balanceado"}),
    ("16a_redistribucion_off", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0, "sag1_activo": False,
                                 "distribucion_t1": "balanceado", "redistribution_enabled": False}),
    ("16b_redistribucion_on", {**_BASE, **_ACTIVA, "duracion_t8_h": 0.0, "sag1_activo": False,
                                "distribucion_t1": "balanceado", "redistribution_enabled": True}),
    ("19_recuperacion_lineal", {**_BASE, "duracion_t8_h": 4.0, "feed_recovery_mode": "linear",
                                 "feed_recovery_time_min": 60.0}),
    ("20_recuperacion_exponencial", {**_BASE, "duracion_t8_h": 4.0, "feed_recovery_mode": "exponential",
                                      "feed_recovery_tau_min": 45.0}),
]


def _fmt_pct(x):
    return f"{x:.1f}%" if x is not None else "—"


def _fmt_h(x):
    return f"{x:.2f} h" if x is not None else "—"


def _circuito_resumen(sim: dict, asset_num: str) -> dict:
    """Reporta SAC1 o SAC2 de forma completa e independiente — Fase 2
    seccion 1.2: nunca mezclar el nombre de un circuito con los datos del
    otro."""
    p = f"sag{asset_num}"
    pile_key = f"pile_sag{asset_num}"
    tph_key = f"tph_sag{asset_num}"
    qin_key = "cv315" if asset_num == "1" else "cv316"
    ep = sim.get(f"window_episode_sag{asset_num}")
    return {
        "inventario_inicial_pct": sim[pile_key][0],
        "inventario_minimo_pct": min(sim[pile_key]),
        "inventario_final_pct": sim[pile_key][-1],
        "tendencia_durante_ventana": ep.trend_during_window if ep else None,
        "tendencia_posterior_ventana": ep.trend_after_window if ep else None,
        "tendencia_final": sim[f"pile_trend_sag{asset_num}"],
        "autonomia_minima_h": min((h for h in [sim[f"autonomy_hours_sag{asset_num}"]] if h is not None), default=None),
        "autonomia_legacy_h": sim[f"legacy_autonomia_sag{asset_num}"],
        "autonomia_diverge": sim[f"autonomy_diverges_sag{asset_num}"],
        "rate_efectivo_max_tph": max(sim[tph_key]),
        "rate_efectivo_prom_tph": sum(sim[tph_key]) / len(sim[tph_key]),
        "alimentacion_rechazada_total_tph_sum": round(sum(sim[f"rejected_feed_sag{asset_num}"]), 1),
        "overflow_total_ton": round(sum(sim[f"overflow_sag{asset_num}"]), 1),
        "estado_operacional": sim[f"operational_state_sag{asset_num}"],
        "motivo_restriccion": sim[f"restriction_reason_sag{asset_num}"],
        "motivos_secundarios": sim[f"secondary_restrictions_sag{asset_num}"],
        "dependencia_bolas": sim[f"dependency_message_sag{asset_num}"] or None,
        "error_masa_ton": sim[f"mass_balance_error_sag{asset_num}"],
        "consistente": sim[f"simulation_consistent_sag{asset_num}"],
        "advertencias": sim[f"simulation_warnings_sag{asset_num}"],
        "alcanzo_starved_en_ventana": ep.reached_starved if ep else None,
        "tiempo_del_minimo_h": ep.time_of_minimum_h if ep else None,
        "tiempo_recuperacion_h": ep.recovery_time_hours if ep else None,
        "fraccion_recuperada": ep.recovery_fraction if ep else None,
    }


def _plot(nombre: str, sim: dict) -> None:
    time = sim["time"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=time, y=sim["pile_sag1"], name="Pila SAG1 (%)", line=dict(color="#4FB0E5")))
    fig.add_trace(go.Scatter(x=time, y=sim["pile_sag2"], name="Pila SAG2 (%)", line=dict(color="#E8935A")))
    fig.add_trace(go.Scatter(x=time, y=sim["cv315"], name="Qin SAG1 (TPH)", yaxis="y2",
                              line=dict(color="#4FB0E5", dash="dot")))
    fig.add_trace(go.Scatter(x=time, y=sim["tph_sag1"], name="Qout SAG1 (TPH)", yaxis="y2",
                              line=dict(color="#4FB0E5", dash="dash")))
    fig.add_trace(go.Scatter(x=time, y=sim["cv316"], name="Qin SAG2 (TPH)", yaxis="y2",
                              line=dict(color="#E8935A", dash="dot")))
    fig.add_trace(go.Scatter(x=time, y=sim["tph_sag2"], name="Qout SAG2 (TPH)", yaxis="y2",
                              line=dict(color="#E8935A", dash="dash")))
    for ep, color, nombre_sag in [(sim.get("window_episode_sag1"), "#4FB0E5", "SAG1"),
                                   (sim.get("window_episode_sag2"), "#E8935A", "SAG2")]:
        if ep is not None:
            fig.add_vline(x=ep.time_of_minimum_h, line_dash="dot", line_color=color)
            fig.add_annotation(x=ep.time_of_minimum_h, y=ep.inventory_minimum_pct,
                                text=f"Mínimo {nombre_sag}: {ep.inventory_minimum_pct:.0f}%",
                                showarrow=True, arrowcolor=color, font=dict(color=color, size=9))
    fig.update_layout(
        title=f"Validación circuit_state (Fase 2) — {nombre}",
        xaxis_title="Tiempo (h)",
        yaxis=dict(title="Pila (%)", range=[0, 105]),
        yaxis2=dict(title="TPH", overlaying="y", side="right"),
        legend=dict(orientation="h", y=-0.2),
        height=520,
    )
    fig.write_html(os.path.join(OUT_DIR, f"{nombre}.html"))


def main():
    resumen_total = {}
    for nombre, params in ESCENARIOS:
        try:
            sim = simulate_scenario(**params)
        except Exception as exc:
            print(f"[{nombre}] ERROR: {exc}")
            resumen_total[nombre] = {"error": str(exc)}
            continue
        _plot(nombre, sim)
        resumen = {"SAC1": _circuito_resumen(sim, "1"), "SAC2": _circuito_resumen(sim, "2")}
        resumen_total[nombre] = resumen
        r1, r2 = resumen["SAC1"], resumen["SAC2"]
        print(f"[{nombre}]")
        print(f"  SAC1: {_fmt_pct(r1['inventario_inicial_pct'])} -> min {_fmt_pct(r1['inventario_minimo_pct'])}"
              f" -> {_fmt_pct(r1['inventario_final_pct'])} | durante_ventana={r1['tendencia_durante_ventana']} "
              f"final={r1['tendencia_final']} | estado={r1['estado_operacional']}/{r1['motivo_restriccion']} "
              f"| error_masa={r1['error_masa_ton']:.2e} ton | consistente={r1['consistente']}")
        print(f"  SAC2: {_fmt_pct(r2['inventario_inicial_pct'])} -> min {_fmt_pct(r2['inventario_minimo_pct'])}"
              f" -> {_fmt_pct(r2['inventario_final_pct'])} | durante_ventana={r2['tendencia_durante_ventana']} "
              f"final={r2['tendencia_final']} | estado={r2['estado_operacional']}/{r2['motivo_restriccion']} "
              f"| error_masa={r2['error_masa_ton']:.2e} ton | consistente={r2['consistente']}")

    resumen_path = os.path.join(OUT_DIR, "resumen.json")
    with open(resumen_path, "w", encoding="utf-8") as f:
        json.dump(resumen_total, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResumen: {resumen_path}")
    print(f"Gráficos HTML en: {OUT_DIR}")


if __name__ == "__main__":
    main()
