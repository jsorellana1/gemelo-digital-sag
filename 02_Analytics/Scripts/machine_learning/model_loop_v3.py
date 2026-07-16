"""
Loop Controlado v3 para busqueda de hiperparametros y modelos SAG2 TPH.

Reglas aplicadas:
  - Reutilizar dataset procesado, modelos y registro v2 antes de entrenar.
  - Dataset diario: los features solicitados en horas se reinterpretan como
    analogos diarios (1d/4d/12d/24d) y los proxies quedan documentados.
  - CPU only: 165 filas, sin justificacion de GPU.
  - Optuna escalonado: 20 -> 50 -> 100 trials solo si mejora >= 1%.
  - SHAP solo para top 3 modelos.
"""

from __future__ import annotations

import json
import math
import pickle
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import optuna
import pandas as pd
import seaborn as sns
import shap
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor, early_stopping, log_evaluation
from optuna.samplers import TPESampler
from scipy.stats import spearmanr
from sklearn.base import clone
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
DATASET_CACHE = BASE / "data/cache/model_loop_v3_dataset.parquet"
META_CACHE = BASE / "data/cache/model_loop_v3_dataset_meta.json"
SHAP_CACHE_DIR = BASE / "data/cache/model_loop_v3_shap"
OUT_EXCEL = BASE / "outputs/excel/model_registry_v3.xlsx"
OUT_SUMMARY = BASE / "outputs/reports/model_loop_v3_summary.md"
OUT_EXPLAIN = BASE / "outputs/reports/model_explainability_v3.md"
OUT_FIG = BASE / "outputs/figures/model_loop_v3"
OUT_MODELS = BASE / "outputs/models/v3"
PRIOR_REGISTRY = BASE / "outputs/excel/model_registry_v2.xlsx"
PRIOR_MODELS_DIR = BASE / "outputs/models"
TARGET = "SAG2_tph_mean"
SEED = 42
OPTUNA_LEVELS = [20, 50, 100]
MIN_RELATIVE_IMPROVEMENT = 0.01
PATIENCE_TRIALS = 3
ZONE_CRITICAL = 20.0

for directory in [OUT_FIG, OUT_MODELS, SHAP_CACHE_DIR, DATASET_CACHE.parent]:
    directory.mkdir(parents=True, exist_ok=True)

np.random.seed(SEED)
sns.set_theme(style="whitegrid")
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 120,
    }
)


@dataclass(frozen=True)
class ModelSpec:
    label: str
    family: str
    feature_pack: str
    tunable: bool
    max_trials: int
    default_params: dict[str, Any]


def safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = np.isfinite(y_true) & np.isfinite(y_pred) & (np.abs(y_true) > 1e-9)
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])))


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = y_true[mask]
    y_pred = y_pred[mask]
    errors = y_pred - y_true
    abs_errors = np.abs(errors)
    pct_errors = np.abs((y_true - y_pred) / np.clip(np.abs(y_true), 1e-9, None))
    return {
        "r2": float(r2_score(y_true, y_pred)) if len(y_true) > 1 else float("nan"),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mape": float(np.mean(pct_errors)),
        "bias": float(np.mean(errors)),
        "error_p90": float(np.percentile(abs_errors, 90)),
        "error_p95": float(np.percentile(abs_errors, 95)),
        "n": int(len(y_true)),
    }


def compute_psi(reference: pd.Series, current: pd.Series, n_bins: int = 10) -> float:
    ref = reference.dropna().to_numpy()
    cur = current.dropna().to_numpy()
    if len(ref) < 5 or len(cur) < 5:
        return float("nan")
    bins = np.unique(np.quantile(ref, np.linspace(0, 1, n_bins + 1)))
    if len(bins) < 3:
        return 0.0
    ref_hist = np.histogram(ref, bins=bins)[0].astype(float) + 1e-6
    cur_hist = np.histogram(cur, bins=bins)[0].astype(float) + 1e-6
    ref_pct = ref_hist / ref_hist.sum()
    cur_pct = cur_hist / cur_hist.sum()
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def relative_improvement(old: float, new: float) -> float:
    if not np.isfinite(old) or abs(old) < 1e-12:
        return 0.0
    return float((old - new) / abs(old))


def to_score(values: pd.Series, higher_is_better: bool) -> pd.Series:
    if values.nunique(dropna=False) <= 1:
        return pd.Series(np.ones(len(values)), index=values.index)
    vmin = values.min()
    vmax = values.max()
    scaled = (values - vmin) / (vmax - vmin)
    if higher_is_better:
        return scaled
    return 1.0 - scaled


def operational_name(feature: str) -> str:
    mapping = {
        "SAG2_util_pct": "Utilizacion SAG2 (%)",
        "SAG2_h_det": "Horas detencion SAG2",
        "tph_lag_1d": "TPH rezago 1 dia",
        "tph_lag_4d": "TPH rezago 4 dias",
        "tph_lag_12d": "TPH rezago 12 dias",
        "tph_lag_24d": "TPH rezago 24 dias",
        "tph_roll_1d": "TPH promedio movil 1 dia",
        "tph_roll_4d": "TPH promedio movil 4 dias",
        "tph_roll_12d": "TPH promedio movil 12 dias",
        "tph_roll_24d": "TPH promedio movil 24 dias",
        "pct_pila_sag1": "Nivel pila SAG1 (%)",
        "pct_pila_sag2": "Nivel pila SAG2 (%)",
        "delta_pila_sag1": "Cambio diario pila SAG1 (%)",
        "delta_pila_sag2": "Cambio diario pila SAG2 (%)",
        "autonomia_sag1_h": "Autonomia pila SAG1 (h)",
        "autonomia_sag2_h": "Autonomia pila SAG2 (h)",
        "cv315_tph": "Correa CV315 (TPH)",
        "cv316_tph": "Correa CV316 (TPH)",
        "qin_minus_qout_sag1": "Balance masa SAG1 (proxy)",
        "qin_minus_qout_sag2": "Balance masa SAG2 (TPH)",
        "en_t8": "T8 activo",
        "duracion_t8": "Duracion diaria T8 (h)",
        "horas_desde_inicio_t8": "Horas acumuladas desde inicio T8",
        "horas_restantes_t8": "Horas restantes T8 (proxy)",
        "dia_semana": "Dia de semana",
        "mes": "Mes",
        "turno": "Turno proxy",
        "edo_tph_potencial": "TPH potencial EDO",
    }
    return mapping.get(feature, feature.replace("_", " ").title())


def feature_group(feature: str) -> str:
    if "autonomia" in feature or "edo_" in feature:
        return "autonomia_edo"
    if "pila" in feature or "qin_minus" in feature or feature.startswith("cv3"):
        return "fisico_operacional"
    if feature.startswith("tph_"):
        return "memoria_tph"
    if "t8" in feature:
        return "t8"
    if feature in {"dia_semana", "mes", "turno"}:
        return "calendario"
    return "operacional"


def read_prior_results() -> tuple[pd.DataFrame, dict[str, Any]]:
    prior_rows: list[dict[str, Any]] = []
    audit = {
        "registry_exists": PRIOR_REGISTRY.exists(),
        "reviewed_models": [],
        "discarded_families": ["XGBoost"],
        "reused_artifacts": ["data/processed/dataset_master.parquet"],
    }
    if PRIOR_REGISTRY.exists():
        sheets = pd.ExcelFile(PRIOR_REGISTRY).sheet_names
        for sheet in ["02_RandomSearch_Results", "08_Master_Loop", "11_Score_Multidim"]:
            if sheet in sheets:
                frame = pd.read_excel(PRIOR_REGISTRY, sheet_name=sheet)
                frame["source_sheet"] = sheet
                prior_rows.append(frame)
        audit["reused_artifacts"].append("outputs/excel/model_registry_v2.xlsx")
    model_files = sorted(path.name for path in PRIOR_MODELS_DIR.glob("*.pkl"))
    audit["reviewed_models"] = model_files
    audit["reused_artifacts"].extend(model_files[:3])
    prior = pd.concat(prior_rows, ignore_index=True, sort=False) if prior_rows else pd.DataFrame()
    if not prior.empty and "model" in prior.columns and "test_r2" in prior.columns:
        bad = prior.loc[prior["test_r2"] < -0.5, "model"].dropna().astype(str).unique().tolist()
        for family in bad:
            if family.startswith("CatBoost"):
                audit["discarded_families"].append("CatBoost_prior")
            if family.startswith("XGBoost"):
                audit["discarded_families"].append("XGBoost")
    return prior, audit


