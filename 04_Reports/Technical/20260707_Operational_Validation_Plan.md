# Plan de Validación Operacional — Gemelo Digital Molienda SAG T8

**Fecha:** 2026-07-07
**Contexto:** el router v2 y sus 137/138 tests ya prueban que el simulador
es **técnicamente** correcto. Esta fase pasa a la pregunta central:
¿cuánto valor operacional genera realmente? Se construyó la
infraestructura de **captura** necesaria para responder esa pregunta con
datos reales; las fases de **análisis** que consumen esos datos quedan
documentadas como roadmap, no como código — construirlas hoy sin datos
acumulados significaría stubs vacíos o números fabricados, algo evitado
consistentemente en todo este proyecto (ver `historical_backtesting.py`:
nunca se ajustó una tolerancia para "hacer pasar" un resultado).

---

## Fases construidas esta sesión (captura)

| Fase | Qué se construyó | Dónde |
|---|---|---|
| 1 — Telemetría real | `usuario`, `tiempo_total_seg` agregados a los eventos ya existentes (`simulacion_disparada`, `recomendacion_generada`, que YA estaban wireados de una sesión anterior); evento nuevo `recomendacion_feedback` con `rec_id` para enlazar cada recomendación con su aceptación SI/NO/PARCIAL/NO REGISTRADA | `utils/usage_logger.py`, `pages/simulador_operacional.py` |
| 2 — Modo validación | Checkbox "Validar escenario real"; al marcarlo, guarda snapshot completo (pilas, TPH, T1, CV315, CV316, T3, T8, mantenciones, recomendación) como caso nuevo (nunca sobreescribe) | `utils/operational_case_logger.py`, `components/controls.py::build_feedback_panel` |
| 3 — Dataset de decisiones | Una fila por caso guardado, con `accion_tomada`/`resultado_observado` vacíos hasta que exista seguimiento real | `utils/decisions_log.py` → `01_Data/Operational_Decisions/decisions_log.csv` |
| 5 — Repositorio de casos | Script de ejecución manual que arma un `.md` por caso, con "Aprendizaje" como placeholder para completar a mano (no se sintetiza un aprendizaje que nadie escribió) | `scripts/generar_reporte_casos.py` → `04_Reports/Operational_Cases/{regimen}/{case_id}.md` |
| 8 (parcial) — Dashboard de desempeño | Página nueva `/desempeno_gemelo`: Uso y Adopción reales desde hoy; Calidad reusa `run_backtest`/`run_backtest_proxy` (ya construidos, sin tocar); Valor operacional se muestra explícitamente como pendiente | `app.py::page_desempeno_gemelo` |
| 10 — Validación jefe de sala | Formulario 1-5 (¿fue útil? ¿razonable? ¿decisión distinta?) + comentario, en el mismo panel que el checkbox y el feedback SI/NO/PARCIAL — un solo panel, no tres separados | `validation/feedback_form.py`, `components/controls.py::build_feedback_panel` |

---

## Fases dejadas como roadmap (análisis — requieren datos acumulados)

| Fase | Por qué no se construye todavía | Criterio de activación |
|---|---|---|
| 4 — Score de Valor Operacional (`engine/value_tracking.py`) | Producción recuperada, riesgo evitado y aporte a PAM solo se pueden calcular comparando recomendación vs. resultado real — hoy `resultado_observado` está vacío en todas las filas | N≥30 casos en `decisions_log.csv` con `resultado_observado` no vacío |
| 6 — Calibración automática (`engine/calibration_engine.py`) | Comparar simulación vs. realidad mensualmente requiere al menos 1 mes de decisiones reales acumuladas | ≥1 mes calendario de datos en `Operational_Decisions/` |
| 7 — Confianza operacional real | Hoy la confianza (Alta/Media/Baja) se basa en backtesting histórico general, no en "casos similares + éxito de recomendaciones" — eso requiere suficiente densidad de casos por régimen | N≥15 casos por régimen con feedback (`recomendacion_aceptada` ≠ NO REGISTRADA) |
| 9 — Detector de casos nuevos (`engine/novelty_detector.py`) | Necesita una distribución histórica de escenarios "normales" contra la cual comparar — los `operational_cases/` de hoy no alcanzan una base representativa | N≥100 casos guardados, cubriendo los 6 regímenes |
| PDF ejecutivo `04_Reports/Executive/YYYYMMDD_Valor_Operacional_Gemelo.pdf` | No hay datos de valor real que reportar todavía (depende de Fase 4) | Cuando Fase 4 tenga insumos reales |

**No se ajustó ningún umbral de estas fases para que "pareciera avanzado"
antes de tiempo** — los números de N mínimo son de referencia inicial,
ajustables cuando haya evidencia de cuánta densidad de datos hace falta
para que cada análisis tenga sentido estadístico.

---

## Verificación

- Suite completa: `pytest 05_Dashboard/tests -q` — 137/138 (baseline sin
  regresión; el 1 fallo es el flake de timing preexistente, documentado
  en sesiones anteriores).
- `app.py` importa limpio; `/riesgo` y `/desempeno_gemelo` responden 200;
  `page_desempeno_gemelo()` se probó llamándola directamente (sin
  navegador disponible por el proxy corporativo) y renderiza sin
  excepciones, incluyendo la tabla de calidad con backtesting real de
  los 6 regímenes.
- Módulos nuevos (`operational_case_logger`, `decisions_log`,
  `feedback_form`, `usage_logger.adopcion_global`) probados end-to-end
  manualmente: guardar caso → aparece en `list_operational_cases()` →
  fila en `decisions_log.csv` → seguimiento posterior via
  `update_decision_followup()` → reporte via `generar_reporte_casos.py`.
- Bug real encontrado y corregido durante esta verificación: pandas
  3.0+ lanza `TypeError` al asignar texto en una columna que arrancó
  como `float64` (todas las filas vacías) — `decisions_log.py` ahora
  lee con `dtype=str` explícito. Documentado en `feedback_technical.md`.
