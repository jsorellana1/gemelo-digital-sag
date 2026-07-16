"""
generar_reporte_casos.py — Repositorio de casos reales (Fase 5, cierre
de brechas "Validacion Operacional Real", 2026-07-07).

Ejecucion MANUAL (no un callback en vivo): lee
01_Data/Operational_Decisions/decisions_log.csv +
runtime_data/operational_cases/*.json y escribe un .md por caso en
04_Reports/Operational_Cases/{regimen}/{case_id}.md.

Situacion/recomendacion salen de datos reales (el snapshot guardado).
Decision real/resultado real salen de decisions_log.csv SI YA existen
(pueden estar vacios — no se fabrica un seguimiento que nadie registro
todavia). "Aprendizaje" queda como placeholder para completar a mano:
sintetizar un aprendizaje es un juicio humano, no algo que este script
deba inventar.

Uso:
    python scripts/generar_reporte_casos.py
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASHBOARD_ROOT = os.path.dirname(_HERE)
_PROJECT_ROOT = os.path.dirname(_DASHBOARD_ROOT)
sys.path.insert(0, _DASHBOARD_ROOT)

from utils.operational_case_logger import list_operational_cases  # noqa: E402
from utils.decisions_log import read_decisions  # noqa: E402

_OUT_DIR = os.path.join(_PROJECT_ROOT, "04_Reports", "Operational_Cases")


def _render_caso_md(caso: dict, decision_row: dict | None) -> str:
    regimen = caso.get("regimen", "desconocido")
    case_id = caso.get("case_id", "sin_id")
    fecha = caso.get("_timestamp_str", "")

    lines = [
        f"# Caso {case_id} — {regimen}",
        "",
        f"**Fecha:** {fecha}",
        "",
        "## Situación",
        "",
        f"- Régimen: {regimen}",
        f"- Pila SAG1: {caso.get('pila_sag1_pct', '—')}% · Pila SAG2: {caso.get('pila_sag2_pct', '—')}%",
        f"- TPH SAG1: {caso.get('tph_sag1', '—')} · TPH SAG2: {caso.get('tph_sag2', '—')}",
        f"- T1: {caso.get('t1_tph', '—')} TPH · CV315: {caso.get('cv315_tph', '—')} TPH · "
        f"CV316: {caso.get('cv316_tph', '—')} TPH · T3: {caso.get('t3_tph', '—')} TPH",
        f"- T8: {caso.get('duracion_t8_h', 0)}h · Turno: {caso.get('turno', '—')}",
        f"- Mantenciones activas: {caso.get('mantenciones') or 'ninguna'}",
        "",
        "## Recomendación",
        "",
        caso.get("recomendacion", "(sin explicación registrada)"),
        "",
        "## Decisión real",
        "",
        (decision_row or {}).get("accion_tomada") or "*(pendiente — sin seguimiento registrado todavía)*",
        "",
        "## Resultado real",
        "",
        (decision_row or {}).get("resultado_observado") or "*(pendiente — sin seguimiento registrado todavía)*",
        "",
        "## Aprendizaje",
        "",
        "<!-- completar manualmente -->",
        "",
    ]
    return "\n".join(lines)


def generar_reporte():
    casos = list_operational_cases()
    if not casos:
        print("No hay casos guardados en runtime_data/operational_cases/ todavía — nada que reportar.")
        return

    decisiones = read_decisions()
    decisiones_por_case_id = {row["case_id"]: row for row in decisiones.to_dict("records")} if not decisiones.empty else {}

    n_escritos = 0
    for caso in casos:
        regimen = caso.get("regimen", "desconocido") or "desconocido"
        case_id = caso.get("case_id", "sin_id")
        dest_dir = os.path.join(_OUT_DIR, regimen)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, f"{case_id}.md")
        contenido = _render_caso_md(caso, decisiones_por_case_id.get(case_id))
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(contenido)
        n_escritos += 1

    print(f"{n_escritos} casos escritos en {_OUT_DIR}")


if __name__ == "__main__":
    generar_reporte()
