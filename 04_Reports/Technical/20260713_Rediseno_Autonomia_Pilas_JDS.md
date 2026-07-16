# Rediseño Simulador Operacional — Autonomía de Pilas, Rates Sostenibles y Quick Wins JdS

**Fecha:** 2026-07-13
**Base:** Gemelo Digital Molienda v1.3.0 (`05_Dashboard/`)
**Plan de implementación:** ver historial de la sesión (plan aprobado antes de codificar)

---

## 1. Motivación

El simulador operacional venía creciendo desde v1.0 con una lógica aditiva:
cada mejora (Router V2, Harmony Index, Monte Carlo adaptativo, Optimizer
V3→V5) agregó una vista, un botón o un gráfico nuevo a la pantalla
principal. El resultado, a la fecha del rediseño, era una vista con 10
gráficos intercambiables, un cockpit de 4 columnas, un accordion de detalle
técnico y un bloque de comparación — potente, pero que no respondía en
menos de 10 segundos las preguntas que un Jefe de Sala realmente hace
durante una ventana T8 o una mantención:

> ¿Cuánto aguantan las pilas? ¿Qué rate uso? ¿Qué MoBos opero? ¿Cuál pila
> llega primero a crítico? ¿Cuándo empieza a recuperar? ¿Qué acción rápida
> conviene?

Este rediseño reenfoca la **vista principal** a 6 bloques fijos + 1
gráfico dominante, sin perder ninguna capacidad existente — todo lo que no
respondía directamente esas preguntas se movió a un panel "Ver detalle
técnico" colapsado por defecto, no se eliminó.

---

## 2. Mapeo pregunta → bloque UI

| Pregunta del JdS | Bloque | Fuente de datos |
|---|---|---|
| ¿Aguanto el escenario? | 6.1 Estado general | `make_estado_general_card` (IRO + P(seguro) + autonomía mínima, 3 niveles) |
| ¿Cuánto aguanta SAG1/SAG2? | 6.2 / 6.3 Autonomía | `make_autonomia_resumen_card` (autonomía esperada, tiempo a crítico, pila mínima proyectada, estado) |
| ¿Qué rate uso? ¿Qué MoBos? | 6.4 Recomendación | `make_recomendacion_corta_table` (rate actual/recomendado + MoBos recomendados, 2 filas) |
| ¿Cuándo empieza a recuperar? | 6.5 Recuperación | `make_recuperacion_card` + `engine.balance_diagnostics.compute_recovery_time` |
| ¿Qué acción rápida conviene? | 6.6 Quick win | `make_quick_win_card` + `engine.quick_wins.evaluate_quick_wins` |
| ¿Cuándo empieza a bajar/sube/mínimo/crítico? | Gráfico único | `make_master_pile_chart` (extiende `make_pile_chart` con mantención, mínimo proyectado, inicio de recuperación) |

---

## 3. Decisiones de arquitectura

### 3.1 Nada se elimina, se mueve

El código y las vistas existentes (10 opciones de `sim-main-view`, MC fan
chart, sensibilidad, top5, tabs secundarias, Óptimo según pila, Monte
Carlo manual) siguen intactos, reubicados dentro de "Ver detalle técnico"
(colapsado por defecto — antes, por un detalle de configuración del
`Accordion`, este panel arrancaba **abierto**; el rediseño corrige eso de
paso). El toggle Rápido/Avanzado (`ctrl-app-mode`) se eliminó: ya no
aporta nada cuando el detalle técnico vive siempre en el mismo lugar, no
detrás de un modo.

### 3.2 Ranking de rate: prioridad estricta, no score ponderado

`engine/rate_recommendation.py` implementa el orden de prioridad
lexicográfico pedido (evitar vaciado → evitar overflow → autonomía mínima
→ continuidad → recuperación → cambios bruscos → producción), donde cada
nivel **solo desempata** entre los candidatos que sobrevivieron el nivel
anterior — nunca se compensan entre sí. Esto es deliberadamente distinto
de `optimizer_v5.py::score_v5_candidate`, que combina todo en una suma
ponderada. V3/V4/V5 siguen intactos para quien los use desde detalle
técnico; `rate_recommendation.py` es la capa nueva que decide qué se
muestra en el bloque 6.4 y en la columna "Alternativo" de la comparación
de escenarios (sección 9).

### 3.3 Escenario "Alternativo" — generado automáticamente, sin costo extra

En vez de correr una búsqueda V3 completa (4-9.5s en frío, ya documentado
como fuera del SLA de 3s en `tests/test_ui_response_time.py`), el
"Alternativo" se arma re-rankeando 3 candidatos ya calculados en el mismo
callback (Actual, Recomendado V3-band, Producción máxima P90+2 MoBos) con
`rank_candidates()`. Esto mantiene el principio de "botón único" (nada que
el JdS deba configurar) sin agregar una simulación cara nueva.

### 3.4 Quick wins: catálogo fijo, evaluación directa

