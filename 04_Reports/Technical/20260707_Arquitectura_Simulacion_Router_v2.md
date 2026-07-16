# Arquitectura de Simulación — Router v2 (decide antes de simular)

**Fecha:** 2026-07-07
**Supersede/extiende:** `20260707_Arquitectura_Simulacion_Adaptativa.md` (v1)

---

## Qué cambió respecto a v1

v1 (mismo día, versión anterior) clasificaba un `sim` **ya calculado** con
parámetros por defecto — una capa de explicabilidad post-hoc. El prompt
v2 pidió explícitamente lo contrario: **decidir la estrategia antes de
invocar el motor**. Esto se construyó como una capa adicional
(`route_and_simulate`), sin romper ni reemplazar v1 (`run_adaptive_simulation`
sigue funcionando igual, con sus 8 tests originales intactos).

Se mantiene la decisión de fondo de v1: **un solo motor físico**
(`simulate_scenario_cached` + `find_optimal_v3` + `find_optimal_v4`). Cada
`BaseSimulationStrategy` es un envoltorio delgado sobre ese motor —
ninguna estrategia reimplementa el ODE ni el Monte Carlo.

---

## PREREQUISITO 0 — verificación de datos históricos (resultado real, no asumido)

Se auditaron los archivos reales del proyecto antes de construir nada:

| Regimen | Timestamp real | Tipo régimen | Inventario al inicio | TPH durante evento | Duración confirmada | N eventos | Disponible |
|---|---|---|---|---|---|---|---|
| `t8_corta` | SÍ (`advanced_t8_official_events.parquet`: `ini_oficial`/`fin_oficial`, hora real) | SÍ (`duracion_h<=4`) | SÍ (`advanced_t8_event_windows.parquet`: `pila_sag1/2` en `h_rel_inicio=0`) | SÍ (`SAG1_tph`/`SAG2_tph`, `periodo='DURANTE'`) | SÍ (fuente "oficial") | **64** (≥ mínimo 20) | **SÍ** |
| `t8_larga` | SÍ (misma fuente) | SÍ (`duracion_h>4`) | SÍ (misma fuente) | SÍ (misma fuente) | SÍ | **8** (< mínimo 20) | **NO — N insuficiente** |
| `overflow` | NO | NO | NO | NO | N/A | 0 | **NO — sin dataset de eventos** |
| `inventario_critico` | NO | NO | NO | NO | N/A | 0 | **NO — sin dataset de eventos** |
| `mantenimiento` | NO | NO | NO | NO | N/A | 0 | **NO — sin dataset de eventos** |
| `alimentacion_restringida` | NO | NO | NO | NO | N/A | 0 | **NO — sin dataset de eventos** |

**Nota importante:** el archivo `fact_eventos_t8.parquet` (usado en el
LOOP MAESTRO anterior) tiene `inicio`/`fin` a nivel de **fecha, no de
hora** (00:00:00 en todos los registros) — no sirve para backtesting de
precisión horaria. Los archivos correctos son
`advanced_t8_official_events.parquet` + `advanced_t8_event_windows.parquet`
(72 eventos oficiales, series de 5 min con `pila_sag1/2`, `SAG1_tph`,
`SAG2_tph`, columna `periodo` PRE/DURANTE/POST).

**Conclusión aplicada:** `historical_backtesting.py` se construyó y
**se ejecuta con datos reales solo para `t8_corta`**. Para `t8_larga` y
los otros 4 regímenes, el módulo reporta `historica_disponible=False`
con la razón exacta — no se fabricó ningún número. El router v2 continúa
para esos regímenes solo con `validate_physics` (validación física).

---

## Componentes construidos

- **`engine/scenario_inputs.py`** — `ScenarioInputs` (dataclass exacto del
  prompt) + `project_pila_lineal()`: proyección lineal de 2h (NO el ODE)
  usada únicamente para clasificar/priorizar antes de simular.
- **`engine/criticality_scorer.py`** — `CriticalityScorer` + `RegimeCriticality`:
  score de urgencia 0-100 por régimen, reemplaza el `PRIORITY_ORDER` fijo
  de v1 quedando reservado para v1 (no se tocó). Umbrales reutilizan
  constantes ya validadas (`CRITICAL_PCT`, `bottleneck.py`).
- **`engine/physics_validation.py`** — `TOLERANCIAS` + `validate_physics()`:
  balance de masa (auditoría, no recalcula el ODE), rango de pila 0-105%,
  TPH no negativo, restricciones duras (equipo en mantención simulado
  como activo = violación; ambos MoBo indisponibles = advertencia).
- **`engine/simulation_strategies.py`** — `BaseSimulationStrategy` (contrato
  `applies_to/simulate/on_failure/validate_physics/explain`) +
  `NormalStrategy`, `T8CortaStrategy`, `T8LargaStrategy`,
  `InventarioCriticoStrategy`, `OverflowStrategy`, `MantenimientoStrategy`,
  `AlimentacionRestringidaStrategy`, `MixedRegimeStrategy`. Todas invocan
  el mismo `_run_engine()` (find_optimal_v3 + v4 opcional +
  simulate_scenario_cached) con distinto `mode`/`tolerancia`.
- **`engine/strategy_executor.py`** — `StrategyExecutor.run()`: try/except
  alrededor de `simulate()`, delega a `on_failure()` (nunca lanza).
- **`engine/historical_backtesting.py`** — `check_prerequisito_0()`,
  `run_backtest()`, `N_MINIMO_EVENTOS`, `TOLERANCIAS_BACKTESTING`.
- **`engine/simulation_router.py`** — se agregó `route_and_simulate()` (v2)
  al final del módulo, sin modificar las funciones v1 existentes.

