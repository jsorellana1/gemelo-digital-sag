"""test_sag1_operando_composition.py — Verifica la hipotesis del usuario
(2026-07-15, continuacion de Diagnostico_Causa_Deriva_Temporal_PAM.md):
si hay mantenciones/paradas de SAG1 o SAG2, las correas cv315/cv316
deben estar sin alimentacion (detenidas), y esos periodos no deberian
tratarse igual que un evento t8_corta real (SAG1 drenando la pila).

Metodologia: para cada uno de los 72 eventos oficiales T8
(`advanced_t8_official_events.parquet`), calcula la fraccion de tiempo
que `SAG1_operando`/`SAG2_operando` estuvieron en 1 durante la ventana
`ini_oficial`-`fin_oficial` (serie real `advanced_t8_historical_5min.
parquet`), y cruza esa fraccion con el error de pila que
`_run_backtest_t8('t8_corta')` ya calcula por evento (ruta productiva
real, sin modificarla).

No modifica ningun parametro de produccion. Solo diagnostico.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "05_Dashboard"))
_CACHE = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))
sys.path.insert(0, _DASHBOARD)

from engine.historical_backtesting import _run_backtest_t8  # noqa: E402

CUTOFF_HOLDOUT = pd.Timestamp("2026-04-30")
UMBRAL_APAGADO = 0.5  # fraccion de tiempo operando por debajo de la cual se considera "apagado"


def _fraccion_operando_por_evento() -> pd.DataFrame:
    ev = pd.read_parquet(os.path.join(_CACHE, "advanced_t8_official_events.parquet"))
    hist = pd.read_parquet(os.path.join(_CACHE, "advanced_t8_historical_5min.parquet"))
    hist["fecha"] = pd.to_datetime(hist["fecha"])
    hist = hist.set_index("fecha").sort_index()

    rows = []
    for _, r in ev.iterrows():
        sub = hist.loc[r["ini_oficial"]:r["fin_oficial"]]
        if len(sub) == 0:
            continue
        rows.append((r["evento_id"], r["fecha"], r["duracion_h"],
                     sub["SAG1_operando"].mean(), sub["SAG2_operando"].mean()))
    return pd.DataFrame(rows, columns=["evento_id", "fecha", "duracion_h", "sag1_op", "sag2_op"])


def main() -> None:
    res = _run_backtest_t8("t8_corta", enforce_prereq=False)
    det = pd.DataFrame(res.detalle)
    opd = _fraccion_operando_por_evento()
    m = det.merge(opd, on="evento_id", how="left")
    m["hold_out"] = m["fecha"] >= CUTOFF_HOLDOUT
    m["sag1_apagado"] = m["sag1_op"] < UMBRAL_APAGADO

    print("=== Composicion calibracion vs hold-out (t8_corta) ===")
    print(m.groupby(["hold_out", "sag1_apagado"])["err_pila_sag1_pp"].agg(["count", "mean"]))

    calib = m[~m["hold_out"]]
    corr = np.corrcoef(calib["sag1_op"], calib["err_pila_sag1_pp"])[0, 1]
    print(f"\nCorrelacion sag1_op (fraccion continua) vs error, solo calibracion: {corr:.3f}")

    print("\n=== MAE 'como para como' (excluye eventos con SAG1 apagado) ===")
    calib_activo = calib[~calib["sag1_apagado"]]
    holdout_activo = m[m["hold_out"] & (~m["sag1_apagado"])]
    print(f"Calibracion, SAG1 realmente operando: N={len(calib_activo)}  "
          f"MAE={calib_activo['err_pila_sag1_pp'].mean():.2f}pp")
    print(f"Hold-out,   SAG1 realmente operando: N={len(holdout_activo)}  "
          f"MAE={holdout_activo['err_pila_sag1_pp'].mean():.2f}pp")

    print("\n=== MAE agregado tal como se reporta hoy (sin filtrar) ===")
    print(f"Calibracion completa: N={len(calib)}  MAE={calib['err_pila_sag1_pp'].mean():.2f}pp")
    print(f"Hold-out completo:    N={len(m[m['hold_out']])}  "
          f"MAE={m[m['hold_out']]['err_pila_sag1_pp'].mean():.2f}pp")


if __name__ == "__main__":
    main()
