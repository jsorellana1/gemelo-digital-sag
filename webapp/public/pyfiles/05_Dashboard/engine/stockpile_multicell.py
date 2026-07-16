"""
stockpile_multicell.py - Fase 1 multi-celda para pilas SAG.

Objetivo:
- modelar disponibilidad local por canal sin transferencia lateral aun;
- calibrar una cota empirica n_canales_activos -> rate alcanzable;
- mantener el motor agregado actual como default.

La implementacion es deliberadamente conservadora:
- usa solo canales con calidad historica aceptable por defecto;
- capea el rate agregado por una tabla monotona calibrada;
- conserva masa aplicando update_stockpile_mass_balance por canal.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from engine.circuit_state import update_stockpile_mass_balance


RAW_PILAS_REND_PATH = (
    Path(__file__).resolve().parents[2]
    / "01_Data"
    / "Raw"
    / "Tonelajes_pila"
    / "pilas_rendimientos.xlsx"
)

ACTIVE_THRESHOLD_PCT = 5.0

# Defaults calibrados desde pilas_rendimientos.xlsx (2025-08-01 -> 2026-06-30)
# usando q90 por bucket de canales activos, monotonia acumulada y tope P90.
DEFAULT_MULTICELL_LAYOUTS = {
    "SAG1": {
        "channel_labels": ("D", "B", "A"),
        "source_columns": ("SAG:%_LI2016D", "SAG:LI2016B", "SAG:LI2016A"),
        "neighbor_pairs": ((0, 1), (1, 2)),
        "ignored_channels": ("C",),
        "ignored_reason": "SAG:LI2016C con cobertura historica insuficiente (~50.6%).",
        "rate_table_tph": {0: 0.0, 1: 1346.68, 2: 1398.91, 3: 1454.0},
        "quality_summary": {
            "SAG:%_LI2016D": {"coverage_pct": 83.42, "nunique": 73660, "frozen": False},
            "SAG:LI2016B": {"coverage_pct": 99.50, "nunique": 92245, "frozen": False},
            "SAG:LI2016A": {"coverage_pct": 99.78, "nunique": 86582, "frozen": False},
            "SAG:LI2016C": {"coverage_pct": 50.63, "nunique": 46841, "frozen": False},
        },
    },
    "SAG2": {
        "channel_labels": ("1", "2", "4", "5", "6"),
        "source_columns": (
            "SAG2:260_LI_PILA01",
            "SAG2:260_LI_PILA02",
            "SAG2:260_LI_PILA04",
            "SAG2:260_LI_PILA05",
            "SAG2:260_LI_PILA06",
        ),
        # Orden circular aproximado segun PI: 1 -> 2 -> 4 -> 5 -> 6 -> 1.
        "neighbor_pairs": ((0, 1), (1, 2), (2, 3), (3, 4), (4, 0)),
        "ignored_channels": ("3",),
        "ignored_reason": "SAG2:260_LI_PILA03 congelado (~0.3723% todo el periodo).",
        "rate_table_tph": {0: 0.0, 1: 2359.00, 2: 2510.43, 3: 2516.0, 4: 2516.0, 5: 2516.0},
        "default_spatial_capacity_params": {
            "intercept": 0.32183,
            "min_pct_coef": 0.00918,
            "range_pct_coef": 0.00517,
            "min_factor": 0.35,
            "max_factor": 1.00,
        },
        "quality_summary": {
            "SAG2:260_LI_PILA01": {"coverage_pct": 99.95, "nunique": 77942, "frozen": False},
            "SAG2:260_LI_PILA02": {"coverage_pct": 99.95, "nunique": 64088, "frozen": False},
            "SAG2:260_LI_PILA03": {"coverage_pct": 99.95, "nunique": 1, "frozen": True},
            "SAG2:260_LI_PILA04": {"coverage_pct": 99.95, "nunique": 20283, "frozen": False},
            "SAG2:260_LI_PILA05": {"coverage_pct": 99.95, "nunique": 72080, "frozen": False},
            "SAG2:260_LI_PILA06": {"coverage_pct": 99.95, "nunique": 37520, "frozen": False},
        },
    },
}


@dataclass(frozen=True)
class MultiCellConfig:
    asset: str
    channel_labels: tuple[str, ...]
    source_columns: tuple[str, ...]
    neighbor_pairs: tuple[tuple[int, int], ...]
    ignored_channels: tuple[str, ...]
    ignored_reason: str
    active_threshold_pct: float
    rate_table_tph: dict[int, float]
    feed_weights: tuple[float, ...]
    max_rate_tph: float
    spatial_capacity_mode: str
    spatial_capacity_params: dict[str, Any]


def _normalize_weights(weights: tuple[float, ...] | list[float] | None, n: int) -> tuple[float, ...]:
    if weights is None:
        return tuple(1.0 / n for _ in range(n))
    if len(weights) != n:
        raise ValueError(f"Expected {n} feed weights, got {len(weights)}")
    total = float(sum(max(0.0, float(w)) for w in weights))
    if total <= 0:
        raise ValueError("Feed weights must sum to a positive value")
    return tuple(max(0.0, float(w)) / total for w in weights)


def build_multicell_config(
    asset: str,
    max_rate_tph: float,
    rate_table_tph: dict[int, float] | None = None,
    active_threshold_pct: float = ACTIVE_THRESHOLD_PCT,
    feed_weights: tuple[float, ...] | list[float] | None = None,
    spatial_capacity_mode: str = "none",
    spatial_capacity_params: dict[str, Any] | None = None,
) -> MultiCellConfig:
    layout = DEFAULT_MULTICELL_LAYOUTS[asset]
    labels = tuple(layout["channel_labels"])
    weights = _normalize_weights(feed_weights, len(labels))
    neighbor_pairs = tuple(
        (int(i), int(j))
        for i, j in layout.get("neighbor_pairs", ())
        if 0 <= int(i) < len(labels) and 0 <= int(j) < len(labels) and int(i) != int(j)
    )
    table = dict(rate_table_tph or layout["rate_table_tph"])
    table = {int(k): min(float(v), float(max_rate_tph)) for k, v in table.items()}
    table[0] = 0.0
    spatial_params = dict(layout.get("default_spatial_capacity_params", {}))
    spatial_params.update(spatial_capacity_params or {})
    return MultiCellConfig(
        asset=asset,
        channel_labels=labels,
        source_columns=tuple(layout["source_columns"]),
        neighbor_pairs=neighbor_pairs,
        ignored_channels=tuple(layout["ignored_channels"]),
        ignored_reason=str(layout["ignored_reason"]),
        active_threshold_pct=float(active_threshold_pct),
        rate_table_tph=table,
        feed_weights=weights,
        max_rate_tph=float(max_rate_tph),
        spatial_capacity_mode=str(spatial_capacity_mode),
        spatial_capacity_params=spatial_params,
    )


def _normalize_shape_to_total(
    total_pile_pct: float,
    channel_levels_pct: list[float] | tuple[float, ...] | None,
    n_channels: int,
) -> list[float]:
    if channel_levels_pct is None:
        return [float(total_pile_pct)] * n_channels
    if len(channel_levels_pct) != n_channels:
        raise ValueError(f"Expected {n_channels} channel levels, got {len(channel_levels_pct)}")
    safe = [max(0.0, float(v)) for v in channel_levels_pct]
    avg = sum(safe) / n_channels if n_channels > 0 else 0.0
    if avg <= 0:
        return [float(total_pile_pct)] * n_channels
    scale = float(total_pile_pct) / avg
    return [max(0.0, min(100.0, v * scale)) for v in safe]


def initialize_channel_tons(
    total_pile_pct: float,
    cap_total_ton: float,
    config: MultiCellConfig,
    channel_levels_pct: list[float] | tuple[float, ...] | None = None,
) -> list[float]:
    normalized_pct = _normalize_shape_to_total(total_pile_pct, channel_levels_pct, len(config.channel_labels))
    cap_per_channel = cap_total_ton / len(config.channel_labels)
    return [pct / 100.0 * cap_per_channel for pct in normalized_pct]


def channel_levels_pct(channel_tons: list[float], cap_total_ton: float) -> list[float]:
    if not channel_tons:
        return []
    cap_per_channel = cap_total_ton / len(channel_tons)
    if cap_per_channel <= 0:
        return [0.0 for _ in channel_tons]
    return [ton / cap_per_channel * 100.0 for ton in channel_tons]


def aggregate_pile_pct(channel_tons: list[float], cap_total_ton: float) -> float:
    if cap_total_ton <= 0:
        return 0.0
    return sum(channel_tons) / cap_total_ton * 100.0


def count_active_channels(
    channel_tons: list[float],
    cap_total_ton: float,
    active_threshold_pct: float,
) -> int:
    return sum(1 for pct in channel_levels_pct(channel_tons, cap_total_ton) if pct > active_threshold_pct)


def calibrated_rate_cap_tph(
    requested_rate_tph: float,
    channel_tons: list[float],
    cap_total_ton: float,
    config: MultiCellConfig,
) -> float:
    active = count_active_channels(channel_tons, cap_total_ton, config.active_threshold_pct)
    calibrated = config.rate_table_tph.get(active, requested_rate_tph)
    return min(max(0.0, float(requested_rate_tph)), float(calibrated), float(config.max_rate_tph))


def spatial_capacity_factor(
    channel_tons: list[float],
    cap_total_ton: float,
    config: MultiCellConfig,
) -> float:
    if config.spatial_capacity_mode != "min_range_linear":
        return 1.0
    levels = channel_levels_pct(channel_tons, cap_total_ton)
    if not levels:
        return 1.0
    min_pct = min(levels)
    range_pct = max(levels) - min_pct
    params = config.spatial_capacity_params or {}
    factor = (
        float(params.get("intercept", 0.0))
        + float(params.get("min_pct_coef", 0.0)) * float(min_pct)
        + float(params.get("range_pct_coef", 0.0)) * float(range_pct)
    )
    min_factor = float(params.get("min_factor", 0.0))
    max_factor = float(params.get("max_factor", 1.0))
    return max(min_factor, min(max_factor, factor))


def _allocate_requested_reclaim(
    requested_rate_tph: float,
    qin_splits_tph: list[float],
    channel_tons: list[float],
    cap_per_channel_ton: float,
    delta_t_h: float,
    active_threshold_pct: float,
) -> tuple[list[float], int]:
    if requested_rate_tph <= 0 or delta_t_h <= 0 or not channel_tons:
        return [0.0 for _ in channel_tons], 0

    active_indices: list[int] = []
    available_rates: list[float] = []
    for idx, ton in enumerate(channel_tons):
        pct = ton / cap_per_channel_ton * 100.0 if cap_per_channel_ton > 0 else 0.0
        if pct > active_threshold_pct:
            active_indices.append(idx)
            available_rates.append(max(0.0, ton / delta_t_h + qin_splits_tph[idx]))

    if not active_indices:
        return [0.0 for _ in channel_tons], 0

    available_total = float(sum(available_rates))
    target_total = min(float(requested_rate_tph), available_total)
    if target_total <= 0 or available_total <= 0:
        return [0.0 for _ in channel_tons], len(active_indices)

    splits = [0.0 for _ in channel_tons]
    for idx, available in zip(active_indices, available_rates):
        splits[idx] = target_total * available / available_total
    return splits, len(active_indices)


def apply_lateral_transfer(
    channel_tons: list[float],
    cap_total_ton: float,
    config: MultiCellConfig,
    lateral_transfer_coeff_h: float = 0.0,
    delta_t_h: float = 0.0,
) -> tuple[list[float], float]:
    if lateral_transfer_coeff_h <= 0 or delta_t_h <= 0 or len(channel_tons) <= 1 or not config.neighbor_pairs:
        return list(channel_tons), 0.0

    tons = [max(0.0, float(v)) for v in channel_tons]
    alpha = min(0.5, max(0.0, float(lateral_transfer_coeff_h) * float(delta_t_h)))
    if alpha <= 0:
        return tons, 0.0

    deltas = [0.0 for _ in tons]
    moved_total = 0.0
    for i, j in config.neighbor_pairs:
        diff = tons[i] - tons[j]
        if abs(diff) <= 1e-12:
            continue
        move = alpha * abs(diff)
        if diff > 0:
            move = min(move, tons[i] + deltas[i])
            deltas[i] -= move
            deltas[j] += move
        else:
            move = min(move, tons[j] + deltas[j])
            deltas[j] -= move
            deltas[i] += move
        moved_total += move

    next_tons = [max(0.0, ton + delta) for ton, delta in zip(tons, deltas)]

    if cap_total_ton > 0:
        cap_per_channel = cap_total_ton / len(next_tons)
        next_tons = [min(cap_per_channel, ton) for ton in next_tons]

    residual = sum(tons) - sum(next_tons)
    if abs(residual) > 1e-9 and next_tons:
        next_tons[0] = max(0.0, next_tons[0] + residual)

    return next_tons, moved_total


def advance_multicell_stockpile(
    channel_tons: list[float],
    qin_requested_tph: float,
    qout_requested_tph: float,
    cap_total_ton: float,
    delta_t_h: float,
    config: MultiCellConfig,
    lateral_transfer_coeff_h: float = 0.0,
) -> dict:
    n_channels = len(channel_tons)
    if n_channels == 0:
        return {
            "channel_tons_next": [],
            "accepted_feed_tph": 0.0,
            "overflow_ton": 0.0,
            "rejected_feed_tph": max(0.0, float(qin_requested_tph)),
            "qout_effective_tph": 0.0,
            "active_channels": 0,
            "rate_cap_tph": 0.0,
            "lateral_moved_ton": 0.0,
        }

    cap_per_channel = cap_total_ton / n_channels
    qin_splits = [float(qin_requested_tph) * w for w in config.feed_weights]
    base_rate_cap = calibrated_rate_cap_tph(qout_requested_tph, channel_tons, cap_total_ton, config)
    spatial_factor = spatial_capacity_factor(channel_tons, cap_total_ton, config)
    rate_cap = min(float(config.max_rate_tph), float(base_rate_cap) * float(spatial_factor))
    qout_splits, active_channels = _allocate_requested_reclaim(
        requested_rate_tph=rate_cap,
        qin_splits_tph=qin_splits,
        channel_tons=channel_tons,
        cap_per_channel_ton=cap_per_channel,
        delta_t_h=delta_t_h,
        active_threshold_pct=config.active_threshold_pct,
    )

    next_tons: list[float] = []
    accepted_feed = 0.0
    overflow = 0.0
    rejected_feed = 0.0
    qout_effective = 0.0

    for ton, qin_i, qout_i in zip(channel_tons, qin_splits, qout_splits):
        ton_next, accepted_i, overflow_i, rejected_i, qout_eff_i = update_stockpile_mass_balance(
            pile_inventory_ton=float(ton),
            f_in_requested=float(qin_i),
            f_out_requested=float(qout_i),
            cap_max_ton=cap_per_channel,
            delta_t_h=delta_t_h,
        )
        next_tons.append(ton_next)
        accepted_feed += accepted_i
        overflow += overflow_i
        rejected_feed += rejected_i
        qout_effective += qout_eff_i

    next_tons, lateral_moved_ton = apply_lateral_transfer(
        next_tons,
        cap_total_ton=cap_total_ton,
        config=config,
        lateral_transfer_coeff_h=lateral_transfer_coeff_h,
        delta_t_h=delta_t_h,
    )

    return {
        "channel_tons_next": next_tons,
        "accepted_feed_tph": accepted_feed,
        "overflow_ton": overflow,
        "rejected_feed_tph": rejected_feed,
        "qout_effective_tph": qout_effective,
        "active_channels": active_channels,
        "rate_cap_tph": rate_cap,
        "base_rate_cap_tph": base_rate_cap,
        "spatial_capacity_factor": spatial_factor,
        "lateral_moved_ton": lateral_moved_ton,
    }


@lru_cache(maxsize=1)
def load_multicell_history(path: str | None = None) -> pd.DataFrame:
    target = Path(path) if path is not None else RAW_PILAS_REND_PATH
    return pd.read_excel(target, header=1)


@lru_cache(maxsize=4)
def _load_multicell_lookup_arrays(asset: str, path: str | None = None) -> tuple[list[str], list[int], list[list[float]]]:
    df = load_multicell_history(path)
    if "fecha" not in df.columns:
        return [], [], []
    layout = DEFAULT_MULTICELL_LAYOUTS[asset]
    cols = list(layout["source_columns"])
    work = df[["fecha"] + cols].copy()
    work["fecha"] = pd.to_datetime(work["fecha"], errors="coerce")
    for col in cols:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
    if work.empty:
        return cols, [], []
    timestamps_ns = [int(ts.value) for ts in work["fecha"]]
    rows = [
        [max(0.0, float(v)) if pd.notna(v) else 0.0 for v in row]
        for row in work[cols].to_numpy(dtype=float)
    ]
    return cols, timestamps_ns, rows


def lookup_channel_levels_at_time(
    asset: str,
    timestamp,
    max_gap_min: float = 15.0,
    path: str | None = None,
) -> list[float] | None:
    import bisect

    cols, timestamps_ns, rows = _load_multicell_lookup_arrays(asset, path)
    if not timestamps_ns:
        return None

    ts = pd.Timestamp(timestamp)
    ts_ns = int(ts.value)
    idx = bisect.bisect_left(timestamps_ns, ts_ns)
    candidates: list[int] = []
    if idx < len(timestamps_ns):
        candidates.append(int(idx))
    if idx > 0:
        candidates.append(int(idx - 1))
    if not candidates:
        return None

    best_idx = min(candidates, key=lambda i: abs(timestamps_ns[i] - ts_ns))
    best_gap_min = abs(timestamps_ns[best_idx] - ts_ns) / 60_000_000_000.0
    if best_gap_min > max_gap_min:
        return None

    levels = rows[best_idx]
    if not levels:
        return None
    return list(levels)


def summarize_sensor_quality(df: pd.DataFrame) -> dict[str, dict[str, float | int | bool]]:
    cols = []
    for layout in DEFAULT_MULTICELL_LAYOUTS.values():
        cols.extend(layout["source_columns"])
        for ignored in layout["ignored_channels"]:
            if ignored in ("C", "3"):
                continue
    mapped = {
        "SAG1:C": "SAG:LI2016C",
        "SAG2:3": "SAG2:260_LI_PILA03",
    }
    cols.extend(mapped.values())

    out: dict[str, dict[str, float | int | bool]] = {}
    total = len(df)
    for col in cols:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        finite = s.dropna()
        nunique = int(finite.nunique(dropna=True))
        std = float(finite.std()) if not finite.empty else 0.0
        out[col] = {
            "coverage_pct": round(finite.size / total * 100.0, 2) if total else 0.0,
            "nunique": nunique,
            "std": round(std, 6),
            "frozen": bool(nunique <= 1 or std <= 1e-9),
        }
    return out


def calibrate_rate_table_from_history(
    df: pd.DataFrame,
    asset: str,
    rate_col: str,
    candidate_columns: list[str] | tuple[str, ...],
    max_rate_tph: float,
    active_threshold_pct: float = ACTIVE_THRESHOLD_PCT,
    quantile: float = 0.9,
    min_coverage_pct: float = 75.0,
) -> dict:
    quality = summarize_sensor_quality(df)
    usable_cols = [
        col for col in candidate_columns
        if quality.get(col, {}).get("coverage_pct", 0.0) >= min_coverage_pct
        and not quality.get(col, {}).get("frozen", False)
    ]
    work = df[list(usable_cols) + [rate_col]].copy()
    for col in usable_cols + [rate_col]:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=list(usable_cols) + [rate_col])
    work["active_channels"] = (work[list(usable_cols)] > active_threshold_pct).sum(axis=1)

    grouped = (
        work.groupby("active_channels")[rate_col]
        .agg(["count", "mean", "median", lambda s: s.quantile(quantile)])
        .reset_index()
    )
    grouped.columns = ["active_channels", "count", "mean_rate_tph", "median_rate_tph", "quantile_rate_tph"]
    grouped = grouped.sort_values("active_channels").reset_index(drop=True)

    monotonic: dict[int, float] = {0: 0.0}
    running = 0.0
    for row in grouped.itertuples(index=False):
        running = max(running, float(row.quantile_rate_tph))
        monotonic[int(row.active_channels)] = min(float(max_rate_tph), running)

    return {
        "asset": asset,
        "active_threshold_pct": active_threshold_pct,
        "quantile": quantile,
        "usable_columns": list(usable_cols),
        "dropped_columns": [c for c in candidate_columns if c not in usable_cols],
        "quality": quality,
        "summary": grouped.to_dict(orient="records"),
        "rate_table_tph": monotonic,
    }
