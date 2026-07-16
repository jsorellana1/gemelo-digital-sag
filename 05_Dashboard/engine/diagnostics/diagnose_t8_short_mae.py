"""
diagnose_t8_short_mae.py — Diagnostico del MAE observado en el backtesting
de t8_corta (Prompt "CIERRE DE BRECHAS POST ROUTER v2", TAREA 1,
2026-07-07).

Calcula error CON SIGNO (no solo abs) por evento, bias, std y MAE, y
clasifica el tipo de error segun el arbol de decision del prompt. Se
ejecuta ANTES de tocar cualquier otra brecha — resultado obligatorio en
04_Reports/Technical/DIAGNOSTICO_MAE_t8_corta.md.
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

_CACHE_DIR = os.path.normpath(os.path.join(_DASHBOARD, "..", "01_Data", "Cache"))

BREAKPOINTS_SAG1 = {
    "cross_35": 35.0,
    "cross_25": 25.0,
    "cross_crit5": 20.0,
}


def _post_value_at_event_end(fin_grp: pd.DataFrame, col: str) -> float | None:
    """Retorna el valor de `col` en la fila de POST mas cercana a
    h_rel_fin=0 (INMEDIATAMENTE despues de terminar el evento) — NO el
    ultimo registro de la ventana POST, que puede estar hasta 48h despues
    (ver hallazgo de causa raiz mas abajo)."""
    fin_grp = fin_grp.dropna(subset=[col])
    if fin_grp.empty:
        return None
    idx = (fin_grp["h_rel_fin"] - 0.0).abs().idxmin()
    return float(fin_grp.loc[idx, col])


def _last_post_value(fin_grp: pd.DataFrame, col: str) -> float | None:
    """Metodo ORIGINAL (con bug) usado en historical_backtesting.py v1:
    toma el ultimo registro de la ventana POST (hasta 48h despues del
    evento). Se conserva aqui solo para comparar y documentar la causa
    raiz del MAE alto."""
    s = fin_grp[col].dropna()
    return float(s.iloc[-1]) if not s.empty else None


def _breakpoint_summary(df: pd.DataFrame) -> dict[str, dict[str, dict[str, float | int]]]:
    out: dict[str, dict[str, dict[str, float | int]]] = {}
    for col in BREAKPOINTS_SAG1:
        grupos: dict[str, dict[str, float | int]] = {}
        for crossed in (False, True):
            sub = df.loc[df[col] == crossed, "error_abs_correcto"].dropna()
            grupos["si" if crossed else "no"] = {
                "n": int(sub.size),
                "media": float(sub.mean()) if sub.size else float("nan"),
                "mediana": float(sub.median()) if sub.size else float("nan"),
            }
        out[col] = grupos
    return out


def _load_t8_corta_windows() -> pd.DataFrame:
    ev = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_official_events.parquet"))
    w = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_event_windows.parquet"))
    ids_corta = ev.loc[ev["duracion_h"] <= 4, "evento_id"]
    return w[w["evento_id"].isin(ids_corta)]


def run_diagnosis() -> dict:
    from engine.simulator import simulate_scenario_cached

    w_corta = _load_t8_corta_windows()

    filas = []
    for evento_id, grp in w_corta.groupby("evento_id"):
        ini = grp[(grp["h_rel_inicio"] >= -0.05) & (grp["h_rel_inicio"] <= 0.10)]
        durante = grp[grp["periodo"] == "DURANTE"]
        post = grp[grp["periodo"] == "POST"]
        if ini.empty or durante.empty or post.empty:
            continue

        pila1_ini_s = ini["pila_sag1"].dropna()
        pila2_ini_s = ini["pila_sag2"].dropna()
        if pila1_ini_s.empty:
            continue

        pila1_fin_obs_correcto = _post_value_at_event_end(post, "pila_sag1")
        pila1_fin_obs_bug = _last_post_value(post, "pila_sag1")
        if pila1_fin_obs_correcto is None:
            continue

        tph1_mean = float(durante["SAG1_tph"].dropna().mean()) if not durante["SAG1_tph"].dropna().empty else 0.0
        tph2_mean = float(durante["SAG2_tph"].dropna().mean()) if not durante["SAG2_tph"].dropna().empty else 0.0
        duracion_h = float(grp["duracion_h"].iloc[0])

        sim = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini_s.iloc[0]),
            pila_sag2_pct=float(pila2_ini_s.iloc[0]) if not pila2_ini_s.empty else 50.0,
            rate_sag1_pct=tph1_mean / 1454.0 * 100.0,
            rate_sag2_pct=tph2_mean / 2516.0 * 100.0,
            duracion_t8_h=duracion_h,
            horizonte_horas=duracion_h,
        )
        pila1_fin_sim = sim["pile_sag1"][-1]

        filas.append({
            "evento_id": evento_id,
            "duracion_h": duracion_h,
            "pila1_ini": float(pila1_ini_s.iloc[0]),
            "tph1_mean_observado": tph1_mean,
            "pila1_fin_pred": pila1_fin_sim,
            "pila1_fin_obs_correcto": pila1_fin_obs_correcto,
            "pila1_fin_obs_bug_metodo_v1": pila1_fin_obs_bug,
            "error_con_signo_correcto": pila1_fin_sim - pila1_fin_obs_correcto,
            "error_con_signo_bug_v1": (pila1_fin_sim - pila1_fin_obs_bug) if pila1_fin_obs_bug is not None else None,
        })

    df = pd.DataFrame(filas)

    errores_correctos = df["error_con_signo_correcto"].dropna().values
    errores_bug_v1 = df["error_con_signo_bug_v1"].dropna().values

    def _stats(arr):
        arr = np.asarray(arr, dtype=float)
        return {
            "n": len(arr),
            "bias": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "mae": float(np.mean(np.abs(arr))),
        }

    stats_correcto = _stats(errores_correctos)
    stats_bug_v1 = _stats(errores_bug_v1)

    return {
        "df": df,
        "stats_metodo_corregido": stats_correcto,
        "stats_metodo_v1_bug": stats_bug_v1,
    }


def run_breakpoint_diagnosis_manual_feed() -> dict:
    from engine.simulator import simulate_scenario_cached

    filas = []
    w_corta = _load_t8_corta_windows()
    for evento_id, grp in w_corta.groupby("evento_id"):
        ini = grp[(grp["h_rel_inicio"] >= -0.05) & (grp["h_rel_inicio"] <= 0.10)]
        durante = grp[grp["periodo"] == "DURANTE"]
        post = grp[grp["periodo"] == "POST"]
        if ini.empty or durante.empty or post.empty:
            continue

        pila1_ini_s = ini["pila_sag1"].dropna()
        pila2_ini_s = ini["pila_sag2"].dropna()
        if pila1_ini_s.empty:
            continue

        pila1_fin_obs = _post_value_at_event_end(post, "pila_sag1")
        if pila1_fin_obs is None:
            continue

        tph1_mean = float(durante["SAG1_tph"].dropna().mean()) if not durante["SAG1_tph"].dropna().empty else 0.0
        tph2_mean = float(durante["SAG2_tph"].dropna().mean()) if not durante["SAG2_tph"].dropna().empty else 0.0
        cv315_mean = float(durante["correa_315"].dropna().mean()) if not durante["correa_315"].dropna().empty else 0.0
        cv316_mean = float(durante["correa_316"].dropna().mean()) if not durante["correa_316"].dropna().empty else 0.0
        duracion_h = float(grp["duracion_h"].iloc[0])

        sim = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini_s.iloc[0]),
            pila_sag2_pct=float(pila2_ini_s.iloc[0]) if not pila2_ini_s.empty else 50.0,
            rate_sag1_pct=tph1_mean / 1454.0 * 100.0,
            rate_sag2_pct=tph2_mean / 2516.0 * 100.0,
            duracion_t8_h=duracion_h,
            horizonte_horas=duracion_h,
            cv_mode="manual" if (cv315_mean > 0 or cv316_mean > 0) else "auto",
            cv315_manual_tph=cv315_mean,
            cv316_manual_tph=cv316_mean,
        )
        pile_sag1 = np.asarray(sim.get("pile_sag1") or [], dtype=float)
        pila1_fin_sim = float(pile_sag1[-1])

        filas.append({
            "evento_id": evento_id,
            "error_con_signo": pila1_fin_sim - pila1_fin_obs,
            "error_abs": abs(pila1_fin_sim - pila1_fin_obs),
            "cross_35": bool((pile_sag1 < BREAKPOINTS_SAG1["cross_35"]).any()),
            "cross_25": bool((pile_sag1 < BREAKPOINTS_SAG1["cross_25"]).any()),
            "cross_crit5": bool((pile_sag1 < BREAKPOINTS_SAG1["cross_crit5"]).any()),
            "pile_min_sim": float(pile_sag1.min()) if pile_sag1.size else None,
        })

    df = pd.DataFrame(filas)
    return {
        "df": df,
        "n": int(len(df)),
        "mae": float(df["error_abs"].mean()) if not df.empty else float("nan"),
        "bias": float(df["error_con_signo"].mean()) if not df.empty else float("nan"),
        "breakpoint_summary": _breakpoint_summary(df.rename(columns={"error_abs": "error_abs_correcto"})),
    }


def _clasificar(bias: float, std: float, mae: float) -> str:
    if abs(bias) > 15.0:
        return "ERROR_ESTRUCTURAL"
    if abs(bias) <= 15.0 and std > 20.0:
        return "VARIABILIDAD_INTRINSECA_ALTA"
    return "REVISAR_ALINEACION_TEMPORAL"


if __name__ == "__main__":
    r = run_diagnosis()
    print("=== Metodo v1 (bug: usa ultimo registro POST, hasta 48h despues) ===")
    print(r["stats_metodo_v1_bug"])
    print()
    print("=== Metodo corregido (usa registro POST mas cercano a h_rel_fin=0) ===")
    print(r["stats_metodo_corregido"])
    s = r["stats_metodo_corregido"]
    print()
    print("Clasificacion:", _clasificar(s["bias"], s["std"], s["mae"]))
    print()
    print("=== Error absoluto por cruce de breakpoints de _pile_feedback_factor (metodo actual con CV manual) ===")
    br = run_breakpoint_diagnosis_manual_feed()
    print(f"n={br['n']}   bias={br['bias']:.2f} pp   MAE={br['mae']:.2f} pp")
    for key, thr in BREAKPOINTS_SAG1.items():
        g = br["breakpoint_summary"][key]
        print(
            f"{key} (< {thr:.1f}%): "
            f"N no/si={g['no']['n']}/{g['si']['n']} | "
            f"media={g['no']['media']:.2f}/{g['si']['media']:.2f} pp | "
            f"mediana={g['no']['mediana']:.2f}/{g['si']['mediana']:.2f} pp"
        )
