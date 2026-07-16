# Fase 1 Multi-celda - Pilas SAG

Fecha: 2026-07-15

## Alcance

Se implemento una primera version **opcional** del modelo multi-celda
para pilas SAG en el motor del simulador. No reemplaza el modelo
agregado actual; queda apagado por default y solo se activa cuando se
pasa `multicell_enabled=True` a `simulate_scenario()` /
`simulate_ode()`.

Esta fase **no** modela aun transferencia lateral de masa
(cono/crater/funnel flow explicito). Modela solamente:

- estado local por canal;
- disponibilidad por canal segun nivel local;
- cota empirica `n_canales_activos -> rate` calibrada desde historico;
- balance de masa por canal reusando el kernel validado
  `update_stockpile_mass_balance()`.

## Fuente de datos

Archivo usado:

- `01_Data/Raw/Tonelajes_pila/pilas_rendimientos.xlsx`

Resolucion observada:

- ~96k filas
- 5 min
- 2025-08-01 -> 2026-06-30

## Canales usados por defecto

### SAG1

Canales utilizables en Fase 1:

- D -> `SAG:%_LI2016D`
- B -> `SAG:LI2016B`
- A -> `SAG:LI2016A`

Canal excluido:

- C -> `SAG:LI2016C`

Motivo:

- cobertura historica insuficiente (~50.6%)

Tabla calibrada por defecto (`q90`, monotonia acumulada, tope P90=1454):

- 0 activos -> 0 TPH
- 1 activo -> 1346.68 TPH
- 2 activos -> 1398.91 TPH
- 3 activos -> 1454.00 TPH

### SAG2

Canales utilizables en Fase 1:

- 1 -> `SAG2:260_LI_PILA01`
- 2 -> `SAG2:260_LI_PILA02`
- 4 -> `SAG2:260_LI_PILA04`
- 5 -> `SAG2:260_LI_PILA05`
- 6 -> `SAG2:260_LI_PILA06`

Canal excluido:

- 3 -> `SAG2:260_LI_PILA03`

Motivo:

- sensor congelado (~0.3723% durante todo el periodo)

Tabla calibrada por defecto (`q90`, monotonia acumulada, tope P90=2516):

- 0 activos -> 0 TPH
- 1 activo -> 2359.00 TPH
- 2 activos -> 2510.43 TPH
- 3 activos -> 2516.00 TPH
- 4 activos -> 2516.00 TPH
- 5 activos -> 2516.00 TPH

## Integracion implementada

Archivos principales:

- `05_Dashboard/engine/stockpile_multicell.py`
- `05_Dashboard/engine/ode_model.py`
- `05_Dashboard/engine/simulator.py`
- `05_Dashboard/engine/historical_backtesting.py`
- `05_Dashboard/engine/simulation_router.py`
- `05_Dashboard/engine/simulation_strategies.py`
- `05_Dashboard/engine/diagnostics/calibrate_multicell_rate_table.py`
- `05_Dashboard/engine/diagnostics/compare_multicell_backtest.py`
- `05_Dashboard/tests/test_stockpile_multicell.py`
- `05_Dashboard/tests/test_backtesting_multicell.py`

Comportamiento:

1. Se construye una configuracion por activo con:
   - canales utilizables
   - canales ignorados
   - threshold de actividad (`>5%`)
   - tabla de capacidad calibrada
2. Si el usuario entrega niveles iniciales por canal, se usan como
   **forma** espacial inicial y se reescalan para conservar el tonelaje
   total de pila.
3. El `qout` pedido por el motor actual se capea por la tabla
   `n_canales_activos -> rate`.
4. El `qin` total se reparte por pesos configurables
   (uniformes por default).
5. Se avanza el balance por canal con el mismo kernel de masa ya
   validado en el simulador agregado.
6. El resultado se re-agrega a:
   - `pile_sag1` / `pile_sag2`
   - `tph_sag1` / `tph_sag2`

Claves nuevas de salida cuando `multicell_enabled=True`:

- `pile_sag1_channels_pct`
- `pile_sag2_channels_pct`
- `active_channels_sag1`
- `active_channels_sag2`
- `multicell_rate_cap_sag1_tph`
- `multicell_rate_cap_sag2_tph`
- `multicell_channel_labels_sag1`
- `multicell_channel_labels_sag2`
- `multicell_ignored_channels_sag1`
- `multicell_ignored_channels_sag2`

## Integracion de orquestacion

