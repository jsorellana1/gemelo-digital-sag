# Sprint 1 — Gemelo Digital v4.1: Planificador de Turno, Explicabilidad, Mapa de Cuellos de Botella

**Fecha:** 2026-07-06
**Contexto:** implementación del Sprint 1 de la propuesta post-reenfoque
(`20260625_Modelos_Improvement_Summary.md` + priorización 2026-07-06).
Decisión previa confirmada: implementar Sprint 1 completo ahora.

---

## 1. Explicabilidad Operacional

`engine/explicabilidad.py::explain_recommendation(best, pila1, pila2,
duracion_t8, asset)` — traduce campos ya calculados por `find_optimal_v3`
(autonomía, régimen, `p_safe`, brecha P90) a un listado de razones en
lenguaje simple. **No agrega ningún cálculo nuevo**, solo formatea lo que
el optimizador ya produce.

Ejemplo real (pila SAG1=18%, T8=8h):
```
SAG1 recomendado = 1516 TPH
• Pila SAG1 = 18%
• Autonomía estimada = 0.1 h
• Ventana T8 = 8 h
• Régimen operacional: t8_larga
• Riesgo de vaciado estimado = 100%
```

Wireado como acordeón colapsable ("¿Por qué?") dentro del badge de
"Óptimo según pila", para SAG1 y SAG2 por separado.

---

## 2. Mapa de Cuellos de Botella

`engine/bottleneck.py::full_bottleneck_map(sim, ch1_on, ch2_on,
correa315_estado, correa316_estado)` — extiende el detector de cuello de
botella (ya existente desde la sesión de Optimizer V4) a un **mapa
completo de 10 componentes** (CH1, CH2, T1, CV315, CV316, Pila SAG1, Pila
SAG2, SAG1, SAG2, Molinos de bolas), cada uno con color verde/amarillo/rojo
e impacto estimado en TPH cuando es cuantificable directamente (chancado,
correas — usando las mismas fórmulas de capacidad ya validadas en
`ode_model.py`, sin duplicar lógica).

Para pilas/autonomía y molinos de bolas el impacto se deja explícitamente
en `None` — es un riesgo, no una pérdida de capacidad instantánea
cuantificable, y no se fuerza un número sin base real.

Nueva vista "Cuellos de Botella" en el selector de "Vista principal"
(`components/graphs.py::make_bottleneck_map_chart`), disponible en Modo
Rápido y Avanzado (es diagnóstico, no dispara Monte Carlo).

---

## 3. Planificador de Turno

`engine/turno_planner.py::build_hourly_schedule(base_hour, horizonte_h,
duracion_t8, maint_windows, rate1_tph, rate2_tph, bola1_label,
bola2_label)` — cronograma hora a hora reutilizando `engine.scheduler`
(`equipos_en_mantencion`, `sag_forzado_off`), que **ya calculaba
disponibilidad de equipos en función de la hora** — lo único nuevo es
tabular esa evolución para las 24 horas en vez de mostrar solo el estado
en la hora actual.

**Decisión de diseño importante:** el rate SAG1/SAG2 mostrado es
**constante** a lo largo del horizonte (el mismo que recomienda
V3/V4) — el motor no genera un plan que cambie el rate hora a hora dentro
de una misma corrida. Lo que sí varía por hora, con base real, es:
- Disponibilidad de 411/412/511/512 según ventanas de mantención
  programadas (columna "ON"/"MANTENCIÓN" por hora).
- Si la hora cae dentro de la ventana T8.
- Si el rate SAG1/SAG2 se apaga por mantención completa del molino.

Se evitó fabricar un "plan dinámico" que reoptimizara rate hora a hora —
eso habría requerido una re-arquitectura del optimizador (múltiples
corridas encadenadas) fuera del alcance de este sprint, y no estaba
respaldado por ninguna necesidad identificada en el análisis previo.

Nueva vista "Planificador de Turno" (tabla, `components/graphs.py::
make_turno_planificador_table`) — filas resaltadas en rojo claro para
horas en mantención, azul claro para horas T8.

---

## 4. Tests y QA

11 tests nuevos (`tests/test_sprint1_planificador.py`) — cubren:
explicabilidad incluye pila/autonomía/T8/riesgo; mapa de 10 componentes
completo; colores correctos ante CH2 fuera / correa inactiva; cronograma
horario refleja mantenciones solo en su ventana; SAG completo en
mantención apaga el rate todas las horas; T8 activo solo en las primeras
horas del horizonte.

**Suite completa: 70/70 tests pasan** (59 previos + 11 nuevos).
`app.py` importa limpio, 19 callbacks registrados (sin cambios — no se
agregó ningún callback nuevo, todo se integró en callbacks existentes).

---

## 5. Qué no se tocó

Sin cambios en `ode_model.py`, `rules_engine.py`, `risk_engine.py`,
`optimizer_v2.py`/`v3.py` (scoring/grid), tuning de Monte Carlo, ni en la
lógica de `scheduler.py` (solo se reutilizó, no se modificó). Todas las
piezas nuevas son capas de presentación/diagnóstico sobre datos que el
motor validado ya produce.

---

## Pendiente (no incluido en Sprint 1, ver roadmap original)

Prioridades 2-10 de la propuesta (`Inventory Health Index`, autonomía
probabilística P10/P50/P90, riesgo de sobrellenado, costo de cambio
operacional, aprendizaje histórico, dashboard ejecutivo CIO, calibración
continua) quedan para sprints futuros, a definir con el usuario.
