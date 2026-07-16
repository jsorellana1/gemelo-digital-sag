"""
sensitivity_circuit_state.py — Sensibilidad de parametros NO calibrados del
kernel de dominio (engine/circuit_state.py, Fase 2, seccion 12 del pedido
"Segunda fase de mejora del Simulador Operacional SAG").

Estos 4 parametros no tienen dato calibrado confirmado desde planta; se
usan defaults documentados como supuestos. Este script mide cuanto cambia
el resultado (KPIs de pila/autonomia) al moverlos dentro de un rango
razonable, sobre un escenario de ventana representativo (8h, riesgo de
minimo) — para que quede documentado cuan sensible es el simulador a cada
supuesto, sin necesidad de recalibrarlos con datos reales todavia.

Uso:
    python 05_Dashboard/scripts/sensitivity_circuit_state.py
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASH_DIR = os.path.dirname(_HERE)
if _DASH_DIR not in sys.path:
    sys.path.insert(0, _DASH_DIR)

from engine.simulator import simulate_scenario
from engine import circuit_state as cs
from engine.ode_model import CAP_TON

OUT_DIR = os.path.join(_DASH_DIR, "outputs", "validation", "circuit_state")
os.makedirs(OUT_DIR, exist_ok=True)

_BASE = dict(
    pila_sag1_pct=55.0, pila_sag2_pct=55.0, rate_sag1_pct=100.0, rate_sag2_pct=100.0,
    sag1_activo=True, sag2_activo=True, correa315_estado="reducida", correa316_estado="reducida",
    bolas_sag1="solo_411", bolas_sag2="solo_511", horizonte_horas=24.0, duracion_t8_h=8.0,
    rate_sag1_tph=1236.0, rate_sag2_tph=2214.0,
)

PARAM_GRIDS = {
    "one_ball_capacity_factor": {
        "valores": [0.40, 0.55, 0.70],
        "kwargs_extra": {"enforce_downstream_ball_capacity": True},
        "kwarg": "one_ball_capacity_factor",
        "default_actual": 0.55,
    },
    "feed_recovery_time_min": {
        "valores": [0, 30, 60, 120],
        "kwargs_extra": {},
        "kwarg": "feed_recovery_time_min",
        "default_actual": 0.0,
    },
    "sag_ramp_up_time_min": {
        "valores": [0, 15, 30, 60],
        "kwargs_extra": {},
        "kwarg": "sag_ramp_up_time_min",
        "default_actual": 0.0,
    },
}


def _kpis(sim: dict) -> dict:
    return {
        "pile_min_sag1_pct": round(min(sim["pile_sag1"]), 1),
        "pile_min_sag2_pct": round(min(sim["pile_sag2"]), 1),
        "pile_final_sag1_pct": round(sim["pile_sag1"][-1], 1),
        "autonomy_hours_sag1": sim["autonomy_hours_sag1"],
        "autonomy_hours_sag2": sim["autonomy_hours_sag2"],
        "operational_state_sag1": sim["operational_state_sag1"],
        "restriction_reason_sag1": sim["restriction_reason_sag1"],
        "mass_balance_error_sag1_ton": round(sim["mass_balance_error_sag1"], 4),
        "tph_sag1_prom": round(sum(sim["tph_sag1"]) / len(sim["tph_sag1"]), 1),
    }


def main():
    resultado = {}
    for nombre_param, cfg in PARAM_GRIDS.items():
        filas = []
        for valor in cfg["valores"]:
            params = {**_BASE, **cfg["kwargs_extra"], cfg["kwarg"]: valor}
            sim = simulate_scenario(**params)
            fila = {"valor": valor, **_kpis(sim)}
            filas.append(fila)
        resultado[nombre_param] = {
            "default_actual": cfg["default_actual"],
            "filas": filas,
        }
        print(f"\n=== Sensibilidad: {nombre_param} (default actual = {cfg['default_actual']}) ===")
        print(f"{'valor':>8} | {'min_SAC1%':>10} | {'min_SAC2%':>10} | {'fin_SAC1%':>10} | "
              f"{'autonomia_h':>12} | {'estado_SAC1':>14} | {'err_masa_ton':>12}")
        for fila in filas:
            aut = fila["autonomy_hours_sag1"]
            aut_s = f"{aut:.2f}" if aut is not None else "-"
            print(f"{fila['valor']:>8} | {fila['pile_min_sag1_pct']:>10} | {fila['pile_min_sag2_pct']:>10} | "
                  f"{fila['pile_final_sag1_pct']:>10} | {aut_s:>12} | {fila['operational_state_sag1']:>14} | "
                  f"{fila['mass_balance_error_sag1_ton']:>12}")

    # trend_tolerance_tph no se propaga como parametro de simulate_ode
    # (es una constante interna de determine_pile_trend/analyze_window_episode).
    # Se mide directo sobre el kernel, aplicado a las series Qin/Qout de un
    # escenario ya simulado con el default actual.
    sim_base = simulate_scenario(**_BASE)
    filas_tol = []
    for tol in [0.5, 1.0, 2.0, 5.0, 10.0]:
        ep = cs.analyze_window_episode(
            sim_base["time"], sim_base["pile_sag1"], sim_base["cv315"], sim_base["tph_sag1"],
            window_start_h=0.0, window_end_h=8.0, cap_ton=CAP_TON["SAG1"],
            critical_pct=15.0, trend_tolerance_tph=tol,
        )
        filas_tol.append({
            "valor": tol,
            "trend_during_window": ep.trend_during_window if ep else None,
            "trend_after_window": ep.trend_after_window if ep else None,
            "trend_final": ep.trend_final if ep else None,
        })
    resultado["trend_tolerance_tph"] = {"default_actual": 1.0, "filas": filas_tol}
    print(f"\n=== Sensibilidad: trend_tolerance_tph (default actual = 1.0) ===")
    print(f"{'valor':>8} | {'durante_ventana':>16} | {'posterior_ventana':>18} | {'final':>10}")
    for fila in filas_tol:
        print(f"{fila['valor']:>8} | {str(fila['trend_during_window']):>16} | "
              f"{str(fila['trend_after_window']):>18} | {str(fila['trend_final']):>10}")

    out_path = os.path.join(OUT_DIR, "sensibilidad_parametros.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResumen: {out_path}")


if __name__ == "__main__":
    main()
