# Registro de limpieza recurrente

Log liviano de cada ciclo de limpieza (uno por tarea/modificación, no un
reporte extenso). Ver `cleanup_plan.md` (raíz del repo) para el inventario
completo de la primera pasada integral.

---

## 2026-07-14 — Primera pasada integral (04_Reports/ + 05_Dashboard/)

**Modificación asociada:** cierre de la Fase 2 del simulador operacional
SAG (kernel `engine/circuit_state.py`, ver
`04_Reports/Technical/20260714_Logica_Operacional_Pilas_SAG.md`).

**Archivos creados:**
- `cleanup_plan.md` (raíz) — inventario y clasificación de la primera pasada.
- `06_Documentation/cleanup_log.md` (este archivo).

**Archivos archivados** (`git mv`, no eliminados — conservan valor de
auditoría del historial de iteración):
- `04_Reports/Technical/02_EventStudy_T8/20260625_EventStudy_T8_Ejecutivo_v1.md` → `04_Reports/Technical/99_Historicos/`
- `04_Reports/Technical/02_EventStudy_T8/20260625_EventStudy_T8_Tecnico_v1.md` → `04_Reports/Technical/99_Historicos/`
- `04_Reports/Technical/06_SHAP/20260625_SHAP_Explainability_v1.md` → `04_Reports/Technical/99_Historicos/`

**Archivos destrackeados** (`git rm --cached`, se quedan en disco local):
- `05_Dashboard/outputs/logs/20260701_optimizer_v3_integration.md` (quedó
  trackeado antes de que `outputs/logs/` se agregara a `.gitignore`).

**Archivos eliminados:** ninguno en esta pasada.

**Pendiente de revisión manual** (ver `cleanup_plan.md` para el detalle):
`08_Modelo_Causal/` vs `09_Modelo_Causal_Final/`, los 2 reportes
"Efecto Gaviota", y la ubicación de
`05_Dashboard/dist/_backups/Gemelo_Digital_Molienda_v1_1_0_APROBADO_20260706.zip`
(entregable aprobado dentro de una carpeta gitignoreada como build).

**Fuera de alcance:** `01_Data/`, `03_Models/` (datos/modelos activos de
esta misma rama, requieren trazabilidad de calibración antes de auditar).

**Pruebas ejecutadas después de la limpieza:**
`python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py`
→ 319 passed, 0 failed. `import pages.simulador_operacional` → OK.
Ninguna ruta rota encontrada (`grep` de las rutas antiguas de los 4
archivos movidos/destrackeados en todo el repo, solo aparecen en este
mismo log y en `cleanup_plan.md`).

**Espacio liberado:** ~0 MB (solo se movieron/destrackearon archivos de
texto pequeños; no se eliminó contenido).

---

## 2026-07-14 — Segunda pasada: inventario completo con hashes SHA-256

**Modificación asociada:** ampliación explícita del alcance a pedido del
usuario, incluyendo `01_Data/`/`03_Models/`/`99_Archive/` (previamente
fuera de alcance en la primera pasada).

**Inventario:** 4780 archivos, 1.55 GB totales (excluye `.git/`). Ver
`cleanup_plan.md` sección "Segunda pasada" para el detalle completo por
extensión/carpeta.

**Archivos eliminados** (147, vía cuarentena `_cleanup_quarantine/` →
pruebas → borrado definitivo, protocolo de riesgo medio del propio
usuario):
- `99_Archive/figures/**` (~90 PNG, 0 trackeados en git) — duplicados
  byte a byte de `02_Analytics/Figures/**`.
- `99_Archive/reports/*.md` (11, trackeados) + `*.pdf`/`*.pptx` (6, no
  trackeados) — duplicados byte a byte de `04_Reports/Technical/**`.
- `99_Archive/Usersjorel038AppDataLocalTemp*.txt` (6, trackeados) —
  volcados de depuración sin valor interpretativo.
- `-CO0000330678.gitignore` (raíz, no trackeado) — copia huérfana de
  conflicto de sincronización de OneDrive, contenido subconjunto
  desactualizado del `.gitignore` vigente.

**Archivos consolidados:** ninguno adicional (la consolidación de
reportes ya se hizo en la primera pasada).

**Archivos archivados:** ninguno adicional en esta pasada.

**Pendiente de revisión manual** (nuevo, ver `cleanup_plan.md`):
`Threshold_SAG1.png`/`Threshold_SAG2.png` son byte-idénticos entre sí
(posible bug del script generador); 2 capturas UX con nombres distintos
pero contenido idéntico; carpeta `advanced_t8_historical` duplicada en
dos ubicaciones dentro de `02_Analytics/Figures/`.

**Fuera de alcance confirmado:** ningún archivo dentro de `01_Data/` o
`03_Models/` calificó como duplicado exacto verificado — no se tocó
ninguno. El resto de `99_Archive/` (`catboost_info_*`, `models_duplicate/`,
`notebooks/`, `scripts/`) tampoco tuvo coincidencia de hash — se conserva
sin tocar.

**Pruebas ejecutadas después de la limpieza:**
`python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py`
→ 319 passed. `import app` (carga histórico + precomputa figuras) → OK.
`import pages.simulador_operacional` → OK. 0 rutas rotas encontradas.

**Espacio liberado:** 33.0 MB (`99_Archive/` pasó de 55.7 MB a 22.0 MB).

---

## 2026-07-14 — Rediseño de navegación/UX del Simulador Operacional

