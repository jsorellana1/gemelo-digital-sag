"""
event_study_t8.py — Event Study Industrial: impacto de ventanas Teniente 8.

Metodologia:
    Cada ventana T8 es un evento. Se alinean todos los eventos en t=0
    (hora oficial de inicio) y se computa la respuesta promedio de TPH.

Hora 0 = inicio oficial de la ventana (regla operacional, no inferida):
    2h  -> 14:00
    4h  -> 12:00
    8h  -> 08:00
    12h -> 08:00

Uso standalone:
    python src/event_study_t8.py

Uso desde notebook:
    from event_study_t8 import run_event_study
    results = run_event_study(df_rend=df_rend)
"""
from __future__ import annotations

import json
import logging
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from scipy import stats

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False

warnings.filterwarnings("ignore")
logging.getLogger("matplotlib").setLevel(logging.WARNING)

# ── Rutas ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_INT = BASE_DIR / "data" / "intermediate"
OUT_FIG  = BASE_DIR / "outputs" / "figures" / "event_study"
OUT_XLS  = BASE_DIR / "outputs" / "excel"
OUT_RPT  = BASE_DIR / "outputs" / "reports"
LOGS_DIR = BASE_DIR / "logs"

for _p in (OUT_FIG, OUT_XLS, OUT_RPT, LOGS_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ── Parámetros ─────────────────────────────────────────────────────────────────
PRE_H   = 24     # horas antes de t=0 para la ventana de análisis
POST_H  = 24     # horas después de t=0
BIN_MIN = 30     # resolución de la curva de respuesta (minutos)
MIN_PTS_BASELINE = 20   # mínimo de puntos 5-min en pre para un evento válido
TPH_OP  = 50     # umbral operacional: TPH <= esto no es producción real
ALPHA   = 0.05   # nivel de significancia estadística

# Horarios oficiales por duración — NO modificar
T8_TIMES: dict[int, tuple[int, int]] = {
    2:  (14, 16),
    4:  (12, 16),
    8:  ( 8, 16),
    12: ( 8, 20),
}
DURATIONS = [2, 4, 8, 12]

# Colores por activo y duración
if _YAML_OK:
    try:
        _cfg = yaml.safe_load((BASE_DIR / "config" / "config.yaml").read_text(encoding="utf-8"))
        ACTIVOS = _cfg.get("activos", ["SAG1", "SAG2", "PMC", "UNITARIO"])
        COLOR_ACTIVO: dict[str, str] = _cfg.get("colores", {
            "SAG1": "#1f77b4", "SAG2": "#ff7f0e", "PMC": "#2ca02c", "UNITARIO": "#d62728"
        })
    except Exception:
        ACTIVOS = ["SAG1", "SAG2", "PMC", "UNITARIO"]
        COLOR_ACTIVO = {"SAG1": "#1f77b4", "SAG2": "#ff7f0e", "PMC": "#2ca02c", "UNITARIO": "#d62728"}
else:
    ACTIVOS = ["SAG1", "SAG2", "PMC", "UNITARIO"]
    COLOR_ACTIVO = {"SAG1": "#1f77b4", "SAG2": "#ff7f0e", "PMC": "#2ca02c", "UNITARIO": "#d62728"}

COLOR_DUR: dict[int, str] = {2: "#4878D0", 4: "#EE854A", 8: "#6ACC65", 12: "#D65F5F"}
MARKER_DUR: dict[int, str] = {2: "o", 4: "s", 8: "^", 12: "D"}


# ═══════════════════════════════════════════════════════════════════════════════
# Paso 1 — Carga y construcción del dataset de eventos
# ═══════════════════════════════════════════════════════════════════════════════

def _load_rend(df_rend: pd.DataFrame | None = None) -> pd.DataFrame:
    if df_rend is not None:
        df = df_rend.copy()
        df["fecha"] = pd.to_datetime(df["fecha"])
        # Normalizar MUN → UNITARIO
        for col in list(df.columns):
            if col.startswith("MUN_"):
                df.rename(columns={col: col.replace("MUN_", "UNITARIO_")}, inplace=True)
        return df.sort_values("fecha").reset_index(drop=True)
    rend_path = DATA_INT / "rendimientos_clean.parquet"
    if not rend_path.exists():
        raise FileNotFoundError(f"No se encontró rendimientos en {rend_path}")
    df = pd.read_parquet(rend_path)
    df["fecha"] = pd.to_datetime(df["fecha"])
    for col in list(df.columns):
        if col.startswith("MUN_"):
            df.rename(columns={col: col.replace("MUN_", "UNITARIO_")}, inplace=True)
    return df.sort_values("fecha").reset_index(drop=True)


def _load_t8_events(pam_mantto_dir: Path | None = None) -> pd.DataFrame:
    """
    Carga eventos T8 desde PAM Mantto o desde ventanas_t8.parquet como fallback.
    Retorna DataFrame con columnas: fecha, duracion_h, ini_oficial, fin_oficial.
    """
    # Intentar desde efecto_gaviota si está disponible
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR / "src"))
        from efecto_gaviota import (
            build_t8_event_table_from_pam, build_event_records,
            duration_group
        )
        _, event_table, diag = build_t8_event_table_from_pam(pam_mantto_dir)
        if not event_table.empty:
            events = build_event_records(event_table)
            rows = [{
                "fecha":       ev["fecha"].date(),
                "duracion_h":  int(round(ev["horas_t8"])),
                "ini_oficial": ev["ini"],
                "fin_oficial": ev["fin"],
            } for ev in events]
            df = pd.DataFrame(rows)
            df["evento_id"] = [f"EV{str(i+1).zfill(3)}" for i in range(len(df))]
            return df
    except Exception:
        pass

    # Fallback: ventanas_t8.parquet
    parquet_path = DATA_INT / "ventanas_t8.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError("No se encontraron eventos T8 (PAM ni parquet).")

    df_v = pd.read_parquet(parquet_path)
    df_v["fecha"] = pd.to_datetime(df_v["fecha"]).dt.normalize()
    df_v = df_v[df_v["horas_t8"] > 0].sort_values("fecha").reset_index(drop=True)

    rows = []
    for _, row in df_v.iterrows():
        fecha = row["fecha"]
        dur   = int(min(DURATIONS, key=lambda d: abs(d - float(row["horas_t8"]))))
        h_ini, h_fin = T8_TIMES.get(dur, (8, 8 + dur))
        ini = fecha + pd.Timedelta(hours=h_ini)
        fin = fecha + pd.Timedelta(hours=h_fin)
        rows.append({"fecha": fecha.date(), "duracion_h": dur,
                     "ini_oficial": ini, "fin_oficial": fin})

    df = pd.DataFrame(rows)
    df["evento_id"] = [f"EV{str(i+1).zfill(3)}" for i in range(len(df))]
    return df