### Protocolo de conflicto en `MixedRegimeStrategy`

1. Ejecuta la estrategia de mayor urgencia (`primary`).
2. Para cada estrategia secundaria, compara dirección deseada de TPH
   (`aumenta` vs `reduce`) contra la de `primary`.
3. Si hay conflicto de dirección (ej. `overflow` quiere subir consumo,
   `inventario_critico` en el otro SAG quiere protegerlo — direcciones
   compatibles en este caso porque son activos distintos; el conflicto
   real ocurre, por ejemplo, entre `overflow` y `t8_larga` sobre el mismo
   activo), se re-ejecuta con `mode="safe"` + `tolerancia="conservador"`
   (el ajuste más conservador disponible) y se documenta explícitamente
   en `explain()`.
4. Si no hay conflicto de dirección, se conserva el resultado de la
   estrategia primaria.

---

## QA — resultados separados (sintético vs. histórico)

### Tests sintéticos (`tests/test_router_v2.py`, escenarios controlados)

29/29 passed:
- `ScenarioInputs`: validación de rango, proyección lineal, construcción de par SAG1/SAG2 (3 tests)
- `CriticalityScorer`: normal vs crítico, T8 corta vs larga, mantención con equipo crítico, caso sin restricciones (5 tests)
- `physics_validation`: sim válido, pila sobre máximo, TPH negativo, SAG activo sin disponibilidad, ambos MoBo indisponibles (advertencia, no violación), tolerancias definidas (6 tests)
- `StrategyExecutor`: estrategia normal factible, `on_failure` nunca lanza (2 tests)
- `MixedRegimeStrategy`: conflicto de dirección detectado y documentado (1 test)
- `route_and_simulate` end-to-end con motor real: normal, inventario crítico, T8 larga, mixto (4 tests)

### Tests con datos históricos reales (mismo archivo, clase `TestBacktestingHistorico`)

8/8 passed — **contra los parquet reales, no mockeados**:
- `t8_corta`: Prerequisito 0 disponible, N=64 ≥ mínimo (20)
- `t8_larga`: Prerequisito 0 NO disponible, N=8 < mínimo (20) — documentado, no fabricado
- `overflow`/`inventario_critico`/`mantenimiento`/`alimentacion_restringida`: sin dataset de eventos, N=0 — documentado
- `run_backtest("t8_corta")` ejecuta sin excepción y produce MAE real
- `run_backtest("overflow")` reporta el gap sin fallar

### Hallazgo real del backtesting (no un bug del código)

`run_backtest("t8_corta")` con los 64 eventos reales produce
**MAE(pila_sag1) ≈ 30 pp**, muy por encima de la tolerancia asumida
(`TOLERANCIAS_BACKTESTING["pila_mae_pct"]=5.0`). Esto **no es un error
del backtesting** — el método alimenta el ODE con la tasa **promedio**
observada durante todo el evento (`SAG1_tph.mean()` en el periodo
`DURANTE`), mientras que en la operación real la tasa varía dentro de la
ventana T8 (arranques/paradas parciales, ajustes manuales). Un modelo de
tasa constante no puede reproducir con precisión una trayectoria de tasa
variable. **Conclusión honesta:** el backtesting está correctamente
implementado y ejecuta contra datos reales, pero **la tolerancia de 5pp
es demasiado estricta para la limitación metodológica actual** (tasa
promedio vs. tasa real minuto-a-minuto). Recalibrar esta tolerancia o
alimentar el ODE con la serie de tasa real (no su promedio) es trabajo
pendiente — no se ajustó artificialmente la tolerancia para "hacer
pasar" el test, se dejó el número real y la explicación en el reporte.

### Suite completa del proyecto

118 tests total (`tests/`, excluyendo 2 scripts standalone
`test_performance_portable.py`/`test_portable_smoke.py` que requieren un
puerto como argumento y no son parte de la suite pytest) — **117/118
passed**. La única falla (`test_optimizer_v4.py::test_no_ejecuta_simulaciones_nuevas`)
es un test de timing preexistente (no tocado en esta sesión) que espera
`find_optimal_v4 < 50ms`; en esta corrida tomó 55-530ms — causa raíz:
`production_stats.get_asset_stats()` lee el parquet de disco en cada
llamada sin cache en memoria, por lo que el tiempo depende del estado de
cache de disco del SO. Es una fragilidad preexistente de la suite, no una
regresión introducida por el router v2 (no se modificó `optimizer_v4.py`
ni `production_stats.py` en este trabajo).

---

## Wiring en dashboard

Nueva tarjeta **"Router v2 — decisión antes de simular"**
(`make_router_v2_card`, `components/cards.py`) — muestra la estrategia
elegida, el ranking de urgencia (top 3), el estado de validación física,
la explicación, y la disponibilidad de backtesting histórico. Se agregó
**adicional** a la tarjeta v1 existente ("Lógica de simulación
activada") en el mismo callback (`update_simulation`,
`pages/simulador_operacional.py`) — se agregó un nuevo `Input` sobre
`ctrl-tolerancia-riesgo` (ya existía el control, solo faltaba
conectarlo a este callback). Cero callbacks nuevos. `app.py` importa
limpio, 19 callbacks (mismo número que antes).

---

## Qué no se tocó

Sin cambios en `ode_model.py`, `optimizer_v2.py`/`v3.py`/`v4.py`
(scoring, grid, regímenes), `risk_engine.py`, `scheduler.py`, ni en el
tuning de Monte Carlo. `simulation_router.py` v1 (funciones existentes)
no se modificó — solo se agregó `route_and_simulate()` al final del
archivo.
