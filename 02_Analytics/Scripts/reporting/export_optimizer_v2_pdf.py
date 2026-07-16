"""
export_optimizer_v2_pdf.py — Genera reporte tecnico del Optimizer v2.

Salidas:
  04_Reports/Technical/10_Optimizer_v2/20260701_Optimizer_v2_Design.md
  04_Reports/Technical/10_Optimizer_v2/20260701_Optimizer_v2_Executive.pdf
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
REPORTS = BASE / "04_Reports" / "Technical" / "10_Optimizer_v2"
FIGURES = BASE / "02_Analytics" / "Figures" / "12_Optimizer_v2"
CACHE   = BASE / "01_Data" / "Cache" / "bola_delta_tph.json"

REPORTS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

MD_PATH  = REPORTS / "20260701_Optimizer_v2_Design.md"
PDF_PATH = REPORTS / "20260701_Optimizer_v2_Executive.pdf"


# ---- Helpers (equivalentes a export_model_loop_v3_pdf) -----------------------

def split_markdown_sections(text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_title = "Resumen"
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = line.replace("## ", "", 1).strip()
            current_lines = []
        elif line:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, current_lines))
    return sections


def add_text_page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    ax  = fig.add_axes([0.06, 0.05, 0.88, 0.90])
    ax.axis("off")
    ax.text(0.0, 1.0, title, fontsize=16, fontweight="bold", va="top")

    y = 0.94
    for line in lines:
        wrapped = textwrap.wrap(line, width=95) or [""]
        for part in wrapped:
            ax.text(0.0, y, part, fontsize=10.5, va="top", family="DejaVu Sans")
            y -= 0.027
            if y < 0.06:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
                fig = plt.figure(figsize=(8.27, 11.69))
                ax  = fig.add_axes([0.06, 0.05, 0.88, 0.90])
                ax.axis("off")
                ax.text(0.0, 1.0, f"{title} (cont.)", fontsize=16, fontweight="bold", va="top")
                y = 0.94
        y -= 0.008

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def add_image_page(pdf: PdfPages, img_path: Path, title: str = "") -> None:
    if not img_path.exists():
        print(f"  [SKIP] figura no encontrada: {img_path.name}")
        return
    img = plt.imread(str(img_path))
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.imshow(img)
    ax.axis("off")
    if title:
        fig.suptitle(title, fontsize=13, fontweight="bold", y=0.99)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


# ---- Carga calibracion -------------------------------------------------------

def _load_calibration() -> dict:
    if CACHE.exists():
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---- Generacion MD -----------------------------------------------------------

def build_md(cal: dict) -> str:
    sag1 = cal.get("SAG1", {})
    sag2 = cal.get("SAG2", {})

    d1_1 = sag1.get("delta_tph_1bola", "N/A")
    d1_2 = sag1.get("delta_tph_2bola", "N/A")
    d2_1 = sag2.get("delta_tph_1bola", "N/A")
    d2_2 = sag2.get("delta_tph_2bola", "N/A")
    warn1 = sag1.get("warning", "")
    warn2 = sag2.get("warning", "")
    n01   = sag1.get("n_per_stratum", {}).get("0", "N/A")
    n02   = sag2.get("n_per_stratum", {}).get("0", "N/A")

    lines = f"""# Optimizer v2 — Diseno Tecnico y Validacion

Fecha: 2026-07-01
Version: v2.0
Autor: Juan Orellana / AA_CIO_DET / Codelco El Teniente

---

## 1. Motivacion y Problema Resuelto

El optimizador legacy (v1) usaba score = TPH - deficit_autonomia * 2000. Esta penalizacion
dura hacia que SAG1 (pila 4575 ton, drenaje 23.76 %/h) entrara casi siempre en zona
infactible al activar bolas, aniquilando su score. Resultado: el boton Optimo segun pila
siempre recomendaba sin_bola para SAG1, independientemente de las condiciones de inventario.

El Optimizer v2 reemplaza la penalizacion dura por una funcion multicriterio ponderada
donde la autonomia es un componente suave (10%), no una barrera.

## 2. Funcion Objetivo Multicriterio

  score = 0.40 * prod_norm + 0.30 * p_safe + 0.20 * inv_norm + 0.10 * auton_norm

Donde:
  prod_norm  = TPH_total / 3970 (P90 SAG1+SAG2 como referencia)
  p_safe     = P(autonomia >= umbral) del Monte Carlo adaptativo
  inv_norm   = pila_final_promedio / 70%
  auton_norm = (a1/6h + a2/8h) / 2

Todos los componentes en [0, 1]. Autonomia contribuye solo el 10% -- SAG1 con bolas
recibe penalizacion parcial, no aniquilamiento.

## 3. Calibracion Historica DELTA_TPH Bolas

### Resultados

| SAG  | Delta TPH (1 bola) | Delta TPH (2 bolas) | n0 (sin bola) | Fuente         |
|------|--------------------|---------------------|---------------|----------------|
| SAG1 | {d1_1} TPH         | {d1_2} TPH          | {n01}         | {"Historico" if not warn1 else "Modelo legacy"} |
| SAG2 | {d2_1} TPH         | {d2_2} TPH          | {n02}         | {"Historico" if not warn2 else "Modelo legacy"} |

### Notas de calibracion

SAG1: {warn1 or "Sin advertencias -- calibracion aceptada"}
SAG2: {warn2 or "Sin advertencias -- calibracion aceptada"}

Limite minimo para calibracion historica valida: n0 >= 200 (MIN_N0).
Cuando n0 < MIN_N0 se usa modelo de ingenieria legacy: BOLA_BONUS=0.08 * P90.
SAG1 P90=1454 TPH -> delta_legacy = 116.3 TPH/bola.
SAG2 P90=2516 TPH -> delta_legacy = 201.3 TPH/bola.

