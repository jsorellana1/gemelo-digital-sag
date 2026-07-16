# Lógica operacional centralizada: pilas, ventanas y molinos SAG–bolas

**Fecha:** 2026-07-14
**Base:** Gemelo Digital Molienda v1.3.0 (`05_Dashboard/`)
**Plan aprobado:** ver historial de sesión (plan de integración aditiva
sobre `engine/ode_model.py::simulate_ode`, revisado antes de codificar)

---

## 1. Reglas implementadas

Las 18 reglas del pedido quedaron implementadas como funciones puras en
**`engine/circuit_state.py`** (kernel de dominio nuevo, sin dependencias de
Dash/UI), e integradas dentro de **`engine/ode_model.py::simulate_ode`**
(el único punto de entrada real del motor físico, confirmado por
exploración de código: solo `engine/simulator.py::simulate_scenario`/
`simulate_scenario_cached` lo invocan).

| Regla | Función | Dónde se usa |
|---|---|---|
| 1-3: ventana, factor de alimentación, recuperación gradual | `calculate_effective_feed`, `resolve_window_feed_factor`, `OperationalWindow` | Reemplaza el `factors_correa` hardcodeado/duplicado (`compute_qin` + inline en el loop) |
| 4: dependencia SAG→bolas | `resolve_equipment_dependencies` | Corrige un bug real de visualización (ver sección 7) |
| 5: consumo cero con SAG apagado | ya existía (`qout=0 if not sag_activo`), preservado |
| 6-7: inventario mínimo/máximo, overflow/rechazo explícitos | `update_stockpile_mass_balance` | Reemplaza el clip silencioso de `step_pile()` |
| 8-9: rate efectivo, capacidad por Nº de bolas | `calculate_effective_sag_rate` | Función completa disponible y testeada; la integración en `simulate_ode` usa la porción de rampa (ver sección 5, decisión de alcance) |
| 10: rampas de arranque/detención | `apply_rate_ramp` | Aplicado a `qout1`/`qout2` cada paso, default=0 (instantáneo) |
| 11: estados operacionales y tendencia de pila | `determine_operational_state`, `determine_pile_trend` | Nuevas claves `operational_state_sagX`, `pile_trend_sagX` |
| 12-13: redistribución, ventana por circuito | `redistribute_feed`, `OperationalWindow.feed_factor_sac1/sac2` | `redistribution_enabled=False` por default |
| 14: ventanas múltiples/superpuestas/que cruzan medianoche | `OperationalWindow` + `resolve_window_feed_factor` (`min` de factores activos) | Ver tests 17-18 |
| 15: orden de prioridad | Orden de cómputo dentro del loop de `simulate_ode` (dependencias → ventana → inventario → capacidad → rampa → balance) |
| 16: recomendaciones coherentes | `generate_operational_recommendation` | Enriquece `explicacion` en `simulate_scenario` (aditivo, no reemplaza `rules_engine.py`) |
| 17: autonomía con consumo neto | `calculate_stockpile_autonomy` | Nuevas claves `autonomy_hours_sagX`, `autonomy_message_sagX` |
| 18: conservación de masa | `validate_mass_conservation` | Nuevas claves `mass_balance_error_sagX` |

---

## 2. Ecuaciones

**Balance de masa (única fuente de verdad, sin cambios respecto al
motor original — Regla fundamental):**

```
M[t+1] = clip(M[t] + (F_in_accepted[t] - F_out_effective[t]) * Δt, 0, M_max)
```

**Regla 6 corregida (ver sección 7 — bug real encontrado y corregido):**

```
available_rate = M[t] / Δt + F_in_requested[t]
F_out_effective[t] = min(F_out_requested[t], available_rate)
```

**Regla 7 (overflow/rechazo explícitos):**

```
available_storage = M_max - M[t]
F_in_accepted[t]  = min(F_in_requested[t], available_storage/Δt + F_out_effective[t])
rejected_feed[t]  = F_in_requested[t] - F_in_accepted[t]
overflow[t]       = max(0, M[t] + (F_in_accepted[t]-F_out_effective[t])*Δt - M_max)
```

**Regla 17 (autonomía neta):**

```
net_drain_rate = F_out_effective - F_in_effective   (solo si F_out > F_in)
autonomia_h    = max(0, (M - M_min) / net_drain_rate)
```

**Regla 18 (conservación de masa, verificada en cada escenario — ver sección 6):**

