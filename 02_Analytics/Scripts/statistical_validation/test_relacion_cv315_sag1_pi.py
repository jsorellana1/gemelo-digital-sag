"""test_relacion_cv315_sag1_pi.py — Verifica la hipotesis fisica del
usuario (2026-07-15, continuacion de Diagnostico_Causa_Deriva_Temporal_
PAM.md): el rate de SAG1 deberia ser similar a lo que correa_315 le
alimenta, analogo al caso de referencia correa_316/SAG2 (que nunca tuvo
problemas de sensor).

Fuente: `01_Data/Raw/Tonelajes_pila/data_rendimiento_sag1.txt` (export
directo PI, tag REND_TMS_SAG1_PI, 2025-08-01 a 2026-07-15, resolucion
nativa ~10 min) proporcionado por el usuario -- mucho mas largo que el
export de correa_315, permite construir ventanas de entrenamiento
robustas con SAG1 genuinamente activo.

No modifica ningun parametro de produccion. Reporta honestamente que la
relacion, aunque real, no es estable en el tiempo (~27% de deriva entre
ventanas), por lo que no reemplaza la reconstruccion multivariada ya
usada en 755e83a.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_RAW_SAG1 = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "01_Data", "Raw", "Tonelajes_pila", "data_rendimiento_sag1.txt"))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))

UMBRAL_ACTIVO_TPH = 50.0


def cargar_pi_sag1() -> pd.DataFrame:
    df = pd.read_csv(_RAW_SAG1, sep="\t", skiprows=4,
                      names=["time_raw", "value", "attrs"], engine="python")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["fecha"] = pd.to_datetime(df["time_raw"], format="mixed", dayfirst=True)
    return df.dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)


def dias_activos_por_mes(pi_sag1_daily: pd.Series) -> pd.DataFrame:
    activo = pi_sag1_daily > UMBRAL_ACTIVO_TPH
    return activo.groupby(activo.index.to_period("M")).agg(["sum", "count"])


def _r2_mae(y_true: pd.Series, y_pred: pd.Series) -> tuple[float, float]:
    r2 = 1 - np.sum((y_true - y_pred) ** 2) / np.sum((y_true - y_true.mean()) ** 2)
    mae = float(np.mean(np.abs(y_true - y_pred)))
    return float(r2), mae


def main() -> None:
    pi_sag1 = cargar_pi_sag1()
    pi_sag1.to_parquet(os.path.join(_CACHE_DIR, "pi_sag1_rendimiento_raw_parsed.parquet"))
    pi_sag1_daily = pi_sag1.set_index("fecha")["value"].resample("1D").mean().rename("SAG1_tph_PI")

    print("=== Dias con SAG1 activo (>50 TPH) por mes, histórico completo ===")
    print(dias_activos_por_mes(pi_sag1_daily).to_string())

    hist = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_historical_5min.parquet"))
    hist["fecha"] = pd.to_datetime(hist["fecha"])
    cv315_daily = hist.set_index("fecha")["correa_315"].resample("1D").mean()
    cv316_daily = hist.set_index("fecha")["correa_316"].resample("1D").mean()
    sag2_daily = hist.set_index("fecha")["SAG2_tph"].resample("1D").mean()

    m = pd.concat([pi_sag1_daily, cv315_daily, cv316_daily, sag2_daily], axis=1).dropna()
    m.columns = ["SAG1_tph_PI", "correa_315", "correa_316", "SAG2_tph"]
    m["activo_sag1"] = m["SAG1_tph_PI"] > UMBRAL_ACTIVO_TPH
    m["activo_sag2"] = m["SAG2_tph"] > UMBRAL_ACTIVO_TPH

    train = m[(m.index >= "2025-09-01") & (m.index < "2026-01-01") & m["activo_sag1"]]
    test = m[(m.index >= "2026-03-01") & (m.index < "2026-04-01") & m["activo_sag1"]]
    print(f"\n=== CV315 ~ SAG1_tph_PI: train sep-dic 2025 (N={len(train)}), "
          f"test marzo 2026 (N={len(test)}) ===")

    b1, b0 = np.polyfit(train["SAG1_tph_PI"], train["correa_315"], 1)
    r2_lin, mae_lin = _r2_mae(test["correa_315"], b0 + b1 * test["SAG1_tph_PI"])
    print(f"Regresion lineal: correa_315 = {b0:.1f} + {b1:.3f}*SAG1_tph_PI  "
          f"R2={r2_lin:.3f}  MAE={mae_lin:.1f} TPH")

    ratio = (train["correa_315"] / train["SAG1_tph_PI"]).median()
    r2_ratio, mae_ratio = _r2_mae(test["correa_315"], ratio * test["SAG1_tph_PI"])
    print(f"Razon mediana: correa_315 = {ratio:.3f}*SAG1_tph_PI  "
          f"R2={r2_ratio:.3f}  MAE={mae_ratio:.1f} TPH")

    print("\n=== Control: estabilidad de la razon en el circuito de referencia (CV316/SAG2) ===")
    for label, ini, fin in [("sep-dic 2025", "2025-09-01", "2026-01-01"),
                             ("marzo 2026", "2026-03-01", "2026-04-01")]:
        sub = m[(m.index >= ini) & (m.index < fin) & m["activo_sag2"]]
        r_315 = (sub["correa_315"] / sub["SAG1_tph_PI"]).median() if len(sub) else float("nan")
        r_316 = (sub["correa_316"] / sub["SAG2_tph"]).median() if len(sub) else float("nan")
        print(f"{label}: N={len(sub)}  razon correa_315/SAG1={r_315:.3f}  "
              f"razon correa_316/SAG2={r_316:.3f}")


if __name__ == "__main__":
    main()
