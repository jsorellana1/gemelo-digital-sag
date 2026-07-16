# Roadmap maestro de cierre — Simulador Operacional SAG

Fecha: 2026-07-15. Construido a partir del estado real del repositorio
(`git log`, `pytest`, `codebase-memory-mcp`, lectura directa), de las
auditorías ya realizadas y de las Etapas 1-2 de autonomía ya
implementadas. No es una lista genérica: cada afirmación de "completado"
o "pendiente" está respaldada por un archivo, una métrica o un comando
verificable, listados junto a cada ítem.

**Fuentes cruzadas para este roadmap:**
- `04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md` (5 pasadas: AST, MCP real, Arquitecto Principal, causa raíz de divergencia, reencuadre Etapa 1)
- `04_Reports/Technical/20260714_Auditoria_Integral_Simulador_Operacional.md`
- `04_Reports/Technical/20260715_Migracion_Autonomia_Etapa2.md`
- `06_Documentation/cleanup_log.md`
- Estado de commit real: `git log` (`73b7128`, branch `feature/gemelo-v1-2-0-optimizacion-motor-evidencia`)
- Suite de tests real: `python -m pytest tests -q` → **367 passed** (2026-07-15, verificado en esta misma pasada)
- `codebase-memory-mcp 0.9.0`: mapa de consumidores, `search_graph(max_degree=0)` para código muerto, confirmación de V4/V5 sin callers de producción

## Limitación de MCP reconfirmada en esta pasada

Tras commitear (`73b7128`), `index_status` muestra `head_sha` actualizado
al nuevo commit, pero `index_repository(mode="full")` sigue devolviendo
`nodes=5672/edges=19959` (idéntico al conteo previo al commit), mientras
`expected_nodes=5741/expected_edges=20327` indica que el indexador
detectó más contenido del que efectivamente materializó en el grafo
consultable. Se documenta como discrepancia — el roadmap usa el grafo
como **mapa base + ahorro de tokens**, y todas las cifras de código
muerto/consumidores citadas aquí fueron cruzadas con lectura directa o
`search_code` antes de citarse.

---

## 1. Estado actual (resumen ejecutivo)

### Cerrado y verificado con evidencia

| Ítem | Evidencia |
|---|---|
| Conservación de masa | `mass_balance_error_sagX` < 1e-10 t en 15+ escenarios probados en Etapas 1-2 |
| Dependencia SAG→bolas | `circuit_state.py::resolve_equipment_dependencies`, Regla 4, testeado |
| Kernel `circuit_state.py` | 18+ funciones puras, sin estado global, ~850 líneas, cubierto por `test_circuit_state.py`/`test_circuit_state_phase2.py` |
| Estados operacionales, motivos de restricción, tendencias de pila | `determine_operational_state`, `determine_restriction_reason`, `determine_pile_trend` — implementados y testeados |
| Ventanas, recuperación, episodios | `OperationalWindow`, `analyze_window_episode`, `calculate_effective_feed` |
| Persistencia con `schema_version` | `utils/state_schema.py`, `test_state_schema.py`, `test_scenario_state_migration.py` |
| UX de navegación | `components/navigation.py`, `04_Reports/Technical/20260714_Rediseno_Navegacion_UX_Simulador.md` |
| Etapa 1 de autonomía | `historical_preventive_autonomy_sagX_h`, `dynamic_net_autonomy_sagX_h/_status`, badges duales, gráfico con serie + marcador — 358 tests en el momento de cierre |
| Etapa 2 parcial de autonomía | `AutonomyContext`, `build_autonomy_context`, `recommend_action` migrado con compatibilidad legacy 100% preservada — 367 tests |
| Commit reproducible del estado actual | `73b7128` en `feature/gemelo-v1-2-0-optimizacion-motor-evidencia`, working tree con solo 2 archivos sueltos (`01_Data/Raw/PI_alimentadores_pila_sag1/2.png`, sin trackear) |

### Diferido y pendiente (confirmado, no supuesto)

| Ítem | Evidencia de que sigue pendiente |
|---|---|
| `risk_engine.py` sin migrar | `compute_iro`/`compute_iro_series`/`simple_iro` siguen recibiendo `autonomia_sag1_h`/`autonomia_sag2_h` legacy (confirmado en `20260715_Migracion_Autonomia_Etapa2.md`, sección 3) |
| `optimizer_v2.py`/`optimizer_v3.py` sin migrar | `REF_AUTON_SAG1/2` y `compute_multi_criteria_score` siguen en legacy (misma fuente, sección 4) |
| `bottleneck.py`, `quick_wins.py`, `hourly_plan.py` | Confirmados como consumidores de `sim["autonomia_sag1/2"]` legacy en el mapa de 33 consumidores de la Etapa 1 |
| Sensibilidad de tolerancias `RESTRICTED` | `determine_operational_state` sigue usando `rate_effective < rate_target - 1e-6` (comparación exacta, sin tolerancia configurable) — no auditado |
| V4/V5: confirmación + decisión de producto | **Confirmado esta pasada vía MCP**: `find_optimal_v4`/`find_optimal_v5` tienen `in_degree=0` — cero consumidores de producción, solo tests. Documentado, decisión de producto (archivar/conectar) aún no tomada |
| Motores de recomendación en estado sombra | **Confirmado esta pasada vía MCP**: `rate_recommendation.py::recommend_rate` (in_degree=0), `rules_engine.py::recommend_rate` (in_degree=0), `circuit_state.py::generate_operational_recommendation` (in_degree=0) — 3 funciones completas de recomendación sin ningún consumidor de producción, coexistiendo con `recommend_action` (el único motor activo real) |
| Calibración factor una bola | `ONE_BALL_CAPACITY_FACTOR = 0.55` en `ode_model.py:28` — constante fija, sin fuente de calibración documentada (a diferencia de `DRAIN_PCT_H`, que sí tiene 27 eventos + informe de calibración) |
| Validación histórica formal (hold-out) | `historical_backtesting.py::run_backtest` existe y se reusa en `/desempeno_gemelo`, pero no hay separación documentada calibración/validación/test ni métricas MAE/RMSE/bias publicadas por ventana |
| Refactor `update_simulation` | `register_simulador_callbacks` (`pages/simulador_operacional.py`) mide 1.928 líneas, complejidad ciclomática 85, cognitiva 118 (medido en la auditoría MCP de 2026-07-14, aún vigente — no se tocó en Etapas 1-2) |
| Centralización de constantes | `DRAIN_PCT_H`, `CRITICAL_PCT`, `AUTONOMY_THRESHOLDS` duplicadas en `ode_model.py` y `rules_engine.py` con los mismos valores (23.76/6.18, etc.) — confirmado en la Cuarta pasada de la auditoría de Etapa 1 |
| Código muerto | **9 candidatos confirmados por `search_graph(max_degree=0, exclude_entry_points=true)` en esta pasada**: `compute_cv_tph`, `page_simulador` (app.py), `read_jefe_sala_feedback`, `regime_fn_factory`, más 4 en `02_Analytics/` y 2 falsos positivos de JS (`scrollToTopOnClick`/`toggleBackToTop`, event listeners) |
| Commit reproducible | **Resuelto parcialmente en esta pasada**: existe `73b7128`, pero sin tag de línea base ni manifiesto actualizado post-commit |
| Validación visual real / modo claro-oscuro | Sin evidencia de sesión de usuario registrada en el repositorio (no hay archivo de resultados de prueba con Jefe de Sala) |
| Documentación final | `packaging/README_USUARIO.md` existe (uso general), pero no hay diccionario de parámetros/outputs, catálogo de reglas, ni guía de calibración dedicados |

---

## 2. Roadmap por fases

### Fase 0 — Reproducibilidad y línea base

**Objetivo:** crear una línea base reproducible antes de seguir modificando.

**Estado real:** **CERRADA (5/5 criterios)** — actualizado 2026-07-15.

| Criterio | Estado |
|---|---|
| `git status`/`git diff --stat` registrados | ✅ hecho |
| `audit_worktree_manifest.json` actualizado | ✅ existe, commiteado en `73b7128` |
| Commit técnico del estado validado | ✅ `73b7128` (171 archivos) + `c3094a1` (roadmap + limpieza Fase 0) |
| Tag de línea base (`simulator-autonomy-stage2-baseline`) | ✅ **creado esta pasada** sobre `73b7128` |
| `git checkout <commit>` reproduce 367 tests + escenarios + UI | ✅ verificado |

**Bloqueo activo:** ninguno. Los 2 archivos sueltos
(`01_Data/Raw/PI_alimentadores_pila_sag1/2.png`) se clasificaron como
activos legítimos (mismo patrón que las demás capturas SCADA ya
versionadas) y se commitearon en `c3094a1`. Working tree limpio.

**Condición de cierre:** cumplida. **Fase 0 cerrada.**

---

### Fase 1 — Correctitud operacional del estado y autonomía

**Objetivo:** cerrar la migración funcional iniciada en Etapa 2.

**Estado real:** EN IMPLEMENTACIÓN (1.1-1.4 hechas, solo 1.5 pendiente —
5/7 criterios).

**Dependencias:** requiere Etapa 2 (✅ ya completa para `recommend_action`).

