"""
validate_p_safe_calibration.py — Seccion 19 del programa de validacion
estadistica: compara la probabilidad de seguridad predicha por Monte
Carlo (p_safe, mismo modelo de ruido que adaptive_mc_eval en
optimizer_v2.py) contra la frecuencia real observada, sobre los 63
eventos t8_corta reales (los unicos con "safe/no safe" verificable
directamente desde la serie 5-min observada).

No reusa adaptive_mc_eval directamente (requiere un dict "cand" con
config de bolas que no se conoce por evento historico -- habria que
fabricarla). En su lugar reproduce el MISMO modelo de ruido (pila
+-2.5pp, feed factor Normal(1,0.12), T8 +-1h) sobre simulate_scenario_
cached directamente, con bolas_sag1/2="sin_bola" (default), igual que
usa historical_backtesting.py -- evita el confusor de una config de
bolas no observada.

Ejecutar: python 02_Analytics/Scripts/statistical_validation/validate_p_safe_calibration.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "05_Dashboard"))
_REPORTS_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "04_Reports", "Technical"))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))
sys.path.insert(0, _DASHBOARD)

from engine.simulator import simulate_scenario_cached  # noqa: E402
from engine.ode_model import CRITICAL_PCT, P90  # noqa: E402

N_MC = 150
SEED = 7
HOLDOUT_CUTOFF = pd.Timestamp("2026-04-30")


def _real_safe(grp: pd.DataFrame) -> bool:
    """True si la pila SAG1 real nunca toco/bajo el nivel critico durante
    el evento + inmediatamente despues (periodos DURANTE + POST)."""
    obs = grp[grp["periodo"].isin(["DURANTE", "POST"])]
    pila = obs["pila_sag1"].dropna()
    if pila.empty:
        return None
    return bool(pila.min() > CRITICAL_PCT["SAG1"])


def _p_safe_mc(pila1_ini: float, cv315_mean: float, cv316_mean: float,
               duracion_h: float, rate_sag1_pct: float, rng: np.random.Generator) -> float:
    """rate_sag1_pct: rate EFECTIVO realmente observado durante el evento
    (tph1_mean/P90*100, igual que historical_backtesting.py::_run_backtest_t8)
    -- NO 100% fijo. Usar 100% fijo (como hace adaptive_mc_eval en
    produccion, donde tiene sentido porque cv315_nom ya viene de un
    candidato del grid, no de un promedio historico crudo) sobre un feed
    ya restringido historicamente fuerza consumo agresivo contra feed
    bajo y confunde la validacion -- ver Calibracion_Monte_Carlo.md,
    seccion 'Intento de validacion de p_safe', primer intento descartado."""
    safe_count = 0
    for _ in range(N_MC):
        p1 = float(np.clip(rng.normal(pila1_ini, 2.5), 5, 95))
        ff = float(np.clip(rng.normal(1.0, 0.12), 0.55, 1.50))
        dt8 = float(np.clip(rng.normal(duracion_h, 1.0), 0.5, duracion_h + 3))
        c315v, c316v = cv315_mean * ff, cv316_mean * ff
        sim = simulate_scenario_cached(
            pila_sag1_pct=p1, pila_sag2_pct=50.0,
            rate_sag1_pct=rate_sag1_pct, rate_sag2_pct=100.0,
            duracion_t8_h=dt8, horizonte_horas=dt8,
            cv_mode="manual", cv315_manual_tph=c315v, cv316_manual_tph=c316v,
        )
        pile_traj = sim.get("pile_sag1") or [p1]
        if min(pile_traj) > CRITICAL_PCT["SAG1"]:
            safe_count += 1
    return safe_count / N_MC


def main() -> None:
    usar_corregido = "--corrected" in sys.argv
    windows_file = "advanced_t8_event_windows_corrected.parquet" if usar_corregido else "advanced_t8_event_windows.parquet"
    print(f"Fuente de datos: {windows_file}")

    ev = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_official_events.parquet"))
    w = pd.read_parquet(os.path.join(_CACHE_DIR, windows_file))
    ev = ev[ev["duracion_h"] <= 4].copy()
    w = w[w["evento_id"].isin(ev["evento_id"])].copy()

    rng = np.random.default_rng(SEED)
    filas = []
    for evento_id, grp in w.groupby("evento_id"):
        ini = grp[(grp["h_rel_inicio"] >= -0.05) & (grp["h_rel_inicio"] <= 0.10)]
        durante = grp[grp["periodo"] == "DURANTE"]
        if ini.empty or durante.empty:
            continue
        pila1_ini = ini["pila_sag1"].dropna()
        if pila1_ini.empty:
            continue
        real_safe = _real_safe(grp)
        if real_safe is None:
            continue

        cv315_mean = float(durante["correa_315"].dropna().mean()) if not durante["correa_315"].dropna().empty else 0.0
        cv316_mean = float(durante["correa_316"].dropna().mean()) if not durante["correa_316"].dropna().empty else 0.0
        tph1_mean = float(durante["SAG1_tph"].dropna().mean()) if not durante["SAG1_tph"].dropna().empty else 0.0
        rate_sag1_pct = min(100.0, max(10.0, tph1_mean / P90["SAG1"] * 100.0))
        duracion_h = float(grp["duracion_h"].iloc[0])
        event_start = grp["ini_oficial"].dropna().iloc[0] if "ini_oficial" in grp.columns and not grp["ini_oficial"].dropna().empty else None

        p_safe = _p_safe_mc(float(pila1_ini.iloc[0]), cv315_mean, cv316_mean, duracion_h, rate_sag1_pct, rng)
        split = "calibracion" if (event_start is not None and pd.Timestamp(event_start) <= HOLDOUT_CUTOFF) else "hold_out"
        filas.append({
            "evento_id": evento_id, "evento_inicio": str(event_start),
            "pila_ini_pct": float(pila1_ini.iloc[0]), "duracion_h": duracion_h,
            "p_safe_predicho": round(p_safe, 3), "real_safe": real_safe, "split": split,
        })

    df = pd.DataFrame(filas)
    print(f"N eventos evaluados: {len(df)}")
    df["real_safe_int"] = df["real_safe"].astype(int)
    brier = float(((df["p_safe_predicho"] - df["real_safe_int"]) ** 2).mean())
    print(f"Brier score global: {brier:.4f}  (0=perfecto, 0.25=no mejor que predecir 0.5 siempre)")

    # Reliability: bins de p_safe_predicho
    bins = [0, 0.5, 0.7, 0.85, 0.95, 1.001]
    labels = ["<0.50", "0.50-0.70", "0.70-0.85", "0.85-0.95", ">=0.95"]
    df["bin"] = pd.cut(df["p_safe_predicho"], bins=bins, labels=labels, right=False, include_lowest=True)
    tabla = df.groupby("bin", observed=True).agg(
        n=("real_safe_int", "size"),
        p_safe_predicho_medio=("p_safe_predicho", "mean"),
        frecuencia_real_segura=("real_safe_int", "mean"),
    ).round(3)
    print("\n=== Reliability (predicho vs. observado) ===")
    print(tabla.to_string())

    print("\n=== Por split ===")
    print(df.groupby("split").agg(
        n=("real_safe_int", "size"),
        p_safe_medio=("p_safe_predicho", "mean"),
        frecuencia_real=("real_safe_int", "mean"),
        brier=("real_safe_int", lambda s: float(((df.loc[s.index, "p_safe_predicho"] - s) ** 2).mean())),
    ).round(3).to_string())

    sufijo = "_corrected" if usar_corregido else ""
    out = os.path.join(_REPORTS_DIR, f"p_safe_calibration_validation{sufijo}.csv")
    df.to_csv(out, index=False, encoding="utf-8")
    tabla.to_csv(os.path.join(_REPORTS_DIR, f"p_safe_calibration_reliability{sufijo}.csv"), encoding="utf-8")
    print(f"\nGuardado: {out}")


if __name__ == "__main__":
    main()