```
error = M_inicial + Σ F_in_accepted·Δt - Σ F_out_effective·Δt - M_final - Σ overflow
```

---

## 3. Archivos modificados

| Archivo | Propósito |
|---|---|
| `engine/circuit_state.py` (nuevo) | Kernel de dominio: `OperationalWindow`, `CircuitState`, y las 13 funciones puras de la sección 1. |
| `engine/ode_model.py` | `simulate_ode` gana 6 parámetros opcionales (`windows`, `sag_ramp_up/down_time_min`, `feed_recovery_time_min`, `one_ball_capacity_factor`, `redistribution_enabled`), todos con default = comportamiento previo. El loop interno ahora delega en el kernel para: factor de ventana, dependencia SAG→bolas, rampa, y balance de masa con overflow/rechazo. `compute_qin` usa la constante compartida `VENTANA_FACTOR_ESTADO` (antes duplicada). 16 claves nuevas en el dict de retorno (aditivas, ninguna existente se quitó/renombró). |
| `engine/simulator.py` | `simulate_scenario` propaga los parámetros nuevos y enriquece `explicacion` con el mensaje de dependencia SAG→bolas cuando existe. |
| `components/cards.py` | `make_autonomia_resumen_card` acepta `dependency_message` opcional — se muestra en los bloques 6.2/6.3 de la vista principal cuando un SAG está OFF con bolas solicitadas ON. |
| `pages/simulador_operacional.py` | Pasa `dependency_message_sagX` a las cards; agrega nota de overflow/rechazo a la explicación del gráfico principal cuando corresponde. |
| `tests/test_circuit_state.py` (nuevo) | 42 tests — los 30 casos obligatorios del pedido + 12 adicionales, todos contra las funciones puras del kernel (aislados, sin correr el ODE completo). |
| `tests/test_ode_model_integration.py` (nuevo) | 19 tests de integración: compatibilidad por defecto (`windows=None`+rampas=0 ≡ no pasar esos parámetros), invariantes preexistentes preservados, conservación de masa en el motor completo (5 duraciones de T8), y 5 de los 12 escenarios mínimos del pedido verificados end-to-end. |
| `scripts/validate_circuit_state.py` (nuevo) | Genera los 10 escenarios gráficos pedidos + `resumen.json` con métricas de conservación de masa por escenario. |

---

## 4. Bug real encontrado y corregido durante la validación (Regla 6)

La validación gráfica (sección 6) expuso un error de conservación de masa
de **hasta -3.140 toneladas** en escenarios con ventana T8 larga (8-12h) o
agotamiento de pila. Causa raíz: la función original de balance de masa
(el `step_pile()` preexistente, y mi primera versión de
`update_stockpile_mass_balance`) **recortaba el inventario a 0 DESPUÉS de
calcular el balance**, pero nunca limitaba `F_out` — es decir, el modelo
"consumía" mineral que la pila ya no tenía, y luego simplemente pisaba el
resultado a 0 sin corregir la contabilidad. Esto es exactamente lo que la
Regla 6 del pedido advierte explícitamente: *"no basta con recortar el
resultado a cero"*.

**Corrección aplicada** en `update_stockpile_mass_balance` (ver ecuación
en sección 2): ahora `F_out_effective` se limita a
`M/Δt + F_in_requested` **antes** de calcular el nuevo inventario — el
SAG nunca puede consumir más mineral del que existía más lo que entró en
el mismo paso. Esto cambió la firma de la función (retorna también
`f_out_effective_tph`) y se propagó a `simulate_ode`: `tph_sag1`/`tph_sag2`
(lo que se grafica y se reporta) ahora reflejan el consumo REAL, no el
solicitado, cuando la pila está cerca de agotarse.

Resultado tras la corrección: el error de conservación de masa bajó de
cientos/miles de toneladas a **~1e-10 toneladas** (ruido de punto flotante)
en los 10 escenarios de validación — ver sección 6.

---

## 5. Decisiones de alcance (declaradas, no implícitas)

