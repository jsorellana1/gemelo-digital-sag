"""
Analisis diario de Teniente 8 como variable operacional continua.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import scipy.stats as stats
import statsmodels.api as sm
from matplotlib import pyplot as plt
from patsy import dmatrix
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.tsa.statespace.sarimax import SARIMAX

try:
    from xgboost import XGBRegressor
except ImportError:  # pragma: no cover - entorno sin xgboost
    XGBRegressor = None

from src.ingestion.loader import cargar_config, cargar_pam_mantto


ACTIVOS = ["SAG1", "SAG2", "PMC", "MUN"]
GRUPOS_COMPARABLES = [0.0, 2.0, 4.0, 12.0]


@dataclass
class AnalysisArtifacts:
    t8_master: pd.DataFrame
    daily_dataset: pd.DataFrame
    group_summary: pd.DataFrame
    exact_summary: pd.DataFrame
    linear_results: pd.DataFrame
    recovery_summary: pd.DataFrame
    tests_summary: pd.DataFrame
    tukey_summary: pd.DataFrame
    nonlinear_summary: pd.DataFrame
    threshold_summary: pd.DataFrame
    sarimax_summary: pd.DataFrame
    bayes_summary: pd.DataFrame
    ist8_summary: pd.DataFrame
    pila_summary: pd.DataFrame
    spline_predictions: pd.DataFrame


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _safe_mean(series: pd.Series) -> float:
    valid = series.dropna()
    return float(valid.mean()) if not valid.empty else np.nan


def _safe_min_oper(series: pd.Series) -> float:
    valid = series[series > 0]
    return float(valid.min()) if not valid.empty else np.nan


def _safe_max(series: pd.Series) -> float:
    valid = series.dropna()
    return float(valid.max()) if not valid.empty else np.nan


def _coerce_group_label(hours: float) -> str:
    return f"{int(hours)}h" if float(hours).is_integer() else f"{hours:.1f}h"


def build_t8_master(cfg: dict, prod_dates: pd.Series) -> pd.DataFrame:
    t8_positive = cargar_pam_mantto(cfg).copy()
    t8_positive["fecha"] = pd.to_datetime(t8_positive["fecha"]).dt.normalize()

    full_dates = pd.DataFrame(
        {
            "fecha": pd.date_range(
                pd.to_datetime(prod_dates.min()).normalize(),
                pd.to_datetime(prod_dates.max()).normalize(),
                freq="D",
            )
        }
    )
    t8_master = full_dates.merge(t8_positive, on="fecha", how="left")
    t8_master["horas_t8"] = t8_master["horas_t8"].fillna(0.0).astype(float)
    t8_master["grupo_t8"] = t8_master["horas_t8"].map(_coerce_group_label)
    return t8_master


def build_daily_dataset(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = Path(cfg["rutas"]["base"])
    fact_rend = pd.read_parquet(base / "data" / "processed" / "fact_rendimiento.parquet")
    fact_prod = pd.read_parquet(base / "data" / "processed" / "fact_produccion.parquet")

    fact_rend["fecha"] = pd.to_datetime(fact_rend["fecha"])
    fact_prod["fecha"] = pd.to_datetime(fact_prod["fecha"]).dt.normalize()

    t8_master = build_t8_master(cfg, fact_prod["fecha"])

    daily = (
        fact_rend.assign(fecha=fact_rend["fecha"].dt.normalize())
        .groupby(["fecha", "activo_id"], as_index=False)
        .agg(
            tph_promedio_operando=("tph", lambda s: _safe_mean(s[s > 0])),
            tph_max=("tph", _safe_max),
            tph_min_operando=("tph", _safe_min_oper),
            ton_real=("ton", "sum"),
            horas_op=("operando", lambda s: float(s.sum()) * 5.0 / 60.0),
        )
    )
    daily["utilizacion"] = daily["horas_op"] / 24.0
    daily["detenciones_h"] = 24.0 - daily["horas_op"]
    daily["tph_promedio_dia"] = daily["ton_real"] / 24.0

    daily = daily.merge(
        fact_prod[["fecha", "activo_id", "ton_prog"]],
        on=["fecha", "activo_id"],
        how="left",
    )
    daily["desviacion_ton"] = daily["ton_real"] - daily["ton_prog"]
    daily["desviacion_ton_pct"] = np.where(
        daily["ton_prog"].gt(0),
        (daily["ton_real"] - daily["ton_prog"]) / daily["ton_prog"] * 100.0,
        np.nan,
    )

    daily = daily.merge(t8_master[["fecha", "horas_t8", "grupo_t8"]], on="fecha", how="left")
    daily["horas_t8"] = daily["horas_t8"].fillna(0.0)
    daily["grupo_t8_objetivo"] = np.where(
        daily["horas_t8"].isin(GRUPOS_COMPARABLES),
        daily["horas_t8"].map(_coerce_group_label),
        "Otros",
    )
    daily["dia_semana"] = daily["fecha"].dt.dayofweek
    daily["mes"] = daily["fecha"].dt.month
    daily["semana_iso"] = daily["fecha"].dt.isocalendar().week.astype(int)

    daily = daily.sort_values(["activo_id", "fecha"]).reset_index(drop=True)
    for lag in [1, 2, 3, 7]:
        daily[f"horas_t8_lag{lag}"] = daily.groupby("activo_id")["horas_t8"].shift(lag)
    daily["horas_t8_roll3"] = (
        daily.groupby("activo_id")["horas_t8"].transform(lambda s: s.rolling(3, min_periods=1).mean())
    )
    daily["horas_t8_roll7"] = (
        daily.groupby("activo_id")["horas_t8"].transform(lambda s: s.rolling(7, min_periods=1).mean())
    )

    baseline = (
        daily.loc[daily["horas_t8"].eq(0)]
        .groupby("activo_id")["tph_promedio_operando"]
        .median()
        .rename("tph_baseline_0h")
    )
    daily = daily.merge(baseline, on="activo_id", how="left")
    daily["drop_pct_vs_0h"] = np.where(
        daily["tph_baseline_0h"].gt(0),
        (daily["tph_promedio_operando"] - daily["tph_baseline_0h"]) / daily["tph_baseline_0h"] * 100.0,
        np.nan,
    )
    daily["caida_rendimiento_10pct"] = daily["drop_pct_vs_0h"] <= -10.0
    return t8_master, daily


def build_group_summary(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    target = daily.loc[daily["horas_t8"].isin(GRUPOS_COMPARABLES)].copy()
    group_summary = (
        target.groupby(["activo_id", "horas_t8"], as_index=False)
        .agg(
            n_dias=("fecha", "count"),
            tph_promedio=("tph_promedio_operando", "mean"),
            tph_maximo=("tph_max", "mean"),
            tph_minimo=("tph_min_operando", "mean"),
            toneladas_dia=("ton_real", "mean"),
            utilizacion=("utilizacion", "mean"),
            detenciones_h=("detenciones_h", "mean"),
            ton_prog=("ton_prog", "mean"),
            desvio_ton_pct=("desviacion_ton_pct", "mean"),
        )
    )
    group_summary["grupo_t8"] = group_summary["horas_t8"].map(_coerce_group_label)

    exact_summary = (
        daily.groupby(["activo_id", "horas_t8"], as_index=False)
        .agg(
            n_dias=("fecha", "count"),
            tph_promedio=("tph_promedio_operando", "mean"),
            tph_dia_equiv=("tph_promedio_dia", "mean"),
            utilizacion=("utilizacion", "mean"),
            toneladas_dia=("ton_real", "mean"),
        )
        .sort_values(["activo_id", "horas_t8"])
    )
    exact_summary["grupo_t8"] = exact_summary["horas_t8"].map(_coerce_group_label)
    return group_summary, exact_summary


def run_stat_tests(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    tukey_rows: list[pd.DataFrame] = []

    for activo in ACTIVOS:
        subset = daily[
            daily["activo_id"].eq(activo)
            & daily["horas_t8"].isin(GRUPOS_COMPARABLES)
            & daily["tph_promedio_operando"].notna()
        ].copy()
        groups = {
            horas: grp["tph_promedio_operando"].dropna().to_numpy()
            for horas, grp in subset.groupby("horas_t8")
        }
        valid_groups = {k: v for k, v in groups.items() if len(v) >= 2}
        if len(valid_groups) < 2:
            continue

        ordered = [valid_groups[h] for h in sorted(valid_groups)]
        anova = stats.f_oneway(*ordered)
        kruskal = stats.kruskal(*ordered)
        grand_mean = np.mean(np.concatenate(ordered))
        ss_between = sum(len(v) * (np.mean(v) - grand_mean) ** 2 for v in ordered)
        ss_total = sum(((v - grand_mean) ** 2).sum() for v in ordered)
        eta_sq = ss_between / ss_total if ss_total else np.nan

        rows.append(
            {
                "activo_id": activo,
                "grupos": ", ".join(_coerce_group_label(h) for h in sorted(valid_groups)),
                "anova_f": anova.statistic,
                "anova_p": anova.pvalue,
                "eta_sq": eta_sq,
                "kruskal_h": kruskal.statistic,
                "kruskal_p": kruskal.pvalue,
            }
        )

        tukey_df = subset[subset["horas_t8"].isin(valid_groups)].copy()
        tukey = pairwise_tukeyhsd(
            endog=tukey_df["tph_promedio_operando"],
            groups=tukey_df["horas_t8"].map(_coerce_group_label),
            alpha=0.05,
        )
        tk = pd.DataFrame(tukey.summary().data[1:], columns=tukey.summary().data[0])
        tk.insert(0, "activo_id", activo)
        tukey_rows.append(tk)

    tests_df = pd.DataFrame(rows)
    tukey_df = pd.concat(tukey_rows, ignore_index=True) if tukey_rows else pd.DataFrame()
    return tests_df, tukey_df


def fit_linear_models(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    lag_map = {
        "horas_t8": 0,
        "horas_t8_lag1": 1,
        "horas_t8_lag2": 2,
        "horas_t8_lag3": 3,
        "horas_t8_lag7": 7,
    }

    for activo in ACTIVOS:
        subset = daily[daily["activo_id"].eq(activo)].copy()
        for feature, lag_dias in lag_map.items():
            model_df = subset[[feature, "tph_promedio_operando"]].dropna()
            if len(model_df) < 20:
                continue
            X = sm.add_constant(model_df[[feature]])
            model = sm.OLS(model_df["tph_promedio_operando"], X).fit()
            ci = model.conf_int().loc[feature]
            rows.append(
                {
                    "activo_id": activo,
                    "feature": feature,
                    "lag_dias": lag_dias,
                    "pendiente_tph_por_hora": model.params[feature],
                    "ic_95_lo": ci[0],
                    "ic_95_hi": ci[1],
                    "p_value": model.pvalues[feature],
                    "r2": model.rsquared,
                    "n_obs": len(model_df),
                }
            )
    return pd.DataFrame(rows)


def infer_recovery(linear_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for activo in ACTIVOS:
        subset = linear_results[
            linear_results["activo_id"].eq(activo)
            & linear_results["lag_dias"].isin([0, 1, 2, 3])
        ].sort_values("lag_dias")
        sig_negative = subset[
            subset["pendiente_tph_por_hora"].lt(0) & subset["p_value"].lt(0.10)
        ]
        if sig_negative.empty:
            recovery_h = 24.0
            status = "sin evidencia fuerte de arrastre >24h"
        else:
            last_lag = int(sig_negative["lag_dias"].max())
            recovery_h = float((last_lag + 1) * 24)
            status = f"efecto negativo visible hasta lag {last_lag}"
        rows.append(
            {
                "activo_id": activo,
                "recuperacion_estimada_h": recovery_h,
                "interpretacion": status,
            }
        )
    return pd.DataFrame(rows)


def _time_series_cv(
    X: pd.DataFrame,
    y: pd.Series,
    estimator,
    n_splits: int = 4,
) -> tuple[float, float]:
    if len(X) < 30:
        return np.nan, np.nan
    n_splits = min(n_splits, max(2, len(X) // 20))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    maes: list[float] = []
    r2s: list[float] = []
    for train_idx, test_idx in tscv.split(X):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        estimator.fit(X_train, y_train)
        pred = estimator.predict(X_test)
        maes.append(mean_absolute_error(y_test, pred))
        r2s.append(r2_score(y_test, pred))
    return float(np.mean(maes)), float(np.mean(r2s))


def _build_spline_predictions(model_df: pd.DataFrame, activo: str) -> tuple[pd.DataFrame, dict]:
    hours_max = max(12.0, float(model_df["horas_t8"].max()))
    spline_X = dmatrix(
        "0 + bs(horas_t8, df=4, degree=3, include_intercept=False)",
        {"horas_t8": model_df["horas_t8"]},
        return_type="dataframe",
    )
    fitted = sm.OLS(model_df["tph_promedio_operando"], sm.add_constant(spline_X)).fit()

    grid = pd.DataFrame({"horas_t8": np.linspace(0.0, hours_max, 200)})
    grid_basis = dmatrix(
        "0 + bs(horas_t8, df=4, degree=3, include_intercept=False)",
        {"horas_t8": grid["horas_t8"]},
        return_type="dataframe",
    )
    grid["activo_id"] = activo
    grid["tph_pred"] = fitted.predict(sm.add_constant(grid_basis, has_constant="add"))
    baseline = float(grid.loc[grid["horas_t8"].sub(0).abs().idxmin(), "tph_pred"])
    grid["drop_pct_pred"] = np.where(
        baseline != 0,
        (grid["tph_pred"] - baseline) / baseline * 100.0,
        np.nan,
    )

    moderate = grid.loc[grid["drop_pct_pred"].le(-5.0), "horas_t8"]
    severe = grid.loc[grid["drop_pct_pred"].le(-10.0), "horas_t8"]
    threshold = {
        "activo_id": activo,
        "threshold_5pct_h": float(moderate.iloc[0]) if not moderate.empty else np.nan,
        "threshold_10pct_h": float(severe.iloc[0]) if not severe.empty else np.nan,
    }
    return grid, threshold


def fit_nonlinear_models(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    spline_rows: list[pd.DataFrame] = []
    thresholds: list[dict] = []
    features = [
        "horas_t8",
        "horas_t8_lag1",
        "horas_t8_lag2",
        "horas_t8_lag3",
        "horas_t8_lag7",
        "horas_t8_roll3",
        "horas_t8_roll7",
        "ton_prog",
        "dia_semana",
        "mes",
    ]

    for activo in ACTIVOS:
        subset = daily[daily["activo_id"].eq(activo)].copy().sort_values("fecha")
        model_df = subset[features + ["tph_promedio_operando"]].dropna()
        if len(model_df) < 30:
            continue

        X = model_df[features]
        y = model_df["tph_promedio_operando"]

        rf = RandomForestRegressor(
            n_estimators=300,
            max_depth=5,
            min_samples_leaf=4,
            random_state=42,
        )
        rf_mae, rf_r2 = _time_series_cv(X, y, rf)
        rf.fit(X, y)
        rows.append(
            {
                "activo_id": activo,
                "modelo": "RandomForest",
                "cv_mae": rf_mae,
                "cv_r2": rf_r2,
                "top_feature": features[int(np.argmax(rf.feature_importances_))],
            }
        )

        if XGBRegressor is not None:
            xgb = XGBRegressor(
                n_estimators=250,
                learning_rate=0.05,
                max_depth=4,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                objective="reg:squarederror",
                n_jobs=1,
            )
            xgb_mae, xgb_r2 = _time_series_cv(X, y, xgb)
            xgb.fit(X, y)
            rows.append(
                {
                    "activo_id": activo,
                    "modelo": "XGBoost",
                    "cv_mae": xgb_mae,
                    "cv_r2": xgb_r2,
                    "top_feature": features[int(np.argmax(xgb.feature_importances_))],
                }
            )

        same_day_df = subset[["horas_t8", "tph_promedio_operando"]].dropna()
        if len(same_day_df) >= 20:
            spline_pred, threshold = _build_spline_predictions(same_day_df, activo)
            spline_rows.append(spline_pred)
            thresholds.append(threshold)
            rows.append(
                {
                    "activo_id": activo,
                    "modelo": "SplineGAM",
                    "cv_mae": np.nan,
                    "cv_r2": np.nan,
                    "top_feature": "horas_t8",
                }
            )

    nonlinear_df = pd.DataFrame(rows)
    spline_df = pd.concat(spline_rows, ignore_index=True) if spline_rows else pd.DataFrame()
    threshold_df = pd.DataFrame(thresholds)
    return nonlinear_df, spline_df, threshold_df


def fit_sarimax_models(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for activo in ACTIVOS:
        subset = daily[daily["activo_id"].eq(activo)].copy().sort_values("fecha")
        series_df = subset[["tph_promedio_dia", "horas_t8"]].dropna()
        if len(series_df) < 40:
            continue
        try:
            model = SARIMAX(
                endog=series_df["tph_promedio_dia"],
                exog=series_df[["horas_t8"]],
                order=(1, 0, 0),
                trend="c",
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            result = model.fit(disp=False)
            coef = result.params.get("horas_t8", np.nan)
            pvalue = result.pvalues.get("horas_t8", np.nan)
            rows.append(
                {
                    "activo_id": activo,
                    "coef_horas_t8": coef,
                    "p_value": pvalue,
                    "aic": result.aic,
                }
            )
        except Exception as exc:  # pragma: no cover - defensa operacional
            rows.append(
                {
                    "activo_id": activo,
                    "coef_horas_t8": np.nan,
                    "p_value": np.nan,
                    "aic": np.nan,
                    "error": str(exc),
                }
            )
    return pd.DataFrame(rows)


def compute_bayesian_probabilities(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for activo in ACTIVOS:
        subset = daily[daily["activo_id"].eq(activo)].copy()
        for horas in [2.0, 4.0, 12.0]:
            group = subset[
                subset["horas_t8"].eq(horas) & subset["caida_rendimiento_10pct"].notna()
            ]
            n = len(group)
            if n == 0:
                continue
            k = int(group["caida_rendimiento_10pct"].sum())
            alpha = 1 + k
            beta = 1 + (n - k)
            lo, hi = stats.beta.interval(0.90, alpha, beta)
            rows.append(
                {
                    "activo_id": activo,
                    "horas_t8": horas,
                    "n_dias": n,
                    "n_caidas": k,
                    "p_posterior": alpha / (alpha + beta),
                    "ic90_lo": lo,
                    "ic90_hi": hi,
                }
            )
    return pd.DataFrame(rows)


def compute_ist8(daily: pd.DataFrame) -> pd.DataFrame:
    data = daily[
        daily["horas_t8"].gt(0)
        & daily["tph_promedio_operando"].notna()
        & daily["tph_baseline_0h"].notna()
    ].copy()
    data["perdida_tph"] = np.maximum(data["tph_baseline_0h"] - data["tph_promedio_operando"], 0.0)
    data["ist8_diario"] = np.where(data["horas_t8"].gt(0), data["perdida_tph"] / data["horas_t8"], np.nan)

    summary = (
        data.groupby("activo_id", as_index=False)
        .agg(
            ist8_promedio=("ist8_diario", "mean"),
            ist8_mediana=("ist8_diario", "median"),
            perdida_tph_media=("perdida_tph", "mean"),
        )
        .sort_values("ist8_promedio", ascending=False)
        .reset_index(drop=True)
    )
    summary["ranking_ist8"] = np.arange(1, len(summary) + 1)
    return summary


def compute_pila_proxy(daily: pd.DataFrame, recovery: pd.DataFrame) -> pd.DataFrame:
    data = daily.merge(recovery[["activo_id", "recuperacion_estimada_h"]], on="activo_id", how="left")
    data = data[data["horas_t8"].gt(0)].copy()
    data["perdida_pct_pos"] = np.maximum(-data["drop_pct_vs_0h"], 0.0)
    data["indice_consumo_pila"] = (
        data["horas_t8"] * data["perdida_pct_pos"] * (1.0 + data["recuperacion_estimada_h"] / 24.0)
    )
    summary = (
        data.groupby("activo_id", as_index=False)
        .agg(
            indice_consumo_pila_prom=("indice_consumo_pila", "mean"),
            agotamiento_pct_prom=("perdida_pct_pos", "mean"),
            recuperacion_h=("recuperacion_estimada_h", "mean"),
        )
        .sort_values("indice_consumo_pila_prom", ascending=False)
    )
    return summary


def save_figures(
    exact_summary: pd.DataFrame,
    spline_predictions: pd.DataFrame,
    linear_results: pd.DataFrame,
    fig_dir: Path,
) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)

    if not exact_summary.empty:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=False, sharey=False)
        axes = axes.flatten()
        for ax, activo in zip(axes, ACTIVOS):
            obs = exact_summary[exact_summary["activo_id"].eq(activo)]
            ax.plot(obs["horas_t8"], obs["tph_promedio"], marker="o", label="Promedio observado")
            pred = spline_predictions[spline_predictions["activo_id"].eq(activo)]
            if not pred.empty:
                ax.plot(pred["horas_t8"], pred["tph_pred"], linewidth=2, label="Spline")
            ax.set_title(activo)
            ax.set_xlabel("Horas T8")
            ax.set_ylabel("TPH promedio")
            ax.grid(alpha=0.2)
            ax.legend()
        fig.tight_layout()
        fig.savefig(fig_dir / "T8_dosis_respuesta.png", dpi=150)
        plt.close(fig)

    lag_df = linear_results[linear_results["lag_dias"].isin([0, 1, 2, 3])]
    if not lag_df.empty:
        fig, ax = plt.subplots(figsize=(12, 6))
        width = 0.18
        offsets = np.linspace(-0.27, 0.27, len(ACTIVOS))
        base = np.arange(4)
        for offset, activo in zip(offsets, ACTIVOS):
            subset = lag_df[lag_df["activo_id"].eq(activo)].sort_values("lag_dias")
            values = subset.set_index("lag_dias").reindex([0, 1, 2, 3])["pendiente_tph_por_hora"].to_numpy()
            ax.bar(base + offset, values, width=width, label=activo)
        ax.set_xticks(base, ["0d", "1d", "2d", "3d"])
        ax.set_ylabel("Pendiente TPH por hora T8")
        ax.set_xlabel("Lag")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
        fig.tight_layout()
        fig.savefig(fig_dir / "T8_efecto_lags.png", dpi=150)
        plt.close(fig)


def write_excel(artifacts: AnalysisArtifacts, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        artifacts.t8_master.to_excel(writer, sheet_name="T8_Master", index=False)
        artifacts.daily_dataset.to_excel(writer, sheet_name="Dataset_Diario", index=False)
        artifacts.group_summary.to_excel(writer, sheet_name="Comparativo_0_2_4_12", index=False)
        artifacts.exact_summary.to_excel(writer, sheet_name="Horas_Exactas", index=False)
        artifacts.linear_results.to_excel(writer, sheet_name="Elasticidad_Lags", index=False)
        artifacts.recovery_summary.to_excel(writer, sheet_name="Recuperacion", index=False)
        artifacts.tests_summary.to_excel(writer, sheet_name="ANOVA_Kruskal", index=False)
        artifacts.tukey_summary.to_excel(writer, sheet_name="Tukey", index=False)
        artifacts.nonlinear_summary.to_excel(writer, sheet_name="No_Lineal", index=False)
        artifacts.threshold_summary.to_excel(writer, sheet_name="Umbrales", index=False)
        artifacts.sarimax_summary.to_excel(writer, sheet_name="SARIMAX", index=False)
        artifacts.bayes_summary.to_excel(writer, sheet_name="Bayes", index=False)
        artifacts.ist8_summary.to_excel(writer, sheet_name="IST8", index=False)
        artifacts.pila_summary.to_excel(writer, sheet_name="Pila_Proxy", index=False)


def write_markdown(artifacts: AnalysisArtifacts, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    daily = artifacts.daily_dataset
    linear_same = artifacts.linear_results[artifacts.linear_results["lag_dias"].eq(0)].copy()
    linear_same = linear_same.sort_values("activo_id")
    lag_focus = artifacts.linear_results[artifacts.linear_results["lag_dias"].isin([1, 2, 3])].copy()

    period_text = f"{daily['fecha'].min().date()} a {daily['fecha'].max().date()}"
    observed_hours = ", ".join(
        _coerce_group_label(v)
        for v in sorted(daily["horas_t8"].dropna().unique().tolist())
    )

    lines = [
        "# Analisis Critico - Teniente 8 como Variable Operacional Continua",
        "",
        f"- Periodo analizado: {period_text}",
        f"- Valores observados de `horas_t8`: {observed_hours}",
        "- Grupos comparables formales: 0h, 2h, 4h, 12h",
        "- Nota: 16h y 24h se conservaron para curva dosis-respuesta y umbrales, pero tienen baja frecuencia muestral.",
        "",
        "## Hallazgos Clave",
        "",
    ]

    if not artifacts.ist8_summary.empty:
        top = artifacts.ist8_summary.sort_values("ranking_ist8").head(4)
        for _, row in top.iterrows():
            lines.append(
                f"- IST8 rank {int(row['ranking_ist8'])}: {row['activo_id']} con {row['ist8_promedio']:.2f} TPH perdidos por hora T8."
            )
        lines.append("")

    for _, row in linear_same.iterrows():
        direction = "reduce" if row["pendiente_tph_por_hora"] < 0 else "aumenta"
        lines.append(
            f"- {row['activo_id']}: el modelo lineal mismo dia estima que cada hora adicional de T8 {direction} "
            f"{abs(row['pendiente_tph_por_hora']):.2f} TPH (IC95% {row['ic_95_lo']:.2f} a {row['ic_95_hi']:.2f}, R2={row['r2']:.3f})."
        )
    lines.append("")

    if not artifacts.recovery_summary.empty:
        for _, row in artifacts.recovery_summary.iterrows():
            lines.append(
                f"- {row['activo_id']}: recuperacion estimada {row['recuperacion_estimada_h']:.0f} h; {row['interpretacion']}."
            )
        lines.append("")

    if not artifacts.threshold_summary.empty:
        lines.append("## Umbrales Dosis-Respuesta")
        lines.append("")
        for _, row in artifacts.threshold_summary.iterrows():
            t5 = "sin evidencia" if pd.isna(row["threshold_5pct_h"]) else f"{row['threshold_5pct_h']:.1f} h"
            t10 = "sin evidencia" if pd.isna(row["threshold_10pct_h"]) else f"{row['threshold_10pct_h']:.1f} h"
            lines.append(f"- {row['activo_id']}: umbral ~5% en {t5}; umbral ~10% en {t10}.")
        lines.append("")

    if not artifacts.tests_summary.empty:
        lines.append("## Significancia Estadistica")
        lines.append("")
        for _, row in artifacts.tests_summary.iterrows():
            lines.append(
                f"- {row['activo_id']}: ANOVA p={row['anova_p']:.4f}, Kruskal p={row['kruskal_p']:.4f}, eta^2={row['eta_sq']:.3f}."
            )
        lines.append("")

    if not artifacts.bayes_summary.empty:
        lines.append("## Probabilidad Bayesiana de Caida >10% vs baseline 0h")
        lines.append("")
        for _, row in artifacts.bayes_summary.iterrows():
            lines.append(
                f"- {row['activo_id']} | {int(row['horas_t8'])}h: P(caida)={row['p_posterior']:.2%} "
                f"(IC90% {row['ic90_lo']:.2%} - {row['ic90_hi']:.2%}, n={int(row['n_dias'])})."
            )
        lines.append("")

    lines.extend(
        [
            "## Cautelas",
            "",
            "- Los grupos de 12h, 16h y 24h tienen pocos dias observados; sirven para detectar severidad, no para sobreinterpretar precision.",
            "- El lag de 7 dias puede mezclar efecto real con periodicidad semanal de la operacion.",
            "- El `Indice_Consumo_Pila` generado es un proxy operacional, no una medicion fisica directa de stock.",
        ]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def run_analysis(cfg_path: Path | None = None) -> AnalysisArtifacts:
    cfg_path = cfg_path or (_repo_root() / "config" / "config.yaml")
    cfg = cargar_config(cfg_path)

    t8_master, daily = build_daily_dataset(cfg)
    group_summary, exact_summary = build_group_summary(daily)
    tests_summary, tukey_summary = run_stat_tests(daily)
    linear_results = fit_linear_models(daily)
    recovery_summary = infer_recovery(linear_results)
    nonlinear_summary, spline_predictions, threshold_summary = fit_nonlinear_models(daily)
    sarimax_summary = fit_sarimax_models(daily)
    bayes_summary = compute_bayesian_probabilities(daily)
    ist8_summary = compute_ist8(daily)
    pila_summary = compute_pila_proxy(daily, recovery_summary)

    return AnalysisArtifacts(
        t8_master=t8_master,
        daily_dataset=daily,
        group_summary=group_summary,
        exact_summary=exact_summary,
        linear_results=linear_results,
        recovery_summary=recovery_summary,
        tests_summary=tests_summary,
        tukey_summary=tukey_summary,
        nonlinear_summary=nonlinear_summary,
        threshold_summary=threshold_summary,
        sarimax_summary=sarimax_summary,
        bayes_summary=bayes_summary,
        ist8_summary=ist8_summary,
        pila_summary=pila_summary,
        spline_predictions=spline_predictions,
    )


def main() -> None:
    root = _repo_root()
    artifacts = run_analysis(root / "config" / "config.yaml")
    save_figures(
        artifacts.exact_summary,
        artifacts.spline_predictions,
        artifacts.linear_results,
        root / "outputs" / "figures",
    )
    write_excel(artifacts, root / "outputs" / "excel" / "Analisis_T8_Intensidad.xlsx")
    write_markdown(artifacts, root / "outputs" / "reports" / "Analisis_T8_Intensidad.md")


if __name__ == "__main__":
    main()
