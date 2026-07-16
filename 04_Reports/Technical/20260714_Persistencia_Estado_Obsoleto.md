# Persistencia de estado obsoleto — causa raíz y corrección definitiva

**Fecha:** 2026-07-14
**Base:** Gemelo Digital Molienda v1.3.0 (`05_Dashboard/`)

---

## 1. Causa raíz

**Store afectado (el que realmente causó el síntoma reportado):** no fue
un `dcc.Store` — fue un archivo en disco, `outputs/state/last_scenario.json`
(`utils/scenario_state.py`), que **sobrevive a reinicios del servidor y a
actualizaciones de versión de la app** (a diferencia de un `dcc.Store` de
sesión, que al menos se pierde en pestaña nueva/incógnito).

**Estructura obsoleta:** el archivo se escribía "pelado", sin ningún
campo de versión:

```json
{"pila1": 40, "pila2": 55, "duracion_t8": 4, "rate1_tph": 1236, ...}
```

**Callback consumidor:** `precargar_ultimo_escenario` (`pages/
simulador_operacional.py`), disparado con `Input("url","pathname")` en
**cada** carga de la página `/`. Lee `load_last_scenario()` y, si
encuentra un archivo, sobrescribe `ctrl-pila-sag1`, `ctrl-pila-sag2`,
`ctrl-duracion-t8`, `ctrl-rate-sag1/2`, `ctrl-bolas-sag1/2`, `ctrl-turno`
con los valores guardados — sin ninguna validación de que esos valores
sigan siendo compatibles con el código actual.

**Mecanismo del fallo:** el archivo real encontrado en esta sesión traía
`duracion_t8: 4`, que sigue siendo válido, así que en la mayoría de los
casos el bug no se manifestaba como excepción — se manifestaba como
**inconsistencia silenciosa**: el layout se reconstruye en cada carga con
la sábana de controles nueva (rediseño JdS del 2026-07-13, con los 6
bloques nuevos y `graph-main` como único gráfico dominante), pero el
`dcc.Graph(id="graph-main")` **no tenía ningún `figure` inicial
explícito** — su valor por defecto implícito de Dash es un `go.Figure()`
totalmente vacío. Plotly.js autorranguea una figura vacía a un rango
arbitrario (`x: -1..6`, `y: -1..4`, exactamente lo que se ve en la
captura del usuario) **antes** de que el callback `update_simulation`
responda. Si esa primera respuesta se demora, se pierde, o el usuario
mira la pantalla en el instante entre el primer paint y la respuesta del
callback, ve exactamente el síntoma reportado. Los 6 bloques nuevos
(`div-estado-general`, etc.) tenían el mismo problema: `html.Div(id=...)`
sin `children` inicial — invisibles hasta la primera respuesta del
callback.

**Por qué el servidor seguía respondiendo HTTP 200 pese al fallo:**
porque no había ningún fallo del lado del servidor — el callback
`update_simulation` **sí** calculaba y devolvía los datos completos (se
verificó directamente contra el backend: series de 289 puntos,
correctamente serializadas). El problema era puramente de **qué se
muestra antes de que llegue esa respuesta**, y de que un archivo de
estado sin versión se recargaba sin validar si aún encajaba con el layout
actual.

**Complicación adicional encontrada durante la verificación (no es un
bug de código, es un artefacto de la sesión de depuración):** quedaron
dos procesos `python run_app.py` corriendo en paralelo desde intentos de
reinicio anteriores en esta misma conversación — uno viejo (puerto 8050,
código sin corregir) y uno nuevo (puerto 8051, código corregido). Las
primeras verificaciones contra `localhost:8050` seguían mostrando el
rótulo `v1.1.2` porque golpeaban el proceso viejo. Se resolvió matando
ambos procesos por PID exacto y levantando uno solo limpio.

---

## 2. Archivos modificados

