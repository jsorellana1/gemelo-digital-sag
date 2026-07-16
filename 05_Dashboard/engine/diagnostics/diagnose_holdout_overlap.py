"""
diagnose_holdout_overlap.py - Diagnostico reproducible del solape entre
la calibracion historica de DRAIN_PCT_H y el backtesting oficial T8.

Objetivo:
1. Medir si advanced_t8_official_events.parquet contiene eventos que
   caen dentro de las ventanas usadas para calibrar DRAIN_PCT_H
   (fact_eventos_t8.parquet).
2. Proponer cortes temporales factibles para construir un hold-out real.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", ".."))
_ROOT = os.path.normpath(os.path.join(_DASHBOARD, ".."))
if _DASHBOARD not in sys.path:
    sys.path.insert(0, _DASHBOARD)

FACT_PATH = os.path.join(_ROOT, "01_Data", "Processed", "fact_eventos_t8.parquet")
ADV_PATH = os.path.join(_ROOT, "01_Data", "Cache", "advanced_t8_official_events.parquet")


def _load_windows() -> tuple[pd.DataFrame, pd.DataFrame]:
    fact = pd.read_parquet(FACT_PATH)
    adv = pd.read_parquet(ADV_PATH)

    fact_w = fact[["ventana_id", "inicio", "fin", "duracion_h"]].drop_duplicates().copy()
    fact_w["inicio"] = pd.to_datetime(fact_w["inicio"])
    fact_w["fin"] = pd.to_datetime(fact_w["fin"])
    fact_w["fecha_inicio"] = fact_w["inicio"].dt.normalize()
    fact_w["fecha_fin"] = fact_w["fin"].dt.normalize()
    fact_w = fact_w.sort_values(["fecha_inicio", "ventana_id"]).reset_index(drop=True)

    adv_w = adv[["evento_id", "fecha", "duracion_h", "ini_oficial", "fin_oficial"]].copy()
    adv_w["fecha"] = pd.to_datetime(adv_w["fecha"]).dt.normalize()
    adv_w["ini_oficial"] = pd.to_datetime(adv_w["ini_oficial"])
    adv_w["fin_oficial"] = pd.to_datetime(adv_w["fin_oficial"])
    adv_w = adv_w.sort_values(["fecha", "evento_id"]).reset_index(drop=True)
    return fact_w, adv_w


def _bucket_counts(series: pd.Series) -> dict[str, int]:
    bins = pd.cut(series, bins=[-1, 2, 6, 12, 10**9], labels=["<=2h", "3-6h", "7-12h", ">12h"])
    counts = bins.value_counts().sort_index()
    return {str(k): int(v) for k, v in counts.items()}


def run_diagnosis() -> dict:
    fact_w, adv_w = _load_windows()

    overlap_rows = []
    for _, ev in adv_w.iterrows():
        matches = fact_w[(fact_w["fecha_inicio"] <= ev["fecha"]) & (fact_w["fecha_fin"] >= ev["fecha"])]
        overlap_rows.append({
            "evento_id": ev["evento_id"],
            "fecha": ev["fecha"],
            "duracion_h_adv": float(ev["duracion_h"]),
            "n_fact_windows_covering": int(len(matches)),
            "fact_ids": matches["ventana_id"].tolist(),
        })
    overlap = pd.DataFrame(overlap_rows)

    exact_matches = fact_w.merge(
        adv_w,
        left_on=["fecha_inicio", "duracion_h"],
        right_on=["fecha", "duracion_h"],
        how="inner",
    )

    cutoff_candidates = []
    for cutoff in pd.to_datetime(["2026-03-31", "2026-04-15", "2026-04-30", "2026-05-15", "2026-05-31"]):
        fact_cal = fact_w[fact_w["fecha_fin"] <= cutoff]
        fact_hold = fact_w[fact_w["fecha_inicio"] > cutoff]
        adv_cal = adv_w[adv_w["fecha"] <= cutoff]
        adv_hold = adv_w[adv_w["fecha"] > cutoff]
        cutoff_candidates.append({
            "cutoff": cutoff.date().isoformat(),
            "fact_cal_windows": int(len(fact_cal)),
            "fact_hold_windows": int(len(fact_hold)),
            "adv_cal_events": int(len(adv_cal)),
            "adv_hold_events": int(len(adv_hold)),
            "adv_cal_short": int((adv_cal["duracion_h"] <= 4).sum()),
            "adv_hold_short": int((adv_hold["duracion_h"] <= 4).sum()),
            "fact_cal_buckets": _bucket_counts(fact_cal["duracion_h"]),
        })

    return {
        "fact_windows": fact_w,
        "adv_events": adv_w,
        "overlap": overlap,
        "exact_matches": exact_matches,
        "cutoff_candidates": cutoff_candidates,
        "summary": {
            "fact_windows_n": int(len(fact_w)),
            "adv_events_n": int(len(adv_w)),
            "adv_events_covered_by_any_fact_window": int((overlap["n_fact_windows_covering"] > 0).sum()),
            "adv_events_not_covered": int((overlap["n_fact_windows_covering"] == 0).sum()),
            "exact_fecha_duracion_matches": int(len(exact_matches)),
            "fact_start_min": fact_w["fecha_inicio"].min().date().isoformat(),
            "fact_end_max": fact_w["fecha_fin"].max().date().isoformat(),
            "adv_start_min": adv_w["fecha"].min().date().isoformat(),
            "adv_end_max": adv_w["fecha"].max().date().isoformat(),
        },
    }


if __name__ == "__main__":
    r = run_diagnosis()
    s = r["summary"]
    print("=== Solape calibracion vs backtesting oficial ===")
    print(
        f"fact windows={s['fact_windows_n']} ({s['fact_start_min']} -> {s['fact_end_max']}) | "
        f"adv events={s['adv_events_n']} ({s['adv_start_min']} -> {s['adv_end_max']})"
    )
    print(
        f"adv cubiertos por >=1 ventana de calibracion: "
        f"{s['adv_events_covered_by_any_fact_window']}/{s['adv_events_n']}"
    )
    print(f"matches exactos fecha_inicio+duracion: {s['exact_fecha_duracion_matches']}")
    print()
    print("=== Cortes candidatos para hold-out real ===")
    for c in r["cutoff_candidates"]:
        print(
            f"{c['cutoff']}: "
            f"fact cal/hold={c['fact_cal_windows']}/{c['fact_hold_windows']} | "
            f"adv cal/hold={c['adv_cal_events']}/{c['adv_hold_events']} | "
            f"t8_corta cal/hold={c['adv_cal_short']}/{c['adv_hold_short']}"
        )
