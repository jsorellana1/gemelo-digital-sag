"""
compare_multicell_backtest.py - Comparacion baseline vs multicelda
sobre backtesting historico, con split temporal real.

Objetivos:
1. Reusar `engine.historical_backtesting.run_backtest_variant` para no
   duplicar la logica de evaluacion.
2. Comparar baseline agregado vs candidato multicelda con el MISMO set
   de eventos por regimen y split.
3. Materializar un resumen reproducible por regimen/split para decidir
   si la Fase 1 multicelda merece pasar a calibracion formal.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", ".."))
_ROOT = os.path.normpath(os.path.join(_DASHBOARD, ".."))
if _DASHBOARD not in sys.path:
    sys.path.insert(0, _DASHBOARD)

from engine.historical_backtesting import run_backtest_variant  # noqa: E402


CUTOFF_RECOMENDADO = pd.Timestamp("2026-04-30")
REGIMENES_DEFAULT = [
    "t8_corta",
    "overflow",
    "inventario_critico",
    "mantenimiento",
    "alimentacion_restringida",
]
VARIANTES = {
    "baseline_agregado": {},
    "candidato_multicelda_fase1": {"multicell_enabled": True},
}

OUTPUT_DIR = os.path.join(_ROOT, "04_Reports", "Technical")
SUMMARY_CSV = os.path.join(OUTPUT_DIR, "20260715_multicell_backtest_summary.csv")
DELTA_CSV = os.path.join(OUTPUT_DIR, "20260715_multicell_backtest_delta_vs_baseline.csv")


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "nan"


def _split_windows(cutoff: pd.Timestamp) -> dict[str, tuple[pd.Timestamp | None, pd.Timestamp | None]]:
    cutoff = pd.Timestamp(cutoff).normalize()
    cal_end = cutoff + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    hold_start = cutoff + pd.Timedelta(days=1)
    return {
        "full": (None, None),
        "calibration": (None, cal_end),
        "holdout": (hold_start, None),
    }


def compare_multicell_backtest(
    cutoff: pd.Timestamp = CUTOFF_RECOMENDADO,
    regimenes: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    regimenes = regimenes or REGIMENES_DEFAULT
    split_windows = _split_windows(cutoff)

    rows: list[dict] = []
    for regimen in regimenes:
        for split_name, (start_time, end_time) in split_windows.items():
            for variant_name, overrides in VARIANTES.items():
                result = run_backtest_variant(
                    regimen,
                    simulation_overrides=overrides or None,
                    start_time=start_time,
                    end_time=end_time,
                )
                rows.append({
                    "regimen": regimen,
                    "split": split_name,
                    "variant": variant_name,
                    "start_time": start_time.isoformat() if start_time is not None else "",
                    "end_time": end_time.isoformat() if end_time is not None else "",
                    "historica_disponible": bool(result.historica_disponible),
                    "n_eventos": int(result.n_eventos),
                    "pila_mae_sag1_pp": result.pila_mae_sag1_pp,
                    "pila_mae_sag2_pp": result.pila_mae_sag2_pp,
                    "pila_bias_sag1_pp": result.pila_bias_sag1_pp,
                    "pila_std_sag1_pp": result.pila_std_sag1_pp,
                    "tph_mae_sag1_pct": result.tph_mae_sag1_pct,
                    "cv_mae_sag1_pct": result.cv_mae_sag1_pct,
                    "error_tiempo_critico_h": result.error_tiempo_critico_h,
                    "dentro_tolerancia": result.dentro_tolerancia,
                    "razon": result.razon,
                })

    summary = pd.DataFrame(rows)
    baseline = (
        summary[summary["variant"] == "baseline_agregado"]
        .rename(
            columns={
                "historica_disponible": "baseline_disponible",
                "n_eventos": "baseline_n_eventos",
                "pila_mae_sag1_pp": "baseline_mae_sag1_pp",
                "pila_bias_sag1_pp": "baseline_bias_sag1_pp",
                "tph_mae_sag1_pct": "baseline_tph_mae_sag1_pct",
                "error_tiempo_critico_h": "baseline_tcrit_mae_h",
            }
        )[
            [
                "regimen",
                "split",
                "baseline_disponible",
                "baseline_n_eventos",
                "baseline_mae_sag1_pp",
                "baseline_bias_sag1_pp",
                "baseline_tph_mae_sag1_pct",
                "baseline_tcrit_mae_h",
            ]
        ]
    )
    delta = summary.merge(baseline, on=["regimen", "split"], how="left")
    delta["delta_mae_sag1_pp"] = delta["pila_mae_sag1_pp"] - delta["baseline_mae_sag1_pp"]
    delta["delta_bias_sag1_pp"] = delta["pila_bias_sag1_pp"] - delta["baseline_bias_sag1_pp"]
    delta["delta_tph_mae_sag1_pct"] = delta["tph_mae_sag1_pct"] - delta["baseline_tph_mae_sag1_pct"]
    delta["delta_tcrit_mae_h"] = delta["error_tiempo_critico_h"] - delta["baseline_tcrit_mae_h"]
    return summary, delta


def export_multicell_backtest(
    cutoff: pd.Timestamp = CUTOFF_RECOMENDADO,
    regimenes: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary, delta = compare_multicell_backtest(cutoff=cutoff, regimenes=regimenes)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary.to_csv(SUMMARY_CSV, index=False, encoding="utf-8")
    delta.to_csv(DELTA_CSV, index=False, encoding="utf-8")
    return summary, delta


if __name__ == "__main__":
    summary_df, delta_df = export_multicell_backtest()
    print("=== Comparacion backtesting baseline vs multicelda ===")
    print(f"cutoff hold-out real = {CUTOFF_RECOMENDADO.date().isoformat()}")
    print(f"summary_csv = {SUMMARY_CSV}")
    print(f"delta_csv   = {DELTA_CSV}")
    print()
    for regimen in REGIMENES_DEFAULT:
        sub = delta_df[(delta_df["regimen"] == regimen) & (delta_df["split"] == "holdout")]
        if sub.empty:
            continue
        print(f"[{regimen}]")
        for _, row in sub.iterrows():
            print(
                f"  {row['variant']}: disponible={row['historica_disponible']} "
                f"n={int(row['n_eventos'])} mae_sag1={_fmt(row['pila_mae_sag1_pp'])} "
                f"delta_vs_base={_fmt(row['delta_mae_sag1_pp'])}"
            )