| Archivo | Propósito |
|---|---|
| `utils/version.py` (nuevo) | Fuente única de `APP_VERSION` (leída de `packaging/VERSION.txt`, nunca hardcodeada) y `APP_STATE_SCHEMA_VERSION` (independiente, sube solo cuando cambia la forma de los datos persistidos). Detección de modo de ejecución vía `sys.frozen`. |
| `utils/state_schema.py` (nuevo) | `make_envelope()`, `normalize_persisted_state()`, `get_data()`, `make_json_safe()`, y los defaults documentados de cada store. Único punto de verdad para validar/migrar/sanitizar estado persistido. |
| `utils/scenario_state.py` | `save_last_scenario`/`load_last_scenario` ahora escriben/leen el archivo envuelto en el sobre versionado; un archivo sin `schema_version` (como todos los escritos antes de este cambio) se trata como "nunca se guardó nada", no se precarga. |
| `pages/simulador_operacional.py` | Los 7 `dcc.Store` de sesión (`store-plant-state`, `store-mc-results`, `store-ultima-recomendacion-id`, `store-ultimo-snapshot-caso`, `store-recommendation-scenario-hash`, `store-recommendation-scenario-params`, `store-recommendation-contexto`) ahora se escriben con `make_envelope()` y se leen con `get_data()`/`normalize_persisted_state()` en vez de accederse "pelados" con corchetes frágiles. Layout inicial usa `build_initial_kpi_cards()` y `build_empty_simulation_figure()` en vez de divs/figuras vacías implícitas. |
| `components/cards.py` | `build_initial_estado_general/autonomia_card/recomendacion_corta/recuperacion_card/quick_win_card/scenario_compare` + `build_initial_kpi_cards()` — estado "idle" explícito y reconocible para los 6 bloques. |
| `components/graphs.py` | `build_empty_simulation_figure()` — figura inicial deliberada con anotación "Ejecute una simulación...", nunca un `go.Figure()` vacío con rango autogenerado. |
| `app.py` | Rótulo de versión ahora usa `utils.version.version_label()` (`f"v{APP_VERSION} · {EXECUTION_MODE}"`) en vez de `"v1.1.2 · Modo local (.exe portátil)"` hardcodeado en dos lugares. |
| `tests/test_state_schema.py` (nuevo) | 22 casos de `normalize_persisted_state`/`make_json_safe` (None, dict vacío, lista, string, sin versión, versión antigua, versión actual, campos faltantes, tipos incorrectos, NaN, Inf, numpy array, datetime, corrupción, copia profunda, etc.). |
| `tests/test_layout_smoke.py` (nuevo) | Verifica que el layout inicial (antes de cualquier callback) siempre contenga los IDs críticos y que los 6 bloques + `graph-main` traigan contenido/figura inicial no vacíos. |
| `tests/test_scenario_state_migration.py` (nuevo) | Prueba de persistencia antigua simulada: un `last_scenario.json` "pelado" (formato pre-versión) se descarta automáticamente en vez de precargar un `duracion_t8` incompatible con las 5 opciones fijas actuales. |
| `tests/test_performance_portable.py` | Sin cambios adicionales en esta ronda (ya corregido en la sesión anterior). |

---

## 3. Cambios implementados

- **Versionado:** `APP_STATE_SCHEMA_VERSION = 2` (independiente de `APP_VERSION`, que se lee de `packaging/VERSION.txt`). Subir este número invalida automáticamente todo estado persistido antiguo en el siguiente load.
- **Normalización centralizada:** `normalize_persisted_state()` es el único punto que decide si un estado sobrevive — nunca lanza excepción, siempre retorna una estructura válida, completa campos opcionales faltantes con el default, usa `deepcopy` para no mutar estructuras compartidas.
- **Invalidación automática:** ausencia de `schema_version`, versión distinta, `data` no-dict, o campos obligatorios faltantes → se descarta y se reemplaza por el estado inicial, con logging (`logger.warning`/`logger.info`) que distingue cada caso — sin ninguna acción manual del usuario.
- **Layout inicial explícito:** los 6 bloques y `graph-main` existen siempre desde el primer render con contenido "idle" reconocible (`build_initial_kpi_cards()`, `build_empty_simulation_figure()`), no dependen de que un callback ya haya corrido.
- **Callbacks protegidos:** los sitios que antes accedían `recommendation_params["pila1"]` a ciegas ahora normalizan primero con `required_keys` explícitos (`RECOMMENDATION_PARAMS_REQUIRED`) — un estado con un campo faltante se descarta completo en vez de lanzar `KeyError` a mitad de un render.
- **Serialización segura:** `make_json_safe()` (invocado automáticamente dentro de `make_envelope()`) convierte `np.integer`/`np.floating`/arrays NumPy/`NaN`/`Inf`/`datetime` a formas JSON-seguras antes de escribir cualquier store — evita que una escritura falle a mitad de camino y deje el store parcialmente actualizado.
- **Logging:** cada descarte/migración queda registrado con el `kind` del store afectado, la versión encontrada y la esperada.
- **Versión visible:** `v{APP_VERSION} · {EXECUTION_MODE}` generado dinámicamente; `APP_VERSION` se lee de `packaging/VERSION.txt` (ya era la fuente única de verdad del pipeline de release, no se duplicó); `EXECUTION_MODE` se detecta con `sys.frozen`.