- **La integración en `simulate_ode` NO reemplaza el sistema de rate
  calibrado** (`effective_rate` + dose-response `_t8_factor_sagX` +
  `_pile_feedback_factor`, calibrados con 70 eventos históricos reales).
  `calculate_effective_sag_rate` (Reglas 8-9 completas) existe y está
  testeada como función standalone, pero `simulate_ode` solo usa de ella
  la porción de **rampa** (`apply_rate_ramp`) y el **límite por
  inventario** (ahora dentro de `update_stockpile_mass_balance`, Regla 6).
  El factor de capacidad por Nº de bolas (Regla 9) sigue viniendo del
  mecanismo preexistente calibrado (auto-downgrade de `_nb1_eff`/`_nb2_eff`
  por umbral de rate, `BOLA_THRESHOLD_TPH`), no de
  `calculate_effective_sag_rate`. Motivo: reemplazar el sistema calibrado
  completo arriesgaba invalidar el ajuste histórico sin una recalibración
  que está fuera del alcance de esta tarea.
- **`one_ball_capacity_factor=0.55`**: sin dato calibrado confirmado en el
  proyecto — supuesto explícito, parametrizable (no hardcodeado dentro de
  una función), usado únicamente por `calculate_effective_sag_rate`
  (disponible para quien la use directamente; no está en la ruta activa
  de `simulate_ode` por la razón anterior).
- **`feed_recovery_time_min=0` por default** = recuperación instantánea,
  igual al motor previo. Rampas lineal/escalonada disponibles y testeadas,
  pero no son el comportamiento por defecto de ningún escenario existente.
- **`redistribution_enabled=False` por default**: la redistribución entre
  SAC1/SAC2 (Reglas 12-13) está implementada y testeada
  (`redistribute_feed`), pero apagada por default — activarla cambiaría el
  balance de masa por circuito de forma visible y debe ser una decisión
  explícita del llamador, no un cambio de comportamiento silencioso.
- **No se tocó `compute_autonomia`** (fórmula simple, `(pile_pct-crit)/
  drain_pct_h`, usada directo por ~15 archivos fuera de `ode_model.py`).
  `calculate_stockpile_autonomy` (consumo neto, Regla 17) es una función
  **nueva y adicional**, expuesta como `autonomy_hours_sagX`/
  `autonomy_message_sagX`, sin reemplazar la fórmula original en ningún
  punto de consumo existente.

---

## 6. Validación gráfica — 10 escenarios

Generados con `python scripts/validate_circuit_state.py`
(`outputs/validation/circuit_state/*.html` + `resumen.json`):

| Escenario | Pila SAG1 inicio→fin | Tendencia | Estado | Error masa SAG1 (ton) |
|---|---|---|---|---|
| 01 Ventana 2h | 54.5%→65.5% | FILLING | RESTRICTED | 6.4e-11 |
| 02 Ventana 4h | 54.5%→55.7% | FILLING | RESTRICTED | 6.6e-11 |
| 03 Ventana 8h | 54.5%→45.6% | FILLING | RESTRICTED | 4.9e-11 |
| 04 Ventana 12h | 54.5%→40.9% | FILLING | RESTRICTED | 3.5e-11 |
| 05 Sin ventana | 55.1%→98.7% | FILLING | RESTRICTED | 8.1e-11 |
| 06 SAG1 OFF | 55.7%→100.0% | FILLING | OFF | 1.8e-12 |
| 07 SAG2 OFF | 54.9%→24.8% | STABLE | RESTRICTED | 1.4e-10 |
| 08 1 molino de bolas fuera de servicio | 55.1%→98.7% | FILLING | RESTRICTED | 8.1e-11 |
| 09 Agotamiento de pila (inicio 19.4%) | 19.4%→45.3% | FILLING | RESTRICTED | -3.0e-11 |
| 10 Recuperación post-ventana | 29.6%→52.4% | FILLING | RESTRICTED | 4.8e-11 |

Notas de lectura:
- **Escenario 06** (SAG1 OFF): `dependency_message_sag1` = *"Molinos 411 y
  412 solicitados ON, pero quedan inactivos porque el SAG asociado está
  OFF."* — confirma la Regla 4 funcionando end-to-end. `rejected_feed_sag1`
  acumula ~310.535 t porque, con SAG1 apagado y `distribucion_t1=
  "balanceado"`, la pila llega a 100% y deja de aceptar el resto de la
  alimentación asignada a CV315 (comportamiento esperado: Regla 7 en
  acción, no un error).
- **Escenario 09** (agotamiento): la pila parte en 19.4% (ya bajo el
  crítico de SAG1, 15%) — el estado queda `RESTRICTED` porque la
  alimentación (correa activa) supera al consumo limitado, por lo que la
  pila se recupera (`FILLING`) en vez de agotarse del todo; confirma que
  el "agotamiento" depende del balance real, no de una regla artificial.

