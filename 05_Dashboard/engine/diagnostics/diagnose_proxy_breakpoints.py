"""
diagnose_proxy_breakpoints.py - Diagnostico reproducible del efecto de
_pile_feedback_factor en los regimenes proxy de historical_backtesting.

Replica exactamente la llamada de run_backtest_proxy() para cada evento,
pero conserva la trayectoria completa de pile_sag1 para medir si la
simulacion cruza los breakpoints de 35% / 25% / (CRITICAL_PCT+5%).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", ".."))
if _DASHBOARD not in sys.path:
    sys.path.insert(0, _DASHBOARD)

from engine.diagnostics.regime_event_detector import detectar_todos_los_regimenes, _load_serie
from engine.ode_model import CRITICAL_PCT

BREAKPOINTS_SAG1 = {
    "cross_35": 35.0,
    "cross_25": 25.0,
    "cross_crit5": CRITICAL_PCT["SAG1"] + 5.0,
}


def _breakpoint_summary(df: pd.DataFrame, error_col: str = "error_abs") -> dict[str, dict[str, dict[str, float | int]]]:
    out: dict[str, dict[str, dict[str, float | int]]] = {}
    for col in BREAKPOINTS_SAG1:
        grupos: dict[str, dict[str, float | int]] = {}
        for crossed in (False, True):
            sub = df.loc[df[col] == crossed, error_col].dropna()
            grupos["si" if crossed else "no"] = {
                "n": int(sub.size),
                "media": float(sub.mean()) if sub.size else float("nan"),
                "mediana": float(sub.median()) if sub.size else float("nan"),
            }
        out[col] = grupos
    return out


def run_proxy_breakpoint_diagnosis(regimen: str) -> dict:
    from engine.simulator import simulate_scenario_cached

    df = _load_serie()
    eventos = [
        e for e in detectar_todos_los_regimenes()
        if e.es_valido_para_backtesting and e.regimen.startswith(regimen)
    ]

    filas = []
    for ev in eventos:
        sub = df[(df["fecha"] >= ev.inicio) & (df["fecha"] <= ev.fin)]
        if sub.empty:
            continue

        fila_ini, fila_fin = sub.iloc[0], sub.iloc[-1]
        pila1_ini = fila_ini.get("pila_sag1")
        pila2_ini = fila_ini.get("pila_sag2")
        pila1_fin_obs = fila_fin.get("pila_sag1")
        if pd.isna(pila1_ini) or pd.isna(pila1_fin_obs):
            continue

        tph1_mean = float(sub["SAG1_tph"].dropna().mean()) if not sub["SAG1_tph"].dropna().empty else 0.0
        tph2_mean = float(sub["SAG2_tph"].dropna().mean()) if not sub["SAG2_tph"].dropna().empty else 0.0
        cv315_mean = float(sub["correa_315"].dropna().mean()) if not sub["correa_315"].dropna().empty else 0.0
        cv316_mean = float(sub["correa_316"].dropna().mean()) if not sub["correa_316"].dropna().empty else 0.0
        duracion_h = max(ev.duracion_min / 60.0, 0.1)

        sim = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini),
            pila_sag2_pct=float(pila2_ini) if not pd.isna(pila2_ini) else 50.0,
            rate_sag1_pct=tph1_mean / 1454.0 * 100.0,
            rate_sag2_pct=tph2_mean / 2516.0 * 100.0,
            sag1_activo=("mantenimiento_SAG1" != ev.regimen),
            sag2_activo=("mantenimiento_SAG2" != ev.regimen),
            duracion_t8_h=0.0,
            horizonte_horas=duracion_h,
            cv_mode="manual" if (cv315_mean > 0 or cv316_mean > 0) else "auto",
            cv315_manual_tph=cv315_mean,
            cv316_manual_tph=cv316_mean,
        )
        pile_sag1 = np.asarray(sim.get("pile_sag1") or [], dtype=float)
        pila1_fin_sim = float(pile_sag1[-1])

        filas.append({
            "regimen": ev.regimen,
            "error_abs": abs(pila1_fin_sim - float(pila1_fin_obs)),
            "error_signed": pila1_fin_sim - float(pila1_fin_obs),
            "cross_35": bool((pile_sag1 < BREAKPOINTS_SAG1["cross_35"]).any()),
            "cross_25": bool((pile_sag1 < BREAKPOINTS_SAG1["cross_25"]).any()),
            "cross_crit5": bool((pile_sag1 < BREAKPOINTS_SAG1["cross_crit5"]).any()),
            "pile_min_sim": float(pile_sag1.min()) if pile_sag1.size else None,
        })

    detalle = pd.DataFrame(filas)
    subtype_summary = (
        detalle.groupby("regimen")[["error_abs", "error_signed"]]
        .agg(["count", "mean", "median"])
        .to_dict()
        if not detalle.empty else {}
    )

    return {
        "regimen": regimen,
        "n": int(len(detalle)),
        "mae": float(detalle["error_abs"].mean()) if not detalle.empty else float("nan"),
        "bias": float(detalle["error_signed"].mean()) if not detalle.empty else float("nan"),
        "mediana_error": float(detalle["error_abs"].median()) if not detalle.empty else float("nan"),
        "detalle": detalle,
        "breakpoint_summary": _breakpoint_summary(detalle),
        "subtype_summary": subtype_summary,
    }


if __name__ == "__main__":
    for regimen in ("overflow", "mantenimiento", "inventario_critico", "alimentacion_restringida"):
        r = run_proxy_breakpoint_diagnosis(regimen)
        print(f"=== {regimen} ===")
        print(f"n={r['n']}   bias={r['bias']:.2f} pp   MAE={r['mae']:.2f} pp   mediana={r['mediana_error']:.2f} pp")
        for key, thr in BREAKPOINTS_SAG1.items():
            g = r["breakpoint_summary"][key]
            print(
                f"{key} (< {thr:.1f}%): "
                f"N no/si={g['no']['n']}/{g['si']['n']} | "
                f"media={g['no']['media']:.2f}/{g['si']['media']:.2f} pp | "
                f"mediana={g['no']['mediana']:.2f}/{g['si']['mediana']:.2f} pp"
            )
        detalle = r["detalle"]
        if not detalle.empty and detalle["regimen"].nunique() > 1:
            print("subtipos:")
            for subtype, grp in detalle.groupby("regimen"):
                print(
                    f"  {subtype}: "
                    f"n={len(grp)} | "
                    f"bias={grp['error_signed'].mean():.2f} pp | "
                    f"MAE={grp['error_abs'].mean():.2f} pp | "
                    f"mediana={grp['error_abs'].median():.2f} pp"
                )
        print()
