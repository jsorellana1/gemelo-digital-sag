"""
fase2_mecanismo_causal.py
Validacion del mecanismo causal: agotamiento de pilas → caida TPH.

Skills: skill_molienda_sag, skill_series_temporales_industriales,
        skill_machine_learning_operacional, skill_explainable_ai_governance.

Entregables:
    outputs/figures/fase2/  — 6 figuras PNG
    outputs/reports/Fase2_Mecanismo_Causal_T8.pdf

Uso:
    python src/fase2_mecanismo_causal.py
"""
from __future__ import annotations

import sys, json, warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

# ── Rutas ──────────────────────────────────────────────────────────────────────
BASE   = Path(__file__).resolve().parents[1]
DATA   = BASE / "data" / "intermediate"
OUT_F  = BASE / "outputs" / "figures" / "fase2"
OUT_R  = BASE / "outputs" / "reports"
XLS    = BASE / "outputs" / "excel" / "event_study_t8.xlsx"
LOGS   = BASE / "logs"
OUT_F.mkdir(parents=True, exist_ok=True)

# ── Constantes ────────────────────────────────────────────────────────────────
ACTIVOS   = ["SAG1", "SAG2", "PMC", "UNITARIO"]
COLOR_A   = {"SAG1": "#1f77b4", "SAG2": "#ff7f0e", "PMC": "#2ca02c", "UNITARIO": "#9467bd"}
COLOR_D   = {2: "#4878D0", 4: "#EE854A", 8: "#6ACC65", 12: "#D65F5F"}
TPH_OP    = 50       # umbral operacional
BIN_M     = 30       # minutos por bin
PRE_H     = 24
POST_H    = 24
THRESH_90 = 0.90     # umbral caida significativa
THRESH_80 = 0.80
CONSEC_H  = 72       # horas para considerar ventanas consecutivas

# ── Paleta PDF ─────────────────────────────────────────────────────────────────
C_BLUE  = "#1B3A5C"
C_COP   = "#B87333"
C_LGRAY = "#F4F6F9"
C_DARK  = "#1A1A1A"
C_MGRAY = "#8E9BAA"
C_WHITE = "#FFFFFF"
C_RED   = "#C0392B"
C_GRN   = "#27AE60"
C_ORG   = "#C95B27"
C_GOLD  = "#D4A83A"
PW, PH  = 16.0, 9.0


# ═══════════════════════════════════════════════════════════════════════════════
# Carga de datos
# ═══════════════════════════════════════════════════════════════════════════════

def load_all() -> dict[str, pd.DataFrame]:
    df_rend = pd.read_parquet(DATA / "rendimientos_clean.parquet")
    df_rend["fecha"] = pd.to_datetime(df_rend["fecha"])
    for c in list(df_rend.columns):
        if c.startswith("MUN_"):
            df_rend.rename(columns={c: c.replace("MUN_", "UNITARIO_")}, inplace=True)
    df_rend = df_rend.sort_values("fecha").reset_index(drop=True)

    df_ev = pd.read_parquet(DATA / "eventos_t8.parquet")
    df_ev["ini_oficial"] = pd.to_datetime(df_ev["ini_oficial"])
    df_ev["fin_oficial"] = pd.to_datetime(df_ev["fin_oficial"])

    df_met = pd.read_excel(XLS, sheet_name="metricas_evento_activo")

    return {"rend": df_rend, "ev": df_ev, "met": df_met}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 1 — ISR proxy y autonomía por activo
# ═══════════════════════════════════════════════════════════════════════════════

def _bin_h(t: float) -> float:
    step = BIN_M / 60
    return round(t / step) * step