Todos los errores de conservación de masa quedaron en el orden de
`1e-10` a `1e-12` toneladas — ruido de punto flotante, no error real.

---

## 7. Fix adicional: dependencia SAG→bolas en la visualización (Regla 4)

Al integrar `resolve_equipment_dependencies`, se encontró que el código
original tenía la condición **invertida** para `b411_eff`/`b511_eff`:

```python
# ANTES (bug): con SAG1 OFF, "not sag1_activo" es True -> el OR se
# satisface de inmediato -> b411_eff = _b411 (se mostraba "ON" aunque
# el SAG estuviera apagado).
b411_eff = _b411 if (_b411 and (not sag1_activo or regime_fn is None or _nb1_eff >= 1)) else 0
```

Este bug era puramente de **visualización** (`bola411_arr`/etc., usadas
solo por el gráfico de timeline de molinos de bolas) — no afectaba
`tph_sag1`/`tph_sag2` ni el balance de masa, que ya usaban `sag1_activo`
directamente. Corregido como parte natural de la Regla 4 (`ball_effective
= ball_requested and sag_effective_on`), confirmado con el test de
integración `test_escenario_5_sag_apagado_durante_ventana_bolas_quedan_off`.

---

## 8. Evidencia de pruebas

```text
comando: python -m pytest tests --ignore=tests/test_portable_smoke.py --ignore=tests/test_performance_portable.py -q
resultado: 292 passed in 84.47s
  (231 preexistentes sin regresión
   + 42 en tests/test_circuit_state.py — los 30 casos obligatorios + 12 adicionales
   + 19 en tests/test_ode_model_integration.py)
```

---

## 9. Validación funcional

- **Unitaria (kernel aislado):** 42/42 tests de `circuit_state.py` pasan.
- **Integración (motor completo):** 19/19 tests confirman compatibilidad
  por defecto exacta (`windows=None`+rampas=0 idéntico a no pasar esos
  parámetros), invariantes preexistentes preservados (T8 monotónico, SAG
  off no consume, T1=CV315+CV316+T3, capacidad de chancado), y
  conservación de masa <10 toneladas de tolerancia en 5 duraciones de T8
  distintas (0/2/4/8/12h) corridas contra el motor real.
- **Gráfica (10 escenarios):** ver sección 6 — todos con error de
  conservación de masa ~1e-10 ton.
- **Regresión completa:** 292/292 tests del proyecto (incluye optimizer
  V2-V5, backtesting histórico, router, T1/T3 balance) — cero fallos.
- **App en vivo:** pendiente de verificación manual con 2 escenarios
  reales (ver riesgos residuales).

---

## 10. Supuestos explícitos

- `one_ball_capacity_factor = 0.55` — sin dato calibrado confirmado en el
  proyecto (documentado en `engine/ode_model.py::ONE_BALL_CAPACITY_FACTOR`
  y en `calculate_effective_sag_rate`). Parametrizable, no usado en la
  ruta activa de `simulate_ode` por defecto (ver sección 5).
- Umbral de tendencia de pila (`FILLING`/`DRAINING`/`STABLE`):
  `|F_in - F_out| > 1.0 TPH` — valor de tolerancia razonable para evitar
  "parpadeo" de estado con ruido numérico, sin calibración específica.
- `M_min_operational` para `calculate_stockpile_autonomy` se tomó igual a
  `CRITICAL_PCT[asset]` (mismo umbral crítico ya calibrado en
  `ode_model.py`), no un valor nuevo independiente.
- Capacidad de recepción del circuito receptor en `redistribute_feed`
  (usada solo si `redistribution_enabled=True`, no activo por default) se
  fijó en `P90[asset] * 1.5` como supuesto razonable, sin dato de
  capacidad de correa/tolva confirmado — a revisar si se activa la
  redistribución en producción.

---

## 11. Riesgos residuales

- **No se verificó con un navegador real** el impacto visual de los
  cambios en `components/cards.py`/`pages/simulador_operacional.py`
  (mensaje de dependencia, nota de overflow) — verificado solo por HTTP
  directo/tests, no por captura de pantalla en la app corriendo.
- **`redistribution_enabled=True` no se probó en la app real**, solo en
  los tests unitarios/integración — antes de activarlo en producción,
  correr el mismo tipo de validación gráfica de la sección 6 con
  redistribución encendida.
