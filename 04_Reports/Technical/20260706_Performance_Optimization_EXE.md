# Optimización de Performance — Gemelo Digital de Molienda (.exe)

Fecha: 2026-07-06

Ejecutado sobre `05_Dashboard/`. Ver medición base en
`20260706_Performance_Dash_EXE.md`. Contexto de la decisión de reactividad
del Monte Carlo: `20260702_UX_UI_Operational_Control_Center.md` y
`skill_token_optimization_loop.md` (Regla 21).

## Decisión de alcance — historial de dos pasadas

**Primera pasada (mañana 2026-07-06):** el prompt original (Fase 3/4)
pedía gatear Monte Carlo/optimizador detrás de un botón "Aplicar cambios".
Eso contradecía la decisión documentada el 2026-07-02 (Monte Carlo
reactivo en cada slider). Se preguntó al usuario y confirmó **mantener**
la reactividad en vivo — no se implementó Apply-button; el esfuerzo se
redirigió a cache por escenario + límite de tiempo seguro (filas 3-5 de la
tabla original, más abajo).

**Segunda pasada (tarde 2026-07-06):** un nuevo prompt volvió a pedir el
gating (Fase 6/11 de ese prompt). Se confrontó la misma contradicción y
esta vez el usuario **confirmó explícitamente revertir** la decisión del
2026-07-02. Se implementó:

- **Fase 6 (gating por botón):** `run_monte_carlo`
  (`pages/simulador_operacional.py`) — los 27 parámetros de escenario
  volvieron de `Input` a `State`; único disparador:
  `Input("btn-monte-carlo", "n_clicks")`. Se verificó que
  `run_riesgo_optimizer` (`app.py`, los 4 botones de optimización de
  `/riesgo`) ya estaba correctamente gateado desde antes (no requirió cambio).
- **Fase 11 (modo rápido/avanzado):** nuevo selector `ctrl-app-mode`
  (`components/controls.py`, sidebar) con opciones Rápido/Avanzado,
  default Rápido. Callback `toggle_modo_rapido_avanzado`
  (`pages/simulador_operacional.py`) oculta el botón "Monte Carlo" y quita
  la opción "Robustez MC" de la vista principal cuando el modo es Rápido;
  ambos vuelven a aparecer en modo Avanzado. Si el usuario estaba viendo
  "Robustez MC" y cambia a Rápido, la vista vuelve a "Inventario"
  automáticamente.
- Reportes actualizados con la reversión:
  `20260702_UX_UI_Operational_Control_Center.md` (sección 3.1, nueva) y
  `skill_token_optimization_loop.md` (Regla 21, nota de reversión).

Las filas 3-5 de la tabla original de abajo describen el estado de la
**primera pasada** y ya no reflejan el comportamiento actual del código —
se dejan como registro histórico de por qué existía el cache de escenario
(sigue vigente y sigue siendo útil incluso con el gating por botón: un
escenario ya calculado sigue sirviéndose desde cache al re-ejecutar Monte
Carlo con el botón).

## Resumen por fase (primera pasada, histórico salvo notas [→ actualizado])

