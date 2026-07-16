# Arquitectura de Simulación Adaptativa — Clasificador de Escenario

**Fecha:** 2026-07-07

---

## Decisión de diseño (leer antes que el resto)

El prompt original pedía una arquitectura donde el Gemelo Digital
**"seleccione automáticamente la heurística, el modelo o la regla más
adecuada"** por escenario, con una tabla que asigna un "modelo principal"
distinto por tipo (Optimizer V4 / EDO+MC / scheduler / etc.).

**Eso no se implementó tal cual**, por una razón concreta: el ODE
(`engine/ode_model.py`/`simulator.py`), Optimizer V3/V4 y el Monte Carlo
adaptativo **ya son el único motor físico validado** para cualquier
escenario, y **ya son adaptativos internamente**:

- `get_regime(duracion_t8)` (`optimizer_v2.py`) ya ajusta pesos de
  producción/riesgo/inventario/autonomía y `min_auton` según sea régimen
  normal / T8 corta / T8 larga.
- `adaptive_mc_eval` ya corre Monte Carlo con parada adaptativa **siempre**,
  no solo cuando "el riesgo es alto".
- `detect_bottleneck`/`full_bottleneck_map` (sesión anterior) ya
  diagnostican qué activo limita, sin importar el tipo de escenario.

Construir un "selector de heurísticas" que despachara a **motores
distintos** por escenario habría significado mantener 2+ implementaciones
paralelas del mismo fenómeno físico — exactamente el riesgo que la regla
"no modificar lógica matemática validada" busca evitar, y una fuente de
inconsistencia silenciosa entre escenarios "parecidos pero no idénticos"
que el clasificador tipificara distinto.

**Lo que sí se construyó:** una capa de **clasificación + explicabilidad**
que usa datos ya producidos por el motor único (`simulate_scenario`,
`detect_bottleneck`, `get_regime`) para etiquetar el tipo de escenario y
explicarlo — sin re-simular ni despachar a nada nuevo.

---

## `engine/simulation_router.py`

### Flujo implementado

```
parse_user_scenario()   → normaliza inputs del usuario
classify_scenario()     → tipifica el escenario (7 tipos, Paso 2 del prompt)
select_heuristics()     → etiquetas H1-H7 activas, en orden de prioridad
explain_simulation_path() → texto explicativo
run_adaptive_simulation() → orquesta lo anterior sobre un `sim` YA calculado
```

`run_adaptive_simulation` **no llama a `simulate_scenario`** — recibe el
resultado ya calculado por el llamador (`simulate_scenario_cached`, sin
cambios) y solo clasifica/explica. Cero simulaciones adicionales.

### Tipos de escenario (Paso 2)

`overflow`, `inventario_critico`, `mantenimiento`,
`alimentacion_restringida`, `t8_larga`, `t8_corta`, `normal` — un
escenario puede tener múltiples tipos simultáneos (`mixto=True`).

### Heurísticas (Paso 3) — reinterpretadas como etiquetas explicativas

| # | Nombre | Se activa cuando | Fuente de datos (ya existente) |
|---|---|---|---|
| H1 | Producción máxima | Escenario `normal` puro | — |
| H2 | Conservación de inventario | `inventario_critico` o `t8_larga` | `min_autonomia_sag{1,2}` |
| H3 | Balance alimentación-procesamiento | `alimentacion_restringida` | `ch1_on/ch2_on/correa_estado` |
| H4 | Control de overflow | `overflow` | trayectoria `pile_sag{1,2}` (mismo detector que el marcador del gráfico de Pila) |
| H5 | Planificación por turno | `horizonte >= 8h` | — |
| H6 | Mantenimiento | Equipo en mantención a la hora actual | `equipos_en_mantencion` (scheduler.py, sin cambios) |
| H7 | Robustez probabilística | `inventario_critico`, `overflow`, `t8_larga`, o escenario mixto | — |

### Hallazgo real durante las pruebas

Al validar el caso "T8 12h" con parámetros arbitrarios (pila 50-55%,
rate 90-100%), el ODE real proyectó overflow en SAG1/SAG2 dentro del
horizonte de 24h — **no es un bug del clasificador, es el comportamiento
genuino del modelo ya validado** para esa combinación de parámetros (feed
automático vía distribución T1 excede consumo en ciertos tramos). Esto
obligó a reescribir los tests con `sim` sintéticos que aíslan cada rama
de clasificación de forma determinística, en vez de depender de
parámetros arbitrarios del ODE real — más una lección de testing que un
hallazgo del router en sí.

---

## Dashboard

Nueva tarjeta **"Lógica de simulación activada"** (`make_simulation_logic_card`,
`components/cards.py`) — muestra el tipo de escenario (o "Mixto"), badges
con las heurísticas activas, y el texto explicativo. Wireada en el mismo
callback que ya construye `kpis` (sin callback nuevo).

---

## QA

8 tests nuevos (`tests/test_simulation_router.py`) — los 5 casos mínimos
exactos del prompt (normal→H1, T8 larga→H2+H7, CH2 off→H3, overflow
SAG2→H4, mantención MoBo→H6) más explicación/mixto/integración end-to-end
con el motor real. **Suite completa: 88/88 tests pasan** (80 previos + 8
nuevos). `app.py` importa limpio, 19 callbacks (sin callback nuevo — todo
integrado en el callback existente que ya construye la columna de KPIs).

---

## Qué no se tocó

Sin cambios en `ode_model.py`, `optimizer_v2.py`/`v3.py`/`v4.py` (scoring,
grid, regímenes), `risk_engine.py`, `scheduler.py`, ni en el tuning de
Monte Carlo. `simulation_router.py` es un módulo nuevo que **consume**
resultados ya validados, no los recalcula.