- **Rampas de arranque/detención (`sag_ramp_up/down_time_min`)** no tienen
  ningún valor calibrado propuesto — quedan disponibles pero con default 0
  (sin rampa); si se decide usarlas en un escenario real, definir el
  tiempo de rampa con el equipo de terreno antes de exponerlas en la UI.
- **Fase de validación histórica** (comparar contra eventos T8 reales,
  igual que la brecha ya documentada en el rediseño JdS del 2026-07-13 y
  en la sábana maestra de datos) sigue sin abordarse — este cambio mejora
  la corrección física del motor pero no reemplaza esa validación
  pendiente contra datos reales.

---

## Fase 2 (2026-07-14) — profundización sobre el kernel de la Fase 1

**No se reescribió el motor.** Todo lo de esta fase se construyó **sobre**
`engine/circuit_state.py`/`engine/ode_model.py` tal como quedaron en la
Fase 1 — se agregaron funciones y parámetros opcionales nuevos, con el
mismo contrato: default = comportamiento idéntico al anterior, ninguna
clave del dict de retorno se quitó ni renombró.

## F2.1 Qué se agregó al kernel (`engine/circuit_state.py`)

| Función/dato nuevo | Resuelve |
|---|---|
| `analyze_window_episode(...)` → `WindowEpisodeAnalysis` | Separa la tendencia **durante** la ventana de la tendencia **después**, reporta el instante exacto del mínimo, si llegó a STARVED, y el tiempo de recuperación real (no solo "inicio de recuperación") — Fase 1 solo exponía la tendencia final, colapsando ambos períodos en una sola etiqueta. |
| `determine_restriction_reason(...)` | Motivo **específico** de restricción con precedencia documentada (`SAG_OFF > BALL_MILLS_OFF > STARVED > capacidad aguas abajo > inventario bajo > ventana > rampas > pila llena > alimentación rechazada > normal`) — antes solo existía `operational_state=RESTRICTED` sin decir *por qué*. |
| `compare_autonomy_sources(...)` | Compara la autonomía legada (`compute_autonomia`, fórmula simple) contra la nueva de consumo neto (`calculate_stockpile_autonomy`, Regla 17) y marca si divergen más de 1h — para detectar cuándo ambas fuentes cuentan historias distintas, sin eliminar ninguna. |
| `evaluate_simulation_quality(...)` | Chequeo automático de consistencia (error de masa dentro de tolerancia, sin valores negativos/NaN) sobre cada corrida — nuevas claves `simulation_consistent_sagX`/`simulation_warnings_sagX`. |
| Modo de recuperación `"exponential"` en `calculate_effective_feed` | Alternativa a la rampa lineal ya existente, con constante de tiempo (`feed_recovery_tau_min`) configurable por separado del tiempo de rampa. |

## F2.2 Gap real encontrado y corregido: `feed_recovery_time_min` nunca se aplicaba

La Fase 1 agregó el parámetro `feed_recovery_time_min` a `simulate_ode` pero
**nunca lo consumía dentro del loop** — el factor de ventana volvía a 1.0
instantáneamente al terminar la ventana, sin importar el valor del
parámetro. Se agregó `_feed_con_recuperacion()` en `ode_model.py`, que
localiza la ventana más reciente ya terminada para el activo y llama a
`calculate_effective_feed` con la rampa (lineal o exponencial) realmente
activa. Confirmado con la tabla de sensibilidad (F2.4): con este fix, mover
`feed_recovery_time_min` de 0→120 min ahora sí desplaza el inventario final
(43.2%→45.6% en el escenario de referencia), donde antes no tenía ningún
efecto medible.

## F2.3 Reescritura de `scripts/validate_circuit_state.py`

Se diagnosticaron y corrigieron 3 problemas de reporte (no del motor: los
números ya eran correctos en Fase 1, el script solo los mostraba mal):

1. **Tendencia colapsada a un solo estado final** → ahora reporta
   `trend_during_window`/`trend_after_window`/`trend_final` por separado
   vía `window_episode_sagX`.
2. **Resumen no simétrico entre SAC1/SAC2** → `_circuito_resumen()` genera
   el mismo bloque completo (inventario, autonomía, rate, motivo de
   restricción, rechazo/overflow, consistencia) para **cada** circuito en
   **cada** escenario, sin mezclar el nombre de un circuito con datos del
   otro.