| Fase | Estado | Qué se hizo |
|---|---|---|
| 1. Instrumentación | ✅ | `05_Dashboard/utils/perf_logger.py` — decorator `@timed` + `log_duration()`, escribe en `outputs/logs/performance.log` (formato `timestamp \| callback \| duracion_ms \| scenario_hash \| cache_hit`). Se usó `outputs/logs/` en vez de `05_Dashboard/logs/` para seguir la convención ya existente de `app.log`. |
| 2. Reporte callbacks lentos | ✅ | `20260706_Performance_Dash_EXE.md` — medición headless (sin `.exe`/navegador disponible en este entorno). |
| 3. Separar liviano/pesado | ✅ [→ actualizado] | `simulate_scenario` ya es sub-ms (siempre liviano). Monte Carlo/optimizador ahora SÍ están separados del cambio de slider — ver Fase 6/11 de la segunda pasada, arriba. |
| 4. Debounce + botón Aplicar | ✅ [→ actualizado] | Implementado como gating por botón (`btn-monte-carlo` ya existía en la UI, se usó ese en vez de agregar uno nuevo "Aplicar cambios"). No se agregó debounce a los sliders — el botón ya evita el recálculo continuo, es redundante agregar ambos. |
| 5. Cache por escenario | ✅ | `05_Dashboard/engine/scenario_cache.py` — LRU en memoria por hash de parámetros. `simulate_scenario_cached` (envuelve `simulate_scenario` para llamadas deterministas puntuales, NO para las muestras internas de Monte Carlo) y `find_optimal_v3` quedan cacheados. Repetir un escenario ya visto: ~7,000 ms → ~0.1 ms. |
| 6. Precomputar escenarios frecuentes | ⚠️ Adaptado | Se descartó un `precomputed_scenarios.parquet` estático: un snapshot en disco puede quedar desincronizado del motor calibrado si este cambia después (violaría "no cambiar la lógica matemática validada" de forma silenciosa). En su lugar, `app.py` precalienta `simulation_cache` al arrancar para 20 combinaciones (T8 ∈ {0,2,4,8,12} × pila ∈ {20,40,60,80}) usando el mismo `simulate_scenario_cached` — nunca puede quedar stale porque es el mismo cómputo, no una copia. No se precalienta `find_optimal_v3` (20 optimizaciones completas en el arranque violarían el objetivo de apertura <15s). |
| 7. Gráficos Plotly | ✅ | `make_autonomia_historica` resampleada de 5 min a 30 min (~8,640 → ~1,440 puntos, -6x payload de arranque). `make_pile_chart`/`make_tph_chart` (las reactivas del simulador) ya usaban solo ~288 puntos (paso ODE de 5 min sobre 24h) — no tenían problema de volumen; se les agregó `uirevision` para no perder el zoom/pan del usuario en cada redraw. |
| 8. Límites seguros Monte Carlo | ✅ | `engine/optimizer_v2.py`: nuevo `MC_MAX_SECONDS = 8.0` — techo de tiempo real, aditivo. **No se tocó** `MC_MAX_N/MC_BATCH/MC_CONV_TOL/MC_CONV_CONSEC/MC_MIN_N` (tuning matemático validado). Si se corta por tiempo, el resultado queda marcado `mc_timed_out=True` y `mc_warning="No convergente, usar con cautela"`. |
| 9. Feedback visual en cálculos pesados | ✅ Ya existía | `dcc.Loading` ya envuelve `graph-mc`, `div-mc-summary`, `graph-hourly-risk`, `graph-pareto`, etc. en `pages/simulador_operacional.py`. No se agregó disable-de-botón: Dash ejecuta callbacks de forma serializada por sesión y el spinner ya comunica el estado "corriendo". |
| 10. `--onedir` | ✅ | `build_exe.bat` y `Gemelo_Digital_Molienda.spec` cambiados de `--onefile` a `--onedir` (+ `COLLECT()` en el spec). Evita la descompresión a carpeta temporal en cada apertura. **Importante:** `runtime_data/`, `assets/`, `config/` ahora se copian dentro de `dist/Gemelo_Digital_Molienda/` (junto al `.exe` y la carpeta `_internal/`), no junto a un único archivo — no requiere cambios de código porque las rutas ya se resuelven vía `sys.executable`. |
| 11. Excluir librerías no usadas | ✅ Ya estaba hecho | `torch, sklearn, numba, tensorflow, xgboost, lightgbm, catboost, statsmodels, shap, ruptures, matplotlib, jupyter, notebook, ipykernel, IPython, pytest, tkinter` ya excluidos (144 MB final, documentado en `20260702_Construccion_EXE.md`). Sin cambios. |
| 12-13. Carga única de datos / runtime cache liviano | ✅ Verificado, sin cambios | `DF_HIST` se carga una sola vez a nivel de módulo en `app.py` (no dentro de callbacks). `runtime_data/Cache/advanced_t8_historical_5min.parquet` (13 MB, 93,612 filas × 17 cols) ya es el subconjunto liviano — no se encontró ninguna lectura de Excel/parquet/raw dentro de un callback disparado por slider (`load_current_state()` solo se llama en callbacks gatillados por botón, no por `Input` continuo). Crear un `runtime_cache.parquet` adicional habría sido un duplicado sin beneficio real. |
| 14. Separar callbacks tarjetas/gráfico/MC | ✅ Ya estaba hecho | `app.py`/`simulador_operacional.py` ya tienen callbacks independientes por bloque de salida (tarjetas, gráfico principal, gráficos secundarios, Monte Carlo). |
| 15. Modo rápido / avanzado | ✅ [→ actualizado] | Implementado en la segunda pasada — ver Fase 11 arriba (`ctrl-app-mode`, oculta botón MC + opción "Robustez MC" en modo Rápido). |
| 16. Validación en `.exe` | ⚠️ Pendiente — requiere entorno con GUI | Este entorno no tiene navegador/GUI para cronometrar clicks reales. Ver sección siguiente. |
| 17. Reporte final | ✅ | Este documento. |