**Modificación asociada:** fix del patrón "seleccionar vista abajo →
scroll arriba → ver gráfico" reportado sobre `01_Data/Raw/graficos y
botones.pdf`. Ver `04_Reports/Technical/
20260714_Rediseno_Navegacion_UX_Simulador.md` (reporte único y
consolidado del tema, no se crearon reportes parciales adicionales).

**Archivos creados:**
- `components/navigation.py` — NAV_SECTIONS/CHART_TABS centralizados, barra sticky, botones de navegación contextual.
- `assets/back_to_top.js` — listener JS nativo (no clientside_callback, ver motivo en el reporte).
- `tests/test_ux_navigation.py` — 12 pruebas de estructura.

**Archivos modificados:** `pages/simulador_operacional.py` (selector de
vista movido junto al gráfico, anclas de sección, grid de tarjetas),
`assets/styles.css` (CSS de navegación, aislado del bug sticky de
2026-07-07).

**Archivos eliminados:** ninguno.

**Código muerto detectado y corregido en esta misma pasada:** 2 líneas
de artefacto de redacción (`if False else None`) en el test nuevo,
corregidas antes de correr la suite — no llegaron a quedar commiteadas
sin revisar.

**Pruebas ejecutadas después de la limpieza:**
`python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py`
→ 331 passed (319 preexistentes + 12 nuevas). `import app` → OK.

**Espacio liberado:** no aplica (cambio de código/CSS, sin artefactos binarios).

**Riesgo residual declarado:** confirmación visual en navegador real
(1920×1080/1600×900/1366×768) pendiente del usuario — no hay herramienta
de captura en este entorno; ver reporte para el detalle.

---

## 2026-07-14 — Segunda iteración UX/UI: jerarquía de decisión

**Modificación asociada:** Decision Banner, selector de circuito
(visual), categorías de gráfico, semáforo de 5 niveles, marcas de
evento y tooltips enriquecidos. Ver
`04_Reports/Technical/20260714_Rediseno_Navegacion_UX_Simulador.md`,
sección "Segunda iteración" (mismo reporte consolidado, no uno nuevo).

**Archivos creados:** `components/navigation.py` (extendido, ya
existía), `tests/test_decision_hierarchy.py`. Sin archivos nuevos fuera
de código fuente/tests.

**Archivos modificados:** `components/cards.py`, `components/graphs.py`,
`pages/simulador_operacional.py`, `assets/styles.css`.

**Archivos temporales generados y descartados (nunca commiteados):**
- Script de verificación de contraste WCAG (scratchpad de la sesión).
- Servidor de smoke test en puerto 8051 — iniciado para verificar que
  la app real arranca sin errores tras el cambio (`_dash-layout`,
  `_dash-dependencies`), detenido por su PID específico al terminar
  (nunca se tocó el proceso preexistente en el puerto 8050).

**Corrección real encontrada durante este ciclo (no solo verificación):**
el script de contraste detectó que `ROJO` (#E94A4A) en texto pequeño
(severidad del banner, "Baja" de la tarjeta de confianza) daba 3.99:1,
bajo el umbral AA de 4.5:1 — se agregó `ROJO_TEXTO_PEQUENO` (#F0605C,
4.70:1) para esos dos usos específicos, sin tocar el `ROJO` global (que
sigue siendo correcto en los usos de texto grande ya existentes).

**Pruebas ejecutadas después de la limpieza:**
`python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py`
→ 346 passed (331 + 15 nuevas). Smoke check HTTP de la app real: `/` →
200, `_dash-layout` serializa sin error, `_dash-dependencies` confirma
28 callbacks registrados.

**Espacio liberado:** no aplica (cambio de código/CSS).

---

## 2026-07-14 — Auditoría estructural (sin codebase-memory-mcp)

**Modificación asociada:** ninguna (tarea de solo diagnóstico, cero
cambios de código). Ver
`04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md`.

**Archivos creados:** el reporte anterior únicamente.

**Archivos temporales generados y descartados (scratchpad, nunca
commiteados):** `ast_index.py`, `ast_analyze.py`, `result_ast_index.json`
(~700 KB), `ast_analyze_output.txt` — indexador AST propio usado como
sustituto declarado de `codebase-memory-mcp` (no instalado; ver reporte
para el detalle de por qué no se instaló en esta sesión).

**Pruebas ejecutadas:** no aplica (sin cambios de código).

**Espacio liberado:** no aplica.

---

## 2026-07-14 — Arquitecto Principal: 5 fichas de diseño + implementación P0-1

**Modificación asociada:** modo "Arquitecto Principal" con navegación
MCP-first estricta sobre un backlog de 5 mejoras. Plan aprobado antes de
implementar. Ver `04_Reports/Technical/
20260714_Auditoria_Estructural_Simulador.md`, sección "Tercera pasada".

**Archivos modificados:** `components/cards.py`
(`make_autonomia_resumen_card`, 2 parámetros opcionales nuevos),
`pages/simulador_operacional.py` (2 call sites actualizados).

**Implementado:** P0-1 Opción A — surfacear el flag de divergencia de
autonomía (`autonomy_diverges_sagX`/`autonomy_diff_sagX_h`) que ya se
calculaba desde la Fase 2 de esta sesión pero solo llegaba a un
`logging.debug()` invisible. Cero cambios a `compute_autonomia`,
`calculate_stockpile_autonomy`, ni a sus callers de producción.

**Diferido (con ficha de diagnóstico+evidencia+diseño completa, sin
implementar):** P0-1 opciones B/C, P0-2 (capacidad de bolas —
`BOLA_DELTA_TPH` ya calibrado vs `ONE_BALL_CAPACITY_FACTOR` no
calibrado), P1-1 (ventanas múltiples en UI), P1-2 (sigmas Monte Carlo),
P2 (refactor de `update_simulation`, medido en 1.928 líneas/complejidad
ciclomática 85 vía MCP sin abrir el archivo).

**Hallazgo importante encontrado en la validación (no en el diseño
original):** la divergencia de autonomía es sistemática y de gran
magnitud (ej. 0.36h vs 143h en el escenario más benigno probado),
divergió en los 3 escenarios probados — riesgo real de fatiga de alarma
si se muestra sin más contexto. Documentado como hallazgo prioritario,
no ajustado sin datos históricos que respalden un nuevo umbral.

**Pruebas ejecutadas:** `python -m pytest tests -q
--ignore=tests/test_performance_portable.py
--ignore=tests/test_portable_smoke.py` → 346 passed. Validación directa
con `simulate_scenario_cached` en 3 escenarios. `query_graph` tras
re-indexar confirma cero acoplamiento nuevo en
`make_autonomia_resumen_card`.

**Espacio liberado:** no aplica.

---

## 2026-07-14 — Auditoría estructural, segunda pasada (con codebase-memory-mcp real)

**Modificación asociada:** ninguna (diagnóstico). El usuario instaló
`codebase-memory-mcp 0.9.0` en su propia terminal (instalador oficial,
revisado antes de correr) y reinició Claude Code; se repitió la
auditoría con la herramienta real y se actualizó el mismo reporte de la
pasada anterior (no se creó un archivo nuevo). Ver
`04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md`,
sección "Segunda pasada".

**Artefactos generados:** ninguno en el repositorio —
`index_repository` se ejecutó con `persistence=false`; confirmado que
no existe carpeta `.codebase-memory/` en la raíz tras indexar.

**Hallazgos nuevos respecto a la primera pasada (AST):** 2 candidatos a
código muerto adicionales confirmados (`compute_cv_tph` en
`engine/ode_model.py`, `read_jefe_sala_feedback` en
`validation/feedback_form.py`); confirmación doble del duplicado
`recommend_rate`; uso más amplio de lo documentado para
`simulate_scenario_cached` (también consumido desde `app.py` y scripts
de diagnóstico/backtesting, no solo el Simulador Operacional).

**Discrepancias de herramienta documentadas** (no ocultadas): `trace_path`
no resuelve funciones anidadas profundamente (`update_simulation` y el
resto de los callbacks de `pages/simulador_operacional.py` no existen
como nodos propios en el grafo) ni relaciones cross-file que el LSP solo
pudo confirmar a nivel de archivo (`USAGE`, no `CALLS`) — mitigado
usando `query_graph` con Cypher directo (`CALLS|USAGE`) en su lugar.

**Pruebas ejecutadas:** no aplica (sin cambios de código).

**Espacio liberado:** no aplica.

---

## 2026-07-14 — Causa raíz de divergencia 100% autonomía legacy vs balance neto

**Modificación asociada:** ninguna (investigación pedida explícitamente
por el usuario tras la Ficha 1 de P0-1: "si, dale con la
investigación"). Sin cambios de código. Resultado agregado a
`04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md`,
sección "Cuarta pasada — causa raíz de la divergencia 100% (P0-1,
seguimiento)".

**Método:** MCP-first (`get_code_snippet` de `compute_autonomia` y
`calculate_stockpile_autonomy`, `search_code`/`Grep` sobre los reportes
de calibración de `DRAIN_PCT_H` y sobre el consumidor real
`_tiempo_hasta_umbral`), sin abrir archivos completos sin evidencia
previa.

**Hallazgo:** no es un bug ni una miscalibración — las dos fórmulas
responden preguntas distintas por diseño. `compute_autonomia` usa una
tasa de drenaje **histórica fija** (`DRAIN_PCT_H`, calibrada sobre 27
episodios reales de descarga, bucket 7-12h) y responde "si ahora
empezara un evento de drenaje típico, cuánto dura la pila" —
independiente de si la pila está drenando en ese instante.
`calculate_stockpile_autonomy` usa el flujo neto **real** del paso
simulado y devuelve `None` ("sin riesgo") si la pila no está
efectivamente drenando. Confirmado que uno de los 5 consumidores reales
de `compute_autonomia` (`historical_backtesting.py::
_tiempo_hasta_umbral`) la usa como un umbral de % de pila fijo
disfrazado de horas, consistente con este diseño. El 100% de divergencia
medido en la Ficha 1 es la consecuencia esperada de comparar
directamente una alerta de peor-caso contra una proyección de
caso-actual con un único `threshold_h`.

**Recomendación entregada (no implementada, pendiente de decisión del
usuario):** no ajustar `threshold_h`; reencuadrar las dos métricas como
señales complementarias con nombres que reflejen su semántica real, o
limitar el flag de divergencia al caso en que ambas fuentes miden la
misma condición (pila realmente drenando). Implica revisar el badge de
P0-1 Opción A ya en producción — explícitamente diferido, no tocado en
esta pasada.

**Pruebas ejecutadas:** no aplica (sin cambios de código).

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Reencuadre semántico de autonomía, Etapa 1 (implementado)

**Modificación asociada:** separación formal de "autonomía preventiva
histórica" y "autonomía dinámica actual" pedida explícitamente por el
usuario tras revisar la evidencia de causa raíz. Plan aprobado en modo
plan (`C:\Users\jorel038\.claude\plans\happy-prancing-pelican.md`).
Detalle completo en
`04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md`,
sección "Quinta pasada".

**Archivos modificados:** `05_Dashboard/engine/circuit_state.py`
(`AT_CRITICAL_LEVEL`, `DynamicAutonomyResult`, `classify_dynamic_
autonomy`, `classify_historical_vulnerability`, `classify_autonomy_
divergence` — todo aditivo, nada existente cambia), `05_Dashboard/
engine/ode_model.py::simulate_ode` (14 claves nuevas en el dict de
retorno), `05_Dashboard/components/cards.py::make_autonomia_resumen_
card` (5 parámetros opcionales nuevos, comportamiento previo intacto si
no se pasan), `05_Dashboard/pages/simulador_operacional.py` (2 llamados
actualizados), `05_Dashboard/components/graphs.py::make_autonomia_chart`
(relabel + marcador dinámico puntual), `05_Dashboard/engine/
historical_backtesting.py` (solo docstring, cero cambio de
comportamiento), `05_Dashboard/tests/test_circuit_state_phase2.py`
(+14 tests, clase `TestReencuadreAutonomiaEtapa1`).

**Alcance explícito:** solo Etapa 1 (nomenclatura + badges + estados +
tests). Los 6 módulos de decisión que consumen la métrica legacy
(`recommend_action`, `risk_engine.py`, `optimizer_v2.py`, `bottleneck.py`,
`quick_wins.py`, `hourly_plan.py`) NO se tocaron — Etapa 2, diferida.

**Bug propio detectado y corregido:** un `Edit` encadenado dejó 2 líneas
residuales en el último test nuevo (`test_backtesting_mantiene_
comportamiento_previo`) referenciando variables de un test anterior
(`sim_off`/`sim_on` inexistentes en ese scope) — detectado por la
corrida de pytest, corregido antes de dar la Etapa 1 por completa.

**Limitación de codebase-memory-mcp confirmada esta pasada:**
`index_status` reporta `head_sha == base_sha` (el HEAD de git) incluso
tras `index_repository(mode="full")` repetido — el indexador lee del
commit de git, no del árbol de trabajo con cambios sin commitear. Los 3
símbolos nuevos de `circuit_state.py` no aparecieron en `search_graph`
por este motivo (coherente con la regla de no commitear sin pedido
explícito). La validación de acoplamiento se hizo por lectura directa
del código en su lugar.

**Pruebas ejecutadas:**
```text
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 358 passed en 87s (corrida limpia; una corrida previa en background
  sufrió suspensión de equipo ~13.6h, produciendo un falso positivo de
  timing no relacionado con este cambio — reproducido como no-regresión
  al aislar ese test: 4221-6588ms, muy por debajo del techo de 20000ms)
