# Skill: Product Owner de Analítica Avanzada — FRAG SAG

## Propósito

Guiar decisiones de priorización, alcance y validación de producto para el pipeline analítico
FRAG SAG, balanceando valor operacional inmediato con calidad técnica sostenible.

---

# Principios

## Regla 1 — Valor operacional primero

Una mejora que reduce el tiempo de análisis semanal del supervisor HSEC es más valiosa
que una mejora técnica que solo el equipo de datos nota.

Antes de implementar: preguntar `¿qué decisión operacional mejora este cambio?`

## Regla 2 — El formato actual es contrato con el usuario

Los supervisores e inspectores ya saben leer el Excel y PDF actuales.
Cambios de formato requieren capacitación, que tiene costo real.
Solo cambiar formato si el beneficio es claramente mayor al costo de adaptación.

## Regla 3 — Priorizar por impacto × esfuerzo, no por interés técnico

| Cuadrante | Acción |
|-----------|--------|
| Alto impacto + bajo esfuerzo (Quick Win) | Hacer esta semana |
| Alto impacto + alto esfuerzo (Corto/Mediano plazo) | Planificar con hitos |
| Bajo impacto + bajo esfuerzo | Backlog con baja prioridad |
| Bajo impacto + alto esfuerzo | Descartar |

## Regla 4 — Métricas de producto, no de código

El éxito del pipeline FRAG SAG se mide con:
- ¿El supervisor recibió el informe a tiempo? (entrega oportuna)
- ¿El FRAG predijo correctamente la dirección de riesgo? (calibración)
- ¿Los RC priorizados coincidieron con los eventos de la semana? (precisión rondas)
- ¿Cuántos "SIN RC" se lograron inferir con alta confianza? (cobertura clasificador)

## Regla 5 — Deuda técnica visible en el roadmap

Cada deuda técnica identificada tiene un ID (QW-*, CP-*, MP-*) en el roadmap.
No resolver deuda técnica implícitamente — declararla y priorizarla explícitamente.

---

# Roadmap Vigente — FRAG SAG v2

## Quick Wins (< 1 semana c/u)

| ID | Descripción | Estado |
|----|-------------|--------|
| QW-1 | PermissionError PDF → fallback timestamp | Completado |
| QW-2 | frag_history.csv fuera de Git (.gitignore) | Completado |
| QW-3 | Anomaly detector umbral 8→4 semanas | Completado |
| QW-4 | Corpus RC suplementario AT inferencer | Completado |
| QW-5 | Reliability diagram hoja Performance | Completado |
| QW-6 | Test fallback PermissionError PDF | Completado |
| QW-7 | Prompt caching Anthropic | Completado |
| QW-8 | Actualizar 4 skills incompletos | En progreso |
| QW-9 | Nuevo skill: forecasting industrial | Pendiente |
| QW-10 | Nuevo skill: data quality governance | Pendiente |

## Corto Plazo (1-4 semanas)

| ID | Descripción | Beneficio esperado |
|----|-------------|-------------------|
| CP-1 | Pandera schema validation DataFrames entrada | Errores claros cuando datos malformados |
| CP-2 | frag_history → SQLite (fuera de Git) | Historial acumulable sin conflictos de merge |
| CP-3 | Hybrid BM25+vector search en RAG | Mayor precisión en recuperación de contexto HSEC |
| CP-4 | Cobertura tests >= 75% en CI | Detectar regresiones antes de producción |
| CP-5 | Structured outputs JSON en LLM | Eliminar hallucination_cleaner.py, más confiable |
| CP-6 | Streaming en LLM largas (1914 tokens) | Sin timeout en análisis histórico |
| CP-7 | Snapshot tests estructura Excel 7 hojas | Detectar regresión en formato antes de entregar |

## Mediano Plazo (1-3 meses)

| ID | Descripción | Condición de entrada |
|----|-------------|---------------------|
| MP-1 | MLE fitting parámetros Hawkes | Requiere >= 12 semanas de historial |
| MP-3 | SHAP values por RC-semana en Excel | Requiere sklearn + SHAP instalados en prod |
| MP-4 | Cache semántico LLM | Requiere CP-5 completado |
| MP-6 | Seasonal baseline FRAG por semana del año | Requiere >= 52 semanas de historial |

---

# Stakeholders y Canales

| Stakeholder | Necesidad principal | Entregable FRAG |
|-------------|--------------------|----|
| Supervisor HSEC planta SAG | RC prioritarios esta semana | PDF Sec 7 — Plan rondas |
| Gerencia HSEC | Tendencia del riesgo, alertas | PDF Sec 2 + Excel FRAG_Semana |
| CIO/Analytics | Calidad del modelo, estabilidad | Excel Performance_Modelo |
| Mantenimiento | Actividades programadas vs riesgo | Excel MIPER + PDF Sec 6 |
| Seguridad operacional | RC inferidos, cobertura AT | Excel Inferencia_RC |

---

# Criterios de Aceptación — Ejemplos

## QW-4 (corpus RC suplementario)

- [ ] El inferencer clasifica al menos 7 RC distintos (antes: 5)
- [ ] F1-macro >= 0.60 en CV con corpus expandido
- [ ] El CSV de corpus está en `docs/references/` (versionado, no datos sensibles)
- [ ] Los logs indican "corpus suplementario cargado" con N ejemplos > 100

## CP-1 (Pandera schema)

- [ ] Si falta columna "Fecha" en AT → error claro con nombre de columna y hoja
- [ ] Si RC tiene formato inesperado → log warning pero pipeline continúa
- [ ] Los tests unitarios cubren columnas faltantes, tipos incorrectos, valores nulos

## CP-7 (Snapshot tests Excel)

- [ ] Test verifica que el workbook tiene exactamente 7 hojas
- [ ] Test verifica nombres de hojas (no orden, que puede cambiar)
- [ ] Test verifica que hoja Performance tiene secciones 1-9 (al menos N filas de contenido)

---

# Definition of Done — Pipeline FRAG SAG

Una feature está "done" cuando:
1. El código pasa `ruff check` sin errores
2. Los tests relevantes pasan (`pytest tests/ -k feature_name`)
3. El pipeline completo `main.py` ejecuta sin excepción con datos de prueba
4. El Excel y PDF generados tienen el formato esperado (verificación visual)
5. Los logs son informativos y no contienen Unicode problemático
6. El cambio no requiere modificar `.env` o credenciales hardcodeadas

---

# Anti-patrones de Gestión

- **No** comprometerse con fechas sin estimar el esfuerzo técnico primero
- **No** implementar una feature "mientras estamos" si no estaba en el roadmap
- **No** ignorar el feedback del usuario sobre legibilidad del reporte
- **No** asumir que CI verde = producto correcto (siempre verificar el PDF/Excel generado)
- **No** medir calidad del modelo solo con F1-macro — también verificar cobertura operacional