`engine/quick_wins.py` no optimiza — evalúa un catálogo fijo de 8 acciones
(reducir SAG1/SAG2 N TPH x H horas, mover CV315/CV316, reducir T3, cambiar
MoBos) contra el escenario ya simulado (`simulate_scenario_cached`, mismo
mecanismo que usa toda la página), y ordena por beneficio/costo
(Δautonomía / |Δproducción%|). Solo se muestran acciones con
Δautonomía > 0.

### 3.5 Hora de recuperación

`engine/balance_diagnostics.py` ya tenía `compute_post_t8_balance`
(clasifica recupera/plana/drena en el instante justo después de T8). Se
agregó `compute_recovery_time`, que además busca la primera hora en que
la pila cruza el umbral de alerta (`WARNING_PCT`, mismo umbral calibrado
existente) — solo si `Qin>Qout` en ese tramo; si no, no se extrapola.

---

## 4. Archivos modificados

- **Nuevo:** `engine/quick_wins.py`, `engine/rate_recommendation.py`.
- **Extendido:** `engine/balance_diagnostics.py` (`compute_recovery_time`, `explain_recovery`).
- **Extendido:** `components/graphs.py` (`make_master_pile_chart`, `make_qin_qout_chart`).
- **Extendido:** `components/cards.py` (6 funciones nuevas para los bloques 6.1-6.6 y sección 9).
- **Reestructurado:** `components/controls.py` (sidebar recortada a entradas mínimas; tolerancia de riesgo, modo de vista, distribución T1 y acciones manuales V3/MC movidas a un `AccordionItem` "Avanzado"; toggle Rápido/Avanzado eliminado).
- **Reestructurado:** `pages/simulador_operacional.py` (layout de 6 bloques + gráfico único + detalle técnico; callback `update_simulation` extendido con 8 outputs nuevos, reusando datos ya calculados en el mismo callback — sin duplicar simulaciones salvo 1 corrida extra cacheada para el candidato "producción máxima").
- **Extendido:** `assets/styles.css` (`.estado-general-banner`, `.quick-win-card`, reusan los tokens de color ya definidos).
- **Corregido:** `tests/test_performance_portable.py::measure_tab_change` (medía el callback `toggle_modo_rapido_avanzado`, eliminado en este rediseño; ahora mide el cambio de `sim-main-view` directo, que ya no tiene un toggle liviano intermedio).

---

## 5. Qué NO se hizo en este pase (brechas explícitas)

- **Fase 15 (validación histórica):** medir error de nivel/autonomía/tiempo
  crítico/hora de recuperación/condición crece-estable-drena contra
  eventos T8 reales es un trabajo de analítica separado, del mismo tamaño
  que la Fase 6 ("análisis de valor incremental") ya identificada y
  pospuesta en el diseño de la sábana maestra de datos
  (`20260713_Sabana_Maestra_Fase10_Loop_Respuestas.md`). Recomendación:
  reusar `historical_backtesting.py` (ya calcula `cv_mae_sag1_pct` y
  errores de tiempo por evento) como base.
- **UX de 1366×768 sin scroll:** el layout se diseñó para caber sin scroll
  con los 6 bloques + gráfico en esa resolución, pero no se verificó
  pixel-a-pixel en un dispositivo real de esa resolución exacta — se
  probó funcionalmente (callback, datos, ausencia de errores), no
  visualmente a esa resolución específica.
- **Reglas de MoBos (sección 11) como función explícita:** hoy la
  recomendación de MoBos sigue viniendo de `check_bola_rule`/R16 (regla
  dura ya existente, nunca 0 MoBos con SAG operativo) más el candidato
  ganador de `rate_recommendation.rank_candidates`. No se escribió una
  función `recommend_mobos()` separada — las 3 reglas de la sección 11 ya
  están satisfechas por la combinación de R16 (regla dura) + el filtro de
  autonomía mínima segura (nivel 3 del ranking), pero no hay un único
  punto de código que las declare juntas explícitamente.

---

## 6. Verificación realizada

- `python -m pytest tests -q` (excluyendo los 2 scripts standalone que no
  son suites pytest): **201 passed**, mismo resultado que antes del
  rediseño — sin regresiones.
- Import estático de todos los módulos tocados: sin errores de sintaxis.
- App levantada en vivo (`python run_app.py`): arranque limpio, layout
  servido sin ids duplicados (verificado contra `/_dash-layout`), y el
  callback `update_simulation` (23 outputs) confirmado registrado con la
  firma exacta esperada contra `/_dash-dependencies`.
- Cada función nueva (`compute_recovery_time`, `evaluate_quick_wins`,
  `rank_candidates`, `make_master_pile_chart`, `make_qin_qout_chart`, las
  6 cards nuevas) ejercitada directamente con datos simulados reales
  (T8=4h, pila SAG1=40%, pila SAG2=55%) — sin excepciones, resultados
  fisicamente coherentes (ej. SAG1 con menor drenaje relativo mostró
  `estado="drena"` sin hora de recuperación; SAG2 mostró `estado="recupera"`
  con hora de recuperación calculada).
- No se corrió la Fase 6 de `release_portable.bat` (build portable) como
  parte de este cambio — se recomienda regenerar el `.exe`/`.zip` cuando
  se decida distribuir esta versión.
