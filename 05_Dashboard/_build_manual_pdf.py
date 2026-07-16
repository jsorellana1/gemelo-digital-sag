"""
_build_manual_pdf.py — Genera PDF desde Markdown usando reportlab (ya
instalado, sin nueva dependencia de runtime). Script de build, no se
distribuye con el .exe.

Uso:
    python 05_Dashboard/_build_manual_pdf.py
        -> packaging/README_USUARIO.md -> packaging/README_USUARIO.pdf (default)
    python 05_Dashboard/_build_manual_pdf.py <src.md> <dst.pdf>
        -> convierte cualquier par markdown/pdf con el mismo estilo

Fuente unica de verdad (2026-07-06): todos los documentos de empaquetado
(README_USUARIO, GUIA_RAPIDA_VALIDACION, FORMULARIO_FEEDBACK_VALIDACION,
VERSION.txt, QA_CHECKLIST.md) viven en 05_Dashboard/packaging/ — NUNCA
editar las copias dentro de dist/Gemelo_Digital_Molienda/, se pierden en
cada rebuild. Ver 05_Dashboard/scripts/build_portable.py.
"""
import os
import re
import sys

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_PACKAGING = os.path.join(_HERE, "packaging")

AZUL = "#1F3864"


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)
    return text


def build(src: str | None = None, dst: str | None = None):
    SRC = src or os.path.join(_PACKAGING, "README_USUARIO.md")
    DST = dst or os.path.join(_PACKAGING, "README_USUARIO.pdf")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=AZUL, spaceAfter=6, alignment=TA_CENTER)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=AZUL, spaceBefore=14, spaceAfter=6)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], textColor=AZUL, spaceBefore=10, spaceAfter=4)
    sub = ParagraphStyle("Sub", parent=styles["Normal"], alignment=TA_CENTER, textColor="#555555", spaceAfter=14)
    body = ParagraphStyle("Body", parent=styles["Normal"], spaceAfter=8, leading=15)

    story = []
    with open(SRC, encoding="utf-8") as f:
        lines = f.read().splitlines()

    list_buffer = []

    def flush_list():
        nonlocal list_buffer
        if list_buffer:
            story.append(ListFlowable(
                [ListItem(Paragraph(_inline(li), body)) for li in list_buffer],
                bulletType="bullet",
            ))
            story.append(Spacer(1, 6))
            list_buffer = []

    for raw in lines:
        line = raw.rstrip()
        if not line or line == "---":
            flush_list()
            continue
        if line.startswith("# "):
            flush_list()
            story.append(Paragraph(_inline(line[2:]), h1))
        elif line.startswith("## "):
            flush_list()
            story.append(Paragraph(_inline(line[3:]), h2))
        elif line.startswith("### "):
            flush_list()
            story.append(Paragraph(_inline(line[4:]), h3))
        elif line.startswith("*") and line.endswith("*") and not line.startswith("- "):
            flush_list()
            story.append(Paragraph(_inline(line.strip("*")), sub))
        elif line.startswith("- "):
            list_buffer.append(line[2:])
        else:
            flush_list()
            story.append(Paragraph(_inline(line), body))
    flush_list()

    doc = SimpleDocTemplate(DST, pagesize=LETTER,
                             topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=2.2*cm, rightMargin=2.2*cm)
    doc.build(story)
    print(f"PDF generado: {DST}")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        build(sys.argv[1], sys.argv[2])
    else:
        build()
