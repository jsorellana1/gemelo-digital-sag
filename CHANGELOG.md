# Changelog — Rendimientos Molienda / Gemelo Digital

Registra hitos por evolución conceptual del proyecto (no versionado
semántico estricto — el historial de commits de git es la fuente de verdad
para el detalle línea a línea).

---

## v8 — Roadmap de cierre, autonomía dinámica y diagnóstico de fidelidad histórica (2026-07-14 → 2026-07-15)

Rama `feature/gemelo-v1-2-0-optimizacion-motor-evidencia`. Sin número de
versión formal asignado todavía (decisión de release pendiente) — esta
entrada documenta el trabajo conceptual, el detalle línea a línea está en
el historial de git desde `73b7128` en adelante.

- **Reencuadre semántico de autonomía (Etapa 1-2):** separación explícita
  entre autonomía dinámica actual (balance neto de la trayectoria
  simulada) y vulnerabilidad histórica preventiva (percentil calibrado) —
  antes mezcladas bajo una sola etiqueta ambigua. Propagado de forma
  aditiva a `risk_engine.py` (sub-scores), `bottleneck.py` (categorías),
  `quick_wins.py` (deltas explícitos), `hourly_plan.py` (estado dinámico
  por hora), y migración parcial de `rules_engine.py::recommend_action`
  vía `AutonomyContext`.
- **Roadmap maestro de cierre** (`04_Reports/Technical/
  20260715_Roadmap_Cierre_Simulador_Operacional.md`): 9 fases con panel
  de avance, matriz de bloqueos y condiciones de cierre explícitas,
  derivado de evidencia real del repositorio (no genérico). Usado como
  plan de trabajo vivo durante toda esta serie de sesiones.
- **Optimizer V2 — dual score:** `compute_dual_score`/`compare_rankings`
  (grid determinístico) y extensión a Monte Carlo (`p_dynamic_safe`,
  `pct_draining_sagX`/`pct_at_critical_sagX`) — señal de seguridad
  dinámica complementaria a `p_safe`, puramente aditiva (no cambia la
  selección real del optimizador).
- **P0 de fidelidad histórica descubierto y diagnosticado a fondo (Fase
  4B):** el motor físico no pasaba su propia tolerancia declarada
  (5pp de MAE) en 4 de 5 regímenes de backtesting. Investigación causal
  extensa (`Diagnostico_Causa_Deriva_Temporal_PAM.md`,
  `20260715_Diagnostico_Fidelidad_Historica.md`): descarta hipótesis de
  factor fijo mal aplicado; confirma que `_pile_feedback_factor` mitiga
  parte del sesgo (debilitarlo empeora el hold-out); descubre que el
  hold-out histórico usado hasta ahora estaba 100% contaminado por
  solape con las ventanas de calibración; encuentra la causa raíz más
  probable — el sensor `correa_315` roto desde 2026-04-30 (confirmado
  cruzando PAM Mantto real y, después, exports directos del PI System) —
  y que el 68% de los eventos de *calibración* de `t8_corta` tenían SAG1
  apagado, inflando artificialmente el MAE de calibración reportado.
  Reconstrucción estadística de `correa_315` (R²=0.127, diagnóstica, no
  sustituto del sensor real) deja la calibración de `p_safe`
  prácticamente resuelta (Brier hold-out 0.621→0.004); la fidelidad de
  pila mejora sustancialmente pero sigue sobre tolerancia — bloqueado en
  obtener la serie real corregida desde Instrumentación.
- **Motor multicelda SAG1/SAG2 (I+D, no productivo):** representación
  opcional por celdas locales de cada pila (`engine/multicell/`,
  `engine/stockpile_multicell.py`), feature-flagged y apagado por
  defecto — el motor agregado sigue siendo la única ruta productiva.
  Investigación con hold-out temporal real concluye que SAG1 (lineal)
  degrada la fidelidad y SAG2 (radial) mejora parcial e
  inconsistentemente; decisión explícita de no migrar, mantener como
  línea de I+D focalizada en SAG2.
