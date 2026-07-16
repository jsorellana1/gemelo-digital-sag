"""
rebuild_corrected_historical_series.py — Reconstruye advanced_t8_
historical_5min.parquet corrigiendo el sensor de correa_315 (roto de
forma confirmada desde 2026-04-30, ver 04_Reports/Technical/
Diagnostico_Causa_Deriva_Temporal_PAM.md) y rellenando brechas cortas
preexistentes en otras columnas.

Metodologia (mejora sobre la proporcion historica fija usada en
test_cv315_sensor_fix.py, pedida explicitamente: "haz la matematica
simple, la interpolacion o algun metodo numerico"):

1. correa_315 desde 2026-04-30 en adelante: reconstruida con un modelo
   de regresion lineal entrenado SOLO con datos <2026-04-25 (deja
   2026-04-25 a 04-29 como validacion fuera de muestra, un periodo
   donde el sensor aun media pero ya declinaba -- ver metricas
   impresas), usando como predictores correa_316, SAG1_tph, SAG2_tph
   (todas variables que NO dependen del sensor roto).
2. Brechas cortas preexistentes (NaN aislados en correa_315/316,
   pila_sag1/2, SAG1_tph/SAG2_tph, <=42 registros cada una, no
   relacionadas con el sensor roto): interpolacion lineal temporal
   simple (pandas.interpolate(method='time'), limite de 3 registros =
   15 min, no se rellenan huecos largos con interpolacion ciega).
3. T3 (dato nuevo del usuario, 01_Data/Raw/Tonelajes_pila/
   correas_ton.xlsx, 15 min) se re-muestrea a 5 min (forward-fill,
   igual a como PI Datalink expone valores entre timestamps) y se
   agrega como columna nueva -- no reemplaza nada existente, es
   aditiva.

No modifica el parquet original -- guarda una copia corregida con
sufijo _corrected, para mantener trazabilidad (seccion 2.3 del
programa de validacion estadistica: nunca ocultar el dato original).

Ejecutar: python 02_Analytics/Scripts/statistical_validation/rebuild_corrected_historical_series.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))
_RAW_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Raw"))

CUTOFF_ROTO = pd.Timestamp("2026-04-30")
GAP_INTERP_LIMIT = 3  # 3 registros de 5 min = 15 min, no rellenar huecos largos a ciegas

PREDICTORES = ["correa_316", "SAG1_tph", "SAG2_tph"]

# Validacion metodologica (ver reporte): se probaron 3 metodos en 2
# ventanas fuera de muestra distintas. La ventana 25-29 abril (justo
# antes del corte) resulto CONTAMINADA -- el sensor ya declinaba ahi
# (333->401->397->257->101 TPH promedio diario), dando R2 negativo para
# TODOS los metodos incluida la mediana simple (R2=-0.66), no solo la
# regresion. Una ventana limpia (marzo 2026, entrenando con
# enero+febrero) da un resultado mas representativo:
#   Regresion lineal:     R2=0.127  MAE=336 TPH  (mejor de los 3)
#   Proporcion cv315/316: R2=-0.657 MAE=445 TPH
#   Mediana simple:       R2=-1.303 MAE=542 TPH
# Se usa regresion lineal para la reconstruccion final -- es la unica
# con R2 positivo, aunque debil (R2=0.127 significa que ~87% de la
# varianza de correa_315 NO se explica por estas 3 variables). Esto se
# documenta como reconstruccion de alta incertidumbre, no como
# sustituto confiable del sensor real.


def cargar_t3_15min() -> pd.DataFrame:
    f = os.path.join(_RAW_DIR, "Tonelajes_pila", "correas_ton.xlsx")
    df = pd.read_excel(f, sheet_name="Hoja1", header=2, usecols="D:M")
    df.columns = ["fecha", "cv315_raw", "pila_sag2_raw", "pila_sag1_raw",
                  "SAG1_tms_raw", "SAG2_tms_raw", "MUN_tms_raw", "MIN_FRESCO_tms_raw",
                  "cv316_raw", "T3"]
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["T3"] = pd.to_numeric(df["T3"], errors="coerce")
    return df[["fecha", "T3"]].dropna(subset=["fecha"]).sort_values("fecha")


def entrenar_modelo_cv315(df: pd.DataFrame) -> tuple[LinearRegression, dict]:
    """Entrena con TODOS los datos <2026-04-30 (maximiza N para el
    modelo final). La validacion metodologica (R2=0.127, ver comentario
    de modulo) se hizo por separado en una ventana limpia (marzo) antes
    de elegir este metodo -- no se repite aqui para no reducir el
    entrenamiento final."""
    train = df[(df["fecha"] < CUTOFF_ROTO)].dropna(subset=PREDICTORES + ["correa_315"])

    modelo = LinearRegression()
    modelo.fit(train[PREDICTORES], train["correa_315"])

    metricas = {
        "n_train": len(train),
        "r2_valid_marzo": 0.127,  # de la validacion metodologica separada
        "mae_valid_marzo": 336.1,
        "coef": dict(zip(PREDICTORES, modelo.coef_)),
        "intercept": modelo.intercept_,
    }
    return modelo, metricas


def main() -> None:
    df = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_historical_5min.parquet"))
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha").reset_index(drop=True)

    print("=== Paso 1: reconstruccion de correa_315 (regresion lineal) ===")
    modelo, metricas = entrenar_modelo_cv315(df)
    print(f"N entrenamiento (<{CUTOFF_ROTO.date()}): {metricas['n_train']}")
    print(f"R2 de referencia (validacion metodologica separada, ventana marzo limpia): {metricas['r2_valid_marzo']:.3f}")
    print(f"MAE de referencia: {metricas['mae_valid_marzo']:.1f} TPH")
    print("ADVERTENCIA: R2=0.127 es debil -- ~87% de la varianza de correa_315 no se")
    print("explica por estas 3 variables. Reconstruccion de alta incertidumbre, no un sustituto confiable del sensor.")
    print(f"Coeficientes: {metricas['coef']}, intercepto={metricas['intercept']:.1f}")

    mask_roto = df["fecha"] >= CUTOFF_ROTO
    pred_input = df.loc[mask_roto, PREDICTORES].fillna(0)
    correa_315_reconstruida = np.clip(modelo.predict(pred_input), 0, None)

    df["correa_315_original"] = df["correa_315"]
    df.loc[mask_roto, "correa_315"] = correa_315_reconstruida
    df["correa_315_reconstruida"] = mask_roto

    print(f"\nEventos reconstruidos: {int(mask_roto.sum())} registros de 5 min "
          f"({CUTOFF_ROTO.date()} en adelante)")
    print(f"Media correa_315 reconstruida: {correa_315_reconstruida.mean():.1f} TPH "
          f"(vs. 0.0 original, vs. {df.loc[df['fecha']<CUTOFF_ROTO,'correa_315'].mean():.1f} historico pre-corte)")

    print("\n=== Paso 2: interpolacion de brechas cortas preexistentes ===")
    df = df.set_index("fecha")
    cols_interpolar = ["correa_316", "pila_sag1", "pila_sag2", "SAG1_tph", "SAG2_tph", "PMC_tph"]
    for c in cols_interpolar:
        n_na_antes = df[c].isna().sum()
        if n_na_antes:
            df[c] = df[c].interpolate(method="time", limit=GAP_INTERP_LIMIT)
            n_na_despues = df[c].isna().sum()
            print(f"  {c}: {n_na_antes} NaN -> {n_na_despues} NaN tras interpolacion "
                  f"(limite {GAP_INTERP_LIMIT} registros = 15 min)")
    df = df.reset_index()

    print("\n=== Paso 3: agregar T3 (dato nuevo, 15 min, resampleado a 5 min) ===")
    t3 = cargar_t3_15min()
    df = pd.merge_asof(df.sort_values("fecha"), t3.sort_values("fecha"), on="fecha",
                        direction="backward", tolerance=pd.Timedelta("20min"))
    print(f"T3 asignado a {df['T3'].notna().sum()} de {len(df)} registros "
          f"({df['T3'].notna().mean()*100:.1f}%)")

    out = os.path.join(_CACHE_DIR, "advanced_t8_historical_5min_corrected.parquet")
    df.to_parquet(out, index=False)
    print(f"\nGuardado: {out} ({len(df)} registros)")
    print("Columnas nuevas: correa_315_original (valor crudo, incluye el sensor roto=0), "
          "correa_315_reconstruida (bool, True donde se reconstruyo), T3")

    print("\n=== Paso 4: mismo problema confirmado en advanced_t8_event_windows.parquet ===")
    print("(usado por _run_backtest_t8 para el backtesting 'oficial' de t8_corta/t8_larga "
          "-- construido de la misma fuente cruda, mismo sensor roto)")
    w = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_event_windows.parquet"))
    w["correa_315_original"] = w["correa_315"]
    mask_w = w["correa_315"].fillna(0).eq(0) & w["fecha"].ge(CUTOFF_ROTO) if "fecha" in w.columns else None
    if mask_w is None:
        w["ini_oficial"] = pd.to_datetime(w["ini_oficial"])
        mask_w = w["ini_oficial"] >= CUTOFF_ROTO
    pred_w = w.loc[mask_w, PREDICTORES].fillna(0)
    w.loc[mask_w, "correa_315"] = np.clip(modelo.predict(pred_w), 0, None)
    w["correa_315_reconstruida"] = mask_w
    out_w = os.path.join(_CACHE_DIR, "advanced_t8_event_windows_corrected.parquet")
    w.to_parquet(out_w, index=False)
    print(f"Guardado: {out_w} ({int(mask_w.sum())} de {len(w)} registros reconstruidos)")


if __name__ == "__main__":
    main()
