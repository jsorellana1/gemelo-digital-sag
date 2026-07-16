"""
diagnose_sag2_lateral_transfer_holdout.py - Sensibilidad hold-out del
coeficiente de transferencia lateral multicelda para SAG2.

Objetivo:
- barrer coeficientes radiales/laterales opcionales solo en SAG2;
- medir impacto sobre MAE de pila SAG1/SAG2 por regimen;
- identificar si la Fase 2 radial agrega valor sobre Fase 1.
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


COEFF_GRID = [0.0, 0.05, 0.10, 0.20, 0.40, 0.80]
REGIMES = ["t8_corta", "inventario_critico", "mantenimiento", "alimentacion_restringida"]
OUTPUT_CSV = Path(_ROOT) / "04_Reports" / "Technical" / "20260715_sag2_lateral_transfer_holdout.csv"


def run_sweep() -> pd.DataFrame:
    rows: list[dict] = []
    for coeff in COEFF_GRID:
        overrides = {
            "multicell_enabled": True,
            "multicell_lateral_transfer_coeff_sag2": coeff,
        }
        for regime in REGIMES:
            result = run_backtest_variant(
                regime,
                simulation_overrides=overrides,
                start_time="2026-05-01",
            )
            rows.append({
                "regimen": regime,
                "coeff_sag2_h": coeff,
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
    df = run_sweep()
    print("=== Sweep hold-out transferencia lateral SAG2 ===")
    print(f"csv = {OUTPUT_CSV}")
    print()
    print(df.to_string(index=False))
