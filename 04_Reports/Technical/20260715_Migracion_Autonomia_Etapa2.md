# Migración de autonomía — Etapa 2 (parcial): `AutonomyContext` + `recommend_action`

Fecha: 2026-07-15. Continuación de la Etapa 1 (2026-07-14, ver
`04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md`,
"Quinta pasada") — donde se separó cómo se **muestra** la autonomía
(dinámica actual vs. vulnerabilidad preventiva histórica). Esta pasada
aborda cómo el simulador **decide** con esas dos métricas.

Alcance del pedido: 6+ módulos (`rules_engine`, `risk_engine`,
`optimizer_v2/v3/v4/v5`, `bottleneck`, `quick_wins`, `hourly_plan`) más
un estudio de sensibilidad de umbrales. Siguiendo el mismo criterio ya
aplicado dos veces en esta serie de sesiones (backlog de 5 mejoras →
solo el ítem de mayor ROI; reencuadre de 17 fases → solo Etapa 1), se
entrega **evidencia completa del mapa de consumidores** pero se
implementa solo el módulo de mayor ROI/menor riesgo:
`rules_engine.py::recommend_action`, el motor de recomendación real
detrás de la UI.

## 1. Mapa de consumidores (Fase 1 del pedido)

`query_graph`/`search_code` (`CALLS|USAGE`), evidencia recolectada antes
de abrir archivos completos:

| Consumidor | Métrica actual | Propósito | Métrica correcta | Acción |
|---|---|---|---|---|
| `rules_engine.py::recommend_action` | `autonomia_sag1/2` (parámetros float directos) | Acción global (EMERGENCIA/EVALUAR_DETENCION/MINIMO_TECNICO/REDUCIR_CARGA/CONSERVADOR/MONITOREAR/OPERACION_NORMAL) | Dinámica gobierna, histórica modula | **MIGRADO esta pasada** |
| `engine/simulator.py::simulate_scenario` (único caller real) | `compute_autonomia(pila_sag1_pct,...)` sobre el **estado inicial** | construir args de `recommend_action` | `AutonomyContext` construido sobre el mismo estado inicial | **MIGRADO esta pasada** |
| `risk_engine.py::compute_iro/compute_iro_series/simple_iro` | `autonomia_sag1_h`/`autonomia_sag2_h` legacy | score IRO | sub-scores dinámico/histórico separados (Fase 5) | REVISAR — diferido |
| `optimizer_v2.py::REF_AUTON_SAG1/2`, `compute_multi_criteria_score` | legacy | ranking de candidatos | dual score (Fase 9) | REVISAR — diferido |
| `optimizer_v3.py::find_optimal_v3` (real caller de UI vía `simulador_operacional.py`) | hereda de `simulate_scenario`/`recommend_action` | grid + selección | hereda automáticamente la migración de `recommend_action` | indirecto — sin cambio propio necesario |
| `optimizer_v4.py::find_optimal_v4`, `optimizer_v5.py::find_optimal_v5` | **`in_degree=0` confirmado por MCP** | N/A | N/A | **Fase 10: sin consumidores de producción, solo documentar** |
| `bottleneck.py`, `quick_wins.py`, `hourly_plan.py` | legacy (`sim["autonomia_sag1/2"]`) | diagnóstico/plan horario | Fases 6-8 | REVISAR — diferido, cada uno su propio ciclo |

### Hallazgo arquitectónico clave

`recommend_action` se invoca en `simulator.py:174-191` sobre el
**estado inicial** del escenario (`compute_autonomia(pila_sag1_pct,
"SAG1")`, usando el pct de entrada crudo), **no** sobre el estado final
de la trayectoria simulada — que es donde la Etapa 1 agregó
`dynamic_net_autonomy_sagX_status` dentro de `simulate_ode`. El
`AutonomyContext` para `recommend_action` no podía tomarse directamente
de las claves de la Etapa 1; se construyó aplicando los mismos
clasificadores (`classify_dynamic_autonomy`,
`classify_historical_vulnerability`, `classify_autonomy_divergence`, ya
existentes en `circuit_state.py`) sobre los valores del **primer paso**
de la trayectoria (`raw["cv315"][0]`, `raw["tph_sag1"][0]`,
`raw["cv316"][0]`, `raw["tph_sag2"][0]`) — reusando la única fuente de
cálculo, no una fórmula nueva (Fase 12 del pedido).