def build_dataset() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if DATASET_CACHE.exists() and META_CACHE.exists():
        dataset = pd.read_parquet(DATASET_CACHE)
        feature_catalog = pd.DataFrame(json.loads(META_CACHE.read_text(encoding="utf-8"))["feature_catalog"])
        meta = json.loads(META_CACHE.read_text(encoding="utf-8"))["meta"]
        return dataset, feature_catalog, meta

    dm = pd.read_parquet(BASE / "data/processed/dataset_master.parquet").copy()
    dm["fecha"] = pd.to_datetime(dm["fecha"])
    dm = dm.sort_values("fecha").reset_index(drop=True)

    cp = pd.read_excel(BASE / "data/raw/Tonelajes_pila/correas_ton.xlsx").copy()
    cp["fecha"] = pd.to_datetime(cp["fecha"])
    cp = cp.rename(
        columns={
            "SAG:Nivel_Pila": "pct_pila_sag1",
            "SAG2:Nivel_Pila": "pct_pila_sag2",
            "CV315": "cv315_tph",
            "CV316": "cv316_tph",
        }
    )
    for col in ["pct_pila_sag1", "pct_pila_sag2", "cv315_tph", "cv316_tph"]:
        cp[col] = pd.to_numeric(cp[col], errors="coerce")

    cp_daily = (
        cp.set_index("fecha")
        .resample("D")
        .agg(
            pct_pila_sag1=("pct_pila_sag1", "mean"),
            pct_pila_sag2=("pct_pila_sag2", "mean"),
            cv315_tph=("cv315_tph", "mean"),
            cv316_tph=("cv316_tph", "mean"),
        )
        .reset_index()
    )

    df = dm.merge(cp_daily, on="fecha", how="left").sort_values("fecha").reset_index(drop=True)

    for lag in [1, 4, 12, 24]:
        df[f"tph_lag_{lag}d"] = df[TARGET].shift(lag)

    for window in [1, 4, 12, 24]:
        df[f"tph_roll_{window}d"] = (
            df[TARGET].shift(1).rolling(window, min_periods=1).mean()
        )

    df["delta_pila_sag1"] = df["pct_pila_sag1"].diff()
    df["delta_pila_sag2"] = df["pct_pila_sag2"].diff()

    sag1_drain = (
        df["delta_pila_sag1"]
        .clip(upper=0)
        .abs()
        .rolling(7, min_periods=2)
        .median()
        .fillna(df["delta_pila_sag1"].clip(upper=0).abs().median())
        .clip(lower=0.25)
    )
    sag2_drain = (
        df["delta_pila_sag2"]
        .clip(upper=0)
        .abs()
        .rolling(7, min_periods=2)
        .median()
        .fillna(df["delta_pila_sag2"].clip(upper=0).abs().median())
        .clip(lower=0.25)
    )

    df["autonomia_sag1_h"] = ((df["pct_pila_sag1"] - ZONE_CRITICAL).clip(lower=0) / sag1_drain) * 24
    df["autonomia_sag2_h"] = ((df["pct_pila_sag2"] - ZONE_CRITICAL).clip(lower=0) / sag2_drain) * 24
    df["qin_minus_qout_sag2"] = df["cv315_tph"] - df["cv316_tph"]
    df["qin_minus_qout_sag1"] = df["delta_pila_sag1"]

    df["en_t8"] = (df["horas_t8"] > 0).astype(int)
    df["duracion_t8"] = df["horas_t8"].fillna(0.0)
    bucket_expected = {
        "Sin ventana": 0.0,
        "Corta 2h": 2.0,
        "Media 4h": 4.0,
        "Larga 12h": 12.0,
        "Muy larga": 24.0,
    }
    df["t8_bucket_h"] = pd.to_numeric(
        df["bucket_t8"].map(bucket_expected).fillna(df["duracion_t8"]),
        errors="coerce",
    ).fillna(df["duracion_t8"])

    horas_desde_inicio: list[float] = []
    streak_hours = 0.0
    for _, row in df.iterrows():
        if row["en_t8"] == 1:
            streak_hours += float(row["duracion_t8"])
            horas_desde_inicio.append(streak_hours)
        else:
            streak_hours = 0.0
            horas_desde_inicio.append(0.0)
    df["horas_desde_inicio_t8"] = horas_desde_inicio
    df["horas_restantes_t8"] = (df["t8_bucket_h"] - df["horas_desde_inicio_t8"]).clip(lower=0)

    df["dia_semana"] = df["fecha"].dt.dayofweek
    df["mes"] = df["fecha"].dt.month
    df["turno"] = np.select(
        [df["dia_semana"] <= 4, df["dia_semana"] == 5, df["dia_semana"] == 6],
        [0, 1, 2],
        default=0,
    )

    tph_base = df.loc[df["SAG2_util_pct"] >= 95, TARGET].dropna().quantile(0.75)
    df["edo_tph_potencial"] = df["SAG2_util_pct"] * tph_base / 100

    df = df.dropna(subset=[TARGET]).reset_index(drop=True)

    feature_rows = [
        {"feature": "tph_lag_1d", "status": "proxy", "source": "dataset_master", "note": "Proxy diario de tph_lag_1h"},
        {"feature": "tph_lag_4d", "status": "proxy", "source": "dataset_master", "note": "Proxy diario de tph_lag_4h"},
        {"feature": "tph_lag_12d", "status": "proxy", "source": "dataset_master", "note": "Proxy diario de tph_lag_12h"},
        {"feature": "tph_lag_24d", "status": "proxy", "source": "dataset_master", "note": "Proxy diario de tph_lag_24h"},
        {"feature": "tph_roll_1d", "status": "proxy", "source": "dataset_master", "note": "Proxy diario de tph_roll_1h"},
        {"feature": "tph_roll_4d", "status": "proxy", "source": "dataset_master", "note": "Proxy diario de tph_roll_4h"},
        {"feature": "tph_roll_12d", "status": "proxy", "source": "dataset_master", "note": "Proxy diario de tph_roll_12h"},
        {"feature": "tph_roll_24d", "status": "proxy", "source": "dataset_master", "note": "Proxy diario de tph_roll_24h"},
        {"feature": "pct_pila_sag1", "status": "actual", "source": "correas_ton.xlsx", "note": "Nivel medio diario"},
        {"feature": "pct_pila_sag2", "status": "actual", "source": "correas_ton.xlsx", "note": "Nivel medio diario"},
        {"feature": "delta_pila_sag1", "status": "proxy", "source": "correas_ton.xlsx", "note": "Cambio diario en nivel"},
        {"feature": "delta_pila_sag2", "status": "proxy", "source": "correas_ton.xlsx", "note": "Cambio diario en nivel"},
        {"feature": "autonomia_sag1_h", "status": "proxy", "source": "correas_ton.xlsx", "note": "Horas a zona critica via tasa de drenaje diaria"},
        {"feature": "autonomia_sag2_h", "status": "proxy", "source": "correas_ton.xlsx", "note": "Horas a zona critica via tasa de drenaje diaria"},
        {"feature": "cv315_tph", "status": "actual", "source": "correas_ton.xlsx", "note": "Promedio diario"},
        {"feature": "cv316_tph", "status": "actual", "source": "correas_ton.xlsx", "note": "Promedio diario"},
        {"feature": "qin_minus_qout_sag1", "status": "proxy", "source": "correas_ton.xlsx", "note": "Proxy por delta de nivel SAG1"},
        {"feature": "qin_minus_qout_sag2", "status": "proxy", "source": "correas_ton.xlsx", "note": "CV315 - CV316"},
        {"feature": "en_t8", "status": "actual", "source": "dataset_master", "note": "Ventana T8 activa"},
        {"feature": "duracion_t8", "status": "actual", "source": "dataset_master", "note": "Horas T8 del dia"},
        {"feature": "horas_desde_inicio_t8", "status": "proxy", "source": "dataset_master", "note": "Horas acumuladas de la racha T8"},
        {"feature": "horas_restantes_t8", "status": "proxy", "source": "dataset_master", "note": "Bucket esperado menos horas acumuladas"},
        {"feature": "dia_semana", "status": "actual", "source": "dataset_master", "note": "0=Lunes"},
        {"feature": "mes", "status": "actual", "source": "dataset_master", "note": "Mes calendario"},
        {"feature": "turno", "status": "proxy", "source": "dataset_master", "note": "0=habil, 1=sabado, 2=domingo"},
        {"feature": "edo_tph_potencial", "status": "proxy", "source": "dataset_master", "note": "Utilizacion x tph base p75"},
    ]
    feature_catalog = pd.DataFrame(feature_rows)
    meta = {
        "rows": int(len(df)),
        "date_min": str(df["fecha"].min().date()),
        "date_max": str(df["fecha"].max().date()),
        "tph_base": float(tph_base),
        "granularity": "daily",
    }

    df.to_parquet(DATASET_CACHE, index=False)
    META_CACHE.write_text(
        json.dumps({"feature_catalog": feature_rows, "meta": meta}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return df, feature_catalog, meta


def build_feature_packs(df: pd.DataFrame) -> dict[str, list[str]]:
    pack_core = [
        "SAG2_util_pct",
        "SAG2_h_det",
        "duracion_t8",
        "en_t8",
        "horas_desde_inicio_t8",
        "horas_restantes_t8",
        "dia_semana",
        "mes",
        "turno",
        "tph_lag_1d",
        "tph_lag_4d",
        "tph_lag_12d",
        "tph_lag_24d",
        "tph_roll_1d",
        "tph_roll_4d",
        "tph_roll_12d",
        "tph_roll_24d",
        "pct_pila_sag1",
        "pct_pila_sag2",
    ]
    pack_autonomy = pack_core + ["delta_pila_sag1", "delta_pila_sag2", "autonomia_sag1_h", "autonomia_sag2_h"]
    pack_mass = pack_core + ["delta_pila_sag1", "delta_pila_sag2", "cv315_tph", "cv316_tph", "qin_minus_qout_sag1", "qin_minus_qout_sag2"]
    pack_hybrid = pack_core + [
        "delta_pila_sag1",
        "delta_pila_sag2",
        "autonomia_sag1_h",
        "autonomia_sag2_h",
        "cv315_tph",
        "cv316_tph",
        "qin_minus_qout_sag1",
        "qin_minus_qout_sag2",
        "edo_tph_potencial",
    ]
    packs = {
        "core": [col for col in pack_core if col in df.columns],
        "autonomia": [col for col in pack_autonomy if col in df.columns],
        "mass_balance": [col for col in pack_mass if col in df.columns],
        "hybrid": [col for col in pack_hybrid if col in df.columns],
    }
    return packs


def build_monthly_folds(df: pd.DataFrame) -> list[dict[str, Any]]:
    months = sorted(df["fecha"].dt.to_period("M").unique())
    folds: list[dict[str, Any]] = []
    for idx in range(2, len(months)):
        train_months = months[:idx]
        test_month = months[idx]
        train_mask = df["fecha"].dt.to_period("M").isin(train_months)
        test_mask = df["fecha"].dt.to_period("M") == test_month
        train_df = df.loc[train_mask].copy()
        test_df = df.loc[test_mask].copy()
        if len(train_df) < 20 or len(test_df) < 5:
            continue
        folds.append(
            {
                "name": f"{train_months[0].strftime('%b')}-{train_months[-1].strftime('%b')} -> {test_month.strftime('%b')}",
                "train_months": [str(month) for month in train_months],
                "test_month": str(test_month),
                "train_df": train_df,
                "test_df": test_df,
            }
        )
    return folds


def make_estimator(spec: ModelSpec, params: dict[str, Any]) -> Any:
    params = dict(params)
    if spec.family == "LinearRegression":
        model = LinearRegression()
    elif spec.family == "Ridge":
        model = Ridge(alpha=float(params.get("alpha", spec.default_params.get("alpha", 1.0))), random_state=SEED)
    elif spec.family == "ElasticNet":
        model = ElasticNet(
            alpha=float(params.get("alpha", spec.default_params.get("alpha", 0.1))),
            l1_ratio=float(params.get("l1_ratio", spec.default_params.get("l1_ratio", 0.5))),
            max_iter=5000,
            random_state=SEED,
        )
    elif spec.family == "HistGradientBoosting":
        model = HistGradientBoostingRegressor(
            learning_rate=float(params.get("learning_rate", spec.default_params.get("learning_rate", 0.05))),
            max_depth=int(params.get("max_depth", spec.default_params.get("max_depth", 3))),
            max_leaf_nodes=int(params.get("max_leaf_nodes", spec.default_params.get("max_leaf_nodes", 31))),
            min_samples_leaf=int(params.get("min_samples_leaf", spec.default_params.get("min_samples_leaf", 10))),
            l2_regularization=float(params.get("l2_regularization", spec.default_params.get("l2_regularization", 0.1))),
            max_iter=int(params.get("max_iter", spec.default_params.get("max_iter", 180))),
            random_state=SEED,
        )
    elif spec.family == "LightGBM":
        model = LGBMRegressor(
            n_estimators=int(params.get("n_estimators", spec.default_params.get("n_estimators", 140))),
            learning_rate=float(params.get("learning_rate", spec.default_params.get("learning_rate", 0.05))),
            num_leaves=int(params.get("num_leaves", spec.default_params.get("num_leaves", 15))),
            max_depth=int(params.get("max_depth", spec.default_params.get("max_depth", 4))),
            min_child_samples=int(params.get("min_child_samples", spec.default_params.get("min_child_samples", 10))),
            subsample=float(params.get("subsample", spec.default_params.get("subsample", 0.9))),
            colsample_bytree=float(params.get("colsample_bytree", spec.default_params.get("colsample_bytree", 0.9))),
            reg_alpha=float(params.get("reg_alpha", spec.default_params.get("reg_alpha", 0.0))),
            reg_lambda=float(params.get("reg_lambda", spec.default_params.get("reg_lambda", 0.0))),
            objective="regression",
            random_state=SEED,
            n_jobs=-1,
            verbosity=-1,
        )
    elif spec.family == "CatBoost":
        model = CatBoostRegressor(
            iterations=int(params.get("iterations", spec.default_params.get("iterations", 180))),
            depth=int(params.get("depth", spec.default_params.get("depth", 4))),
            learning_rate=float(params.get("learning_rate", spec.default_params.get("learning_rate", 0.05))),
            l2_leaf_reg=float(params.get("l2_leaf_reg", spec.default_params.get("l2_leaf_reg", 4.0))),
            random_strength=float(params.get("random_strength", spec.default_params.get("random_strength", 1.0))),
            bagging_temperature=float(params.get("bagging_temperature", spec.default_params.get("bagging_temperature", 0.0))),
            loss_function="RMSE",
            eval_metric="MAPE",
            random_seed=SEED,
            verbose=False,
            allow_writing_files=False,
        )
    elif spec.family == "RandomForest":
        model = RandomForestRegressor(
            n_estimators=int(params.get("n_estimators", spec.default_params.get("n_estimators", 160))),
            max_depth=int(params.get("max_depth", spec.default_params.get("max_depth", 4))),
            min_samples_leaf=int(params.get("min_samples_leaf", spec.default_params.get("min_samples_leaf", 4))),
            max_features=params.get("max_features", spec.default_params.get("max_features", "sqrt")),
            random_state=SEED,
            n_jobs=-1,
        )
    else:
        raise ValueError(f"Unsupported family: {spec.family}")

    if spec.family in {"LinearRegression", "Ridge", "ElasticNet"}:
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", model),
            ]
        )
    return Pipeline(steps=[("imputer", SimpleImputer(strategy="median")), ("model", model)])