## 4. Monte Carlo Adaptativo

Parametros:
  - Perturbaciones: pilas +/-2.5%, feed CV +/-12%, T8 +/-1h
  - Lotes: 10 simulaciones por batch
  - Convergencia: |Delta_p_safe| < 1% durante 3 checks consecutivos Y n >= 30
  - Cap: 500 simulaciones maximas
  - Candidatos evaluados por MC: top-20 del grid deterministico (100 configs)

El MC adaptativo reemplaza el n_samples fijo (20/30/50). El estado de convergencia
se muestra en el dashboard: "Sim: N -- Convergente/No convergente".

## 5. Frente de Pareto

Tres objetivos: maximizar TPH, maximizar P(safe), maximizar inventario final.
Dominancia O(N^2) sobre N<=100 configuraciones.
Las configuraciones Pareto-optimas reciben badge "Pareto" en la tabla Top-5.

## 6. Modos del Optimizador

| Boton           | Modo        | Logica de seleccion                              |
|-----------------|-------------|--------------------------------------------------|
| Mejor Config    | balanced    | max score multicriterio                          |
| Max Produccion  | max_prod    | max TPH (riesgo ignorado)                        |
| Op. Segura      | safe        | filtra P(safe)>=0.95, max TPH; fallback: mayor P |
| Balance Optimo  | pareto      | top del frente Pareto                            |
| Reset           | --          | carga estado PI en tiempo real                   |

## 7. Preguntas de Validacion

Q1: Por que SAG1 siempre era sin_bola?
A: Penalizacion dura (deficit*2000) aplastaba el score cuando autonomia < 1.5h. SAG1
   con bolas a cualquier rate razonable y pila < 50% tiene autonomia < 1.5h. Corregido
   con componente suave 10% en multicriterio.

Q2: Son validos los DELTA_TPH calibrados?
A: Los datos muestran que los operadores NUNCA apagan las bolas (n0 ~0 para SAG2, n0=11
   para SAG1). Sin grupo de control valido (MIN_N0=200), el modelo de ingenieria legacy
   BOLA_BONUS=0.08 es el mejor estimado disponible. Los deltas historicos por OLS tienen
   sesgo de seleccion severo (se activan bolas cuando produccion ya es alta).

Q3: Cuantas simulaciones hace el MC?
A: Variable: entre 30 y 500. Para condiciones tipicas converge en 50-80 sims por config,
   evaluando 20 configs = 1000-1600 simulaciones totales por click.

Q4: Que pasa en modo Operacion Segura si ninguna config cumple P(safe)>=0.95?
A: El fallback retorna la configuracion con mayor P(safe) disponible. No crashea.

Q5: Los graficos nuevos que muestran?
A: Pareto scatter (TPH vs P(crisis), color=inventario): permite ver la frontera
   eficiente. Impacto bolas (3 subplots: DELTA_TPH, DELTA_Autonomia, DELTA_Inventario):
   cuantifica el trade-off de activar bolas para cada SAG.

## 8. Archivos Nuevos / Modificados

  02_Analytics/Scripts/calibrar_bola_delta_tph.py  [NUEVO]
  01_Data/Cache/bola_delta_tph.json               [GENERADO]
  02_Analytics/Figures/12_Optimizer_v2/            [DIRECTORIO NUEVO]
  05_Dashboard/engine/ode_model.py                 [MODIFICADO -- effective_rate aditivo]
  05_Dashboard/engine/optimizer_v2.py              [NUEVO -- 340 lineas]
  05_Dashboard/components/graphs.py                [MODIFICADO -- +2 funciones]
  05_Dashboard/components/cards.py                 [MODIFICADO -- +make_top5_card]
  05_Dashboard/components/controls.py              [MODIFICADO -- rm ctrl-mc-n]
  05_Dashboard/app.py                              [MODIFICADO -- +4 callbacks, +5 botones]
"""
    return lines


# ---- Main -------------------------------------------------------------------

def main() -> None:
    cal = _load_calibration()

    # --- Markdown ---
    md_text = build_md(cal)
    MD_PATH.write_text(md_text, encoding="utf-8")
    print(f"[OK] MD generado: {MD_PATH}")

    # --- PDF ---
    sections = split_markdown_sections(md_text)

    with PdfPages(str(PDF_PATH)) as pdf:
        # Portada
        fig = plt.figure(figsize=(8.27, 11.69))
        ax  = fig.add_axes([0.1, 0.3, 0.8, 0.6])
        ax.axis("off")
        ax.text(0.5, 0.95, "Optimizer v2",
                fontsize=28, fontweight="bold", ha="center", va="top",
                color="#1F3864")
        ax.text(0.5, 0.82, "Diseno Tecnico y Validacion",
                fontsize=16, ha="center", va="top", color="#555")
        ax.text(0.5, 0.72, "Codelco Division El Teniente",
                fontsize=13, ha="center", va="top", color="#777")
        ax.text(0.5, 0.62, "2026-07-01",
                fontsize=13, ha="center", va="top", color="#777")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Secciones de texto
        for title, lines in sections:
            add_text_page(pdf, title, lines)

        # Figuras de calibracion
        for fname in sorted(FIGURES.glob("*.png")):
            add_image_page(pdf, fname, fname.stem.replace("_", " ").title())

        # Metadata
        d = pdf.infodict()
        d["Title"]   = "Optimizer v2 — Diseno Tecnico"
        d["Author"]  = "Juan Orellana / AA_CIO_DET"
        d["Subject"] = "Optimizador multicriterio molienda SAG"

    print(f"[OK] PDF generado: {PDF_PATH}")


if __name__ == "__main__":
    main()