El flujo `route_and_simulate()` ahora acepta overrides multi-celda y los
propaga hasta:

- el optimizador (`find_optimal_v3` -> `run_deterministic_grid` ->
  `adaptive_mc_eval`);
- la simulacion final del escenario;

de modo que la eleccion de candidatos y la simulacion final comparten la
misma fisica opcional.

Parámetros expuestos:

- `multicell_enabled`
- `initial_channel_levels_sag1`
- `initial_channel_levels_sag2`
- `multicell_rate_table_sag1`
- `multicell_rate_table_sag2`
- `multicell_feed_weights_sag1`
- `multicell_feed_weights_sag2`
- `multicell_active_threshold_pct`

Esto deja el modo multi-celda utilizable desde la capa de router sin
tener que entrar directo a `simulate_scenario()`.

## Integracion de backtesting

Se agrego `run_backtest_variant()` en
`05_Dashboard/engine/historical_backtesting.py` para evaluar
**candidatos parametrizados** sin contaminar el cache del baseline.

Capacidades nuevas:

- pasar `simulation_overrides` hasta `simulate_scenario_cached()`;
- recortar el periodo evaluado con `start_time` / `end_time`;
- reutilizar la misma metodologia de backtesting para baseline,
  calibration y hold-out;
- mantener intactos `run_backtest()` y `run_backtest_proxy()` como
  wrappers baseline cacheados.

Esto habilita comparaciones reproducibles tipo:

- baseline agregado
- vs candidato multicelda
- en calibration
- vs hold-out real

sin duplicar logica ni tocar el comportamiento productivo por default.

## Evidencia inicial baseline vs multicelda

Se ejecuto:

- `python 05_Dashboard/engine/diagnostics/compare_multicell_backtest.py`

Artefactos generados:

- `04_Reports/Technical/20260715_multicell_backtest_summary.csv`
- `04_Reports/Technical/20260715_multicell_backtest_delta_vs_baseline.csv`

Split temporal usado:

- calibration: eventos con inicio hasta `2026-04-30`
- hold-out: eventos con inicio desde `2026-05-01`

Resultado hold-out SAG1 (MAE pp):

- `t8_corta`: 36.63 -> 34.41 (`-2.22pp`)
- `inventario_critico`: 24.62 -> 22.86 (`-1.76pp`)
- `mantenimiento`: 19.18 -> 18.50 (`-0.68pp`)
- `alimentacion_restringida`: 16.02 -> 15.92 (`-0.10pp`)

Observaciones:

- La Fase 1 multicelda mejora el hold-out en los 4 regimenes con datos
  disponibles, pero la magnitud es **moderada**.
- `overflow` no tuvo eventos hold-out detectados tras el corte temporal,
  por lo que sigue actuando como control solo en calibration.
- La mejora mas visible aparece en `t8_corta` e
  `inventario_critico`, consistente con una fisica donde la
  disponibilidad espacial limita el vaciado efectivo.
- Aun con multicelda, los MAE hold-out siguen muy por encima de la
  tolerancia de `5pp`; esto confirma que Fase 1 ayuda, pero **no cierra**
  por si sola la brecha de fidelidad.

## Limitaciones actuales

- No hay transferencia lateral entre celdas.
- Los pesos de alimentacion por canal son uniformes por default.
- La geometria real de descarga queda representada solo via estado local
  inicial + canales activos, no por angulo de reposo ni flujo lateral.
- La calibracion usa cuantiles historicos por numero de canales activos;
  no distingue todavia turno, mineral, setpoint operativo ni regimen.
- El optimizador ya evalua candidatos con los mismos overrides
  multi-celda, pero la grilla y el MC todavia no fueron recalibrados
  especificamente para una fisica espacial; por ahora reutilizan el
  mismo espacio de busqueda de tasas/bolas que el modelo agregado.

## Proximo paso recomendado

El mayor ROI inmediato ya no es otra pasada de plumbing, sino una
**calibracion formal del candidato multicelda** sobre el split temporal
real:

- fijar baseline vs multicelda como modelos A/B;
- recalibrar tabla `n_canales_activos -> rate` por activo y regimen;
- validar de nuevo en hold-out antes de introducir transferencia lateral.

Despues de eso, la siguiente fase natural sigue siendo una
**Fase 2 con transferencia lateral**:

- agregar flujo entre celdas vecinas;
- calibrar constante de relajacion lateral;
- distinguir firma de cono vs crater a partir de dispersion temporal
  entre canales.