## 2. Reglas migradas — qué métrica usa cada regla

`engine/circuit_state.py` — nuevo `AutonomyContext` (dataclass frozen) +
`build_autonomy_context(...)` (empaqueta los 3 clasificadores de la
Etapa 1 sin recalcular fórmulas).

`engine/rules_engine.py::recommend_action` — nuevo helper
`_accion_por_contexto_dinamico(ctx_sag1, ctx_sag2, duracion_t8_h)` con
el orden de prioridad pedido:

1. SAG/chancado OFF (sin cambio, lógica previa intacta).
2. `AT_CRITICAL_LEVEL` en cualquier SAG → `EMERGENCIA`.
3. `DRAINING`: `<0.5h` → `EMERGENCIA`; `<1.0h` → `EVALUAR_DETENCION`;
   `<duracion_t8_h` restante → `REDUCIR_CARGA` (cuantificado: balance
   neto, horas, ventana, diferencia con la histórica).
4. `FILLING` + vulnerabilidad histórica `CRITICA`/`ALTA` → `MONITOREAR`
   (nunca detención).
5. `STABLE` + vulnerabilidad histórica `CRITICA` → `CONSERVADOR`/
   `MONITOREAR` según haya T8 activo.
6. Si ninguna regla dispara → cae al fallback legacy existente (que ya
   usa la autonomía histórica para modular precaución — cumple la
   "Regla general" del pedido sin necesidad de reescribir esa rama).

`autonomy_context_sag1`/`autonomy_context_sag2` son **opcionales**: si
alguno falta, `recommend_action` se ejecuta byte-por-byte igual que
antes de esta migración (confirmado con 5 casos exactos, ver sección
5).

## 3. Riesgo (`risk_engine.py`) — no migrado esta pasada

Sigue usando `autonomia_sag1_h`/`autonomia_sag2_h` (histórica). La Fase
5 del pedido exige separar `dynamic_depletion_risk`/
`historical_vulnerability_risk`/`equipment_risk`/`window_risk` con pesos
documentados antes de tocar el IRO — un ciclo propio, diferido.

## 4. Optimización — no migrada esta pasada

`optimizer_v2.py`/`optimizer_v3.py` siguen con `REF_AUTON_SAG1/2` y el
score legacy. `find_optimal_v3` hereda automáticamente la migración de
`recommend_action` (porque pasa por `simulate_scenario`), pero el score
de selección de candidatos en sí no cambia — Fase 9, diferida (requiere
diseñar `dynamic_safety_score`/`historical_buffer_score` sin doble
penalización, documentado en el pedido como su propio análisis).

**`find_optimal_v4`/`find_optimal_v5` (Fase 10)**: confirmado vía
`query_graph` (`in_degree=0` en ambos) que **no tienen ningún consumidor
de producción** — solo `tests/test_optimizer_v4.py`/
`test_optimizer_v5.py` los referencian. Por instrucción explícita del
pedido ("Si V5 no está activo: documentarlo; no ampliar su alcance"),
no se tocaron ni se expandieron.

## 5. Compatibilidad

`recommend_action(**kwargs)` sin `autonomy_context_sag1/2` produce el
mismo `(accion, explicacion)` exacto que antes de esta migración,
verificado con 5 combinaciones (`test_compatibilidad_sin_autonomy_
context_es_identica_a_legacy`, comparación de tupla completa, no solo
de la acción). `compute_autonomia`, `calculate_stockpile_autonomy`,
`autonomia_sag1/2`, `legacy_autonomia_sag1/2` sin cambios.

## 6. Escenarios validados

```text
llenando         -> MONITOREAR      (recuperación 163 t/h, vulnerabilidad crítica, sin detención)
drenando_rapido  -> REDUCIR_CARGA   (drena 1454 t/h, crítico en 2.4h, ventana 6.0h)
estable          -> CONSERVADOR     (fallback legacy — dinámica no disparó regla fuerte)
sag_off          -> MONITOREAR      (fallback legacy, mensaje de dependencia intacto)
nivel_critico    -> EMERGENCIA      (AT_CRITICAL_LEVEL, drena 756 t/h, crítico en 2 min)
```

