"""
calibrar_bola_delta_tph.py
Script offline: calibra el efecto real (dTPH) de activar molinos de bola
SAG1 (411/412) y SAG2 (511/512) a partir de datos historicos PI Historian.

Metodo: media estratificada controlada por banda de feed de chancado.
(OLS naive sobreestima: operadores activan bolas cuando produccion ya es alta.)

Output:  01_Data/Cache/bola_delta_tph.json
Figura:  02_Analytics/Figures/12_Optimizer_v2/05_bola_delta_calibracion.png
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---- Paths -------------------------------------------------------------------
_HERE  = Path(__file__).resolve().parent          # .../02_Analytics/Scripts
_ROOT  = _HERE.parent.parent                       # .../07_Rendimientos
DATA_RAW   = _ROOT / "01_Data"  / "Raw"
CACHE_DIR  = _ROOT / "01_Data"  / "Cache"
FIG_DIR    = _ROOT / "02_Analytics" / "Figures" / "12_Optimizer_v2"
OUT_JSON   = CACHE_DIR / "bola_delta_tph.json"
OUT_FIG    = FIG_DIR   / "05_bola_delta_calibracion.png"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Añadir engine al path para reutilizar loaders
sys.path.insert(0, str(_ROOT / "05_Dashboard"))
from engine.realtime_loader import _load_tonelaje, _load_estados  # noqa: E402
from engine.ode_model import P90                                   # noqa: E402

# ---- Parametros operacionales ------------------------------------------------
RATE_SAG1_MIN, RATE_SAG1_MAX = 400.0, 1700.0
RATE_SAG2_MIN, RATE_SAG2_MAX = 800.0, 2700.0
T8_DROP_THRESHOLD = 0.55    # igual que detect_t8()
T8_ROLLING_W      = 60      # ventana 5h (60 filas x 5min)
MIN_N0            = 200     # n minimo en estrato n_bolas=0 para calibracion valida
BOLA_BONUS_LEGACY = 0.08    # referencia modelo anterior (ingenieria)
MAX_DELTA_FRAC    = 0.15    # cap: max dTPH = 15% de P90


# ---- Carga -------------------------------------------------------------------

def _load_join() -> pd.DataFrame:
    df_ton = _load_tonelaje()
    df_est = _load_estados()
    df_ton = df_ton.sort_values("Fecha").reset_index(drop=True)
    df_est = df_est.sort_values("Fecha").reset_index(drop=True)
    df = pd.merge_asof(
        df_ton[["Fecha", "cv315", "cv316", "pila_sag1", "pila_sag2",
                "rate_sag1", "rate_sag2"]],
        df_est[["Fecha", "SAG1", "SAG2", "mobo411", "mobo412",
                "mobo511", "mobo512"]],
        on="Fecha",
        direction="nearest",
        tolerance=pd.Timedelta("10min"),
    ).dropna(subset=["SAG1", "rate_sag1"])
    return df


# ---- Flag T8 -----------------------------------------------------------------

def _flag_t8(df: pd.DataFrame) -> pd.Series:
    cv_total = df["cv315"] + df["cv316"]
    baseline = cv_total.rolling(T8_ROLLING_W, min_periods=20).median().shift(T8_ROLLING_W)
    baseline = baseline.bfill().fillna(cv_total.median())
    return (baseline > 200) & (cv_total < T8_DROP_THRESHOLD * baseline)


# ---- Calibracion -------------------------------------------------------------

def _calibrate_asset(
    df: pd.DataFrame,
    asset: str,
    rate_col: str,
    pila_col: str,
    bola_cols: list,
    rate_min: float,
    rate_max: float,
    p90_ref: float,
) -> dict:
    """
    Calibra dTPH por molino de bola usando media estratificada controlada
    por banda de feed de chancado (elimina sesgo de seleccion).
    """
    df = df.copy()
    df["n_bolas"] = df[bola_cols[0]].astype(int) + df[bola_cols[1]].astype(int)
    df["cv_total"] = df["cv315"] + df["cv316"]

    mask = (
        df[asset].eq(True)
        & df["SAG1"].eq(True) & df["SAG2"].eq(True)
        & df[rate_col].between(rate_min, rate_max)
        & df[pila_col].between(5.0, 98.0)
        & df["cv_total"].between(500, 5000)
        & (~df["_t8_activo"])
    )
    sub = df.loc[mask, [rate_col, pila_col, "n_bolas", "cv_total"]].dropna().copy()

    n_total  = len(sub)
    strata_n = sub["n_bolas"].value_counts().sort_index()
    n0 = int(strata_n.get(0, 0))
    n1 = int(strata_n.get(1, 0))
    n2 = int(strata_n.get(2, 0))
    strata_n_dict = {str(k): int(v) for k, v in strata_n.items()}

    base_mean = float(sub[rate_col].mean())

    # ---- Verificar si hay suficiente grupo de control (n_bolas=0) ------------
    # Sin grupo de control adecuado, la calibracion empirica es invalida.
    # En estos datos, SAG2 NUNCA opera sin bolas (n0=0) y SAG1 casi nunca
    # (n0~11), por lo que usamos el modelo de ingenieria legacy como referencia.
    warning = None
    method = "legacy_engineering"

    if n0 < MIN_N0:
        w = (f"n_bolas=0 insuficiente (n0={n0} < {MIN_N0}): no hay grupo de control "
             f"para calibrar dTPH empiricamente. Se usa modelo de ingenieria "
             f"BOLA_BONUS={BOLA_BONUS_LEGACY} (={BOLA_BONUS_LEGACY*100:.0f}% de P90).")
        warning = w
        print(f"  [fallback] {asset}: {w}")
        delta_1 = round(BOLA_BONUS_LEGACY * p90_ref, 1)
        delta_2 = round(BOLA_BONUS_LEGACY * 2 * p90_ref, 1)
    else:
        # Hay suficientes datos: media estratificada controlada por banda de feed
        method = "stratified_controlled"
        means_raw = sub.groupby("n_bolas")[rate_col].mean()
        m0_raw = float(means_raw.get(0, sub[rate_col].mean()))

        delta_1_bands = []
        delta_2_bands = []
        try:
            sub["cv_band"] = pd.qcut(sub["cv_total"], q=4, labels=False, duplicates="drop")
            for _, grp in sub.groupby("cv_band"):
                g0 = grp.loc[grp["n_bolas"] == 0, rate_col]
                g1 = grp.loc[grp["n_bolas"] == 1, rate_col]
                g2 = grp.loc[grp["n_bolas"] == 2, rate_col]
                if len(g0) >= 10 and len(g1) >= 5:
                    delta_1_bands.append(g1.mean() - g0.mean())
                if len(g0) >= 10 and len(g2) >= 5:
                    delta_2_bands.append(g2.mean() - g0.mean())
        except Exception as e:
            warning = f"bandas fallaron: {e}"

        delta_1 = float(np.median(delta_1_bands)) if delta_1_bands else max(0.0, float(means_raw.get(1, m0_raw)) - m0_raw)
        delta_2 = float(np.median(delta_2_bands)) if delta_2_bands else max(0.0, float(means_raw.get(2, m0_raw)) - m0_raw)
        delta_1 = max(0.0, delta_1)
        delta_2 = max(delta_1, max(0.0, delta_2))

        # Cap de sanidad
        cap = MAX_DELTA_FRAC * p90_ref
        if delta_1 > cap:
            w = f"delta_1={delta_1:.1f} excede cap {cap:.1f} -> usando cap"
            warning = (warning + " | " + w) if warning else w
            print(f"  [cap] {asset}: {w}")
            delta_1 = cap
        if delta_2 > cap * 2:
            delta_2 = cap * 2

    print(f"  {asset}: {method}, D1={delta_1:.1f} TPH, D2={delta_2:.1f} TPH, "
          f"base={base_mean:.1f} TPH, n={n_total} (0:{n0} 1:{n1} 2:{n2})")

    return {
        "delta_tph_per_bola": round(delta_1, 1),
        "delta_tph_1bola":    round(delta_1, 1),
        "delta_tph_2bola":    round(delta_2, 1),
        "base_tph_mean":      round(base_mean, 1),
        "n_total":            n_total,
        "n_per_stratum":      strata_n_dict,
        "method":             method,
        "warning":            warning,
    }


# ---- Figura de diagnostico ---------------------------------------------------

def _make_figure(df: pd.DataFrame, res: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Calibracion dTPH Molinos de Bola - Datos historicos PI",
                 fontsize=13, fontweight="bold")

    for ax, asset, rate_col, bola_cols, r_lim in [
        (axes[0], "SAG1", "rate_sag1", ["mobo411", "mobo412"], (400, 1700)),
        (axes[1], "SAG2", "rate_sag2", ["mobo511", "mobo512"], (800, 2700)),
    ]:
        sub = df.copy()
        sub["n_bolas"] = sub[bola_cols[0]].astype(int) + sub[bola_cols[1]].astype(int)
        mask = (
            sub[asset].eq(True)
            & sub["SAG1"].eq(True) & sub["SAG2"].eq(True)
            & sub[rate_col].between(*r_lim)
            & (~sub["_t8_activo"])
        )
        s = sub.loc[mask, [rate_col, "n_bolas"]].dropna()
        colors = {0: "#1f77b4", 1: "#ff7f0e", 2: "#2ca02c"}
        for n in [0, 1, 2]:
            vals = s.loc[s["n_bolas"] == n, rate_col]
            if len(vals) > 0:
                ax.hist(vals, bins=40, alpha=0.55, color=colors[n],
                        label=f"{n} bolas (n={len(vals):,})")
                ax.axvline(vals.mean(), color=colors[n], lw=2, ls="--")
        r = res[asset]
        ax.set_title(
            f"{asset}: D1={r['delta_tph_1bola']:.0f} TPH / D2={r['delta_tph_2bola']:.0f} TPH"
            f"\nMetodo: {r['method']}",
            fontsize=10,
        )
        ax.set_xlabel("Rate SAG (TPH)")
        ax.set_ylabel("Frecuencia")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(str(OUT_FIG), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Figura guardada: {OUT_FIG}")


# ---- Main --------------------------------------------------------------------

def main():
    print("=" * 65)
    print("CALIBRACION dTPH MOLINOS DE BOLA")
    print("=" * 65)

    print("\n[1/4] Cargando datos historicos...")
    df = _load_join()
    print(f"  Registros tras merge: {len(df):,}")

    print("\n[2/4] Detectando periodos T8...")
    df["_t8_activo"] = _flag_t8(df)
    n_t8 = df["_t8_activo"].sum()
    print(f"  Filas T8 activo (excluidas): {n_t8:,} ({100*n_t8/len(df):.1f}%)")

    print("\n[3/4] Calibrando SAG1 (molinos 411/412)...")
    res_sag1 = _calibrate_asset(
        df, "SAG1", "rate_sag1", "pila_sag1",
        ["mobo411", "mobo412"],
        RATE_SAG1_MIN, RATE_SAG1_MAX,
        P90["SAG1"],
    )

    print("\n[3/4] Calibrando SAG2 (molinos 511/512)...")
    res_sag2 = _calibrate_asset(
        df, "SAG2", "rate_sag2", "pila_sag2",
        ["mobo511", "mobo512"],
        RATE_SAG2_MIN, RATE_SAG2_MAX,
        P90["SAG2"],
    )

    legacy_sag1 = round(P90["SAG1"] * BOLA_BONUS_LEGACY, 1)
    legacy_sag2 = round(P90["SAG2"] * BOLA_BONUS_LEGACY, 1)
    print(f"\n  Legacy  : SAG1 +{legacy_sag1} TPH/bola | SAG2 +{legacy_sag2} TPH/bola")
    print(f"  Calibrad: SAG1 +{res_sag1['delta_tph_1bola']} TPH/bola | "
          f"SAG2 +{res_sag2['delta_tph_1bola']} TPH/bola")

    output = {
        "version": "v1.0",
        "fecha_calibracion": "2026-07-01",
        "SAG1": res_sag1,
        "SAG2": res_sag2,
        "legacy_bola_bonus": BOLA_BONUS_LEGACY,
        "legacy_delta_sag1_tph": legacy_sag1,
        "legacy_delta_sag2_tph": legacy_sag2,
        "notes": (
            "Media estratificada controlada por banda de feed de chancado. "
            "T8-activo excluido. Cap: 15% de P90 por bola. "
            "Datos: ~93k filas a 5-min frecuencia, PI Historian."
        ),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[4/4] JSON guardado: {OUT_JSON}")

    print("\n[4/4] Generando figura...")
    try:
        _make_figure(df, {"SAG1": res_sag1, "SAG2": res_sag2})
    except Exception as e:
        print(f"  Figura no generada: {e}")

    print("\nCalibración completa.")
    print(f"  -> {OUT_JSON}")
    return output


if __name__ == "__main__":
    main()