---

## 4. Evidencia de pruebas

```text
comando: python -m pytest tests --ignore=tests/test_portable_smoke.py --ignore=tests/test_performance_portable.py -q
resultado: 231 passed in 67.53s
  (201 preexistentes sin regresión + 30 nuevas: 22 en test_state_schema.py,
   3 en test_layout_smoke.py, 5 en test_scenario_state_migration.py)
```

---

## 5. Validación funcional

- **Python (`python run_app.py`):** verificado — servidor arranca limpio, layout inicial sin ids duplicados, callback de 23 outputs registrado con la firma exacta esperada.
- **Estado obsoleto real (no simulado):** el archivo `outputs/state/last_scenario.json` presente en disco en esta sesión era, de hecho, un archivo escrito por el código *anterior* a esta corrección (sin `schema_version`). Al reiniciar el servidor con el código corregido, el log mostró en vivo:
  `WARNING: Estado persistido incompatible (kind=last_scenario). Version encontrada=None, version esperada=2. Se restablecera automaticamente.`
  — y la aplicación siguió funcionando normalmente, con `graph-main` mostrando la serie completa (289 puntos) y los 6 bloques con datos reales.
- **Reinicio del servidor:** verificado (múltiples reinicios durante esta sesión), sin dejar la interfaz atrapada en datos incompatibles.
- **Recarga forzada / pestaña reutilizada:** no verificado con un navegador real interactivo (ver riesgos residuales) — verificado por el mecanismo equivalente: request HTTP directo simulando el `sessionStorage` de una pestaña con estado antiguo, normalizado correctamente.
- **`.exe` portátil:** no se recompiló el `.exe` en esta sesión (no se pidió) — el código de detección `sys.frozen`/`sys._MEIPASS` y la resolución de rutas de `VERSION.txt`/`outputs/state/` ya seguían el mismo patrón usado en el resto del proyecto (`scenario_state.py`, `perf_logger.py`), no se modificó esa lógica de resolución de rutas, solo el contenido que se lee/escribe en esas rutas.

---

## 6. Riesgos residuales

- **No se verificó con un navegador real** (Chrome/Edge con DevTools) debido a que Playwright no pudo descargar Chromium en este entorno (inspección SSL corporativa bloqueó la descarga). Toda la verificación de "qué llega al cliente" se hizo por HTTP directo contra `/_dash-update-component`/`_dash-layout`, reconstruyendo el payload exacto que el navegador enviaría. Es un sustituto razonable pero no idéntico a una prueba real de renderizado en el DOM.
- **No se implementó la máquina de estados completa `idle/running/success/error/stale`** a nivel de cada callback individual (sección 13 del pedido) — se cubre el caso más importante (layout siempre válido, estado persistido siempre versionado) pero no hay un campo `status` explícito en cada store de dominio (`simulation_state`/`recommendation_state` separados como se sugería en la sección 6 del pedido). El diseño actual (un envelope genérico reusado para los 7 stores) es más simple y ya resuelve el bug real, pero es menos granular que la arquitectura de "estados por dominio" completa descrita en el pedido original.
- **No se agregó `simulation_id`/correlación de eventos** (sección 22) para trazar parámetros→simulación→recomendación→gráfico end-to-end en los logs — quedó fuera de alcance por tiempo.
- **`store-recommendation-contexto`** se envolvió por consistencia pero no tiene ningún lector en el código actual (se escribe, nunca se lee) — cambio de forma seguro pero no ejercitado por ningún test.
- **El `.exe` portátil no se recompiló** para confirmar el comportamiento exacto en modo `frozen` — la lógica de detección de rutas sigue el mismo patrón ya usado y probado en `scenario_state.py`, pero no hay una verificación end-to-end nueva del `.exe` en esta sesión.
