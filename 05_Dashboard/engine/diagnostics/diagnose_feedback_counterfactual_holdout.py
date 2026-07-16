"""
diagnose_feedback_counterfactual_holdout.py - Sensibilidad out-of-sample
de _pile_feedback_factor sobre t8_corta.

Objetivos:
1. Reusar el split temporal real propuesto en Fase 5 (cutoff 2026-04-30).
2. Correr t8_corta en calibracion y hold-out con versiones escaladas del
   feedback de pila baja, sin tocar codigo productivo.
3. Medir si relajar o desactivar _pile_feedback_factor mejora o empeora
   el MAE de pila, y si el efecto se concentra en los eventos que
   baseline cruza bajo 35%.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", ".."))
_ROOT = os.path.normpath(os.path.join(_DASHBOARD, ".."))
if _DASHBOARD not in sys.path:
    sys.path.insert(0, _DASHBOARD)

CUTOFF_RECOMENDADO = pd.Timestamp("2026-04-30")
ADV_EVENTS_PATH = os.path.join(_ROOT, "01_Data", "Cache", "advanced_t8_official_events.parquet")
ADV_WINDOWS_PATH = os.path.join(_ROOT, "01_Data", "Cache", "advanced_t8_event_windows.parquet")

SCALES = {
    "baseline_100": 1.00,
    "feedback_075": 0.75,
    "feedback_050": 0.50,
    "feedback_025": 0.25,
    "feedback_000": 0.00,
}


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "nan"


def _tiempo_hasta_critico(
    pila_vals: list[float],
    tiempos_h: list[float],
    compute_autonomia_fn: Callable[[float, str], float],
) -> float | None:
    for pila, t in zip(pila_vals, tiempos_h):
        if pila is None or (isinstance(pila, float) and np.isnan(pila)):
            continue
        if compute_autonomia_fn(float(pila), "SAG1") < 1.0:
            return float(t)
    return None


def _scaled_feedback_factory(
    original_feedback_fn: Callable[[float, str], float],
    scale: float,
) -> Callable[[float, str], float]:
    def _scaled_feedback(pile_pct: float, asset: str) -> float:
        base = float(original_feedback_fn(pile_pct, asset))
        return 1.0 - scale * (1.0 - base)

    return _scaled_feedback


def _load_split_ids(cutoff: pd.Timestamp = CUTOFF_RECOMENDADO) -> tuple[set[str], set[str]]:
    adv = pd.read_parquet(ADV_EVENTS_PATH)
    adv["fecha"] = pd.to_datetime(adv["fecha"]).dt.normalize()
    ids_cal = set(adv.loc[(adv["fecha"] <= cutoff) & (adv["duracion_h"] <= 4), "evento_id"])
    ids_hold = set(adv.loc[(adv["fecha"] > cutoff) & (adv["duracion_h"] <= 4), "evento_id"])
    return ids_cal, ids_hold


def _run_t8_corta_subset(event_ids: set[str], compute_autonomia_fn) -> pd.DataFrame:
    from engine.simulator import simulate_scenario_cached

    adv_windows = pd.read_parquet(ADV_WINDOWS_PATH)
    ww = adv_windows[adv_windows["evento_id"].isin(event_ids)]

    filas = []
    for evento_id, grp in ww.groupby("evento_id"):
        ini = grp[(grp["h_rel_inicio"] >= -0.05) & (grp["h_rel_inicio"] <= 0.10)]
        durante = grp[grp["periodo"] == "DURANTE"]
        fin = grp[grp["periodo"] == "POST"]
        if ini.empty or durante.empty or fin.empty:
            continue

        pila1_ini = ini["pila_sag1"].dropna()
        pila2_ini = ini["pila_sag2"].dropna()
        fin1 = fin.dropna(subset=["pila_sag1"])
        if pila1_ini.empty or fin1.empty:
            continue

        idx1 = (fin1["h_rel_fin"] - 0.0).abs().idxmin()
        pila1_fin_obs = float(fin1.loc[idx1, "pila_sag1"])
        tph1_mean = float(durante["SAG1_tph"].dropna().mean()) if not durante["SAG1_tph"].dropna().empty else 0.0
        tph2_mean = float(durante["SAG2_tph"].dropna().mean()) if not durante["SAG2_tph"].dropna().empty else 0.0
        cv315_mean = float(durante["correa_315"].dropna().mean()) if not durante["correa_315"].dropna().empty else 0.0
        cv316_mean = float(durante["correa_316"].dropna().mean()) if not durante["correa_316"].dropna().empty else 0.0
        duracion_h = float(grp["duracion_h"].iloc[0])

        sim = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini.iloc[0]),
            pila_sag2_pct=float(pila2_ini.iloc[0]) if not pila2_ini.empty else 50.0,
            rate_sag1_pct=tph1_mean / 1454.0 * 100.0,
            rate_sag2_pct=tph2_mean / 2516.0 * 100.0,
            duracion_t8_h=duracion_h,
            horizonte_horas=duracion_h,
            cv_mode="manual" if (cv315_mean > 0 or cv316_mean > 0) else "auto",
            cv315_manual_tph=cv315_mean,
            cv316_manual_tph=cv316_mean,
        )

        pile_sag1 = np.asarray(sim.get("pile_sag1") or [], dtype=float)
        pred1 = float(pile_sag1[-1])
        signed = pred1 - pila1_fin_obs

        obs = grp[grp["h_rel_inicio"] >= -0.05].sort_values("h_rel_inicio")
        t_obs = _tiempo_hasta_critico(
            obs["pila_sag1"].tolist(),
            obs["h_rel_inicio"].tolist(),
            compute_autonomia_fn,
        )
        t_sim = _tiempo_hasta_critico(
            sim.get("pile_sag1") or [],
            sim.get("time") or [],
            compute_autonomia_fn,
        )

        filas.append({
            "evento_id": evento_id,
            "error_abs": abs(signed),
            "error_signed": signed,
            "tcrit_error": abs(t_sim - t_obs) if (t_obs is not None and t_sim is not None) else np.nan,
            "cross_35": bool((pile_sag1 < 35.0).any()),
            "cross_25": bool((pile_sag1 < 25.0).any()),
            "cross_20": bool((pile_sag1 < 20.0).any()),
            "pile_min_sim": float(pile_sag1.min()) if pile_sag1.size else np.nan,
        })

    return pd.DataFrame(filas)


def _summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "n": 0,
            "mae": None,
            "bias": None,
            "std": None,
            "tcrit_mae": None,
            "n_tcrit": 0,
        }

    signed = df["error_signed"].dropna()
    tcrit = df["tcrit_error"].dropna()
    return {
        "n": int(len(df)),
        "mae": float(df["error_abs"].mean()),
        "bias": float(signed.mean()) if not signed.empty else None,
        "std": float(signed.std(ddof=0)) if not signed.empty else None,
        "tcrit_mae": float(tcrit.mean()) if not tcrit.empty else None,
        "n_tcrit": int(len(tcrit)),
    }


def _run_variant(scale: float, ids_cal: set[str], ids_hold: set[str]) -> dict:
    from engine import historical_backtesting as hb
    from engine import ode_model
    from engine.scenario_cache import simulation_cache

    original_feedback_fn = ode_model._pile_feedback_factor
    patched_feedback_fn = _scaled_feedback_factory(original_feedback_fn, scale)
    try:
        ode_model._pile_feedback_factor = patched_feedback_fn
        simulation_cache.clear()
        hb.run_backtest.cache_clear()
        hb.check_prerequisito_0.cache_clear()
        cal_df = _run_t8_corta_subset(ids_cal, ode_model.compute_autonomia)
        simulation_cache.clear()
        hb.run_backtest.cache_clear()
        hb.check_prerequisito_0.cache_clear()
        hold_df = _run_t8_corta_subset(ids_hold, ode_model.compute_autonomia)
    finally:
        ode_model._pile_feedback_factor = original_feedback_fn
        simulation_cache.clear()
        hb.run_backtest.cache_clear()
        hb.check_prerequisito_0.cache_clear()

    return {
        "scale": scale,
        "cal_df": cal_df,
        "hold_df": hold_df,
        "cal": _summarize(cal_df),
        "hold": _summarize(hold_df),
    }


def _subgroup_curve(
    baseline_df: pd.DataFrame,
    variant_map: dict[str, dict],
    subset: str,
    cross_col: str = "cross_35",
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    out: dict[str, dict[str, dict[str, float | int | None]]] = {}
    base = baseline_df[["evento_id", cross_col]].copy()
    for crossed in (False, True):
        label = "si" if crossed else "no"
        ids = set(base.loc[base[cross_col] == crossed, "evento_id"])
        curva: dict[str, dict[str, float | int | None]] = {}
        for variant_name, payload in variant_map.items():
            df = payload[f"{subset}_df"]
            sub = df[df["evento_id"].isin(ids)]
            curva[variant_name] = _summarize(sub)
        out[label] = curva
    return out


def compare_feedback_variants(cutoff: pd.Timestamp = CUTOFF_RECOMENDADO) -> dict:
    ids_cal, ids_hold = _load_split_ids(cutoff)

    variant_map = {
        name: _run_variant(scale, ids_cal, ids_hold)
        for name, scale in SCALES.items()
    }

    baseline_cal_df = variant_map["baseline_100"]["cal_df"]
    baseline_hold_df = variant_map["baseline_100"]["hold_df"]

    return {
        "cutoff": cutoff.date().isoformat(),
        "cal_ids_n": int(len(ids_cal)),
        "hold_ids_n": int(len(ids_hold)),
        "variants": {
            name: {
                "scale": payload["scale"],
                "cal": payload["cal"],
                "hold": payload["hold"],
            }
            for name, payload in variant_map.items()
        },
        "cal_curve_by_baseline_cross35": _subgroup_curve(baseline_cal_df, variant_map, "cal", "cross_35"),
        "hold_curve_by_baseline_cross35": _subgroup_curve(baseline_hold_df, variant_map, "hold", "cross_35"),
        "cal_curve_by_baseline_cross25": _subgroup_curve(baseline_cal_df, variant_map, "cal", "cross_25"),
        "hold_curve_by_baseline_cross25": _subgroup_curve(baseline_hold_df, variant_map, "hold", "cross_25"),
        "cal_curve_by_baseline_cross20": _subgroup_curve(baseline_cal_df, variant_map, "cal", "cross_20"),
        "hold_curve_by_baseline_cross20": _subgroup_curve(baseline_hold_df, variant_map, "hold", "cross_20"),
        "missing_hold_ids_baseline": sorted(list(ids_hold - set(baseline_hold_df["evento_id"]))),
    }


if __name__ == "__main__":
    r = compare_feedback_variants()
    print("=== Sensibilidad hold-out de _pile_feedback_factor ===")
    print(f"cutoff={r['cutoff']} | t8_corta cal/hold ids={r['cal_ids_n']}/{r['hold_ids_n']}")
    print()
    print("== Curva global ==")
    for variant_name, payload in r["variants"].items():
        cal = payload["cal"]
        hold = payload["hold"]
        print(
            f"{variant_name} scale={payload['scale']:.2f} | "
            f"cal n={cal['n']} mae={_fmt(cal['mae'])} "
            f"bias={_fmt(cal['bias'])} tcrit={_fmt(cal['tcrit_mae'])}"
        )
        print(
            f"                         hold n={hold['n']} mae={_fmt(hold['mae'])} "
            f"bias={_fmt(hold['bias'])} tcrit={_fmt(hold['tcrit_mae'])}"
        )
    print()
    print("== Hold-out por cruce baseline <35% ==")
    for crossed, curva in r["hold_curve_by_baseline_cross35"].items():
        print(f"baseline_cross_35={crossed}")
        for variant_name, stats in curva.items():
            print(
                f"  {variant_name}: n={stats['n']} mae={_fmt(stats['mae'])} "
                f"bias={_fmt(stats['bias'])} tcrit={_fmt(stats['tcrit_mae'])}"
            )
    print()
    print("== Hold-out por cruce baseline <25% ==")
    for crossed, curva in r["hold_curve_by_baseline_cross25"].items():
        print(f"baseline_cross_25={crossed}")
        for variant_name, stats in curva.items():
            print(
                f"  {variant_name}: n={stats['n']} mae={_fmt(stats['mae'])} "
                f"bias={_fmt(stats['bias'])} tcrit={_fmt(stats['tcrit_mae'])}"
            )
    print()
    print("== Hold-out por cruce baseline <20% ==")
    for crossed, curva in r["hold_curve_by_baseline_cross20"].items():
        print(f"baseline_cross_20={crossed}")
        for variant_name, stats in curva.items():
            print(
                f"  {variant_name}: n={stats['n']} mae={_fmt(stats['mae'])} "
                f"bias={_fmt(stats['bias'])} tcrit={_fmt(stats['tcrit_mae'])}"
            )
    print()
    print("missing_hold_ids_baseline", r["missing_hold_ids_baseline"])