- **Limpieza (Fase 7):** 9 candidatos de código muerto resueltos (4
  eliminados, 4 falsos positivos de MCP descartados con evidencia
  directa de `Grep`, 1 genuino fuera del alcance del simulador);
  funciones de recomendación en estado sombra resueltas (2 eliminadas,
  `rank_candidates` confirmada activa); constantes duplicadas
  centralizadas (`components/cards.py` importa de `engine/ode_model.py`
  en vez de mantener una copia literal).
- **Validación con escenarios dorados:** `recommend_action` pasa 4/5
  escenarios canónicos; gap real confirmado (SAG apagado + pila subiendo
  hacia el límite no escala la acción) documentado como `xfail(strict=
  True)`, pendiente de decisión de producto sobre la acción/mensaje
  correcto.
- Suite de tests creció de 367 a 430 (1 xfailed documentado) a lo largo
  de esta serie de sesiones, sin regresiones.

## v7 — Reenfoque autonomía/armonía + pipeline de release (2026-07-09 → 2026-07-12)

Ver `05_Dashboard/packaging/VERSION.txt` (v1.2.0 y v1.3.0) para el
detalle completo — resumen aquí para que el changelog raíz no quede
desincronizado del empaquetado real:

- **v1.2.0:** optimización medida (no estimada) del loop caliente del
  ODE (`-36%` en cache-miss, elimina un `dir()` innecesario), normalización
  de claves de cache para evitar invalidación por ruido de sliders
  continuos, y una serie de módulos de motor "basados en evidencia"
  (`bottleneck.py`, `optimizer_v4.py`, `simulation_router.py` y
  estrategias asociadas, `historical_backtesting.py`, `turno_planner.py`,
  entre otros) más nueva página `/performance`.
- **v1.3.0:** reenfoque del simulador hacia supervivencia/autonomía
  (`optimizer_v5.py`, score multiobjetivo con 3 perfiles), Índice de
  Armonía Operacional (`harmony_index.py`), métricas de variabilidad TPH
  y penalización de transitorios, plan operacional por hora, fix de
  performance en `regime_event_detector.py` (~22s → ~0.4s), y pipeline de
  release en un clic (`release_portable.bat` + manifiesto trazable).

---

## v6 — Dashboard Operacional / Gemelo Digital (2026-06 → 2026-07)

- Simulador operacional con recomendación automática (Optimizer V3) y
  Monte Carlo bajo demanda.
- Página "¿Qué pasa si...?" con comparador de 3 escenarios (Configurado /
  Conservador / Máx Producción).
- Extracción de la página simulador a `05_Dashboard/pages/simulador_operacional.py`
  (antes monolítico en `app.py`).
- Turnos (C/A/B) y eje "hora del día" real en los gráficos del simulador.
- Mantenciones programables por equipo (SAG1/SAG2/411/412/511/512, luego
  extendido a CH1/CH2/CV315/CV316/T1/T3) como restricción dura del
  optimizador — patrón: equipo en mantención al inicio del horizonte queda
  forzado OFF para toda la corrida.
- Gantt "Estado Operacional por Hora" (ON/OFF/MANTTO, 12 equipos).
- **Regla R16** (al menos 1 molino de bolas activo por SAG): filtro duro en
  el optimizador, detección de conflictos de planificación (ambos molinos
  de un SAG en mantención simultánea), advertencia en UI manual, indicador
  en `/riesgo`. Validada contra `01_Data/Raw/estados_activos.xlsx`
  (216/93601 registros en violación real en SAG1, 9/93601 en SAG2 — <0.3%
  del tiempo operado, sin patrón sistemático).