**1.1 `risk_engine.py::compute_iro` — HECHO (2026-07-15).** Corrección
de riesgo real vs. lo estimado: `query_graph` confirmó que `compute_iro`
tiene **un solo caller de producción real** (`engine/simulator.py:229`)
— el import en `app.py::comparar_whatif` resultó vestigial (esa función
lee `sim["iro_result"]` ya calculado por `simulate_scenario`, nunca
llama a `compute_iro` directamente). Migración aditiva: `autonomy_
context_sag1/2: AutonomyContext | None = None` nuevos, **el `iro` total
y los 5 sub-scores legacy quedan matemáticamente idénticos** (verificado
con test dedicado, no solo revisión visual) — no se repartió el peso
`WEIGHTS["autonomia"]=0.30` entre dos sub-scores nuevos porque no hay
dato para recalibrarlo (instrucción explícita del pedido: "si no hay
evidencia para recalibrar, preserva el score total y agrega sub-scores
aditivos"). Se agregan `dynamic_depletion_score`/`historical_
vulnerability_score` solo cuando el llamador pasa `AutonomyContext`
(reusando los mismos objetos ya construidos para `recommend_action`, sin
recomputar). `05_Dashboard/tests/test_risk_engine.py` (7 tests nuevos,
incluye el caso central: pila con vulnerabilidad histórica crítica pero
llenándose → `dynamic_depletion_score=100` mientras `autonomia_score`
legacy sigue bajo, demostrando la incoherencia que motivó esta fase).
374 tests totales pasando (367 + 7).

**1.2 `bottleneck.py` — HECHO (2026-07-15).** Campo aditivo `categoria`
en cada candidato/entrada del mapa (`STOCKPILE_DYNAMIC_DEPLETION` /
`STOCKPILE_LOW_BUFFER` / `BALL_MILL_CAPACITY` / `FEED_RESTRICTION` /
`CHANCADO_LIMIT` / `SAG_OFF`), sin tocar severidad/color/motivo ya
testeados. Hallazgo de diseño importante: `detect_bottleneck` usa
`min_autonomia_sagX` (**mínimo de toda la trayectoria**, no el estado
final) — un escenario que tuvo un momento crítico real (autonomía 0.05h
en algún punto) y termina `FILLING` sigue clasificándose con severidad
`alta` (correcto: el riesgo real ocurrió), pero ahora también lleva
`categoria=STOCKPILE_LOW_BUFFER` para indicar que ya no está drenando.
No se cambió la severidad — sería incorrecto ocultar un riesgo real ya
ocurrido solo porque el escenario se recuperó al final. 4 tests nuevos.

**1.3 `quick_wins.py` — HECHO (2026-07-15).** `QuickWin.delta_
autonomia_h` (ambiguo, medía el colchón preventivo histórico)
renombrado explícitamente a `delta_historical_buffer_h`; nueva
`delta_dynamic_autonomy_h` (mejora real en balance neto del estado
final). El criterio de filtro/orden (`beneficio_costo`) sigue anclado al
colchón preventivo — no se cambió sin datos para justificar el cambio.
2 consumidores UI actualizados (`components/cards.py`, `pages/
simulador_operacional.py`). 5 tests nuevos.

**1.4 `hourly_plan.py` — HECHO (2026-07-15).** Hallazgo: `build_hourly_
plan` tiene **cero consumidores de producción** (solo su propio test) —
riesgo de esta migración más bajo de lo estimado. Agregadas 8 columnas
aditivas por bloque horario (`dynamic_status_sagX`, `net_balance_sagX_
tph`, `dynamic_autonomy_sagX_h`, `historical_vulnerability_sagX`),
calculadas reusando `classify_dynamic_autonomy`/`classify_historical_
vulnerability` de la Etapa 1 sobre las series de 5 min que `simulate_
ode` ya produce — sin ejecutar ninguna simulación nueva. Degrada con
gracia a `None` si el dict no trae `pile_sag1/2` (dict sintético
mínimo). 2 tests nuevos.

**1.5 Sensibilidad de tolerancias `RESTRICTED` — HECHO (2026-07-15).**
`circuit_state.py::determine_operational_state` reemplaza la comparación
exacta `rate_effective < rate_target - 1e-6` por
`(rate_target - rate_effective) > max(tolerance_tph, rate_target *
tolerance_pct)`, con parámetros opcionales `rate_restriction_tolerance_
tph`/`_pct` — default preserva el comportamiento previo (`1e-6`,
efectivamente cero tolerancia). **No se fijó un valor de producción**
(instrucción explícita del pedido: "no fijes valores definitivos sin
sensibilidad") — se corrió el estudio con datos reales de 2 escenarios
(`sensibilidad_restricted.py`, scratchpad) reconstruyendo la trayectoria
`tph_sagX` vs. `rate_target` que `simulate_ode` ya produce (sin
recalcular nada):

```text
Escenario T8 8h, correas reducidas:
  SAG1 (target 1454 TPH): baseline 97.2% RESTRICTED -> 10TPH:97.2% | 25TPH:92.0% | 50TPH:83.4% | 1%:97.2% | 2%:90.7% | 5%:76.8%
  SAG2 (target 2516 TPH): baseline 57.4% RESTRICTED -> 10TPH:54.0% | 25TPH:49.5% | 50TPH:41.5% | 1%:49.1% | 2%:40.8% | 5%:32.9%

Escenario T8 12h, correas inactivas:
  SAG1 (target 1454 TPH): baseline 53.3% RESTRICTED -> 10TPH:53.3% | 25TPH:53.3% | 50TPH:52.6% | 1%:53.3% | 2%:53.3% | 5%:52.6%
  SAG2 (target 2516 TPH): baseline 99.7% RESTRICTED -> 10TPH:98.3% | 25TPH:95.8% | 50TPH:91.7% | 1%:95.5% | 2%:91.7% | 5%:90.7%
```

**Hallazgo real (no esperado a priori):** el % de pasos RESTRICTED es
altísimo en ambos escenarios (53-99%) incluso con tolerancia amplia
(5%) — la clasificación RESTRICTED durante ventanas T8 activas está
dominada por la restricción de alimentación real (correas reducidas/
inactivas), **no por ruido de precisión de punto flotante**. Esto
significa: (a) el comportamiento previo (comparación exacta) no estaba
generando falsos positivos masivos que una tolerancia razonable
resolviera — el "problema" que motivó esta fase es mucho más acotado de
lo que el pedido asumía; (b) cualquier tolerancia entre 10-50 TPH o
1-5% mueve el % RESTRICTED en 5-20 puntos porcentuales, un efecto real
pero no dramático, y **la elección del valor final es una decisión de
producto** (qué tan sensible debe ser la alarma), no una que deba
tomarse sin involucrar al Jefe de Sala/Metalurgista. 4 tests nuevos en
`test_circuit_state.py` (`TestToleranciaRestricted`) cubren default
preservado, tolerancia TPH, tolerancia %, y que diferencias grandes
siguen RESTRICTED con cualquier tolerancia razonable.

**Condición de cierre — Fase 1 COMPLETA (7/7):** ningún consumidor de
decisión operacional ambiguo entre histórica y dinámica.
`risk_engine.py`, `bottleneck.py`, `quick_wins.py`, `hourly_plan.py` ya
no son ambiguos — cada uno expone ahora el desglose dinámico/histórico
sin cambiar su comportamiento legacy por defecto. La tolerancia
`RESTRICTED` es configurable con evidencia de sensibilidad real
documentada; el valor de producción queda como decisión de producto
pendiente, no como brecha de ingeniería.

---

### Fase 2 — Consolidación del motor de recomendaciones

**Objetivo:** eliminar la coexistencia de motores de recomendación desconectados.

**Estado real:** EN ANÁLISIS (evidencia recolectada esta pasada, 0
código nuevo).

**Evidencia MCP recolectada esta pasada** (antes de proponer cualquier
cambio):

| Función | Consumidores de producción | Clasificación sugerida |
|---|---|---|
| `rules_engine.py::recommend_action` | `engine/simulator.py::simulate_scenario` (real, ~24 consumidores aguas abajo) | **motor principal** |
| `rate_recommendation.py::rank_candidates` | `in_degree=2` (consumidores reales, sin identificar en esta pasada — requiere `trace_path`/`query_graph` dedicado) | complementaria — investigar antes de decidir |
| `rate_recommendation.py::recommend_rate` | `in_degree=0` | candidato a eliminar o archivar |
| `rules_engine.py::recommend_rate` | `in_degree=0` | candidato a eliminar o archivar — **nombre duplicado con el anterior, mismo símbolo funcional confirmado en la auditoría de la segunda pasada (2026-07-14)** |
| `circuit_state.py::generate_operational_recommendation` | `in_degree=0` | candidato a eliminar o archivar — código del kernel de dominio escrito pero nunca conectado a `simulate_ode` |

**Hallazgo de esta pasada:** había **4 funciones completas de
recomendación sin consumidores de producción** coexistiendo con la única
activa (`recommend_action`). Esto era exactamente el problema que la
Fase 2 del pedido busca resolver — no era hipotético, estaba confirmado.

**Actualización (2026-07-15, cierre de brechas):**
- `rate_recommendation.py::recommend_rate` — **eliminada**. Confirmado
  `in_degree=0` vía MCP + `grep` (ni `pages/simulador_operacional.py` ni
  ningún test la importaban; solo envolvía `rank_candidates()` sin
  agregar nada que el caller real no hiciera ya directamente). 367 tests
  siguen pasando tras la eliminación.
- `rules_engine.py::recommend_rate` — **eliminada**. Confirmado
  `in_degree=0`, sin imports ni tests. Superada por `determine_regime`
  (cuyos `bounds` ya se usan directamente en `simulator.py`).
- `rate_recommendation.py::rank_candidates` — **confirmada como motor
  complementario activo**, no tocada. `query_graph` confirmó 2 relaciones
  reales: `pages/simulador_operacional.py` la llama directamente (tabla
  de comparación de escenarios) y la ya-eliminada `recommend_rate` la
  envolvía. Se mantiene intacta.
- `circuit_state.py::generate_operational_recommendation` — **NO
  eliminada, clasificada como "revisar" y diferida a Fase 5**. Al leer su
  código completo se confirmó que es una función bien diseñada y ya
  cuantificada (Regla 16, 67 líneas, complejidad 11) que hace casi
  exactamente lo que la Fase 4 de la Etapa 2 pidió para `recommend_
  action` — pero nunca se conectó a `simulate_ode`. Es una duplicación
  conceptual real con el helper `_accion_por_contexto_dinamico` agregado
  en Etapa 2, no código muerto sin valor. Eliminarla sin decidir cuál de
  las dos arquitecturas de mensaje gana sería destruir trabajo útil —
  esta decisión queda explícitamente para la Fase 5 (`RecommendationService`).

**Condición de cierre (parcial, actualizada):** 2 de 4 funciones sombra
resueltas (eliminadas con evidencia y sin romper tests). Queda 1
decisión de fondo pendiente (`generate_operational_recommendation` vs.
`_accion_por_contexto_dinamico`) para cuando se aborde `RecommendationService`
en Fase 5 — no se resuelve con una eliminación rápida, requiere diseño.

**Validación con escenarios dorados (2026-07-15, continuación —
sección 29 del programa de validación estadística):** ver
`04_Reports/Technical/Validacion_Motor_Recomendaciones.md` y
`05_Dashboard/tests/test_golden_scenarios_recommend_action.py`.
`recommend_action` pasa 4/5 escenarios canónicos (pila baja+llenando →
MONITOREAR; pila alta+drenando rápido → REDUCIR_CARGA; agotamiento
antes de fin de ventana → EMERGENCIA con mensaje cuantificado tasa+
tiempo; ventana termina antes del crítico → MONITOREAR). **Gap real
confirmado ejecutando el código (no especulado)**: SAG apagado con
pila subiendo hacia el 100% (`pile_sag1_pct=96%`, `sag1_activo=False`)
retorna `OPERACION_NORMAL` — el motor no escala la acción ante riesgo
de overflow inminente, solo agrega una nota informativa que no cambia
la severidad. Dejado como test `xfail(strict=True)` documentado, no
corregido (requiere decisión de producto: qué acción/mensaje debe
generar el sistema en ese escenario).

---

### Fase 3 — Optimización y dual score

**Objetivo:** alinear la optimización con la nueva semántica de autonomía.

**Estado real:** EN IMPLEMENTACIÓN (3.2-3.4 hechas para `optimizer_v2.py`
— el motor real detrás de `find_optimal_v3`; 3.5 documentada con
decisión explícita; 3.1 cubierto como evidencia dentro de 3.2).

**3.1-3.2 Inventario y doble penalización — CONFIRMADA (2026-07-15).**
`compute_multi_criteria_score` (`optimizer_v2.py`, el score real que
ordena `run_deterministic_grid`/`adaptive_mc_eval`, ambos en el camino
de `find_optimal_v3`) combina `inv_norm` (% de pila final) y
`auton_norm` (`a1_min`/`a2_min`, la autonomía histórica **mínima de la
trayectoria** — que a su vez es `compute_autonomia(pile_pct)`, una
función DIRECTA y monótona del mismo % de pila). Los pesos por régimen
(`w["inventario"]` 10-20% + `w["autonomia"]` 5-10%, ver docstring del
módulo) penalizan la misma señal subyacente dos veces con distinta
intensidad — confirmado algebraicamente, no solo sospechado. **No se
recalibraron los pesos** (instrucción explícita del pedido: nada se
cambia sin datos que lo respalden) — se documentó en el propio código
(`optimizer_v2.py::compute_multi_criteria_score`, docstring extendido).

**3.3-3.4 Dual score — HECHO (2026-07-15).** `run_deterministic_grid`
ahora agrega 6 claves aditivas por candidato (`dynamic_status_sagX`,
`dynamic_autonomy_sagX_h`, `historical_vulnerability_sagX`) — ya
calculadas por `simulate_scenario` por candidato, **cero simulaciones
extra**. Nuevas funciones `compute_dual_score` (`dynamic_safety_score`/
`historical_buffer_score`, `None` explícito si faltan datos, nunca 0 por
defecto) y `compare_rankings` (`ranking_diverges`/`top_legacy`/
`top_dynamic`). **`det_score` y el orden de `results.sort(...)` no
cambian** — verificado con test dedicado
(`test_run_deterministic_grid_no_cambia_su_orden_de_seleccion`).

**Hallazgo real, no hipotético:** una corrida de prueba (T8 4h, correas
inactivas, pila 45%) mostró `ranking_diverges=True` — el candidato #1
por `det_score` legacy y el candidato #1 por `dynamic_safety_score` son
**distintos**. El score legacy no está eligiendo al candidato más seguro
en tiempo real en este escenario. Esto es exactamente la evidencia que
Fase 3.3-3.4 pedía generar — la decisión de **si** cambiar la selección
oficial queda para una sesión futura con más escenarios de prueba, no
tomada aquí. 10 tests nuevos (`test_optimizer_v2_dual_score.py`).

**3.5 Decisión V4/V5 — TOMADA (2026-07-15).** Confirmado (ya en la
pasada anterior, revalidado aquí): `find_optimal_v4`/`find_optimal_v5`
tienen `in_degree=0` — cero consumidores de producción, solo sus propios
tests. Revisado el historial de git: ambos aparecen ya completos y
testeados en los commits base del proyecto (no son WIP a medio hacer).
**Decisión explícita**: no conectar, consolidar, archivar ni eliminar en
esta sesión — la elección entre 4 alternativas reales
(`compute_multi_criteria_score` ponderado vs. `rank_candidates`
lexicográfico vs. `score_v5_candidate`/harmony index vs. algo nuevo) es
una decisión de **producto** (qué filosofía de recomendación prefiere el
Jefe de Sala/Metalurgista), no una decisión de ingeniería que deba
tomarse unilateralmente. Se documenta como pendiente de decisión
explícita del usuario, no como omisión.

**3.6 Dual score en Monte Carlo (`adaptive_mc_eval`) — HECHO (2026-07-15,
continuación).** Mismo patrón aditivo que 3.3-3.4: por muestra Monte
Carlo, `adaptive_mc_eval` ya lee `dynamic_net_autonomy_sagX_status` que
`simulate_ode` calcula (Etapa 1) — cero simulaciones extra. Nuevos
campos en el resultado: `pct_draining_sagX`/`pct_at_critical_sagX` (%
de muestras en cada estado dinámico por SAG) y `p_dynamic_safe`
(fracción de muestras donde ningún circuito está `DRAINING`/`AT_
CRITICAL_LEVEL`, análogo en interpretación a `p_safe` pero basado en
balance neto real por muestra en vez de autonomía histórica mínima).
`p_safe` y `multi_criteria_score` no cambian — verificado con test
dedicado (`test_score_y_orden_no_cambian`). 3 tests nuevos
(`TestAdaptiveMcEvalDualScore` en `test_optimizer_v2_dual_score.py`),
incluye el mismo hallazgo de Fase 3.3-3.4: `p_safe` y `p_dynamic_safe`
pueden divergir para el mismo candidato (evidencia, no bug).

**Limpieza de código muerto asociada (Fase 7, 4/9 candidatos, 2026-07-15
continuación):** eliminados `regime_fn_factory` (`rules_engine.py`,
`in_degree=0`, superado por `determine_regime` usado directamente),
`compute_cv_tph` (`ode_model.py`, `in_degree=0`), `read_jefe_sala_
feedback` (`validation/feedback_form.py`, `in_degree=0`) y `page_
simulador`+import huérfano de `build_sidebar` (`app.py`, reemplazado
hace tiempo por `page_simulador_operacional` en `pages/simulador_
operacional.py`, que sí importa `build_sidebar` correctamente). Grep
confirma cero referencias rotas; `import app` carga limpio; 426 tests
pasando (367 base + 22 Fase 1 + 10 Fase 3 grid + 3 Fase 3.6 MC + otros
acumulados de esta serie de sesiones).

**Verificación de los candidatos restantes en `02_Analytics/`
(2026-07-15, continuación posterior):** MCP seguía reportando
`in_degree=0` para 3 funciones ahí (`michaelis_menten`,
`semaforo_autonomia`, `tiempo_hasta_zona`), pero al verificar cada una
con `Grep` directo (no confiar solo en MCP, práctica ya establecida)
**2 de las 3 son falsos positivos**: `michaelis_menten` se usa como
callback pasado a `scipy_curve_fit(michaelis_menten, ...)` (dos veces,
mismo archivo) y `semaforo_autonomia` se usa vía `.apply(semaforo_
autonomia)` — el grafo MCP no traza funciones pasadas como argumento/
callback, solo llamadas directas por nombre. **Solo `tiempo_hasta_zona`
(`estrategia_pilas.py`) es código muerto genuino** (cero referencias
fuera de su propia definición). Al estar en `02_Analytics/` (scripts de
análisis exploratorio, no del dashboard productivo), sigue la misma
política ya establecida en `20260714_Auditoria_Estructural_Simulador.
md`: decisión del equipo de analítica, no del equipo del simulador —
no se elimina unilateralmente en esta pasada.

**`optimizer_v3.py` — confirmado que NO necesita migración propia
(2026-07-15, verificado con lectura de código + ejecución real):**
`find_optimal_v3` no calcula ningún score propio — llama directamente
a `run_deterministic_grid` y `adaptive_mc_eval` (ambas ya instrumentadas
con dual score en 3.3-3.4) y solo reordena el resultado (`multi_
criteria_score`/`tph_mean`/`p_safe`) para elegir por `mode`. `_enrich_
v3` muta los dicts *in-place*, nunca los reconstruye — verificado
empíricamente ejecutando `find_optimal_v3` directamente: el resultado
`best` ya trae las 9 claves dual-score (`p_dynamic_safe`, `pct_
draining_sagX`, `pct_at_critical_sagX`, `dynamic_status_sagX`,
`historical_vulnerability_sagX`) sin ningún cambio de código, con el
mismo patrón de divergencia ya documentado (`p_safe=0.0` vs. `p_
dynamic_safe=0.52` para el mismo candidato en una corrida real).

**Condición de cierre: CUMPLIDA.** El camino de decisión completo (grid
determinístico + Monte Carlo + V3, que es lo que realmente usa la UI)
expone dual score de forma consistente, sin duplicar silenciosamente la
señal de nivel/autonomía, y sin necesitar trabajo adicional en V3. V4/V5
tienen decisión explícita (no acción, con justificación). Queda
pendiente, fuera del alcance técnico de esta fase, decidir **si** alguna
vez se reemplaza la selección oficial (`multi_criteria_score`) por la
señal dinámica — es una decisión de producto, no una brecha de
instrumentación.

---

### Fase 4 — Calibración y validación histórica

**Objetivo:** demostrar fidelidad contra datos reales no utilizados para calibrar.

**Estado real:** EN IMPLEMENTACIÓN — la infraestructura de backtesting
resultó mucho más madura de lo que esta misma sección asumía antes de
esta pasada (ver hallazgo de corrección de estimación abajo). Se
extendió con bias/std reales y se descubrió un problema metodológico
real (hold-out).

**Corrección de estimación importante:** `historical_backtesting.py::
run_backtest`/`run_backtest_proxy` **ya existían, completos y con datos
reales** — no eran una brecha de "cero backtesting". Ya calculaban MAE
por régimen contra 6 regímenes (t8_corta, t8_larga, inventario_crítico,
overflow, mantenimiento, alimentación_restringida), con disciplina
explícita de "no fabricar" (si `N < N_MINIMO_EVENTOS`, reporta
`historica_disponible=False` con razón, nunca inventa un resultado). El
diagnóstico de t8_corta (`04_Reports/Technical/
DIAGNOSTICO_MAE_t8_corta.md`, 2026-07-07) ya incluía bias/std, no solo
MAE. Lo que faltaba: bias/std para los otros 4 regímenes, y correr todo
de una vez para tener el cuadro completo.

**4.1 Auditoría de parámetros — CONFIRMADA con evidencia directa:**

| Parámetro | Calibrado | Fuente |
|---|---|---|
| `DRAIN_PCT_H` (ode_model.py) | ✅ Sí | 27 episodios reales, IC90 (`20260625_Pilas_Descarga_Robusto.md`) |
| `BOLA_DELTA_TPH` (ode_model.py) | ✅ Sí | `02_Analytics/Scripts/calibrar_bola_delta_tph.py` (script real, existente) |
| `ONE_BALL_CAPACITY_FACTOR=0.55` (ode_model.py:28) | ❌ No | Sin fuente — ya documentado como supuesto en `20260714_Logica_Operacional_Pilas_SAG.md` sec.10 y en `README_USUARIO.md` (Fase 7 quick win, esta misma serie de sesiones) |
| `VENTANA_FACTOR_ESTADO["reducida"]=0.4` (ode_model.py:22) | ❌ No | Sin fuente citada en el código |
| `_pile_feedback_factor` (breakpoints 35%/25%/crit+5%, magnitudes -15/-30/-50%) | ❌ No | Sin fuente citada — hand-picked |
| Sigmas Monte Carlo: pila ±2.5pp, feed ±12%, T8 ±1h (`optimizer_v2.py:425-428`) | ❌ No | **Auditado con evidencia cuantitativa el 2026-07-15** (ver `Calibracion_Monte_Carlo.md`): los 3 sigmas subestiman proxies empíricos reales — T8 (std real 2.07h vs. 1.0h asumido, 2.07x, distribución muy asimétrica skew=5.0), feed (CV real 0.34 en ventanas de 4h vs. 0.12 asumido, 2.85x, confirma y refina la comparación direccional previa al mismo horizonte temporal), pila (SAG1 1.18x más volátil que el sigma compartido, SAG2 0.39x — el sigma único de 2.5pp para ambos activos probablemente sobrestima SAG2 y subestima SAG1). **Validación de `p_safe` contra desenlaces reales ejecutada** (misma pasada): bien calibrado en calibración (Brier=0.18, mejor que baseline ingenuo), muy mal calibrado en hold-out (Brier=0.62, predice `p_safe`≈0.25 cuando 94.7% de esos eventos fueron realmente seguros) — **tercera línea de evidencia independiente de la misma deriva temporal sistémica** ya encontrada en la regresión de fidelidad. No se recalibran sigmas hasta resolver esa deriva (prioridad mayor) |
| Pesos `PERFILES_V5` (optimizer_v5.py) | ❌ No | Sin fuente citada — V5 sin consumidores de producción (Fase 3.5), menor prioridad |

**4.3 Backtesting real ejecutado — resultados reales, no proyectados
(2026-07-15):**

```text
Régimen                    N     MAE(pp)  bias(pp)  std(pp)  ¿dentro tolerancia 5pp?
t8_corta                   63    18.88    -16.91    19.92    NO
t8_larga                    8    N/A (N<20, insuficiente)     N/A
inventario_critico         221    13.89    -11.02    18.73    NO
overflow                    97     4.51     +3.47     4.63    SÍ (único que pasa)
mantenimiento              239    14.47     +0.27    20.76    NO
alimentacion_restringida  1477    12.80    -11.82    12.81    NO
```

**Hallazgo real, no favorable, reportado sin suavizar:** el simulador
**falla su propia tolerancia declarada (5.0pp) en 4 de los 5 regímenes**
con datos suficientes. Patrón consistente: la mayoría de los regímenes
tienen **bias negativo** (el motor subestima la pila final, ya
diagnosticado para t8_corta en 2026-07-07 como causado por asumir
alimentación plena cuando el T8 real la restringe ~55-66%). `overflow`
es el único régimen dentro de tolerancia. Esto **no es una regresión de
esta sesión** — es el estado real, preexistente, nunca antes agregado en
un solo lugar.

**Hallazgo metodológico nuevo — separación calibración/validación
(hold-out) ahora sí resuelta con evidencia fuerte:** el cruce
evento-a-evento entre `01_Data/Processed/fact_eventos_t8.parquet`
(calibración de `DRAIN_PCT_H`) y
`01_Data/Cache/advanced_t8_official_events.parquet` (backtesting
oficial `t8_corta`) confirma que el solape no es parcial sino
**total**. Las 29 ventanas únicas de calibración cubren el rango
`2026-01-02` → `2026-06-25`, exactamente el mismo rango del dataset
oficial; usando el criterio temporal correcto (un evento oficial queda
contaminado si cae entre `inicio` y `fin` de una ventana de
calibración), **72 de 72 eventos oficiales** quedan cubiertos por al
menos una ventana de calibración. Solo 6 hacen match exacto por
fecha+duración, pero **0 de 72** quedan completamente fuera de muestra.
Conclusión: el criterio de aceptación "existe conjunto hold-out" de este
pedido **NO está satisfecho hoy** y el MAE de `t8_corta` reportado hasta
ahora no es una validación fuera de muestra para `DRAIN_PCT_H`.

**Corte recomendado para construir el hold-out real:** `2026-04-30`.
Deja 21 ventanas de calibración, 50 eventos oficiales en calibración y
22 eventos oficiales hold-out; para `t8_corta`, deja 44 eventos en
calibración y **20 eventos hold-out**, justo el mínimo de suficiencia
ya exigido por `historical_backtesting.py`. Cortes más tardíos dejan
hold-out demasiado chico (14 eventos cortos al `2026-05-15`, 10 al
`2026-05-31`).

**Recalibración experimental ya ejecutada sobre ese split (misma
continuación):** recalibrando `DRAIN_PCT_H` con ventanas <=
`2026-04-30` se obtiene SAG1=**27.85%/h** y SAG2=**5.85%/h** (21
eventos válidos por SAG), pero el MAE de pila en `t8_corta` queda
**idéntico** antes/después del cambio tanto en calibración (11.21pp) como
en hold-out (36.63pp). La métrica que sí cambia, `error_tiempo_critico_h`,
empeora en hold-out (5.45h -> 7.44h). Conclusión: `DRAIN_PCT_H` **no es
la palanca correcta** para el P0 de fidelidad de pila en la ruta actual
del motor; cambiarlo en producción no está justificado por esta evidencia.

**Sensibilidad contrafactual de `_pile_feedback_factor` ya ejecutada
también sobre ese hold-out real:** usando exactamente la ruta productiva
de `run_backtest("t8_corta")`, pero escalando temporalmente el feedback
de pila baja a `75%`, `50%`, `25%` y `0%`, el MAE de hold-out empeora de
forma **monótona**: `36.63pp` (baseline) -> `37.59pp` -> `38.43pp` ->
`38.98pp` -> `39.26pp`; el bias también se vuelve más negativo
(`-36.30pp` -> `-38.93pp`). En calibración ocurre lo mismo
(`11.21pp` -> `13.46pp`). Interpretación correcta: `_pile_feedback_factor`
sí es el mejor **marcador** de dónde se concentra el error, pero
relajarlo o apagarlo **no corrige** el P0; al contrario, el mecanismo
actual amortigua parcialmente el sesgo negativo cuando la pila entra a
zona baja. El siguiente foco debe ser explicar por qué el motor llega a
esas zonas con tanto sesgo, no quitar el amortiguador.

**4.2 Factor una bola:** `ONE_BALL_CAPACITY_FACTOR` sigue sin calibrar.
Existe una ruta concreta y ya usada para hacerlo:
`02_Analytics/Scripts/calibrar_bola_delta_tph.py` calibró `BOLA_DELTA_
TPH` (el mecanismo SÍ activo) con esta misma metodología — la Ficha 2
de la Etapa 1 (Arquitecto Principal, 2026-07-14) ya recomendó reusar
ese script apuntado a `ONE_BALL_CAPACITY_FACTOR`. No se ejecutó en esta
pasada (requiere adaptar el script, no solo correrlo) — próximo paso
concreto, no una brecha sin plan.

**Extensión aditiva implementada:** `BacktestResult` gana `pila_bias_
sag1_pp`/`pila_std_sag1_pp` (misma metodología que ya usaba el
diagnóstico de t8_corta), ahora calculados para los 5 regímenes con
datos, no solo t8_corta. `dentro_tolerancia`/`pila_mae_sag1_pp` sin
cambios. 6 tests nuevos (`test_backtesting_bias_std.py`).

**Pendiente (fuera de esta pasada):** confirmar/resolver la separación
calibración-validación (requiere cruce evento-a-evento, no solo fechas
de inicio); RMSE explícito (actualmente MAE+bias+std, matemáticamente
derivable pero no expuesto como campo propio); desglose por ventana
0/2/4/8/12h específicamente (hoy es por régimen t8_corta/t8_larga, una
categorización distinta); calibración real de sigmas MC; ejecución de
4.2 (factor una bola).

**Condición de cierre:** el simulador **ya no está "solo validado por
tests"** — tiene backtesting real contra datos históricos, con métricas
conocidas y publicadas (bias/std/MAE por régimen). **No está cerrada**:
el resultado real es que el modelo no pasa su propia tolerancia en la
mayoría de los regímenes, y la separación calibración/validación no está
confirmada — ambos son hallazgos honestos que bloquean el cierre final
(ver sección 9), no builderas para desactivar.

**Fase 4B — Diagnóstico causal (2026-07-15, parcial):** ver
`04_Reports/Technical/20260715_Diagnostico_Fidelidad_Historica.md` y
`04_Reports/Technical/backtesting_baseline_manifest.json` (línea base
congelada: git HEAD, hash de 4 datasets fuente, parámetros activos,
resultados por régimen). Metodología del MAE validada (mide estado
final del evento, no trayectoria/mínimo; alineación temporal corregida
en la ruta "oficial" desde 2026-07-07 pero **no** en la ruta "proxy" —
inconsistencia real, sin resolver). Diagnóstico causal de
`alimentacion_restringida` (N=1.477, prioridad máxima por N): **la
hipótesis de "factor fijo 0.4 mal aplicado" queda descartada con
evidencia de código** — `VENTANA_FACTOR_ESTADO` nunca se invoca en esta
ruta de backtesting (`duracion_t8_h=0.0`, `cv_mode="manual"` con valores
reales observados). El error se concentra en un subconjunto de eventos
(P90 error pila=30pp vs. mediana=10pp) con mediana de error de F_out=0%
— apunta a divergencia de trayectoria/dinámica cerca del nivel crítico
(`_pile_feedback_factor`, hipótesis 3.2 del pedido) como causa más
probable que el nivel de alimentación, incluso para el régimen de mayor
N.

**Fase 3.2-3.5 confirmada con evidencia cuantitativa (misma pasada,
continuación):** se reprodujo cada evento de `alimentacion_restringida`
(N=1.477), `inventario_critico` (N=221), `t8_corta` (N=63),
`mantenimiento` (N=239) y `overflow` (N=97) conservando la trayectoria
simulada completa, y se comparó el error de pila entre eventos que
cruzan los breakpoints de `_pile_feedback_factor` (35%/25%/`CRITICAL_
PCT`+5%) y los que no. **Patrón confirmado en 4 regímenes y control
positivo en el quinto**: los eventos que cruzan tienen **2.0-2.5x más
error** en `alimentacion_restringida`, `inventario_critico` y
`mantenimiento`, y una señal todavía más fuerte en `t8_corta`
(25.8-32.4pp vs. 3.8-6.6pp, **4.9-8.3x**). `overflow`, en cambio, cruza
**0/97** veces cualquier breakpoint y es el único régimen dentro de
tolerancia (MAE 4.51pp), funcionando como control positivo de
especificidad. En `mantenimiento`, el bias agregado casi nulo (+0.27pp)
esconde cancelación entre subtipos (`mantenimiento_SAG1` +8.30pp vs.
`mantenimiento_SAG2` −10.50pp), confirmando la heterogeneidad física que
ya se sospechaba. Es la causa individual más fuerte identificada hasta
ahora — aunque no explica el 100% del error agregado. **Extensión
hold-out ya ejecutada en esta misma continuación:** debilitar
`_pile_feedback_factor` en `t8_corta` fuera de muestra empeora el MAE de
forma monótona (`36.63pp` -> `39.26pp`), por lo que la lectura correcta
ya no es "el feedback actual sobrecastiga", sino "los eventos que caen a
zona baja son donde el modelo ya viene más desalineado y el feedback
actual ayuda parcialmente". Se mantiene como mecanismo no calibrado, pero
deja de ser candidato prioritario para una corrección rápida por simple
atenuación.

Fases 7-11 del pedido de Fase 4B **no ejecutadas esta pasada** — el
pedido completo es un programa de varias sesiones.

**Fase 4B continuación — Regresión multivariada del error de pila
(2026-07-15, mismo día, pasada posterior):** en respuesta a un pedido
más amplio de validación estadística (37 secciones), se priorizó
continuar el diagnóstico causal con un modelo formal en vez de seguir
iterando hipótesis de a una. Ver `04_Reports/Technical/
Analisis_Estadistico_Simulador.md` y `Validacion_Modelos_Regresion.md`
(scripts reproducibles en `02_Analytics/Scripts/statistical_validation/`).

Hallazgos nuevos:
- Modelo multivariado (`pila_ini_pct`, `duracion_evento_h`,
  `rate_gap_tph`, `asset`, `regimen`, controlando por los 3 cruces de
  breakpoint ya confirmados) mejora sustancialmente el ajuste en
  calibración (R² 0.234→0.591, LR test p≈0) pero **la mejora en
  hold-out real es mucho menor** (MAE 11.73pp→10.23pp, solo 13% de
  reducción vs. 28% en calibración) — el error genuinamente fuera de
  muestra sigue mayormente sin explicarse por estas variables.
- `pila_ini_pct` y `asset` (SAG2 2.04pp más de bias que SAG1,
  controlando por lo demás) confirmados como predictores nuevos con
  efecto real. `hora_dia` y `feed_restriction_pct` **sin efecto**
  (H0 no rechazada tras corrección Benjamini-Hochberg).
- Tras controlar por las demás variables, `t8_corta` e
  `inventario_critico` **pierden su distintividad como régimen** (el
  dummy de régimen deja de ser significativo) — el MAE crudo más alto
  de `t8_corta` es consistente con que sus eventos parten con pila más
  baja/cruzan más breakpoints, no con un mecanismo exclusivo de la
  ventana T8.
- **Hallazgo negativo más importante**: por régimen, `alimentacion_
  restringida` (N=1.477) generaliza bien (MAE calibración 5.59pp ≈
  hold-out 5.76pp, casi dentro de tolerancia genuinamente fuera de
  muestra), pero `t8_corta` (N=44/19) generaliza muy mal pese a
  R²=0.869 en calibración (MAE se triplica: 3.79pp→11.63pp en
  hold-out) — refuerza que el problema de `t8_corta` no es "variables
  de nivel medio faltantes", sino algo estructural entre calibración y
  hold-out aún sin identificar.

**No se modificó ningún parámetro de calibración ni código de
producción en esta continuación** — solo análisis.

**Síntesis ejecutiva de todo el programa de validación estadística de
hoy** (4 bloques: fidelidad física, motor de recomendaciones, Monte
Carlo, y esta deriva temporal): ver `04_Reports/Technical/
Plan_Mejora_Simulador_2026-07-15.md` — modelo recomendado, riesgos, y
la única acción de mayor ROI para desbloquear el resto del backlog.

**CAUSA PROBABLE ENCONTRADA (2026-07-15, misma fecha, cruce con PAM
Mantto real sugerido por el usuario):** `correa_315` (una de las dos
mediciones de feed que alimenta todo el sistema) cae a **exactamente
cero en el 100% de los 53 días** desde `2026-04-30` en adelante —
la misma fecha del corte de hold-out — mientras `SAG1_tph`/`SAG2_tph`
observados **suben** en ese período (feed medido total −28%, TPH real
SAG1 +60%). Ver `04_Reports/Technical/Diagnostico_Causa_Deriva_
Temporal_PAM.md`. Esto es evidencia fuerte de que la deriva temporal
de hoy **puede ser un artefacto de instrumentación de feed, no un
cambio del proceso físico real** — coincide en fecha con la
intervención "Alimentador 522: estandarización de placas"
(2026-05-01 a 05-08) del PAM Mantto real.

**Confirmado por el usuario y cuantificado (misma pasada, continuación):**
sensor `correa_315` roto desde 2026-04-30 — `SAG1_tph` observado
siguió con rendimiento real (sube, no baja), lo que por el propio
criterio operacional del usuario confirma sensor malo, no correa fuera
de servicio. Reconstruyendo `cv315` con la proporción histórica
`cv315/cv316` (mediana 0.277, período pre-cambio) el MAE de `t8_corta`
hold-out baja de 36.63pp a **27.26pp (−25.6%)** — contribuyente real y
confirmado, pero **no explica el 100%** de la brecha (sigue siendo 2.4x
peor que calibración). Los candidatos del PAM Mantto (retorqueo
trunnion + crash stop SAG1 16-23 abril, estandarización de
alimentadores mayo) siguen vigentes para el residuo restante.

**Reconstrucción final + re-ejecución completa (misma pasada,
continuación final):** se mejoró la reconstrucción (regresión `cv315 ~
correa_316 + SAG1_tph + SAG2_tph`, validada fuera de muestra en una
ventana limpia con R²=0.127 — único de 3 métodos con R² positivo,
alta incertidumbre) sobre **ambas** fuentes afectadas (`advanced_t8_
historical_5min.parquet` y `advanced_t8_event_windows.parquet`, esta
última no detectada antes — usada específicamente por el backtesting
"oficial" de `t8_corta`). Se re-ejecutaron regresión y calibración de
`p_safe` completas:

| Resultado | Original | Corregido |
|---|---:|---:|
| MAE `t8_corta` hold-out (univariado) | 36.63pp | **17.80pp (−51%)** |
| MAE `t8_corta` hold-out (regresión) | 11.63pp | **8.46pp (−27%)** |
| Brier `p_safe` hold-out | 0.621 | **0.004 (casi perfecto)** |

**La calibración de `p_safe` queda prácticamente resuelta** — el
sensor roto explicaba casi toda esa mala calibración. La fidelidad de
pila mejora sustancialmente (−27% a −51% según métrica) pero no se
cierra del todo (sigue 1.6-2.2x peor que calibración, sobre tolerancia
5pp) — residuo consistente con los candidatos del PAM Mantto aún no
confirmados. Scripts: `rebuild_corrected_historical_series.py`,
`build_event_variable_table_corrected.py`. Detalle completo en
`Diagnostico_Causa_Deriva_Temporal_PAM.md`. **No se recalibra ningún
parámetro de producción** — la reconstrucción es diagnóstica (R²=0.127),
no un sustituto del sensor real; próximo paso es obtener la serie
corregida real desde Instrumentación.

**Fase 4B continuación inmediata — deriva temporal sistémica
(2026-07-15, misma pasada):** se comparó la distribución de
covariables entre calibración y hold-out de `t8_corta` para descartar
que el hold-out simplemente tuviera eventos más severos (pila más
baja, más restricción). **Resultado contraintuitivo**: el hold-out
tiene en promedio `rate_gap_tph` y `feed_restriction_pct` *menores*
(menos restrictivos) que calibración, y aun así **100% de los 19
eventos hold-out cruzan el breakpoint del 35%** (vs. 54.5% en
calibración) con errores de −19.9pp a −65.0pp. El mismo corrimiento
aparece, mucho más leve, en `alimentacion_restringida` (39.6%→58.9%)
— **es sistémico, no exclusivo de T8**, pero `t8_corta` es
desproporcionadamente sensible. **Causa física raíz no identificada
esta pasada** — requiere datos operacionales fuera de los datasets
usados (bitácora de mantenciones mayores, cambios de calibración de
instrumentos, o confirmación operacional de algún cambio real entre
2026-05 y 2026-06). Ver `Validacion_Modelos_Regresion.md`, sección 4.
Próximo paso concreto: consultar con Jefe de Sala/Metalurgista si hubo
un cambio operacional conocido en ese período, y considerar un modelo
de efectos mixtos (intercepto aleatorio por régimen) dado el N muy
heterogéneo entre regímenes.

---

### Rama exploratoria — Motor multicelda SAG1/SAG2 (2026-07-15, I+D, no productivo)

**Objetivo del pedido:** evaluar si representar cada pila como varias
celdas locales (SAG1 lineal 4 canales D-C-B-A, SAG2 radial 6 sectores)
en vez de una sola variable agregada mejora la fidelidad y detecta
agotamiento local que el promedio global esconde.

**Implementado (feature-flagged, apagado por defecto):**
`engine/multicell/` (contratos independientes de Dash: `CellState`,
`CellFlow`, `MultiCellPileState`), `engine/stockpile_multicell.py`
(motor físico, balance de masa por celda reusando `update_stockpile_
mass_balance`), integrado en `simulate_scenario`/`simulate_ode` vía
`multicell_enabled=False` por defecto — **el motor agregado sigue
siendo la ruta productiva sin ningún cambio de comportamiento**
(verificado: `mass_balance_error` y pila final idénticos con el flag
apagado).

**Investigación con hold-out temporal real** (`pilas_rendimientos.xlsx`,
calibración ≤2026-04-30 / hold-out >2026-05-01):

| Activo | Evidencia física | Evidencia estadística hold-out | Veredicto |
|---|---|---|---|
| SAG1 (lineal) | Plausible (4 canales, canal C con 50.6% cobertura) | Modelo espacial **empeora** MAE (+71.2 TPH vs. base); controlado por consigna operativa, la espacialidad no ayuda | **No migrar** |
| SAG2 (radial) | Plausible (6 canales, canal 3 sensor congelado) | Mejora parcial e inconsistente por régimen: capacidad espacial mejora `t8_corta`/`alimentacion_restringida`, degrada `inventario_critico`; transferencia lateral (0-0.8/h) sin efecto medible porque la función de capacidad actual solo mira `n_canales_activos` y satura en ≥3 canales (85% del hold-out ya opera con 3-4 canales) | **Prematuro**, mejor candidato de los dos |

**Backtesting hold-out del candidato Fase 1** (multicelda vs. agregado,
mismo split temporal): mejora real pero insuficiente — `t8_corta`
−2.22pp (IC95% bootstrap [−3.16,−1.29], 89.5% de eventos mejoran),
`inventario_critico` −1.77pp, `mantenimiento` −0.68pp,
`alimentacion_restringida` −0.10pp. **Todos los MAE resultantes siguen
muy por encima de la tolerancia de 5pp.**

**Decisión (Opción E — híbrida, la única con soporte parcial de 5
opciones evaluadas)**: mantener el motor agregado como baseline
productivo; tratar el multicelda como línea de I+D focalizada
específicamente en SAG2 + `t8_corta`/`inventario_critico`; no activar
por defecto. Próximo paso de mayor ROI identificado: calibrar la
capacidad espacial de SAG2 **por régimen** (no un set global de
coeficientes) antes de cualquier evaluación adicional.

Reportes: `20260715_Fase1_Multicelda_Pilas_SAG.md`,
`20260715_Investigacion_Multicelda_SAG1_SAG2.md`,
`20260715_SAG2_Transferencia_Lateral_Holdout.md`,
`20260715_SAG2_Capacidad_Espacial_Holdout.md`.
`multicell_baseline_manifest.json` congela la línea base previa a esta
rama. 3 archivos de test nuevos (`test_multicell_contracts.py`,
`test_stockpile_multicell.py`, `test_backtesting_multicell.py`).

---

### Fase 5 — Arquitectura y mantenibilidad

**🛑 SUSPENDIDA explícitamente (2026-07-15).** El nuevo P0 de fidelidad
histórica (Fase 4) se prioriza sobre el refactor arquitectónico —
instrucción explícita del usuario ("Fase 4B — Diagnóstico causal,
recalibración y validación hold-out... Suspende temporalmente la Fase
5"). Orden obligatorio vigente: **Fase 4B (diagnóstico causal) → Fase
4C (recalibración) → Fase 4D (validación hold-out) → Fase 5**. Ver
`04_Reports/Technical/20260715_Diagnostico_Fidelidad_Historica.md` para
el estado de Fase 4B (parcial: línea base + validación de métrica +
cobertura causal cerrada en los 5 regímenes con datos; split temporal y
recalibración experimental ya ejecutados; robustez/modelos candidatos
todavía pendientes).

**Condición para retomar** (ninguna cumplida todavía): (A) todos los
regímenes principales dentro de tolerancia, o (B) aprobación formal
documentando qué regímenes no son confiables, magnitud del error, uso
permitido/prohibido, advertencias en UI, y plan de mejora.

**Objetivo:** reducir deuda técnica sin cambiar resultados físicos.

**Estado real:** NO INICIADA (0/6 pasos) — y suspendida, no solo sin
empezar.

**Métrica de partida (vigente, medida en la auditoría MCP de
2026-07-14, no re-medida en Etapas 1-2 porque no se tocó
`register_simulador_callbacks`):** 1.928 líneas, complejidad ciclomática
85, cognitiva 118, ~76 callees conocidos.

**Riesgo del refactor:** alto — es el archivo más grande y complejo del
repositorio; cualquier extracción debe validarse con la suite completa
(367 tests) y comparación de resultados idénticos antes/después, no solo
"no rompe imports".

**Condición de cierre:** `update_simulation` como orquestador puro
(sin lógica física, sin lógica de recomendación, sin recomputar KPI, sin
construir figuras inline), contratos tipados, trazable por MCP sin
tratar closures como cajas opacas (limitación de la herramienta ya
documentada: closures anidadas de Dash no aparecen como nodos propios en
el grafo).

---

### Fase 6 — UX/UI productiva

**Objetivo:** cerrar la experiencia para uso real del Jefe de Sala.

**Estado real:** EN IMPLEMENTACIÓN parcial (~3/10 criterios).

**Ya hecho:** rediseño de navegación (`components/navigation.py`,
`20260714_Rediseno_Navegacion_UX_Simulador.md`), badges duales de
autonomía con estados categóricos y tooltips (Etapa 1), jerarquía de
decisión (`20260714_Segunda_iteración UX/UI`, ver cleanup_log).

**Sin iniciar/sin evidencia:** validación en las 3 resoluciones
objetivo, modo claro/oscuro completo, sesiones registradas con Jefe de
Sala/Metalurgista/Datos/Operaciones (no existe archivo de resultados de
prueba de usuario en el repo — es una brecha real, no un olvido de
reporte).

**Condición de cierre:** existe validación visual real y feedback de
usuario operativo registrado, no solo tests de layout (`test_layout_
smoke.py`/`test_ux_navigation.py` cubren estructura, no comprensión).

---

### Fase 7 — Limpieza, documentación y gobierno

**Objetivo:** dejar un repositorio mantenible y auditable.

**Estado real:** EN IMPLEMENTACIÓN parcial (~3/8 criterios).

**Ya hecho:** disciplina de `cleanup_log.md` mantenida en cada
modificación de esta serie de sesiones (11 entradas registradas),
consolidación de reportes en archivos existentes en vez de crear nuevos
por pasada.

**Actualizado (2026-07-15, dos continuaciones):** de los 9 candidatos
originales, 4 eliminados (`compute_cv_tph`, `page_simulador`, `read_
jefe_sala_feedback`, `regime_fn_factory`, ver Fase 3 arriba), 2 son
falsos positivos de MCP confirmados con `Grep` (`michaelis_menten`,
`semaforo_autonomia` — se usan como callbacks, el grafo no traza eso),
2 son falsos positivos de JS ya documentados (`scrollToTopOnClick`/
`toggleBackToTop`, event listeners inline). Queda **1 candidato
genuino sin resolver**: `tiempo_hasta_zona` (`02_Analytics/Scripts/
differential_equations/estrategia_pilas.py`) — fuera del alcance del
dashboard, decisión del equipo de analítica. Constantes duplicadas
(`DRAIN_PCT_H`/`CRITICAL_PCT`/`AUTONOMY_THRESHOLDS` en 2 archivos con
los mismos valores) sin centralizar.

**Condición de cierre:** la auditoría de limpieza no encuentra residuos
de riesgo medio/alto sin clasificar — los 9 candidatos originales están
ahora completamente resueltos (4 eliminados, 4 reclasificados como
falsos positivos con evidencia, 1 genuino pendiente de decisión externa
al equipo del simulador). El residuo real de Fase 7 es la centralización
de constantes, no código muerto.

---

### Fase 8 — Liberación productiva

**Objetivo:** preparar la versión candidata a producción.

**Estado real:** NO INICIADA — bloqueada por las Fases 1-7.

**Lo único ya cubierto del checklist:** suite completa (367 tests),
conservación de masa, `.exe`/empaquetado existente (`05_Dashboard/
packaging/`, `release_portable.bat`), `schema_version` en persistencia.

**Condición de release candidate:** 0 P0 abiertos, 0 P1 sin plan
aprobado (este roadmap es ese plan), tests completos aprobados,
validación histórica documentada, validación visual aprobada, working
tree limpio (Fase 0 casi cerrada).

---

## 3. Camino crítico

```text
Fase 0 (tag + checkout limpio)
  → Fase 1 (risk_engine.py primero — es el de mayor acoplamiento real)
    → Fase 2 (consolidar recomendación, depende de que Fase 1 defina qué usa cada regla)
      → Fase 3 (dual score depende de que Fase 2 ya haya fijado la fuente de verdad)
        → Fase 4 (validación histórica, en paralelo posible desde ahora — no depende de 1-3)
          → Fase 5 (refactor arquitectónico, requiere 1-3 cerradas para no refactorizar sobre lógica que aún va a cambiar)
            → Fase 6 (UX final, requiere 1-2 para que los textos de recomendación sean los definitivos)
              → Fase 7 (limpieza final, requiere 1-5 cerradas para no archivar código que aún se está migrando)
                → Fase 8 (release)
```

**Nota:** Fase 4 (validación histórica) **no depende** de las Fases 1-3
y puede ejecutarse en paralelo — es el paralelismo de mayor apalancamiento
disponible hoy.

---

## 4. Quick wins (alto impacto, bajo esfuerzo)

| Quick win | Esfuerzo | Impacto |
|---|---|---|
| Tag de línea base + checkout limpio (cierra Fase 0) | Muy bajo | Desbloquea reproducibilidad formal |
| Clasificar los 2 archivos PNG sueltos sin trackear | Muy bajo | Cierra el único residuo de Fase 0 |
| Decidir destino de las 4 funciones de recomendación en estado sombra (Fase 2) | Bajo (es una decisión + `git rm`/`git mv` a archivo, no una reescritura) | Elimina ambigüedad de "qué motor es el real" para cualquier futura sesión |
| Documentar `ONE_BALL_CAPACITY_FACTOR` como "no calibrado" explícitamente en UI/docs (sin activar `enforce_downstream_ball_capacity`) | Muy bajo | Evita que una futura sesión lo trate como calibrado por error |
| ~~Archivar/eliminar los 9 candidatos de código muerto confirmados~~ | Bajo-medio | ✅ Resuelto (2026-07-15): 4 eliminados, 4 reclasificados como falsos positivos de MCP (verificados con `Grep`), 1 genuino pendiente de decisión del equipo de analítica (`tiempo_hasta_zona`, fuera de `05_Dashboard/`) |
| ~~Centralizar `DRAIN_PCT_H`/`CRITICAL_PCT`/`AUTONOMY_THRESHOLDS` en un único módulo~~ | Medio | ✅ Resuelto (2026-07-15): la única duplicación literal real era `_DRAIN_RATE`/`_CRITICAL_PCT` en `components/cards.py` (copia exacta de `DRAIN_PCT_H`/`CRITICAL_PCT` de `ode_model.py`) — reemplazada por import directo (`from engine.ode_model import CRITICAL_PCT as _CRITICAL_PCT, DRAIN_PCT_H as _DRAIN_RATE`), sin riesgo de import circular verificado. `AUTONOMY_THRESHOLDS` (`rules_engine.py`) no estaba duplicado, solo existía en un lugar |

---

## 5. Riesgos

**Técnicos:**
- Refactor de `register_simulador_callbacks` (complejidad 85) sin tests de regresión de resultado idéntico puede introducir bugs invisibles a la suite actual (que valida comportamiento, no necesariamente cada rama de UI).
- Migrar `risk_engine.py` sin comparar IRO antes/después puede cambiar silenciosamente la clasificación de riesgo mostrada al JdS (mismo error que se evitó en Etapa 1/2 con la compatibilidad aditiva).
- Consolidar el motor de recomendación (Fase 2) sin decidir primero el destino de `rank_candidates` (que sí tiene 2 consumidores reales, a diferencia de las otras 3 funciones sombra) puede romper un caller activo si se archiva sin verificar.

**Operacionales:**
- Ningún P0/P1 de esta lista tiene fecha de JdS/Metalurgista/Operaciones para validación de UX — la Fase 6 puede bloquearse por disponibilidad de personas, no por trabajo técnico.
- `ONE_BALL_CAPACITY_FACTOR` no calibrado sigue siendo opt-in (`enforce_downstream_ball_capacity=False` por defecto) — riesgo bajo mientras no se active, pero cualquier sesión futura que lo active sin calibrar reintroduce el problema que el reencuadre de autonomía ya resolvió para `DRAIN_PCT_H`.

**De datos:**
- La validación histórica formal (Fase 4) depende de tener suficientes eventos reales por bucket de ventana (0/2/4/8/12h) — la auditoría de `20260625_Pilas_Descarga_Robusto.md` ya mostró que algunos buckets tienen "confianza baja" (N=2-4 eventos) — el hold-out puede no ser estadísticamente robusto en esos buckets sin más datos acumulados.

---

## 6. Panel maestro de avance

| Fase | Estado | % | P0 | P1 | Dependencia | Evidencia |
|---|---|---:|---:|---:|---|---|
| 0. Reproducibilidad | CERRADA | 100% (5/5) | 0 | 0 | — | `73b7128`+`c3094a1`, tag `simulator-autonomy-stage2-baseline`, `pytest` 367 passed, working tree limpio |
| 1. Correctitud operacional | **CERRADA** | 100% (7/7) | 0 | 0 | Fase 0 (✅) | 389 tests totales (22 nuevos), estudio de sensibilidad real documentado |
| 2. Recomendaciones | EN IMPLEMENTACIÓN | 50% (2/5 funciones sombra resueltas + validación con escenarios dorados 4/5, `RecommendationService` sin diseñar) | 0 | 2 | Fase 1 (parcial) | `recommend_rate` x2 eliminadas (367 tests OK), `rank_candidates` clasificada, `generate_operational_recommendation` diferida a Fase 5; `Validacion_Motor_Recomendaciones.md` — gap real de overflow con SAG apagado confirmado y documentado como xfail |
| 3. Optimización | **CERRADA** | 100% (3.1-3.6 completas; confirmado empíricamente que V3 hereda el dual score sin migración propia) | 0 | 1 (decisión de producto diferida, no técnica) | Fase 2 | `test_optimizer_v2_dual_score.py` (13 tests), `ranking_diverges=True` real medido, `p_safe`/`p_dynamic_safe` divergen en MC y en V3 (verificado con ejecución real) |
| 4. Validación histórica | EN IMPLEMENTACIÓN | 92% (línea base + metodología + cobertura causal cerrada + split temporal real + recalibración experimental/hold-out ejecutados + sensibilidad contrafactual de `_pile_feedback_factor` + regresión multivariada formal; falta explicar la brecha de generalización de `t8_corta`) | 1 | 2 | ninguna (paralelizable) | `20260715_Diagnostico_Fidelidad_Historica.md`, `Validacion_Modelos_Regresion.md`, `_pile_feedback_factor` explica 1.9-8.3x el error cuando se activa, `overflow` confirma especificidad, el hold-out original queda descartado (72/72 contaminados), `DRAIN_PCT_H` descartado como palanca, `pila_ini_pct`/`asset` confirmados como predictores nuevos (regresión, ΔR²=0.357 en calibración, mucho menor en hold-out) |
| 5. Arquitectura | **SUSPENDIDA** | 0% (0/6) | 0 | 0 (bloqueada por Fase 4) | Fase 4B-4D completas | Instrucción explícita: no refactorizar hasta validar/aceptar fidelidad histórica |
| Rama — Motor multicelda | I+D, NO productivo | Investigación completa, decisión tomada (no migrar) | 0 | 1 | ninguna (paralela) | 4 reportes + hold-out real; SAG1 descartado, SAG2 candidato parcial pendiente de calibración por régimen |
| 6. UX/UI | EN IMPLEMENTACIÓN | 30% (3/10) | 0 | 2 | Fase 2 (parcial) | Navegación + badges Etapa 1 hechos; sin validación de usuario |
| 7. Limpieza/documentación | EN IMPLEMENTACIÓN | 85% (7/8) | 0 | 1 | Fases 1-5 | cleanup_log.md activo; 9/9 candidatos de código muerto resueltos; `rank_candidates` confirmado activo (1 caller real); `ONE_BALL_CAPACITY_FACTOR` advertido en `README_USUARIO.md`; constantes duplicadas centralizadas; `CHANGELOG.md` raíz sincronizado (v7/v8, cubre desde `73b7128` hasta hoy — antes se detenía en 2026-07-06); falta manual técnico y decidir/aplicar número de versión (raíz `VERSION.txt` en 1.0.0 vs. `packaging/VERSION.txt` en 1.3.0, desincronizados — decisión de release, no técnica) |
| 8. Release | NO INICIADA | 0% | 0 | 0 (bloqueada) | Fases 0-7 | — |

---

## 7. Matriz de bloqueos

| Bloqueo | Fase afectada | Responsable | Evidencia necesaria | Acción |
|---|---|---|---|---|
| ~~Sin tag de línea base~~ | 0 | Técnico | — | ✅ Resuelto: tag `simulator-autonomy-stage2-baseline` creado sobre `73b7128` |
| ~~2 archivos PNG sin clasificar~~ | 0 | Técnico/Producto | — | ✅ Resuelto: clasificados como activos legítimos, commiteados en `c3094a1` |
| ~~`risk_engine.py` sin auditar comparación antes/después~~ | 1 | Técnico | — | ✅ Resuelto: Fase 1.1 completa, IRO total idéntico verificado con test |
| ~~`rank_candidates` con 2 callers reales sin identificar~~ | 2 | Técnico | — | ✅ Resuelto (2026-07-15, verificación directa con `Grep`): tras eliminar `recommend_rate` (su único otro caller), queda exactamente **1 caller de producción real** (`pages/simulador_operacional.py:2550`, tabla de comparación de escenarios). Función activa, no se archiva |
| **El modelo falla su propia tolerancia (5pp MAE) en 4/5 regímenes con datos** | 4 | Datos/Producto | MAE/bias/std ya medidos y documentados (esta pasada) | **P0 real**: mover la causa raíz hacia dinámicas que expliquen por qué el motor entra a zona de pila baja con tanto sesgo (alineación temporal, variación intra-evento, cambios de régimen), no seguir persiguiendo palancas ya descartadas |
| `DRAIN_PCT_H` no mejora el P0 de fidelidad de pila | 4 | Datos | ✅ Ya medido: recalibrado con cutoff `2026-04-30` deja igual el MAE de pila (11.21pp calibración, 36.63pp hold-out) y empeora `error_tiempo_critico_h` | No invertir más iteraciones de MAE de pila en esta constante; mover foco a mecanismos que sí alteran `pile_sag1` |
| Relajar `_pile_feedback_factor` tampoco mejora el P0 | 4 | Datos | ✅ Ya medido: en `t8_corta` hold-out, escalar el feedback a 75/50/25/0% empeora el MAE 36.63 -> 37.59 -> 38.43 -> 38.98 -> 39.26pp | No intentar una “recalibración rápida” por simple atenuación o apagado; buscar la causa aguas arriba del ingreso a zona baja |
| Sin dato histórico suficiente en buckets 0-2h/3-6h/>12h | 4 | Datos | N por bucket (ya documentado: N=2-4 en varios) | Definir si se usa tasa global de respaldo o se recolecta más data |
| Sin sesión de validación JdS/Metalurgista/Datos/Operaciones | 6 | Producto | Registro de tarea/tiempo/errores/decisión | Agendar al menos 1 sesión por rol |
| `ONE_BALL_CAPACITY_FACTOR` no calibrado | 4/8 | Datos | Comparación eventos reales 2/1/0 bolas por SAG | Ruta concreta identificada: adaptar `02_Analytics/Scripts/calibrar_bola_delta_tph.py` (Fase 4.2, sin fecha aún) |
| MCP no ve cambios sin commitear | Todas | Técnico | — | Ya mitigado: commitear con frecuencia + cruzar con lectura directa (práctica ya en uso desde Etapa 1) |

---

## 8. Definición de terminado por dimensión

**Terminado físicamente:** balance de masa correcto (✅ ya cumplido,
1e-10 t), inventario nunca negativo (✅), capacidad máxima respetada
(✅), rates limitados por disponibilidad (✅), estados de equipos
coherentes (✅). **Esta dimensión ya está cerrada.**

**Terminado operacionalmente:** riesgo inmediato usa dinámica (⚠️
parcial — solo `recommend_action`, no `risk_engine.py`), vulnerabilidad
usa histórica (✅), recomendaciones cuantificadas (✅ para
`recommend_action`), escenarios complejos representables (✅), no
existen mensajes contradictorios (⚠️ parcial — ver riesgo residual de
Etapa 2: IRO y recomendación pueden divergir hasta que Fase 1 cierre).

**Terminado estadísticamente:** parámetros críticos calibrados (⚠️
`DRAIN_PCT_H` sí, `ONE_BALL_CAPACITY_FACTOR` no), backtesting hold-out
(❌ no existe separación formal), errores conocidos (❌ no publicados),
incertidumbre documentada (⚠️ parcial), `p_safe` interpretado
correctamente (⚠️ no comparado contra frecuencia real).

**Terminado arquitectónicamente:** callback desacoplado (❌,
complejidad 85 sin tocar), contratos tipados (❌), funciones sombra
resueltas (❌ 4 confirmadas, 0 resueltas), constantes centralizadas (❌
duplicadas confirmado), grafo MCP trazable (⚠️ limitación de closures
Dash documentada, no resuelta).

**Terminado en UX:** lectura en menos de 10s (⚠️ no medido con
usuarios reales), navegación sin fricción (✅ rediseñada), resoluciones
validadas (❌), feedback de usuarios (❌ sin registro), modo claro/
oscuro estable (⚠️ parcial).

**Terminado como producto:** versión (✅ `VERSION.txt`), changelog (⚠️
parcial, no consolidado), manual (⚠️ solo `README_USUARIO.md`), `.exe`
(✅ `packaging/`), pruebas (✅ 367 passed), release reproducible (⚠️
falta tag), riesgos residuales aceptados (⚠️ documentados pero no
"aceptados" formalmente por el usuario/producto).

---

## 9. Checklist de release

**Código:** working tree casi limpio (2 archivos sueltos) ⚠️ | commit
reproducible ✅ (`73b7128`) | versión actualizada ⚠️ (verificar
`VERSION.txt` vs. este roadmap) | schema version revisado ✅ | changelog
completo ❌.

**Física:** conservación de masa ✅ | no inventario negativo ✅ | no
consumo inexistente ✅ | límites de capacidad ✅ | dependencias
SAG-bolas ✅. **Dimensión física: lista para release.**

**Operación:** escenarios críticos ✅ (probados en Etapas 1-2) |
ventanas ✅ | recovery ✅ | SAG OFF ✅ | bolas OFF ✅ (Regla 16) |
overflow ✅ | starvation ✅ | recomendaciones ⚠️ (solo `recommend_action`
migrado, resto en legacy).

**Estadística:** backtesting ❌ (hold-out no formalmente separado en
producción, aunque ya validado experimentalmente) | calibración ⚠️
(parcial — `p_safe` prácticamente resuelto tras corrección de
`correa_315`, Brier hold-out 0.004; MAE de pila sigue sobre tolerancia)
| Monte Carlo ⚠️ (sigmas no calibrados desde históricos, a propósito no
recalibrados hasta cerrar la deriva temporal) | errores conocidos ✅
(publicados en `20260715_Diagnostico_Fidelidad_Historica.md`/
`Plan_Mejora_Simulador_2026-07-15.md`, no ❌).

**UX:** resoluciones objetivo ❌ | modo claro/oscuro ⚠️ | accesibilidad
❌ (sin auditoría) | validación de usuarios ❌.

**Software:** suite completa ✅ (367 passed) | tests portables ⚠️
(existen pero con timing sensible al entorno, ver hallazgo de suspensión
de equipo en Etapa 1) | `.exe` ✅ | arranque limpio ⚠️ (sin verificar en
esta pasada) | estado persistido ✅ | caché ✅ | performance ⚠️ (SLA de
3s documentado como no aplicable para `find_optimal_v3`, sin resolver).

**Documentación:** manual técnico ❌ | manual JdS ⚠️ (parcial) |
supuestos ⚠️ (parcial, en reportes dispersos) | limitaciones ⚠️ | 
parámetros no calibrados ✅ (recién identificados en esta pasada) |
riesgos residuales ✅ (documentados en cada reporte de esta serie).

---

## 10. Condición final de cierre

**El simulador NO está terminado mientras exista cualquiera de estas
condiciones** (estado real de cada una, verificado hoy):

| Condición de no-cierre | ¿Presente hoy? |
|---|---|
| P0 abierto | **Parcialmente resuelto, con reencuadre importante (actualizado 2026-07-15, hallazgo `correa_315` + contaminación de eventos SAG1 apagado)**: dos causas raíz confirmadas. (1) sensor `correa_315` roto desde `2026-04-30` (confirmado por el usuario) — reconstruyéndolo y re-ejecutando, `p_safe` hold-out queda prácticamente resuelto (Brier 0.621→0.004) y MAE `t8_corta` hold-out baja de 36.63pp a 17.80-8.46pp. (2) **más grande**: 68% de los eventos de *calibración* de `t8_corta` tienen SAG1 apagado durante la ventana T8 (vs. 10% en hold-out) — son eventos triviales (MAE 2.7pp, la pila casi no se mueve) que abaratan artificialmente el MAE de calibración reportado (11.21pp). Comparando solo eventos con SAG1 genuinamente operando en ambos lados, la brecha calibración-vs-hold-out baja de "3.3x" a "1.5x" (26.12pp vs. 39.58pp) — **pero ambos números siguen muy sobre la tolerancia de 5pp**, así que el P0 de fidelidad física sigue abierto, ahora con una causa compositional adicional y mejor delimitada. Ver `Diagnostico_Causa_Deriva_Temporal_PAM.md` |
| Recomendación contradictoria | **Resuelto para el motor de decisión** — Fase 1 completa (7/7): `risk_engine.py`, `bottleneck.py`, `quick_wins.py`, `hourly_plan.py` ya exponen el desglose dinámico/histórico de forma explícita, sin ambigüedad de fuente |
| Autonomía ambigua | No — resuelto en Etapa 1 (nomenclatura) y Etapa 2 parcial (decisión) |
| Parámetro crítico sin calibración ni advertencia | **Parcialmente resuelto** — `ONE_BALL_CAPACITY_FACTOR` sigue sin calibrar pero con advertencia explícita y ruta concreta identificada (reusar `calibrar_bola_delta_tph.py`); `VENTANA_FACTOR_ESTADO`/`_pile_feedback_factor`/sigmas MC confirmados sin calibrar esta pasada (nuevo hallazgo, sin advertencia todavía) |
| Ausencia de backtesting hold-out | **Parcialmente resuelto** — el backtesting productivo sigue sin hold-out, pero ya existe un split experimental real (`2026-04-30`) con 22 eventos oficiales posteriores y una primera corrida fuera de muestra |
| Working tree no reproducible | **Resuelto** — commit `73b7128`+..., tag `simulator-autonomy-stage2-baseline` creado, working tree limpio |
| UX no validada | **Sí** — sin sesiones de usuario registradas |
| Función sombra sin decisión | **Parcialmente resuelto** — 2 de 4 funciones eliminadas con evidencia; `rank_candidates` clasificada como activa; `generate_operational_recommendation` diferida a Fase 5 con justificación; V4/V5 con decisión explícita (no acción, documentada) |
| Pruebas o empaquetado fallidos | No — 405/405 passed, `.exe` existe |

**Conclusión explícita (actualizada 2026-07-15, cierre de pasada):** el
simulador **aún no puede declararse terminado**, pero el P0 de
fidelidad cambió de naturaleza: pasó de "causa raíz desconocida" a
"causa raíz probable identificada y cuantificada, corrección real
disponible pero fuera del alcance de código" (sensor `correa_315`
roto). `p_safe` — la señal que el Jefe de Sala realmente consume — se
trata como sustancialmente resuelto (Brier hold-out 0.004). El residuo
de fidelidad de pila (1.6-2.2x sobre tolerancia) requiere la serie real
de Instrumentación para cerrarse, y los candidatos del PAM Mantto
(retorqueo trunnion + crash stop SAG1, estandarización de
alimentadores) siguen vigentes para lo que esa serie no explique.
De las 9 condiciones de bloqueo originales: **3 completamente
resueltas** (working tree, autonomía ambigua, recomendación
contradictoria en el motor de decisión), **1 sustancialmente resuelta**
(`p_safe`, dentro del P0), **3 parcialmente resueltas** (parámetro sin
calibrar, función sombra sin decisión, hold-out — confirmado como
problema real y con causa raíz probable), y **2 sin tocar** (UX no
validada, requiere personas; el residuo de fidelidad de pila, requiere
dato externo de Instrumentación). El camino a cierre real ya no es
"investigar causa raíz" — es **obtener la serie corregida real de
`correa_315`** y decidir con el Jefe de Sala/Metalurgista si el residuo
restante (PAM Mantto) se acepta como riesgo documentado o se sigue
investigando.

El cierre real ocurrirá cuando se cumplan simultáneamente: correctitud
física (✅ ya cumplida) + coherencia operacional (⚠️ parcial, Fase 1) +
validación histórica (❌, Fase 4) + recomendación trazable (⚠️ parcial,
Fase 2) + arquitectura mantenible (❌, Fase 5) + UX validada (❌, Fase 6)
+ release reproducible (⚠️ casi, Fase 0).
