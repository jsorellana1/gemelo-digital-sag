"""
diagnose_sag2_spatial_capacity_holdout.py - Hold-out del modelo de
capacidad espacial para SAG2.

Compara:
- multicelda Fase 1
- multicelda Fase 1 + capacidad espacial min/range para SAG2
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", ".."))
_ROOT = os.path.normpath(os.path.join(_DASHBOARD, ".."))
if _DASHBOARD not in sys.path:
    sys.path.insert(0, _DASHBOARD)

from engine.historical_backtesting import run_backtest_variant  # noqa: E402


REGIMES = ["t8_corta", "inventario_critico", "mantenimiento", "alimentacion_restringida"]
SPATIAL_PARAMS = {
    "intercept": 0.32183,
    "min_pct_coef": 0.00918,
    "range_pct_coef": 0.00517,
    "min_factor": 0.35,
    "max_factor": 1.0,
}
OUTPUT_CSV = Path(_ROOT) / "04_Reports" / "Technical" / "20260715_sag2_spatial_capacity_holdout.csv"


def run_compare() -> pd.DataFrame:
    variants = {
        "fase1_multicell": {
            "multicell_enabled": True,
        },
        "fase1_plus_sag2_spatial_cap": {
            "multicell_enabled": True,
            "multicell_spatial_capacity_mode_sag2": "min_range_linear",
            "multicell_spatial_capacity_params_sag2": SPATIAL_PARAMS,
        },
    }
    rows: list[dict] = []
    for variant_name, overrides in variants.items():
        for regime in REGIMES:
            result = run_backtest_variant(
                regime,
                simulation_overrides=overrides,
                start_time="2026-05-01",
            )
            rows.append({
                "variant": variant_name,
                "regimen": regime,
                "historica_disponible": bool(result.historica_disponible),
                "n_eventos": int(result.n_eventos),
                "pila_mae_sag1_pp": result.pila_mae_sag1_pp,
                "pila_mae_sag2_pp": result.pila_mae_sag2_pp,
                "pila_bias_sag1_pp": result.pila_bias_sag1_pp,
                "tph_mae_sag1_pct": result.tph_mae_sag1_pct,
                "razon": result.razon,
            })
    df = pd.DataFrame(rows)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    return df


if __name__ == "__main__":
    df = run_compare()
    print("=== Hold-out capacidad espacial SAG2 ===")
    print(f"csv = {OUTPUT_CSV}")
    print()
    print(df.to_string(index=False))