def save_eventos_parquet(df_eventos: pd.DataFrame) -> Path:
    path = DATA_INT / "eventos_t8.parquet"
    df_eventos.to_parquet(path, index=False)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# Paso 2-3 — Construcción del Event Dataset con tiempo relativo
# ═══════════════════════════════════════════════════════════════════════════════

def build_event_dataset(
    df_eventos: pd.DataFrame,
    df_rend:    pd.DataFrame,
    pre_h:  int = PRE_H,
    post_h: int = POST_H,
) -> pd.DataFrame:
    """
    Para cada evento cruza con rendimientos 5-min y agrega:
        horas_relativas = (timestamp - ini_oficial) / 3600s
        periodo = PRE | VENTANA | POST
    """
    chunks: list[pd.DataFrame] = []

    for _, ev in df_eventos.iterrows():
        ini  = ev["ini_oficial"]
        fin  = ev["fin_oficial"]
        dur  = ev["duracion_h"]
        t0   = ini - pd.Timedelta(hours=pre_h)
        t1   = ini + pd.Timedelta(hours=post_h)

        mask = (df_rend["fecha"] >= t0) & (df_rend["fecha"] <= t1)
        df_w = df_rend.loc[mask].copy()
        if df_w.empty:
            continue

        df_w["evento_id"]      = ev["evento_id"]
        df_w["fecha_evento"]   = ev["fecha"]
        df_w["duracion_h"]     = dur
        df_w["ini_oficial"]    = ini
        df_w["fin_oficial"]    = fin
        df_w["horas_relativas"] = (df_w["fecha"] - ini).dt.total_seconds() / 3600
        df_w["periodo"] = "POST"
        df_w.loc[df_w["horas_relativas"] < 0,  "periodo"] = "PRE"
        df_w.loc[(df_w["horas_relativas"] >= 0) &
                 (df_w["fecha"] < fin), "periodo"] = "VENTANA"

        chunks.append(df_w)

    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Paso 4 — Curvas de respuesta promedio
# ═══════════════════════════════════════════════════════════════════════════════

def _bin_h(t: float, bin_min: int = BIN_MIN) -> float:
    """Redondea horas al bin más cercano (e.g. BIN_MIN=30 → 0.5h)."""
    step = bin_min / 60
    return round(t / step) * step


def build_response_curves(
    df_ev_ds: pd.DataFrame,
    activos:  list[str] = ACTIVOS,
    bin_min:  int = BIN_MIN,
) -> pd.DataFrame:
    """
    Agrega TPH por (activo, horas_relativas_bin) sobre todos los eventos válidos.
    Retorna DataFrame con columnas: activo, h_rel, tph_mean, tph_std, tph_p25, tph_p75, n.
    """
    rows: list[dict] = []
    df_ev_ds = df_ev_ds.copy()
    df_ev_ds["h_rel_bin"] = df_ev_ds["horas_relativas"].apply(lambda t: _bin_h(t, bin_min))

    for activo in activos:
        col_tph = f"{activo}_tph"
        col_op  = f"{activo}_operando"
        if col_tph not in df_ev_ds.columns:
            continue
        # Solo puntos operacionales con TPH real
        mask_op = df_ev_ds[col_op] & (df_ev_ds[col_tph] > TPH_OP)
        df_a = df_ev_ds.loc[mask_op, ["evento_id", "h_rel_bin", col_tph]].copy()

        grp = df_a.groupby("h_rel_bin")[col_tph].agg(
            tph_mean="mean",
            tph_std="std",
            tph_p25=lambda x: np.nanpercentile(x, 25),
            tph_p75=lambda x: np.nanpercentile(x, 75),
            n="count",
        ).reset_index()
        grp.columns = ["h_rel", "tph_mean", "tph_std", "tph_p25", "tph_p75", "n"]
        grp["activo"] = activo
        rows.append(grp)

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(["activo", "h_rel"]).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Paso 7 — Métricas por evento
# ═══════════════════════════════════════════════════════════════════════════════