```
Más 10 escenarios directos vía `simulate_scenario` con
`|mass_balance_error_sagX| < 1e-10 t` en todos, y verificación puntual
de los estados DRAINING/SAG_OFF/CONSISTENT extremo a extremo.

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Migración de autonomía Etapa 2 (parcial): `AutonomyContext` + `recommend_action`

**Modificación asociada:** primera migración funcional pedida por el
usuario tras Etapa 1 — que las decisiones internas dejen de basarse
solo en la autonomía preventiva histórica. Plan aprobado en modo plan
(mismo archivo `happy-prancing-pelican.md`, reescrito para esta tarea).
Detalle completo en `04_Reports/Technical/
20260715_Migracion_Autonomia_Etapa2.md`.

**Archivos modificados:** `05_Dashboard/engine/circuit_state.py`
(`AutonomyContext`, `build_autonomy_context` — aditivo), `05_Dashboard/
engine/simulator.py::simulate_scenario` (construye `autonomy_context_
sag1/2` sobre el ESTADO INICIAL del escenario, no el final — hallazgo
importante: `recommend_action` siempre evaluó el estado inicial, no la
trayectoria simulada), `05_Dashboard/engine/rules_engine.py::
recommend_action` (nuevo helper `_accion_por_contexto_dinamico` con el
orden de prioridad del pedido; parámetros nuevos 100% opcionales,
comportamiento legacy preservado byte-a-byte si no vienen),
`05_Dashboard/tests/test_rules_engine.py` (+11 tests,
`TestRecommendActionAutonomyContext`).

**Alcance explícito:** solo `rules_engine.py::recommend_action`
(mayor ROI: es el motor de recomendación real detrás de la UI, ~24
consumidores aguas abajo vía `simulate_scenario`). `risk_engine.py`,
`bottleneck.py`, `quick_wins.py`, `hourly_plan.py`,
`optimizer_v2.py`/`optimizer_v3.py` (dual score) NO se tocaron —
diferido, cada uno su propio ciclo. `optimizer_v4.py`/`optimizer_v5.py`
confirmados sin consumidores de producción (`in_degree=0` vía MCP) —
solo documentado, sin ampliar su alcance (instrucción explícita del
pedido).

**Limitación de codebase-memory-mcp confirmada de nuevo:**
`index_status` sigue reportando `head_sha == base_sha` tras los cambios
sin commitear — mismo comportamiento que en Etapa 1. Acoplamiento de
`AutonomyContext`/`build_autonomy_context`/nuevos parámetros de
`recommend_action` validado por lectura directa (único caller real:
`simulator.py`).

**Pruebas ejecutadas:**
```text
python -m pytest tests/test_rules_engine.py -q
→ 25 passed (11 nuevos)

python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 367 passed en 110.72s, cero regresiones
```
5 escenarios directos vía `simulate_scenario` (llenando/drenando rápido/
estable/SAG off/nivel crítico) con `|mass_balance_error_sagX| <
1.1e-10 t` en todos; confirmado que una pila llenándose con
vulnerabilidad histórica crítica ya no dispara EVALUAR_DETENCION
(ahora MONITOREAR, cuantificado con la tasa de recuperación real).

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Roadmap maestro de cierre del Simulador Operacional

**Modificación asociada:** ninguna (documento de planificación, sin
cambios de código), pedido explícito del usuario. Nuevo archivo
`04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md`.

**Método:** MCP-first (`search_graph(max_degree=0)` para confirmar 9
candidatos de código muerto y las 4 funciones de recomendación en
"estado sombra"; `search_code` para `recommend_rate`/`rank_candidates`/
`generate_operational_recommendation`; `index_status` para reconfirmar
la limitación conocida) cruzado con `git log`/`git status`/`pytest`
reales.

**Hallazgos nuevos confirmados en esta pasada (no en el roadmap del
pedido, descubiertos al recolectar evidencia):**
- `find_optimal_v4`/`find_optimal_v5`: `in_degree=0` confirmado — cero
  consumidores de producción, decisión de producto aún pendiente.
- 4 funciones completas de recomendación sin consumidor de producción
  coexistiendo con `recommend_action` (la única activa):
  `rate_recommendation.py::recommend_rate`, `rules_engine.py::
  recommend_rate` (nombre duplicado), `circuit_state.py::
  generate_operational_recommendation`. `rate_recommendation.py::
  rank_candidates` sí tiene 2 consumidores reales — no debe archivarse
  sin identificarlos primero.
- `ONE_BALL_CAPACITY_FACTOR = 0.55` confirmado sin fuente de
  calibración documentada (a diferencia de `DRAIN_PCT_H`, que sí la
  tiene) — ejemplo concreto citado en el roadmap como condición de
  no-cierre.

**Reindexación MCP tras el commit `73b7128`:** `index_status` actualizó
`head_sha` al nuevo commit, pero `index_repository(mode="full")` no
reflejó el contenido nuevo en los conteos de nodos/aristas
(`expected_nodes` > `nodes` real) — discrepancia documentada, no
resuelta; el roadmap se apoyó en lectura directa donde fue necesario.

**Pruebas ejecutadas:** `python -m pytest tests -q
--ignore=tests/test_performance_portable.py
--ignore=tests/test_portable_smoke.py` → 367 passed (confirmación de
línea base para el roadmap, sin cambios de código en esta pasada).

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Cierre de brechas del roadmap: Fase 0 + Fase 2 parcial + Fase 7 quick win

**Modificación asociada:** primer lote de cierre de brechas pedido
explícitamente por el usuario ("comienza a cerrar todas las brechas
identificadas"), siguiendo el camino crítico del roadmap.

**Fase 0 (cerrada):** tag anotado `simulator-autonomy-stage2-baseline`
creado sobre `73b7128`. Los 2 PNG sueltos (`01_Data/Raw/
PI_alimentadores_pila_sag1/2.png`) se clasificaron como activos
legítimos (mismo patrón que las demás capturas SCADA ya versionadas) y
se commitearon junto con el roadmap en `c3094a1`.

**Fase 2 (parcial):** investigados los callers reales de las 4
funciones de recomendación en "estado sombra" antes de tocar nada
(`query_graph` + `grep`, sin abrir archivos completos hasta tener el
mapa). Resultado: `rate_recommendation.py::recommend_rate` y
`rules_engine.py::recommend_rate` confirmadas con `in_degree=0` real
(sin imports, sin tests) — **eliminadas**. `rate_recommendation.py::
rank_candidates` confirmada con 2 consumidores reales (`pages/
simulador_operacional.py` directo + la ya-eliminada `recommend_rate`) —
**no tocada**. `circuit_state.py::generate_operational_recommendation`
leída completa: es código bien diseñado (Regla 16, cuantificado) que
duplica conceptualmente el helper `_accion_por_contexto_dinamico` de la
Etapa 2 pero nunca se conectó — **no eliminada**, decisión diferida
explícitamente a Fase 5 (`RecommendationService`) porque eliminarla sin
decidir cuál arquitectura de mensaje gana destruiría trabajo útil.

**Fase 7 (quick win):** agregada una entrada en las Preguntas
Frecuentes de `packaging/README_USUARIO.md` explicando en lenguaje
llano que `ONE_BALL_CAPACITY_FACTOR` no está calibrado con datos (a
diferencia de la tasa de drenaje de pilas) y que está desactivado por
defecto — antes esta advertencia solo existía en un reporte técnico, no
en el manual que lee el Jefe de Sala.

**Archivos modificados:** `05_Dashboard/engine/rate_recommendation.py`
(-19 líneas), `05_Dashboard/engine/rules_engine.py` (-13 líneas),
`05_Dashboard/packaging/README_USUARIO.md` (+9 líneas), `04_Reports/
Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md` (panel de
avance y condición final de cierre actualizados con las brechas
resueltas en esta pasada).

**Pruebas ejecutadas:**
```text
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 367 passed en 87.21s, cero regresiones tras eliminar las 2 funciones muertas
```

**Espacio liberado:** ~32 líneas de código muerto eliminadas (2
funciones completas, cero riesgo confirmado antes de borrar).

---

## 2026-07-15 — Fase 1.1 del roadmap: sub-scores dinámico/histórico en risk_engine.py

**Modificación asociada:** segundo ítem del camino crítico del roadmap
tras Fase 0/2/7. Detalle en `04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md`, sección "Fase 1".

**Hallazgo que corrigió el riesgo estimado:** el roadmap original
asumía 2 callers de producción reales para `compute_iro` (`app.py` +
`simulator.py`). `query_graph` confirmó que `app.py::comparar_whatif`
solo importa `compute_iro` sin llamarlo — lee `sim["iro_result"]` ya
calculado por `simulate_scenario`. El único caller real es `engine/
simulator.py:229`, lo que redujo el riesgo real de la migración.

**Archivos modificados:** `05_Dashboard/engine/risk_engine.py`
(`_historical_vulnerability_score`, `_dynamic_depletion_score`,
parámetros opcionales `autonomy_context_sag1/2` en `compute_iro` — el
`iro` total y los 5 sub-scores legacy no cambian, verificado con test),
`05_Dashboard/engine/simulator.py` (reusa `_hist_h_sag1/2`/
`autonomy_context_sag1/2` ya construidos para `recommend_action` en vez
de recomputar), `05_Dashboard/tests/test_risk_engine.py` (nuevo, 7
tests).

**Decisión explícita de no recalibrar pesos:** siguiendo la instrucción
del pedido ("si no hay evidencia para recalibrar, preserva el score
total y agrega sub-scores aditivos"), `WEIGHTS["autonomia"]=0.30` no se
repartió entre los 2 sub-scores nuevos — quedan como diagnóstico
adicional, no alteran el cálculo del IRO mostrado hoy.

**Pruebas ejecutadas:**
```text
python -m pytest tests/test_risk_engine.py -q
→ 7 passed

