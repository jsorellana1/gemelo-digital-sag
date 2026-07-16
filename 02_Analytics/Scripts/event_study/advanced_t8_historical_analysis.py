from __future__ import annotations

import importlib.util
import json
import math
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_HIST_FILE = BASE_DIR / "data" / "raw" / "tonelaje_v2.xlsx"
LEGACY_UNITARIO = BASE_DIR / "data" / "intermediate" / "rendimientos_clean.parquet"
EVENTS_RAW = BASE_DIR / "data" / "intermediate" / "ventanas_t8.parquet"

CACHE_DIR = BASE_DIR / "data" / "cache"
OUT_FIG = BASE_DIR / "outputs" / "figures" / "advanced_t8_historical"
OUT_XLS = BASE_DIR / "outputs" / "excel"
OUT_RPT = BASE_DIR / "outputs" / "reports"
LOGS_DIR = BASE_DIR / "logs"

for directory in (CACHE_DIR, OUT_FIG, OUT_XLS, OUT_RPT, LOGS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

TPH_THRESHOLD = 50.0
DT_HOURS = 5 / 60
PRE_HOURS = 24
POST_HOURS = 48
BIN_HOURS = 0.5
ROLLING_POINTS = 12
MIN_BASELINE_POINTS = 24
SEVERE_DROP_PCT = 20.0
AUTONOMY_RULES = {
    "SAG1": {"critical_pct": 15.0, "drain_pct_h": 23.76},
    "SAG2": {"critical_pct": 18.2, "drain_pct_h": 6.18},
}
T8_TIMES: dict[int, tuple[int, int]] = {
    2: (14, 16),
    4: (12, 16),
    8: (8, 16),
    12: (8, 20),
}
CANONICAL_DURATIONS = [2, 4, 8, 12]
ASSET_COLORS = {
    "SAG1": "#1f77b4",
    "SAG2": "#ff7f0e",
    "PMC": "#2ca02c",
    "UNITARIO": "#d62728",
}
ASSET_ORDER = ["SAG1", "SAG2", "PMC", "UNITARIO"]


@dataclass
class PiecewiseFit:
    breakpoints: tuple[float, float] | None
    grid_x: np.ndarray
    grid_y: np.ndarray
    mse: float | None


def _maybe_lowess() -> Any | None:
    if importlib.util.find_spec("statsmodels") is None:
        return None
    try:
        from statsmodels.nonparametric.smoothers_lowess import lowess

        return lowess
    except Exception:
        return None


def _maybe_umap_hdbscan() -> tuple[Any | None, Any | None]:
    umap_cls = None
    hdbscan_mod = None
    if importlib.util.find_spec("umap") is not None:
        try:
            from umap import UMAP

            umap_cls = UMAP
        except Exception:
            umap_cls = None
    if importlib.util.find_spec("hdbscan") is not None:
        try:
            import hdbscan

            hdbscan_mod = hdbscan
        except Exception:
            hdbscan_mod = None
    return umap_cls, hdbscan_mod


LOWESS = _maybe_lowess()
UMAP_CLASS, HDBSCAN_MODULE = _maybe_umap_hdbscan()


def canonical_duration(hours_t8: float) -> int:
    return min(CANONICAL_DURATIONS, key=lambda item: abs(item - float(hours_t8)))


def _source_mtime(paths: list[Path]) -> float:
    mtimes = [path.stat().st_mtime for path in paths if path.exists()]
    return max(mtimes) if mtimes else 0.0


def _load_cached_parquet(cache_path: Path, source_paths: list[Path]) -> pd.DataFrame | None:
    if not cache_path.exists():
        return None
    if cache_path.stat().st_mtime < _source_mtime(source_paths):
        return None
    return pd.read_parquet(cache_path)


def _save_cached_parquet(df: pd.DataFrame, cache_path: Path) -> pd.DataFrame:
    df.to_parquet(cache_path, index=False)
    return df


def load_historical_5min() -> pd.DataFrame:
    cache_path = CACHE_DIR / "advanced_t8_historical_5min.parquet"
    cached = _load_cached_parquet(cache_path, [RAW_HIST_FILE, LEGACY_UNITARIO])
    if cached is not None:
        cached["fecha"] = pd.to_datetime(cached["fecha"])
        return cached

    usecols = [
        "Fecha",
        "CV_315(tmh/h)",
        "CV_316(tmh/h)",
        "SAG2:Nivel_Pila",
        "SAG:Nivel_Pila",
        "REND_TMS_SAG1_PI",
        "REND_TMS_SAG2_PI",
        "REND_TMS_PMC",
    ]
    df = pd.read_excel(RAW_HIST_FILE, usecols=usecols)
    df = df.rename(
        columns={
            "Fecha": "fecha",
            "CV_315(tmh/h)": "correa_315",
            "CV_316(tmh/h)": "correa_316",
            "SAG2:Nivel_Pila": "pila_sag2",
            "SAG:Nivel_Pila": "pila_sag1",
            "REND_TMS_SAG1_PI": "SAG1_tph",
            "REND_TMS_SAG2_PI": "SAG2_tph",
            "REND_TMS_PMC": "PMC_tph",
        }
    )
    df["fecha"] = pd.to_datetime(df["fecha"])
    numeric_cols = [column for column in df.columns if column != "fecha"]
    for column in numeric_cols:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["pila_sag1"] = df["pila_sag1"].clip(0, 100)
    df["pila_sag2"] = df["pila_sag2"].clip(0, 100)
    df["correa_315"] = df["correa_315"].clip(lower=0)
    df["correa_316"] = df["correa_316"].clip(lower=0)
    df = (
        df.sort_values("fecha")
        .drop_duplicates("fecha")
        .set_index("fecha")
        .resample("5min")
        .mean()
        .reset_index()
    )

    df["UNITARIO_tph"] = np.nan
    if LEGACY_UNITARIO.exists():
        legacy = pd.read_parquet(LEGACY_UNITARIO)
        legacy["fecha"] = pd.to_datetime(legacy["fecha"])
        legacy_unit = legacy.rename(columns={"MUN_tph": "UNITARIO_tph"})[
            ["fecha", "UNITARIO_tph"]
        ].copy()
        df = df.merge(legacy_unit, on="fecha", how="left", suffixes=("", "_legacy"))
        df["UNITARIO_tph"] = df["UNITARIO_tph"].fillna(df.pop("UNITARIO_tph_legacy"))

    for asset in ASSET_ORDER:
        tph_col = f"{asset}_tph"
        if tph_col not in df.columns:
            df[tph_col] = np.nan
        df[f"{asset}_operando"] = df[tph_col] > TPH_THRESHOLD
        df[f"{asset}_ton"] = df[tph_col].where(df[tph_col] > TPH_THRESHOLD, other=0.0) * DT_HOURS

    return _save_cached_parquet(df, cache_path)


def load_official_events() -> pd.DataFrame:
    cache_path = CACHE_DIR / "advanced_t8_official_events.parquet"
    cached = _load_cached_parquet(cache_path, [EVENTS_RAW])
    if cached is not None:
        cached["fecha"] = pd.to_datetime(cached["fecha"])
        cached["ini_oficial"] = pd.to_datetime(cached["ini_oficial"])
        cached["fin_oficial"] = pd.to_datetime(cached["fin_oficial"])
        return cached

    if not EVENTS_RAW.exists():
        raise FileNotFoundError(f"No existe la fuente de eventos: {EVENTS_RAW}")

    df = pd.read_parquet(EVENTS_RAW).copy()
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.normalize()
    df = (
        df[df["horas_t8"] > 0]
        .groupby("fecha", as_index=False)["horas_t8"]
        .max()
        .sort_values("fecha")
        .reset_index(drop=True)
    )
    rows: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        dur = canonical_duration(float(row["horas_t8"]))
        h_ini, h_fin = T8_TIMES[dur]
        ini = row["fecha"] + pd.Timedelta(hours=h_ini)
        fin = row["fecha"] + pd.Timedelta(hours=h_fin)
        rows.append(
            {
                "evento_id": f"EV{idx + 1:03d}",
                "fecha": row["fecha"],
                "horas_t8_raw": float(row["horas_t8"]),
                "duracion_h": dur,
                "ini_oficial": ini,
                "fin_oficial": fin,
            }
        )
    events = pd.DataFrame(rows)
    return _save_cached_parquet(events, cache_path)


def build_event_windows(df_5min: pd.DataFrame, df_events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cache_path = CACHE_DIR / "advanced_t8_event_windows.parquet"
    cached = _load_cached_parquet(cache_path, [RAW_HIST_FILE, LEGACY_UNITARIO, EVENTS_RAW])
    if cached is not None:
        cached["fecha"] = pd.to_datetime(cached["fecha"])
        cached["fecha_evento"] = pd.to_datetime(cached["fecha_evento"])
        cached["ini_oficial"] = pd.to_datetime(cached["ini_oficial"])
        cached["fin_oficial"] = pd.to_datetime(cached["fin_oficial"])
        valid_events = (
            cached[
                ["evento_id", "fecha_evento", "duracion_h", "horas_t8_raw", "ini_oficial", "fin_oficial"]
            ]
            .drop_duplicates()
            .rename(columns={"fecha_evento": "fecha"})
            .sort_values(["fecha", "evento_id"])
            .reset_index(drop=True)
        )
        return cached, valid_events

    min_ts = df_5min["fecha"].min()
    max_ts = df_5min["fecha"].max()
    chunks: list[pd.DataFrame] = []
    valid_events: list[dict[str, Any]] = []

    for event in df_events.itertuples(index=False):
        start = event.ini_oficial - pd.Timedelta(hours=PRE_HOURS)
        end = event.fin_oficial + pd.Timedelta(hours=POST_HOURS)
        if start < min_ts or end > max_ts:
            continue
        window = df_5min.loc[(df_5min["fecha"] >= start) & (df_5min["fecha"] <= end)].copy()
        if window.empty:
            continue
        window["evento_id"] = event.evento_id
        window["fecha_evento"] = event.fecha
        window["duracion_h"] = event.duracion_h
        window["horas_t8_raw"] = event.horas_t8_raw
        window["ini_oficial"] = event.ini_oficial
        window["fin_oficial"] = event.fin_oficial
        window["h_rel_inicio"] = (window["fecha"] - event.ini_oficial).dt.total_seconds() / 3600
        window["h_rel_fin"] = (window["fecha"] - event.fin_oficial).dt.total_seconds() / 3600
        window["periodo"] = "POST"
        window.loc[window["h_rel_inicio"] < 0, "periodo"] = "PRE"
        window.loc[(window["h_rel_inicio"] >= 0) & (window["h_rel_fin"] < 0), "periodo"] = "DURANTE"
        chunks.append(window)
        valid_events.append(
            {
                "evento_id": event.evento_id,
                "fecha": event.fecha,
                "duracion_h": event.duracion_h,
                "horas_t8_raw": event.horas_t8_raw,
                "ini_oficial": event.ini_oficial,
                "fin_oficial": event.fin_oficial,
            }
        )

    df_windows = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    if not df_windows.empty:
        _save_cached_parquet(df_windows, cache_path)
    return df_windows, pd.DataFrame(valid_events)


def _first_sustained_hour(hours: np.ndarray, values: np.ndarray, threshold: float, below: bool) -> float:
    if len(hours) == 0:
        return math.nan
    cond = values <= threshold if below else values >= threshold
    count = 0
    for hour, ok in zip(hours, cond):
        count = count + 1 if bool(ok) else 0
        if count >= 3:
            return float(hour)
    return math.nan


def compute_event_metrics(df_windows: pd.DataFrame, df_valid_events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    context_rows: list[dict[str, Any]] = []

    for event in df_valid_events.itertuples(index=False):
        df_event = df_windows[df_windows["evento_id"] == event.evento_id].copy()
        if df_event.empty:
            continue

        start_idx = (df_event["h_rel_inicio"].abs()).idxmin()
        start_row = df_event.loc[start_idx]
        pre_slice = df_event[df_event["periodo"] == "PRE"]
        context_rows.append(
            {
                "evento_id": event.evento_id,
                "fecha": event.fecha,
                "duracion_h": event.duracion_h,
                "horas_t8_raw": event.horas_t8_raw,
                "pile_sag1_t0": float(start_row["pila_sag1"]) if pd.notna(start_row["pila_sag1"]) else math.nan,
                "pile_sag2_t0": float(start_row["pila_sag2"]) if pd.notna(start_row["pila_sag2"]) else math.nan,
                "correa315_pre_mean": float(pre_slice["correa_315"].mean()),
                "correa316_pre_mean": float(pre_slice["correa_316"].mean()),
                "correa315_t0": float(start_row["correa_315"]) if pd.notna(start_row["correa_315"]) else math.nan,
                "correa316_t0": float(start_row["correa_316"]) if pd.notna(start_row["correa_316"]) else math.nan,
            }
        )

        for asset in ASSET_ORDER:
            tph_col = f"{asset}_tph"
            op_col = f"{asset}_operando"
            if tph_col not in df_event.columns:
                continue

            asset_slice = df_event[["fecha", "periodo", "h_rel_inicio", tph_col, op_col]].copy()
            asset_slice = asset_slice.dropna(subset=[tph_col])
            if asset_slice.empty:
                continue

            baseline_values = asset_slice.loc[
                (asset_slice["periodo"] == "PRE") & (asset_slice[op_col]),
                tph_col,
            ]
            if len(baseline_values) < MIN_BASELINE_POINTS:
                continue

            baseline = float(baseline_values.mean())
            if baseline <= TPH_THRESHOLD:
                continue

            after_start = asset_slice.loc[asset_slice["h_rel_inicio"] >= 0].copy()
            if after_start.empty:
                continue
            after_start["smooth"] = after_start[tph_col].rolling(ROLLING_POINTS, min_periods=3).mean()
            smooth_values = after_start["smooth"].fillna(after_start[tph_col]).to_numpy()
            rel_hours = after_start["h_rel_inicio"].to_numpy()

            onset_h = _first_sustained_hour(rel_hours, smooth_values, baseline * 0.95, below=True)

            min_idx = int(np.nanargmin(smooth_values))
            tph_min = float(smooth_values[min_idx])
            h_to_min = float(rel_hours[min_idx])
            drop_abs = baseline - tph_min
            drop_pct = max(drop_abs / baseline * 100, 0.0)

            rec_hours = rel_hours[min_idx:]
            rec_values = smooth_values[min_idx:]
            recovery_90_h = _first_sustained_hour(rec_hours, rec_values, baseline * 0.90, below=False)
            recovery_100_h = _first_sustained_hour(rec_hours, rec_values, baseline * 1.00, below=False)

            during_mean = float(asset_slice.loc[asset_slice["periodo"] == "DURANTE", tph_col].mean())
            post_mean = float(asset_slice.loc[asset_slice["periodo"] == "POST", tph_col].mean())
            post_24_mean = float(
                asset_slice.loc[
                    (asset_slice["h_rel_inicio"] >= event.duracion_h) & (asset_slice["h_rel_inicio"] <= event.duracion_h + 24),
                    tph_col,
                ].mean()
            )
            rows.append(
                {
                    "evento_id": event.evento_id,
                    "fecha": event.fecha,
                    "duracion_h": event.duracion_h,
                    "horas_t8_raw": event.horas_t8_raw,
                    "activo": asset,
                    "baseline_tph": round(baseline, 1),
                    "tph_min": round(tph_min, 1),
                    "drop_abs": round(drop_abs, 1),
                    "drop_pct": round(drop_pct, 2),
                    "onset_h": round(onset_h, 2) if not math.isnan(onset_h) else math.nan,
                    "h_to_min": round(h_to_min, 2),
                    "recovery_90_h": round(recovery_90_h, 2) if not math.isnan(recovery_90_h) else math.nan,
                    "recovery_100_h": round(recovery_100_h, 2) if not math.isnan(recovery_100_h) else math.nan,
                    "during_mean_tph": round(during_mean, 1) if not math.isnan(during_mean) else math.nan,
                    "post_mean_tph": round(post_mean, 1) if not math.isnan(post_mean) else math.nan,
                    "post24_mean_tph": round(post_24_mean, 1) if not math.isnan(post_24_mean) else math.nan,
                    "drop_during_pct": round(max((baseline - during_mean) / baseline * 100, 0.0), 2)
                    if not math.isnan(during_mean)
                    else math.nan,
                    "drop_post_pct": round(max((baseline - post_mean) / baseline * 100, 0.0), 2)
                    if not math.isnan(post_mean)
                    else math.nan,
                    "severe_drop": int(drop_pct >= SEVERE_DROP_PCT),
                }
            )

    metrics = pd.DataFrame(rows)
    context = pd.DataFrame(context_rows)
    if not metrics.empty and not context.empty:
        metrics = metrics.merge(context, on=["evento_id", "fecha", "duracion_h", "horas_t8_raw"], how="left")
    return metrics, context


def build_curve_table(df_windows: pd.DataFrame, df_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    metric_lookup = (
        df_metrics[["evento_id", "activo", "baseline_tph"]]
        .drop_duplicates()
        .set_index(["evento_id", "activo"])["baseline_tph"]
        .to_dict()
    )
    for asset in ASSET_ORDER:
        tph_col = f"{asset}_tph"
        if tph_col not in df_windows.columns:
            continue
        for event_id, event_slice in df_windows.groupby("evento_id"):
            baseline = metric_lookup.get((event_id, asset))
            if baseline is None or baseline <= 0:
                continue
            subset = event_slice[["h_rel_inicio", "duracion_h", tph_col]].dropna().copy()
            if subset.empty:
                continue
            subset["h_bin"] = (subset["h_rel_inicio"] / BIN_HOURS).round() * BIN_HOURS
            subset["tph_pct"] = subset[tph_col] / baseline * 100.0
            grouped = (
                subset.groupby(["duracion_h", "h_bin"], as_index=False)["tph_pct"]
                .mean()
                .assign(evento_id=event_id, activo=asset)
            )
            rows.extend(grouped.to_dict("records"))

    curves = pd.DataFrame(rows)
    if curves.empty:
        return curves

    curves = (
        curves.groupby(["activo", "duracion_h", "h_bin"], as_index=False)
        .agg(
            tph_pct_mean=("tph_pct", "mean"),
            tph_pct_median=("tph_pct", "median"),
            n=("tph_pct", "count"),
            tph_pct_std=("tph_pct", "std"),
        )
    )
    return curves


def summarize_metrics(df_metrics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df_metrics.empty:
        return pd.DataFrame(), pd.DataFrame()

    asset_summary = (
        df_metrics.groupby("activo", as_index=False)
        .agg(
            n_eventos=("evento_id", "count"),
            caida_promedio_pct=("drop_pct", "mean"),
            caida_max_pct=("drop_pct", "max"),
            retardo_prom_h=("onset_h", "mean"),
            tiempo_min_prom_h=("h_to_min", "mean"),
            recuperacion_90_prom_h=("recovery_90_h", "mean"),
            baseline_prom_tph=("baseline_tph", "mean"),
        )
        .round(2)
    )
    valid_asset_summary = asset_summary.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["caida_promedio_pct", "caida_max_pct"], how="all"
    )
    if not valid_asset_summary.empty:
        score_matrix = valid_asset_summary[
            ["caida_promedio_pct", "caida_max_pct", "recuperacion_90_prom_h"]
        ].fillna(valid_asset_summary.median(numeric_only=True))
        z_matrix = (score_matrix - score_matrix.mean()) / score_matrix.std(ddof=0).replace(0, 1)
        valid_asset_summary["vulnerabilidad_score"] = (z_matrix.mean(axis=1) * 10 + 50).round(1)
        asset_summary = asset_summary.merge(
            valid_asset_summary[["activo", "vulnerabilidad_score"]],
            on="activo",
            how="left",
        )

    duration_summary = (
        df_metrics.groupby(["activo", "duracion_h"], as_index=False)
        .agg(
            n_eventos=("evento_id", "count"),
            caida_promedio_pct=("drop_pct", "mean"),
            caida_mediana_pct=("drop_pct", "median"),
            caida_std_pct=("drop_pct", "std"),
            caida_q25_pct=("drop_pct", lambda x: x.quantile(0.25)),
            caida_q75_pct=("drop_pct", lambda x: x.quantile(0.75)),
            retardo_prom_h=("onset_h", "mean"),
            recuperacion_90_prom_h=("recovery_90_h", "mean"),
            recuperacion_90_mediana_h=("recovery_90_h", "median"),
            recuperacion_90_std_h=("recovery_90_h", "std"),
        )
        .round(2)
    )
    return asset_summary, duration_summary


def plot_no_data_figure(filename: str, title: str, note: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.axis("off")
    ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=16, fontweight="bold")
    ax.text(0.5, 0.38, note, ha="center", va="center", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT_FIG / filename, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_event_study_assets(curves: pd.DataFrame, duration_summary: pd.DataFrame) -> None:
    for idx, asset in enumerate(ASSET_ORDER, start=1):
        file_name = f"{idx:02d}_EventStudy_{asset}.png"
        asset_curves = curves[curves["activo"] == asset].copy()
        asset_dur = duration_summary[duration_summary["activo"] == asset].copy()
        if asset_curves.empty:
            plot_no_data_figure(
                file_name,
                f"Event Study {asset}",
                "Sin cobertura suficiente en la fuente histórica para este activo.",
            )
            continue

        fig, axes = plt.subplots(1, 2, figsize=(16, 5.5), gridspec_kw={"width_ratios": [1.7, 1.0]})
        ax_curve, ax_bar = axes
        ax_curve.axvspan(0, 12, color="#E8F0FE", alpha=0.45, label="Rango posible DURANTE T8 (2-12h)")
        for dur in CANONICAL_DURATIONS:
            sub = asset_curves[asset_curves["duracion_h"] == dur]
            if sub.empty:
                continue
            ax_curve.plot(
                sub["h_bin"],
                sub["tph_pct_mean"],
                linewidth=2,
                label=f"{dur}h",
            )
        for marker_h in [0, 2, 4, 8, 12]:
            ax_curve.axvline(marker_h, color="gray", linestyle="--", linewidth=0.8, alpha=0.45)
        ax_curve.axhline(100, color="black", linestyle=":", linewidth=1)
        ax_curve.set_xlim(-PRE_HOURS, 60)
        ax_curve.set_ylim(0, max(110, asset_curves["tph_pct_mean"].max() * 1.05))
        ax_curve.set_title(f"{asset} | Curva PRE / DURANTE / POST")
        ax_curve.set_xlabel("Horas relativas al inicio T8")
        ax_curve.set_ylabel("TPH normalizado (% baseline PRE)")
        ax_curve.grid(True, alpha=0.25)
        ax_curve.legend(frameon=False)

        if asset_dur.empty:
            ax_bar.axis("off")
            ax_bar.text(0.5, 0.5, "Sin métricas por duración", ha="center", va="center")
        else:
            LOW_N_THRESH = 15
            x = np.arange(len(asset_dur))
            width = 0.38
            asset_color = ASSET_COLORS.get(asset, "#4C78A8")

            # ── Caída % — eje izquierdo ─────────────────────────────────────
            caida_err = [
                (asset_dur["caida_promedio_pct"] - asset_dur["caida_q25_pct"]).clip(lower=0).values,
                (asset_dur["caida_q75_pct"] - asset_dur["caida_promedio_pct"]).clip(lower=0).values,
            ]
            bars_caida = ax_bar.bar(
                x - width / 2,
                asset_dur["caida_promedio_pct"],
                width,
                color=asset_color,
                alpha=0.82,
                label="Caída % (media)",
                zorder=3,
            )
            ax_bar.errorbar(
                x - width / 2,
                asset_dur["caida_promedio_pct"],
                yerr=caida_err,
                fmt="none",
                color="black",
                capsize=4,
                linewidth=1.2,
                zorder=4,
            )
            # Punto de mediana sobre la barra de caída
            ax_bar.scatter(
                x - width / 2,
                asset_dur["caida_mediana_pct"],
                marker="D",
                color="white",
                edgecolors=asset_color,
                s=28,
                zorder=5,
                label="Caída % (mediana)",
            )
            ax_bar.set_ylabel("Caída TPH (%)", color=asset_color, fontsize=9)
            ax_bar.tick_params(axis="y", labelcolor=asset_color)

            # ── Rec. 90% (h) — eje derecho ────────────────────────────────
            ax_rec = ax_bar.twinx()
            rec_err = asset_dur["recuperacion_90_std_h"].fillna(0).values
            ax_rec.bar(
                x + width / 2,
                asset_dur["recuperacion_90_prom_h"],
                width,
                color="#757575",
                alpha=0.72,
                label="Rec. 90% (h) media",
                zorder=3,
            )
            ax_rec.errorbar(
                x + width / 2,
                asset_dur["recuperacion_90_prom_h"],
                yerr=rec_err,
                fmt="none",
                color="#424242",
                capsize=4,
                linewidth=1.2,
                zorder=4,
            )
            ax_rec.scatter(
                x + width / 2,
                asset_dur["recuperacion_90_mediana_h"],
                marker="D",
                color="white",
                edgecolors="#424242",
                s=28,
                zorder=5,
                label="Rec. 90% (h) mediana",
            )
            ax_rec.set_ylabel("Recuperación 90% (h)", color="#424242", fontsize=9)
            ax_rec.tick_params(axis="y", labelcolor="#424242")

            # ── Etiquetas N sobre cada grupo de barras ─────────────────────
            for i_x, row in enumerate(asset_dur.itertuples()):
                n = int(row.n_eventos)
                low_n = n < LOW_N_THRESH
                label_color = "#C62828" if low_n else "#333333"
                prefix = "⚠ " if low_n else ""
                ax_bar.text(
                    i_x,
                    max(row.caida_promedio_pct, row.caida_q75_pct) + 1.5,
                    f"{prefix}n={n}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color=label_color,
                    fontweight="bold" if low_n else "normal",
                )

            ax_bar.set_xticks(x)
            ax_bar.set_xticklabels([f"{int(v)}h" for v in asset_dur["duracion_h"]])
            ax_bar.set_title("Daño promedio por duración\n◆ = mediana  |  barra = IQR  |  ⚠ n<15", fontsize=9)
            ax_bar.grid(True, alpha=0.2, axis="y", zorder=0)

            # Leyenda combinada
            handles1, labels1 = ax_bar.get_legend_handles_labels()
            handles2, labels2 = ax_rec.get_legend_handles_labels()
            ax_bar.legend(handles1 + handles2, labels1 + labels2,
                          frameon=False, fontsize=7.5, loc="upper right")
        fig.tight_layout()
        fig.savefig(OUT_FIG / file_name, dpi=140, bbox_inches="tight")
        plt.close(fig)


def plot_gaviota_comparativa(curves: pd.DataFrame) -> None:
    if curves.empty:
        plot_no_data_figure("05_Gaviota_Comparativa.png", "Efecto Gaviota Comparativo", "Sin curvas históricas disponibles.")
        return

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True, sharey=True)
    axes = axes.flatten()
    for ax, dur in zip(axes, CANONICAL_DURATIONS):
        ax.axvspan(0, dur, color="#FDEBD0", alpha=0.55)
        for asset in ASSET_ORDER:
            sub = curves[(curves["activo"] == asset) & (curves["duracion_h"] == dur)]
            if sub.empty:
                continue
            ax.plot(sub["h_bin"], sub["tph_pct_mean"], linewidth=2, color=ASSET_COLORS.get(asset), label=asset)
        ax.axhline(100, color="black", linestyle=":", linewidth=1)
        ax.axvline(0, color="gray", linestyle="--", linewidth=0.9)
        ax.set_title(f"Gaviota comparativa {dur}h")
        ax.set_xlim(-PRE_HOURS, dur + POST_HOURS)
        ax.grid(True, alpha=0.25)
    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False)
    fig.suptitle("Efecto Gaviota por duración T8", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT_FIG / "05_Gaviota_Comparativa.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def fit_piecewise_curve(x: np.ndarray, y: np.ndarray) -> PiecewiseFit:
    if len(x) < 500:
        return PiecewiseFit(None, np.array([]), np.array([]), None)
    candidates = np.arange(15, 86, 5)
    best_mse = None
    best_breaks = None
    best_grid_y = np.array([])
    grid_x = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 200)

    for i, b1 in enumerate(candidates):
        for b2 in candidates[i + 1 :]:
            if b2 - b1 < 10:
                continue
            seg1 = x < b1
            seg2 = (x >= b1) & (x < b2)
            seg3 = x >= b2
            if min(seg1.sum(), seg2.sum(), seg3.sum()) < 250:
                continue
            models = []
            preds = np.zeros_like(y)
            for mask in (seg1, seg2, seg3):
                model = LinearRegression()
                model.fit(x[mask].reshape(-1, 1), y[mask])
                preds[mask] = model.predict(x[mask].reshape(-1, 1))
                models.append(model)
            mse = mean_squared_error(y, preds)
            if best_mse is None or mse < best_mse:
                best_mse = mse
                best_breaks = (float(b1), float(b2))
                grid_pred = np.zeros_like(grid_x)
                masks = (grid_x < b1, (grid_x >= b1) & (grid_x < b2), grid_x >= b2)
                for model, mask in zip(models, masks):
                    grid_pred[mask] = model.predict(grid_x[mask].reshape(-1, 1))
                best_grid_y = grid_pred

    return PiecewiseFit(best_breaks, grid_x, best_grid_y, best_mse)


def build_elasticity_curves(df_5min: pd.DataFrame, asset: str, pile_col: str) -> tuple[pd.DataFrame, pd.DataFrame, PiecewiseFit]:
    tph_col = f"{asset}_tph"
    op_col = f"{asset}_operando"
    subset = df_5min.loc[df_5min[op_col] & df_5min[pile_col].between(0, 100), [pile_col, tph_col]].dropna()
    if len(subset) > 20000:
        subset = subset.sample(20000, random_state=42)
    x = subset[pile_col].to_numpy()
    y = subset[tph_col].to_numpy()
    grid = np.linspace(max(0, np.nanmin(x)), min(100, np.nanmax(x)), 200)

    curve_rows: list[dict[str, Any]] = []

    if LOWESS is not None and len(subset) > 300:
        low = LOWESS(y, x, frac=0.18, return_sorted=True)
        low_df = pd.DataFrame({"x": low[:, 0], "y": low[:, 1], "metodo": "LOWESS"})
        curve_rows.extend(low_df.to_dict("records"))

    spline_model = make_pipeline(
        SplineTransformer(n_knots=6, degree=3, include_bias=False),
        Ridge(alpha=1.0),
    )
    spline_model.fit(x.reshape(-1, 1), y)
    spline_pred = spline_model.predict(grid.reshape(-1, 1))
    curve_rows.extend(pd.DataFrame({"x": grid, "y": spline_pred, "metodo": "GAM_Spline"}).to_dict("records"))

    piecewise = fit_piecewise_curve(x, y)
    if piecewise.breakpoints is not None and len(piecewise.grid_x) > 0:
        curve_rows.extend(
            pd.DataFrame(
                {
                    "x": piecewise.grid_x,
                    "y": piecewise.grid_y,
                    "metodo": "Piecewise",
                }
            ).to_dict("records")
        )

    curves_df = pd.DataFrame(curve_rows)
    return subset, curves_df, piecewise


def plot_elasticity(asset: str, subset: pd.DataFrame, curves_df: pd.DataFrame, piecewise: PiecewiseFit, pile_label: str, filename: str) -> list[float]:
    if subset.empty:
        plot_no_data_figure(filename, f"Elasticidad {asset}", "Sin datos operacionales suficientes.")
        return []

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.scatter(subset.iloc[:, 0], subset.iloc[:, 1], s=8, alpha=0.08, color=ASSET_COLORS.get(asset))
    for method, color in [("LOWESS", "#1f77b4"), ("GAM_Spline", "#d62728"), ("Piecewise", "#2ca02c")]:
        sub = curves_df[curves_df["metodo"] == method]
        if sub.empty:
            continue
        ax.plot(sub["x"], sub["y"], linewidth=2.2, color=color, label=method)
    breakpoints = list(piecewise.breakpoints) if piecewise.breakpoints is not None else []
    for bp in breakpoints:
        ax.axvline(bp, color="#444444", linestyle="--", linewidth=1)
        ax.text(bp + 0.8, subset.iloc[:, 1].quantile(0.08), f"{bp:.0f}%", fontsize=9, color="#444444")
    ax.set_title(f"{asset} | Elasticidad {pile_label} → TPH")
    ax.set_xlabel(f"{pile_label} (%)")
    ax.set_ylabel(f"TPH {asset}")
    ax.grid(True, alpha=0.22)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT_FIG / filename, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return breakpoints


def semaforo_autonomia(value: float) -> str:
    if pd.isna(value):
        return "SIN_DATO"
    if value < 2:
        return "ROJO"
    if value < 4:
        return "NARANJA"
    if value < 8:
        return "AMARILLO"
    return "VERDE"


def compute_autonomy(df_5min: pd.DataFrame, df_valid_events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    hourly = (
        df_5min.set_index("fecha")
        .resample("1h")
        .mean(numeric_only=True)
        .reset_index()
    )
    hourly["en_t8"] = False
    for event in df_valid_events.itertuples(index=False):
        mask = (hourly["fecha"] >= event.ini_oficial) & (hourly["fecha"] <= event.fin_oficial)
        hourly.loc[mask, "en_t8"] = True

    for sag, cfg in AUTONOMY_RULES.items():
        pile_col = "pila_sag1" if sag == "SAG1" else "pila_sag2"
        aut_col = f"autonomia_{sag.lower()}_h"
        hourly[aut_col] = ((hourly[pile_col] - cfg["critical_pct"]).clip(lower=0) / cfg["drain_pct_h"]).clip(upper=24)
        hourly[f"semaforo_{sag.lower()}"] = hourly[aut_col].apply(semaforo_autonomia)

    rows: list[dict[str, Any]] = []
    for sag in ("SAG1", "SAG2"):
        aut_col = f"autonomia_{sag.lower()}_h"
        for scope, mask in {
            "Total": pd.Series(True, index=hourly.index),
            "Con_T8": hourly["en_t8"],
            "Sin_T8": ~hourly["en_t8"],
        }.items():
            sample = hourly.loc[mask, aut_col].dropna()
            if sample.empty:
                continue
            rows.append(
                {
                    "SAG": sag,
                    "periodo": scope,
                    "media_h": round(float(sample.mean()), 2),
                    "min_h": round(float(sample.min()), 2),
                    "p10_h": round(float(sample.quantile(0.10)), 2),
                    "p25_h": round(float(sample.quantile(0.25)), 2),
                    "pct_cerca_limite_4h": round(float((sample < 4).mean() * 100), 1),
                    "pct_critico_2h": round(float((sample < 2).mean() * 100), 1),
                }
            )
    return hourly, pd.DataFrame(rows)


def plot_autonomy(hourly: pd.DataFrame, df_valid_events: pd.DataFrame, sag: str, filename: str) -> None:
    pile_col = "pila_sag1" if sag == "SAG1" else "pila_sag2"
    aut_col = f"autonomia_{sag.lower()}_h"
    cfg = AUTONOMY_RULES[sag]

    fig, axes = plt.subplots(2, 1, figsize=(15, 7), sharex=True, gridspec_kw={"height_ratios": [1.2, 1.0]})
    ax1, ax2 = axes
    for event in df_valid_events.itertuples(index=False):
        ax1.axvspan(event.ini_oficial, event.fin_oficial, color="#FDEBD0", alpha=0.6)
        ax2.axvspan(event.ini_oficial, event.fin_oficial, color="#FDEBD0", alpha=0.6)
    ax1.plot(hourly["fecha"], hourly[aut_col], color=ASSET_COLORS.get(sag), linewidth=1.2)
    ax1.axhline(8, color="#2ca02c", linestyle="--", linewidth=1)
    ax1.axhline(4, color="#ff7f0e", linestyle="--", linewidth=1)
    ax1.axhline(2, color="#d62728", linestyle="--", linewidth=1)
    ax1.set_ylabel("Autonomía (h)")
    ax1.set_title(f"{sag} | Autonomía histórica {hourly['fecha'].min().date()} → {hourly['fecha'].max().date()}")
    ax1.grid(True, alpha=0.2)

    ax2.plot(hourly["fecha"], hourly[pile_col], color="#4C78A8", linewidth=1.1)
    ax2.axhline(cfg["critical_pct"], color="#d62728", linestyle="--", linewidth=1.1)
    ax2.set_ylabel("Pila (%)")
    ax2.set_xlabel("Fecha")
    ax2.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT_FIG / filename, dpi=140, bbox_inches="tight")
    plt.close(fig)


def build_risk_tree(df_metrics: pd.DataFrame) -> tuple[pd.DataFrame, str, pd.DataFrame]:
    focus = df_metrics[df_metrics["activo"] == "SAG2"].copy()
    if focus.empty:
        return pd.DataFrame(), "Sin datos para árbol de riesgo.", pd.DataFrame()

    event_level = focus[
        [
            "evento_id",
            "fecha",
            "duracion_h",
            "pile_sag1_t0",
            "pile_sag2_t0",
            "correa315_pre_mean",
            "correa316_pre_mean",
            "baseline_tph",
            "drop_pct",
            "recovery_90_h",
            "onset_h",
        ]
    ].copy()
    event_level = event_level.rename(
        columns={
            "drop_pct": "drop_pct_sag2",
            "recovery_90_h": "recovery_90_h_sag2",
            "onset_h": "retardo_h_sag2",
        }
    )
    event_level["riesgo_alto"] = (event_level["drop_pct_sag2"] >= 85).astype(int)

    features = [
        "pile_sag1_t0",
        "pile_sag2_t0",
        "duracion_h",
        "correa315_pre_mean",
        "correa316_pre_mean",
        "baseline_tph",
    ]
    X = event_level[features].copy()
    imputer = SimpleImputer(strategy="median")
    X_imp = imputer.fit_transform(X)
    y = event_level["riesgo_alto"].to_numpy()

    tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=5, random_state=42)
    tree.fit(X_imp, y)
    rules = export_text(tree, feature_names=features)

    bins = [0, 20, 30, 40, 50, 60, 100]
    labels = [10, 25, 35, 45, 55, 80]
    event_level["pile_sag2_bin"] = pd.cut(
        event_level["pile_sag2_t0"],
        bins=bins,
        labels=labels,
        include_lowest=True,
    )
    heat_df = (
        event_level.groupby(["duracion_h", "pile_sag2_bin"], as_index=False)
        .agg(riesgo=("riesgo_alto", "mean"), n=("riesgo_alto", "count"))
        .rename(columns={"pile_sag2_bin": "pile_sag2_t0"})
    )
    heat_df["pile_sag2_t0"] = pd.to_numeric(heat_df["pile_sag2_t0"], errors="coerce")
    return event_level, rules, heat_df


def plot_risk_heatmap(heat_df: pd.DataFrame) -> None:
    if heat_df.empty:
        plot_no_data_figure("10_Heatmap_Riesgo_T8.png", "Heatmap de Riesgo T8", "Sin datos para estimar riesgo.")
        return
    pivot = heat_df.pivot(index="duracion_h", columns="pile_sag2_t0", values="riesgo").sort_index()
    counts = heat_df.pivot(index="duracion_h", columns="pile_sag2_t0", values="n").sort_index()
    cmap = LinearSegmentedColormap.from_list("risk", ["#2ca02c", "#f0ad4e", "#d62728"])
    fig, ax = plt.subplots(figsize=(12, 5))
    im = ax.imshow(pivot.values, cmap=cmap, aspect="auto", vmin=0, vmax=1)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([f"{int(v)}h" for v in pivot.index])
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{int(v)}%" for v in pivot.columns], rotation=45, ha="right")
    ax.set_title("Riesgo empírico de caída SAG2 | pila inicial × duración T8")
    ax.set_xlabel("Pila SAG2 al inicio de la ventana")
    ax.set_ylabel("Duración T8")
    for i, dur in enumerate(pivot.index):
        for j, pile in enumerate(pivot.columns):
            n = counts.loc[dur, pile] if pile in counts.columns else np.nan
            ax.text(
                j,
                i,
                f"{pivot.loc[dur, pile]:.0%}\n(n={int(n) if pd.notna(n) else 0})",
                ha="center",
                va="center",
                fontsize=8,
                color="black",
            )
    fig.colorbar(im, ax=ax, label="Probabilidad estimada de riesgo alto")
    fig.tight_layout()
    fig.savefig(OUT_FIG / "10_Heatmap_Riesgo_T8.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def build_event_clusters(df_metrics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    focus = df_metrics[df_metrics["activo"].isin(["SAG1", "SAG2", "PMC"])].copy()
    if focus.empty:
        return pd.DataFrame(), pd.DataFrame()

    event_level = (
        focus.groupby(["evento_id", "fecha", "duracion_h"], as_index=False)
        .agg(
            pile_sag1_t0=("pile_sag1_t0", "mean"),
            pile_sag2_t0=("pile_sag2_t0", "mean"),
            correa315_pre_mean=("correa315_pre_mean", "mean"),
            correa316_pre_mean=("correa316_pre_mean", "mean"),
            drop_pct_prom=("drop_pct", "mean"),
            drop_pct_max=("drop_pct", "max"),
            rec90_prom_h=("recovery_90_h", "mean"),
            retardo_prom_h=("onset_h", "mean"),
        )
    )
    feat_cols = [
        "duracion_h",
        "pile_sag1_t0",
        "pile_sag2_t0",
        "correa315_pre_mean",
        "correa316_pre_mean",
        "drop_pct_prom",
        "drop_pct_max",
        "rec90_prom_h",
        "retardo_prom_h",
    ]
    X = SimpleImputer(strategy="median").fit_transform(event_level[feat_cols])
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    pca = PCA(n_components=2, random_state=42)
    pca_emb = pca.fit_transform(Xs)
    event_level["pca_1"] = pca_emb[:, 0]
    event_level["pca_2"] = pca_emb[:, 1]

    if UMAP_CLASS is not None:
        try:
            umap_emb = UMAP_CLASS(n_neighbors=10, min_dist=0.25, random_state=42).fit_transform(Xs)
            event_level["umap_1"] = umap_emb[:, 0]
            event_level["umap_2"] = umap_emb[:, 1]
        except Exception:
            event_level["umap_1"] = event_level["pca_1"]
            event_level["umap_2"] = event_level["pca_2"]
    else:
        event_level["umap_1"] = event_level["pca_1"]
        event_level["umap_2"] = event_level["pca_2"]

    if HDBSCAN_MODULE is not None:
        try:
            clusterer = HDBSCAN_MODULE.HDBSCAN(min_cluster_size=6)
            labels = clusterer.fit_predict(Xs)
        except Exception:
            labels = KMeans(n_clusters=4, random_state=42, n_init=20).fit_predict(Xs)
    else:
        labels = KMeans(n_clusters=4, random_state=42, n_init=20).fit_predict(Xs)
    event_level["cluster_id"] = labels.astype(int)

    cluster_summary = (
        event_level.groupby("cluster_id", as_index=False)
        .agg(
            eventos=("evento_id", "count"),
            drop_pct_prom=("drop_pct_prom", "mean"),
            drop_pct_max=("drop_pct_max", "mean"),
            rec90_prom_h=("rec90_prom_h", "mean"),
        )
        .round(2)
        .sort_values("drop_pct_prom")
        .reset_index(drop=True)
    )
    def _cluster_label(drop_pct: float) -> str:
        if drop_pct < 15:
            return "Sin impacto"
        if drop_pct < 40:
            return "Moderadas"
        if drop_pct < 70:
            return "Severas"
        return "Críticas"

    cluster_summary["categoria"] = cluster_summary["drop_pct_prom"].apply(_cluster_label)
    event_level = event_level.merge(cluster_summary[["cluster_id", "categoria"]], on="cluster_id", how="left")
    return event_level, cluster_summary


def plot_recovery_time(df_metrics: pd.DataFrame) -> None:
    if df_metrics.empty:
        plot_no_data_figure("11_Recovery_Time.png", "Recovery Time", "Sin métricas de recuperación.")
        return
    focus = df_metrics[df_metrics["activo"].isin(["SAG1", "SAG2", "PMC", "UNITARIO"])]
    assets = [asset for asset in ASSET_ORDER if asset in focus["activo"].unique()]
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    data_left = [focus.loc[focus["activo"] == asset, "recovery_90_h"].dropna().values for asset in assets]
    axes[0].boxplot(data_left, labels=assets, patch_artist=True)
    for patch, asset in zip(axes[0].artists if hasattr(axes[0], "artists") else [], assets):
        patch.set_facecolor(ASSET_COLORS.get(asset))
    axes[0].set_title("Recovery 90% por activo")
    axes[0].set_ylabel("Horas")
    axes[0].grid(True, alpha=0.2, axis="y")

    duration_summary = (
        focus.groupby("duracion_h", as_index=False)["recovery_90_h"]
        .mean()
        .sort_values("duracion_h")
    )
    axes[1].bar(
        [f"{int(v)}h" for v in duration_summary["duracion_h"]],
        duration_summary["recovery_90_h"],
        color="#4C78A8",
        alpha=0.85,
    )
    axes[1].set_title("Recovery 90% promedio por duración T8")
    axes[1].set_ylabel("Horas")
    axes[1].grid(True, alpha=0.2, axis="y")

    fig.tight_layout()
    fig.savefig(OUT_FIG / "11_Recovery_Time.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_vulnerability_ranking(asset_summary: pd.DataFrame) -> None:
    if asset_summary.empty:
        plot_no_data_figure("12_Ranking_Vulnerabilidad.png", "Ranking de Vulnerabilidad", "Sin datos para ranking.")
        return
    ranking = asset_summary.sort_values("vulnerabilidad_score", ascending=True)
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.barh(ranking["activo"], ranking["vulnerabilidad_score"], color=[ASSET_COLORS.get(asset, "#4C78A8") for asset in ranking["activo"]], alpha=0.9)
    for bar, value in zip(bars, ranking["vulnerabilidad_score"]):
        ax.text(value + 0.6, bar.get_y() + bar.get_height() / 2, f"{value:.1f}", va="center", fontsize=9)
    ax.set_title("Ranking de vulnerabilidad operacional frente a T8")
    ax.set_xlabel("Score compuesto (caída + máximo daño + recuperación)")
    ax.grid(True, alpha=0.2, axis="x")
    fig.tight_layout()
    fig.savefig(OUT_FIG / "12_Ranking_Vulnerabilidad.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def build_final_answers(
    asset_summary: pd.DataFrame,
    duration_summary: pd.DataFrame,
    autonomy_kpis: pd.DataFrame,
    df_metrics: pd.DataFrame,
    breakpoints: dict[str, list[float]],
    cluster_summary: pd.DataFrame,
    risk_rules: str,
) -> pd.DataFrame:
    answers: list[dict[str, str]] = []
    valid_assets = asset_summary.dropna(subset=["vulnerabilidad_score"]).copy()
    worst_asset = valid_assets.sort_values("vulnerabilidad_score", ascending=False).iloc[0]["activo"] if not valid_assets.empty else "N/D"
    slow_asset = asset_summary.sort_values("recuperacion_90_prom_h", ascending=False).iloc[0]["activo"] if not asset_summary.empty else "N/D"
    worst_duration = (
        duration_summary.groupby("duracion_h")["caida_promedio_pct"].mean().sort_values(ascending=False).index[0]
        if not duration_summary.empty
        else "N/D"
    )
    worst_event_row = df_metrics.sort_values("drop_pct", ascending=False).iloc[0] if not df_metrics.empty else None
    sag2_total = autonomy_kpis[(autonomy_kpis["SAG"] == "SAG2") & (autonomy_kpis["periodo"] == "Total")]
    sag1_total = autonomy_kpis[(autonomy_kpis["SAG"] == "SAG1") & (autonomy_kpis["periodo"] == "Total")]
    sag2_total_row = sag2_total.iloc[0] if not sag2_total.empty else None
    sag1_total_row = sag1_total.iloc[0] if not sag1_total.empty else None

    answers.append({"pregunta": "1. ¿Qué activo es más vulnerable?", "respuesta": str(worst_asset)})
    answers.append({"pregunta": "2. ¿Qué activo se recupera más lento?", "respuesta": str(slow_asset)})
    answers.append({"pregunta": "3. ¿Qué duración T8 genera mayor impacto?", "respuesta": f"{worst_duration}h"})
    answers.append(
        {
            "pregunta": "4. ¿Existe un nivel crítico de pila?",
            "respuesta": f"SAG1 ≈ {breakpoints.get('SAG1', ['N/D'])[0] if breakpoints.get('SAG1') else 'N/D'}% | SAG2 ≈ {breakpoints.get('SAG2', ['N/D'])[0] if breakpoints.get('SAG2') else 'N/D'}%",
        }
    )
    answers.append(
        {
            "pregunta": "5. ¿Cuál es la autonomía operacional real?",
            "respuesta": f"SAG1 media={sag1_total_row['media_h']:.1f}h, p10={sag1_total_row['p10_h']:.1f}h | SAG2 media={sag2_total_row['media_h']:.1f}h, p10={sag2_total_row['p10_h']:.1f}h"
            if sag1_total_row is not None and sag2_total_row is not None
            else "N/D",
        }
    )
    answers.append(
        {
            "pregunta": "6. ¿Qué porcentaje del tiempo se opera cerca del límite?",
            "respuesta": f"SAG1 <4h: {sag1_total_row['pct_cerca_limite_4h']:.1f}% | SAG2 <4h: {sag2_total_row['pct_cerca_limite_4h']:.1f}%"
            if sag1_total_row is not None and sag2_total_row is not None
            else "N/D",
        }
    )
    answers.append(
        {
            "pregunta": "7. ¿Qué eventos históricos fueron más críticos?",
            "respuesta": f"{worst_event_row['activo']} | {pd.to_datetime(worst_event_row['fecha']).date()} | caída {worst_event_row['drop_pct']:.1f}%"
            if worst_event_row is not None
            else "N/D",
        }
    )
    answers.append(
        {
            "pregunta": "8. ¿Cuándo debería reducirse carga?",
            "respuesta": "Cuando la autonomía esperada baje de 4h o la pila SAG2 entre bajo el primer quiebre con T8 >=4h.",
        }
    )
    answers.append(
        {
            "pregunta": "9. ¿Cuándo debería evaluarse una detención preventiva?",
            "respuesta": "Cuando la autonomía proyectada baje de 2h y el árbol marque riesgo alto con pilas bajas y ventana larga.",
        }
    )
    answers.append(
        {
            "pregunta": "10. ¿Qué KPI deberían incorporarse al CIO y Power BI?",
            "respuesta": "Autonomía SAG1/SAG2, p10 autonomía, % tiempo <4h, riesgo T8, caída promedio por activo, recovery 90%, cluster del evento.",
        }
    )
    answers.append({"pregunta": "Clustering", "respuesta": cluster_summary.to_json(orient="records", force_ascii=False) if not cluster_summary.empty else "N/D"})
    answers.append({"pregunta": "Reglas árbol", "respuesta": risk_rules})
    return pd.DataFrame(answers)


def build_markdown_report(
    df_5min: pd.DataFrame,
    df_events: pd.DataFrame,
    df_valid_events: pd.DataFrame,
    asset_summary: pd.DataFrame,
    duration_summary: pd.DataFrame,
    autonomy_kpis: pd.DataFrame,
    final_answers: pd.DataFrame,
    breakpoints: dict[str, list[float]],
    risk_rules: str,
    cluster_summary: pd.DataFrame,
    unitario_note: str,
    elapsed_seconds: float,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Análisis Avanzado T8 | Histórico ampliado",
        f"*Generado: {now}*",
        "",
        "## Cobertura utilizada",
        f"- Serie histórica principal: `{RAW_HIST_FILE.name}`",
        f"- Rango 5-min: **{df_5min['fecha'].min()}** → **{df_5min['fecha'].max()}**",
        f"- Eventos oficiales reutilizados y recanonizados: **{len(df_events)}**",
        f"- Eventos con ventana completa analizable (-24h / fin+48h): **{len(df_valid_events)}**",
        f"- Ventanas oficiales consideradas: {', '.join(f'{k}h={v[0]:02d}:00-{v[1]:02d}:00' for k, v in T8_TIMES.items())}",
        "",
        "## Hallazgos principales",
    ]

    if not asset_summary.empty:
        ranking = asset_summary.sort_values("vulnerabilidad_score", ascending=False)
        worst = ranking.iloc[0]
        slow = asset_summary.sort_values("recuperacion_90_prom_h", ascending=False).iloc[0]
        lines.extend(
            [
                f"- Activo más vulnerable: **{worst['activo']}** con score {worst['vulnerabilidad_score']:.1f}.",
                f"- Recuperación más lenta: **{slow['activo']}** con {slow['recuperacion_90_prom_h']:.1f} h al 90%.",
                f"- Mayor impacto por duración: **{duration_summary.groupby('duracion_h')['caida_promedio_pct'].mean().idxmax()}h**.",
            ]
        )
    else:
        lines.append("- No hubo métricas suficientes para resumir activos.")

    lines.extend(
        [
            "",
            "## Elasticidad Pila → TPH",
            f"- Quiebres SAG1 estimados: {breakpoints.get('SAG1', []) or 'Sin quiebre robusto'}",
            f"- Quiebres SAG2 estimados: {breakpoints.get('SAG2', []) or 'Sin quiebre robusto'}",
            "",
            "## Autonomía operacional",
        ]
    )

    if not autonomy_kpis.empty:
        for row in autonomy_kpis.itertuples(index=False):
            if row.periodo != "Total":
                continue
            lines.append(
                f"- {row.SAG}: media={row.media_h:.1f}h | min={row.min_h:.1f}h | p10={row.p10_h:.1f}h | p25={row.p25_h:.1f}h | %<4h={row.pct_cerca_limite_4h:.1f}%"
            )
    else:
        lines.append("- Sin KPI horario suficiente.")

    lines.extend(["", "## Respuestas finales"])
    for row in final_answers.head(10).itertuples(index=False):
        lines.append(f"- **{row.pregunta}** {row.respuesta}")

    lines.extend(
        [
            "",
            "## Reglas operacionales sugeridas",
            "```text",
            risk_rules.strip(),
            "```",
            "",
            "## Clustering de eventos",
            cluster_summary.to_markdown(index=False) if not cluster_summary.empty else "Sin clusters suficientes.",
            "",
            "## Limitaciones reales del dataset",
            f"- {unitario_note}",
            "- El histórico ampliado comienza el 2025-08-01, pero los eventos T8 oficiales disponibles en PAM reutilizado siguen concentrados en 2026-01 a 2026-06.",
            "- La autonomía es un KPI proxy en horas basado en nivel de pila (%) y tasas históricas calibradas; no reemplaza la capacidad física real en toneladas.",
            "",
            "## Auditoría de eficiencia",
            f"- Archivos reutilizados: `{EVENTS_RAW.name}`, `{LEGACY_UNITARIO.name}`",
            f"- Cache generado: `{(CACHE_DIR / 'advanced_t8_historical_5min.parquet').name}`, `{(CACHE_DIR / 'advanced_t8_event_windows.parquet').name}`",
            "- Joins evitados: no se releen PAM Producción ni se recalcula la capa diaria legacy.",
            f"- Tiempo total de ejecución: {elapsed_seconds:.1f} s",
        ]
    )
    return "\n".join(lines)


def export_excel(
    df_events: pd.DataFrame,
    df_valid_events: pd.DataFrame,
    df_metrics: pd.DataFrame,
    asset_summary: pd.DataFrame,
    duration_summary: pd.DataFrame,
    elasticity_outputs: dict[str, pd.DataFrame],
    autonomy_hourly: pd.DataFrame,
    autonomy_kpis: pd.DataFrame,
    risk_event_level: pd.DataFrame,
    cluster_events: pd.DataFrame,
    final_answers: pd.DataFrame,
) -> Path:
    out_path = OUT_XLS / "advanced_t8_historical_analysis.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_events.to_excel(writer, sheet_name="eventos_reutilizados", index=False)
        df_valid_events.to_excel(writer, sheet_name="eventos_analizables", index=False)
        df_metrics.to_excel(writer, sheet_name="metricas_evento_activo", index=False)
        asset_summary.to_excel(writer, sheet_name="resumen_activo", index=False)
        duration_summary.to_excel(writer, sheet_name="resumen_duracion", index=False)
        autonomy_hourly.to_excel(writer, sheet_name="autonomia_horaria", index=False)
        autonomy_kpis.to_excel(writer, sheet_name="autonomia_kpis", index=False)
        risk_event_level.to_excel(writer, sheet_name="arbol_riesgo_eventos", index=False)
        cluster_events.to_excel(writer, sheet_name="clusters_eventos", index=False)
        final_answers.to_excel(writer, sheet_name="respuestas_finales", index=False)
        for key, value in elasticity_outputs.items():
            value.to_excel(writer, sheet_name=key[:31], index=False)
    return out_path


def run_advanced_t8_historical_analysis(verbose: bool = True) -> dict[str, Any]:
    t0 = time.time()
    if verbose:
        print("=" * 78)
        print("  Analisis avanzado de rendimientos PRE / DURANTE / POST T8")
        print("=" * 78)

    df_5min = load_historical_5min()
    df_events = load_official_events()
    df_windows, df_valid_events = build_event_windows(df_5min, df_events)
    if df_windows.empty:
        raise ValueError("No se pudieron construir ventanas de evento con cobertura completa.")

    if verbose:
        print(f"  Serie 5-min: {len(df_5min):,} filas | {df_5min['fecha'].min()} -> {df_5min['fecha'].max()}")
        print(f"  Eventos oficiales reutilizados: {len(df_events)} | analizables: {len(df_valid_events)}")

    df_metrics, df_context = compute_event_metrics(df_windows, df_valid_events)
    curves = build_curve_table(df_windows, df_metrics)
    asset_summary, duration_summary = summarize_metrics(df_metrics)

    plot_event_study_assets(curves, duration_summary)
    plot_gaviota_comparativa(curves)

    elasticity_outputs: dict[str, pd.DataFrame] = {}
    breakpoints: dict[str, list[float]] = {}
    for asset, pile_col, label, filename in [
        ("SAG1", "pila_sag1", "Pila SAG1", "06_Pila_vs_TPH_SAG1.png"),
        ("SAG2", "pila_sag2", "Pila SAG2", "07_Pila_vs_TPH_SAG2.png"),
    ]:
        subset, curve_df, piecewise = build_elasticity_curves(df_5min, asset, pile_col)
        elasticity_outputs[f"elasticidad_{asset.lower()}_muestra"] = subset.rename(
            columns={pile_col: label, f"{asset}_tph": f"TPH_{asset}"}
        )
        elasticity_outputs[f"elasticidad_{asset.lower()}_curvas"] = curve_df
        breakpoints[asset] = plot_elasticity(asset, subset, curve_df, piecewise, label, filename)

    autonomy_hourly, autonomy_kpis = compute_autonomy(df_5min, df_valid_events)
    plot_autonomy(autonomy_hourly, df_valid_events, "SAG1", "08_Autonomia_Historica_SAG1.png")
    plot_autonomy(autonomy_hourly, df_valid_events, "SAG2", "09_Autonomia_Historica_SAG2.png")

    risk_event_level, risk_rules, heat_df = build_risk_tree(df_metrics)
    plot_risk_heatmap(heat_df)

    cluster_events, cluster_summary = build_event_clusters(df_metrics)
    plot_recovery_time(df_metrics)
    plot_vulnerability_ranking(asset_summary)

    unitario_events = int(df_metrics.loc[df_metrics["activo"] == "UNITARIO", "evento_id"].nunique()) if not df_metrics.empty else 0
    unitario_note = (
        f"UNITARIO fue reconstruido parcialmente desde `{LEGACY_UNITARIO.name}` y sólo aporta hasta 2026-06-14; eventos con cobertura útil: {unitario_events}."
        if unitario_events > 0
        else "UNITARIO no está presente en `tonelaje_v2.xlsx`; no hubo cobertura suficiente para análisis histórico robusto."
    )

    final_answers = build_final_answers(
        asset_summary,
        duration_summary,
        autonomy_kpis,
        df_metrics,
        breakpoints,
        cluster_summary,
        risk_rules,
    )
    excel_path = export_excel(
        df_events,
        df_valid_events,
        df_metrics,
        asset_summary,
        duration_summary,
        elasticity_outputs,
        autonomy_hourly,
        autonomy_kpis,
        risk_event_level,
        cluster_events,
        final_answers,
    )
    elapsed = time.time() - t0
    report_text = build_markdown_report(
        df_5min,
        df_events,
        df_valid_events,
        asset_summary,
        duration_summary,
        autonomy_kpis,
        final_answers,
        breakpoints,
        risk_rules,
        cluster_summary,
        unitario_note,
        elapsed,
    )
    report_path = OUT_RPT / "advanced_t8_historical_analysis.md"
    report_path.write_text(report_text, encoding="utf-8")

    with open(LOGS_DIR / "skill_audit.log", "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "fecha": datetime.now().isoformat(),
                    "script": "src/advanced_t8_historical_analysis.py",
                    "source": str(RAW_HIST_FILE),
                    "event_source": str(EVENTS_RAW),
                    "n_eventos_reutilizados": int(len(df_events)),
                    "n_eventos_analizables": int(len(df_valid_events)),
                    "n_metricas": int(len(df_metrics)),
                    "unitario_note": unitario_note,
                    "excel": str(excel_path),
                    "report": str(report_path),
                    "elapsed_s": round(elapsed, 2),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    if verbose:
        print(f"  Excel: {excel_path.name}")
        print(f"  Reporte: {report_path.name}")
        print(f"  Tiempo total: {elapsed:.1f}s")
        print("=" * 78)

    return {
        "df_5min": df_5min,
        "df_events": df_events,
        "df_valid_events": df_valid_events,
        "df_metrics": df_metrics,
        "asset_summary": asset_summary,
        "duration_summary": duration_summary,
        "autonomy_kpis": autonomy_kpis,
        "cluster_summary": cluster_summary,
        "risk_rules": risk_rules,
        "excel_path": excel_path,
        "report_path": report_path,
        "unitario_note": unitario_note,
    }


if __name__ == "__main__":
    run_advanced_t8_historical_analysis(verbose=True)
