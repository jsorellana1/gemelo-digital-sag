"""
calibrate_monte_carlo_sigmas.py — Compara los sigmas asumidos en
adaptive_mc_eval (05_Dashboard/engine/optimizer_v2.py, secc. ~444-447:
pila +-2.5pp, feed factor +-12%, T8 +-1h) contra proxies empiricos
derivados de datos historicos reales (secciones 18-19 del programa de
validacion estadistica). No modifica optimizer_v2.py -- solo genera
evidencia para decidir si vale la pena recalibrar.

Ejecutar: python 02_Analytics/Scripts/statistical_validation/calibrate_monte_carlo_sigmas.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))
_REPORTS_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "04_Reports", "Technical"))

ASSUMED = {"pila_sigma_pp": 2.5, "feed_sigma_frac": 0.12, "t8_sigma_h": 1.0}


def calibrar_t8() -> dict:
    ev = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_official_events.parquet"))
    diff = ev["horas_t8_raw"] - ev["duracion_h"]
    return {
        "variable": "duracion_t8_h",
        "n": len(diff),
        "mean_diff": float(diff.mean()),
        "std_diff": float(diff.std()),
        "skew_diff": float(diff.skew()),
        "p90_diff": float(diff.quantile(0.90)),
        "max_diff": float(diff.max()),
        "sigma_asumido": ASSUMED["t8_sigma_h"],
    }


def calibrar_pila() -> pd.DataFrame:
    df = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_historical_5min.parquet"))
    filas = []
    for asset, col in (("SAG1", "pila_sag1"), ("SAG2", "pila_sag2")):
        d = df[col].diff().dropna()
        filas.append({
            "asset": asset, "n": len(d), "std_5min_diff_pp": float(d.std()),
            "p1_p99_5min_diff_pp": (float(d.quantile(0.01)), float(d.quantile(0.99))),
            "sigma_asumido_pp": ASSUMED["pila_sigma_pp"],
        })
    return pd.DataFrame(filas)


def calibrar_feed() -> dict:
    df = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_historical_5min.parquet"))
    feed = (df["correa_315"].fillna(0) + df["correa_316"].fillna(0))
    feed = feed[feed > 100]
    roll_mean = feed.rolling(48, min_periods=24).mean()
    roll_std = feed.rolling(48, min_periods=24).std()
    cv = (roll_std / roll_mean).dropna()
    cv = cv[np.isfinite(cv)]
    return {
        "variable": "feed_cv_ventana_4h", "n": len(cv),
        "mean_cv": float(cv.mean()), "median_cv": float(cv.median()), "std_cv": float(cv.std()),
        "sigma_asumido_frac": ASSUMED["feed_sigma_frac"],
    }


def main() -> None:
    t8 = calibrar_t8()
    pila = calibrar_pila()
    feed = calibrar_feed()

    print("=== T8: horas_t8_raw - duracion_h (bucket nominal) ===")
    print(t8)
    print(f"Ratio std_real/sigma_asumido: {t8['std_diff'] / t8['sigma_asumido']:.2f}x")
    print()

    print("=== Pila: dispersion de cambios 5-min (proxy de volatilidad de corto plazo) ===")
    print(pila.to_string(index=False))
    print()

    print("=== Feed: CV en ventanas moviles de 4h (mismo horizonte tipico de escenario) ===")
    print(feed)
    print(f"Ratio CV_real/sigma_asumido: {feed['median_cv'] / feed['sigma_asumido_frac']:.2f}x")
    print()

    resumen = pd.DataFrame([
        {"parametro": "duracion_t8_h", "sigma_asumido": t8["sigma_asumido"],
         "proxy_empirico": round(t8["std_diff"], 2), "ratio": round(t8["std_diff"] / t8["sigma_asumido"], 2),
         "n": t8["n"], "nota": "std de (horas_t8_raw - duracion_h), distribucion muy asimetrica (skew=5.0)"},
        {"parametro": "pila_sag1_pct", "sigma_asumido": ASSUMED["pila_sigma_pp"],
         "proxy_empirico": round(pila.iloc[0]["std_5min_diff_pp"], 2),
         "ratio": round(pila.iloc[0]["std_5min_diff_pp"] / ASSUMED["pila_sigma_pp"], 2),
         "n": int(pila.iloc[0]["n"]), "nota": "std de cambios 5-min consecutivos, proxy de volatilidad de corto plazo, no de incertidumbre de condicion inicial"},
        {"parametro": "pila_sag2_pct", "sigma_asumido": ASSUMED["pila_sigma_pp"],
         "proxy_empirico": round(pila.iloc[1]["std_5min_diff_pp"], 2),
         "ratio": round(pila.iloc[1]["std_5min_diff_pp"] / ASSUMED["pila_sigma_pp"], 2),
         "n": int(pila.iloc[1]["n"]), "nota": "mismo proxy que SAG1"},
        {"parametro": "feed_factor", "sigma_asumido": ASSUMED["feed_sigma_frac"],
         "proxy_empirico": round(feed["median_cv"], 3), "ratio": round(feed["median_cv"] / ASSUMED["feed_sigma_frac"], 2),
         "n": feed["n"], "nota": "CV mediano en ventanas moviles de 4h (mismo horizonte que un escenario tipico), no exactamente el mismo concepto estadistico que el factor multiplicativo del MC"},
    ])
    out = os.path.join(_REPORTS_DIR, "monte_carlo_calibration.csv")
    resumen.to_csv(out, index=False, encoding="utf-8")
    print(f"Guardado: {out}")


if __name__ == "__main__":
    main()
