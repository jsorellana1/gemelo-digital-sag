"""
build_event_variable_table_corrected.py — Igual que build_event_
variable_table.py, pero usando las fuentes con correa_315 reconstruida
(sensor roto confirmado desde 2026-04-30, ver 04_Reports/Technical/
Diagnostico_Causa_Deriva_Temporal_PAM.md):

- advanced_t8_historical_5min_corrected.parquet (en vez de la original)
- advanced_t8_event_windows_corrected.parquet (en vez de la original)

Requiere haber corrido primero rebuild_corrected_historical_series.py.
No modifica los parquets originales -- lee las copias _corrected.

Ejecutar: python 02_Analytics/Scripts/statistical_validation/build_event_variable_table_corrected.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "05_Dashboard"))
_REPORTS_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "04_Reports", "Technical"))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))
sys.path.insert(0, _DASHBOARD)

from engine.historical_backtesting import (  # noqa: E402
    _evento_en_rango, _with_historical_multicell_levels, check_prerequisito_0,
)
from engine.ode_model import P90, CRITICAL_PCT  # noqa: E402
from engine.diagnostics import regime_event_detector as _red  # noqa: E402

HOLDOUT_CUTOFF = pd.Timestamp("2026-04-30")

BREAKPOINTS_SAG1 = {"35pct": 35.0, "25pct": 25.0, "crit5pct": CRITICAL_PCT["SAG1"] + 5.0}


def _cargar_serie_corregida() -> pd.DataFrame:
    df = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_historical_5min_corrected.parquet"))
    return df.sort_values("fecha").reset_index(drop=True)


# Monkeypatch: detectar_todos_los_regimenes() llama a _load_serie() por
# nombre de modulo -- reemplazarla aqui hace que TODA la deteccion de
# eventos proxy (incluida check_prerequisito_0) use la serie corregida,
# sin tocar el archivo de produccion.
_red._load_serie = _cargar_serie_corregida


def _cruces(trayectoria_pct: list[float], breakpoints: dict[str, float]) -> dict[str, bool]:
    if not trayectoria_pct:
        return {k: False for k in breakpoints}
    minimo = min(v for v in trayectoria_pct if v is not None and not (isinstance(v, float) and np.isnan(v)))
    return {k: bool(minimo < umbral) for k, umbral in breakpoints.items()}


def _fila_base(regimen_base: str, asset: str, split: str, event_start) -> dict:
    return {
        "regimen": regimen_base, "asset": asset, "split": split,
        "hora_dia": event_start.hour if hasattr(event_start, "hour") else None,
    }


def _proxy_rows(regimen_base: str) -> list[dict]:
    from engine.simulator import simulate_scenario_cached

    prereq = check_prerequisito_0()[regimen_base]
    if not prereq.disponible:
        print(f"  [{regimen_base}] SIN DATOS SUFICIENTES: {prereq.razon}")
        return []

    df = _cargar_serie_corregida()
    eventos = [
        e for e in _red.detectar_todos_los_regimenes()
        if e.es_valido_para_backtesting and e.regimen.startswith(regimen_base)
    ]
    rows = []
    for ev in eventos:
        sub = df[(df["fecha"] >= ev.inicio) & (df["fecha"] <= ev.fin)]
        if sub.empty:
            continue
        fila_ini, fila_fin = sub.iloc[0], sub.iloc[-1]
        pila1_ini, pila2_ini = fila_ini.get("pila_sag1"), fila_ini.get("pila_sag2")
        pila1_fin_obs = fila_fin.get("pila_sag1")
        if pd.isna(pila1_ini) or pd.isna(pila1_fin_obs):
            continue

        tph1_mean = float(sub["SAG1_tph"].dropna().mean()) if not sub["SAG1_tph"].dropna().empty else 0.0
        tph2_mean = float(sub["SAG2_tph"].dropna().mean()) if not sub["SAG2_tph"].dropna().empty else 0.0
        cv315_mean = float(sub["correa_315"].dropna().mean()) if not sub["correa_315"].dropna().empty else 0.0
        cv316_mean = float(sub["correa_316"].dropna().mean()) if not sub["correa_316"].dropna().empty else 0.0
        duracion_h = max(ev.duracion_min / 60.0, 0.1)

        sag1_activo = "mantenimiento_SAG1" != ev.regimen
        sag2_activo = "mantenimiento_SAG2" != ev.regimen

        sim = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini),
            pila_sag2_pct=float(pila2_ini) if not pd.isna(pila2_ini) else 50.0,
            rate_sag1_pct=tph1_mean / P90["SAG1"] * 100.0,
            rate_sag2_pct=tph2_mean / P90["SAG2"] * 100.0,
            sag1_activo=sag1_activo, sag2_activo=sag2_activo,
            duracion_t8_h=0.0, horizonte_horas=duracion_h,
            cv_mode="manual" if (cv315_mean > 0 or cv316_mean > 0) else "auto",
            cv315_manual_tph=cv315_mean, cv316_manual_tph=cv316_mean,
            **_with_historical_multicell_levels(None, ev.inicio),
        )
        pred1 = sim["pile_sag1"][-1]
        cruces = _cruces(sim.get("pile_sag1") or [], BREAKPOINTS_SAG1)

        asset = "SAG1" if ev.regimen.endswith("SAG1") else ("SAG2" if ev.regimen.endswith("SAG2") else "AMBOS")
        split = "calibracion" if pd.Timestamp(ev.inicio) <= HOLDOUT_CUTOFF else "hold_out"
        row = _fila_base(regimen_base, asset, split, ev.inicio)
        row.update({
            "evento_inicio": str(ev.inicio),
            "pila_error_pp": float(pred1 - float(pila1_fin_obs)),
            "pila_ini_pct": float(pila1_ini),
            "duracion_evento_h": duracion_h,
            "rate_gap_tph": P90["SAG1"] - tph1_mean,
            "feed_restriction_pct": (cv315_mean + cv316_mean) / (P90["SAG1"] + P90["SAG2"]) * 100.0,
            "t8_activo": False, "duracion_t8_h": 0.0,
            "cruza_35pct": cruces["35pct"], "cruza_25pct": cruces["25pct"], "cruza_crit5pct": cruces["crit5pct"],
        })
        rows.append(row)
    return rows


def _t8_rows(regimen: str) -> list[dict]:
    from engine.simulator import simulate_scenario_cached

    prereq = check_prerequisito_0()[regimen]
    if not prereq.disponible:
        print(f"  [{regimen}] SIN DATOS SUFICIENTES: {prereq.razon}")
        return []

    ev = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_official_events.parquet"))
    w = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_event_windows_corrected.parquet"))
    ev = ev[ev["duracion_h"] <= 4].copy() if regimen == "t8_corta" else ev[ev["duracion_h"] > 4].copy()
    ids = ev["evento_id"].tolist()
    w = w[w["evento_id"].isin(ids)].copy()

    rows = []
    for evento_id, grp in w.groupby("evento_id"):
        ini = grp[(grp["h_rel_inicio"] >= -0.05) & (grp["h_rel_inicio"] <= 0.10)]
        durante = grp[grp["periodo"] == "DURANTE"]
        fin = grp[grp["periodo"] == "POST"]
        if ini.empty or durante.empty or fin.empty:
            continue
        pila1_ini = ini["pila_sag1"].dropna()
        pila2_ini = ini["pila_sag2"].dropna()
        fin1 = fin.dropna(subset=["pila_sag1"])
        if pila1_ini.empty or fin1.empty:
            continue
        idx1 = (fin1["h_rel_fin"] - 0.0).abs().idxmin()
        pila1_fin_obs = float(fin1.loc[idx1, "pila_sag1"])

        tph1_mean = float(durante["SAG1_tph"].dropna().mean()) if not durante["SAG1_tph"].dropna().empty else 0.0
        tph2_mean = float(durante["SAG2_tph"].dropna().mean()) if not durante["SAG2_tph"].dropna().empty else 0.0
        cv315_mean = float(durante["correa_315"].dropna().mean()) if not durante["correa_315"].dropna().empty else 0.0
        cv316_mean = float(durante["correa_316"].dropna().mean()) if not durante["correa_316"].dropna().empty else 0.0
        duracion_h = float(grp["duracion_h"].iloc[0])
        event_start = grp["ini_oficial"].dropna().iloc[0] if "ini_oficial" in grp.columns and not grp["ini_oficial"].dropna().empty else None
        if event_start is None:
            continue

        sim = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini.iloc[0]),
            pila_sag2_pct=float(pila2_ini.iloc[0]) if not pila2_ini.empty else 50.0,
            rate_sag1_pct=tph1_mean / P90["SAG1"] * 100.0,
            rate_sag2_pct=tph2_mean / P90["SAG2"] * 100.0,
            duracion_t8_h=duracion_h, horizonte_horas=duracion_h,
            cv_mode="manual" if (cv315_mean > 0 or cv316_mean > 0) else "auto",
            cv315_manual_tph=cv315_mean, cv316_manual_tph=cv316_mean,
            **_with_historical_multicell_levels(None, event_start),
        )
        pred1 = sim["pile_sag1"][-1]
        cruces = _cruces(sim.get("pile_sag1") or [], BREAKPOINTS_SAG1)

        split = "calibracion" if pd.Timestamp(event_start) <= HOLDOUT_CUTOFF else "hold_out"
        row = _fila_base(regimen, "SAG1", split, pd.Timestamp(event_start))
        row.update({
            "evento_inicio": str(event_start),
            "pila_error_pp": float(pred1 - pila1_fin_obs),
            "pila_ini_pct": float(pila1_ini.iloc[0]),
            "duracion_evento_h": duracion_h,
            "rate_gap_tph": P90["SAG1"] - tph1_mean,
            "feed_restriction_pct": (cv315_mean + cv316_mean) / (P90["SAG1"] + P90["SAG2"]) * 100.0,
            "t8_activo": True, "duracion_t8_h": duracion_h,
            "cruza_35pct": cruces["35pct"], "cruza_25pct": cruces["25pct"], "cruza_crit5pct": cruces["crit5pct"],
        })
        rows.append(row)
    return rows


def main() -> None:
    all_rows: list[dict] = []
    print("Construyendo tabla de eventos CON cv315 reconstruida (fuentes _corrected)...")
    for regimen in ("t8_corta",):
        rows = _t8_rows(regimen)
        print(f"  [{regimen}] {len(rows)} eventos")
        all_rows.extend(rows)
    for regimen in ("inventario_critico", "overflow", "mantenimiento", "alimentacion_restringida"):
        rows = _proxy_rows(regimen)
        print(f"  [{regimen}] {len(rows)} eventos")
        all_rows.extend(rows)

    if not all_rows:
        raise RuntimeError("No se genero ninguna fila -- revisar prerequisitos de datos.")

    tabla = pd.DataFrame(all_rows)
    out_path = os.path.join(_REPORTS_DIR, "event_variable_table_corrected.csv")
    tabla.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\nTabla guardada: {out_path} ({len(tabla)} eventos totales)")
    print(tabla.groupby(["regimen", "split"]).size())


if __name__ == "__main__":
    main()
