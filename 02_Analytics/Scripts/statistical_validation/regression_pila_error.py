"""
regression_pila_error.py — EDA + regresion multivariada sobre el error de
pila final (pila_error_pp) de event_variable_table.csv (ver
build_event_variable_table.py).

Objetivo (continuacion de 04_Reports/Technical/
20260715_Diagnostico_Fidelidad_Historica.md): responder si existen
variables, ademas del cruce de breakpoints de _pile_feedback_factor ya
confirmado, que expliquen el error de pila final -- con un modelo de
regresion formal, ajustado en calibracion (<=2026-04-30) y evaluado en
hold-out real (>2026-04-30), no solo comparaciones de medias por
subgrupo.

Ejecutar: python 02_Analytics/Scripts/statistical_validation/regression_pila_error.py
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.multitest import multipletests

warnings.filterwarnings("ignore")

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPORTS_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "04_Reports", "Technical"))

BASE_FORMULA = "pila_error_pp ~ cruza_35pct + cruza_25pct + cruza_crit5pct"
CANDIDATE_TERMS = [
    "pila_ini_pct", "duracion_evento_h", "rate_gap_tph",
    "feed_restriction_pct", "hora_dia", "C(regimen)", "C(asset)",
]
MULTI_FORMULA = BASE_FORMULA + " + " + " + ".join(CANDIDATE_TERMS)

MIN_N_REGIMEN = 30  # bajo este N no se ajusta un modelo por regimen (no fabricar)


def _to_bool_int(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("cruza_35pct", "cruza_25pct", "cruza_crit5pct", "t8_activo"):
        df[c] = df[c].astype(bool).astype(int)
    return df


def _vif(df: pd.DataFrame, formula: str) -> pd.DataFrame:
    y, X = sm.regression.linear_model.OLS.from_formula(formula, data=df).exog_names, None
    design = sm.regression.linear_model.OLS.from_formula(formula, data=df)
    X = pd.DataFrame(design.exog, columns=design.exog_names)
    rows = []
    for i, col in enumerate(X.columns):
        if col == "Intercept":
            continue
        try:
            v = variance_inflation_factor(X.values, i)
        except Exception:
            v = np.nan
        rows.append({"variable": col, "VIF": round(v, 2)})
    return pd.DataFrame(rows)


def _fit_report(df_calib: pd.DataFrame, df_holdout: pd.DataFrame, formula: str, label: str) -> dict:
    model = smf.ols(formula, data=df_calib).fit()
    pred_holdout = model.predict(df_holdout) if len(df_holdout) else None
    mae_holdout = (
        float((pred_holdout - df_holdout["pila_error_pp"]).abs().mean())
        if pred_holdout is not None and len(df_holdout) else None
    )
    mae_calib = float(model.resid.abs().mean())
    return {
        "label": label,
        "model": model,
        "n_calib": int(model.nobs),
        "n_holdout": int(len(df_holdout)),
        "r2": model.rsquared,
        "r2_adj": model.rsquared_adj,
        "aic": model.aic,
        "bic": model.bic,
        "mae_calib": mae_calib,
        "mae_holdout": mae_holdout,
    }


def analizar_pooled(df: pd.DataFrame) -> dict:
    """Modelo pooled (todos los regimenes con dummy) -- mayor N, mayor
    poder estadistico, a costa de asumir efectos comunes entre regimenes
    (limitacion explicita, seccion 9 del prompt sugiere efectos mixtos
    como alternativa -- fuera de alcance de esta pasada)."""
    df = df[df["regimen"] != "overflow"].copy()  # overflow: 0 varianza en cruces, separacion perfecta
    calib = df[df["split"] == "calibracion"]
    holdout = df[df["split"] == "hold_out"]

    base = _fit_report(calib, holdout, BASE_FORMULA, "pooled_base")
    multi = _fit_report(calib, holdout, MULTI_FORMULA, "pooled_multivariado")

    lr_stat = -2.0 * (base["model"].llf - multi["model"].llf)
    df_diff = multi["model"].df_model - base["model"].df_model
    from scipy import stats as sstats
    lr_pvalue = float(sstats.chi2.sf(lr_stat, df_diff)) if df_diff > 0 else None

    vif_df = _vif(calib, MULTI_FORMULA)

    pvals = multi["model"].pvalues.drop("Intercept", errors="ignore")
    reject, pvals_adj, _, _ = multipletests(pvals.values, alpha=0.05, method="fdr_bh")
    bh = pd.DataFrame({
        "variable": pvals.index, "coef": multi["model"].params[pvals.index].values,
        "p_value": pvals.values, "p_value_bh": pvals_adj, "significativo_bh": reject,
    })

    return {"base": base, "multi": multi, "lr_stat": lr_stat, "lr_pvalue": lr_pvalue,
            "df_diff": df_diff, "vif": vif_df, "bh": bh}


def analizar_por_regimen(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for regimen in sorted(df["regimen"].unique()):
        sub = df[df["regimen"] == regimen]
        calib = sub[sub["split"] == "calibracion"]
        holdout = sub[sub["split"] == "hold_out"]
        if len(calib) < MIN_N_REGIMEN:
            filas.append({"regimen": regimen, "n_calib": len(calib), "n_holdout": len(holdout),
                          "estado": f"N calibracion < {MIN_N_REGIMEN}, no se ajusta modelo (no se fabrica resultado)"})
            continue
        formula = MULTI_FORMULA.replace(" + C(regimen)", "")
        n_asset = sub["asset"].nunique()
        if n_asset < 2:
            formula = formula.replace(" + C(asset)", "")
        try:
            r = _fit_report(calib, holdout, formula, regimen)
            filas.append({
                "regimen": regimen, "n_calib": r["n_calib"], "n_holdout": r["n_holdout"],
                "r2": round(r["r2"], 3), "r2_adj": round(r["r2_adj"], 3),
                "mae_calib_pp": round(r["mae_calib"], 2),
                "mae_holdout_pp": round(r["mae_holdout"], 2) if r["mae_holdout"] is not None else None,
                "estado": "OK",
            })
        except Exception as e:
            filas.append({"regimen": regimen, "n_calib": len(calib), "n_holdout": len(holdout),
                          "estado": f"ERROR: {e}"})
    return pd.DataFrame(filas)


def main() -> None:
    nombre_tabla = sys.argv[1] if len(sys.argv) > 1 else "event_variable_table.csv"
    path = os.path.join(_REPORTS_DIR, nombre_tabla)
    df = pd.read_csv(path)
    df = _to_bool_int(df)
    print(f"Tabla cargada: {len(df)} eventos, regimenes={df['regimen'].unique().tolist()}")

    print("\n=== EDA rapido ===")
    print(df.groupby("regimen")["pila_error_pp"].agg(["count", "mean", "std", "min", "max"]).round(2))
    print("\nMissingness:")
    print(df.isna().sum()[df.isna().sum() > 0])

    print("\n=== Modelo pooled (excluye overflow) ===")
    res = analizar_pooled(df)
    print(f"Base:        R2={res['base']['r2']:.3f}  R2_adj={res['base']['r2_adj']:.3f}  "
          f"AIC={res['base']['aic']:.1f}  MAE_calib={res['base']['mae_calib']:.2f}pp  "
          f"MAE_holdout={res['base']['mae_holdout']:.2f}pp")
    print(f"Multivariado: R2={res['multi']['r2']:.3f}  R2_adj={res['multi']['r2_adj']:.3f}  "
          f"AIC={res['multi']['aic']:.1f}  MAE_calib={res['multi']['mae_calib']:.2f}pp  "
          f"MAE_holdout={res['multi']['mae_holdout']:.2f}pp")
    print(f"Likelihood-ratio test (multivariado vs base): stat={res['lr_stat']:.2f}, "
          f"df={res['df_diff']}, p={res['lr_pvalue']:.4g}")
    print("\nVIF (multivariado):")
    print(res["vif"].to_string(index=False))
    print("\nCoeficientes candidatos con correccion Benjamini-Hochberg:")
    print(res["bh"].round(4).to_string(index=False))

    print("\n=== Modelos por regimen ===")
    por_reg = analizar_por_regimen(df)
    print(por_reg.to_string(index=False))

    # Entregable seccion 34 del prompt
    coefs_pooled = res["multi"]["model"].params.reset_index()
    coefs_pooled.columns = ["variable", "coef"]
    ci = res["multi"]["model"].conf_int()
    coefs_pooled["ci_low"] = ci[0].values
    coefs_pooled["ci_high"] = ci[1].values
    coefs_pooled["p_value"] = res["multi"]["model"].pvalues.values
    coefs_pooled["modelo"] = "pooled_multivariado"
    sufijo = "_corrected" if "corrected" in nombre_tabla else ""
    out_csv = os.path.join(_REPORTS_DIR, f"regression_results{sufijo}.csv")
    coefs_pooled.to_csv(out_csv, index=False, encoding="utf-8")
    por_reg_path = os.path.join(_REPORTS_DIR, f"regression_results_por_regimen{sufijo}.csv")
    por_reg.to_csv(por_reg_path, index=False, encoding="utf-8")
    print(f"\nGuardado: {out_csv}")
    print(f"Guardado: {por_reg_path}")


if __name__ == "__main__":
    main()
