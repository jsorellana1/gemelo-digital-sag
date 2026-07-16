# Diagnóstico de fidelidad histórica — Fase 4B (parcial)

Fecha: 2026-07-15. Continuación de la Fase 4 del roadmap de cierre
(`04_Reports/Technical/20260715_Roadmap_Cierre_Simulador_Operacional.md`)
tras el hallazgo de que el simulador falla su tolerancia de MAE (5.0pp)
en 4 de 5 regímenes con datos suficientes.

**Alcance real de esta pasada** (el pedido original de Fase 4B-4D es un
programa de investigación de varias sesiones — ver "Fase 4 Congelamiento
de línea base"): Fase 1 (congelar línea base) completa. Fase 2
(validar la métrica) completa. Fase 3.1 (diagnóstico causal de
`alimentacion_restringida`, el régimen de mayor N) con un hallazgo real
y verificado — descartado. **Fase 3.2 (`_pile_feedback_factor`) con un
hallazgo real y verificado — confirmado con evidencia cuantitativa
fuerte. Fase 3.3 (`t8_corta`) también queda confirmada en esta
continuación: comparte el mismo patrón de breakpoints con una señal
incluso más fuerte. Fase 3.4 (`mantenimiento`) y Fase 3.5 (`overflow`
como control positivo) también quedan cerradas en esta continuación.**
Fase 5 del pedido (split calibración/validación temporal real) también
queda ejecutada en esta continuación y confirma que hoy **no existe
hold-out genuino** para `DRAIN_PCT_H`; se propone un corte temporal
concreto para construirlo. **Fase 6 (recalibración experimental de
`DRAIN_PCT_H` con ese hold-out)** también queda ejecutada y muestra que
esa constante **no mueve el MAE de pila** en la ruta actual del motor.
Fases 7-11 (modelos candidatos B-F, bootstrap/intervalos de confianza,
impacto en decisiones) **no se ejecutaron esta pasada** — se documentan
como próximos pasos concretos, no como brechas sin plan. **No se
modificó ningún parámetro de calibración en esta pasada**
(`DRAIN_PCT_H`, `VENTANA_FACTOR_ESTADO`, `_pile_feedback_factor` sin
cambios) — solo diagnóstico.

---

## Fase 1 — Línea base congelada

Ver `04_Reports/Technical/backtesting_baseline_manifest.json` (generado
en esta pasada): branch, HEAD (`2579ae4`), working tree limpio, hash
SHA-256 (16 hex) de los 4 datasets fuente usados por el backtesting,
parámetros activos (`DRAIN_PCT_H`, `CRITICAL_PCT`, `VENTANA_FACTOR_
ESTADO`, `ONE_BALL_CAPACITY_FACTOR`), `N_MINIMO_EVENTOS`,
`TOLERANCIAS_BACKTESTING`, y los resultados MAE/bias/std por régimen
tal como estaban al momento de esta investigación — línea base para
comparar cualquier cambio futuro.

## Fase 2 — Validación de la métrica

Confirmado leyendo `historical_backtesting.py::run_backtest`/
`run_backtest_proxy` (no se modificó, solo se auditó):

- **Definición del error**: `pila_mae_sag1_pp = mean(|pila_sim_final -
  pila_obs_final|)` — error absoluto medio en puntos porcentuales de
  pila, calculado sobre **el estado final del evento** (no la
  trayectoria completa, no el mínimo). `pila_bias_sag1_pp = mean(pila_
  sim_final - pila_obs_final)` (con signo — agregado en la pasada
  anterior de esta serie).
- **Alineación temporal**: para `t8_corta`/`t8_larga` (fuente oficial),
  el "final" observado es el registro POST más cercano a `h_rel_fin=0`
  (inmediatamente al terminar el evento) — corregido en 2026-07-07 tras
  un bug donde se usaba el último registro de una ventana POST de 48h
  (ver comentario en el código citando `DIAGNOSTICO_MAE_t8_corta.md`).
  Para los regímenes proxy, es literalmente `sub.iloc[-1]` (última fila
  de la sub-serie del evento detectado) — **sin el mismo cuidado de
  alineación** que ya se aplicó a t8_corta. Esto es una discrepancia
  metodológica real entre ambas rutas de backtesting, no confirmada como
  causa del error pero **documentada como hipótesis a verificar en la
  siguiente pasada** (Fase 3.2+).
- **Timestamps/interpolación/timezone**: los eventos proxy usan
  `df["fecha"] >= ev.inicio` / `<= ev.fin` sobre la serie de 5 min ya
  resampleada — sin interpolación adicional, sin manejo de timezone
  explícito (se asume que la serie fuente ya está en hora local
  consistente).
- **Datos faltantes**: ambas rutas descartan eventos con `pila_ini`/
  `pila_fin` nulos (`dropna`) antes de calcular error — no se imputa.
- **Qué mide el MAE hoy**: estado final del evento, no el mínimo ni el
  tiempo del mínimo (`error_tiempo_critico_h` es una métrica aparte, ya
  existente, solo para regímenes con `DIRECCION_CRITICIDAD` definida:
  `t8_corta`, `t8_larga`, `inventario_critico`, `overflow` — no
  `mantenimiento`/`alimentacion_restringida`).
- **Métricas complementarias ya disponibles tras la pasada anterior**:
  MAE, bias, std (⇒ RMSE es derivable: para error con media `bias` y
  desviación `std`, `RMSE² = bias² + std²` — no se agregó como campo
  propio esta pasada, es aritmética directa sobre los campos ya
  expuestos). Mediana/P90 del error absoluto: **calculados ad-hoc en
  esta pasada** para `alimentacion_restringida` (ver Fase 3.1) a partir
  de `BacktestResult.detalle`, no expuestos todavía como campo
  permanente de `BacktestResult` — pendiente si se confirman útiles de
  forma recurrente.

**Conclusión de Fase 2**: el MAE está bien definido y es reproducible,
pero **mide únicamente el estado final del evento**, con una
inconsistencia de alineación temporal entre la ruta "oficial" (t8_corta,
ya corregida) y la ruta "proxy" (los otros 4 regímenes, sin la misma
corrección aplicada). No se encontró un error de cálculo que invalide
las cifras reportadas — son reales.

---

## Fase 3.1 — Diagnóstico causal: `alimentacion_restringida` (N=1.477, prioridad máxima)

### Hallazgo principal: la hipótesis del "factor fijo 0.4" queda descartada para este régimen

Se verificó en el código (`engine/ode_model.py::compute_qin`, líneas
240-258) que `VENTANA_FACTOR_ESTADO["reducida"]=0.4` **solo se aplica
si `t8_activo` es `True`** (es decir, `duracion_t8_h > 0`). El
backtesting de `alimentacion_restringida`
(`historical_backtesting.py::run_backtest_proxy`, líneas ~398-407) llama
a `simulate_scenario_cached` con **`duracion_t8_h=0.0`** y
**`cv_mode="manual"`, `cv315_manual_tph=cv315_mean` / `cv316_manual_tph=
cv316_mean`** — los valores REALES observados de CV315/CV316 durante el
evento, no un factor fijo. **El factor 0.4 nunca se invoca en esta ruta
de backtesting.** La hipótesis 3.1 del pedido ("si aplica un factor fijo
0.4 cuando la reducción real es variable") es correcta como preocupación
general del modelo pero **no explica el error de este régimen
específico** — el modelo ya recibe la alimentación real como dato de
entrada aquí.

### Descomposición del error: el problema no está en F_in a nivel agregado

Con el modelo recibiendo la alimentación real observada, se comparó el
error de pila final (lo que falla la tolerancia) contra el error de TPH
efectivo simulado (`tph_sag1` promedio del evento vs. `SAG1_tph`
observado promedio — mide si el CONSUMO/F_out simulado reproduce el
real):

```text
                          media      mediana    P90
Error pila final (pp)    12.80      10.01      30.04
Error TPH/F_out (%)      10.07       0.00      37.80   (n=1.156/1.477 eventos)
```

**Hallazgo clave**: la **mediana** del error de TPH es **0.0%** — en la
mitad o más de los eventos, el consumo simulado reproduce el observado
casi exactamente. Sin embargo la mediana del error de pila sigue siendo
~10pp. Esto es evidencia real (no especulación) de que el error **no es
principalmente un sesgo sistemático de nivel de alimentación o
consumo** — es más consistente con:

1. **Divergencia de trayectoria/dinámica**: aunque los promedios de
   F_in/F_out coincidan, el *momento* en que cambian dentro del evento
   puede no coincidir (el balance de masa integra en el tiempo — un
   desfase temporal entre observado y simulado, aunque los promedios
   sean iguales, produce error acumulado en la pila).
2. **Un subconjunto de eventos con error grande** (P90=30-38pp, muy por
   encima de la mediana) que arrastra la media — no un error uniforme
   en todos los eventos. Esto apunta a una causa que aplica solo a
   ciertas condiciones (ej. eventos donde el SAG queda `STARVED` en el
   modelo pero no en la realidad, o viceversa — exactamente la hipótesis
   3.2 del pedido, "_pile_feedback_factor"/comportamiento bajo
   `CRITICAL_PCT`), no a un parámetro de nivel de alimentación mal
   calibrado.

**Implicación para el orden de investigación**: la hipótesis 3.2
(`_pile_feedback_factor`, comportamiento cerca de `CRITICAL_PCT`,
posible doble reducción de rate, geometría `CAP_TON × pile_pct/100`) es
**más prometedora que 3.1 para explicar el grueso del error**, incluso
para el régimen de mayor N. Se recomienda que la siguiente pasada
invierta el orden de prioridad del pedido original: 3.2 antes que
profundizar más en 3.1.

### No se investigó esta pasada (explícitamente diferido)

- Segmentación por circuito/duración/hora/nivel inicial/rate/bolas/
  chancadores (pedido en la sección "Segmenta por").
- Cálculo de `f_real_feed = F_in_observado / F_in_baseline` y su
  distribución (no aplica directamente dado que el hallazgo principal
  ya descarta el factor fijo como causa — pero podría revelarse útil
  igual para caracterizar la variabilidad real de F_in, pendiente).
- Los 20 eventos con mayor error individual (candidatos a inspección
  manual/outlier).

---

## Fase 3.2 — Diagnóstico causal: `_pile_feedback_factor` (confirmado con evidencia cuantitativa)

### Método

Se reprodujo la misma llamada que usa `run_backtest_proxy` para cada
evento (mismo `pila_ini`, `rate`, `cv_mode`/`cv315_manual_tph`/
`cv316_manual_tph`, `horizonte_horas`), pero **conservando la
trayectoria simulada completa** de `pile_sag1` (que `run_backtest_proxy`
descarta tras extraer solo el estado final) para detectar si la
simulación cruzó alguno de los 3 breakpoints de
`_pile_feedback_factor` (`ode_model.py:354-380`: 35% → conservador,
25% → mínimo técnico, `CRITICAL_PCT+5%` → emergencia). Se comparó el
error de pila final entre eventos que SÍ cruzaron cada breakpoint y
eventos que NO, para `alimentacion_restringida` (N=1.477) e
`inventario_critico` (N=221) — los dos regímenes con mayor prioridad
por N y por MAE.

### Resultado — `alimentacion_restringida` (N=1.477)

```text
Breakpoint cruzado en la    N (no/sí)    Error medio (pp)   Error mediana (pp)
simulación
< 35% (conservador)          870 / 607     8.56 / 18.88        7.57 / 15.15
< 25% (mínimo técnico)      1077 / 400     9.34 / 22.11        8.24 / 18.62
< CRITICAL_PCT+5% (emerg.)  1161 / 316     9.83 / 23.74        8.49 / 21.43
```

### Resultado — `inventario_critico` (N=221)

```text
Breakpoint cruzado en la   N (no/sí)    Error medio (pp)   Error mediana (pp)
simulación
< 35% (conservador)          78 / 143      7.10 / 17.59        4.65 / 10.46
< 25% (mínimo técnico)      106 / 115      7.92 / 19.40        4.26 / 12.04
< CRITICAL_PCT+5% (emerg.)  115 / 106      8.42 / 19.82        5.37 / 11.40
```

### Hallazgo confirmado

**Patrón consistente y fuerte en ambos regímenes**: los eventos donde la
pila SIMULADA cruza los breakpoints de `_pile_feedback_factor` tienen
**2.0-2.5x más error** que los que no cruzan, y el error crece
monótonamente cuanto más profundo el breakpoint (35% → 25% → crítico+5%
→ error creciente en ambos regímenes). Esto es evidencia cuantitativa
real, no especulación, de que el dose-response automático de
`_pile_feedback_factor` (breakpoints y magnitudes de reducción —15%/
—30%/—50% — sin fuente de calibración citada, confirmado en la Fase 4.1
de la pasada anterior) es un **contribuyente real y medible** al error
de fidelidad, más que el nivel de alimentación (hipótesis 3.1, ya
descartada).

**Interpretación física**: el modelo asume que, ante una pila baja,
**siempre** se reduce el rate según una curva fija de 3 tramos. Si el
comportamiento operacional real difiere (los operadores no siempre
reducen exactamente así, o reducen antes/después, o en menor/mayor
magnitud, o la decisión depende de factores que el modelo no ve — T8,
turno, criticidad de otros equipos), la trayectoria simulada diverge
de la real precisamente en los eventos donde este mecanismo se activa
— coincide exactamente con el patrón observado (P90 alto, mediana de
F_out=0% pero pila con error persistente, ver Fase 3.1).

**Importante — no es evidencia de causalidad completa**: incluso los
eventos que NUNCA cruzan 35% siguen teniendo error medio de 7-9pp,
por encima de la tolerancia de 5pp. `_pile_feedback_factor` explica una
parte real y sustancial del error, no todo — quedan otras fuentes por
investigar (Fase 3.4 en adelante, geometría `CAP_TON`, alineación
temporal de la ruta proxy ya señalada en Fase 2).

**No se modificó `_pile_feedback_factor` en esta pasada** — la
recalibración (Fase 4C del pedido) requiere primero: (a) datos reales
de cuándo/cuánto reducen los operadores el rate ante pila baja (no
disponibles en este análisis), y (b) el split calibración/validación
temporal real (Fase 5 del pedido de Fase 4B, **ya diagnosticada en esta
continuación**) para no repetir el problema de hold-out ya encontrado
con `DRAIN_PCT_H`.

---

## Fase 3.3 — Diagnóstico causal: `t8_corta` (confirmado con la misma metodología)

### Método

Se extendió exactamente la misma lógica de cruce de breakpoints al
backtesting "oficial" de `t8_corta` (63 eventos válidos), reutilizando
la llamada actual de `run_backtest()` tras la corrección de
2026-07-07: mismo `pila_ini`, mismo `rate` promedio observado, misma
duración real del T8 y `cv_mode="manual"` con `cv315_manual_tph`/
`cv316_manual_tph` observados durante `DURANTE`. Como en Fase 3.2, se
conservó la trayectoria completa de `pile_sag1` para marcar si la
simulación cruzó alguno de los breakpoints de `_pile_feedback_factor`
(35%, 25%, `CRITICAL_PCT+5%` = 20% para SAG1) y se comparó el error de
pila final entre eventos que SÍ cruzan y eventos que NO.

### Resultado — `t8_corta` (N=63)

```text
Breakpoint cruzado en la   N (no/sí)    Error medio (pp)   Error mediana (pp)
simulación
< 35% (conservador)         20 / 43      4.00 / 25.80        2.87 / 27.39
< 25% (mínimo técnico)      29 / 34      3.81 / 31.73        1.73 / 31.45
< CRITICAL_PCT+5% (emerg.)  33 / 30      6.58 / 32.41        1.80 / 32.60
```

### Hallazgo confirmado

**`t8_corta` comparte la misma causa y con señal más fuerte que los
regímenes proxy**: los eventos donde la simulación cruza los breakpoints
de `_pile_feedback_factor` tienen **4.9-8.3x más error** que los que no
cruzan. El patrón también es monotónico: mientras más profundo el cruce
(35% → 25% → crítico+5%), mayor el error medio del subconjunto que sí
cruza.

**Interpretación importante para `t8_corta`**: el diagnóstico de
2026-07-07 sigue siendo correcto pero incompleto. Alimentar el backtest
con `cv_mode="manual"` y la restricción real de correas explicó la
primera gran caída del MAE (27.8pp → 18.9pp), pero el error remanente
ya no se distribuye parejo: queda **fuertemente concentrado** en los
eventos donde el ODE activa su feedback fijo de pila baja. Es decir, el
problema ya no es solo "feed real vs. feed asumido"; también hay una
divergencia material en la forma en que el modelo reduce el rate cuando
la pila simulada entra en zona baja durante un T8 real.

**Matiz relevante**: a diferencia de `alimentacion_restringida` e
`inventario_critico`, en `t8_corta` los eventos que NO cruzan 35% tienen
error medio de **4.00pp**, esencialmente dentro de la tolerancia de 5pp.
Eso sugiere que, para este régimen, `_pile_feedback_factor` explica una
fracción todavía mayor del MAE total que en los otros dos casos ya
diagnosticados.

---

## Fase 3.4 — Diagnóstico causal: `mantenimiento` (heterogéneo, pero con señal real de `_pile_feedback_factor`)

### Método

Se aplicó la misma reproducción evento-a-evento de
`run_backtest_proxy("mantenimiento")`, conservando la trayectoria
completa de `pile_sag1` para marcar cruces de breakpoints. A diferencia
de los otros regímenes, aquí la mezcla de eventos es físicamente más
heterogénea por construcción (`mantenimiento_SAG1` y
`mantenimiento_SAG2`), así que además del agregado total se inspeccionó
el sesgo por subtipo.

### Resultado — `mantenimiento` (N=239)

```text
Breakpoint cruzado en la   N (no/sí)    Error medio (pp)   Error mediana (pp)
simulación
< 35% (conservador)        163 / 76      11.15 / 21.59       7.69 / 18.47
< 25% (mínimo técnico)     199 / 40      12.31 / 25.22       8.00 / 18.91
< CRITICAL_PCT+5% (emerg.) 209 / 30      12.91 / 25.31       8.71 / 18.91
```

### Hallazgo confirmado

**También aquí `_pile_feedback_factor` es un contribuyente real**: los
eventos que cruzan breakpoints tienen **~1.9-2.1x más error** que los
que no cruzan, con crecimiento monotónico del grupo que sí cruza
(21.59pp → 25.22pp → 25.31pp). La señal es más débil que en `t8_corta`,
pero consistente con la observada en `alimentacion_restringida` e
`inventario_critico`.

**La heterogeneidad de `mantenimiento` queda confirmada cuantitativamente**:
el bias agregado casi nulo (+0.27pp) **no significa ausencia de
problema**, sino cancelación entre subtipos de signo opuesto:
`mantenimiento_SAG1` tiene bias medio **+8.30pp** (MAE 12.86pp),
mientras `mantenimiento_SAG2` tiene bias medio **−10.50pp** (MAE
16.63pp). Esto explica por qué el régimen total muestra MAE alto con
bias global cercano a cero, tal como sugería el pedido original.

**Interpretación útil**: en `mantenimiento`, `_pile_feedback_factor`
explica parte real del error, pero no toda. El régimen mezcla al menos
dos mecanismos distintos y la señal del feedback de pila baja se ve
especialmente fuerte en `mantenimiento_SAG2`, donde los eventos que
cruzan 35%/25% muestran errores muy superiores al resto. La conclusión
correcta no es "causa única", sino "contribuyente confirmado dentro de
un régimen heterogéneo".

---

## Fase 3.5 — `overflow` como control positivo

### Método

Se corrió la misma reproducción evento-a-evento de
`run_backtest_proxy("overflow")`, nuevamente conservando la trayectoria
de `pile_sag1` para verificar si algún evento entraba en los umbrales
bajos donde actúa `_pile_feedback_factor`.

### Resultado — `overflow` (N=97)

```text
Breakpoint cruzado en la   N (no/sí)    Error medio (pp)   Error mediana (pp)
simulación
< 35% (conservador)         97 / 0       4.51 / N/A         3.69 / N/A
< 25% (mínimo técnico)      97 / 0       4.51 / N/A         3.69 / N/A
< CRITICAL_PCT+5% (emerg.)  97 / 0       4.51 / N/A         3.69 / N/A
```

### Hallazgo confirmado

**`overflow` funciona como control positivo limpio**: **0 de 97** eventos
cruzan cualquiera de los breakpoints de `_pile_feedback_factor`, y el
régimen es justamente el único que ya estaba dentro de tolerancia
(MAE=4.51pp). Esto no "prueba" por sí solo que `_pile_feedback_factor`
sea la única fuente de error en los otros regímenes, pero sí refuerza la
**especificidad del mecanismo**: cuando el régimen permanece lejos de la
zona de pila baja donde el feedback actúa, el backtesting no exhibe el
mismo problema de fidelidad.

**Interpretación práctica**: el control positivo sale como uno esperaría
si el problema estuviera asociado a la dinámica de inventario bajo, no a
un defecto transversal del cálculo de MAE. `overflow` no necesita una
causa correctiva nueva en esta pasada; más bien sirve como contraste
contra los regímenes donde el feedback sí entra en juego.

---

## Fase 5 — Split calibración/validación temporal real (ejecutada)

### Método

Se cruzó explícitamente `01_Data/Processed/fact_eventos_t8.parquet`
(fuente usada para calibrar `DRAIN_PCT_H`) contra
`01_Data/Cache/advanced_t8_official_events.parquet` (fuente del
backtesting oficial `t8_corta`) con dos criterios:

1. **Match estricto** por fecha de inicio + duración.
2. **Cobertura temporal real**: un evento oficial se considera
   contaminado si su fecha cae dentro del intervalo [`inicio`, `fin`]
   de una ventana de calibración de `fact_eventos_t8`, aunque esta no
   tenga hora exacta.

El segundo criterio es el relevante para hold-out, porque
`fact_eventos_t8` documenta solo fechas-día y en el propio informe de
calibración (`20260625_Pilas_Descarga_Robusto.md`) se declara que esas
ventanas se expanden a cobertura diaria, no a timestamps exactos.

### Resultado

```text
Ventanas únicas de calibración (`fact_eventos_t8`)           : 29
Eventos oficiales de backtesting (`advanced_t8_official`)   : 72
Rango calibración                                           : 2026-01-02 -> 2026-06-25
Rango backtesting oficial                                   : 2026-01-02 -> 2026-06-25
Matches exactos fecha+duración                              : 6
Eventos oficiales cubiertos por >=1 ventana de calibración  : 72 / 72
Eventos oficiales fuera de toda ventana de calibración      : 0 / 72
```

**Hallazgo principal**: el problema ya no es "solape probable" sino
**solape total**. Los 72 eventos oficiales del backtesting caen dentro
de alguna de las 29 ventanas usadas para calibrar `DRAIN_PCT_H`. El
hold-out actual es, por tanto, **nulo**: hoy no existe un solo evento
oficial completamente fuera de muestra para ese parámetro.

### Corte temporal recomendado

Se evaluaron cortes simples para construir un split real sin inventar
datos nuevos. El mejor equilibrio encontrado en esta pasada es
**2026-04-30**:

```text
Corte 2026-04-30
- Ventanas de calibración: 21
- Eventos oficiales en calibración: 50
- Eventos oficiales hold-out: 22
- Eventos `t8_corta` (<=4h) en calibración/hold-out: 44 / 20
```

**Por qué este corte es el candidato natural**:

- Mantiene **20 eventos `t8_corta`** en hold-out, justo el mínimo de
  suficiencia ya usado por `historical_backtesting.py`.
- Conserva **21 ventanas de calibración** para recalcular
  `DRAIN_PCT_H`, evitando un conjunto de entrenamiento demasiado chico.
- Cortes más tardíos (`2026-05-15`, `2026-05-31`) dejan hold-out
  demasiado pequeño para `t8_corta` (14 y 10 eventos, respectivamente).

### Conclusión operativa

**Fase 5 queda cerrada como diagnóstico, no como recalibración**:

- Hoy **no hay hold-out genuino** para `DRAIN_PCT_H`.
- El MAE histórico de `t8_corta` reportado hasta ahora **no es fuera de
  muestra** para ese parámetro.
- La siguiente pasada ya no debe "verificar si hay solape", sino usar
  ese split para probar si cualquier candidato de recalibración mejora
  realmente el hold-out.

---

## Fase 6 — Recalibración experimental de `DRAIN_PCT_H` con hold-out real

### Método

Se ejecutó una recalibración experimental de `DRAIN_PCT_H` usando el
corte recomendado de Fase 5 (`2026-04-30`) y la misma lógica física del
modelo de descarga robusto: cálculo evento-a-evento de tasa de descarga
en ventanas T8 y promedio global por activo. Para evitar ambigüedades
del Excel crudo, la corrida reutilizó la serie ya normalizada
`advanced_t8_historical_5min.parquet`, que contiene las mismas señales
5-min (`pila_sag1/2`, `SAG1_tph/2_tph`, estados operando) que usa el
resto de la validación histórica.

Luego se evaluó `t8_corta` sobre dos subconjuntos:

1. **Calibración**: eventos oficiales con fecha <= `2026-04-30`
   (`44` eventos).
2. **Hold-out**: eventos oficiales con fecha > `2026-04-30`
   (`20` eventos, `19` utilizables; `EV072` queda fuera por datos
   incompletos de pila final).

La comparación se hizo **antes y después** de parchear temporalmente
`ode_model.DRAIN_PCT_H`, limpiando `simulation_cache` y los `lru_cache`
de `historical_backtesting` para evitar resultados contaminados por
cache.

### Nueva calibración propuesta

```text
DRAIN_PCT_H recalibrado con cutoff 2026-04-30
- SAG1: 27.85 %/h   (vs. actual 23.76, +17.2%)
- SAG2:  5.85 %/h   (vs. actual  6.18,  -5.3%)
- N válido de calibración: 21 eventos por SAG
```

### Resultado en `t8_corta`

```text
Subset                N    MAE pila (pp)   Bias (pp)   MAE t_crit (h)
Calibración actual    44     11.21          -8.54        3.28
Calibración recalib.  44     11.21          -8.54        4.36
Hold-out actual       19     36.63         -36.30        5.45
Hold-out recalib.     19     36.63         -36.30        7.44
```

### Hallazgo confirmado

**Recalibrar `DRAIN_PCT_H` no cambia en absoluto el MAE de pila** en
esta ruta de backtesting: MAE, bias y std de pila quedan idénticos antes
y después del cambio, tanto en calibración como en hold-out. Esto
confirma empíricamente lo que ya sugería la lectura del código:
`DRAIN_PCT_H` alimenta `compute_autonomia()` y métricas derivadas, pero
**no gobierna la trayectoria de `pile_sag1`** en la ruta actual de
`simulate_scenario()` / `simulate_ode()` usada por `run_backtest()`.

**Más importante aún**: el hold-out real de `t8_corta` sale mucho peor
que el agregado full-sample publicado hasta ahora:

- `t8_corta` calibración (<= `2026-04-30`): **MAE 11.21pp**
- `t8_corta` hold-out (> `2026-04-30`): **MAE 36.63pp**

Es decir, al pasar a una evaluación realmente fuera de muestra, el error
de pila **se triplica** aproximadamente. Esto sugiere que el MAE de
18.88pp reportado sobre el dataset completo estaba materialmente
optimista por contaminación temporal y/o cambio de régimen, no porque
`DRAIN_PCT_H` estuviera "mal calibrado" para la física de pila.

**Además, la recalibración empeora la métrica de tiempo a crítico**:
`t8_corta` hold-out pasa de **5.45h** a **7.44h** de MAE en
`error_tiempo_critico_h`. Eso significa que cambiar `DRAIN_PCT_H` a los
nuevos valores tampoco ofrece una mejora clara ni siquiera en la métrica
que sí depende directamente de esa constante.

### Conclusión operativa

**Fase 6 queda cerrada con resultado negativo pero útil**:

- `DRAIN_PCT_H` **no es la palanca correcta** para arreglar el P0 de
  fidelidad de pila.
- Aplicar esta recalibración en producción **no está justificado** en
  esta pasada.
- La siguiente iteración debe concentrarse en parámetros/mecanismos que
  sí alteran la trayectoria física de pila (`_pile_feedback_factor`,
  alineación temporal proxy, tasa variable intra-evento, etc.), y usar
  el hold-out ya construido para validar cualquier candidato nuevo.

---

## Fase 6.1 — Contrafactual hold-out de `_pile_feedback_factor`

### Método

Se ejecutó un experimento contrafactual sobre el mismo split temporal
real de Fase 5 (`2026-04-30`), reutilizando exactamente la llamada
actual de `run_backtest("t8_corta")` (mismo `pila_ini`, `rate` medio
observado, `duracion_h` real y `cv_mode="manual"` con `cv315`/`cv316`
observados), pero parcheando temporalmente `ode_model._pile_feedback_
factor` con una familia de versiones **escaladas**:

- `1.00`: baseline actual
- `0.75`: 75% del efecto actual
- `0.50`: 50% del efecto actual
- `0.25`: 25% del efecto actual
- `0.00`: feedback completamente desactivado (`factor=1.0`)

La escala se aplicó sobre la **reducción respecto de 1.0**, no sobre la
pila misma: `feedback_escalado = 1 - escala * (1 - feedback_actual)`.
Entre variantes se limpiaron `simulation_cache` y los `lru_cache` de
`historical_backtesting` para evitar contaminación por cache.

### Resultado global

```text
Escala feedback     Calibración (44)                 Hold-out (19)
                    MAE pila   Bias    MAE t_crit    MAE pila   Bias    MAE t_crit
1.00 baseline       11.21pp   -8.54pp   3.28h       36.63pp   -36.30pp   5.45h
0.75                11.84pp   -9.17pp   3.28h       37.59pp   -37.26pp   5.45h
0.50                12.64pp   -9.97pp   3.28h       38.43pp   -38.10pp   5.45h
0.25                13.09pp  -10.42pp   3.28h       38.98pp   -38.66pp   5.45h
0.00 sin feedback   13.46pp  -10.79pp   3.28h       39.26pp   -38.93pp   5.45h
```

### Hallazgo confirmado

**La evidencia fuera de muestra va en dirección opuesta a “desactivar o
relajar `_pile_feedback_factor`”**:

- En **calibración**, debilitar el feedback empeora el MAE de
  `11.21pp` a `13.46pp`.
- En **hold-out real**, debilitar el feedback empeora el MAE de
  `36.63pp` a `39.26pp`.
- El deterioro es **monótono** en ambos subconjuntos: mientras menor la
  intensidad del feedback, más negativo queda el bias y mayor el error.

Esto confirma dos cosas a la vez:

1. `_pile_feedback_factor` **sí está en el camino físico principal** del
   backtesting de `t8_corta` (modula `qout`, luego cambia la trayectoria
   de `pile_sag1`).
2. El feedback actual, aunque no esté formalmente calibrado con una
   fuente citada, es **direccionalmente útil**: removerlo o suavizarlo
   hace que la simulación subestime todavía más la pila final.

### Lectura correcta del hallazgo de Fase 3

La asociación fuerte observada antes (“los eventos que cruzan
breakpoints tienen mucho más error”) **sigue siendo cierta**, pero el
contrafactual hold-out obliga a afinar la interpretación:

- No significa que el feedback actual sea el culpable principal por
  exceso de reducción.
- Significa que **los eventos que caen a zona de pila baja son el
  subconjunto donde el modelo ya viene más desalineado**, y el feedback
  actual **mitiga parte** de ese desalineamiento en vez de crearlo.

La señal de hold-out es especialmente fuerte porque en el subconjunto
fuera de muestra:

- **19/19** eventos baseline cruzan `<35%`
- **18/19** cruzan `<25%`
- **16/19** cruzan `<20%` (`CRITICAL_PCT+5%` para SAG1)

Y aun dentro de esos subconjuntos profundos, reducir el feedback vuelve
el error peor de forma monotónica:

- Baseline `<25%` (18 eventos): `37.17pp` -> `39.93pp`
- Baseline `<20%` (16 eventos): `36.51pp` -> `39.40pp`

### Conclusión operativa

**Fase 6.1 cierra otro falso camino de recalibración rápida**:

- `_pile_feedback_factor` **sigue siendo el marcador individual más
  fuerte** de dónde se concentra el error.
- Pero **no conviene** atacar el P0 actual “apagando” o “suavizando” ese
  mecanismo: en hold-out real eso empeora el modelo.
- La siguiente iteración debe buscar causas que expliquen por qué el
  motor llega a esas zonas bajas con tanto sesgo negativo
  (alineación temporal proxy, variación intra-evento de `F_in/F_out`,
  cambios de régimen no capturados, etc.), no quitar el amortiguador que
  hoy ya ayuda parcialmente.

---

## Resultado consolidado de esta pasada

| Régimen | N | MAE (pp) | Bias (pp) | Diagnóstico de esta pasada |
|---|---|---|---|---|
| `alimentacion_restringida` | 1.477 | 12.80 | −11.82 | Hipótesis "factor fijo 0.4" **descartada** con evidencia de código. **`_pile_feedback_factor` confirmado como marcador/driver operativo fuerte**: eventos que cruzan sus breakpoints tienen 2.0-2.5x más error (18.88-23.74pp vs 8.56-9.83pp). La evidencia hold-out posterior en `t8_corta` sugiere que el mecanismo actual mitiga parte del sesgo en vez de causarlo por sí solo. |
| `inventario_critico` | 221 | 13.89 | −11.02 | Mismo patrón confirmado con `_pile_feedback_factor`: 2.0-2.5x más error en eventos que cruzan breakpoints (17.59-19.82pp vs 7.10-8.42pp). Sigue siendo una señal causal útil para focalizar, no una justificación para apagar el feedback. |
| `t8_corta` | 63 | 18.88 | −16.91 | Diagnóstico de 2026-07-07 **ampliado y afinado**: tras corregir feed real (`cv_mode="manual"`), el error remanente queda fuertemente concentrado en eventos que cruzan los breakpoints de `_pile_feedback_factor` (**4.9-8.3x más error**, 25.80-32.41pp vs. 3.81-6.58pp). Con hold-out real post-`2026-04-30`, el MAE fuera de muestra sube a **36.63pp**; recalibrar `DRAIN_PCT_H` no lo mueve, y **debilitar `_pile_feedback_factor` lo empeora monótonamente** (36.63pp -> 39.26pp). |
| `mantenimiento` | 239 | 14.47 | +0.27 | `_pile_feedback_factor` también aparece como contribuyente real (**~1.9-2.1x más error** cuando cruza breakpoints: 21.59-25.31pp vs. 11.15-12.91pp), pero dentro de un régimen efectivamente heterogéneo: el bias agregado casi nulo es cancelación entre `mantenimiento_SAG1` (+8.30pp) y `mantenimiento_SAG2` (−10.50pp). La lección de hold-out en `t8_corta` sugiere prudencia antes de “aflojar” ese feedback aquí. |
| `overflow` | 97 | 4.51 | +3.47 | **Control positivo confirmado**: 0/97 eventos cruzan cualquier breakpoint de `_pile_feedback_factor` y el régimen permanece dentro de tolerancia. Refuerza la especificidad del mecanismo de pila baja. |

## Próximos pasos concretos (no ejecutados esta pasada)

1. **Cobertura causal cerrada esta pasada**: los 5 regímenes con datos
   suficientes ya tienen diagnóstico causal o control positivo
   documentado (`alimentacion_restringida`, `inventario_critico`,
   `t8_corta`, `mantenimiento`, `overflow`).
2. **`DRAIN_PCT_H` descartado como palanca para MAE de pila**:
   recalibrarlo con cutoff `2026-04-30` cambia autonomía/tiempo a
   crítico, pero deja **idénticos** el MAE/bias/std de pila en
   calibración y hold-out. No conviene seguir iterando esa constante
   para resolver el P0 actual.
3. **No aflojar `_pile_feedback_factor` sin evidencia nueva**:
   en `t8_corta` hold-out real, reducirlo o apagarlo empeora el MAE de
   forma monótona (36.63pp -> 39.26pp). El mecanismo es parte de la
   física activa y hoy ayuda parcialmente; no es el siguiente lever
   razonable para una corrección rápida.
4. Investigar el error que **persiste incluso en eventos que no cruzan
   breakpoints** en los regímenes proxy y, más importante aún, el sesgo
   estructural que hace que casi todo el hold-out de `t8_corta` sí
   termine cruzándolos (19/19 bajo 35%, 18/19 bajo 25%, 16/19 bajo 20%).
   `_pile_feedback_factor` no es la única causa en el conjunto completo.
5. Formalizar la descomposición del error por subgrupos/outliers,
   especialmente en `mantenimiento`, donde el agregado mezcla al menos
   dos mecanismos físicos distintos.
6. ~~Corregir la alineación temporal de la ruta "proxy"~~ — **verificado
   y descartado (2026-07-15, pasada posterior)**: `run_backtest_proxy`
   usa `sub.iloc[-1]` sobre `sub = df[(df["fecha"] >= ev.inicio) &
   (df["fecha"] <= ev.fin)]`, y `ev.fin` (`regime_event_detector.py::
   _construir_evento`, línea `fin=fila_fin["fecha"].to_pydatetime()`)
   **es exactamente** la fecha de la última fila de la ventana detectada
   — sin padding. No es análogo al bug de 2026-07-07 en `_run_backtest_
   t8` (que sí tenía una ventana POST de 48h separada, requiriendo
   buscar la fila más cercana a `h_rel_fin=0`): el dataset proxy no tiene
   esa estructura, y `sub.iloc[-1]` ya apunta al estado final correcto
   por construcción. Confirmado leyendo `_construir_evento` completo, no
   solo el patrón de código superficial. **No requiere cambio.**
7. Usar el hold-out ya construido (`> 2026-04-30`) para probar solo
   candidatos que sí alteren la trayectoria física de pila y que hoy sí
   apunten en la dirección correcta (variación intra-evento de feed/rate,
   ventanas operacionales más realistas, alineación de estado final).
8. Fases 7-11 (modelos candidatos B-F, selección, robustez/bootstrap,
   impacto en decisiones) — no iniciadas, dependen de lo anterior.

## Condición para retomar Fase 5 (arquitectura) — sin cumplir todavía

Ni la Condición A (todos los regímenes principales dentro de
tolerancia) ni la Condición B (aprobación formal documentando
limitaciones aceptadas) están cumplidas. **La Fase 5 de refactor
arquitectónico sigue suspendida.**
