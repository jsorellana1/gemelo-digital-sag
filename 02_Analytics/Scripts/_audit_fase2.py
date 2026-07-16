import json, sys
from datetime import datetime
from pathlib import Path

BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
LOGS  = BASE / "logs"

skills = ["skill_molienda_sag.md","skill_series_temporales_industriales.md",
          "skill_machine_learning_operacional.md","skill_estadistica_bayesiana_avanzada.md",
          "skill_process_mining_industrial.md","skill_explainable_ai_governance.md"]

print("=== SKILL AUDIT — Fase 2 Mecanismo Causal ===")
for sk in skills:
    p = BASE / "Skills" / sk
    print(f"  {'OK' if p.exists() else 'NO'} {sk}")

libs_check = ["sklearn","xgboost","shap","scipy","statsmodels"]
print("\n=== LIBRERIAS ML ===")
avail = []
for lib in libs_check:
    try:
        m = __import__(lib)
        ver = getattr(m, "__version__", "?")
        print(f"  OK  {lib} {ver}")
        avail.append(lib)
    except ImportError:
        print(f"  NO  {lib}")

print("\n=== DATOS DISPONIBLES ===")
for f in ["data/intermediate/rendimientos_clean.parquet",
          "data/intermediate/eventos_t8.parquet",
          "outputs/excel/event_study_t8.xlsx"]:
    p = BASE / f
    print(f"  {'OK' if p.exists() else 'FALTA'} {f}")

with open(LOGS / "skill_audit.log", "a", encoding="utf-8") as lf:
    lf.write(json.dumps({"fecha": datetime.now().isoformat(),
                         "script": "src/fase2_mecanismo_causal.py",
                         "skills": skills, "libs": avail}, ensure_ascii=False) + "\n")
print("\nRegistrado en skill_audit.log")