3. **Escenario "09_agotamiento_pila" mal nombrado** → en realidad mostraba
   recuperación desde nivel bajo (balance neto positivo); se renombró a
   `14_recuperacion_desde_nivel_bajo` y se agregó
   `13_agotamiento_efectivo` (pila baja + correa inactiva + rate alto), que
   sí fuerza `reached_starved=True` de forma medible (SAC1 llega a STARVED
   en t≈1.3h, recupera en t≈2.9h en el escenario de referencia).

El script ahora corre 19 escenarios (los 10 originales + agotamiento real +
1/0 bolas por SAG + pila llena con rechazo + comparación redistribución
ON/OFF + recuperación lineal/exponencial), guarda HTML + `resumen.json` en
`outputs/validation/circuit_state/` (carpeta regenerable, agregada a
`.gitignore` — ver limpieza en F2.7).

**Verificación de conservación de masa (los 19 escenarios):** todos entre
`1e-10` y `1e-12` toneladas — mismo orden de magnitud que la Fase 1, sin
regresión al agregar las funciones nuevas.

## F2.4 Sensibilidad de parámetros no calibrados (`scripts/sensitivity_circuit_state.py`)

Sobre un escenario de referencia (ventana T8 de 8h, 1 bola por SAG), se
movió cada parámetro sin dato calibrado dentro de un rango razonable y se
midió el impacto en KPIs:

| Parámetro | Rango probado | Impacto medido |
|---|---|---|
| `one_ball_capacity_factor` | 0.40 – 0.70 | **Alto**: inventario mínimo SAC1 pasa de 41.9% (0.40) a -0.0%/STARVED (0.70) — es el supuesto más sensible del kernel. Solo tiene efecto cuando `enforce_downstream_ball_capacity=True` (opt-in, no está en la ruta calibrada por default — ver Fase 1 sección 5). |
| `feed_recovery_time_min` | 0 – 120 min | Bajo-moderado: inventario final SAC1 43.2%→45.6% (2.4pp) en el escenario probado. |
| `sag_ramp_up_time_min` | 0 – 60 min | Bajo: inventario final SAC1 45.3%→45.6% (0.3pp). |
| `trend_tolerance_tph` | 0.5 – 10 TPH | Nulo en el escenario probado: la magnitud del drenaje/llenado supera ampliamente todos los umbrales probados, la clasificación FILLING/DRAINING no cambia. No se expone como parámetro de `simulate_ode` (es interno a `determine_pile_trend`/`analyze_window_episode`); se midió llamando el kernel directo con las series ya simuladas. |

Conclusión operacional: si se decide calibrar alguno de estos cuatro
supuestos con datos reales de planta, **priorizar `one_ball_capacity_factor`**
— es el único con impacto suficiente para cambiar si un escenario llega o
no a STARVED. Los otros tres pueden quedarse en su default documentado sin
riesgo material mientras no se activen explícitamente.

Datos completos: `outputs/validation/circuit_state/sensibilidad_parametros.json`.

## F2.5 Controles avanzados mínimos en la UI (`components/controls.py`, `pages/simulador_operacional.py`)

Se agregaron al `AccordionItem "Avanzado"` (ya existente, colapsado por
defecto) 6 controles nuevos para los parámetros de Fase 1-2 que antes solo
eran accesibles llamando al motor directamente: modo de recuperación
(instantánea/exponencial), tiempo de recuperación, rampa de arranque SAG,
switch para forzar la capacidad de 1 bola como techo físico, factor de
capacidad con 1 bola, y switch de redistribución SAC1↔SAC2. Todos con el
default que reproduce el comportamiento actual — nadie que no abra
"Avanzado" ve ningún cambio. Se conectaron a los 3 puntos de
`update_simulation()` donde se llama `simulate_scenario_cached(...)` para
el escenario que el usuario ve (actual, con baseline sin T8, y modo
"recomendación vigente"). **No** se conectaron a los 2 puntos que generan
los escenarios de comparación fijos Configurado/Conservador/Máx Producción
— esos representan políticas de rate, no exploración de los supuestos
físicos nuevos, y mezclarlos habría hecho la comparación menos legible sin
que se haya pedido.

## F2.6 Anotaciones incrementales en el gráfico principal (`components/graphs.py::make_master_pile_chart`)

