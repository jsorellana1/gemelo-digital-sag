"""
diagnose_drain_recalibration_holdout.py - Recalibracion experimental de
DRAIN_PCT_H con split temporal real y evaluacion hold-out.

Objetivos:
1. Recalibrar DRAIN_PCT_H usando solo ventanas fact_eventos_t8 hasta un
   cutoff temporal.
2. Medir t8_corta en calibracion vs hold-out antes y despues del cambio.
3. Responder si DRAIN_PCT_H realmente mueve el MAE de pila de run_backtest().
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", ".."))
_ROOT = os.path.normpath(os.path.join(_DASHBOARD, ".."))
if _DASHBOARD not in sys.path:
    sys.path.insert(0, _DASHBOARD)

CUTOFF_RECOMENDADO = pd.Timestamp("2026-04-30")

SERIES_5MIN_PATH = os.path.join(_ROOT, "01_Data", "Cache", "advanced_t8_historical_5min.parquet")
FACT_T8_PATH = os.path.join(_ROOT, "01_Data", "Processed", "fact_eventos_t8.parquet")
ADV_EVENTS_PATH = os.path.join(_ROOT, "01_Data", "Cache", "advanced_t8_official_events.parquet")
ADV_WINDOWS_PATH = os.path.join(_ROOT, "01_Data", "Cache", "advanced_t8_event_windows.parquet")


def _assign_bucket(hours: float) -> str:
    for name, (lo, hi) in {
        "Corta": (0, 2),
        "Media": (2, 6),
        "Larga": (6, 12),
        "Muy_larga": (12, 999),
    }.items():
        if lo < hours <= hi:
            return name
    return "Muy_larga"


def recalibrate_drain_pct(cutoff: pd.Timestamp = CUTOFF_RECOMENDADO) -> dict:
    """Replica la logica central del modelo de descarga robusto, pero
    restringiendo las ventanas de calibracion al cutoff temporal.

    Usa advanced_t8_historical_5min.parquet (serie ya normalizada a 5
    minutos y reutilizada por el backtesting) para evitar ambiguedades
    del Excel crudo, manteniendo las mismas senales fisicas:
    pila_sag1/2, SAG1_tph/2_tph y SAG1_operando/2_operando.
    """
    series = pd.read_parquet(SERIES_5MIN_PATH)
    series["fecha"] = pd.to_datetime(series["fecha"])

    vent = pd.read_parquet(FACT_T8_PATH)
    vent = vent[["ventana_id", "inicio", "fin", "duracion_h"]].drop_duplicates("ventana_id").copy()
    vent["inicio"] = pd.to_datetime(vent["inicio"])
    vent["fin"] = pd.to_datetime(vent["fin"]) + pd.Timedelta(days=1) - pd.Timedelta(minutes=5)
    vent = vent[vent["fin"].dt.normalize() <= cutoff]

    series["en_t8"] = False
    series["ventana_id"] = np.nan
    series["duracion_h"] = np.nan
    for _, v in vent.iterrows():
        mask = (series["fecha"] >= v["inicio"]) & (series["fecha"] <= v["fin"])
        series.loc[mask, "en_t8"] = True
        series.loc[mask, "ventana_id"] = v["ventana_id"]
        series.loc[mask, "duracion_h"] = v["duracion_h"]

    df_t8 = series[series["en_t8"]].sort_values("fecha").copy()
    records = []
    for sag in ("SAG1", "SAG2"):
        col_pila = "pila_sag1" if sag == "SAG1" else "pila_sag2"
        col_tph = f"{sag}_tph"
        col_op = f"{sag}_operando"
        for vid in df_t8["ventana_id"].dropna().unique():
            sub = df_t8[df_t8["ventana_id"] == vid].copy()
            if len(sub) < 3:
                continue
            dur_h = float(sub["duracion_h"].iloc[0])
            delta_nivel = float(sub[col_pila].iloc[0] - sub[col_pila].iloc[-1])
            rates = sub[col_pila].diff().div(5 / 60).dropna()
            rates_neg = rates[rates < -0.01]
            tasa_inst = -float(rates_neg.mean()) if len(rates_neg) > 0 else np.nan
            tasa_bruta = delta_nivel / dur_h if dur_h > 0 else np.nan
            records.append({
                "ventana_id": int(vid),
                "sag": sag,
                "duracion_h": dur_h,
                "bucket": _assign_bucket(dur_h),
                "tasa_descarga": tasa_inst if pd.notna(tasa_inst) else tasa_bruta,
                "rate_sag_mean": float(sub.loc[sub[col_op], col_tph].mean()) if sub[col_op].any() else np.nan,
            })

    calc = pd.DataFrame(records)
    calc["tasa_valida"] = (calc["tasa_descarga"] > 0) & calc["tasa_descarga"].notna()
    rates = {}
    for sag in ("SAG1", "SAG2"):
        sub = calc[(calc["sag"] == sag) & calc["tasa_valida"]]
        rates[sag] = {
            "drain_pct_h": float(sub["tasa_descarga"].mean()),
            "n_valid": int(len(sub)),
            "std": float(sub["tasa_descarga"].std()) if len(sub) > 1 else 0.0,
        }
    return {
        "cutoff": cutoff.date().isoformat(),
        "fact_windows_n": int(vent["ventana_id"].nunique()),
        "rates": rates,
        "detalle": calc,
    }


def _run_t8_corta_subset(event_ids: set[str]) -> dict:
    from engine import ode_model
    from engine.simulator import simulate_scenario_cached

    adv_windows = pd.read_parquet(ADV_WINDOWS_PATH)
    ww = adv_windows[adv_windows["evento_id"].isin(event_ids)]

    err, signed, err_tcrit, used_ids = [], [], [], []
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

        pred1 = float(sim["pile_sag1"][-1])
        err.append(abs(pred1 - pila1_fin_obs))
        signed.append(pred1 - pila1_fin_obs)
        used_ids.append(evento_id)

        obs = grp[grp["h_rel_inicio"] >= -0.05].sort_values("h_rel_inicio")
        t_obs = _tiempo_hasta_critico(obs["pila_sag1"].tolist(), obs["h_rel_inicio"].tolist(), ode_model)
        t_sim = _tiempo_hasta_critico(sim.get("pile_sag1") or [], sim.get("time") or [], ode_model)
        if t_obs is not None and t_sim is not None:
            err_tcrit.append(abs(t_sim - t_obs))

    return {
        "n": int(len(err)),
        "mae": float(np.mean(err)) if err else None,
        "bias": float(np.mean(signed)) if signed else None,
        "std": float(np.std(signed)) if signed else None,
        "tcrit_mae": float(np.mean(err_tcrit)) if err_tcrit else None,
        "n_tcrit": int(len(err_tcrit)),
        "used_ids": used_ids,
    }


def _tiempo_hasta_critico(pila_vals: list[float], tiempos_h: list[float], ode_model_module) -> float | None:
    for pila, t in zip(pila_vals, tiempos_h):
        if pila is None or (isinstance(pila, float) and np.isnan(pila)):
            continue
        if ode_model_module.compute_autonomia(float(pila), "SAG1") < 1.0:
            return float(t)
    return None


def compare_baseline_vs_recalibrated(cutoff: pd.Timestamp = CUTOFF_RECOMENDADO) -> dict:
    from engine import historical_backtesting as hb
    from engine import ode_model
    from engine.scenario_cache import simulation_cache

    recal = recalibrate_drain_pct(cutoff)
    new_drain = {asset: v["drain_pct_h"] for asset, v in recal["rates"].items()}

    adv = pd.read_parquet(ADV_EVENTS_PATH)
    adv["fecha"] = pd.to_datetime(adv["fecha"]).dt.normalize()
    ids_cal = set(adv.loc[(adv["fecha"] <= cutoff) & (adv["duracion_h"] <= 4), "evento_id"])
    ids_hold = set(adv.loc[(adv["fecha"] > cutoff) & (adv["duracion_h"] <= 4), "evento_id"])

    baseline_cal = _run_t8_corta_subset(ids_cal)
    baseline_hold = _run_t8_corta_subset(ids_hold)

    old_drain = dict(ode_model.DRAIN_PCT_H)
    try:
        ode_model.DRAIN_PCT_H.update(new_drain)
        simulation_cache.clear()
        hb.run_backtest.cache_clear()
        hb.check_prerequisito_0.cache_clear()
        recal_cal = _run_t8_corta_subset(ids_cal)
        recal_hold = _run_t8_corta_subset(ids_hold)
    finally:
        ode_model.DRAIN_PCT_H.clear()
        ode_model.DRAIN_PCT_H.update(old_drain)
        simulation_cache.clear()
        hb.run_backtest.cache_clear()
        hb.check_prerequisito_0.cache_clear()

    return {
        "cutoff": cutoff.date().isoformat(),
        "new_drain": new_drain,
        "cal_ids_n": int(len(ids_cal)),
        "hold_ids_n": int(len(ids_hold)),
        "baseline_cal": baseline_cal,
        "baseline_hold": baseline_hold,
        "recal_cal": recal_cal,
        "recal_hold": recal_hold,
        "missing_hold_ids": sorted(list(ids_hold - set(baseline_hold["used_ids"]))),
    }


if __name__ == "__main__":
    r = compare_baseline_vs_recalibrated()
    print("=== Recalibracion experimental DRAIN_PCT_H ===")
    print(f"cutoff={r['cutoff']} | new_drain={r['new_drain']}")
    print(f"t8_corta cal/hold ids={r['cal_ids_n']}/{r['hold_ids_n']}")
    print("baseline_cal", {k: v for k, v in r["baseline_cal"].items() if k != "used_ids"})
    print("baseline_hold", {k: v for k, v in r["baseline_hold"].items() if k != "used_ids"})
    print("recal_cal", {k: v for k, v in r["recal_cal"].items() if k != "used_ids"})
    print("recal_hold", {k: v for k, v in r["recal_hold"].items() if k != "used_ids"})
    print("missing_hold_ids", r["missing_hold_ids"])