python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 374 passed en 100.05s (367 previos + 7 nuevos), cero regresiones
```
Confirmado además `|mass_balance_error_sagX| < 1e-10 t` en escenario de
verificación (el cambio no toca el motor físico).

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Fases 1.2-1.4 del roadmap: bottleneck.py, quick_wins.py, hourly_plan.py

**Modificación asociada:** continuación directa del camino crítico del
roadmap tras Fase 1.1. Detalle completo en `04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md`, sección "Fase 1".

**1.2 `bottleneck.py`:** campo aditivo `categoria` (6 valores:
`STOCKPILE_DYNAMIC_DEPLETION`/`STOCKPILE_LOW_BUFFER`/`BALL_MILL_
CAPACITY`/`FEED_RESTRICTION`/`CHANCADO_LIMIT`/`SAG_OFF`) en
`detect_bottleneck`/`full_bottleneck_map`, sin cambiar severidad/color/
motivo ya testeados. Hallazgo relevante: el detector usa el **mínimo de
toda la trayectoria**, no el estado final — un escenario con un momento
crítico real que termina recuperándose mantiene severidad "alta"
(correcto, el riesgo ocurrió) pero ahora indica `categoria=LOW_BUFFER`.

**1.3 `quick_wins.py`:** `QuickWin.delta_autonomia_h` renombrado
explícitamente a `delta_historical_buffer_h` (rename real, no alias —
2 consumidores UI actualizados) + nueva `delta_dynamic_autonomy_h`. El
criterio de ranking (`beneficio_costo`) sigue anclado al colchón
preventivo, sin recalibrar sin datos.

**1.4 `hourly_plan.py`:** hallazgo — `build_hourly_plan` tiene **cero
consumidores de producción**, solo su propio test, lo que bajó el
riesgo real de esta migración. 8 columnas nuevas por bloque horario
reusando los clasificadores de la Etapa 1 sobre las series de 5 min ya
producidas por `simulate_ode` (sin simulación nueva); degrada a `None`
con dicts sintéticos que no traen `pile_sag1/2`.

**Pruebas ejecutadas:**
```text
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 385 passed en 110.79s (367 base Etapa1/2 + 18 nuevos: risk_engine 7,
  bottleneck 4, quick_wins 5, hourly_plan 2), cero regresiones