**No se rediseñó el gráfico a 4 paneles** (fuera de alcance declarado, ver
"Alcance de Fase 2" al inicio de la sesión). Se enriqueció el marcador de
"nivel mínimo proyectado" ya existente para usar `window_episode_sagX`
cuando está disponible: ahora muestra el instante exacto del mínimo
calculado por la ventana (no un `argmin` crudo que podía caer fuera del
período relevante), resalta en rojo y con anotación "STARVED" si el
circuito llegó a agotarse, y agrega una línea vertical de "recuperación
completa" en el tiempo real que toma volver al nivel pre-ventana (antes
solo había una línea de "inicio de recuperación" heurística basada en
`duracion_t8_h`, sin indicar cuánto tardaba la recuperación real). Cuando
no hay ventana (`window_episode_sagX is None`), el gráfico cae de vuelta al
comportamiento anterior sin error (verificado explícitamente).

## F2.7 Limpieza aplicada durante esta fase

- Eliminados 10 archivos HTML obsoletos en `outputs/validation/circuit_state/`
  generados por la versión anterior de `validate_circuit_state.py`
  (nombres de escenario que ya no existen tras el rename de F2.3).
- Agregado `05_Dashboard/outputs/validation/` y `05_Dashboard/outputs/debug/`
  a `.gitignore` — son artefactos 100% regenerables vía los scripts de
  `scripts/`, no evidencia formal versionada.
- No se generaron reportes parciales adicionales: esta sección se agregó
  al reporte ya existente de la Fase 1 en vez de crear un archivo nuevo,
  siguiendo la regla de consolidación por tema.

## F2.8 Evidencia de pruebas (Fase 2)

```text
comando: python -m pytest tests --ignore=tests/test_portable_smoke.py --ignore=tests/test_performance_portable.py -q
resultado: 319 passed in ~92-168s (variable por carga del equipo)
  (231 preexistentes + 42 test_circuit_state.py + 19 test_ode_model_integration.py
   [Fase 1, sin regresión] + 27 test_circuit_state_phase2.py [nuevos])
```

Corrida repetida 3 veces durante esta fase (tras cada bloque de cambios:
kernel, wiring UI, anotaciones de gráfico) — 319/319 las 3 veces, cero
regresiones acumuladas.

## F2.9 Qué quedó explícitamente fuera de alcance (declarado, no implícito)

Siguiendo la instrucción del pedido de no declarar como validado lo que
solo se comprobó matemáticamente, se deja constancia explícita de lo que
esta fase **no** hizo:

- **Backtesting histórico con partición train/val/test de eventos T8
  reales** (sección 11 del pedido) — no se ejecutó. Todo lo reportado en
  este documento (conservación de masa, sensibilidad, escenarios) es
  verificación **matemática/interna** del motor (el balance cuadra, los
  parámetros responden como se espera), **no** validación contra
  desempeño real de planta.
- **Rediseño completo del gráfico principal a 4 paneles** (sección 9) — se
  hicieron anotaciones incrementales (F2.6), no la reestructuración
  completa pedida.
- **Cobertura exhaustiva de los ~25 escenarios listados en la sección 15**
  del pedido — se cubrió un subconjunto representativo de 19 escenarios
  (ver F2.3), no la lista completa.
- **Verificación manual en navegador de los controles nuevos** — se probó
  por import + llamada directa al motor con los kwargs nuevos y por la
  suite de tests, no por captura de pantalla de la app corriendo con los
  sliders movidos.
- La app no se reinició para esta fase (se evitó por la lección ya
  documentada sobre matar procesos `python.exe` sin autorización expresa);
  la verificación funcional de la UI queda pendiente de que el usuario
  reinicie su propio servidor y confirme visualmente el nuevo
  `AccordionItem "Avanzado"` y las anotaciones del gráfico.

## F2.10 Riesgos residuales (Fase 2)

- `one_ball_capacity_factor` es el supuesto más sensible del kernel (F2.4)
  y sigue sin dato calibrado — si se activa
  `enforce_downstream_ball_capacity=True` en un escenario real, hacerlo
  junto con el equipo de terreno, no solo desde la UI.
- Los controles avanzados nuevos no tienen validación de rango cruzada en
  la UI más allá de los límites del slider (ej. nada impide combinar
  `redistribution_enabled=True` con `enforce_downstream_ball_capacity=True`
  simultáneamente — combinación no probada explícitamente, aunque cada una
  por separado sí lo está).
- Igual que en Fase 1: la validación histórica contra eventos T8 reales
  sigue pendiente como la brecha más importante antes de tratar cualquier
  resultado de este motor como predicción operacional confiable, en vez de
  una simulación físicamente consistente.
