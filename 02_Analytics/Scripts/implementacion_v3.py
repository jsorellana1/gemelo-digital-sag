"""
implementacion_v3.py
Genera figuras y reporte MD del Optimizer V3.

Ejecutar desde la raiz del proyecto:
  python 02_Analytics/Scripts/implementacion_v3.py

Salidas:
  02_Analytics/Figures/13_Optimizer_V3/v3_01_pesos_comparacion.png
  02_Analytics/Figures/13_Optimizer_V3/v3_02_candidatos_historicos.png
  02_Analytics/Figures/13_Optimizer_V3/v3_03_escenarios_comparacion.png
  02_Analytics/Figures/13_Optimizer_V3/v3_04_roi_bolas.png
  04_Reports/Technical/11_Optimizer_V3/20260701_Optimizer_V3_Implementation.md
"""
from __future__ import annotations
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "05_Dashboard"))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from engine.optimizer_v3 import (
    find_optimal_v3, compute_brecha, compute_roi_bolas, compare_v2_v3_weights,
    SAG1_P50, SAG1_P75, SAG1_P90, SAG1_MAX, SAG1_CRITICAL,
    SAG1_HIGH_EVENTS, R1_CANDS_V3, REGIMES_V3,
)

FIGURES = ROOT / "02_Analytics" / "Figures" / "13_Optimizer_V3"
REPORTS = ROOT / "04_Reports" / "Technical" / "11_Optimizer_V3"
DATA    = ROOT / "01_Data" / "Cache"
FIGURES.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

AZUL    = "#1F3864"
VERDE   = "#27AE60"
NARANJA = "#E67E22"
ROJO    = "#C0392B"
GRIS    = "#95A5A6"
CELESTE = "#2980B9"

T8_SCENARIOS = [0, 2, 4, 8, 12]
LABELS_T8    = ["Sin T8", "T8=2h", "T8=4h", "T8=8h", "T8=12h"]
MODES_EVAL   = ["balanced", "max_prod", "safe"]


# ---- Seccion 1: Ejecutar escenarios ----------------------------------------

def run_all_scenarios() -> pd.DataFrame:
    print("[1/5] Ejecutando 5 T8 x 3 modos con Optimizer V3...")
    rows = []
    for t8, label in zip(T8_SCENARIOS, LABELS_T8):
        for mode in MODES_EVAL:
            try:
                best, _ = find_optimal_v3(
                    pila1=45.0, pila2=50.0, duracion_t8=t8,
                    sag1_on=True, sag2_on=True,
                    ch1_on=True, ch2_on=True,
                    c315="activa", c316="activa",
                    t1_mode="chancado", t1_manual=4000.0,
                    t3_frac=0.0, distribucion_t1="proporcional",
                    mode=mode,
                )
            except Exception as e:
                print(f"  SKIP t8={t8} mode={mode}: {e}")
                continue

            rows.append({
                "t8":              t8,
                "label_t8":        label,
                "mode":            mode,
                "r1":              best["r1"],
                "b1":              best["b1"],
                "r2":              best["r2"],
                "b2":              best["b2"],
                "tph_total":       best["tph_mean"],
                "p_safe":          best["p_safe"],
                "a1_med":          best.get("a1_med", 0),
                "inv_sag1_fin":    best.get("inv_sag1_final", 0),
                "mc_score":        best.get("multi_criteria_score", 0),
                "regime":          best.get("regime", ""),
                "brecha_tph":      best.get("brecha_p90", {}).get("brecha_tph_sag1", 0),
                "brecha_ton_dia":  best.get("brecha_p90", {}).get("brecha_ton_dia", 0),
                "zona":            best.get("brecha_p90", {}).get("zona", ""),
                "validation":      best.get("validation_answer", ""),
            })
            print(f"  T8={t8}h/{mode}: SAG1={best['r1']} TPH {best['b1'][:6]} | "
                  f"TPH={best['tph_mean']:.0f} | P(safe)={best['p_safe']*100:.0f}%")

    df = pd.DataFrame(rows)
    print(f"   -> {len(df)} resultados completados")
    return df


