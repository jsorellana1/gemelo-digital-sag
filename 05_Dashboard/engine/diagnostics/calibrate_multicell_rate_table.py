"""
calibrate_multicell_rate_table.py - Recalibracion reproducible de tablas
n_canales_activos -> rate para la Fase 1 multi-celda.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", ".."))
if _DASHBOARD not in sys.path:
    sys.path.insert(0, _DASHBOARD)

from engine.ode_model import P90
from engine.stockpile_multicell import (  # noqa: E402
    DEFAULT_MULTICELL_LAYOUTS,
    calibrate_rate_table_from_history,
    load_multicell_history,
)


def main() -> None:
    df = load_multicell_history()
    specs = {
        "SAG1": {
            "rate_col": "SAG:WIC2101",
            "candidate_columns": (
                "SAG:%_LI2016D",
                "SAG:LI2016B",
                "SAG:LI2016A",
                "SAG:LI2016C",
            ),
        },
        "SAG2": {
            "rate_col": "sag2:260_wit_1835",
            "candidate_columns": (
                "SAG2:260_LI_PILA01",
                "SAG2:260_LI_PILA02",
                "SAG2:260_LI_PILA03",
                "SAG2:260_LI_PILA04",
                "SAG2:260_LI_PILA05",
                "SAG2:260_LI_PILA06",
            ),
        },
    }
    for asset, spec in specs.items():
        result = calibrate_rate_table_from_history(
            df=df,
            asset=asset,
            rate_col=spec["rate_col"],
            candidate_columns=spec["candidate_columns"],
            max_rate_tph=P90[asset],
        )
        print(f"=== {asset} ===")
        print("usable_columns", result["usable_columns"])
        print("dropped_columns", result["dropped_columns"])
        print("rate_table_tph", result["rate_table_tph"])
        print("default_rate_table_tph", DEFAULT_MULTICELL_LAYOUTS[asset]["rate_table_tph"])
        print("summary")
        for row in result["summary"]:
            print(row)
        print()


if __name__ == "__main__":
    main()