## Cambios de código (archivos tocados)

- `05_Dashboard/utils/perf_logger.py` — nuevo
- `05_Dashboard/engine/scenario_cache.py` — nuevo
- `05_Dashboard/engine/simulator.py` — agrega `simulate_scenario_cached`
- `05_Dashboard/engine/optimizer_v3.py` — cachea `find_optimal_v3`
- `05_Dashboard/engine/optimizer_v2.py` — `MC_MAX_SECONDS`, `@timed` en `adaptive_mc_eval`
- `05_Dashboard/app.py` — usa `simulate_scenario_cached` en los 3 puntos de simulación determinista de `/riesgo`; instrumenta arranque (carga de datos, figuras estáticas, precalentado de cache)
- `05_Dashboard/pages/simulador_operacional.py` — usa `simulate_scenario_cached`
- `05_Dashboard/components/graphs.py` — resample histórico 30 min, `uirevision`, usa `simulate_scenario_cached` en heatmap
- `05_Dashboard/build_exe.bat`, `Gemelo_Digital_Molienda.spec` — `--onedir`

No se modificó ninguna fórmula de `ode_model.py`, `rules_engine.py`,
`risk_engine.py`, ni el tuning de `optimizer_v2.py`/`optimizer_v3.py`
(grids, pesos, umbrales, `MC_MAX_N`, etc.).

## Fase 16 — Validación real (2026-07-06)

Se construyó el `.exe` real con `--onedir` (`python -m PyInstaller ...
run_app.py`, build exitoso, `Build complete!`) y se lanzó el proceso dos
veces, cronometrando con `Stopwatch` desde el arranque del proceso hasta la
primera respuesta HTTP 200 del servidor (equivalente a "la app ya está
lista para usarse", sin depender de que un navegador esté disponible en
este entorno):

| Métrica | Valor medido | Objetivo | Resultado |
|---|---:|---:|---|
| Apertura en frío (1er lanzamiento tras el build) | **8.54 s** | < 15 s | ✅ |
| Apertura en caliente (2do lanzamiento) | **2.39 s** | < 15 s | ✅ con margen amplio |
| Tamaño en disco (`dist/Gemelo_Digital_Molienda/`) | 366 MB | — | ⚠️ ver nota |

**Nota de tamaño:** `--onedir` deja los archivos sin comprimir en disco, por
lo que el total (366 MB) es mayor que el `.exe` único de `--onefile` (144
MB reportado en `20260702_Construccion_EXE.md`). Es el trade-off esperado:
más espacio en disco a cambio de no descomprimir nada en cada apertura. Si
366 MB es un problema para distribución (USB, email corporativo), la
alternativa es comprimir la carpeta `dist/Gemelo_Digital_Molienda/` en un
`.zip`/instalador una sola vez — el usuario final igual descomprime una
vez, no en cada apertura.

**Lo que falta validar con navegador real** (no disponible en este
entorno): tiempo de cambio de parámro percibido en pantalla, clicks en
"Ejecutar optimización"/"Simular Monte Carlo", cambio de pestaña. Como
proxy, se validó el costo de cómputo puro de esas mismas funciones en
`20260706_Performance_Dash_EXE.md` (llamando al motor real, no simulado):
`simulate_scenario` ~1 ms, `find_optimal_v3` ~7 s en frío / ~0.1 ms
repitiendo escenario. La diferencia entre "cómputo puro" y "percibido en
pantalla" es la serialización Plotly + red localhost, típicamente
decenas de ms — no debería mover estos números de forma significativa.
Si alguien con acceso a un navegador quiere confirmar el número exacto
percibido, los pasos son: abrir `dist\Gemelo_Digital_Molienda\Gemelo_Digital_Molienda.exe`
y cronometrar cambio de pila SAG1, cambio de T8, click "Ejecutar
optimización", click "Simular Monte Carlo", cambio de pestaña.

## Recomendaciones futuras

- Si en producción `find_optimal_v3` sigue por encima de 8s en máquinas de
  usuario final más lentas, el candidato de siguiente palanca es reducir
  `TOP_CANDS_FOR_MC` (actualmente 20) — pero es tuning validado, requiere
  aprobación explícita antes de tocarlo.
- Si el cache de escenarios crece demasiado en sesiones muy largas,
  `ScenarioCache.maxsize` ya está acotado (512/128/128) — no requiere acción,
  solo monitorear vía `outputs/logs/performance.log` (columna `cache_hit`).