```
Confirmado además extremo a extremo con `simulate_scenario` real:
`|mass_balance_error_sagX| < 1e-10 t`, y `build_hourly_plan` produciendo
estados dinámicos correctos (DRAINING → AT_CRITICAL_LEVEL → SAG_OFF a
medida que la pila se agota) sobre datos de simulación real.

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Fase 1.5 del roadmap: sensibilidad de tolerancias RESTRICTED — Fase 1 COMPLETA

**Modificación asociada:** último ítem de la Fase 1 del roadmap.
Detalle completo en `04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md`, sección "Fase 1".

**Cambio:** `circuit_state.py::determine_operational_state` reemplaza
`rate_effective < rate_target - 1e-6` (comparación exacta) por
`(rate_target - rate_effective) > max(tolerance_tph, rate_target *
tolerance_pct)`, con 2 parámetros opcionales nuevos — default preserva
el comportamiento previo exacto.

**Estudio de sensibilidad ejecutado (no solo documentado como
pendiente):** script `sensibilidad_restricted.py` (scratchpad, fuera
del repo) reconstruyó la trayectoria `tph_sagX` vs. `rate_target` de 2
escenarios reales (T8 8h correas reducidas, T8 12h correas inactivas)
usando datos que `simulate_ode` ya produce, y midió el % de pasos
RESTRICTED bajo 6 combinaciones de tolerancia (10/25/50 TPH, 1/2/5%).

**Hallazgo no esperado a priori:** el % RESTRICTED es altísimo (53-99%)
en ambos escenarios incluso con tolerancia amplia — la clasificación
está dominada por restricción real de alimentación durante T8, no por
ruido de punto flotante. El "problema" que motivó esta fase (posibles
falsos positivos) resultó más acotado de lo asumido. **No se fijó un
valor de tolerancia de producción** — instrucción explícita del pedido
("no fijes valores definitivos sin sensibilidad"); la elección queda
como decisión de producto pendiente, documentada con evidencia real, no
como brecha de ingeniería sin analizar.

**Pruebas ejecutadas:**
```text
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 389 passed en 164.05s (385 previos + 4 nuevos en TestToleranciaRestricted), cero regresiones
```

**Cierre de Fase 1 completa del roadmap (1.1-1.5, 7/7 criterios).**

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Fase 3 del roadmap: dual score en optimizer_v2.py, decisión V4/V5

**Modificación asociada:** continuación del camino crítico tras Fase 1.
Detalle completo en `04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md`, sección "Fase 3".

**Doble penalización confirmada algebraicamente (3.1-3.2):**
`compute_multi_criteria_score` (`optimizer_v2.py`, el score real que
ordena `run_deterministic_grid`/`adaptive_mc_eval`, en el camino de
`find_optimal_v3`) combina `inv_norm` (% de pila) y `auton_norm`
(autonomía histórica mínima = `compute_autonomia(pile_pct)`, función
directa del mismo %) — dos pesos penalizando la misma señal. Documentado
en el propio código, pesos NO recalibrados sin datos.

**Dual score aditivo (3.3-3.4):** `run_deterministic_grid` agrega 6
claves por candidato (ya calculadas por `simulate_scenario`, cero
simulaciones extra). Nuevas `compute_dual_score`/`compare_rankings` en
`optimizer_v2.py`. `det_score` y el orden de selección real NO cambian
(test dedicado). Hallazgo real: una corrida de prueba mostró
`ranking_diverges=True` — el candidato #1 por score legacy y el #1 por
seguridad dinámica son distintos en al menos un escenario probado.

**Decisión V4/V5 (3.5):** confirmado de nuevo `in_degree=0` para
`find_optimal_v4`/`find_optimal_v5`. Decisión explícita: no conectar/
consolidar/archivar/eliminar en esta sesión — es una decisión de
producto (qué filosofía de recomendación prefiere el JdS/Metalurgista
entre 4 alternativas reales ya implementadas), no de ingeniería.
Documentado como pendiente de decisión, no como omisión.

**Archivos modificados:** `05_Dashboard/engine/optimizer_v2.py`
(`compute_dual_score`, `compare_rankings`, 6 claves aditivas en
`run_deterministic_grid`, docstring extendido en `compute_multi_
criteria_score`), `05_Dashboard/tests/test_optimizer_v2_dual_score.py`
(nuevo, 10 tests).

**Pruebas ejecutadas:**
```text
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 399 passed en 101.44s (389 previos + 10 nuevos), cero regresiones
```

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Fase 4 del roadmap: backtesting real ejecutado, P0 de fidelidad descubierto

**Modificación asociada:** continuación del camino crítico tras Fase 3
(Fase 4 es paralelizable, no depende de 1-3). Detalle completo en
`04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md`,
sección "Fase 4".

**Corrección de estimación:** la infraestructura de backtesting
(`historical_backtesting.py::run_backtest`/`run_backtest_proxy`) ya
existía, completa, con datos reales y disciplina de "no fabricar"
resultados sin N suficiente — no era la brecha de "cero backtesting"
que el roadmap original asumía. Se extendió (aditivo) con `pila_bias_
sag1_pp`/`pila_std_sag1_pp` para los 5 regímenes con datos (antes solo
t8_corta tenía esta métrica, en un reporte de 2026-07-07).

**Hallazgo real, no favorable — P0 nuevo:** al correr el backtesting
completo, el modelo **falla su propia tolerancia de MAE (5.0pp) en 4 de
5 regímenes**: t8_corta MAE=18.88pp, inventario_crítico=13.89pp,
mantenimiento=14.47pp, alimentación_restringida=12.80pp. Solo overflow
(4.51pp) pasa. Bias mayormente negativo (el motor subestima la pila
final) — ya diagnosticado parcialmente para t8_corta desde 2026-07-07
(alimentación asumida plena vs. restricción real durante T8), nunca
antes confirmado para los otros 4 regímenes en un solo lugar.

**Hallazgo metodológico — hold-out no confirmado:** se cruzaron fechas
entre `fact_eventos_t8.parquet` (calibración de `DRAIN_PCT_H`) y
`advanced_t8_official_events.parquet` (backtesting de t8_corta) — ambos
datasets arrancan en la misma fecha exacta (2026-01-02), evidencia
fuerte de superposición de eventos entre calibración y validación. No
confirmado a nivel evento-por-evento (requiere más trabajo), pero
suficiente para no poder afirmar "existe hold-out" como criterio
cumplido.

**4.1 Auditoría de parámetros (tabla completa en el roadmap):**
confirmado `DRAIN_PCT_H`/`BOLA_DELTA_TPH` calibrados con fuente;
`ONE_BALL_CAPACITY_FACTOR`/`VENTANA_FACTOR_ESTADO["reducida"]`/
`_pile_feedback_factor`/sigmas Monte Carlo/pesos `PERFILES_V5` sin
calibrar, sin fuente citada. Comparación direccional (no concluyente):
CV real de producción diaria (SAG1=0.444) es 3-4x el ±12% de ruido de
alimentación del Monte Carlo — escalas de tiempo distintas, no
directamente comparable, pero amerita revisión.

**4.2 Factor una bola:** no ejecutado esta pasada — ruta concreta
identificada (adaptar `02_Analytics/Scripts/calibrar_bola_delta_tph.py`,
ya usado para calibrar el mecanismo hermano `BOLA_DELTA_TPH`).

**Archivos modificados:** `05_Dashboard/engine/historical_
backtesting.py` (`BacktestResult.pila_bias_sag1_pp`/`pila_std_sag1_pp`,
aditivo puro), `05_Dashboard/tests/test_backtesting_bias_std.py`
(nuevo, 6 tests).

**Pruebas ejecutadas:**
```text
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 405 passed en 98.62s (399 previos + 6 nuevos), cero regresiones
```

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Fase 4B (parcial): diagnóstico causal de fidelidad histórica, Fase 5 suspendida

**Modificación asociada:** pedido explícito del usuario tras el
hallazgo de la Fase 4 (el modelo falla su tolerancia de MAE en 4/5
regímenes). Instrucción explícita: suspender la Fase 5 (refactor
arquitectónico) hasta diagnosticar/recalibrar/validar. Sin cambios de
código de producción esta pasada — solo diagnóstico y un manifiesto
JSON. Detalle completo en `04_Reports/Technical/
20260715_Diagnostico_Fidelidad_Historica.md`.

**Alcance ejecutado (de un pedido de 12 fases, varias sesiones):** Fase
1 (línea base congelada: `backtesting_baseline_manifest.json` con git
HEAD, hash de 4 datasets fuente, parámetros activos, resultados por
régimen). Fase 2 (validación de metodología del MAE: mide estado final
del evento; alineación temporal corregida en la ruta "oficial" desde
2026-07-07 pero NO en la ruta "proxy" — inconsistencia real documentada,
sin resolver). Fase 3.1 (diagnóstico causal de `alimentacion_
restringida`, N=1.477, prioridad máxima).

**Hallazgo principal:** la hipótesis "factor fijo 0.4 mal aplicado"
(sospecha original del roadmap) se **descarta con evidencia de código**
para `alimentacion_restringida` — `VENTANA_FACTOR_ESTADO` solo se aplica
si `t8_activo`, y el backtesting de este régimen usa `duracion_t8_h=0.0`
con `cv_mode="manual"` y valores CV reales observados, nunca invocando
ese factor. El error real se concentra en un subconjunto de eventos
(P90 pila=30pp vs. mediana=10pp) con mediana de error de F_out=0% —
apunta a `_pile_feedback_factor`/comportamiento cerca de `CRITICAL_PCT`
(hipótesis 3.2 del pedido) como causa más probable, incluso para el
régimen de mayor N. Se recomienda invertir el orden de prioridad
3.1→3.2 del pedido original en la siguiente pasada.

**Fase 5 (refactor arquitectónico) suspendida explícitamente** en el
roadmap — no retomar hasta cumplir Condición A (regímenes dentro de
tolerancia) o B (aprobación formal de limitaciones aceptadas).

**Archivos generados:** `04_Reports/Technical/
20260715_Diagnostico_Fidelidad_Historica.md`, `04_Reports/Technical/
backtesting_baseline_manifest.json`. Sin cambios a `05_Dashboard/`.

**Pruebas ejecutadas:** no aplica (sin cambios de código de producción
esta pasada — solo lectura, análisis y generación de manifiesto).

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Fase 3.2 confirmada: `_pile_feedback_factor` explica 2-2.5x el error de fidelidad

**Modificación asociada:** continuación directa de Fase 4B tras
confirmar en la pasada anterior que la hipótesis del "factor fijo 0.4"
no explicaba el error de `alimentacion_restringida`. Sin cambios de
código de producción — solo diagnóstico (script de análisis en
scratchpad, no en el repo).

**Método:** se reprodujo cada evento de `alimentacion_restringida`
(N=1.477) e `inventario_critico` (N=221) con la misma llamada que usa
`historical_backtesting.py::run_backtest_proxy`, pero conservando la
trayectoria simulada completa de `pile_sag1` para detectar si cruzó los
3 breakpoints de `_pile_feedback_factor` (35%/25%/`CRITICAL_PCT`+5%,
`ode_model.py:354-380`).

**Hallazgo confirmado con evidencia cuantitativa fuerte**: en ambos
regímenes, los eventos donde la pila simulada cruza estos breakpoints
tienen **2.0-2.5x más error** que los que no cruzan (`alimentacion_
restringida`: 18.9-23.7pp vs. 8.6-9.8pp; `inventario_critico`:
17.6-19.8pp vs. 7.1-8.4pp), y el error crece monótonamente cuanto más
profundo el breakpoint. Es la causa individual más fuerte identificada
hasta ahora — no explica el 100% del error (eventos que nunca cruzan
siguen 2-4pp sobre tolerancia), pero es un contribuyente real y medible,
no una constante mal aplicada por casualidad.

**No se modificó `_pile_feedback_factor`** — recalibrarlo requiere
primero datos reales de comportamiento operacional ante pila baja (no
disponibles en este análisis) y el split calibración/validación
temporal real (Fase 5 del pedido de Fase 4B, aún no ejecutada) — evita
repetir el problema de hold-out ya encontrado con `DRAIN_PCT_H`.

**Archivos modificados:** `04_Reports/Technical/
20260715_Diagnostico_Fidelidad_Historica.md` (nueva sección "Fase
3.2"), `04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md` (actualizado).

**Pruebas ejecutadas:** no aplica (sin cambios de código de producción).

**Espacio liberado:** no aplica.

---

## 2026-07-15 — Motor multicelda SAG1/SAG2 (I+D) + continuación de Fase 4B, consolidado y commiteado

**Modificación asociada:** pedido explícito del usuario de implementar
un motor multicelda para SAG1/SAG2 (17 fases). Al empezar a trabajar se
encontró una cantidad sustancial de trabajo ya presente en el working
tree, sin commitear, que no se había generado en los turnos previos de
esta conversación — evidencia de una sesión/proceso paralelo que ya
había ejecutado gran parte del pedido (motor multicelda completo,
feature-flagged; 3 iteraciones de calibración con hold-out real para
SAG2; continuación de la Fase 4B con hallazgos nuevos importantes).

**Antes de continuar o commitear**, se verificó explícitamente que el
estado no estuviera roto: `simulate_scenario` funciona con y sin
`multicell_enabled`, `mass_balance_error` idéntico en ambos modos, y se
corrió la suite completa (422 passed, 1 falla de timing no reproducible
en corrida aislada — mismo patrón de flake por carga de máquina ya
documentado antes en esta sesión).

**Resumen de lo encontrado y consolidado:**
- Motor multicelda opcional (`engine/multicell/`, `engine/stockpile_
  multicell.py`), apagado por defecto, motor agregado sin cambios de
  comportamiento.
- Investigación con hold-out temporal real: SAG1 empeora con capas
  espaciales simples (descartado); SAG2 mejora parcial e inconsistente
  por régimen (I+D, no productivo). Decisión: Opción E (híbrida),
  mantener agregado en producción.
- Continuación de Fase 4B: `mantenimiento` confirmado como mezcla de 2
  subregímenes con bias opuesto; `overflow` confirmado como control
  positivo limpio; split calibración/validación real ejecutado con
  resultado definitivo (72/72 eventos de backtesting contaminados por
  solape con calibración de `DRAIN_PCT_H` — hold-out hoy es nulo);
  recalibración experimental de `DRAIN_PCT_H` no mueve el MAE de pila
  (descartado como palanca); contrafactual de `_pile_feedback_factor`
  muestra que debilitarlo empeora el hold-out real de forma monótona
  (no es el próximo lever de corrección rápida).
- Hallazgo más importante de toda la continuación: el MAE realmente
  fuera de muestra de `t8_corta` es **36.63pp**, casi el doble del
  18.88pp reportado anteriormente (que estaba contaminado).

**Archivos commiteados:** 36 archivos (ver commit `0e023e4`) — motor
multicelda completo, 8 scripts de diagnóstico nuevos, 4 reportes
nuevos, 3 archivos de test nuevos, 1 skill nueva, actualización del
roadmap maestro y del diagnóstico de fidelidad histórica.

**Pruebas ejecutadas:**
```text
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 422 passed, 1 failed (timing, no reproducible aislado: 4/4 passed en 52.71s)
```

**Espacio liberado:** no aplica (CSVs de resultados quedan gitignored
por política ya existente en el repo, scripts los regeneran on-demand).

---

## 2026-07-15 — Continuación Fase 3.6 (dual score MC) + 4/9 dead-code

**Modificación asociada:** cierre de los ítems "pendiente fuera de esta
pasada" que el roadmap dejó explícitos al final de la sesión anterior —
ver `04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md`,
secciones 3.6 y Fase 7.

**Cambios:**
- `engine/optimizer_v2.py::adaptive_mc_eval` — agrega `pct_draining_
  sagX`/`pct_at_critical_sagX`/`p_dynamic_safe` (aditivo, mismo patrón
  que el grid determinístico de la Fase 3.3-3.4; `p_safe`/`multi_
  criteria_score` sin cambios, verificado con test dedicado).
- `05_Dashboard/tests/test_optimizer_v2_dual_score.py` — 3 tests nuevos
  (`TestAdaptiveMcEvalDualScore`).

**Archivos eliminados (código muerto, `in_degree=0` confirmado vía MCP
en la pasada del 2026-07-15, 4 de los 9 candidatos):**
- `engine/rules_engine.py::regime_fn_factory`
- `engine/ode_model.py::compute_cv_tph`
- `validation/feedback_form.py::read_jefe_sala_feedback`
- `app.py::page_simulador` + import huérfano de `build_sidebar` en
  `app.py` (la función real en producción es `page_simulador_
  operacional` en `pages/simulador_operacional.py`, que ya importa
  `build_sidebar` correctamente por su cuenta)

**Verificación antes de eliminar:** `grep` de los 4 nombres en todo
`05_Dashboard/` confirmó cero referencias activas (las únicas
coincidencias de `page_simulador` son `page_simulador_operacional`, un
símbolo distinto).

**Pruebas ejecutadas:**
```text
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 426 passed
python -c "import app" → carga limpio (historico + figuras estáticas OK)
```

**Pendiente:** quedan 5/9 candidatos de código muerto (4 en
`02_Analytics/`, sin resolver esta pasada).

---

## 2026-07-15 — Nuevos scripts de validación estadística (regresión)

**Modificación asociada:** primer bloque del programa de validación
estadística de 37 secciones pedido por el usuario — ver
`04_Reports/Technical/Analisis_Estadistico_Simulador.md` y
`Validacion_Modelos_Regresion.md`.

**Archivos creados (no son exploratorios desechables — son scripts de
análisis reproducibles, se conservan):**
- `02_Analytics/Scripts/statistical_validation/build_event_variable_table.py`
- `02_Analytics/Scripts/statistical_validation/regression_pila_error.py`
- `04_Reports/Technical/event_variable_table.csv` (2.097 eventos, tabla intermedia — regenerable ejecutando el primer script)
- `04_Reports/Technical/regression_results.csv`
- `04_Reports/Technical/regression_results_por_regimen.csv`
- `04_Reports/Technical/Analisis_Estadistico_Simulador.md`
- `04_Reports/Technical/Validacion_Modelos_Regresion.md`

**No se modificó código de producción** (`05_Dashboard/engine/`) en
esta pasada — solo lectura/reuso de `historical_backtesting.py` y
`regime_event_detector.py` vía import.

**Verificación:** conteos por régimen y ratios de error por cruce de
breakpoint reproducen exactamente los ya publicados en
`20260715_Diagnostico_Fidelidad_Historica.md` antes de confiar en el
modelo nuevo (sanity check documentado en `Analisis_Estadistico_
Simulador.md`, sección de verificación).

---

## 2026-07-15 — Validación del motor de recomendaciones (escenarios dorados)

**Modificación asociada:** sección 29 del programa de validación
estadística — ver `04_Reports/Technical/Validacion_Motor_
Recomendaciones.md`.

**Archivos creados (test permanente, no desechable):**
- `05_Dashboard/tests/test_golden_scenarios_recommend_action.py` (5
  tests, 1 `xfail(strict=True)` documentando un gap real confirmado).

**No se modificó `rules_engine.py`** — el gap encontrado (SAG apagado +
pila llenando hacia el 100% no dispara ninguna acción de riesgo de
overflow, retorna `OPERACION_NORMAL`) requiere decisión de producto,
no una corrección unilateral.

**Pruebas ejecutadas:** `pytest tests -q` → 430 passed, 1 xfailed (sin
regresión sobre los 426 previos).

---

## 2026-07-15 — Calibración de sigmas de Monte Carlo (auditoría)

**Modificación asociada:** secciones 18-19 del programa de validación
estadística — ver `04_Reports/Technical/Calibracion_Monte_Carlo.md`.

**Archivos creados:**
- `02_Analytics/Scripts/statistical_validation/calibrate_monte_carlo_sigmas.py`
- `04_Reports/Technical/monte_carlo_calibration.csv` (gitignored, regenerable)
- `04_Reports/Technical/Calibracion_Monte_Carlo.md`

**No se modificó `optimizer_v2.py`** — los 3 sigmas (pila ±2.5pp, feed
±12%, T8 ±1h) muestran evidencia de subestimar la incertidumbre real
(ratios 1.18x-2.85x según parámetro).

**Validación de `p_safe` (misma pasada, continuación):** agregado
`02_Analytics/Scripts/statistical_validation/validate_p_safe_
calibration.py` + `p_safe_calibration_validation.csv`/`_reliability.csv`
(gitignorados, regenerables). Confirma con una tercera línea de
evidencia independiente la deriva temporal sistémica ya encontrada en
`Validacion_Modelos_Regresion.md`: `p_safe` bien calibrado en
calibración (Brier=0.18), mal calibrado en hold-out (Brier=0.62).

---

## 2026-07-15 — Causa probable de la deriva temporal (cruce con PAM Mantto)

**Modificación asociada:** el usuario sugirió cruzar los hallazgos de
deriva temporal con `01_Data/Raw/PAM/PAM_Mantto/` y `PAM_Produccion/`
(planes de mantención/producción reales, nunca antes parseados en
detalle por el proyecto — el loader existente solo extrae horas T8).

**Archivo creado:** `04_Reports/Technical/Diagnostico_Causa_Deriva_
Temporal_PAM.md`.

**Hallazgo:** `correa_315` cae a exactamente cero en el 100% de los 53
días desde `2026-04-30` (la misma fecha del hold-out ya elegido por
otro criterio) — quiebre estructural confirmado en los datos, no
hipótesis. Coincide con la intervención real "Alimentador 522:
estandarización de placas" (2026-05-01 a 05-08) del PAM Mantto.
Actualiza `Plan_Mejora_Simulador_2026-07-15.md` y el roadmap maestro
con la reserva correspondiente sobre los hallazgos de hoy que usaron
ese período como hold-out.

**No se modificó ningún dato ni código** — solo lectura y análisis de
los Excel de PAM Mantto (no versionados en git, en `01_Data/Raw/`).

**Confirmación y corrección cuantitativa (misma pasada, continuación):**
usuario confirmó sensor `correa_315` roto (criterio: SAG1 siguió con
rendimiento real, no se detuvo) y proveyó
`01_Data/Raw/Tonelajes_pila/correas_ton.xlsx` (15 min, con columna T3
nueva) como intento de corrección — verificado que el tag crudo sigue
en 0.0 ahí también, sin reconstrucción numérica directa disponible.
Se probó una reconstrucción por proporción histórica `cv315/cv316`
(mediana 0.277): reduce el MAE de `t8_corta` hold-out de 36.63pp a
27.26pp (−25.6%), pero no cierra la brecha completa. Documentado en `Diagnostico_Causa_Deriva_Temporal_PAM.md`, formalizado
como `02_Analytics/Scripts/statistical_validation/
test_cv315_sensor_fix.py` (reproducible, verificado que da el mismo
resultado que el experimento inicial).

---

## 2026-07-15 — Reconstrucción final + re-ejecución completa (cv315)

**Modificación asociada:** pedido explícito del usuario de reconstruir
la tabla completa de eventos con `cv315` corregida y re-correr
regresión + calibración de `p_safe`, usando "matemática simple,
interpolación o algún método numérico" para las brechas.

**Archivos creados:**
- `02_Analytics/Scripts/statistical_validation/
  rebuild_corrected_historical_series.py` — reconstruye `correa_315`
  con regresión lineal (validada fuera de muestra, R²=0.127, único
  método con R² positivo de 3 probados), interpola brechas cortas
  preexistentes, agrega T3. Genera `01_Data/Cache/advanced_t8_
  historical_5min_corrected.parquet` y `advanced_t8_event_windows_
  corrected.parquet` (ambas fuentes afectadas, la segunda no detectada
  hasta esta pasada).
- `02_Analytics/Scripts/statistical_validation/
  build_event_variable_table_corrected.py` — reconstruye la tabla de
  eventos usando las fuentes corregidas (monkeypatch de
  `regime_event_detector._load_serie`, sin tocar código de producción).
- `regression_pila_error.py` y `validate_p_safe_calibration.py`
  extendidos con parámetro opcional para usar datos corregidos
  (`--corrected` / nombre de tabla como argumento).

**No se modificaron los parquets originales** — todas las correcciones
viven en copias `_corrected` separadas, trazabilidad completa.

**Resultado:** MAE `t8_corta` hold-out 36.63→17.80pp (univariado,
−51%), 11.63→8.46pp (regresión, −27%); Brier de `p_safe` hold-out
0.621→0.004 (casi perfecto). Ver `Diagnostico_Causa_Deriva_Temporal_
PAM.md` para el detalle completo y las reservas metodológicas (R²=0.127
es una reconstrucción de alta incertidumbre, no un sustituto del
sensor real).

---

## 2026-07-15 — Sincronización del roadmap maestro con el hallazgo de `correa_315`

**Modificación asociada:** las secciones 9 y 10 de
`04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md`
("Checklist de release" y "Condición final de cierre") habían quedado
desactualizadas respecto al hallazgo/reconstrucción de `correa_315`
(commit `755e83a`) — seguían describiendo el P0 de fidelidad como
completamente abierto y con las cifras de MAE previas a la corrección
del sensor.

**Cambio:** actualizada la fila "P0 abierto" y la conclusión de la
sección 10, y la línea "Estadística" de la sección 9, para reflejar que
la calibración de `p_safe` (la señal que consume el Jefe de Sala) está
prácticamente resuelta (Brier hold-out 0.004) y que el residuo de
fidelidad de pila está bloqueado en obtener la serie real corregida
desde Instrumentación, no en investigación de causa raíz adicional. Sin
cambios de código ni de datos — solo sincronización de documentación
con el estado real ya establecido en la sección 4B del mismo archivo.

---

## 2026-07-15 — Contaminación de eventos SAG1-apagado en calibración + verificación PAM Productivo

**Modificación asociada:** el usuario preguntó si los archivos PAM de
mantenimiento podían explicar equipos detenidos por horas/días, y
observó que durante mantención cv315/cv316 deberían estar sin
alimentación (detenidas). Se verificó directamente contra
`SAG1_operando`/`SAG2_operando` (ya en `advanced_t8_historical_5min.
parquet`), lo que llevó a un hallazgo más grande que la pregunta
original.

**Hallazgo principal — contaminación del set de eventos T8:** de los 72
eventos oficiales usados para calibrar/validar `t8_corta`, el **68% de
los eventos de calibración (34/50)** tienen SAG1 mayormente apagado
durante la ventana T8 (vs. solo 10% en hold-out) — son eventos
triviales (MAE 2.70pp, la pila casi no se mueve) que abaratan
artificialmente el MAE de calibración reportado. Comparando "como para
como" (solo eventos con SAG1 genuinamente operando), la brecha
calibración-vs-hold-out baja de 3.3x a 1.5x (26.12pp vs. 39.58pp) —
ambos ya sobre tolerancia. Correlación fracción-operando vs. error,
solo en calibración: r=0.865.

**Verificación secundaria — PAM Productivo como proxy independiente:**
el PROGRAMA diario de `CV 315` (hoja `DATOS DÍA` de
`01_Data/Raw/PAM/PAM_Produccion/`) nunca cae a cero después del
2026-04-30 (confirma sensor roto, no proceso detenido — fuente
completamente independiente del sensor). Como insumo cuantitativo para
mejorar la reconstrucción de `correa_315`, no aporta (R² fuera de
muestra 0.175→0.179, MAE empeora levemente) — la granularidad diaria
no captura la variación de 5 min que domina el error.

**Archivos creados:**
- `02_Analytics/Scripts/statistical_validation/
  test_sag1_operando_composition.py` — cruza `_run_backtest_t8`
  (ruta productiva real, sin modificar) con `SAG1_operando` por
  evento, reproducible.
- `02_Analytics/Scripts/statistical_validation/
  build_pam_produccion_daily_program.py` — extrae el programa diario
  de CV315/CV316/SAG1/SAG2 de los 6 archivos mensuales PAM Productivo.

**No se modificó ningún parámetro de producción ni criterio de
selección de eventos** — ambos hallazgos son diagnósticos. Documentado
en `04_Reports/Technical/Diagnostico_Causa_Deriva_Temporal_PAM.md` y
sincronizado en la fila "P0 abierto" de
`20260715_Roadmap_Cierre_Simulador_Operacional.md`.

---

## 2026-07-15 — Historia real de correa_315 reconstruida desde export directo del PI System

**Modificación asociada:** el usuario exportó directamente desde el PI
System el tag crudo `CH1:210_WIT2001` (`correa_315`,
`01_Data/Raw/Tonelajes_pila/data_cv315.txt`, 51.181 registros,
2026-04-05 a 2026-05-20, resolución nativa ~1 min) y pidió reconstruir
la historia con esta fuente, la más autoritativa disponible en el
proyecto.

**Cronología reconstruida** (clasificación por bloques de 4h, usando
valor + densidad de muestras — el PI comprime por excepción, así que
densidad baja = tag plano):
- 04-05 a 04-10: funcionamiento normal continuo.
- 04-11 a 04-18: degradación intermitente (17-50% de bloques caídos/día)
  — coincide con `CTR 315` (la correa/instrumento, Mtto Mensual 12h,
  PAM real, 2026-04-16).
- 04-19 a 04-23: degradación severa (67-100%) — coincide con el
  retorqueo de trunnion + crash stop de SAG1 ya documentado.
- 04-24 a 04-29: **recuperación completa**, 6 días de funcionamiento
  normal — dato nuevo, descarta que la falla del 30 de abril sea
  deterioro gradual continuo.
- 04-30 en adelante: falla permanente, sin recuperación hasta el fin
  del export (05-20). Candidato ambiguo sin confirmar: `CTR CV15`
  (Mtto Mensual, 2026-04-29) — nombre parecido a `CTR 315` pero no
  confirmado como el mismo equipo.

**No se recuperan valores numéricos** — el sensor real reporta 0 exacto
en esta fuente también, la reconstrucción cuantitativa sigue dependiendo
de la regresión ya construida (R²=0.127). Lo nuevo es la cronología de
validez del sensor, más precisa que el corte único "antes/después del
2026-04-30" usado hasta ahora.

**Archivo creado:** `02_Analytics/Scripts/statistical_validation/
reconstruir_historia_pi_cv315.py` (reproducible). Output intermedio
`01_Data/Cache/pi_cv315_clasificacion_4h.parquet` (no versionado,
regenerable desde el script).

Documentado en `04_Reports/Technical/Diagnostico_Causa_Deriva_Temporal_
PAM.md`. No se modifica ningún parámetro de producción.

---

## 2026-07-15 — Verificación de la relación física CV315↔SAG1 con export PI de rendimiento SAG1

**Modificación asociada:** el usuario aclaró que `CTR CV15` = `CTR 315`
(Correa Transportadora 315) y sugirió que el rate de SAG1 debería ser
similar a lo que le alimenta `correa_315`, análogo al caso de
referencia `correa_316`↔`SAG2_tph` (nunca roto). Proporcionó un segundo
export directo del PI System: `01_Data/Raw/Tonelajes_pila/
data_rendimiento_sag1.txt` (tag `REND_TMS_SAG1_PI`, 120.618 registros,
2025-08-01 a 2026-07-15).

**Hallazgo 1:** confirma con densidad de muestra constante que SAG1
estuvo genuinamente detenido 44 días consecutivos (2026-01-08 a
02-20) — una mantención mayor real, no un artefacto de la bandera
`SAG1_operando` ya usada. Explica por qué el intento anterior de
calibrar con enero-febrero fallaba (solo 6 días activos disponibles).

**Hallazgo 2:** usando septiembre-diciembre 2025 (111 días con SAG1
genuinamente activo) como entrenamiento y marzo 2026 (29 días activos)
como validación fuera de muestra, la relación `correa_315 ~ SAG1_tph`
es real dentro del entrenamiento (r=0.625) pero **no generaliza**
(R² fuera de muestra negativo, tanto regresión lineal como razón
mediana) — la razón `correa_315/SAG1_tph` deriva de 0.738 a 0.537 entre
esas dos ventanas (~27%). El circuito de referencia (`correa_316/
SAG2_tph`) también deriva pero mucho menos (±10%), confirmando que hay
deriva de proceso genérica pero `correa_315` la exhibe con casi 3x más
magnitud.

**Conclusión honesta:** la intuición física del usuario es correcta
(la correlación es real y del mismo orden que el caso de referencia
sin problemas), pero no es utilizable todavía como reconstrucción
cuantitativa confiable — ninguna fórmula fija generaliza entre
ventanas temporales. La reconstrucción multivariada ya construida
(R²=0.127, `755e83a`) sigue siendo la mejor disponible.

**Archivos creados:** `02_Analytics/Scripts/statistical_validation/
test_relacion_cv315_sag1_pi.py` (reproducible). `01_Data/Cache/
pi_sag1_rendimiento_raw_parsed.parquet` (parseado del export PI).

Documentado en `04_Reports/Technical/Diagnostico_Causa_Deriva_Temporal_
PAM.md`. No se modifica ningún parámetro de producción.

---

## 2026-07-15 — Cierre de 3 quick wins del roadmap (rank_candidates, código muerto, constantes duplicadas)

**Modificación asociada:** continuación del roadmap maestro
(`20260715_Roadmap_Cierre_Simulador_Operacional.md`, sección "Quick
wins"), tres ítems pendientes cerrados en esta pasada:

1. **`rank_candidates` (Fase 2, bloqueaba consolidación del motor de
   recomendaciones):** verificado con `Grep` directo — tras la
   eliminación de `recommend_rate` (su único otro caller, ya
   eliminada), queda exactamente 1 caller de producción real
   (`pages/simulador_operacional.py:2550`). Confirmado activo, no se
   archiva. Sin cambios de código, solo verificación y cierre de
   documentación.

2. **Candidatos de código muerto restantes (Fase 7):** MCP seguía
   reportando `in_degree=0` para 4 funciones ya eliminadas en `51a4328`
   (staleness ya conocida) más 3 en `02_Analytics/`. Verificadas con
   `Grep`: `michaelis_menten` y `semaforo_autonomia` son falsos
   positivos (se usan como callbacks pasados a `scipy_curve_fit`/
   `.apply()`, el grafo MCP no traza eso). Solo `tiempo_hasta_zona`
   (`02_Analytics/Scripts/differential_equations/estrategia_pilas.py`)
   es código muerto genuino — fuera del alcance del dashboard, decisión
   del equipo de analítica, no eliminado unilateralmente. De los 9
   candidatos originales del roadmap: 4 eliminados, 4 falsos positivos
   descartados con evidencia, 1 genuino pendiente de decisión externa.

3. **Constantes duplicadas (Fase 7):** la única duplicación literal
   real era `_DRAIN_RATE`/`_CRITICAL_PCT` en `components/cards.py`
   (copia exacta de `DRAIN_PCT_H`/`CRITICAL_PCT` de `engine/
   ode_model.py`). Reemplazada por import directo (`from engine.
   ode_model import CRITICAL_PCT as _CRITICAL_PCT, DRAIN_PCT_H as
   _DRAIN_RATE`) — verificado sin riesgo de import circular
   (`ode_model.py` no importa `components`). `AUTONOMY_THRESHOLDS`
   (`rules_engine.py`) resultó no estar duplicado, solo existía en un
   lugar — la premisa original del roadmap estaba parcialmente
   equivocada, corregida con esta verificación.

**Archivos modificados:** `components/cards.py` (import + eliminación
de 2 líneas de dict literal duplicado).

Documentado en `04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md` (Fase 7 avanza de
55% a 75%, blocking matrix y quick wins actualizados).

---

## 2026-07-15 — Sincroniza CHANGELOG.md raíz (Fase 7 del roadmap)

**Modificación asociada:** el roadmap maestro flagged "changelog
completo ❌" — `CHANGELOG.md` (raíz) se detenía en 2026-07-06 (v6,
"T3 en TPH"), mientras `05_Dashboard/packaging/VERSION.txt` ya tenía
v1.2.0 (2026-07-09) y v1.3.0 (2026-07-12) documentados, y todo el
trabajo desde `73b7128` (2026-07-14) hasta hoy no estaba en ningún
changelog.

**Cambio:** agregadas 2 entradas nuevas a `CHANGELOG.md`:
- **v7** — resumen breve de v1.2.0/v1.3.0 (detalle completo ya vive en
  `packaging/VERSION.txt`, no duplicado).
- **v8** — resumen conceptual de toda esta serie de sesiones: reencuadre
  de autonomía (Etapa 1-2), roadmap maestro de cierre, dual score en
  Optimizer V2, el P0 de fidelidad histórica y su diagnóstico causal
  completo (incluyendo el hallazgo de `correa_315`), motor multicelda
  (I+D, no productivo), limpieza de código muerto y constantes, y la
  validación con escenarios dorados. Sin número de versión formal
  asignado — es una decisión de release, no técnica.

**No se modifica `VERSION.txt`** (raíz, sigue en 1.0.0) — queda
documentado en el roadmap que está desincronizado de `packaging/
VERSION.txt` (1.3.0), pendiente de decisión de release sobre qué
número asignar al estado actual.

Documentado en `04_Reports/Technical/
20260715_Roadmap_Cierre_Simulador_Operacional.md` (Fase 7 avanza de
75% a 85%).

---

## 2026-07-15 — Cierra Fase 3 del roadmap: confirma que optimizer_v3.py hereda el dual score sin migración

**Modificación asociada:** el roadmap tenía pendiente "confirmar si
`optimizer_v3.py` necesita el mismo tratamiento" que `optimizer_v2.py`
(dual score, Fase 3.3-3.4). Verificado con lectura de código + ejecución
real: `find_optimal_v3` no calcula ningún score propio, solo llama a
`run_deterministic_grid`/`adaptive_mc_eval` (ya instrumentadas) y
reordena el resultado — `_enrich_v3` muta los dicts in-place, nunca los
reconstruye. Ejecutando `find_optimal_v3` directamente se confirmó que
el resultado ya trae las 9 claves dual-score (`p_dynamic_safe`, `pct_
draining_sagX`, etc.) sin ningún cambio de código.

**Archivos modificados:** `tests/test_optimizer_v2_dual_score.py`
(nueva clase `TestOptimizerV3HeredaDualScore`, 1 test, fija este
comportamiento como regresión).

**Fase 3 del roadmap queda CERRADA (100%)** — era la última fase
técnica de optimización pendiente; lo único que queda es una decisión
de producto diferida (si alguna vez reemplazar `multi_criteria_score`
por la señal dinámica), no trabajo de instrumentación.

15 tests pasando en el archivo (antes 14). Documentado en
`04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md`.
