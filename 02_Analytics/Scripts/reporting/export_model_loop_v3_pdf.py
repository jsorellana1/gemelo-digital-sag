from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
REPORTS = BASE / "outputs/reports"
FIGURES = BASE / "outputs/figures/model_loop_v3"
PDF_PATH = REPORTS / "model_loop_v3_report.pdf"


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
    ax = fig.add_axes([0.06, 0.05, 0.88, 0.90])
    ax.axis("off")
    ax.text(0.0, 1.0, title, fontsize=18, fontweight="bold", va="top")

    y = 0.95
    for line in lines:
        wrapped = textwrap.wrap(line, width=95) or [""]
        for part in wrapped:
            ax.text(0.0, y, part, fontsize=10.5, va="top", family="DejaVu Sans")
            y -= 0.027
            if y < 0.06:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
                fig = plt.figure(figsize=(8.27, 11.69))
                ax = fig.add_axes([0.06, 0.05, 0.88, 0.90])
                ax.axis("off")
                ax.text(0.0, 1.0, f"{title} (cont.)", fontsize=18, fontweight="bold", va="top")
                y = 0.95
        y -= 0.008

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def add_image_page(pdf: PdfPages, image_path: Path, title: str) -> None:
    img = mpimg.imread(image_path)
    fig = plt.figure(figsize=(8.27, 11.69))
    ax = fig.add_axes([0.05, 0.06, 0.90, 0.88])
    ax.axis("off")
    fig.suptitle(title, fontsize=16, fontweight="bold", y=0.97)
    ax.imshow(img)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    summary_md = (REPORTS / "model_loop_v3_summary.md").read_text(encoding="utf-8")
    explain_md = (REPORTS / "model_explainability_v3.md").read_text(encoding="utf-8")

    sections = split_markdown_sections(summary_md)
    explain_sections = split_markdown_sections(explain_md)

    figure_plan = [
        ("01_comparacion_modelos_v3.png", "Comparacion de Modelos v3"),
        ("02_walk_forward_performance.png", "Walk-Forward Performance"),
        ("03_real_vs_predicho_campeon.png", "Campeon: Real vs Predicho"),
        ("04_error_temporal_campeon.png", "Campeon: Error Temporal"),
        ("05_residuos_campeon.png", "Campeon: Residuos"),
        ("06_shap_summary_operacional.png", "SHAP Summary Operacional"),
        ("07_shap_bar_operacional.png", "SHAP Bar Operacional"),
        ("08_importancia_features_fisicas.png", "Importancia de Features Fisicas"),
        ("09_drift_vs_error.png", "Drift vs Error"),
        ("10_shap_dependence_pila.png", "Dependence SHAP: Pila"),
        ("11_shap_dependence_autonomia.png", "Dependence SHAP: Autonomia"),
        ("12_shap_dependence_t8.png", "Dependence SHAP: T8"),
    ]

    with PdfPages(PDF_PATH) as pdf:
        cover = plt.figure(figsize=(8.27, 11.69))
        ax = cover.add_axes([0.08, 0.08, 0.84, 0.84])
        ax.axis("off")
        ax.text(0.0, 0.92, "Model Loop v3", fontsize=28, fontweight="bold", va="top")
        ax.text(0.0, 0.84, "Reporte Ejecutivo y Tecnico", fontsize=18, va="top")
        ax.text(0.0, 0.76, "Division El Teniente - Codelco", fontsize=14, va="top")
        ax.text(
            0.0,
            0.62,
            "Contenido:\n- Auditoria del loop controlado\n- Ranking de modelos\n- Walk-forward validation\n- Drift y estabilidad\n- Explicabilidad SHAP top 3",
            fontsize=13,
            va="top",
            linespacing=1.5,
        )
        ax.text(0.0, 0.22, f"Origen: {REPORTS / 'model_loop_v3_summary.md'}", fontsize=10, va="top")
        pdf.savefig(cover, bbox_inches="tight")
        plt.close(cover)

        for title, lines in sections:
            add_text_page(pdf, title, lines)

        for title, lines in explain_sections:
            if title == "Resumen":
                continue
            add_text_page(pdf, f"Explicabilidad - {title}", lines)

        for filename, title in figure_plan:
            image_path = FIGURES / filename
            if image_path.exists():
                add_image_page(pdf, image_path, title)

    print(PDF_PATH)


if __name__ == "__main__":
    main()