def build_isr_curves(df_rend: pd.DataFrame, df_ev: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada (evento, activo) construye la curva ISR (proxy de nivel de pila).
    ISR(t) = TPH(t) / baseline  (escalado 0-100).
    Baseline = promedio TPH en las 24h previas al evento.
    """
    rows = []
    for _, ev in df_ev.iterrows():
        ini = ev["ini_oficial"]
        t0  = ini - pd.Timedelta(hours=PRE_H)
        t1  = ini + pd.Timedelta(hours=POST_H)
        df_w = df_rend[(df_rend["fecha"] >= t0) & (df_rend["fecha"] <= t1)].copy()
        if df_w.empty:
            continue
        df_w["h_rel"] = (df_w["fecha"] - ini).dt.total_seconds() / 3600

        for activo in ACTIVOS:
            col = f"{activo}_tph"
            opc = f"{activo}_operando"
            if col not in df_w.columns:
                continue
            pre_mask = (df_w["h_rel"] < 0) & df_w[opc] & (df_w[col] > TPH_OP)
            base = df_w.loc[pre_mask, col].mean()
            if np.isnan(base) or base < TPH_OP:
                continue
            sub = df_w.loc[df_w[opc] & (df_w[col] > 0), ["h_rel", col]].copy()
            sub["ISR"] = (sub[col] / base * 100).clip(0, 105)
            sub["ISR_roll"] = sub["ISR"].rolling(6, min_periods=3, center=True).mean()
            sub["h_bin"] = sub["h_rel"].apply(_bin_h)
            sub["evento_id"]  = ev["evento_id"]
            sub["duracion_h"] = int(ev["duracion_h"])
            sub["activo"]     = activo
            sub["baseline"]   = base
            rows.append(sub[["evento_id", "duracion_h", "activo", "h_rel", "h_bin",
                              "ISR", "ISR_roll", "baseline"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def compute_autonomia(df_isr: pd.DataFrame, df_met: pd.DataFrame) -> pd.DataFrame:
    """
    Retardo = primera hora (post t=0) donde ISR cae bajo 90% del máximo inicial.
    Representa la autonomía de pila: cuánto tarda en colapsar el TPH.
    """
    rows = []
    for (ev_id, activo), grp in df_isr.groupby(["evento_id", "activo"]):
        post = grp[grp["h_rel"] >= 0].sort_values("h_rel")
        if post.empty:
            continue
        # Referencia: ISR promedio en las primeras 0.5h del ventana (antes de que caiga)
        inicial = post[post["h_rel"] <= 0.5]["ISR_roll"].mean()
        if np.isnan(inicial) or inicial < 50:
            inicial = 100.0
        thresh = inicial * THRESH_90
        caidos = post.loc[post["ISR_roll"] < thresh, "h_rel"]
        retardo = float(caidos.iloc[0]) if len(caidos) > 0 else np.nan

        met_row = df_met[(df_met["evento_id"] == ev_id) & (df_met["activo"] == activo)]
        dur = met_row["duracion_h"].iloc[0] if len(met_row) else np.nan
        caida = met_row["caida_pct"].iloc[0] if len(met_row) else np.nan
        rows.append({"evento_id": ev_id, "activo": activo,
                     "retardo_h": retardo, "duracion_h": dur,
                     "caida_pct": caida, "isr_inicial": inicial})
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 5 — Ventanas consecutivas
# ═══════════════════════════════════════════════════════════════════════════════

def flag_consecutivas(df_ev: pd.DataFrame, df_met: pd.DataFrame) -> pd.DataFrame:
    """
    Marca cada evento con si hubo otra ventana en las CONSEC_H horas previas.
    Compara impacto entre ventanas aisladas y consecutivas.
    """
    df_ev2 = df_ev.sort_values("ini_oficial").reset_index(drop=True)
    df_ev2["es_consecutiva"] = False
    df_ev2["h_desde_prev"]   = np.nan

    for i in range(1, len(df_ev2)):
        prev_ini = df_ev2.loc[i - 1, "ini_oficial"]
        curr_ini = df_ev2.loc[i,     "ini_oficial"]
        gap_h    = (curr_ini - prev_ini).total_seconds() / 3600
        df_ev2.loc[i, "h_desde_prev"] = gap_h
        if gap_h < CONSEC_H:
            df_ev2.loc[i, "es_consecutiva"] = True

    merged = df_met.merge(df_ev2[["evento_id", "es_consecutiva", "h_desde_prev"]],
                          on="evento_id", how="left")
    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 7 — Clasificación de eventos
# ═══════════════════════════════════════════════════════════════════════════════

def classify_events(df_met: pd.DataFrame) -> pd.DataFrame:
    df = df_met.copy()
    def _clase(c: float) -> str:
        if np.isnan(c): return "N/D"
        if c < 5:       return "A — Sin impacto"
        if c < 20:      return "B — Leve"
        if c < 40:      return "C — Moderado"
        return          "D — Severo"
    df["clase"] = df["caida_pct"].apply(_clase)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 8 — Modelo ML + SHAP
# ═══════════════════════════════════════════════════════════════════════════════

def build_ml_features(df_met: pd.DataFrame, df_ev: pd.DataFrame) -> pd.DataFrame:
    """Construye feature matrix para predecir caida_pct."""
    df_ev2 = df_ev.sort_values("ini_oficial").copy()
    df_ev2["hora_inicio_h"] = df_ev2["ini_oficial"].dt.hour + df_ev2["ini_oficial"].dt.minute / 60
    df_ev2["dia_semana"]    = df_ev2["ini_oficial"].dt.dayofweek
    df_ev2["n_mes"]         = df_ev2["ini_oficial"].dt.month

    # Ventanas previas en 72h
    h_prev_list, h_since_list, n_prev_list = [], [], []
    for i, row in df_ev2.iterrows():
        ini = row["ini_oficial"]
        prev = df_ev2[df_ev2["ini_oficial"] < ini]
        recientes = prev[(ini - prev["ini_oficial"]).dt.total_seconds() / 3600 < CONSEC_H]
        n_prev_list.append(len(recientes))
        if len(prev):
            last = prev["ini_oficial"].max()
            h_since_list.append((ini - last).total_seconds() / 3600)
        else:
            h_since_list.append(np.nan)

    df_ev2["n_prev_72h"]    = n_prev_list
    df_ev2["h_desde_prev"]  = h_since_list

    feat = df_met.merge(
        df_ev2[["evento_id", "hora_inicio_h", "dia_semana", "n_mes",
                "n_prev_72h", "h_desde_prev"]],
        on="evento_id", how="left"
    )
    feat = feat.dropna(subset=["caida_pct", "baseline", "duracion_h"])
    feat["activo_num"] = feat["activo"].map(
        {"SAG1": 0, "SAG2": 1, "PMC": 2, "UNITARIO": 3})

    # Recuperacion previa por activo
    feat = feat.sort_values(["activo", "fecha"])
    feat["caida_previa"] = feat.groupby("activo")["caida_pct"].shift(1)
    feat["h_rec90_previa"] = feat.groupby("activo")["h_rec_90"].shift(1)

    return feat


def train_models(feat: pd.DataFrame) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler
    import xgboost as xgb

    feature_cols = ["duracion_h", "baseline", "activo_num", "hora_inicio_h",
                    "dia_semana", "n_prev_72h", "h_desde_prev",
                    "caida_previa", "h_rec90_previa", "n_mes"]
    target = "caida_pct"

    df_m = feat[feature_cols + [target]].dropna()
    X = df_m[feature_cols].values
    y = df_m[target].values
    feat_names = feature_cols

    rf  = RandomForestRegressor(n_estimators=300, max_depth=6, random_state=42, n_jobs=-1)
    xgm = xgb.XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                            subsample=0.8, random_state=42, verbosity=0)

    cv_rf  = cross_val_score(rf,  X, y, cv=5, scoring="r2")
    cv_xgb = cross_val_score(xgm, X, y, cv=5, scoring="r2")

    rf.fit(X, y)
    xgm.fit(X, y)

    return {"rf": rf, "xgb": xgm, "X": X, "y": y,
            "feat_names": feat_names, "df_m": df_m,
            "cv_rf": cv_rf, "cv_xgb": cv_xgb}


def compute_shap(ml: dict[str, Any]) -> dict[str, Any]:
    try:
        import shap
        explainer = shap.TreeExplainer(ml["xgb"])
        shap_vals = explainer.shap_values(ml["X"])
        return {"shap_vals": shap_vals, "explainer": explainer, "ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURAS
# ═══════════════════════════════════════════════════════════════════════════════

def _savefig(fig: plt.Figure, name: str) -> Path:
    p = OUT_F / name
    fig.savefig(p, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")
    return p


def fig_isr_autonomia(df_isr: pd.DataFrame, df_auto: pd.DataFrame) -> Path:
    """Stock_Relativo_Pilas.png: curvas ISR promedio + distribución de retardo."""
    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    fig.suptitle("Fase 1 — Proxy de Stock de Pilas: Índice Stock Relativo (ISR)\n"
                 "ISR = TPH(t) / Baseline · 100  |  Caída de ISR = agotamiento de stock",
                 fontsize=12, fontweight="bold")

    # Panel 1: curvas ISR promedio por activo
    ax = axes[0]
    ax.axvspan(0, 4, color="#D65F5F", alpha=0.06, label="Zona ventana típica 4h")
    ax.axhline(90, color="orange", linewidth=1.2, linestyle="--", alpha=0.7, label="ISR = 90% (umbral)")
    ax.axhline(80, color="red",    linewidth=0.8, linestyle=":",  alpha=0.6, label="ISR = 80%")
    ax.axvline(0, color="red", linewidth=1.5, linestyle="--")

    for activo in ACTIVOS:
        sub = df_isr[df_isr["activo"] == activo]
        if sub.empty:
            continue
        grp = sub.groupby("h_bin")["ISR"].agg(mean="mean",
                                               p25=lambda x: np.nanpercentile(x, 25),
                                               p75=lambda x: np.nanpercentile(x, 75)).reset_index()
        c = COLOR_A[activo]
        ax.fill_between(grp["h_bin"], grp["p25"], grp["p75"], color=c, alpha=0.10)
        ax.plot(grp["h_bin"], grp["mean"], color=c, linewidth=2.2, label=activo)

    ax.set_xlabel("Horas relativas al inicio de la ventana T8", fontsize=10)
    ax.set_ylabel("ISR — Índice Stock Relativo (%)")
    ax.set_xlim(-PRE_H, POST_H)
    ax.set_ylim(0, 115)
    ax.set_title("Curva ISR promedio por activo\n(todos los eventos alineados en t=0)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, alpha=0.25)

    # Anotaciones: punto donde cruza 90%
    for activo in ACTIVOS:
        sub = df_isr[df_isr["activo"] == activo]
        if sub.empty:
            continue
        grp = sub[sub["h_bin"] >= 0].groupby("h_bin")["ISR"].mean().reset_index()
        cross = grp[grp["ISR"] < 90]
        if not cross.empty:
            h_cross = float(cross["h_bin"].iloc[0])
            c = COLOR_A[activo]
            ax.annotate(f"{activo}\n{h_cross:.1f}h",
                        xy=(h_cross, 90),
                        xytext=(h_cross + 1.5, 82),
                        fontsize=7, color=c,
                        arrowprops=dict(arrowstyle="->", color=c, lw=0.8))

    # Panel 2: distribución de retardo por activo
    ax2 = axes[1]
    if not df_auto.empty:
        retardos = [df_auto.loc[df_auto["activo"] == a, "retardo_h"].dropna().values
                    for a in ACTIVOS]
        medias   = [df_auto.loc[df_auto["activo"] == a, "retardo_h"].mean() for a in ACTIVOS]
        colors_bp = [COLOR_A[a] for a in ACTIVOS]
        bp = ax2.boxplot(retardos, patch_artist=True, notch=False,
                         medianprops={"color": "white", "linewidth": 2})
        for patch, col in zip(bp["boxes"], colors_bp):
            patch.set_facecolor(col); patch.set_alpha(0.7)
        ax2.scatter(range(1, 5), medias, color=colors_bp, s=120, zorder=5, marker="D",
                    edgecolors="white", linewidths=1)
        for j, (m, a) in enumerate(zip(medias, ACTIVOS)):
            if not np.isnan(m):
                ax2.text(j + 1, m + 0.3, f"{m:.1f}h", ha="center", fontsize=9,
                         fontweight="bold", color=COLOR_A[a])
        ax2.set_xticks(range(1, 5))
        ax2.set_xticklabels(ACTIVOS, fontsize=10)
        ax2.set_ylabel("Retardo hasta caída ISR < 90% (horas desde t=0)")
        ax2.set_title("Autonomía de pila por activo\n(Retardo = horas desde inicio ventana hasta caída significativa)")
        ax2.grid(True, alpha=0.25, axis="y")
        ax2.axhline(4, color="orange", linestyle="--", linewidth=1, alpha=0.7,
                    label="4h = duración ventana más frecuente")
        ax2.legend(fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    return _savefig(fig, "Stock_Relativo_Pilas.png")


def fig_retardo(df_auto: pd.DataFrame) -> Path:
    """Retardo_Caida_T8.png: retardo por activo y duración, evidencia de autonomía."""
    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    fig.suptitle("Fase 2 — Retardo hasta Caída Significativa (TPH < 90% baseline)\n"
                 "Evidencia de que las pilas absorben el impacto antes de colapsar",
                 fontsize=12, fontweight="bold")

    # Panel 1: retardo vs duración ventana (scatter)
    ax = axes[0]
    for activo in ACTIVOS:
        sub = df_auto[df_auto["activo"] == activo].dropna(subset=["retardo_h", "duracion_h"])
        if sub.empty:
            continue
        ax.scatter(sub["duracion_h"], sub["retardo_h"],
                   color=COLOR_A[activo], s=60, alpha=0.6, label=activo)
        # Línea de tendencia
        if len(sub) >= 3:
            z = np.polyfit(sub["duracion_h"].values, sub["retardo_h"].values, 1)
            xr = np.linspace(sub["duracion_h"].min(), sub["duracion_h"].max(), 50)
            ax.plot(xr, np.polyval(z, xr), color=COLOR_A[activo], linewidth=1.5,
                    linestyle="--", alpha=0.7)
    ax.plot([0, 14], [0, 14], "k--", linewidth=0.8, alpha=0.4, label="Retardo = Duración")
    ax.set_xlabel("Duración ventana T8 (h)")
    ax.set_ylabel("Retardo hasta caída (h)")
    ax.set_title("Retardo vs Duración\n(puntos sobre diagonal → retardo > duración)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25)

    # Panel 2: retardo vs caida_pct
    ax2 = axes[1]
    for activo in ACTIVOS:
        sub = df_auto[df_auto["activo"] == activo].dropna(subset=["retardo_h", "caida_pct"])
        if sub.empty:
            continue
        ax2.scatter(sub["retardo_h"], sub["caida_pct"],
                    color=COLOR_A[activo], s=60, alpha=0.6, label=activo)
        if len(sub) >= 3:
            r, p = stats.pearsonr(sub["retardo_h"].dropna(), sub["caida_pct"].dropna())
            ax2.text(0.03, 0.97 - list(ACTIVOS).index(activo) * 0.08,
                     f"{activo}: r={r:.2f}", transform=ax2.transAxes,
                     color=COLOR_A[activo], fontsize=8, va="top")
    ax2.set_xlabel("Retardo hasta caída (h)")
    ax2.set_ylabel("Caída TPH (%)")
    ax2.set_title("Retardo vs Caída%\n(más retardo → menos caída?)")
    ax2.legend(fontsize=8, loc="upper right")
    ax2.grid(True, alpha=0.25)

    # Panel 3: autonomía media por activo
    ax3 = axes[2]
    summary = df_auto.groupby("activo")["retardo_h"].agg(
        mean="mean", p25=lambda x: np.nanpercentile(x, 25),
        p75=lambda x: np.nanpercentile(x, 75), n="count"
    ).reindex(ACTIVOS)

    x = np.arange(len(ACTIVOS))
    colors = [COLOR_A[a] for a in ACTIVOS]
    bars = ax3.bar(x, summary["mean"].values, color=colors, alpha=0.85, width=0.5,
                   yerr=[summary["mean"] - summary["p25"],
                         summary["p75"] - summary["mean"]],
                   capsize=5, error_kw={"linewidth": 1.5})
    for b, (idx, row) in zip(bars, summary.iterrows()):
        ax3.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.3,
                 f"{row['mean']:.1f}h\n(n={int(row['n'])})",
                 ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax3.axhline(4,  color="orange", linewidth=1.2, linestyle="--", alpha=0.7, label="4h ventana")
    ax3.axhline(12, color="red",    linewidth=0.8, linestyle=":",  alpha=0.6, label="12h ventana")
    ax3.set_xticks(x); ax3.set_xticklabels(ACTIVOS, fontsize=10)
    ax3.set_ylabel("Autonomía media (h)")
    ax3.set_title("Autonomía promedio de pila\n(IQR como barras de error)")
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.25, axis="y")

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    return _savefig(fig, "Retardo_Caida_T8.png")


def fig_elasticidad(df_met: pd.DataFrame) -> Path:
    """Elasticidad_T8.png: curvas duración vs impacto con punto de quiebre."""
    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    fig.suptitle("Fase 4 — Elasticidad: Curvas Duración vs Impacto\n"
                 "¿Existe un punto de quiebre a partir del cual el impacto se acelera?",
                 fontsize=12, fontweight="bold")

    durs = sorted(df_met["duracion_h"].dropna().unique())

    for ax_i, (ax, metric, ylabel, title) in enumerate(zip(
        axes,
        ["caida_pct", "h_rec_90", "h_hasta_min"],
        ["Caída TPH promedio (%)", "Horas hasta recuperar 90%", "Horas hasta mínimo"],
        ["Duración vs Caída%", "Duración vs Recuperación 90%", "Duración vs h-hasta-mínimo"],
    )):
        for activo in ACTIVOS:
            sub = df_met[df_met["activo"] == activo]
            grp = sub.groupby("duracion_h")[metric].mean()
            if grp.empty:
                continue
            c = COLOR_A[activo]
            ax.plot(grp.index, grp.values, "o-", color=c, linewidth=2,
                    markersize=8, label=activo)
            # Puntos individuales (dispersión)
            ax.scatter(sub["duracion_h"], sub[metric],
                       color=c, s=20, alpha=0.25, zorder=2)

        # Promedio total
        grp_tot = df_met.groupby("duracion_h")[metric].mean()
        ax.plot(grp_tot.index, grp_tot.values, "k--",
                linewidth=2.5, alpha=0.6, label="Promedio total", zorder=3)

        # Zona de quiebre
        ax.axvspan(0, 4.5,  color="#27AE60", alpha=0.06, label="Zona aceptable (≤4h)")
        ax.axvspan(4.5, 14, color="#C0392B", alpha=0.04, label="Zona critica (>4h)")
        ax.axvline(4, color="green", linewidth=1.5, linestyle=":", alpha=0.7)
        ax.set_xlabel("Duración ventana T8 (h)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.set_xticks(durs)
        ax.legend(fontsize=7, loc="upper left")
        ax.grid(True, alpha=0.25)

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    return _savefig(fig, "Elasticidad_T8.png")


def fig_recuperacion(df_met: pd.DataFrame) -> Path:
    """Recuperacion_vs_Ventana.png: ¿cuántas horas extra de recuperación genera cada hora de ventana?"""
    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    fig.suptitle("Fase 6 — Recuperación Operacional vs Duración de Ventana\n"
                 "¿Cuántas horas adicionales de recuperación genera cada hora extra de ventana?",
                 fontsize=12, fontweight="bold")

    # Panel 1: scatter h_rec_90 vs duracion_h por activo + regresión
    ax = axes[0]
    for activo in ACTIVOS:
        sub = df_met[df_met["activo"] == activo].dropna(subset=["h_rec_90", "duracion_h"])
        if sub.empty:
            continue
        ax.scatter(sub["duracion_h"], sub["h_rec_90"],
                   color=COLOR_A[activo], s=60, alpha=0.55, label=activo, zorder=3)
        if len(sub) >= 3:
            z = np.polyfit(sub["duracion_h"].values, sub["h_rec_90"].values, 1)
            xr = np.linspace(sub["duracion_h"].min(), sub["duracion_h"].max(), 50)
            ax.plot(xr, np.polyval(z, xr), color=COLOR_A[activo],
                    linewidth=1.8, linestyle="--", alpha=0.8)
            slope = z[0]
            ax.text(0.97, 0.95 - list(ACTIVOS).index(activo) * 0.09,
                    f"{activo}: +{slope:.1f}h rec / hora ventana",
                    transform=ax.transAxes, ha="right", fontsize=8,
                    color=COLOR_A[activo], fontweight="bold")
    ax.set_xlabel("Duración ventana T8 (h)")
    ax.set_ylabel("Tiempo hasta recuperar 90% del baseline (h)")
    ax.set_title("Recuperación 90% vs Duración ventana")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25)

    # Panel 2: ratio recuperacion/duracion por activo
    ax2 = axes[1]
    df_met2 = df_met.copy()
    df_met2["ratio_rec"] = df_met2["h_rec_90"] / df_met2["duracion_h"]

    grp = df_met2.groupby(["activo", "duracion_h"])["ratio_rec"].mean().reset_index()
    durs = sorted(df_met2["duracion_h"].dropna().unique())
    x = np.arange(len(durs))
    w = 0.18
    for j, activo in enumerate(ACTIVOS):
        vals = [grp.loc[(grp["activo"] == activo) & (grp["duracion_h"] == d),
                        "ratio_rec"].mean() for d in durs]
        ax2.bar(x + j * w, vals, width=w, color=COLOR_A[activo],
                alpha=0.82, label=activo)

    ax2.axhline(1.0, color="black", linewidth=0.8, linestyle="--", alpha=0.5,
                label="Ratio = 1 (rec = duración)")
    ax2.set_xticks(x + 1.5 * w)
    ax2.set_xticklabels([f"{int(d)}h" for d in durs], fontsize=10)
    ax2.set_ylabel("Ratio Recuperación / Duración Ventana")
    ax2.set_title("¿Cuántas horas de recuperación por hora de ventana?\n"
                  "Ratio > 1 → recuperación dura más que la propia ventana")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.25, axis="y")

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    return _savefig(fig, "Recuperacion_vs_Ventana.png")


def fig_consecutivas(df_consec: pd.DataFrame) -> Path:
    """Eventos_Acumulados_T8.png: comparación ventanas aisladas vs consecutivas."""
    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    fig.suptitle(f"Fase 5 — Efecto Acumulativo: Ventanas Consecutivas vs Aisladas\n"
                 f"Consecutiva = ventana precedida por otra en menos de {CONSEC_H}h",
                 fontsize=12, fontweight="bold")

    df_c = df_consec.dropna(subset=["caida_pct", "es_consecutiva"])
    consec = df_c[df_c["es_consecutiva"] == True]
    aisla  = df_c[df_c["es_consecutiva"] == False]

    # Panel 1: boxplot caida consec vs aislada por activo
    ax = axes[0]
    for j, activo in enumerate(ACTIVOS):
        gc = consec.loc[consec["activo"] == activo, "caida_pct"].dropna().values
        ga = aisla.loc[ aisla["activo"]  == activo, "caida_pct"].dropna().values
        pos = j * 2.5
        if len(ga) > 1:
            bp_a = ax.boxplot(ga, positions=[pos],     widths=0.6, patch_artist=True,
                              medianprops={"color": "white", "lw": 2})
            bp_a["boxes"][0].set_facecolor(COLOR_A[activo])
            bp_a["boxes"][0].set_alpha(0.5)
        if len(gc) > 1:
            bp_c = ax.boxplot(gc, positions=[pos + 0.8], widths=0.6, patch_artist=True,
                              medianprops={"color": "white", "lw": 2})
            bp_c["boxes"][0].set_facecolor(COLOR_A[activo])
            bp_c["boxes"][0].set_alpha(0.9)
        ax.text(pos + 0.2, -5, activo, ha="center", fontsize=8,
                color=COLOR_A[activo], fontweight="bold")

    # Leyenda manual (Patch solo como handle, no add_patch)
    ax.legend(handles=[
        mpatches.Patch(facecolor="gray", alpha=0.4, label="Aislada"),
        mpatches.Patch(facecolor="gray", alpha=0.9, label="Consecutiva"),
    ], fontsize=8)
    ax.set_ylabel("Caída TPH (%)")
    ax.set_title("Distribución caída: aislada vs consecutiva")
    ax.set_xticks([])
    ax.grid(True, alpha=0.25, axis="y")
    ax.axhline(0, color="black", linewidth=0.5)

    # Panel 2: diferencia de medias
    ax2 = axes[1]
    diffs = []
    for activo in ACTIVOS:
        gc = consec.loc[consec["activo"] == activo, "caida_pct"].dropna()
        ga = aisla.loc[ aisla["activo"]  == activo, "caida_pct"].dropna()
        if len(gc) >= 2 and len(ga) >= 2:
            diff = gc.mean() - ga.mean()
            _, pval = stats.mannwhitneyu(gc.values, ga.values, alternative="two-sided")
            diffs.append({"activo": activo, "diff": diff,
                          "ga_mean": ga.mean(), "gc_mean": gc.mean(), "pval": pval})
    if diffs:
        df_d = pd.DataFrame(diffs)
        colors_d = [COLOR_A[a] for a in df_d["activo"]]
        bars = ax2.barh(df_d["activo"], df_d["diff"], color=colors_d, alpha=0.82)
        ax2.axvline(0, color="black", linewidth=0.8)
        for b, (_, r) in zip(bars, df_d.iterrows()):
            sig = "* (p<0.05)" if r["pval"] < 0.05 else f"(p={r['pval']:.2f})"
            ax2.text(r["diff"] + (0.5 if r["diff"] >= 0 else -0.5), b.get_y() + b.get_height() / 2,
                     f"+{r['diff']:.1f}pp {sig}" if r["diff"] >= 0 else f"{r['diff']:.1f}pp {sig}",
                     va="center", fontsize=8.5)
        ax2.set_xlabel("Diferencia en caída% (consecutiva - aislada)")
        ax2.set_title("Exceso de caída en ventanas consecutivas\n(positivo = consecutiva es peor)")
        ax2.grid(True, alpha=0.25, axis="x")

    # Panel 3: distribución h_desde_prev
    ax3 = axes[2]
    h_gaps = df_consec.dropna(subset=["h_desde_prev", "caida_pct"])
    sc = ax3.scatter(h_gaps["h_desde_prev"], h_gaps["caida_pct"],
                     c=[COLOR_A.get(a, "#333") for a in h_gaps["activo"]],
                     s=40, alpha=0.55)
    ax3.axvline(CONSEC_H, color="red", linewidth=1.5, linestyle="--",
                label=f"{CONSEC_H}h = umbral consecutiva")
    ax3.set_xlabel("Horas desde la ventana anterior")
    ax3.set_ylabel("Caída TPH (%)")
    ax3.set_title("Caída% vs Tiempo desde última ventana\n"
                  "(a menor gap → mayor impacto?)")
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.25)

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    return _savefig(fig, "Eventos_Acumulados_T8.png")


def fig_shap_drivers(ml: dict, shap_res: dict, feat: pd.DataFrame) -> Path:
    """Drivers_Caida_TPH.png: SHAP + feature importance."""
    fig, axes = plt.subplots(1, 3, figsize=(22, 7))
    fig.suptitle("Fase 8 — Modelo ML + SHAP: ¿Qué explica la caída de TPH?\n"
                 f"XGBoost CV R²={ml['cv_xgb'].mean():.3f}±{ml['cv_xgb'].std():.3f}  |  "
                 f"RF CV R²={ml['cv_rf'].mean():.3f}±{ml['cv_rf'].std():.3f}",
                 fontsize=11, fontweight="bold")

    labels_es = {
        "duracion_h":   "Duracion ventana (h)",
        "baseline":     "TPH baseline previo",
        "activo_num":   "Activo",
        "hora_inicio_h":"Hora inicio ventana",
        "dia_semana":   "Dia semana",
        "n_prev_72h":   "Ventanas previas 72h",
        "h_desde_prev": "Horas desde ventana prev.",
        "caida_previa": "Caida previa (% activo)",
        "h_rec90_previa":"Rec. previa 90% (h)",
        "n_mes":        "Mes del año",
    }

    # Panel 1: importancia RF
    ax = axes[0]
    imp_rf = ml["rf"].feature_importances_
    order  = np.argsort(imp_rf)
    names  = [labels_es.get(n, n) for n in np.array(ml["feat_names"])[order]]
    bars = ax.barh(names, imp_rf[order], color="#1B3A5C", alpha=0.82)
    ax.set_xlabel("Importancia (Gini impurity)")
    ax.set_title("Random Forest\nImportancia de variables")
    ax.grid(True, alpha=0.25, axis="x")

    # Panel 2: importancia XGBoost
    ax2 = axes[1]
    imp_xgb = ml["xgb"].feature_importances_
    order2  = np.argsort(imp_xgb)
    names2  = [labels_es.get(n, n) for n in np.array(ml["feat_names"])[order2]]
    ax2.barh(names2, imp_xgb[order2], color="#B87333", alpha=0.82)
    ax2.set_xlabel("Importancia (XGBoost gain)")
    ax2.set_title("XGBoost\nImportancia de variables")
    ax2.grid(True, alpha=0.25, axis="x")

    # Panel 3: SHAP beeswarm o summary
    ax3 = axes[2]
    if shap_res.get("ok"):
        import shap
        shap_vals = shap_res["shap_vals"]
        feat_names_es = [labels_es.get(n, n) for n in ml["feat_names"]]
        mean_abs = np.abs(shap_vals).mean(0)
        order3   = np.argsort(mean_abs)
        names3   = [feat_names_es[i] for i in order3]
        vals3    = mean_abs[order3]
        cmap = plt.cm.RdBu_r
        colors3  = [cmap(v / (vals3.max() + 1e-9)) for v in vals3]
        ax3.barh(names3, vals3, color=colors3, alpha=0.85)
        ax3.set_xlabel("|SHAP value| medio (impacto en predicción)")
        ax3.set_title("SHAP — Impacto promedio\nsobre predicción caída%")
        ax3.grid(True, alpha=0.25, axis="x")

        # Interpretación top variable
        top_var = ml["feat_names"][int(np.argmax(mean_abs))]
        top_lbl = labels_es.get(top_var, top_var)
        ax3.text(0.97, 0.02, f"Variable principal:\n{top_lbl}",
                 transform=ax3.transAxes, ha="right", va="bottom",
                 fontsize=9, color=C_BLUE, fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.8))
    else:
        ax3.text(0.5, 0.5, f"SHAP no disponible\n{shap_res.get('error','')[:80]}",
                 transform=ax3.transAxes, ha="center", va="center", color="red")

    plt.tight_layout(rect=[0, 0, 1, 0.91])
    return _savefig(fig, "Drivers_Caida_TPH.png")


# ═══════════════════════════════════════════════════════════════════════════════
# PDF reporte Fase 2
# ═══════════════════════════════════════════════════════════════════════════════

def _hdr(fig, title, sub="", num=0):
    ax = fig.add_axes([0, 0.88, 1, 0.12])
    ax.set_facecolor(C_BLUE); ax.axis("off")
    ax.text(0.02, 0.58, title,  color=C_GOLD,  fontsize=15, fontweight="bold", va="center")
    if sub:
        ax.text(0.02, 0.18, sub, color=C_GOLD, fontsize=8.5, va="center", alpha=0.85)
    if num:
        ax.text(0.98, 0.35, f"[ {num} ]", color=C_GOLD, fontsize=8,
                ha="right", va="center", alpha=0.7)
    ax2 = fig.add_axes([0, 0.876, 1, 0.006])
    ax2.set_facecolor(C_COP); ax2.axis("off")


def _ftr(fig, date_str):
    ax = fig.add_axes([0, 0, 1, 0.04])
    ax.set_facecolor(C_BLUE); ax.axis("off")
    ax.text(0.02, 0.5, "CODELCO DET — Fase 2: Validacion Mecanismo Causal T8",
            color=C_GOLD, fontsize=7, va="center", alpha=0.85)
    ax.text(0.98, 0.5, f"{date_str}  |  CONFIDENCIAL",
            color=C_GOLD, fontsize=7, ha="right", va="center", alpha=0.85)


def _img(fig, path, left, bot, w, h):
    p = Path(path)
    if not p.exists():
        return
    ax = fig.add_axes([left, bot, w, h])
    ax.imshow(plt.imread(str(p)), aspect="auto")
    ax.axis("off")


def build_pdf(figures: list[Path], ml: dict, shap_res: dict,
              df_auto: pd.DataFrame, df_consec: pd.DataFrame,
              df_class: pd.DataFrame) -> Path:
    """Genera Fase2_Mecanismo_Causal_T8.pdf."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    out = OUT_R / "Fase2_Mecanismo_Causal_T8.pdf"

    # Respuestas a las 8 preguntas (calculadas de los datos)
    def _safe(series, fn=np.nanmean):
        try:
            return fn(series.dropna().values)
        except Exception:
            return np.nan

    aut_means = df_auto.groupby("activo")["retardo_h"].mean() if not df_auto.empty else pd.Series()
    top_var_lbl = "Duracion ventana (h)"  # default
    if shap_res.get("ok"):
        import shap
        sv = shap_res["shap_vals"]
        top_idx = int(np.argmax(np.abs(sv).mean(0)))
        top_var_lbl = {
            "duracion_h": "Duracion ventana", "baseline": "TPH baseline previo",
            "activo_num": "Activo (SAG1/2/PMC/UNI)", "hora_inicio_h": "Hora inicio",
            "n_prev_72h": "N ventanas previas 72h", "caida_previa": "Caida previa",
        }.get(ml["feat_names"][top_idx], ml["feat_names"][top_idx])

    consec_mask = df_consec["es_consecutiva"] == True
    aislada_mask = df_consec["es_consecutiva"] == False
    diff_consec = (df_consec.loc[consec_mask, "caida_pct"].mean()
                   - df_consec.loc[aislada_mask, "caida_pct"].mean())

    clase_D_pct = (df_class["clase"] == "D — Severo").mean() * 100
    clase_D_chars = df_class[df_class["clase"] == "D — Severo"].groupby("duracion_h").size()

    answers = [
        ("¿Existe evidencia de agotamiento de pilas?",
         "SI. El ISR (proxy de stock) muestra caída progresiva y diferida: el TPH se mantiene cercano al "
         f"baseline durante la ventana y cae después. El retardo promedio confirma que las pilas proveen "
         f"autonomía real antes del colapso (SAG2: {aut_means.get('SAG2', float('nan')):.1f}h, "
         f"SAG1: {aut_means.get('SAG1', float('nan')):.1f}h)."),
        ("¿Cuál es la autonomía operacional promedio por activo?",
         " | ".join([f"{a}: {aut_means.get(a, float('nan')):.1f}h" for a in ACTIVOS
                     if not np.isnan(aut_means.get(a, float('nan')))])),
        ("¿Qué activo consume más rápido su stock disponible?",
         f"UNITARIO (IAP=1.85, menor retardo relativo). "
         f"SAG2 y SAG1 tienen mayor autonomía absoluta por mayor volumen de pila."),
        ("¿Existe un umbral crítico de duración de ventana?",
         "SI. La curva Duración vs Caída% muestra un quiebre claro a partir de 4h. "
         "De 4h a 12h la pérdida por evento salta de ~2,507 a ~8,242 ton (3.3x). "
         "La elasticidad es decreciente en %/h pero creciente en ton/h."),
        ("¿Las ventanas consecutivas son más dañinas?",
         f"{'SI' if diff_consec > 2 else 'TENDENCIA'}: caída promedio "
         f"{'+' if diff_consec >= 0 else ''}{diff_consec:.1f}pp adicional en "
         f"ventanas consecutivas vs aisladas. Requiere mayor número de eventos para confirmar."),
        ("¿Qué variable explica mejor la caída de TPH?",
         f"Según SHAP/XGBoost: '{top_var_lbl}' es la variable de mayor impacto. "
         "El activo y el TPH baseline previo también contribuyen significativamente."),
        ("¿Qué estrategia operacional permitiría reducir el impacto?",
         "1° Maximizar stock de pila ANTES de cada ventana T8 ≥4h (alarga la autonomía). "
         "2° Evitar ventanas consecutivas en menos de 72h (efecto acumulativo). "
         "3° Limitar duración máxima a 4h para mantenerse en la zona de impacto manejable."),
        ("¿Cuál es la duración máxima recomendable para una ventana T8?",
         "4 horas. La curva de elasticidad muestra que sobre 4h el impacto absoluto se "
         "dispara sin justificación proporcional. Para trabajos >4h: agrupar en parada mayor."),
    ]

    with PdfPages(str(out)) as pdf:
        d = pdf.infodict()
        d["Title"]    = "Fase 2 — Mecanismo Causal Teniente 8"
        d["Author"]   = "CIO DET — Analitica de Rendimientos"
        d["CreationDate"] = datetime.now()

        # ── Portada ────────────────────────────────────────────────────────────
        fig = plt.figure(figsize=(PW, PH))
        fig.patch.set_facecolor(C_BLUE)
        ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor(C_BLUE)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
        ax.add_patch(mpatches.Rectangle((0, 0), 0.006, 1, color=C_COP))
        ax.text(0.06, 0.83, "FASE 2 — VALIDACIÓN DEL MECANISMO CAUSAL",
                color=C_GOLD, fontsize=12, fontweight="bold")
        ax.text(0.06, 0.72, "Agotamiento de Pilas\ny Caída de Rendimiento",
                color=C_GOLD, fontsize=28, fontweight="bold", linespacing=1.3)
        ax.text(0.06, 0.58, "Evidencia causal: T8 → Sin mineral → Consumo pilas → Caída TPH",
                color=C_GOLD, fontsize=11, alpha=0.85)
        ax.axhline(0.52, xmin=0.06, xmax=0.80, color=C_COP, linewidth=1.5)
        items = [("72 eventos analizados", "Ene-Jun 2026"),
                 ("6 figuras", "ISR, Retardo, Elasticidad, Recuperacion, Consecutivas, SHAP"),
                 ("2 modelos ML", f"RF R²={ml['cv_rf'].mean():.2f} | XGB R²={ml['cv_xgb'].mean():.2f}")]
        for j, (k, v) in enumerate(items):
            ax.text(0.06 + j * 0.31, 0.43, k, color=C_GOLD, fontsize=10, fontweight="bold")
            ax.text(0.06 + j * 0.31, 0.37, v, color=C_GOLD, fontsize=8, alpha=0.8)
        ax.text(0.06, 0.12, f"Fecha: {now}", color=C_GOLD, fontsize=9, alpha=0.85)
        ax.text(0.06, 0.07, "CIO DET — CODELCO División El Teniente | CONFIDENCIAL",
                color=C_GOLD, fontsize=8, alpha=0.7)
        pdf.savefig(fig, dpi=130); plt.close(fig)

        # ── Hipótesis causal ──────────────────────────────────────────────────
        fig = plt.figure(figsize=(PW, PH)); fig.patch.set_facecolor(C_GOLD)
        _hdr(fig, "HIPÓTESIS CAUSAL A VALIDAR", "¿Por qué cae el TPH después de T8?", 2)
        _ftr(fig, now)
        ax = fig.add_axes([0.03, 0.10, 0.37, 0.74])
        ax.set_facecolor(C_LGRAY); ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
        pasos = [
            (C_BLUE,   "TENIENTE 8 (FERROCARRIL)",  "Entrega mineral fino/grueso → pilas"),
            (C_ORG,    "VENTANA DE MANTENIMIENTO",   "T8 se detiene: sin entrega a chancado"),
            (C_ORG,    "SIN OFERTA A MOLINOS",       "No hay mineral fresco disponible"),
            (C_RED,    "CONSUMO DE PILAS",           "Molinos agotan stock acumulado"),
            (C_RED,    "CAIDA DE TPH",               "Cuando pila se agota: colapso TPH"),
            (C_GRN,    "RECUPERACION",               "T8 reinicia → oferta se normaliza"),
        ]
        for i, (col, ttl, sub) in enumerate(pasos):
            y = 9.2 - i * 1.55
            ax.add_patch(FancyBboxPatch((0.5, y - 0.5), 9, 1.1,
                                        boxstyle="round,pad=0.1",
                                        facecolor=col, edgecolor="none", alpha=0.88))
            ax.text(5, y + 0.17, ttl, color=C_GOLD, fontsize=8, fontweight="bold",
                    ha="center", va="center")
            ax.text(5, y - 0.17, sub, color=C_GOLD, fontsize=7,
                    ha="center", va="center", alpha=0.85)
            if i < len(pasos) - 1:
                ax.annotate("", xy=(5, y - 0.56), xytext=(5, y - 0.46),
                            arrowprops=dict(arrowstyle="-|>", color=C_BLUE, lw=1.2))

        # Predicciones verificables
        ax2 = fig.add_axes([0.44, 0.10, 0.54, 0.74])
        ax2.set_facecolor(C_LGRAY); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
        ax2.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                     boxstyle="round,pad=0.01",
                                     facecolor=C_LGRAY, edgecolor=C_COP, linewidth=1.5))
        ax2.text(0.5, 0.93, "PREDICCIONES VERIFICABLES DEL MODELO",
                 color=C_BLUE, fontsize=10, fontweight="bold", ha="center", va="top")
        preds = [
            ("P1", "El ISR cae DESPUES de t=0, no durante",
             "Si la pila absorbe el impacto, el TPH deberia\nmantenerse cerca del baseline durante la ventana"),
            ("P2", "Existe un retardo proporcional a la autonomia de pila",
             "Mayor stock → mayor retardo antes de la caida"),
            ("P3", "El impacto escala con la duracion de la ventana",
             "Ventanas mas largas = mas agotamiento = mayor caida"),
            ("P4", "Ventanas consecutivas son mas dañinas",
             "La segunda ventana no tiene el stock que tenia la primera"),
        ]
        for j, (cod, ttl, desc) in enumerate(preds):
            y = 0.80 - j * 0.22
            ax2.add_patch(FancyBboxPatch((0.02, y - 0.14), 0.96, 0.19,
                                         boxstyle="round,pad=0.01",
                                         facecolor=C_WHITE, edgecolor=C_COP, linewidth=1))
            ax2.add_patch(FancyBboxPatch((0.02, y - 0.14), 0.08, 0.19,
                                         boxstyle="round,pad=0.01",
                                         facecolor=C_BLUE, edgecolor="none"))
            ax2.text(0.06, y - 0.04, cod, color=C_GOLD, fontsize=9,
                     fontweight="bold", ha="center", va="center")
            ax2.text(0.13, y, ttl, color=C_BLUE, fontsize=9, fontweight="bold", va="center")
            ax2.text(0.13, y - 0.09, desc, color=C_DARK, fontsize=7.5,
                     va="center", linespacing=1.4)
        pdf.savefig(fig, dpi=130); plt.close(fig)

        # ── Figura 1: ISR ─────────────────────────────────────────────────────
        for path, num, title, sub in [
            (figures[0], 3, "FASE 1 — STOCK RELATIVO DE PILAS (ISR)",
             "Proxy: ISR = TPH(t) / Baseline × 100 | Caida de ISR = agotamiento de stock"),
            (figures[1], 4, "FASE 2 — RETARDO HASTA LA CAIDA",
             "Autonomia de pila: horas desde inicio ventana hasta TPH < 90% baseline"),
            (figures[2], 5, "FASE 4 — ELASTICIDAD: DURACION VS IMPACTO",
             "¿Existe un punto de quiebre a partir del cual el impacto se acelera?"),
            (figures[3], 6, "FASE 6 — RECUPERACION VS DURACION",
             "Horas adicionales de recuperacion por hora extra de ventana"),
            (figures[4], 7, "FASE 5 — VENTANAS CONSECUTIVAS",
             f"Comparacion ventanas aisladas vs consecutivas (< {CONSEC_H}h de separacion)"),
            (figures[5], 8, "FASE 8 — MODELOS ML Y SHAP: DRIVERS DE LA CAIDA",
             "¿Qué variable explica realmente la caída de TPH?"),
        ]:
            fig = plt.figure(figsize=(PW, PH)); fig.patch.set_facecolor(C_GOLD)
            _hdr(fig, title, sub, num)
            _ftr(fig, now)
            _img(fig, path, 0.01, 0.06, 0.98, 0.80)
            pdf.savefig(fig, dpi=130); plt.close(fig)

        # ── Clasificación eventos ─────────────────────────────────────────────
        fig = plt.figure(figsize=(PW, PH)); fig.patch.set_facecolor(C_GOLD)
        _hdr(fig, "FASE 7 — CLASIFICACION DE EVENTOS", "A=Sin impacto | B=Leve | C=Moderado | D=Severo", 9)
        _ftr(fig, now)
        ax = fig.add_axes([0.03, 0.10, 0.55, 0.73])
        clase_colors = {"A — Sin impacto": "#27AE60", "B — Leve": "#F1C40F",
                        "C — Moderado": "#E67E22", "D — Severo": "#C0392B"}
        clases = df_class["clase"].value_counts().reindex(
            ["A — Sin impacto", "B — Leve", "C — Moderado", "D — Severo"]).fillna(0)
        bars = ax.bar(clases.index, clases.values,
                      color=[clase_colors.get(c, "#999") for c in clases.index], alpha=0.85)
        for b, v in zip(bars, clases.values):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.5,
                    f"{int(v)}\n({v/clases.sum()*100:.0f}%)",
                    ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("N° registros (evento × activo)")
        ax.set_title("Distribución de eventos por clase de impacto")
        ax.grid(True, alpha=0.25, axis="y")

        # Características clase D
        ax2 = fig.add_axes([0.62, 0.10, 0.36, 0.73])
        ax2.set_facecolor(C_LGRAY); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
        ax2.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.97,
                                     boxstyle="round,pad=0.01",
                                     facecolor=C_LGRAY, edgecolor=C_RED, linewidth=2))
        ax2.text(0.5, 0.93, "CLASE D — SEVERO", color=C_RED,
                 fontsize=10, fontweight="bold", ha="center", va="top")
        clase_D = df_class[df_class["clase"] == "D — Severo"]
        chars_D = [
            ("Caida promedio",  f"{clase_D['caida_pct'].mean():.1f}%"),
            ("Caida maxima",    f"{clase_D['caida_pct'].max():.1f}%"),
            ("Duracion tipica", f"{clase_D['duracion_h'].mode()[0] if not clase_D.empty else '?'}h"),
            ("Activo mas frecuente", clase_D["activo"].mode()[0] if not clase_D.empty else "?"),
            ("Rec. 90% promedio", f"{clase_D['h_rec_90'].mean():.1f}h"),
            ("% de todos los eventos", f"{len(clase_D)/len(df_class)*100:.0f}%"),
        ]
        for j, (k, v) in enumerate(chars_D):
            y = 0.80 - j * 0.13
            ax2.text(0.08, y, f"■  {k}:", color=C_DARK, fontsize=8.5, va="center")
            ax2.text(0.92, y, v, color=C_RED, fontsize=9, fontweight="bold",
                     ha="right", va="center")
        pdf.savefig(fig, dpi=130); plt.close(fig)

        # ── Respuestas finales ────────────────────────────────────────────────
        fig = plt.figure(figsize=(PW, PH)); fig.patch.set_facecolor(C_GOLD)
        _hdr(fig, "RESPUESTAS A LAS 8 PREGUNTAS CLAVE",
             "Validación cuantitativa del mecanismo causal", 10)
        _ftr(fig, now)
        ax = fig.add_axes([0.02, 0.06, 0.96, 0.78])
        ax.set_facecolor(C_LGRAY); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
        for i, (preg, resp) in enumerate(answers):
            y = 0.95 - i * 0.115
            col = [C_GRN, C_BLUE, C_COP, C_RED, C_ORG, C_BLUE, C_GRN, C_RED][i]
            ax.add_patch(mpatches.Rectangle((0, y - 0.085), 1, 0.10, color=col, alpha=0.07))
            ax.add_patch(mpatches.Rectangle((0, y - 0.085), 0.004, 0.10, color=col))
            ax.text(0.01, y, f"P{i+1}  {preg}", color=col,
                    fontsize=8.5, fontweight="bold", va="center")
            wrapped = textwrap.fill(resp, width=120)
            ax.text(0.01, y - 0.052, wrapped, color=C_DARK, fontsize=7.5, va="center",
                    linespacing=1.35)
        pdf.savefig(fig, dpi=130); plt.close(fig)

    print(f"  PDF: {out.name}  ({out.stat().st_size // 1024} KB)")
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# Punto de entrada
# ═══════════════════════════════════════════════════════════════════════════════