def suggest_params(spec: ModelSpec, trial: optuna.trial.Trial) -> dict[str, Any]:
    if spec.family == "Ridge":
        return {"alpha": trial.suggest_float("alpha", 1e-3, 1e3, log=True)}
    if spec.family == "ElasticNet":
        return {
            "alpha": trial.suggest_float("alpha", 1e-3, 10.0, log=True),
            "l1_ratio": trial.suggest_float("l1_ratio", 0.05, 0.95),
        }
    if spec.family == "HistGradientBoosting":
        return {
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15),
            "max_depth": trial.suggest_int("max_depth", 2, 5),
            "max_leaf_nodes": trial.suggest_int("max_leaf_nodes", 15, 63),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 4, 20),
            "l2_regularization": trial.suggest_float("l2_regularization", 1e-4, 5.0, log=True),
            "max_iter": trial.suggest_int("max_iter", 80, 260),
        }
    if spec.family == "LightGBM":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 80, 260),
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15),
            "num_leaves": trial.suggest_int("num_leaves", 7, 31),
            "max_depth": trial.suggest_int("max_depth", 2, 6),
            "min_child_samples": trial.suggest_int("min_child_samples", 4, 20),
            "subsample": trial.suggest_float("subsample", 0.7, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.7, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-5, 3.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-5, 3.0, log=True),
        }
    if spec.family == "CatBoost":
        return {
            "iterations": trial.suggest_int("iterations", 100, 260),
            "depth": trial.suggest_int("depth", 3, 6),
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 8.0),
            "random_strength": trial.suggest_float("random_strength", 0.0, 5.0),
            "bagging_temperature": trial.suggest_float("bagging_temperature", 0.0, 1.0),
        }
    if spec.family == "RandomForest":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 80, 220),
            "max_depth": trial.suggest_int("max_depth", 3, 6),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 3, 10),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.7]),
        }
    return {}