def load_historical() -> dict:
    hist_file = DATA / "advanced_t8_historical_5min.parquet"
    if not hist_file.exists():
        return {"disponible": False}

    df = pd.read_parquet(hist_file)
    s1 = df[df["SAG1_operando"] == True]
    pcts = {p: round(s1["SAG1_tph"].quantile(p/100), 0) for p in [25, 50, 75, 90, 95]}
    return {
        "disponible":   True,
        "tph_series":   s1["SAG1_tph"].values,
        "pila_series":  s1["pila_sag1"].values if "pila_sag1" in s1 else np.zeros(len(s1)),
        "percentiles":  pcts,
        "mean":         round(s1["SAG1_tph"].mean(), 1),
    }


# ---- Figura 1: Comparacion pesos V2 vs V3 ----------------------------------

def fig_pesos_comparacion() -> Path:
    comp = compare_v2_v3_weights()
    df   = pd.DataFrame(comp)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Optimizer V3 vs V2: Comparacion de Pesos por Regimen",
                 fontsize=13, fontweight="bold", color=AZUL)

    REGIMES_LABELS = {"normal": "Normal (sin T8)", "t8_corta": "T8 Corta (<=4h)", "t8_larga": "T8 Larga (>4h)"}
    COMP_COLORS    = {"produccion": VERDE, "riesgo": ROJO, "inventario": NARANJA, "autonomia": CELESTE, "min_auton_SAG1": AZUL}
    COMP_LABELS    = {"produccion": "Produccion", "riesgo": "Riesgo", "inventario": "Inventario",
                      "autonomia": "Autonomia", "min_auton_SAG1": "Min Auton SAG1 (h)"}

    for ax, (rk, rl) in zip(axes, REGIMES_LABELS.items()):
        sub  = df[df["regimen"] == rk]
        comps = sub["componente"].tolist()
        v2   = sub["v2"].values
        v3   = sub["v3"].values
        x    = np.arange(len(comps))
        w    = 0.35

        bars_v2 = ax.bar(x - w/2, v2, w, label="V2", color=AZUL, alpha=0.6, edgecolor="white")
        bars_v3 = ax.bar(x + w/2, v3, w, label="V3", color=VERDE, alpha=0.85, edgecolor="white")

        # Anotaciones de delta
        for xi, (v2_val, v3_val) in enumerate(zip(v2, v3)):
            delta = v3_val - v2_val
            color = VERDE if delta > 0 else ROJO
            sign  = "+" if delta >= 0 else ""
            ax.annotate(f"{sign}{delta:.2f}", xy=(xi + w/2, v3_val + 0.01),
                        ha="center", fontsize=7.5, color=color, fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels([COMP_LABELS.get(c, c) for c in comps], rotation=20, fontsize=8)
        ax.set_title(rl, fontsize=10, fontweight="bold")
        ax.set_ylim(0, max(v2.max(), v3.max()) * 1.25)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        if rk == "normal":
            ax.set_ylabel("Peso / Umbral", fontsize=9)

    plt.tight_layout()
    out = FIGURES / "v3_01_pesos_comparacion.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"   Figura: {out.name}")
    return out


# ---- Figura 2: Candidatos anclados a historico -----------------------------

def fig_candidatos_historicos(hist: dict) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(f"V3: Grid de candidatos anclado a percentiles historicos SAG1\n"
                 f"(n={SAG1_HIGH_EVENTS} eventos >= P75 por >= 2h sin crisis de inventario)",
                 fontsize=11, fontweight="bold", color=AZUL)

    # Panel 1: histograma con marcas de candidatos
    ax = axes[0]
    if hist.get("disponible"):
        ax.hist(hist["tph_series"], bins=60, color=AZUL, alpha=0.55, edgecolor="white",
                density=True, label="Distribucion historica SAG1")

    # Percentiles historicos
    for pct, val, color, label in [
        (50, SAG1_P50,  GRIS,   f"P50 = {SAG1_P50:.0f} TPH"),
        (75, SAG1_P75,  NARANJA,f"P75 = {SAG1_P75:.0f} TPH"),
        (90, SAG1_P90,  VERDE,  f"P90 = {SAG1_P90:.0f} TPH"),
        (100,SAG1_MAX,  ROJO,   f"MAX = {SAG1_MAX:.0f} TPH"),
    ]:
        ax.axvline(val, color=color, linewidth=2, linestyle="--", label=label)

    # V2 candidatos
    from engine.optimizer_v2 import R1_CANDS as R1_V2
    for r in R1_V2:
        ax.axvline(r, color=AZUL, linewidth=0.8, linestyle=":", alpha=0.5)
    ax.axvline(-1, color=AZUL, linewidth=1.5, linestyle=":", label="Candidatos V2", alpha=0.5)

    # V3 candidatos como puntos
    y_marker = ax.get_ylim()[1] * 0.05 if ax.get_ylim()[1] > 0 else 0.002
    ax.scatter(R1_CANDS_V3, [y_marker] * len(R1_CANDS_V3),
               color=VERDE, s=80, zorder=5, label="Candidatos V3", marker="^")

    ax.set_xlabel("SAG1 TPH", fontsize=9)
    ax.set_ylabel("Densidad", fontsize=9)
    ax.set_title("V2 vs V3: Cobertura del espacio historico", fontsize=10, fontweight="bold")
    ax.legend(fontsize=7.5, loc="upper left")
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)

    # Panel 2: tabla comparativa de candidatos
    ax2 = axes[1]
    ax2.axis("off")

    from engine.optimizer_v2 import R1_CANDS as R1_V2
    table_data = []
    all_cands = sorted(set(R1_V2 + R1_CANDS_V3))
    for c in all_cands:
        in_v2 = "✓" if c in R1_V2 else ""
        in_v3 = "✓" if c in R1_CANDS_V3 else ""
        pct_p90 = c / SAG1_P90 * 100
        b = compute_brecha(float(c))
        table_data.append([f"{c}", f"{pct_p90:.0f}%", in_v2, in_v3, b["zona"]])

    tbl = ax2.table(
        cellText=table_data,
        colLabels=["TPH", "% P90", "V2", "V3", "Zona"],
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.5)
    tbl.scale(1.2, 1.5)

    for (row, col), cell in tbl.get_celld().items():
        if row == 0:
            cell.set_facecolor(AZUL)
            cell.set_text_props(color="white", fontweight="bold")
        elif table_data[row-1][3] == "✓":   # en V3
            cell.set_facecolor("#E8F8F5")
        elif table_data[row-1][2] == "✓":   # solo V2
            cell.set_facecolor("#F5F5F5")
        cell.set_edgecolor("white")

    ax2.set_title("Cobertura de candidatos", fontsize=10, fontweight="bold", pad=80)

    plt.tight_layout()
    out = FIGURES / "v3_02_candidatos_historicos.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"   Figura: {out.name}")
    return out