Los 5 escenarios: `|mass_balance_error_sagX| < 1.1e-10 t` (muy por
debajo del umbral 1e-6 t exigido) — el cambio no toca el motor físico.

## 7. Pruebas

```text
python -m pytest tests/test_rules_engine.py -q
→ 25 passed (11 nuevos en TestRecommendActionAutonomyContext: FILLING+
  vuln crítica, DRAINING+dinámica crítica, DRAINING+ventana, STABLE+
  vuln crítica, SAG_OFF sin romper, nivel crítico dinámico, mensaje
  cuantificado, compatibilidad legacy exacta, suite no regresiona)

python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
→ 367 passed en 110.72s, cero regresiones (358 previos de la Etapa 1 +
  9 de esta pasada: los 11 nuevos de TestRecommendActionAutonomyContext
  menos 2 ya contados en la corrida anterior de test_rules_engine.py)
```

## 8. MCP — qué pudo validarse y qué no

`index_status` reporta `head_sha == base_sha` (HEAD actual) incluso
tras confirmarlo de nuevo esta pasada — el indexador de
`codebase-memory-mcp` lee del commit de git, no del árbol de trabajo con
cambios sin commitear (regla de esta sesión: no commitear sin pedido
explícito). Por eso `AutonomyContext`/`build_autonomy_context`/
`_accion_por_contexto_dinamico` no son visibles vía `search_graph` en
esta pasada. Lo que SÍ se validó vía MCP antes de tocar código: el mapa
de consumidores completo de la sección 1 (incluyendo la confirmación
`in_degree=0` de V4/V5, evidencia previa a cualquier edición). El
acoplamiento de los símbolos nuevos se confirmó por lectura directa: 
`AutonomyContext`/`build_autonomy_context` solo se usan en
`simulator.py`; los nuevos parámetros de `recommend_action` solo se
pasan desde ese mismo único call site.

## 9. Riesgos residuales

- **Incoherencia transitoria explícita**: `risk_engine.py`,
  `bottleneck.py`, `quick_wins.py`, `hourly_plan.py`, y el score de
  `optimizer_v2.py`/`optimizer_v3.py` siguen basados en la autonomía
  histórica. La recomendación principal (`recommend_action`) ya prioriza
  la dinámica, pero el score de riesgo (IRO) y el ranking de
  optimización que se muestran junto a ella todavía no — puede leerse
  como inconsistencia si no se explica (ya explicado aquí).
- **Mensaje legacy duplicado**: `simulator.py` sigue agregando
  `"SAG1 autonomia critica en N min"` (basado en la trayectoria legacy,
  líneas 193-197, sin cambios en esta pasada) al final de la
  explicación, incluso cuando la nueva rama dinámica ya dio un mensaje
  cuantificado — es información adicional, no contradictoria, pero
  vale la pena revisar si consolidarla en una sesión futura.
- **`REF_AUTON_SAG1/2`/tolerancias `RESTRICTED`/Fase 13**: no auditadas
  ni sensibilizadas esta pasada — quedan como próximo paso de mayor
  esfuerzo (requiere correr 6 combinaciones de umbral, un estudio
  propio).

## Próximo paso recomendado, priorizado por ROI

| Prioridad | Ítem | Motivo |
|---|---|---|
| 1 | `risk_engine.py` (Fase 5): separar `dynamic_depletion_risk`/`historical_vulnerability_risk` | El IRO es lo segundo más visible al JdS después de la recomendación; sin esto, riesgo mostrado puede seguir contradiciendo el badge dinámico de la Etapa 1 |
| 2 | `optimizer_v2.py`/`optimizer_v3.py` (Fase 9): dual score con anti-doble-penalización documentada | Afecta directamente qué candidato se recomienda como "óptimo" |
| 3 | `bottleneck.py` (Fase 6): `LOW_BUFFER` vs `DYNAMIC_DEPLETION` | Riesgo de clasificar mal una pila que se está llenando como cuello de botella de agotamiento |
| 4 | `quick_wins.py`/`hourly_plan.py` (Fases 7-8) | Menor urgencia — paneles secundarios, no la recomendación principal |
| 5 | Sensibilidad de tolerancias `RESTRICTED` (Fase 13) | Requiere un estudio propio con 6 combinaciones de umbral, no es un cambio de código simple |