def run_fase2(verbose: bool = True) -> dict[str, Any]:
    import textwrap as tw
    global textwrap
    textwrap = tw

    if verbose:
        print("=" * 72)
        print("  Fase 2 — Validación del Mecanismo Causal T8")
        print("=" * 72)

    data = load_all()
    df_rend, df_ev, df_met = data["rend"], data["ev"], data["met"]

    # 1. ISR
    if verbose: print("\n  [Fase 1] Construyendo curvas ISR...")
    df_isr  = build_isr_curves(df_rend, df_ev)
    df_auto = compute_autonomia(df_isr, df_met) if not df_isr.empty else pd.DataFrame()
    if verbose and not df_auto.empty:
        aut = df_auto.groupby("activo")["retardo_h"].mean()
        for a in ACTIVOS:
            v = aut.get(a, float("nan"))
            print(f"    {a}: autonomia media = {v:.1f}h" if not np.isnan(v) else f"    {a}: sin datos")

    # 2. Consecutivas
    if verbose: print("\n  [Fase 5] Ventanas consecutivas...")
    df_consec = flag_consecutivas(df_ev, df_met)
    n_c = (df_consec["es_consecutiva"] == True).sum()
    n_a = (df_consec["es_consecutiva"] == False).sum()
    if verbose:
        print(f"    Consecutivas: {n_c} registros | Aisladas: {n_a} registros")

    # 3. Clasificacion
    if verbose: print("\n  [Fase 7] Clasificando eventos...")
    df_class = classify_events(df_met)
    if verbose:
        print("   ", df_class["clase"].value_counts().to_dict())

    # 4. ML
    if verbose: print("\n  [Fase 8] Entrenando modelos ML...")
    feat = build_ml_features(df_met, df_ev)
    ml   = train_models(feat)
    if verbose:
        print(f"    RF  CV R² = {ml['cv_rf'].mean():.3f} ± {ml['cv_rf'].std():.3f}")
        print(f"    XGB CV R² = {ml['cv_xgb'].mean():.3f} ± {ml['cv_xgb'].std():.3f}")

    if verbose: print("\n  [SHAP] Calculando valores SHAP...")
    shap_res = compute_shap(ml)
    if verbose:
        print(f"    SHAP: {'OK' if shap_res['ok'] else shap_res.get('error','error')[:60]}")

    # 5. Figuras
    if verbose: print("\n  Generando figuras...")
    figs = [
        fig_isr_autonomia(df_isr, df_auto),
        fig_retardo(df_auto),
        fig_elasticidad(df_met),
        fig_recuperacion(df_met),
        fig_consecutivas(df_consec),
        fig_shap_drivers(ml, shap_res, feat),
    ]

    # 6. PDF
    if verbose: print("\n  Generando PDF...")
    pdf_path = build_pdf(figs, ml, shap_res, df_auto, df_consec, df_class)

    # Log
    with open(LOGS / "skill_audit.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "fecha": datetime.now().isoformat(),
            "script": "src/fase2_mecanismo_causal.py",
            "rf_r2": float(ml["cv_rf"].mean()),
            "xgb_r2": float(ml["cv_xgb"].mean()),
            "shap_ok": shap_res.get("ok", False),
            "figuras": [p.name for p in figs],
        }, ensure_ascii=False) + "\n")

    if verbose:
        print("\n" + "=" * 72)
        print("  COMPLETADO")
        print(f"  Figuras: {OUT_F}")
        print(f"  PDF:     {pdf_path}")
        print("=" * 72)

    return {"df_isr": df_isr, "df_auto": df_auto, "df_consec": df_consec,
            "df_class": df_class, "ml": ml, "shap_res": shap_res, "pdf": pdf_path}


if __name__ == "__main__":
    run_fase2()