def compute_event_metrics(
    df_ev_ds:  pd.DataFrame,
    df_eventos: pd.DataFrame,
    activos:   list[str] = ACTIVOS,
) -> pd.DataFrame:
    """
    Calcula por (evento_id, activo):
        baseline, tph_min, caida_abs, caida_pct,
        tiempo_hasta_minimo_h,
        tiempo_rec_80/90/95/100
    """
    rows: list[dict] = []

    for _, ev in df_eventos.iterrows():
        ev_id = ev["evento_id"]
        ini   = ev["ini_oficial"]
        dur_h = ev["duracion_h"]
        df_e  = df_ev_ds[df_ev_ds["evento_id"] == ev_id]
        if df_e.empty:
            continue

        for activo in activos:
            col = f"{activo}_tph"
            opc = f"{activo}_operando"
            if col not in df_e.columns:
                continue

            pre_mask = (df_e["periodo"] == "PRE") & df_e[opc] & (df_e[col] > TPH_OP)
            pre_vals = df_e.loc[pre_mask, col]
            if len(pre_vals) < MIN_PTS_BASELINE:
                continue
            baseline = float(pre_vals.mean())
            if baseline < TPH_OP:
                continue

            post_mask = df_e["periodo"].isin(["VENTANA", "POST"]) & df_e[opc] & (df_e[col] > 0)
            post_s = df_e.loc[post_mask, [col, "horas_relativas"]].copy()
            post_s["roll"] = post_s[col].rolling(6, min_periods=3).mean()

            if post_s.empty:
                continue

            tph_min = float(post_s["roll"].min()) if not post_s["roll"].isna().all() else float(post_s[col].min())
            h_min   = float(post_s.loc[post_s["roll"].idxmin() if not post_s["roll"].isna().all()
                                        else post_s[col].idxmin(), "horas_relativas"])

            caida_abs = baseline - tph_min
            caida_pct = caida_abs / baseline * 100 if baseline > 0 else np.nan

            def _rec_h(pct: float) -> float:
                thr = baseline * pct
                after_min = post_s.loc[post_s["horas_relativas"] >= h_min].copy()
                after_min["rec_roll"] = after_min[col].rolling(6, min_periods=3).mean()
                ok = after_min.loc[after_min["rec_roll"] >= thr, "horas_relativas"]
                return float(ok.iloc[0]) if len(ok) > 0 else np.nan

            rows.append({
                "evento_id":    ev_id,
                "fecha":        ev["fecha"],
                "duracion_h":   dur_h,
                "activo":       activo,
                "baseline":     round(baseline, 1),
                "tph_min":      round(tph_min,  1),
                "caida_abs":    round(caida_abs, 1),
                "caida_pct":    round(caida_pct, 2) if not np.isnan(caida_pct) else np.nan,
                "h_hasta_min":  round(h_min,     2),
                "h_rec_80":     round(_rec_h(0.80), 2),
                "h_rec_90":     round(_rec_h(0.90), 2),
                "h_rec_95":     round(_rec_h(0.95), 2),
                "h_rec_100":    round(_rec_h(1.00), 2),
                "ist8": round(caida_pct / dur_h, 3) if (not np.isnan(caida_pct) and dur_h > 0) else np.nan,
                # Toneladas
                "ton_pre":      round(df_e.loc[df_e["periodo"]=="PRE",    f"{activo}_ton"].sum(), 0),
                "ton_ventana":  round(df_e.loc[df_e["periodo"]=="VENTANA", f"{activo}_ton"].sum(), 0),
                "ton_post":     round(df_e.loc[df_e["periodo"]=="POST",   f"{activo}_ton"].sum(), 0),
            })

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# Paso 9 — Significancia estadística
# ═══════════════════════════════════════════════════════════════════════════════