# ---- Figura 3: Comparacion 5 T8 x 3 modos ---------------------------------

def fig_escenarios_comparacion(df: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle("Optimizer V3: Recomendaciones por Escenario T8\n"
                 "(Pila SAG1=45%, Pila SAG2=50%, ambos chancadores activos)",
                 fontsize=12, fontweight="bold", color=AZUL)

    metrics = [
        ("tph_total",   "TPH Total (media 24h)", AZUL),
        ("r1",          "Rate SAG1 recomendado (TPH)", VERDE),
        ("p_safe",      "P(Operacion Segura)",  NARANJA),
        ("inv_sag1_fin","Inventario SAG1 Final (%)", CELESTE),
        ("brecha_tph",  "Brecha vs P90 SAG1 (TPH)", ROJO),
        ("mc_score",    "Score Multicriterio V3", GRIS),
    ]
    mode_styles = {"balanced": "o-", "max_prod": "^--", "safe": "s:"}
    mode_colors = {"balanced": AZUL, "max_prod": VERDE, "safe": NARANJA}
    mode_labels = {"balanced": "Balanceado", "max_prod": "Max Produccion", "safe": "Op. Segura"}

    for ax, (col, ylabel, _) in zip(axes.flat, metrics):
        for mode in MODES_EVAL:
            sub = df[df["mode"] == mode].sort_values("t8")
            if sub.empty:
                continue
            vals = sub[col].values
            if col == "p_safe":
                vals = vals * 100
            ax.plot(T8_SCENARIOS[:len(vals)], vals, mode_styles[mode],
                    color=mode_colors[mode], label=mode_labels[mode],
                    linewidth=2, markersize=8)

        # Referencias historicas
        if col == "r1":
            ax.axhline(SAG1_P90, color=VERDE, linewidth=1.5, linestyle=":", alpha=0.7, label=f"P90={SAG1_P90:.0f}")
            ax.axhline(SAG1_P50, color=GRIS,  linewidth=1, linestyle=":", alpha=0.6, label=f"P50={SAG1_P50:.0f}")
        if col == "tph_total":
            ax.axhline(SAG1_P90 + 2214, color=VERDE, linewidth=1, linestyle=":", alpha=0.5,
                       label=f"Ref P90+S2={SAG1_P90+2214:.0f}")
        if col == "p_safe":
            ax.axhline(95, color=ROJO, linewidth=1.5, linestyle="--", alpha=0.6, label="P(safe)=95%")
        if col == "inv_sag1_fin":
            ax.axhline(SAG1_CRITICAL, color=ROJO, linewidth=1.5, linestyle="--", alpha=0.6,
                       label=f"Critico {SAG1_CRITICAL:.0f}%")

        ax.set_xticks(T8_SCENARIOS)
        ax.set_xticklabels(LABELS_T8, fontsize=8, rotation=15)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.set_title(ylabel, fontsize=9, fontweight="bold")
        ax.legend(fontsize=6.5, ncol=2)
        ax.grid(alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    out = FIGURES / "v3_03_escenarios_comparacion.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"   Figura: {out.name}")
    return out


# ---- Figura 4: ROI Bolas ---------------------------------------------------

def fig_roi_bolas(df: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("ROI de Bolas SAG1: Produccion adicional vs Inventario consumido",
                 fontsize=11, fontweight="bold", color=AZUL)

    # Calcular ROI para cada escenario en balanced mode
    bal = df[df["mode"] == "balanced"].sort_values("t8").copy()

    # ROI estimado a partir de brecha_tph vs consumo adicional de pila
    # Asumimos que sin bolas el rate seria P50, con bolas el rate recomendado por V3
    roi_vals = []
    for _, row in bal.iterrows():
        roi = compute_roi_bolas(
            tph_sin_bolas=SAG1_P50,
            tph_con_bolas=float(row["r1"]),
            inv_fin_sin=45.0 - (SAG1_P50 * 24 / 4575 * 100 * 0.3),  # estimado
            inv_fin_con=float(row["inv_sag1_fin"]),
            inv_ini=45.0,
        )
        roi_vals.append(roi)

    # Panel 1: ROI por escenario T8
    ax = axes[0]
    rois = [r["roi_bolas"] for r in roi_vals]
    colors = [VERDE if r > 300 else NARANJA if r > 100 else ROJO for r in rois]
    bars = ax.bar(LABELS_T8[:len(rois)], [min(r, 5000) for r in rois],
                  color=colors, alpha=0.85, edgecolor="white")
    ax.axhline(300, color=VERDE, linewidth=2, linestyle="--", label="Umbral beneficioso (300)")
    ax.axhline(100, color=NARANJA, linewidth=1.5, linestyle=":", label="Umbral moderado (100)")
    for bar, roi in zip(bars, rois):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 50,
                f"{roi:.0f}", ha="center", fontsize=8.5, fontweight="bold")
    ax.set_ylabel("ROI Bolas (t/% pila consumida)", fontsize=9)
    ax.set_title("ROI Bolas por Escenario T8", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xticklabels(LABELS_T8[:len(rois)], rotation=15)

    # Panel 2: Detalle delta TPH vs delta inventario
    ax2 = axes[1]
    delta_tph_vals = [r["delta_tph"] for r in roi_vals]
    delta_inv_vals = [r["delta_inv_consumida"] for r in roi_vals]
    sc = ax2.scatter(delta_inv_vals, delta_tph_vals,
                     c=[r["roi_bolas"] for r in roi_vals],
                     cmap="RdYlGn", s=180, zorder=5, vmin=0, vmax=2000,
                     edgecolors=AZUL, linewidths=1.5)
    for i, (dx, dy, label) in enumerate(zip(delta_inv_vals, delta_tph_vals, LABELS_T8)):
        ax2.annotate(label, (dx, dy), textcoords="offset points",
                     xytext=(6, 4), fontsize=8.5, color=AZUL)
    plt.colorbar(sc, ax=ax2, label="ROI Bolas", shrink=0.85)
    ax2.set_xlabel("Delta Inventario consumido (%)", fontsize=9)
    ax2.set_ylabel("Delta TPH (vs P50 sin bolas)", fontsize=9)
    ax2.set_title("ΔTPH vs ΔInventario por Escenario", fontsize=10, fontweight="bold")
    ax2.grid(alpha=0.25)
    ax2.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    out = FIGURES / "v3_04_roi_bolas.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"   Figura: {out.name}")
    return out


# ---- Reporte MD -------------------------------------------------------------

def build_md(df: pd.DataFrame) -> str:
    bal = df[df["mode"] == "balanced"].sort_values("t8")

    # Tabla de recomendaciones
    tabla_rows = []
    for _, row in bal.iterrows():
        b1_txt = "B411+412" if "ambas" in row["b1"] else "Sin bola"
        tabla_rows.append(
            f"| {row['label_t8']:<8} | {row['regime']:<10} | {row['r1']:.0f} TPH / {b1_txt} | "
            f"{row['tph_total']:.0f} | {row['p_safe']*100:.0f}% | {row['brecha_tph']:.0f} | {row['zona']} |"
        )
    tabla = "\n".join(tabla_rows)

    # Respuestas de validacion
    validaciones = []
    questions = [
        (0, "Sin T8", "¿Por que SAG1 no opera cerca de P90?"),
        (2, "T8=2h",  "¿Realmente necesito restringir SAG1?"),
        (4, "T8=4h",  "¿Cuanto puedo subir SAG1?"),
        (8, "T8=8h",  "¿Cual es la mejor estrategia con T8 larga?"),
        (12,"T8=12h", "¿Cual es el costo productivo de proteger inventario?"),
    ]
    for t8, label, q in questions:
        row = df[(df["t8"] == t8) & (df["mode"] == "balanced")]
        if row.empty:
            continue
        r = row.iloc[0]
        validaciones.append(f"\n### {label}: {q}\n\n{r['validation']}\n")
    val_text = "\n".join(validaciones)

    # Tabla pesos V2 vs V3
    comp = pd.DataFrame(compare_v2_v3_weights())
    normal = comp[comp["regimen"] == "normal"]
    w_tabla = "\n".join([
        f"| {row['componente']:<18} | {row['v2']:.2f} | {row['v3']:.2f} | {'+' if row['delta']>0 else ''}{row['delta']:.2f} |"
        for _, row in normal.iterrows()
    ])

    return f"""# Optimizer V3 — Implementacion basada en evidencia operacional

Fecha: 2026-07-01
Version: V3.0
Autor: Juan Orellana / AA_CIO_DET / Codelco El Teniente

---

## 1. Objetivo

Corregir el sesgo sistemático del Optimizer V2 que subestimaba la capacidad productiva de SAG1.

**Evidencia de sesgo:**
- SAG1 media historica = {SAG1_P50:.0f} TPH (solo {SAG1_P50/SAG1_P90*100:.0f}% del P90)
- SAG1 P90 historico = {SAG1_P90:.0f} TPH (alcanzable segun {SAG1_HIGH_EVENTS} eventos documentados)
- SAG1 MAX historico = {SAG1_MAX:.0f} TPH
- Brecha P50 vs P90 = {SAG1_P90 - SAG1_P50:.0f} TPH = {(SAG1_P90 - SAG1_P50)*24:.0f} t/dia

---

## 2. Cambios V3 vs V2

### 2.1 Anclas historicas (nuevas en V3)

| KPI      | Valor     | Fuente |
|----------|-----------|--------|
| SAG1 P50 | {SAG1_P50:.0f} TPH | Historico 93 612 registros |
| SAG1 P75 | {SAG1_P75:.0f} TPH | Historico |
| SAG1 P90 | {SAG1_P90:.0f} TPH | Historico |
| SAG1 MAX | {SAG1_MAX:.0f} TPH | Maximo observado |
| Eventos alta prod | {SAG1_HIGH_EVENTS} | >= P75 por >= 2h sin crisis |

### 2.2 Grid de candidatos V3 (anclados a percentiles)

V2: [727, 1018, 1309, 1454, 1527]
V3: {R1_CANDS_V3}

Los candidatos V3 eliminan las tasas por debajo del P50 (727, 1018) que nunca
son operacionalmente optimas en regimen normal, y agregan 1200 y 1400 TPH como
puntos intermedios entre P75 y P90.

### 2.3 Pesos regimen Normal (cambio mas critico)

| Componente        | V2   | V3   | Delta |
|-------------------|------|------|-------|
{w_tabla}

La reduccion de min_auton_SAG1 de 0.50h a 0.30h en regimen Normal refleja la
realidad: cuando CV315 opera normalmente, la autonomia del SAG1 no es una
restriccion critica. La pila existe para ser consumida, no conservada.

---

## 3. Nuevo KPI: Brecha P90

**Definicion:**
  brecha_tph_sag1 = max(SAG1_P90 - tph_sag1_recomendado, 0)
  brecha_ton_dia  = brecha_tph * horizonte (horas)

**Zonas de operacion:**
  optima:      >= 97% del P90
  buena:       90-97% del P90
  mejorable:   80-90% del P90
  restringida: < 80% del P90

---

## 4. Nuevo KPI: ROI de Bolas

**Definicion:**
  ROI_Bolas = (ΔTPH × horizonte) / ΔInventario_consumido (%)

Unidad: toneladas adicionales por porcentaje adicional de pila consumida.

**Umbral de decision:**
  ROI > 300 t/% → Beneficioso (activar bolas es optimo)
  ROI 100-300   → Moderado (evaluar segun disponibilidad de inventario)
  ROI < 100     → Marginal (preferir sin bolas si inventario es critico)

---

## 5. Resultados por escenario T8 (modo Balanceado)

| Escenario | Regimen    | Recomendacion SAG1       | TPH Total | P(safe) | Brecha P90 | Zona |
|-----------|------------|--------------------------|-----------|---------|------------|------|
{tabla}

---

## 6. Respuestas a Validaciones Obligatorias
{val_text}

---

## 7. Compatibilidad V2

optimizer_v3.py mantiene compatibilidad total con optimizer_v2.py:
- Misma firma: find_optimal_v3(...) acepta identicos kwargs que find_optimal_v2
- V2 sigue disponible como respaldo: from engine.optimizer_v2 import find_optimal_v2
- Los resultados V3 extienden los de V2 con campos adicionales:
    best["brecha_p90"]         -> dict con brecha vs P90 historico
    best["roi_bolas_sag1"]     -> dict con ROI de activar bolas SAG1
    best["validation_answer"]  -> texto de validacion por regimen
    best["version"]            -> "v3"

---

## 8. Proximos pasos

1. Integrar find_optimal_v3 en app.py callbacks (reemplaza find_optimal_v2)
2. Agregar panel "Oportunidad SAG1" al dashboard (/modelo o /riesgo)
3. Agregar comparador de escenarios (actual vs optimizado)
4. Mostrar KPI brecha_p90 en badge del boton Optimizer
5. Agregar ROI_Bolas en tabla Top-5 del dashboard

---

## 9. Archivos modificados / generados

  05_Dashboard/engine/optimizer_v2.py   [MODIFICADO — run_deterministic_grid acepta r1_cands/r2_cands]
  05_Dashboard/engine/optimizer_v3.py   [NUEVO — 280 lineas]
  02_Analytics/Scripts/implementacion_v3.py [NUEVO — este script]
  02_Analytics/Figures/13_Optimizer_V3/ [NUEVO — 4 figuras]
  04_Reports/Technical/11_Optimizer_V3/20260701_Optimizer_V3_Implementation.md [ESTE ARCHIVO]
"""


# ---- Main -------------------------------------------------------------------

def main():
    print("=== Implementacion Optimizer V3 ===")

    df  = run_all_scenarios()
    hist = load_historical()

    print("[2/5] Figura 1: Pesos V2 vs V3")
    f1 = fig_pesos_comparacion()

    print("[3/5] Figura 2: Candidatos historicos")
    f2 = fig_candidatos_historicos(hist)

    print("[4/5] Figura 3: Escenarios comparacion")
    f3 = fig_escenarios_comparacion(df)

    print("[5/5] Figura 4: ROI Bolas + Reporte MD")
    f4 = fig_roi_bolas(df)

    md = build_md(df)
    out_md = REPORTS / "20260701_Optimizer_V3_Implementation.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"[OK] MD: {out_md}")

    # Resumen en consola
    bal = df[df["mode"] == "balanced"].sort_values("t8")
    print("\n=== RECOMENDACIONES V3 (modo Balanceado) ===")
    for _, row in bal.iterrows():
        b1_txt = "B411+412" if "ambas" in row["b1"] else "SinBola"
        print(f"  {row['label_t8']:<8} [{row['regime']:<10}] "
              f"SAG1={row['r1']:.0f}TPH/{b1_txt} "
              f"| TPH={row['tph_total']:.0f} | P(safe)={row['p_safe']*100:.0f}% "
              f"| Brecha={row['brecha_tph']:.0f}TPH | Zona={row['zona']}")

    print("\n=== COMPLETO ===")


if __name__ == "__main__":
    main()
