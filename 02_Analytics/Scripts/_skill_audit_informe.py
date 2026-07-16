import os, json
from datetime import datetime
from pathlib import Path

BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
skills_dir = BASE / "Skills"
log_path   = BASE / "logs" / "skill_audit.log"

skills_relevant = [
    "skill_molienda_sag.md",
    "skill_product_owner_analitica_minera.md",
    "skill_ux_ui_cio_operations_center.md",
    "skill_series_temporales_industriales.md",
    "skill_operaciones_mina_subterranea.md",
]

entry = {
    "fecha": datetime.now().isoformat(),
    "script": "src/generar_informe_pdf.py",
    "skills_revisados": skills_relevant,
    "accion": "generacion_informe_PDF_comite_T8",
}

print("=== SKILL AUDIT — Generacion Informe PDF ===")
for sk in skills_relevant:
    p = skills_dir / sk
    exists = p.exists()
    print(f"  {'OK' if exists else 'FALTA'} {sk}")
    if exists:
        # Leer primeras 2 lineas del skill
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[:2]
        print(f"     -> {' | '.join(lines[:2])}")

with open(log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("\nRegistrado en skill_audit.log")

# Figuras a incluir
print("\n=== FIGURAS SELECCIONADAS PARA EL INFORME ===")
figures_plan = [
    ("event_study/09_Efecto_Gaviota_Global.png",    "Hallazgo 1 — Efecto gaviota global"),
    ("event_study/05_EventStudy_2h.png",             "Hallazgo 2a — Duración 2h"),
    ("event_study/06_EventStudy_4h.png",             "Hallazgo 2b — Duración 4h"),
    ("event_study/07_EventStudy_8h.png",             "Hallazgo 2c — Duración 8h"),
    ("event_study/08_EventStudy_12h.png",            "Hallazgo 2d — Duración 12h"),
    ("event_study/10_Comparacion_Activos.png",       "Hallazgo 3 — Comparacion activos"),
    ("prescriptivo/P1_IVO_Resiliencia.png",          "Hallazgo 4 — Ranking IVO/Resiliencia"),
    ("event_study/11_Tiempo_Recuperacion.png",       "Hallazgo 5 — Tiempo recuperacion"),
    ("prescriptivo/P2_Toneladas_Perdidas.png",       "Impacto — Toneladas perdidas"),
    ("prescriptivo/P3_Curvas_Estrategicas.png",      "Impacto — Curvas estrategicas"),
    ("prescriptivo/P5_Escenarios.png",               "Oportunidades — Escenarios"),
    ("prescriptivo/P8_Panel_Ejecutivo.png",          "Anexo — Panel ejecutivo"),
]
figs_dir = BASE / "outputs" / "figures"
for fname, desc in figures_plan:
    ok = (figs_dir / fname).exists()
    print(f"  {'OK' if ok else 'FALTA'} {fname:55} | {desc}")