- **Centro de Control Operacional**: fix del bug de "gráfico congelado"
  (causa raíz: `run_monte_carlo` tenía los parámetros de escenario como
  `State` en vez de `Input`); fan chart de confianza por SAG reemplazando
  el frontier plot estadístico; tarjeta "¿por qué confiar?"; gráfico de
  riesgo por hora (P(vaciado)/P(overflow) desde trayectorias Monte Carlo
  reales); semáforo "Estado del Escenario"; retitulado narrativo de
  gráficos como preguntas operacionales.
- **Empaquetado portable `.exe`** (2026-07-02 → 2026-07-06): PyInstaller
  `--onedir` (reemplaza `--onefile`, apertura ~2-13s vs. descompresión en
  cada uso); cache por escenario (`engine/scenario_cache.py`); límite de
  tiempo seguro en Monte Carlo (`MC_MAX_SECONDS`); reversión a gating por
  botón para Monte Carlo/optimizador + selector Modo Rápido/Avanzado;
  banner de versión/estado QA en la app; 43 tests unitarios
  (`05_Dashboard/tests/`); bug corregido de mantención de día completo
  `[0,24]` ignorada silenciosamente (`engine/scheduler.py`). Versiones
  v1.1.0 → v1.1.2. `05_Dashboard/` establecido como única fuente de verdad
  del portable — documentos de entrega en `05_Dashboard/packaging/`, build
  oficial en `05_Dashboard/scripts/build_portable.py`. Ver
  `04_Reports/Technical/2026070*_*.md`.
- **T3 en TPH** (2026-07-06): el desvío hacia T3 se muestra siempre en TPH
  (nunca %) en tarjetas, gráficos y documentación — nueva pestaña "Balance
  T1/T3" (T1, CV315, CV316, T3); alerta explícita cuando CV315+CV316 supera
  T1 disponible; invariante `T1 = CV315 + CV316 + T3` cubierto por
  `test_t3_tph_balance.py`.

## v5 — Optimizer V3 (2026-06)

- Grilla determinística anclada a percentiles históricos (P50/P75/P90/MAX)
  por régimen operacional (normal / T8 corta / T8 larga).
- Monte Carlo adaptativo con parada por convergencia (`adaptive_mc_eval`).
- Frente de Pareto (TPH, P(seguro), inventario) y KPIs de validación
  (brecha vs P90 histórico, ROI de activar bolas).

## v4 — Monte Carlo / Metropolis-Hastings (2026-06)

- Calibración bayesiana de la probabilidad de sobrevivir una ventana T8
  dado pila inicial y duración (Metropolis-Hastings).
- Primeras corridas Monte Carlo sobre el simulador ODE con incertidumbre en
  pila, feed y duración T8.
- Ver `04_Reports/Technical/20260630_Metropolis_Hastings_Ejecutivo.md` y
  `20260630_Metropolis_Hastings_Evaluacion.md`.

## v3 — Modelo causal / Ecuaciones diferenciales (2026-05 → 2026-06)

- Modelo causal basado en inventario de pilas (relación entre nivel de pila
  y decisión/disponibilidad operacional).
- Simulador ODE de dinámica de pilas (balance de masa, `ode_model.py`).
- Motor de reglas operacionales (`rules_engine.py`) — reglas R01-R09.

## v2 — Efecto Gaviota (2026-04 → 2026-05)

- Cuantificación de la caída y recuperación de TPH pre/post ventana T8 por
  activo (SAG1, SAG2, PMC, MUN/UNITARIO).
- Detección de change points estructurales, análisis de sensibilidad por
  duración de ventana.

## v1 — Análisis de rendimientos (2026-04)

- KPIs operacionales base, EDA, ingestión de PAM Producción/Mantto y
  rendimientos 5-min.
- Primeros modelos: Isolation Forest (anomalías), KMeans (regímenes),
  XGBoost (forecast TPH), SHAP (explicabilidad), inferencia bayesiana
  conjugada (P(caída\|T8)), índice compuesto IGI T8.
