# Sincronización recomendación ↔ escenario + diagnóstico físico post-T8

**Fecha:** 2026-07-09

---

## Causa raíz

`apply_ideal_params` (callback de "GENERAR RECOMENDACION",
`pages/simulador_operacional.py`) lee el escenario (T8, pila,
mantenciones...) como `State` y escribe los TPH recomendados en
`ctrl-rate-sag1`/`ctrl-rate-sag2` **una sola vez, al click**.
`update_simulation` (el gráfico) sí es reactivo (`Input`) a esos
mismos parámetros. Si el usuario cambia T8 (u otro parámetro crítico)
**después** de generar la recomendación, el gráfico se recalcula con el
escenario nuevo pero sigue usando los TPH recomendados para el
escenario viejo — sin ninguna señal de que ya no corresponden.

Investigación adicional: el bloque **"Actual vs Recomendado"
(`sim-compare-block`) ya era autosuficiente** — recalcula su propio
lado "recomendado" en vivo con las bandas del `sim` actual
(`sim_recommended`, construido con los mismos parámetros que `sim` en
esa misma ejecución del callback), sin depender de la recomendación
vieja del botón. **No se modificó ese bloque.**

---

## Callbacks afectados

| Callback | Cambio |
|---|---|
| `apply_ideal_params` (`pages/simulador_operacional.py:894`) | Al calcular r1/r2/b1/b2, construye el hash del escenario CON esos valores recién calculados y lo persiste junto al dict completo y un texto de contexto. Agrega 3 `State` nuevos (`ctrl-cv-mode`, `ctrl-cv315-manual`, `ctrl-cv316-manual`) solo para que el hash sea completo — no cambia la lógica de optimización existente. |
| `update_simulation` (`pages/simulador_operacional.py`) | Calcula el hash del escenario actual con los mismos campos; compara contra el hash guardado (`State`, no dispara recálculo por sí solo — Fase 6). Si no coinciden, muestra el banner "⚠ Recomendación desactualizada". Nuevo toggle "Modo de vista" (`ctrl-modo-vista`): en "Recomendación vigente", si el hash coincide, re-simula con los parámetros **congelados** de la última recomendación (cache hit en `simulate_scenario_cached` si nada cambió); si no coincide, cae a "Simulación actual" con aviso explícito. Agrega diagnóstico físico post-T8 y el KPI "Balance Neto de Pila". |

---

## Hash de escenario

`utils/scenario_hash.py` — `build_scenario_dict()` + `hash_scenario()`
(sha1 de `json.dumps(..., sort_keys=True)`, 12 caracteres). Un único
helper reusado por ambos callbacks: 22 campos físicos (T8, pilas,
rates, bolas, on/off de equipos, correas, horizonte, CV manual, T1/T3,
distribución, turno, mantenciones, tolerancia de riesgo). Deliberadamente
**sin** timestamp ni controles cosméticos (`sim-main-view`,
`ctrl-modo-vista`, `btn-reset-zoom`) — verificado con test explícito
(`test_cambiar_vista_o_controles_cosmeticos_no_forma_parte_del_hash`).

Nuevos `dcc.Store` (`app.py`): `store-recommendation-scenario-hash`,
`store-recommendation-scenario-params`, `store-recommendation-contexto`.

---

## Diagnóstico físico post-T8

`engine/balance_diagnostics.py` — `compute_post_t8_balance(sim,
duracion_t8_h)`: audita (no recalcula) Qin (`sim["cv315"]`/`["cv316"]`)
vs Qout (`sim["tph_sag1"]`/`["tph_sag2"]`) en el instante inmediatamente
posterior al fin de T8, clasifica **recupera** (`balance > +20 TPH`),
**plana** (`|balance| <= 20 TPH`), **drena** (`balance < -20 TPH`). El
umbral de 20 TPH absorbe ruido de discretización — no es un juicio
operacional, es una tolerancia numérica.

