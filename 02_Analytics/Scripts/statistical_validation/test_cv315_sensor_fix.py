"""
test_cv315_sensor_fix.py — Prueba si reconstruir cv315 (sensor roto
confirmado desde 2026-04-30, ver 04_Reports/Technical/Diagnostico_
Causa_Deriva_Temporal_PAM.md) con la proporcion historica cv315/cv316
reduce el MAE de fidelidad de t8_corta en el hold-out.

No modifica ningun dato fuente ni codigo de produccion -- es un
experimento de diagnostico. La proporcion usada (mediana historica,
periodo <2026-04-30 con ambas correas activas) es una reconstruccion
aproximada, no una correccion definitiva -- ver seccion "Proximo paso"
del reporte para mejoras pendientes (proporcion condicionada por
regimen/contexto en vez de un valor fijo).

Ejecutar: python 02_Analytics/Scripts/statistical_validation/test_cv315_sensor_fix.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "05_Dashboard"))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))
sys.path.insert(0, _DASHBOARD)

from engine.simulator import simulate_scenario_cached  # noqa: E402
from engine.ode_model import P90  # noqa: E402

HOLDOUT_CUTOFF = pd.Timestamp("2026-04-30")
RATIO_CV315_HISTORICO = 0.277  # mediana cv315/(cv315+cv316), periodo <2026-04-30, ambas correas activas
RATIO_MULT = RATIO_CV315_HISTORICO / (1 - RATIO_CV315_HISTORICO)  # cv315 = cv316 * RATIO_MULT


def main() -> None:
    ev = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_official_events.parquet"))
    w = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_event_windows.parquet"))
    ev = ev[ev["duracion_h"] <= 4].copy()
    w = w[w["evento_id"].isin(ev["evento_id"])].copy()

    resultados = []
    for evento_id, grp in w.groupby("evento_id"):
        ini = grp[(grp["h_rel_inicio"] >= -0.05) & (grp["h_rel_inicio"] <= 0.10)]
        durante = grp[grp["periodo"] == "DURANTE"]
        fin = grp[grp["periodo"] == "POST"]
        if ini.empty or durante.empty or fin.empty:
            continue
        pila1_ini = ini["pila_sag1"].dropna()
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
        event_start = grp["ini_oficial"].dropna().iloc[0] if "ini_oficial" in grp.columns and not grp["ini_oficial"].dropna().empty else None
        if event_start is None:
            continue
        split = "calibracion" if pd.Timestamp(event_start) <= HOLDOUT_CUTOFF else "hold_out"

        sim_base = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini.iloc[0]), pila_sag2_pct=50.0,
            rate_sag1_pct=tph1_mean / P90["SAG1"] * 100.0, rate_sag2_pct=tph2_mean / P90["SAG2"] * 100.0,
            duracion_t8_h=duracion_h, horizonte_horas=duracion_h,
            cv_mode="manual", cv315_manual_tph=cv315_mean, cv316_manual_tph=cv316_mean,
        )
        err_base = sim_base["pile_sag1"][-1] - pila1_fin_obs

        cv315_fix = cv315_mean
        if split == "hold_out" and cv315_mean < 1.0 and cv316_mean > 50.0:
            cv315_fix = cv316_mean * RATIO_MULT

        sim_fix = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini.iloc[0]), pila_sag2_pct=50.0,
            rate_sag1_pct=tph1_mean / P90["SAG1"] * 100.0, rate_sag2_pct=tph2_mean / P90["SAG2"] * 100.0,
            duracion_t8_h=duracion_h, horizonte_horas=duracion_h,
            cv_mode="manual", cv315_manual_tph=cv315_fix, cv316_manual_tph=cv316_mean,
        )
        err_fix = sim_fix["pile_sag1"][-1] - pila1_fin_obs

        resultados.append({
            "evento_id": evento_id, "split": split,
            "cv315_orig": cv315_mean, "cv315_fix": cv315_fix,
            "err_base": err_base, "err_fix": err_fix,
        })

    df = pd.DataFrame(resultados)
    for split in ("calibracion", "hold_out"):
        sub = df[df["split"] == split]
        print(f"=== {split} (N={len(sub)}) ===")
        print(f"  MAE base: {sub['err_base'].abs().mean():.2f}pp   bias: {sub['err_base'].mean():+.2f}pp")
        print(f"  MAE fix:  {sub['err_fix'].abs().mean():.2f}pp   bias: {sub['err_fix'].mean():+.2f}pp")
        print()


if __name__ == "__main__":
    main()