def compute_statistics(df_ev_ds: pd.DataFrame, activos: list[str] = ACTIVOS) -> pd.DataFrame:
    """T-test + Mann-Whitney: TPH pre (-24h a -1h) vs TPH post (0h a +24h)."""
    rows: list[dict] = []
    for activo in activos:
        col = f"{activo}_tph"
        opc = f"{activo}_operando"
        if col not in df_ev_ds.columns:
            continue
        pre  = df_ev_ds.loc[(df_ev_ds["periodo"] == "PRE") & df_ev_ds[opc]  & (df_ev_ds[col] > TPH_OP), col].dropna()
        post = df_ev_ds.loc[(df_ev_ds["periodo"].isin(["VENTANA","POST"])) & df_ev_ds[opc] & (df_ev_ds[col] > TPH_OP), col].dropna()
        if len(pre) < 10 or len(post) < 10:
            continue

        t_stat, t_pval   = stats.ttest_ind(pre.values, post.values, equal_var=False)
        u_stat, u_pval   = stats.mannwhitneyu(pre.values, post.values, alternative="two-sided")
        cohen_d = (pre.mean() - post.mean()) / np.sqrt((pre.std()**2 + post.std()**2) / 2)

        rows.append({
            "activo":        activo,
            "tph_pre_mean":  round(float(pre.mean()),  1),
            "tph_post_mean": round(float(post.mean()), 1),
            "delta_pct":     round((post.mean() - pre.mean()) / pre.mean() * 100, 2),
            "t_stat":        round(float(t_stat),  3),
            "t_pval":        round(float(t_pval),  4),
            "u_stat":        round(float(u_stat),  1),
            "u_pval":        round(float(u_pval),  4),
            "cohen_d":       round(float(cohen_d), 3),
            "significativo": "SI" if min(t_pval, u_pval) < ALPHA else "NO",
            "n_pre":         len(pre),
            "n_post":        len(post),
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# Figuras 01-04: EventStudy por activo
# ═══════════════════════════════════════════════════════════════════════════════

def _plot_response_curve_single(
    ax: plt.Axes,
    df_curve: pd.DataFrame,
    activo: str,
    dur_h: int | None = None,
    color: str | None = None,
    label: str | None = None,
    show_iqr: bool = True,
) -> None:
    """Dibuja curva de respuesta promedio en un eje dado."""
    sub = df_curve[df_curve["activo"] == activo].sort_values("h_rel")
    if sub.empty:
        return
    c = color or COLOR_ACTIVO.get(activo, "#333333")
    lbl = label or activo
    ax.plot(sub["h_rel"], sub["tph_mean"], color=c, linewidth=2.2, label=lbl)
    if show_iqr:
        ax.fill_between(sub["h_rel"], sub["tph_p25"], sub["tph_p75"],
                        color=c, alpha=0.14)


def plot_event_study_by_activo(df_curves: pd.DataFrame, df_metrics: pd.DataFrame) -> None:
    """
    Figuras 01-04: una figura por activo.
    Muestra la curva de respuesta promedio (todos los eventos) con duración desglosada.
    """
    fnames = {
        "SAG1":     "01_EventStudy_SAG1.png",
        "SAG2":     "02_EventStudy_SAG2.png",
        "PMC":      "03_EventStudy_PMC.png",
        "UNITARIO": "04_EventStudy_UNITARIO.png",
    }

    for activo in ACTIVOS:
        fig, axes = plt.subplots(1, 2, figsize=(18, 7))
        color = COLOR_ACTIVO.get(activo, "#333333")

        # Panel izq: curva global + IQR
        ax = axes[0]
        sub_all = df_curves[df_curves["activo"] == activo].sort_values("h_rel")
        if not sub_all.empty:
            ax.fill_between(sub_all["h_rel"], sub_all["tph_p25"], sub_all["tph_p75"],
                            color=color, alpha=0.15, label="IQR 25-75")
            ax.plot(sub_all["h_rel"], sub_all["tph_mean"], color=color,
                    linewidth=2.8, label=f"Media (n puntos={sub_all['n'].sum():,})")

        ax.axvline(0, color="red",    linewidth=1.8, linestyle="--", label="Inicio T8")
        ax.axhline(sub_all["tph_mean"].iloc[:max(1, len(sub_all)//2)].mean() if not sub_all.empty else 0,
                   color="steelblue", linewidth=1.0, linestyle=":", alpha=0.7, label="Baseline aprox.")
        ax.set_title(f"{activo} — Curva de respuesta (todos los eventos)", fontsize=10)
        ax.set_xlabel("Horas relativas al inicio de la ventana T8")
        ax.set_ylabel("TPH promedio (t/h)")
        ax.set_xlim(-PRE_H, POST_H)
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8, loc="lower right")

        # Panel der: por duración de ventana
        ax2 = axes[1]
        for dur in DURATIONS:
            # Filtrar el event dataset por duración
            pass  # Se hace en plot_event_study_by_duracion; aquí mostramos métricas resumen
        if not df_metrics.empty:
            sub_m = df_metrics[df_metrics["activo"] == activo]
            if not sub_m.empty:
                dur_grp = sub_m.groupby("duracion_h")[["caida_pct", "h_rec_90", "ist8"]].mean().round(2)
                x = np.arange(len(dur_grp))
                w = 0.28
                ax2.bar(x - w, dur_grp["caida_pct"].values,   width=w, color="#D65F5F", alpha=0.85, label="Caida %")
                ax2.bar(x,     dur_grp["h_rec_90"].values,    width=w, color="#4878D0", alpha=0.85, label="Rec. 90% (h)")
                ax2.bar(x + w, dur_grp["ist8"].values * 10,   width=w, color="#6ACC65", alpha=0.85, label="IST8 x10")
                ax2.set_xticks(x)
                ax2.set_xticklabels([f"{d}h" for d in dur_grp.index])
                ax2.set_title(f"{activo} — Métricas por duración T8", fontsize=10)
                ax2.set_ylabel("Valor")
                ax2.legend(fontsize=8)
                ax2.grid(True, alpha=0.25, axis="y")

        plt.suptitle(
            f"Event Study T8 — {activo}\nt=0 = inicio oficial ventana | TPH real (t/h)",
            fontsize=12, fontweight="bold"
        )
        plt.tight_layout(rect=[0, 0, 1, 0.94])
        fname = fnames.get(activo, f"EventStudy_{activo}.png")
        fig.savefig(OUT_FIG / fname, dpi=130, bbox_inches="tight")
        plt.close(fig)
        print(f"  {fname}")


# ═══════════════════════════════════════════════════════════════════════════════
# Figuras 05-08: EventStudy por duración
# ═══════════════════════════════════════════════════════════════════════════════

def plot_event_study_by_duration(
    df_ev_ds: pd.DataFrame,
    bin_min: int = BIN_MIN,
) -> None:
    """
    Figuras 05-08: una figura por duración T8.
    Todos los activos superpuestos, curva promedio de TPH real.
    """
    fnames = {2: "05_EventStudy_2h.png", 4: "06_EventStudy_4h.png",
              7: "07_EventStudy_8h.png", 8: "07_EventStudy_8h.png",
              12: "08_EventStudy_12h.png"}
    fnames = {2: "05_EventStudy_2h.png", 4: "06_EventStudy_4h.png",
              8: "07_EventStudy_8h.png", 12: "08_EventStudy_12h.png"}

    for dur in DURATIONS:
        h_ini, h_fin = T8_TIMES.get(dur, (8, 8 + dur))
        dur_h = h_fin - h_ini
        fname = fnames[dur]
        df_dur = df_ev_ds[df_ev_ds["duracion_h"] == dur]
        n_ev   = df_dur["evento_id"].nunique()

        fig, ax = plt.subplots(figsize=(14, 7))
        ax.set_title(
            f"Event Study T8 — Ventanas {dur}h ({h_ini:02d}:00-{h_fin:02d}:00)\n"
            f"t=0 = {h_ini:02d}:00 (inicio oficial) | {n_ev} eventos | todos los activos | TPH real",
            fontsize=11, fontweight="bold",
        )

        if df_dur.empty:
            ax.text(0.5, 0.5, f"Sin eventos T8={dur}h en el periodo",
                    transform=ax.transAxes, ha="center", va="center", color="gray")
        else:
            df_dur2 = df_dur.copy()
            df_dur2["h_rel_bin"] = df_dur2["horas_relativas"].apply(lambda t: _bin_h(t, bin_min))
            for activo in ACTIVOS:
                col = f"{activo}_tph"
                opc = f"{activo}_operando"
                if col not in df_dur2.columns:
                    continue
                mask = df_dur2[opc] & (df_dur2[col] > TPH_OP)
                grp = df_dur2.loc[mask].groupby("h_rel_bin")[col].agg(
                    mean="mean", p25=lambda x: np.nanpercentile(x, 25),
                    p75=lambda x: np.nanpercentile(x, 75)
                ).reset_index()
                grp.columns = ["h_rel", "mean", "p25", "p75"]
                c = COLOR_ACTIVO.get(activo, "#333333")
                ax.fill_between(grp["h_rel"], grp["p25"], grp["p75"], color=c, alpha=0.10)
                ax.plot(grp["h_rel"], grp["mean"], color=c, linewidth=2.2, label=activo)
                # Marcar mínimo
                if not grp.empty:
                    idx_min = grp["mean"].idxmin()
                    h_m, v_m = grp.loc[idx_min, "h_rel"], grp.loc[idx_min, "mean"]
                    ax.annotate(f"{v_m:.0f}", xy=(h_m, v_m),
                                xytext=(h_m + 1, v_m - 8), fontsize=7, color=c,
                                arrowprops=dict(arrowstyle="->", color=c, lw=0.7))

        # Zona ventana sombreada
        ax.axvspan(0, dur_h, color="#D65F5F", alpha=0.08, label=f"Ventana T8 {dur}h")
        ax.axvline(0,     color="red",   linewidth=1.8, linestyle="--", label=f"Inicio ({h_ini:02d}:00)")
        ax.axvline(dur_h, color="green", linewidth=1.4, linestyle="--", label=f"Fin ({h_fin:02d}:00)")
        ax.set_xlabel("Horas relativas al inicio de la ventana T8", fontsize=10)
        ax.set_ylabel("TPH promedio (t/h)", fontsize=10)
        ax.set_xlim(-PRE_H, POST_H)
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=9, loc="lower right", framealpha=0.85)
        plt.tight_layout()
        fig.savefig(OUT_FIG / fname, dpi=130, bbox_inches="tight")
        plt.close(fig)
        print(f"  {fname}  ({n_ev} eventos)")


# ═══════════════════════════════════════════════════════════════════════════════
# Figura 09: Efecto Gaviota Global
# ═══════════════════════════════════════════════════════════════════════════════

def plot_gaviota_global(df_curves: pd.DataFrame) -> None:
    """
    Figura 09: 4 activos en un solo gráfico superpuestos (TPH real).
    Todos los eventos alineados en t=0.
    """
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.set_title(
        "Efecto Gaviota Global — Curva de respuesta promedio\n"
        "t=0 = inicio oficial ventana T8 | todos los eventos | TPH real (t/h)",
        fontsize=12, fontweight="bold",
    )

    for activo in ACTIVOS:
        sub = df_curves[df_curves["activo"] == activo].sort_values("h_rel")
        if sub.empty:
            continue
        c = COLOR_ACTIVO.get(activo, "#333333")
        ax.fill_between(sub["h_rel"], sub["tph_p25"], sub["tph_p75"], color=c, alpha=0.09)
        ax.plot(sub["h_rel"], sub["tph_mean"], color=c, linewidth=2.4, label=activo)

    ax.axvline(0, color="red", linewidth=1.8, linestyle="--", label="Inicio T8")
    ax.set_xlabel("Horas relativas al inicio de la ventana T8", fontsize=10)
    ax.set_ylabel("TPH promedio (t/h)", fontsize=10)
    ax.set_xlim(-PRE_H, POST_H)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=9, loc="lower right")
    plt.tight_layout()
    fig.savefig(OUT_FIG / "09_Efecto_Gaviota_Global.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("  09_Efecto_Gaviota_Global.png")


# ═══════════════════════════════════════════════════════════════════════════════
# Figura 10: Comparación de activos normalizada
# ═══════════════════════════════════════════════════════════════════════════════

def plot_comparacion_activos(df_ev_ds: pd.DataFrame, bin_min: int = BIN_MIN) -> None:
    """
    Figura 10: TPH normalizado (% baseline) para los 4 activos superpuestos.
    Facilita comparar qué activo responde peor.
    """
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.set_title(
        "Comparacion de Activos — TPH normalizado\n"
        "t=0 = inicio oficial | 100% = promedio pre-ventana | todos los eventos",
        fontsize=12, fontweight="bold",
    )

    df_ev_ds2 = df_ev_ds.copy()
    df_ev_ds2["h_rel_bin"] = df_ev_ds2["horas_relativas"].apply(lambda t: _bin_h(t, bin_min))

    for activo in ACTIVOS:
        col = f"{activo}_tph"
        opc = f"{activo}_operando"
        if col not in df_ev_ds2.columns:
            continue

        # Normalizar por baseline de cada evento
        norm_series: list[tuple[np.ndarray, np.ndarray]] = []

        for ev_id, df_e in df_ev_ds2.groupby("evento_id"):
            pre_mask = (df_e["periodo"] == "PRE") & df_e[opc] & (df_e[col] > TPH_OP)
            base = df_e.loc[pre_mask, col].mean()
            if np.isnan(base) or base < TPH_OP:
                continue
            grp = df_e.loc[df_e[opc] & (df_e[col] > 0)].groupby("h_rel_bin")[col].mean()
            if grp.empty:
                continue
            norm_series.append((grp.index.values, grp.values / base * 100))

        if not norm_series:
            continue

        # Interpolar cada evento a eje común
        t_common = np.arange(-PRE_H, POST_H + bin_min / 60, bin_min / 60)
        interp_mat = np.array([np.interp(t_common, t_eje_ev, s_ev, left=np.nan, right=np.nan)
                                for t_eje_ev, s_ev in norm_series])
        med = np.nanmedian(interp_mat, axis=0)
        c = COLOR_ACTIVO.get(activo, "#333333")
        ax.plot(t_common, med, color=c, linewidth=2.4, label=activo)

        # Marcar mínimo
        idx_m = np.nanargmin(med)
        ax.annotate(f"{med[idx_m]:.0f}%", xy=(t_common[idx_m], med[idx_m]),
                    xytext=(t_common[idx_m] + 1.5, med[idx_m] - 3),
                    fontsize=8, color=c,
                    arrowprops=dict(arrowstyle="->", color=c, lw=0.8))

    ax.axhline(100, color="gray",  linewidth=1.0, linestyle=":",  alpha=0.7, label="Baseline 100%")
    ax.axhline(90,  color="orange",linewidth=0.8, linestyle="--", alpha=0.5, label="-10%")
    ax.axvline(0,   color="red",   linewidth=1.8, linestyle="--", label="Inicio T8")
    ax.set_xlabel("Horas relativas al inicio de la ventana T8", fontsize=10)
    ax.set_ylabel("TPH normalizado (% baseline pre-ventana)")
    ax.set_xlim(-PRE_H, POST_H)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=9, loc="lower right")
    plt.tight_layout()
    fig.savefig(OUT_FIG / "10_Comparacion_Activos.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("  10_Comparacion_Activos.png")


# ═══════════════════════════════════════════════════════════════════════════════
# Figura 11: Tiempos de recuperación
# ═══════════════════════════════════════════════════════════════════════════════

def plot_tiempo_recuperacion(df_metrics: pd.DataFrame) -> None:
    """Figura 11: barras de recuperación 80/90/95/100% por activo y duración."""
    if df_metrics.empty:
        return
    REC_COLS   = ["h_rec_80", "h_rec_90", "h_rec_95", "h_rec_100"]
    REC_LABELS = ["80%", "90%", "95%", "100%"]
    REC_COLORS = ["#6ACC65", "#4878D0", "#EE854A", "#D65F5F"]

    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    fig.suptitle("Tiempo de Recuperacion Post-Ventana T8\nHoras desde el minimo hasta recuperar % del baseline",
                 fontsize=12, fontweight="bold")

    for ax, groupby_col, title in zip(axes, ["activo", "duracion_h"],
                                       ["Por activo", "Por duracion T8 (h)"]):
        grp = df_metrics.groupby(groupby_col)[REC_COLS].mean()
        x = np.arange(len(grp))
        w = 0.18
        for k, (col, lbl, clr) in enumerate(zip(REC_COLS, REC_LABELS, REC_COLORS)):
            vals = grp[col].values
            bars = ax.bar(x + k * w, vals, width=w, label=lbl, color=clr, alpha=0.85)
            for b, v in zip(bars, vals):
                if not np.isnan(v):
                    ax.text(b.get_x() + b.get_width()/2, v + 0.3,
                            f"{v:.0f}h", ha="center", va="bottom", fontsize=7)
        ax.set_xticks(x + 1.5 * w)
        xlabels = [str(i) for i in grp.index] if groupby_col == "activo" else [f"{i}h" for i in grp.index]
        ax.set_xticklabels(xlabels, fontsize=10)
        ax.set_ylabel("Horas desde el minimo")
        ax.set_title(title)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25, axis="y")

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(OUT_FIG / "11_Tiempo_Recuperacion.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("  11_Tiempo_Recuperacion.png")


# ═══════════════════════════════════════════════════════════════════════════════
# Figura 12: Caída máxima
# ═══════════════════════════════════════════════════════════════════════════════

def plot_caida_maxima(df_metrics: pd.DataFrame) -> None:
    """Figura 12: distribución de caída % por activo y duración."""
    if df_metrics.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    fig.suptitle("Caida Maxima de Rendimiento post-ventana T8",
                 fontsize=12, fontweight="bold")

    # Panel izq: boxplot por activo
    ax = axes[0]
    data_by_activo = [df_metrics.loc[df_metrics["activo"] == a, "caida_pct"].dropna().values
                      for a in ACTIVOS]
    bp = ax.boxplot(data_by_activo, patch_artist=True, notch=False)
    for patch, activo in zip(bp["boxes"], ACTIVOS):
        patch.set_facecolor(COLOR_ACTIVO.get(activo, "#4878D0"))
        patch.set_alpha(0.7)
    ax.set_xticklabels(ACTIVOS)
    ax.set_ylabel("Caida % (baseline → minimo)")
    ax.set_title("Distribucion de caida % por activo")
    ax.grid(True, alpha=0.25, axis="y")

    # Panel der: heatmap activo × duración
    ax2 = axes[1]
    heat = df_metrics.pivot_table(values="caida_pct", index="activo",
                                   columns="duracion_h", aggfunc="mean")
    try:
        import seaborn as sns
        sns.heatmap(heat, ax=ax2, cmap="RdYlGn_r", annot=True, fmt=".1f",
                    cbar_kws={"label": "Caida % promedio"}, linewidths=0.4)
    except ImportError:
        im = ax2.imshow(heat.values, cmap="RdYlGn_r", aspect="auto")
        ax2.set_xticks(range(len(heat.columns)))
        ax2.set_xticklabels([f"{c}h" for c in heat.columns])
        ax2.set_yticks(range(len(heat.index)))
        ax2.set_yticklabels(heat.index)
        plt.colorbar(im, ax=ax2, label="Caida % promedio")
    ax2.set_title("Caida % promedio por activo y duracion T8")
    ax2.set_xlabel("Duracion T8 (h)")
    ax2.set_ylabel("Activo")

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(OUT_FIG / "12_Caida_Maxima.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("  12_Caida_Maxima.png")


# ═══════════════════════════════════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════════════════════════════════

def export_results(
    df_eventos:    pd.DataFrame,
    df_ev_ds:      pd.DataFrame,
    df_metrics:    pd.DataFrame,
    df_stats:      pd.DataFrame,
    df_curves:     pd.DataFrame,
) -> Path:
    xls = OUT_XLS / "event_study_t8.xlsx"
    with pd.ExcelWriter(xls, engine="openpyxl") as wr:
        df_eventos.to_excel(wr, sheet_name="eventos_t8", index=False)

        # Resumen por activo
        if not df_metrics.empty:
            res_act = df_metrics.groupby("activo").agg(
                n_eventos=("evento_id","count"),
                caida_pct_mean=("caida_pct","mean"),
                caida_pct_max=("caida_pct","max"),
                h_rec90_mean=("h_rec_90","mean"),
                ist8_mean=("ist8","mean"),
            ).round(2)
            res_act.to_excel(wr, sheet_name="resumen_activo")

            # Comparativo por duración
            res_dur = df_metrics.groupby(["activo","duracion_h"]).agg(
                n=("evento_id","count"),
                caida_pct=("caida_pct","mean"),
                h_hasta_min=("h_hasta_min","mean"),
                h_rec80=("h_rec_80","mean"),
                h_rec90=("h_rec_90","mean"),
                h_rec95=("h_rec_95","mean"),
                ist8=("ist8","mean"),
            ).round(2)
            res_dur.to_excel(wr, sheet_name="por_duracion")

            df_metrics.to_excel(wr, sheet_name="metricas_evento_activo", index=False)

        if not df_stats.empty:
            df_stats.to_excel(wr, sheet_name="significancia_estadistica", index=False)

        if not df_curves.empty:
            df_curves.to_excel(wr, sheet_name="curvas_respuesta", index=False)

    return xls


# ═══════════════════════════════════════════════════════════════════════════════
# Paso 10 — Resumen ejecutivo
# ═══════════════════════════════════════════════════════════════════════════════

def build_executive_summary(
    df_eventos: pd.DataFrame,
    df_metrics: pd.DataFrame,
    df_stats:   pd.DataFrame,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_ev = len(df_eventos)

    lines = [
        "# Event Study Industrial T8 — Resumen Ejecutivo",
        f"*Generado: {now}*",
        "",
        "## Configuracion del analisis",
        f"- Eventos T8 analizados: **{n_ev}**",
        f"- Ventana de analisis: -{PRE_H}h a +{POST_H}h relativas al inicio oficial",
        f"- Horarios oficiales: 2h=14-16h | 4h=12-16h | 8h=8-16h | 12h=8-20h",
        "",
    ]

    if df_metrics.empty:
        lines.append("*Sin metricas calculadas — verifique disponibilidad de datos.*")
        return "\n".join(lines)

    worst_a  = df_metrics.groupby("activo")["caida_pct"].mean().idxmax()
    worst_d  = df_metrics.groupby("activo")["caida_pct"].mean().max()
    slow_a   = df_metrics.groupby("activo")["h_rec_90"].mean().idxmax()
    slow_d   = df_metrics.groupby("activo")["h_rec_90"].mean().max()
    sens_a   = df_metrics.groupby("activo")["ist8"].mean().idxmax()
    worst_ev = df_metrics.sort_values("caida_pct", ascending=False).iloc[0]
    n_alto   = (df_metrics["caida_pct"] > 15).sum()

    lines += [
        "## Hallazgos principales",
        f"1. **Activo con mayor caida**: **{worst_a}** ({worst_d:.1f}% caida promedio).",
        f"2. **Recuperacion mas lenta**: **{slow_a}** ({slow_d:.1f}h para 90% del baseline).",
        f"3. **Mayor IST8 (sensibilidad)**: **{sens_a}**.",
        f"4. **Peor evento**: {worst_ev['activo']} el {worst_ev['fecha']} "
        f"(dur={worst_ev['duracion_h']}h, caida={worst_ev['caida_pct']:.1f}%).",
        f"5. **Eventos con caida >15%**: {n_alto} de {len(df_metrics)} registros.",
        "",
    ]

    if not df_stats.empty:
        sig = df_stats[df_stats["significativo"] == "SI"]["activo"].tolist()
        lines += [
            "## Significancia estadistica (T-test + Mann-Whitney)",
            f"- Activos con caida significativa (p<{ALPHA}): **{', '.join(sig) if sig else 'Ninguno'}**",
        ]
        for _, r in df_stats.iterrows():
            lines.append(
                f"  - {r['activo']}: pre={r['tph_pre_mean']:.0f} t/h | "
                f"post={r['tph_post_mean']:.0f} t/h | delta={r['delta_pct']:.1f}% | "
                f"p={r['t_pval']:.4f} | {r['significativo']}"
            )
        lines.append("")

    dur_grp = df_metrics.groupby("duracion_h")["caida_pct"].mean().sort_values(ascending=False)
    lines += [
        "## Comparativo por duracion de ventana",
        "| Duracion | Caida % promedio | Ventana oficial |",
        "|----------|-----------------|-----------------|",
    ]
    for dur, caida in dur_grp.items():
        h_i, h_f = T8_TIMES.get(int(dur), (8, 8 + int(dur)))
        lines.append(f"| {dur}h | {caida:.1f}% | {h_i:02d}:00-{h_f:02d}:00 |")

    lines += [
        "",
        "## Recomendaciones operacionales",
        f"- Monitorear **{worst_a}** de forma prioritaria durante y post-ventana.",
        "- Activar protocolo de compensacion para ventanas >= 4h.",
        "- Asegurar nivel de pila antes de cada ventana programada.",
        "- Ventanas de 12h generan el mayor impacto acumulado — planificar con anticipacion.",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Punto de entrada principal
# ═══════════════════════════════════════════════════════════════════════════════

def run_event_study(
    df_rend:        pd.DataFrame | None = None,
    pam_mantto_dir: Path | None = None,
    activos:        list[str] | None = None,
    pre_h:  int = PRE_H,
    post_h: int = POST_H,
    bin_min: int = BIN_MIN,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Ejecuta el Event Study Industrial completo.

    Genera 12 figuras en outputs/figures/event_study/ y
    event_study_t8.xlsx en outputs/excel/.
    """
    _activos = activos or ACTIVOS

    if verbose:
        print("=" * 72)
        print("  Event Study Industrial — Ventanas Teniente 8")
        print("=" * 72)

    # Rendimientos
    df_rend_clean = _load_rend(df_rend)
    if verbose:
        print(f"  Rendimientos: {len(df_rend_clean):,} registros | "
              f"{df_rend_clean['fecha'].min().date()} -> {df_rend_clean['fecha'].max().date()}")

    # Eventos
    df_eventos = _load_t8_events(pam_mantto_dir)
    path_ev = save_eventos_parquet(df_eventos)
    if verbose:
        print(f"  Eventos T8: {len(df_eventos)} | Guardado: {path_ev.name}")
        for dur in DURATIONS:
            n = (df_eventos["duracion_h"] == dur).sum()
            h_i, h_f = T8_TIMES[dur]
            if n:
                print(f"    - {dur}h ({h_i:02d}:00-{h_f:02d}:00): {n} eventos")

    # Event dataset
    if verbose:
        print("\n  Construyendo event dataset...")
    df_ev_ds = build_event_dataset(df_eventos, df_rend_clean, pre_h=pre_h, post_h=post_h)
    if df_ev_ds.empty:
        raise ValueError("Event dataset vacio: no hay solapamiento entre eventos y rendimientos.")
    if verbose:
        print(f"  Event dataset: {len(df_ev_ds):,} filas | "
              f"{df_ev_ds['evento_id'].nunique()} eventos cruzados")

    # Curvas de respuesta
    df_curves = build_response_curves(df_ev_ds, activos=_activos, bin_min=bin_min)

    # Metricas
    if verbose:
        print("  Calculando metricas...")
    df_metrics = compute_event_metrics(df_ev_ds, df_eventos, activos=_activos)
    if verbose:
        print(f"  Metricas: {len(df_metrics)} registros (eventos x activos)")

    # Estadistica
    df_stats = compute_statistics(df_ev_ds, activos=_activos)

    # Figuras
    if verbose:
        print("\n  Generando figuras...")
    plot_event_study_by_activo(df_curves, df_metrics)
    plot_event_study_by_duration(df_ev_ds, bin_min=bin_min)
    plot_gaviota_global(df_curves)
    plot_comparacion_activos(df_ev_ds, bin_min=bin_min)
    plot_tiempo_recuperacion(df_metrics)
    plot_caida_maxima(df_metrics)

    # Export
    xls_path = export_results(df_eventos, df_ev_ds, df_metrics, df_stats, df_curves)
    if verbose:
        print(f"\n  Excel: {xls_path.name}")

    # Resumen
    summary = build_executive_summary(df_eventos, df_metrics, df_stats)
    rpt = OUT_RPT / "resumen_event_study_t8.md"
    rpt.write_text(summary, encoding="utf-8")
    if verbose:
        print(f"  Reporte: {rpt.name}")
        print()
        print(summary)

    # Log
    with open(LOGS_DIR / "skill_audit.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "fecha": datetime.now().isoformat(),
            "script": "src/event_study_t8.py",
            "n_eventos": len(df_eventos),
            "n_metricas": len(df_metrics),
            "figuras": [p.name for p in sorted(OUT_FIG.glob("*.png"))],
        }, ensure_ascii=False) + "\n")

    if verbose:
        print("=" * 72)
        print("  Completado.")
        print("=" * 72)

    return {
        "df_eventos":  df_eventos,
        "df_ev_ds":    df_ev_ds,
        "df_curves":   df_curves,
        "df_metrics":  df_metrics,
        "df_stats":    df_stats,
        "summary":     summary,
    }


if __name__ == "__main__":
    run_event_study()