`explain_post_t8()` genera el texto mostrado bajo el gráfico ("Post T8:
SAG1 sigue drenando porque el consumo todavía supera a la alimentación
disponible. Balance estimado: -90 TPH..."). Nuevo KPI "Balance Neto de
Pila" (`components/cards.py::make_balance_neto_card`) muestra Qin/Qout/
Balance por SAG con semáforo — solo aparece con T8 activa.

**No se asume que la pila siempre debe subir post-T8** — el texto
generado es honesto sobre los 3 estados posibles, consistente con la
física real (Qin vs Qout), no con una expectativa fija.

---

## Tests agregados

- `tests/test_recommendation_sync.py` — 8 tests: los 4 casos del prompt
  (cambiar T8 invalida, generar con T8 ya seteado coincide, cambiar
  pila invalida, recalcular hace coincidir) + estabilidad del hash +
  que editar el rate manualmente también invalida + que las
  mantenciones forman parte del hash + que los controles cosméticos NO.
- `tests/test_post_t8_balance_logic.py` — 7 tests: Casos A (recupera),
  B (plana), C (drena), sin T8 → None, horizonte insuficiente → None
  (no se fabrica dato), y el texto de `explain_post_t8` refleja el
  signo correcto.
- Total: 15 tests nuevos, 164/164 pasan en la suite completa (el flake
  de timing de `test_optimizer_v4.py`, documentado en sesiones
  anteriores, no se disparó en esta corrida — sigue siendo un test de
  timing preexistente, no relacionado).

Adicionalmente, verificación manual invocando los callbacks reales
(sin navegador, por el proxy corporativo que bloquea Chromium) con
`app.callback_map` — confirmado end-to-end: (a) escenario fresco +
"Recomendación vigente" → sin banner, gráfico muestra el diagnóstico
post-T8 correcto; (b) T8 cambiado tras generar + "Recomendación
vigente" → banner visible, cae a "Simulación actual" con el aviso
correcto; (c) `apply_ideal_params` genera hash + contexto sin error.

---

## Vulnerabilidades revisadas (Fase 15)

| Vulnerabilidad | Estado |
|---|---|
| Recomendación vieja con gráfico nuevo | **Corregida** — banner + Modo de vista gatean la vigencia |
| Gráfico viejo con inputs nuevos | No aplicaba — `update_simulation` siempre fue reactivo |
| Cache reutilizado con hash incorrecto | `simulate_scenario_cached` cachea por parámetros exactos, no por hash propio — no hay colisión posible |
| `last_scenario.json` sobrescribiendo escenario actual | **Corrección a esta fila del reporte anterior** — la QA visual (ver sección siguiente) encontró que `precargar_ultimo_escenario` (`pages/simulador_operacional.py:595-622`) SÍ restaura `ctrl-pila-sag1/2`, `ctrl-duracion-t8`, `ctrl-rate-sag1/2`, `ctrl-bolas-sag1/2`, `ctrl-turno` al abrir la app — la afirmación original de que "nunca alimenta la simulación reactiva" era incorrecta. No es un problema en la práctica: T8 y los rates se restauran **juntos**, desde el mismo snapshot guardado, así que son mutuamente consistentes; y `store-recommendation-scenario-hash` (session, no persiste en disco) siempre empieza en `None` en una sesión nueva, por lo que el banner correctamente no aparece hasta la primera recomendación generada en esa sesión. |
| Rates recomendados escritos en inputs manuales sin trazabilidad | **Corregida** — `snapshot_caso` (Fase 2, cierre anterior) ahora lee pila/TPH desde `sim` en vez de los inputs crudos, consistente incluso en modo "Recomendación vigente" |
| "Actual vs Recomendado" mezclando fuentes | Auditado — **no mezcla**, ambos lados se calculan en la misma ejecución del callback con los mismos inputs actuales |

---

## Validación visual en navegador (2026-07-09, cierre)

**Cómo se hizo:** el proxy corporativo bloquea la descarga del binario
de Chromium que necesita Playwright — se resolvió lanzando Playwright
contra el **Edge ya instalado en el equipo** (`channel="msedge"`), que
no requiere descarga. Se automatizaron los 3 casos del prompt contra la
app corriendo en `localhost:8050`, con capturas reales.

### Casos probados

| Caso | Acción | Resultado |
|---|---|---|
| 1 — Recomendación vigente | T8=Sin T8 → GENERAR RECOMENDACIÓN | Banner vacío ✓. Toggle "Recomendación vigente" no muestra banner ✓ |
| 2 — Recomendación desactualizada | Recomendación ya generada → cambiar T8=4h sin regenerar | Banner "⚠ Recomendación desactualizada" visible ✓ |
| 3 — Recalcular | Con banner visible → GENERAR RECOMENDACIÓN de nuevo | Banner desaparece ✓, etiqueta "Ventana T8 corta (T8 4h)" coincide con el escenario actual ✓, rates recomendados cambian (SAG1 1309→1136 TPH) ✓ |
| Fase 2 — Balance Neto de Pila | T8=4h | KPI muestra Qin/Qout/Balance en TPH por SAG con estado (ej. "SAG1: Qin 928 · Qout 1169 · Balance -241 TPH Drenando") — **en TPH, no en %** ✓ |
| Fase 3 — Explicación post-T8 | T8=4h | Texto explica honestamente que ambos SAG siguen drenando (no asume recuperación automática) ✓ |
| Fase 4 — UX del banner | — | Visible, no tapa KPIs (vive en el sidebar sobre el botón), lenguaje operacional, indica la acción concreta ("Presiona GENERAR RECOMENDACION para recalcular") ✓ |

**Capturas guardadas** en `04_Reports/Technical/ux_screenshots/sync_recomendacion/`:
`01_recomendacion_vigente.png`, `02_recomendacion_desactualizada.png`,
`03_recomendacion_recalculada.png`, `04_balance_neto_pila.png`.

### Hallazgo real durante la validación: latencia, no un bug de lógica

Las primeras corridas automatizadas (con esperas de 2-6s entre acciones)
mostraban el banner **inconsistentemente** — a veces no aparecía cuando
debía, a veces no desaparecía al recalcular. Se investigó con logging
temporal (removido antes de cerrar) y se confirmó que **no es un bug de
la lógica de sincronización**: el callback `update_simulation` invoca
`route_and_simulate`/`find_optimal_v3`, que puede tardar **9 a 16
segundos** por ejecución (mismo número ya documentado en
`tests/test_optimizer_v4.py`, "SLA 3s NO aplica, ver Requisito 9 'Vista
avanzada'"). Con esperas de 20s entre acciones, los 3 casos pasan
consistentemente — ver tabla arriba. Un Jefe de Sala real, guiado por el
spinner de carga (`dcc.Loading` sobre `kpi-column`), naturalmente espera
a que termine antes de la siguiente acción, así que esto no es un
problema de UX práctico — pero **si se encadenan cambios de parámetros
muy rápido (más rápido que el tiempo de respuesta del callback), pueden
quedar respuestas en vuelo que se resuelven fuera de orden** (una
invocación más lenta y más vieja puede sobrescribir el resultado de una
más nueva y más rápida). Esto es una característica preexistente de
Dash con callbacks lentos y `threaded=True`, no algo introducido por
esta mejora — se deja documentado como riesgo conocido, no se intentó
resolver en este cierre (requeriría versionar las respuestas o debounce,
un cambio de arquitectura más grande, fuera de alcance de esta QA).

Adicionalmente, durante la investigación se encontró que Playwright con
`channel="msedge"` puede dejar procesos `msedge.exe` huérfanos si el
script no cierra limpio — **9 procesos quedaron corriendo** en un punto
de esta sesión y causaron falsos positivos/negativos por reutilizar
estado de sesión entre corridas "nuevas". Se resolvió matándolos
explícitamente (`taskkill /F /IM msedge.exe`) antes de cada corrida
limpia — nota para cualquier QA visual futura con este mismo enfoque.

---

## QA (Fase 17)

- `python -c "import app"` limpio.
- `/` (simulador) y `/riesgo` responden 200 (verificado también
  `/desempeno_gemelo`, 200).
- `grep -rn "find_optimal_v2"` — solo aparece en comentarios/docstrings
  de `optimizer_v2.py`/`optimizer_v3.py`, nunca invocado desde la UI.
- `grep -rn "ctrl-mc-n"` — sin resultados.
- Sin rutas absolutas hardcodeadas en `pages/`, `components/`,
  `engine/`, `utils/`, `app.py`.
- **165/165 tests** de la suite completa (164 del cierre anterior + 1
  test de regresión nuevo, `test_regresion_cv_manual_no_afecta_hash_en_modo_auto`,
  ver bug corregido abajo).

---

## Bug real encontrado y corregido durante esta QA

`apply_ideal_params` pasaba el valor **crudo** de
`ctrl-cv315-manual`/`ctrl-cv316-manual` al hash sin normalizar, mientras
`update_simulation` los fuerza a `0.0` cuando `cv_mode != "manual"`.
Como esos controles arrancan en `1000` en el layout (nunca en `0`), el
hash de la recomendación **nunca coincidía con el escenario actual en
modo automático** — el banner de "desactualizada" quedaba pegado
permanentemente, incluso justo después de generar. Encontrado con
logging temporal comparando ambos diccionarios campo por campo. Corregido
normalizando `cv315_manual`/`cv316_manual` a `0.0` en modo `"auto"`
dentro de `apply_ideal_params`, igual que ya hacía `update_simulation`
— y agregado el test de regresión correspondiente en
`tests/test_recommendation_sync.py`.

---

## Decisión de cierre (Fase 8)

- [x] El banner aparece cuando corresponde.
- [x] El banner desaparece al recalcular.
- [x] El toggle funciona visualmente.
- [x] El gráfico no mezcla escenario actual con recomendación antigua.
- [x] El KPI Balance Neto se entiende (Qin/Qout/Balance en TPH, estado con semáforo).
- [x] La explicación post-T8 es clara y no asume recuperación automática.
- [x] Hay screenshots guardados (4 archivos).
- [x] El reporte fue actualizado (esta sección + corrección de la fila de `last_scenario.json`).
- [x] Los tests siguen pasando (165/165).

**Cierre aceptado.** Único pendiente real: el riesgo de respuestas
fuera de orden ante cambios de parámetros muy rápidos, documentado
arriba, queda como mejora futura (no bloqueante — no reproducible bajo
uso normal con el spinner de carga como guía).
