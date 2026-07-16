"""
investigate_multicell_evidence.py - Evidencia fisica, estadistica y
operacional para decidir si migrar desde pila agregada a multicelda.

No modifica el simulador productivo. Solo compara:
- evidencia estadistica en `pilas_rendimientos.xlsx`;
- evidencia operacional via hold-out de backtesting;
- recomendacion de migracion por activo.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", ".."))
_ROOT = os.path.normpath(os.path.join(_DASHBOARD, ".."))
if _DASHBOARD not in sys.path:
    sys.path.insert(0, _DASHBOARD)

from engine.historical_backtesting import run_backtest_variant  # noqa: E402


CUTOFF_HOLDOUT = pd.Timestamp("2026-04-30 23:59:59")
RAW_XLSX = Path(_ROOT) / "01_Data" / "Raw" / "Tonelajes_pila" / "pilas_rendimientos.xlsx"
OUTPUT_DIR = Path(_ROOT) / "04_Reports" / "Technical"
LINEAR_CSV = OUTPUT_DIR / "20260715_multicell_linear_models.csv"
LOGISTIC_CSV = OUTPUT_DIR / "20260715_multicell_logistic_models.csv"
BACKTEST_CSV = OUTPUT_DIR / "20260715_multicell_holdout_deltas.csv"


def _gini(vals: np.ndarray) -> float:
    x = np.asarray(vals, dtype=float)
    x = x[np.isfinite(x)]
    x = np.clip(x, 0, None)
    if x.size == 0:
        return float("nan")
    s = float(x.sum())
    if s <= 0:
        return 0.0
    x = np.sort(x)
    n = x.size
    idx = np.arange(1, n + 1, dtype=float)
    return float((2 * np.sum(idx * x) / (n * s)) - (n + 1) / n)


def _entropy(vals: np.ndarray) -> float:
    x = np.asarray(vals, dtype=float)
    x = x[np.isfinite(x)]
    x = np.clip(x, 0, None)
    s = float(x.sum())
    if x.size == 0 or s <= 0:
        return float("nan")
    p = x / s
    p = p[p > 0]
    return float(-np.sum(p * np.log(p)))


def _asset_config(asset: str) -> dict:
    if asset == "SAG1":
        return {
            "channels": ["SAG:%_LI2016D", "SAG:LI2016B", "SAG:LI2016A"],
            "tph_col": "SAG:WIC2101",
            "controls": ["SAG:250_PROFIT_SAG1.MV0_High", "SAG:250_PROFIT_SAG1.MV0_Low"],
            "target_col": "SAG:250_PROFIT_SAG1.MV0_High",
            "proxy_threshold": 0.85,
            "asym_name": "asym_longitudinal",
            "positions": np.array([-1.0, 0.0, 1.0], dtype=float),
        }
    angles = np.deg2rad([0, -60, -120, 180, 60])
    return {
        "channels": [
            "SAG2:260_LI_PILA01",
            "SAG2:260_LI_PILA02",
            "SAG2:260_LI_PILA04",
            "SAG2:260_LI_PILA05",
            "SAG2:260_LI_PILA06",
        ],
        "tph_col": "sag2:260_wit_1835",
        "controls": ["SAG2:MV01_N(1)", "SAG2:MV01_N(2)"],
        "target_col": "SAG2:MV01_N(2)",
        "proxy_threshold": 0.90,
        "asym_name": "asym_radial",
        "positions": np.c_[np.cos(angles), np.sin(angles)],
    }


def _prepare_asset_frame(df: pd.DataFrame, asset: str) -> pd.DataFrame:
    cfg = _asset_config(asset)
    cols = list(dict.fromkeys(["fecha", cfg["tph_col"], cfg["target_col"], *cfg["controls"], *cfg["channels"]]))
    work = df[cols].copy()
    work["fecha"] = pd.to_datetime(work["fecha"])
    for c in cols[1:]:
        work[c] = pd.to_numeric(work[c], errors="coerce")
    work = work.dropna().copy()

    arr = work[cfg["channels"]].to_numpy(dtype=float)
    work["pile_avg"] = arr.mean(axis=1)
    work["std_canales"] = arr.std(axis=1)
    work["range_canales"] = arr.max(axis=1) - arr.min(axis=1)
    work["canal_min"] = arr.min(axis=1)
    work["canal_max"] = arr.max(axis=1)
    work["cv_canales"] = np.where(work["pile_avg"].abs() > 1e-9, work["std_canales"] / work["pile_avg"], 0.0)
    work["gini_canales"] = [_gini(v) for v in arr]
    work["entropy_canales"] = [_entropy(v) for v in arr]
    work["active_channels"] = (arr > 5.0).sum(axis=1)

    if asset == "SAG1":
        pos = cfg["positions"]
        work[cfg["asym_name"]] = (arr * pos).sum(axis=1) / np.clip(arr.sum(axis=1), 1e-9, None)
    else:
        pos = cfg["positions"]
        vec = (arr[:, :, None] * pos[None, :, :]).sum(axis=1)
        work[cfg["asym_name"]] = np.linalg.norm(vec, axis=1) / np.clip(arr.sum(axis=1), 1e-9, None)

    work["tph"] = work[cfg["tph_col"]]
    work["low_capacity_proxy"] = (work[cfg["tph_col"]] / work[cfg["target_col"]] < cfg["proxy_threshold"]).astype(int)
    return work


def _blocked_bootstrap_delta(
    hold: pd.DataFrame,
    delta_col: str,
    date_col: str = "fecha",
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    days = pd.to_datetime(hold[date_col]).dt.floor("D")
    unique_days = days.drop_duplicates().tolist()
    rng = np.random.default_rng(seed)
    means: list[float] = []
    if len(unique_days) <= 1:
        val = float(hold[delta_col].mean())
        return val, val
    for _ in range(n_boot):
        sampled_days = rng.choice(unique_days, size=len(unique_days), replace=True)
        pieces = [hold.loc[days == day, delta_col].to_numpy(dtype=float) for day in sampled_days]
        merged = np.concatenate([p for p in pieces if p.size > 0])
        means.append(float(np.mean(merged)))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def evaluate_linear_models(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for asset in ("SAG1", "SAG2"):
        cfg = _asset_config(asset)
        work = _prepare_asset_frame(df, asset)
        cal = work[work["fecha"] <= CUTOFF_HOLDOUT].copy()
        hold = work[work["fecha"] > CUTOFF_HOLDOUT].copy()
        asym = cfg["asym_name"]
        models = {
            "base": ["pile_avg"],
            "spatial": [
                "pile_avg",
                "std_canales",
                "range_canales",
                "canal_min",
                "canal_max",
                "cv_canales",
                "gini_canales",
                "entropy_canales",
                "active_channels",
                asym,
            ],
            "control_only": cfg["controls"],
            "control_plus_pile": [*cfg["controls"], "pile_avg"],
            "control_plus_spatial": [
                *cfg["controls"],
                "pile_avg",
                "std_canales",
                "range_canales",
                "canal_min",
                "canal_max",
                "cv_canales",
                "gini_canales",
                "entropy_canales",
                "active_channels",
                asym,
            ],
        }
        hold_predictions: dict[str, np.ndarray] = {}
        for model_name, features in models.items():
            lr = LinearRegression().fit(cal[features], cal["tph"])
            pred_cal = lr.predict(cal[features])
            pred_hold = lr.predict(hold[features])
            hold_predictions[model_name] = pred_hold
            rows.append({
                "asset": asset,
                "model": model_name,
                "n_cal": len(cal),
                "n_hold": len(hold),
                "r2_cal": r2_score(cal["tph"], pred_cal),
                "r2_hold": r2_score(hold["tph"], pred_hold),
                "mae_cal": mean_absolute_error(cal["tph"], pred_cal),
                "mae_hold": mean_absolute_error(hold["tph"], pred_hold),
                "rmse_cal": math.sqrt(mean_squared_error(cal["tph"], pred_cal)),
                "rmse_hold": math.sqrt(mean_squared_error(hold["tph"], pred_hold)),
                "features": ",".join(features),
            })
        hold_eval = hold[["fecha", "tph"]].copy()
        hold_eval["base_err_abs"] = np.abs(hold_predictions["base"] - hold["tph"].to_numpy())
        hold_eval["spatial_err_abs"] = np.abs(hold_predictions["spatial"] - hold["tph"].to_numpy())
        hold_eval["delta_mae_spatial_vs_base"] = hold_eval["spatial_err_abs"] - hold_eval["base_err_abs"]
        ci_lo, ci_hi = _blocked_bootstrap_delta(hold_eval, "delta_mae_spatial_vs_base")
        rows.append({
            "asset": asset,
            "model": "spatial_vs_base_block_bootstrap",
            "n_cal": len(cal),
            "n_hold": len(hold),
            "r2_cal": np.nan,
            "r2_hold": np.nan,
            "mae_cal": np.nan,
            "mae_hold": float(hold_eval["delta_mae_spatial_vs_base"].mean()),
            "rmse_cal": ci_lo,
            "rmse_hold": ci_hi,
            "features": "reported_as mean_delta_mae / ci95_lo / ci95_hi",
        })
    return pd.DataFrame(rows)


def evaluate_logistic_models(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for asset in ("SAG1", "SAG2"):
        cfg = _asset_config(asset)
        work = _prepare_asset_frame(df, asset)
        cal = work[work["fecha"] <= CUTOFF_HOLDOUT].copy()
        hold = work[work["fecha"] > CUTOFF_HOLDOUT].copy()
        asym = cfg["asym_name"]
        models = {
            "base": ["pile_avg"],
            "spatial": [
                "pile_avg",
                "std_canales",
                "range_canales",
                "canal_min",
                "canal_max",
                "cv_canales",
                "gini_canales",
                "entropy_canales",
                asym,
            ],
        }
        for model_name, features in models.items():
            clf = LogisticRegression(max_iter=500, class_weight="balanced")
            clf.fit(cal[features], cal["low_capacity_proxy"])
            proba = clf.predict_proba(hold[features])[:, 1]
            pred = (proba >= 0.5).astype(int)
            rows.append({
                "asset": asset,
                "model": model_name,
                "n_cal": len(cal),
                "n_hold": len(hold),
                "prevalence_cal": float(cal["low_capacity_proxy"].mean()),
                "prevalence_hold": float(hold["low_capacity_proxy"].mean()),
                "auc_hold": roc_auc_score(hold["low_capacity_proxy"], proba),
                "precision_hold": precision_score(hold["low_capacity_proxy"], pred),
                "recall_hold": recall_score(hold["low_capacity_proxy"], pred),
                "f1_hold": f1_score(hold["low_capacity_proxy"], pred),
                "features": ",".join(features),
            })
    return pd.DataFrame(rows)


def evaluate_operational_holdout() -> pd.DataFrame:
    rows: list[dict] = []
    regimes = ["t8_corta", "inventario_critico", "mantenimiento", "alimentacion_restringida"]
    rng = np.random.default_rng(42)
    for regime in regimes:
        base = run_backtest_variant(regime, start_time="2026-05-01")
        multi = run_backtest_variant(regime, simulation_overrides={"multicell_enabled": True}, start_time="2026-05-01")
        if not base.historica_disponible or not multi.historica_disponible:
            rows.append({
                "regimen": regime,
                "n_eventos": 0,
                "mean_delta_pp": np.nan,
                "ci95_lo": np.nan,
                "ci95_hi": np.nan,
                "improved_share": np.nan,
                "baseline_mae_pp": base.pila_mae_sag1_pp,
                "multicell_mae_pp": multi.pila_mae_sag1_pp,
            })
            continue

        bdf = pd.DataFrame(base.detalle)
        mdf = pd.DataFrame(multi.detalle)
        key = "evento_id" if "evento_id" in bdf.columns else "evento_inicio"
        err_col = "err_pila_sag1_pp" if "err_pila_sag1_pp" in bdf.columns else "err_pila_pp"
        merged = bdf[[key, err_col]].merge(mdf[[key, err_col]], on=key, suffixes=("_base", "_multi"))
        merged["delta_pp"] = merged[f"{err_col}_multi"] - merged[f"{err_col}_base"]

        vals = merged["delta_pp"].to_numpy(dtype=float)
        if len(vals) <= 1:
            lo = hi = float(vals.mean())
        else:
            samples = []
            for _ in range(2000):
                sample = rng.choice(vals, size=len(vals), replace=True)
                samples.append(float(np.mean(sample)))
            lo, hi = np.percentile(samples, [2.5, 97.5])
        rows.append({
            "regimen": regime,
            "n_eventos": int(len(vals)),
            "mean_delta_pp": float(np.mean(vals)),
            "ci95_lo": float(lo),
            "ci95_hi": float(hi),
            "improved_share": float((vals < 0).mean()),
            "baseline_mae_pp": base.pila_mae_sag1_pp,
            "multicell_mae_pp": multi.pila_mae_sag1_pp,
        })
    return pd.DataFrame(rows)


def run_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = pd.read_excel(RAW_XLSX, header=1)
    linear_df = evaluate_linear_models(df)
    logistic_df = evaluate_logistic_models(df)
    backtest_df = evaluate_operational_holdout()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    linear_df.to_csv(LINEAR_CSV, index=False, encoding="utf-8")
    logistic_df.to_csv(LOGISTIC_CSV, index=False, encoding="utf-8")
    backtest_df.to_csv(BACKTEST_CSV, index=False, encoding="utf-8")
    return linear_df, logistic_df, backtest_df


if __name__ == "__main__":
    linear_df, logistic_df, backtest_df = run_all()
    print("=== Evidencia multicelda ===")
    print(f"linear_csv   = {LINEAR_CSV}")
    print(f"logistic_csv = {LOGISTIC_CSV}")
    print(f"backtest_csv = {BACKTEST_CSV}")
    print()
    print("-- Linear hold-out --")
    print(
        linear_df[linear_df["model"].isin(["base", "spatial", "control_only", "control_plus_pile", "control_plus_spatial"])]
        [["asset", "model", "r2_hold", "mae_hold", "rmse_hold"]]
        .to_string(index=False)
    )
    print()
    print("-- Logistic hold-out --")
    print(logistic_df[["asset", "model", "auc_hold", "f1_hold"]].to_string(index=False))
    print()
    print("-- Backtest hold-out --")
    print(backtest_df.to_string(index=False))