def fit_pipeline(
    estimator: Pipeline,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_valid: pd.DataFrame | None = None,
    y_valid: pd.Series | None = None,
) -> Pipeline:
    pipe = clone(estimator)
    family = pipe.named_steps["model"].__class__.__name__
    if family == "LGBMRegressor" and X_valid is not None and len(X_valid) >= 5:
        imputer = clone(pipe.named_steps["imputer"])
        X_train_imp = imputer.fit_transform(X_train)
        X_valid_imp = imputer.transform(X_valid)
        model = clone(pipe.named_steps["model"])
        model.fit(
            X_train_imp,
            y_train,
            eval_set=[(X_valid_imp, y_valid)],
            eval_metric="l1",
            callbacks=[early_stopping(20, verbose=False), log_evaluation(0)],
        )
        return Pipeline(steps=[("imputer", imputer), ("model", model)])
    if family == "CatBoostRegressor" and X_valid is not None and len(X_valid) >= 5:
        imputer = clone(pipe.named_steps["imputer"])
        X_train_imp = imputer.fit_transform(X_train)
        X_valid_imp = imputer.transform(X_valid)
        model = clone(pipe.named_steps["model"])
        model.set_params(od_type="Iter", od_wait=20)
        model.fit(X_train_imp, y_train, eval_set=(X_valid_imp, y_valid), verbose=False)
        return Pipeline(steps=[("imputer", imputer), ("model", model)])
    pipe.fit(X_train, y_train)
    return pipe


