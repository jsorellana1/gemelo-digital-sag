# Validación del motor de recomendaciones — escenarios dorados

Fecha: 2026-07-15. Ejecuta la sección 29 del programa de validación
estadística pedido ("Validación del motor de recomendaciones... crear
escenarios donde la acción correcta sea conocida"). No modifica
`rules_engine.py` — solo agrega tests que documentan, con evidencia
ejecutable, el comportamiento real de `recommend_action` frente a los 5
escenarios canónicos del pedido.

**Reproducible:** `05_Dashboard/tests/test_golden_scenarios_
recommend_action.py` (`pytest tests/test_golden_scenarios_recommend_
action.py -v`).

## Resultado: 4/5 escenarios correctos, 1 gap real confirmado

| Caso | Escenario | Esperado (dominio) | Real (código) | Veredicto |
|---|---|---|---|---|
| 1 | Pila baja + llenando | `MONITOREAR` | `MONITOREAR` | ✅ |
| 2 | Pila alta + drenando muy rápido | Reducir rate | `REDUCIR_CARGA` | ✅ |
| 3 | SAG OFF + alimentación activa | Riesgo de overflow | `OPERACION_NORMAL` | ❌ **GAP** |
| 4 | Agotamiento antes del fin de ventana | Acción cuantificada | `EMERGENCIA` con tasa+tiempo en el mensaje | ✅ |
| 5 | Ventana termina antes del crítico | Mantener y monitorear | `MONITOREAR` | ✅ |

## Caso 3 — gap confirmado: sin detección de riesgo de overflow

**Escenario:** SAG1 apagado (`sag1_activo=False`), SAG2 operando,
`pile_sag1_pct=96.0` (pila casi llena, sin consumo porque el molino
está detenido pero la alimentación aguas arriba sigue activa).

```python
recommend_action(
    autonomia_sag1=3.0, autonomia_sag2=8.0,
    pile_sag1_pct=96.0, pile_sag2_pct=50.0,
    t8_activo=False, sag1_activo=False, sag2_activo=True,
    rate_sag1_tph=0.0, rate_sag2_tph=2000.0,
)
# -> ('OPERACION_NORMAL', 'Condiciones normales. SAG1(96%): 3.0h OK | ...
#     | SAG1 (Molino 401) DETENIDO: operando solo con SAG2')
```

**Por qué ocurre (leyendo el código, no especulando):**
`recommend_action` (`rules_engine.py`) solo agrega una nota informativa
a `extras` cuando `sag1_activo=False` ("SAG1 DETENIDO: operando solo
con SAG2") — esa nota queda concatenada al final del mensaje pero
**nunca cambia la acción**. La cadena de decisión completa (`min_auton`,
`chancado_cap_tph`, `worst` status, `min_pile`, `t8_activo`) no incluye
ninguna condición sobre pila **alta** combinada con SAG apagado. El
motor de reglas dinámicas (`_accion_por_contexto_dinamico`, Etapa 2)
tampoco cubre este caso: solo actúa sobre `AT_CRITICAL_LEVEL`,
`DRAINING` y `FILLING`+vulnerabilidad — no existe una rama para "pila
cerca del 100% mientras el equipo que la consume está detenido".

Esto coincide exactamente con lo que la sección 26 del prompt de
validación pedía verificar explícitamente ("Pila llena: evaluar
overflow y rechazo de alimentación") — **no es una brecha hipotética,
es un caso real no cubierto**, confirmado ejecutando el código, no
inferido de la lectura.

**No se corrige en esta pasada** — agregar una acción nueva (ej.
`RIESGO_OVERFLOW`) o una condición que reclasifique este escenario es
una decisión de producto (qué debe recomendar el sistema en overflow
inminente: ¿reactivar el SAG?, ¿desviar a T3?, ¿alertar sin acción
automática?) que corresponde al Jefe de Sala/Metalurgista, no una
elección unilateral de ingeniería — mismo criterio ya aplicado en Fase
3.5 del roadmap para la decisión V4/V5.

**Test dejado como `xfail` documentado** (no oculto, no removido):
`test_caso3_sag_off_alimentacion_activa_espera_riesgo_overflow` en
`test_golden_scenarios_recommend_action.py`, con `strict=True` — si
algún día el motor empieza a cubrir este caso, el test fallará "por
éxito inesperado" y forzará actualizar el test en vez de dejar el gap
documentado y olvidado silenciosamente.

## Casos 1, 2, 4, 5 — confirmados sin cambios necesarios

Los 4 escenarios restantes ya están cubiertos correctamente por la
lógica existente (`_accion_por_contexto_dinamico`, Etapa 2 del
reencuadre de autonomía, 2026-07-15 temprano en el día). El caso 4
además se verificó explícitamente que el mensaje trae una tasa (t/h) y
un tiempo (min/h) cuantificados, no solo una etiqueta de severidad —
cumple el requisito de "recomendación cuantificada" de la sección 25
del prompt.

## Alcance no cubierto en esta pasada

- Las funciones de recomendación "sombra" (`rate_recommendation.py::
  rank_candidates`, `circuit_state.py::generate_operational_
  recommendation`) — ya identificadas y clasificadas en la Fase 2 del
  roadmap maestro, no se re-evaluaron aquí.
- Modelo estadístico de segunda opinión (sección 27 del prompt:
  logística multinomial/ordinal para clasificar acción histórica) — no
  existe un dataset de "acción tomada por el operador" en el repo para
  entrenar esto; requeriría bitácora operacional real, no solo la serie
  física de 5 min ya disponible.
- Análisis causal formal (DAG, sección 28) de acción→resultado — fuera
  de alcance de esta pasada.

## Conclusión

El motor de recomendaciones (`recommend_action`) pasa 4 de 5 escenarios
dorados del pedido. El único gap encontrado (overflow con SAG apagado)
es real, reproducible y ya documentado como test `xfail` — no bloquea
el uso actual del sistema (la nota informativa sigue apareciendo en el
mensaje), pero sí significa que **el sistema no escala la severidad de
la acción** en ese escenario específico. Se recomienda llevar este
hallazgo al Jefe de Sala/Metalurgista para decidir la acción esperada
antes de implementar una corrección.