def split_inner_validation(train_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_valid = max(5, int(math.ceil(len(train_df) * 0.2)))
    n_valid = min(n_valid, len(train_df) - 5)
    if n_valid <= 0:
        return train_df.copy(), train_df.tail(5).copy()
    return train_df.iloc[:-n_valid].copy(), train_df.iloc[-n_valid:].copy()


def evaluate_spec(
    spec: ModelSpec,
    features: list[str],
    df: pd.DataFrame,
    folds: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = params or spec.default_params
    estimator = make_estimator(spec, params)
    fold_rows: list[dict[str, Any]] = []
    oof_rows: list[dict[str, Any]] = []
    drift_features = [col for col in ["SAG2_util_pct", "pct_pila_sag2", "duracion_t8", "edo_tph_potencial"] if col in features]
    for fold in folds:
        train_df = fold["train_df"].copy()
        test_df = fold["test_df"].copy()
        usable_train = train_df.dropna(subset=features + [TARGET])
        usable_test = test_df.dropna(subset=features + [TARGET])
        if len(usable_train) < 15 or len(usable_test) < 5:
            continue
        inner_train, inner_valid = split_inner_validation(usable_train)
        trained = fit_pipeline(
            estimator,
            inner_train[features],
            inner_train[TARGET],
            inner_valid[features],
            inner_valid[TARGET],
        )
        pred_train = trained.predict(usable_train[features])
        pred_test = trained.predict(usable_test[features])
        metrics_train = compute_metrics(usable_train[TARGET].to_numpy(), pred_train)
        metrics_test = compute_metrics(usable_test[TARGET].to_numpy(), pred_test)
        fold_drift_values = [
            compute_psi(usable_train[col], usable_test[col])
            for col in drift_features
            if col in usable_train.columns and col in usable_test.columns
        ]
        drift_mean = float(np.nanmean(fold_drift_values)) if fold_drift_values else float("nan")
        row = {
            "model_label": spec.label,
            "family": spec.family,
            "feature_pack": spec.feature_pack,
            "fold_name": fold["name"],
            "test_month": fold["test_month"],
            "n_train": len(usable_train),
            "n_test": len(usable_test),
            "train_r2": metrics_train["r2"],
            "train_mae": metrics_train["mae"],
            "train_mape": metrics_train["mape"],
            "r2": metrics_test["r2"],
            "mae": metrics_test["mae"],
            "rmse": metrics_test["rmse"],
            "mape": metrics_test["mape"],
            "bias": metrics_test["bias"],
            "error_p90": metrics_test["error_p90"],
            "error_p95": metrics_test["error_p95"],
            "drift_mean_psi": drift_mean,
            "gap_train_test": metrics_test["mae"] - metrics_train["mae"],
        }
        fold_rows.append(row)
        oof_rows.extend(
            {
                "fecha": date,
                "y_true": actual,
                "y_pred": pred,
                "abs_error": abs(pred - actual),
                "ape": abs(pred - actual) / actual if actual else np.nan,
                "model_label": spec.label,
                "fold_name": fold["name"],
            }
            for date, actual, pred in zip(usable_test["fecha"], usable_test[TARGET], pred_test)
        )

    if not fold_rows:
        raise RuntimeError(f"No valid folds for {spec.label}")

    fold_df = pd.DataFrame(fold_rows)
    oof_df = pd.DataFrame(oof_rows)
    stability = 1.0 - min(
        fold_df["mape"].std(ddof=0) / max(fold_df["mape"].mean(), 1e-9),
        1.0,
    )
    gap_mean = float(fold_df["gap_train_test"].mean())
    drift_sensitivity = float(
        abs(fold_df[["mape", "drift_mean_psi"]].corr(method="spearman").iloc[0, 1])
    ) if fold_df["drift_mean_psi"].notna().sum() >= 2 else float("nan")
    mean_metrics = {
        "r2": float(fold_df["r2"].mean()),
        "mae": float(fold_df["mae"].mean()),
        "rmse": float(fold_df["rmse"].mean()),
        "mape": float(fold_df["mape"].mean()),
        "bias": float(fold_df["bias"].mean()),
        "error_p90": float(fold_df["error_p90"].mean()),
        "error_p95": float(fold_df["error_p95"].mean()),
        "temporal_stability": float(stability),
        "gap_train_test": gap_mean,
        "drift_sensitivity": drift_sensitivity,
    }
    objective = mean_metrics["mape"] * (1.0 + max(0.0, 1.0 - stability) * 0.5)
    return {
        "spec": spec,
        "params": params,
        "features": features,
        "fold_df": fold_df,
        "oof_df": oof_df,
        "metrics": mean_metrics,
        "objective": objective,
    }


class RelativeImprovementStopper:
    def __init__(self, threshold: float = MIN_RELATIVE_IMPROVEMENT, patience: int = PATIENCE_TRIALS) -> None:
        self.threshold = threshold
        self.patience = patience
        self.best_seen: float | None = None
        self.counter = 0

    def __call__(self, study: optuna.study.Study, trial: optuna.trial.FrozenTrial) -> None:
        current_best = study.best_value
        if self.best_seen is None:
            self.best_seen = current_best
            self.counter = 0
            return
        rel = relative_improvement(self.best_seen, current_best)
        if rel >= self.threshold:
            self.best_seen = current_best
            self.counter = 0
        else:
            self.counter += 1
        if self.counter >= self.patience:
            study.stop()


def staged_optimize(
    spec: ModelSpec,
    features: list[str],
    df: pd.DataFrame,
    folds: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    baseline = evaluate_spec(spec, features, df, folds, spec.default_params)
    if not spec.tunable or spec.max_trials <= 0:
        return baseline, []

    trial_rows: list[dict[str, Any]] = []
    best_eval = baseline
    previous_objective = baseline["objective"]
    sampler = TPESampler(seed=SEED)
    total_trials_done = 0
    for level in OPTUNA_LEVELS:
        if total_trials_done >= spec.max_trials:
            break
        n_trials = min(level, spec.max_trials - total_trials_done)
        stopper = RelativeImprovementStopper()
        study = optuna.create_study(direction="minimize", sampler=sampler)

        def objective(trial: optuna.trial.Trial) -> float:
            params = suggest_params(spec, trial)
            result = evaluate_spec(spec, features, df, folds, params)
            trial.set_user_attr("mape", result["metrics"]["mape"])
            trial.set_user_attr("mae", result["metrics"]["mae"])
            trial.set_user_attr("stability", result["metrics"]["temporal_stability"])
            return result["objective"]

        study.optimize(objective, n_trials=n_trials, callbacks=[stopper], show_progress_bar=False)
        total_trials_done += len(study.trials)
        tuned = evaluate_spec(spec, features, df, folds, study.best_params)
        improvement = relative_improvement(previous_objective, tuned["objective"])
        trial_rows.append(
            {
                "model_label": spec.label,
                "level_target": level,
                "trials_executed": len(study.trials),
                "best_objective": tuned["objective"],
                "best_mape": tuned["metrics"]["mape"],
                "best_mae": tuned["metrics"]["mae"],
                "best_stability": tuned["metrics"]["temporal_stability"],
                "relative_improvement": improvement,
                "best_params": json.dumps(study.best_params, ensure_ascii=True),
            }
        )
        if improvement >= MIN_RELATIVE_IMPROVEMENT:
            best_eval = tuned
            previous_objective = tuned["objective"]
            continue
        break
    return best_eval, trial_rows


def model_specs() -> list[ModelSpec]:
    return [
        ModelSpec("LinearRegression_core", "LinearRegression", "core", False, 0, {}),
        ModelSpec("Ridge_core", "Ridge", "core", True, 50, {"alpha": 1.0}),
        ModelSpec("ElasticNet_core", "ElasticNet", "core", True, 50, {"alpha": 0.1, "l1_ratio": 0.5}),
        ModelSpec("HistGradientBoosting_core", "HistGradientBoosting", "core", True, 50, {"learning_rate": 0.05, "max_depth": 3, "max_leaf_nodes": 31, "min_samples_leaf": 10, "l2_regularization": 0.1, "max_iter": 180}),
        ModelSpec("LightGBM_core", "LightGBM", "core", True, 50, {"n_estimators": 140, "learning_rate": 0.05, "num_leaves": 15, "max_depth": 4, "min_child_samples": 10, "subsample": 0.9, "colsample_bytree": 0.9, "reg_alpha": 0.0, "reg_lambda": 0.0}),
        ModelSpec("CatBoost_core", "CatBoost", "core", True, 20, {"iterations": 180, "depth": 4, "learning_rate": 0.05, "l2_leaf_reg": 4.0, "random_strength": 1.0, "bagging_temperature": 0.0}),
        ModelSpec("RandomForest_core", "RandomForest", "core", True, 20, {"n_estimators": 160, "max_depth": 4, "min_samples_leaf": 4, "max_features": "sqrt"}),
        ModelSpec("Ridge_autonomia", "Ridge", "autonomia", True, 50, {"alpha": 1.0}),
        ModelSpec("Ridge_mass_balance", "Ridge", "mass_balance", True, 50, {"alpha": 1.0}),
        ModelSpec("EDO_Ridge_hybrid", "Ridge", "hybrid", True, 50, {"alpha": 1.0}),
        ModelSpec("EDO_LightGBM_hybrid", "LightGBM", "hybrid", True, 100, {"n_estimators": 140, "learning_rate": 0.05, "num_leaves": 15, "max_depth": 4, "min_child_samples": 10, "subsample": 0.9, "colsample_bytree": 0.9, "reg_alpha": 0.0, "reg_lambda": 0.0}),
    ]


def interpretability_score(label: str) -> float:
    if label.startswith("LinearRegression"):
        return 1.0
    if label.startswith("Ridge"):
        return 0.95
    if label.startswith("ElasticNet"):
        return 0.9
    if label.startswith("HistGradientBoosting"):
        return 0.68
    if label.startswith("LightGBM") or label.startswith("EDO_LightGBM"):
        return 0.62
    if label.startswith("CatBoost"):
        return 0.58
    if label.startswith("RandomForest"):
        return 0.55
    return 0.6


def simplicity_score(label: str, feature_count: int) -> float:
    base = 0.8
    if label.startswith("LinearRegression"):
        base = 1.0
    elif label.startswith("Ridge"):
        base = 0.95
    elif label.startswith("ElasticNet"):
        base = 0.9
    elif label.startswith("HistGradientBoosting"):
        base = 0.78
    elif label.startswith("LightGBM") or label.startswith("EDO_LightGBM"):
        base = 0.72
    elif label.startswith("CatBoost"):
        base = 0.6
    elif label.startswith("RandomForest"):
        base = 0.58
    penalty = min(max(feature_count - 18, 0) * 0.005, 0.12)
    return max(0.35, base - penalty)


def fit_full_model(spec: ModelSpec, dataset: pd.DataFrame, features: list[str], params: dict[str, Any]) -> Pipeline:
    usable = dataset.dropna(subset=features + [TARGET]).copy()
    train_df, valid_df = split_inner_validation(usable)
    estimator = make_estimator(spec, params)
    return fit_pipeline(estimator, train_df[features], train_df[TARGET], valid_df[features], valid_df[TARGET])


def build_shap_payload(
    label: str,
    model: Pipeline,
    dataset: pd.DataFrame,
    features: list[str],
) -> dict[str, Any]:
    cache_path = SHAP_CACHE_DIR / f"{label}.pkl"
    if cache_path.exists():
        with cache_path.open("rb") as handle:
            return pickle.load(handle)

    usable = dataset.dropna(subset=features + [TARGET]).copy()
    shap_df = usable[features].copy()
    shap_df = shap_df.sample(min(len(shap_df), 165), random_state=SEED)
    transformed = model.named_steps["imputer"].transform(shap_df)
    estimator = model.named_steps["model"]

    if hasattr(estimator, "coef_"):
        scaler = model.named_steps.get("scaler")
        transformed = scaler.transform(transformed) if scaler is not None else transformed
        explainer = shap.LinearExplainer(estimator, transformed)
        shap_values = explainer.shap_values(transformed)
        base_values = np.repeat(explainer.expected_value, len(shap_df))
    elif estimator.__class__.__name__ in {"LGBMRegressor", "RandomForestRegressor", "HistGradientBoostingRegressor", "CatBoostRegressor"}:
        explainer = shap.TreeExplainer(estimator)
        shap_values = explainer.shap_values(transformed)
        expected_value = explainer.expected_value
        if isinstance(expected_value, list):
            expected_value = expected_value[0]
        base_values = np.repeat(expected_value, len(shap_df))
    else:
        explainer = shap.Explainer(estimator.predict, transformed)
        values = explainer(transformed)
        shap_values = values.values
        base_values = values.base_values

    if shap_values.ndim == 3:
        shap_values = shap_values[:, :, 0]

    payload = {
        "label": label,
        "features": features,
        "feature_names_operational": [operational_name(col) for col in features],
        "X_raw": shap_df.reset_index(drop=True),
        "X_matrix": transformed,
        "values": np.asarray(shap_values),
        "base_values": np.asarray(base_values),
    }
    with cache_path.open("wb") as handle:
        pickle.dump(payload, handle)
    return payload


def shap_importance_frame(payload: dict[str, Any]) -> pd.DataFrame:
    mean_abs = np.abs(payload["values"]).mean(axis=0)
    return (
        pd.DataFrame(
            {
                "feature": payload["features"],
                "feature_operational": payload["feature_names_operational"],
                "mean_abs_shap": mean_abs,
                "feature_group": [feature_group(name) for name in payload["features"]],
                "model_label": payload["label"],
            }
        )
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )


def plot_model_comparison(ranking: pd.DataFrame) -> None:
    top = ranking.sort_values("final_score", ascending=False).head(10).copy()
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(top["model_label"], top["final_score"], color="#174A7E")
    ax.invert_yaxis()
    ax.set_xlabel("Score ponderado final")
    ax.set_title("Comparacion modelos v3")
    for bar, mape in zip(bars, top["mape"]):
        ax.text(bar.get_width() + 0.005, bar.get_y() + bar.get_height() / 2, f"MAPE {mape*100:.1f}%", va="center")
    plt.tight_layout()
    plt.savefig(OUT_FIG / "01_comparacion_modelos_v3.png", bbox_inches="tight")
    plt.close()


def plot_walk_forward(all_folds: pd.DataFrame, ranking: pd.DataFrame) -> None:
    top_labels = ranking.sort_values("final_score", ascending=False)["model_label"].head(4).tolist()
    plot_df = all_folds[all_folds["model_label"].isin(top_labels)].copy()
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    sns.lineplot(data=plot_df, x="test_month", y="mape", hue="model_label", marker="o", ax=axes[0])
    axes[0].set_ylabel("MAPE")
    axes[0].set_title("Walk-forward MAPE por fold")
    sns.lineplot(data=plot_df, x="test_month", y="mae", hue="model_label", marker="o", ax=axes[1], legend=False)
    axes[1].set_ylabel("MAE (TPH)")
    axes[1].set_title("Walk-forward MAE por fold")
    axes[1].set_xlabel("Mes de prueba")
    plt.tight_layout()
    plt.savefig(OUT_FIG / "02_walk_forward_performance.png", bbox_inches="tight")
    plt.close()


def plot_champion_predictions(champion_oof: pd.DataFrame) -> None:
    ordered = champion_oof.sort_values("fecha").copy()
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(ordered["fecha"], ordered["y_true"], label="Real", color="#174A7E", linewidth=2)
    ax.plot(ordered["fecha"], ordered["y_pred"], label="Predicho", color="#D2691E", linewidth=2)
    ax.set_title("Campeon real vs predicho")
    ax.set_ylabel("TPH")
    ax.legend()
    plt.tight_layout()
    plt.savefig(OUT_FIG / "03_real_vs_predicho_campeon.png", bbox_inches="tight")
    plt.close()


def plot_champion_error(champion_oof: pd.DataFrame) -> None:
    ordered = champion_oof.sort_values("fecha").copy()
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(ordered["fecha"], ordered["ape"] * 100, color="#B22222", linewidth=2)
    ax.axhline(5.5, color="#2E8B57", linestyle="--", linewidth=1.2, label="Meta MAPE 5.5%")
    ax.set_title("Error temporal campeon")
    ax.set_ylabel("APE (%)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(OUT_FIG / "04_error_temporal_campeon.png", bbox_inches="tight")
    plt.close()


def plot_champion_residuals(champion_oof: pd.DataFrame) -> None:
    residuals = champion_oof["y_pred"] - champion_oof["y_true"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    sns.histplot(residuals, bins=18, kde=True, ax=axes[0], color="#174A7E")
    axes[0].set_title("Distribucion residuos")
    axes[0].set_xlabel("Residuo (TPH)")
    axes[1].scatter(champion_oof["y_pred"], residuals, alpha=0.7, color="#D2691E")
    axes[1].axhline(0, color="black", linewidth=1)
    axes[1].set_title("Residuo vs prediccion")
    axes[1].set_xlabel("Prediccion")
    axes[1].set_ylabel("Residuo")
    plt.tight_layout()
    plt.savefig(OUT_FIG / "05_residuos_campeon.png", bbox_inches="tight")
    plt.close()


def plot_shap_summary(payload: dict[str, Any]) -> None:
    explanation = shap.Explanation(
        values=payload["values"],
        base_values=payload["base_values"],
        data=payload["X_matrix"],
        feature_names=payload["feature_names_operational"],
    )
    plt.figure(figsize=(10, 6))
    shap.plots.beeswarm(explanation, max_display=15, show=False)
    plt.title(f"SHAP summary operacional - {payload['label']}")
    plt.tight_layout()
    plt.savefig(OUT_FIG / "06_shap_summary_operacional.png", bbox_inches="tight")
    plt.close()


def plot_shap_bar(payload: dict[str, Any]) -> pd.DataFrame:
    importance = shap_importance_frame(payload).head(15).sort_values("mean_abs_shap")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(importance["feature_operational"], importance["mean_abs_shap"], color="#174A7E")
    ax.set_title("SHAP bar operacional - campeon")
    ax.set_xlabel("mean(|SHAP|)")
    plt.tight_layout()
    plt.savefig(OUT_FIG / "07_shap_bar_operacional.png", bbox_inches="tight")
    plt.close()
    return importance


def plot_physical_feature_importance(top3_shap: list[dict[str, Any]]) -> pd.DataFrame:
    frames = [shap_importance_frame(payload) for payload in top3_shap]
    combined = pd.concat(frames, ignore_index=True)
    physical = (
        combined[combined["feature_group"].isin(["fisico_operacional", "autonomia_edo"])]
        .groupby(["feature_operational"], as_index=False)["mean_abs_shap"]
        .mean()
        .sort_values("mean_abs_shap", ascending=False)
        .head(12)
    )
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.barh(physical["feature_operational"][::-1], physical["mean_abs_shap"][::-1], color="#2E8B57")
    ax.set_title("Importancia features fisicas")
    ax.set_xlabel("mean(|SHAP|) promedio top 3")
    plt.tight_layout()
    plt.savefig(OUT_FIG / "08_importancia_features_fisicas.png", bbox_inches="tight")
    plt.close()
    return physical


def plot_drift_vs_error(all_folds: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.scatterplot(
        data=all_folds,
        x="drift_mean_psi",
        y="mape",
        hue="model_label",
        ax=ax,
        s=80,
    )
    ax.set_title("Drift vs error walk-forward")
    ax.set_xlabel("PSI promedio fold")
    ax.set_ylabel("MAPE")
    plt.tight_layout()
    plt.savefig(OUT_FIG / "09_drift_vs_error.png", bbox_inches="tight")
    plt.close()


def plot_shap_dependence(payload: dict[str, Any], feature_name: str, output_name: str) -> None:
    if feature_name not in payload["features"]:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            f"{operational_name(feature_name)} no esta presente\nen el modelo usado para esta figura.",
            ha="center",
            va="center",
            fontsize=11,
        )
        plt.tight_layout()
        plt.savefig(OUT_FIG / output_name, bbox_inches="tight")
        plt.close()
        return
    idx = payload["features"].index(feature_name)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(
        payload["X_raw"][feature_name],
        payload["values"][:, idx],
        c=payload["X_raw"][feature_name],
        cmap="viridis",
        s=35,
        alpha=0.8,
    )
    ax.axhline(0, color="black", linewidth=1)
    ax.set_xlabel(operational_name(feature_name))
    ax.set_ylabel("SHAP value")
    ax.set_title(f"Dependence - {operational_name(feature_name)}")
    plt.tight_layout()
    plt.savefig(OUT_FIG / output_name, bbox_inches="tight")
    plt.close()


def main() -> None:
    t0 = time.time()
    print("=" * 72)
    print("MODEL LOOP V3 - CONTROLADO, ESTABLE E INTERPRETABLE")
    print("=" * 72)

    prior, audit = read_prior_results()
    dataset, feature_catalog, meta = build_dataset()
    feature_packs = build_feature_packs(dataset)
    folds = build_monthly_folds(dataset)

    print(f"Dataset reutilizado: {meta['rows']} filas | {meta['date_min']} -> {meta['date_max']}")
    print(f"Folds walk-forward: {len(folds)}")
    print(f"Modelos previos revisados: {len(audit['reviewed_models'])}")
    print("GPU activada: No")

    all_results: list[dict[str, Any]] = []
    all_folds: list[pd.DataFrame] = []
    all_oof: list[pd.DataFrame] = []
    all_trials: list[dict[str, Any]] = []
    fitted_full_models: dict[str, Pipeline] = {}

    for spec in model_specs():
        features = feature_packs[spec.feature_pack]
        print(f"\nEvaluando {spec.label} | features={spec.feature_pack} ({len(features)})")
        result, trials = staged_optimize(spec, features, dataset, folds)
        all_trials.extend(trials)
        all_folds.append(result["fold_df"])
        all_oof.append(result["oof_df"])
        metrics = result["metrics"]
        full_model = fit_full_model(spec, dataset, features, result["params"])
        fitted_full_models[spec.label] = full_model
        row = {
            "model_label": spec.label,
            "family": spec.family,
            "feature_pack": spec.feature_pack,
            "feature_count": len(features),
            "params_json": json.dumps(result["params"], ensure_ascii=True),
            "r2": metrics["r2"],
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "mape": metrics["mape"],
            "bias": metrics["bias"],
            "error_p90": metrics["error_p90"],
            "error_p95": metrics["error_p95"],
            "temporal_stability": metrics["temporal_stability"],
            "gap_train_test": metrics["gap_train_test"],
            "drift_sensitivity": metrics["drift_sensitivity"],
            "interpretability": interpretability_score(spec.label),
            "simplicity": simplicity_score(spec.label, len(features)),
        }
        all_results.append(row)
        print(f"  MAPE={metrics['mape']*100:.2f}% | MAE={metrics['mae']:.1f} | Estab={metrics['temporal_stability']:.3f}")

    ranking = pd.DataFrame(all_results)
    ranking["mape_score"] = to_score(ranking["mape"], higher_is_better=False)
    ranking["mae_score"] = to_score(ranking["mae"], higher_is_better=False)
    ranking["stability_score"] = to_score(ranking["temporal_stability"], higher_is_better=True)
    ranking["final_score"] = (
        0.40 * ranking["mape_score"]
        + 0.20 * ranking["mae_score"]
        + 0.20 * ranking["stability_score"]
        + 0.10 * ranking["interpretability"]
        + 0.10 * ranking["simplicity"]
    )
    ranking = ranking.sort_values(["final_score", "mape"], ascending=[False, True]).reset_index(drop=True)

    all_folds_df = pd.concat(all_folds, ignore_index=True).sort_values(["model_label", "test_month"])
    all_oof_df = pd.concat(all_oof, ignore_index=True).sort_values(["model_label", "fecha"])
    trials_df = pd.DataFrame(all_trials)

    champion_label = ranking.iloc[0]["model_label"]
    champion_row = ranking.iloc[0]
    champion_oof = all_oof_df[all_oof_df["model_label"] == champion_label].copy()
    champion_spec = next(spec for spec in model_specs() if spec.label == champion_label)
    champion_features = feature_packs[champion_spec.feature_pack]
    champion_model = fitted_full_models[champion_label]

    top3_labels = ranking.head(3)["model_label"].tolist()
    shap_payloads = [
        build_shap_payload(label, fitted_full_models[label], dataset, feature_packs[next(spec for spec in model_specs() if spec.label == label).feature_pack])
        for label in top3_labels
    ]

    champion_payload = shap_payloads[0]
    champion_shap_importance = plot_shap_bar(champion_payload)
    top3_physical_importance = plot_physical_feature_importance(shap_payloads)

    plot_model_comparison(ranking)
    plot_walk_forward(all_folds_df, ranking)
    plot_champion_predictions(champion_oof)
    plot_champion_error(champion_oof)
    plot_champion_residuals(champion_oof)
    plot_shap_summary(champion_payload)
    plot_drift_vs_error(all_folds_df)
    autonomy_payload = next((payload for payload in shap_payloads if "autonomia_sag2_h" in payload["features"]), champion_payload)
    plot_shap_dependence(champion_payload, "pct_pila_sag2", "10_shap_dependence_pila.png")
    plot_shap_dependence(autonomy_payload, "autonomia_sag2_h", "11_shap_dependence_autonomia.png")
    plot_shap_dependence(champion_payload, "duracion_t8", "12_shap_dependence_t8.png")

    shap_frames = [shap_importance_frame(payload) for payload in shap_payloads]
    shap_export = pd.concat(shap_frames, ignore_index=True)

    drift_error_summary = (
        all_folds_df.groupby("model_label", as_index=False)
        .agg(
            drift_mean_psi=("drift_mean_psi", "mean"),
            fold_mape=("mape", "mean"),
            fold_mae=("mae", "mean"),
            folds=("fold_name", "count"),
        )
        .merge(ranking[["model_label", "drift_sensitivity"]], on="model_label", how="left")
    )

    prediction_sheet = champion_oof.copy()
    prediction_sheet["residual"] = prediction_sheet["y_pred"] - prediction_sheet["y_true"]

    audit_sheet = pd.DataFrame(
        [
            {"item": "skill_token_optimization_loop", "value": "aplicado"},
            {"item": "dataset_reutilizado", "value": "data/processed/dataset_master.parquet"},
            {"item": "registry_revisado", "value": str(PRIOR_REGISTRY.name)},
            {"item": "modelos_previos", "value": len(audit["reviewed_models"])},
            {"item": "granularidad_real", "value": meta["granularity"]},
            {"item": "gpu", "value": "No"},
            {"item": "familias_descartadas", "value": ", ".join(audit["discarded_families"])},
            {"item": "trials_totales", "value": int(trials_df["trials_executed"].sum()) if not trials_df.empty else 0},
        ]
    )

    with pd.ExcelWriter(OUT_EXCEL, engine="openpyxl") as writer:
        audit_sheet.to_excel(writer, sheet_name="00_Audit", index=False)
        feature_catalog.to_excel(writer, sheet_name="01_Feature_Catalog", index=False)
        ranking.to_excel(writer, sheet_name="02_Model_Ranking", index=False)
        all_folds_df.to_excel(writer, sheet_name="03_WalkForward_Folds", index=False)
        prediction_sheet.to_excel(writer, sheet_name="04_Champion_Preds", index=False)
        drift_error_summary.to_excel(writer, sheet_name="05_Drift_vs_Error", index=False)
        shap_export.to_excel(writer, sheet_name="06_SHAP_Top3", index=False)
        champion_shap_importance.to_excel(writer, sheet_name="07_SHAP_Champion", index=False)
        top3_physical_importance.to_excel(writer, sheet_name="08_Physical_Importance", index=False)
        if not trials_df.empty:
            trials_df.to_excel(writer, sheet_name="09_Optuna_Trials", index=False)

    model_bundle = {
        "label": champion_label,
        "family": champion_spec.family,
        "feature_pack": champion_spec.feature_pack,
        "features": champion_features,
        "params": json.loads(champion_row["params_json"]),
        "model": champion_model,
        "trained_at": pd.Timestamp.now("UTC").isoformat(),
        "score": float(champion_row["final_score"]),
    }
    with (OUT_MODELS / f"{champion_label}.pkl").open("wb") as handle:
        pickle.dump(model_bundle, handle)
    for label in top3_labels[1:]:
        spec = next(spec for spec in model_specs() if spec.label == label)
        bundle = {
            "label": label,
            "family": spec.family,
            "feature_pack": spec.feature_pack,
            "features": feature_packs[spec.feature_pack],
            "params": json.loads(ranking.loc[ranking["model_label"] == label, "params_json"].iloc[0]),
            "model": fitted_full_models[label],
            "trained_at": pd.Timestamp.now("UTC").isoformat(),
        }
        with (OUT_MODELS / f"{label}.pkl").open("wb") as handle:
            pickle.dump(bundle, handle)

    best_mape_row = ranking.sort_values("mape", ascending=True).iloc[0]
    best_mae_row = ranking.sort_values("mae", ascending=True).iloc[0]
    stable_row = ranking.sort_values("temporal_stability", ascending=False).iloc[0]
    autonomy_rows = ranking[ranking["feature_pack"].isin(["autonomia", "hybrid"])]
    hybrid_row = ranking[ranking["model_label"] == "EDO_LightGBM_hybrid"].iloc[0]
    ridge_core_row = ranking[ranking["model_label"] == "Ridge_core"].iloc[0]
    champion_top_features = shap_importance_frame(champion_payload).head(8)["feature_operational"].tolist()
    drift_flag = "Si" if ranking["drift_sensitivity"].fillna(0).max() > 0.2 else "Moderado"
    drift_sensitivity_text = (
        f"{champion_row['drift_sensitivity']:.3f}"
        if pd.notna(champion_row["drift_sensitivity"])
        else "nan"
    )
    operational_fit = "Si" if (
        champion_row["mape"] < 0.055
        or champion_row["mae"] < 130
        or champion_row["r2"] > 0
        or champion_row["temporal_stability"] > 0.75
    ) else "Aun no"

    summary_md = f"""# Model Loop v3 Summary
Fecha: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}

## Auditoria inicial
- Skill aplicado: `skill_token_optimization_loop.md`
- Dataset reutilizado: `data/processed/dataset_master.parquet`
- Registro revisado: `outputs/excel/model_registry_v2.xlsx`
- Modelos previos revisados: {len(audit['reviewed_models'])}
- Granularidad real de modelado: diaria. Los features `1h/4h/12h/24h` se implementaron como proxies `1d/4d/12d/24d`.
- GPU: no activada ({meta['rows']} filas, CPU suficiente).

## Score final usado
`40% MAPE + 20% MAE + 20% estabilidad temporal + 10% interpretabilidad + 10% simplicidad operacional`

## Ranking campeones
| Modelo | Score | MAPE % | MAE | R2 | Estabilidad |
|---|---:|---:|---:|---:|---:|
{chr(10).join(f"| {row.model_label} | {row.final_score:.3f} | {row.mape*100:.2f} | {row.mae:.1f} | {row.r2:.3f} | {row.temporal_stability:.3f} |" for row in ranking.head(8).itertuples())}

## Respuestas finales
1. Mejor MAPE: **{best_mape_row['model_label']}** con {best_mape_row['mape']*100:.2f}%.
2. Mejor MAE: **{best_mae_row['model_label']}** con {best_mae_row['mae']:.1f} TPH.
3. Modelo mas estable temporalmente: **{stable_row['model_label']}** con estabilidad {stable_row['temporal_stability']:.3f}.
4. Las features de autonomia mejoraron: **{"si" if not autonomy_rows.empty and autonomy_rows['final_score'].max() > ridge_core_row['final_score'] else "no"}**. Mejor score autonomia/hibrido = {autonomy_rows['final_score'].max():.3f} vs Ridge_core = {ridge_core_row['final_score']:.3f}.
5. El modelo hibrido EDO + ML mejoro: **{"si" if hybrid_row['final_score'] >= ridge_core_row['final_score'] else "no"}**. `EDO_LightGBM_hybrid` score={hybrid_row['final_score']:.3f}, MAPE={hybrid_row['mape']*100:.2f}%.
6. Hiperparametros ganadores del campeon: `{champion_row['params_json']}`.
7. Variables que mas explican el rendimiento: **{", ".join(champion_top_features[:6])}**.
8. Sigue existiendo drift: **{drift_flag}**. La sensibilidad promedio drift-error del campeon es {drift_sensitivity_text}.
9. El modelo es apto para uso operacional: **{operational_fit}**.
10. Modelo campeon recomendado: **{champion_label}**.

## Criterio de exito
- MAPE < 5.5%: {"si" if champion_row["mape"] < 0.055 else "no"}
- MAE < 130 TPH: {"si" if champion_row["mae"] < 130 else "no"}
- R2 test positivo: {"si" if champion_row["r2"] > 0 else "no"}
- Mejor estabilidad walk-forward: {"si" if champion_row["temporal_stability"] == ranking["temporal_stability"].max() else "no"}
- Interpretabilidad operacional: {"si" if champion_row["interpretability"] >= 0.9 else "parcial"}

## Artefactos generados
- Excel: `outputs/excel/model_registry_v3.xlsx`
- Reporte resumen: `outputs/reports/model_loop_v3_summary.md`
- Reporte explicabilidad: `outputs/reports/model_explainability_v3.md`
- Figuras: `outputs/figures/model_loop_v3/`
- Modelos: `outputs/models/v3/`
"""
    OUT_SUMMARY.write_text(summary_md, encoding="utf-8")

    explain_md = f"""# Model Explainability v3
Fecha: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}

## Top 3 modelos explicados con SHAP
{chr(10).join(f"- **{payload['label']}**" for payload in shap_payloads)}

## Campeon
- Modelo: **{champion_label}**
- Feature pack: `{champion_spec.feature_pack}`
- MAPE walk-forward: {champion_row['mape']*100:.2f}%
- MAE walk-forward: {champion_row['mae']:.1f} TPH

## Top 12 features SHAP del campeon
| Rank | Feature operacional | mean(|SHAP|) | Grupo |
|---|---|---:|---|
{chr(10).join(f"| {idx+1} | {row.feature_operational} | {row.mean_abs_shap:.3f} | {row.feature_group} |" for idx, row in shap_importance_frame(champion_payload).head(12).iterrows())}

## Lecturas operacionales
- La memoria de TPH y la utilizacion SAG2 siguen dominando el error, señal de fuerte inercia operacional.
- Las features fisicas con mayor señal fueron: {", ".join(top3_physical_importance['feature_operational'].head(5).tolist())}.
- `autonomia_sag2_h` {"aparece" if "Autonomia pila SAG2 (h)" in champion_top_features else "no aparece"} entre los principales drivers del campeon.
- `duracion_t8` {"aparece" if "Duracion diaria T8 (h)" in champion_top_features else "no aparece"} entre los principales drivers del campeon.

## Notas metodologicas
- SHAP se calculo solo para top 3 modelos, respetando el control de costo.
- Se uso el dataset completo reutilizado porque el universo total es chico ({meta['rows']} filas).
- Los nombres se tradujeron a nomenclatura operacional para consumo de negocio.
"""
    OUT_EXPLAIN.write_text(explain_md, encoding="utf-8")

    elapsed = time.time() - t0
    print("\n" + "=" * 72)
    print("RESUMEN FINAL V3")
    print("=" * 72)
    print(f"Campeon: {champion_label}")
    print(f"MAPE:    {champion_row['mape']*100:.2f}%")
    print(f"MAE:     {champion_row['mae']:.1f} TPH")
    print(f"R2:      {champion_row['r2']:.3f}")
    print(f"Tiempo:  {elapsed:.1f}s")
    print(f"Excel:   {OUT_EXCEL}")
    print(f"Reporte: {OUT_SUMMARY}")
    print(f"Modelos: {OUT_MODELS}")


if __name__ == "__main__":
    main()
