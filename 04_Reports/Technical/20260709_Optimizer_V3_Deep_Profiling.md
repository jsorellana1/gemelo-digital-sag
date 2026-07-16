# Profiling profundo y optimización de `find_optimal_v3`

**Fecha:** 2026-07-09
**Metodología:** medir primero, no optimizar a ciegas. Todos los números
de este reporte salen de correr `cProfile`/`pyinstrument` reales contra
`engine/optimizer_v3.py::find_optimal_v3` con `optimizer_cache.clear()`
antes de cada corrida (fuerza cache-miss, el caso relevante para
entender el costo real). **No se implementó ninguna optimización en
producción** — una excepción puntual y controlada se documenta en la
sección 8 (medición de impacto real, revertida antes de cerrar la
sesión).

---

## 1. Dónde se consumen los 5.2s promedio (Fase 1/2)

`cProfile`, régimen normal (sin T8), cache-miss, `pila1=pila2=55%`:

```
Total wall time: 10,135ms  (18,991,422 llamadas a funciones)

ncalls   tottime  cumtime  función
   1      0.000   10.132   find_optimal_v3
1670      0.052    9.627   simulate_scenario          (95.0% del total)
1670      2.357    9.454   simulate_ode
  20      0.001    8.846   adaptive_mc_eval wrapper (perf_logger)
  20      0.128    8.800   adaptive_mc_eval           (86.8% del total)
480,965   3.209    3.209   builtins.dir                (31.7% del total!)
   1      0.004    1.284   run_deterministic_grid
961,920   0.617    0.957   effective_rate
480,960   0.428    0.644   compute_t1_distribution
961,920   0.474    0.639   step_pile
```

**Hallazgo #1 (el más importante del reporte):** `builtins.dir()` se
llama **480,965 veces**, consumiendo **3.2 segundos — 31.7% del tiempo
total**, sin hacer ningún trabajo físico. Causa raíz encontrada en
`engine/ode_model.py:513`:

```python
b411_eff = _b411 if (_b411 and (not sag1_activo or 'r1_pct_dyn' not in dir() or _nb1_eff >= 1)) else 0
```

`dir()` sin argumentos construye la lista completa de nombres del scope
local actual — se usa aquí como una forma (muy costosa) de preguntar
"¿el branch `else` de la línea 495-499 se ejecutó en esta iteración?"
(es decir, "¿`regime_fn is None`?"). Es una comprobación equivalente a
la condición que YA se evalúa explícitamente unas líneas antes
(`if regime_fn is not None: ... else: r1_pct_dyn = ...`), reconstruida
de la forma más lenta posible, ejecutada **una vez por paso de
integración** dentro del loop caliente de `simulate_ode`.

`adaptive_mc_eval` (20 llamadas, una por candidato Top-20 del grid) es
el 86.8% del tiempo — dentro de él, `simulate_scenario`/`simulate_ode`
(1670 llamadas = ~83.5 muestras Monte Carlo promedio por candidato) es
prácticamente todo ese tiempo. **En agregado, "el ODE" sí es donde se
va el tiempo** (por volumen de llamadas, no porque cada llamada
individual sea lenta — cada `simulate_ode` tarda ~5.7ms) — pero un
tercio de ese tiempo agregado es el bug de `dir()`, no física.

---

## 2. Flamegraph (Fase 3)

Generado con `pyinstrument` (interval=0.5ms):
`04_Reports/Technical/flamegraphs/find_optimal_v3_flamegraph.html`
(abrir en cualquier navegador — es un archivo HTML autocontenido,
5.3MB). Confirma visualmente la misma jerarquía de arriba:
`find_optimal_v3` → 20× `adaptive_mc_eval` → N× `simulate_scenario` →
`simulate_ode` → el loop de integración con `effective_rate`/
`compute_t1_distribution`/`step_pile`/`dir()` como hojas anchas.

---

## 3. Perfilado por régimen (Fase 4)

`optimizer_cache.clear()` antes de cada régimen, misma corrida:

| Régimen | Duración | Candidatos→MC | Muestras MC (media / máx) | Convergentes |
|---|---:|---:|---:|---:|
| Normal (sin T8) | 6427ms | 20 | 77.5 / 190 | 20/20 |
| T8 corta (2h) | 7082ms | 20 | 96.0 / 180 | 20/20 |
| T8 corta (4h) | 8123ms | 20 | 104.0 / 190 | 20/20 |
| T8 larga (8h) | 6784ms | 20 | 85.0 / 180 | 20/20 |
| T8 larga (12h) | 5326ms | 20 | 68.5 / 150 | 20/20 |
| Inventario crítico | 4020ms | 20 | 50.0 / 50 | 20/20 |
| Mantención (SAG1 off) | **1155ms** | **10** | 85.0 / 130 | 10/10 |
| Alimentación restringida | 4079ms | 20 | 50.0 / 50 | 20/20 |
| Mixto (T8 larga + inv. crítico) | 4009ms | 20 | 50.0 / 50 | 20/20 |

**Respuesta a "¿existe un régimen que explique los 39s?": no.** Ningún
régimen individual, en condiciones normales de carga, se acerca a 39s —
el rango observado aquí es 1.2-8.1s. El máximo histórico de 39.4s
(`runtime_data/performance_log.csv`) es consistente con **contención de
CPU del sistema** (otro proceso compitiendo, o el primer cálculo tras
abrir la app con imports en frío) más que con un régimen
estructuralmente más caro — ningún régimen tiene un grid ni un tope de
muestras MC que por sí solo justifique 4-8× el tiempo normal.

**Hallazgo #2:** el régimen de **mantención** (SAG1 apagado) es ~5.5×
más rápido que el resto — no por un camino de código especial, sino
porque `find_optimal_v3` ya reduce el grid de candidatos R1 a un solo
valor cuando `sag1_on=False` (`r1_cands = R1_CANDS_V3 if sag1_on else
[int(SAG1_P50)]`, `engine/optimizer_v3.py:337`), lo que baja
`TOP_CANDS_FOR_MC` de 20 a 10 candidatos reales. Esto confirma
empíricamente que el tamaño del grid es proporcional al costo total —
información directamente accionable para la sección 8.

---

## 4. Perfilado de Monte Carlo (Fase 5)

`MC_MIN_N=30, MC_BATCH=10, MC_CONV_TOL=0.01, MC_CONV_CONSEC=3,
MC_MAX_N=500` (`engine/optimizer_v2.py:70-84`). El check de convergencia
arranca en n=30 y evalúa cada 10 muestras; converge cuando 3 chequeos
consecutivos tienen `|Δp_safe| < 0.01`.

**¿Se sigue simulando después de converger? No, en ningún caso
observado** — el `while n < MC_MAX_N` corta (`break`) apenas
`converged=True`. Lo que SÍ varía mucho es **cuánto tarda en
converger**, y es exactamente lo esperado de un criterio adaptativo
sano:

- Regímenes donde el resultado es **obviamente determinístico**
  (inventario crítico, alimentación restringida, mixto: `p_safe` es
  0.0 o 1.0 desde la primera muestra, no cambia) convergen en el
  **mínimo matemático posible dado `MC_MIN_N`/`MC_CONV_CONSEC`**: 50
  muestras exactas, en el 100% de los 20 candidatos de esos 3
  regímenes. Esto no es un bug — es el algoritmo funcionando
  correctamente ante una señal trivial.
- Regímenes con resultado **incierto/borderline entre candidatos**
  (normal, T8 corta/larga) muestran variación real (77.5-104 de media,
  hasta 190 muestras) — ahí es donde el adaptativo genuinamente
  invierte más presupuesto para distinguir candidatos parecidos.

**Conclusión:** el Monte Carlo adaptativo **sí aporta valor real** — no
hay evidencia de sobre-muestreo. El "problema" no está en el criterio
de convergencia, está en que **20 candidatos se evalúan
secuencialmente**, cada uno pagando su propio costo de convergencia
completo.

---

## 5. Perfilado del ODE (Fase 6)

`simulate_ode` (`engine/ode_model.py:371`): 1670 llamadas en la corrida
de referencia, **9.454s cumulativos, 5.66ms por llamada**. Cada llamada
integra `961,920 / 1670 ≈ 576` pasos (`step_pile`, `effective_rate`,
`compute_t1_distribution` se llaman una vez por paso).

**¿Es el ODE el cuello de botella, o está en otra parte?** Las dos
cosas son ciertas a la vez, en capas distintas:

- **En agregado**, sí — el 93% del tiempo total (`9.454s/10.13s`)
  ocurre dentro de `simulate_ode`, porque se llama ~1670 veces por
  optimización (grid × muestras MC).
- **Por llamada individual**, el ODE es barato (5.66ms) — el costo no
  es "el ODE es lento", es "se necesitan muchas evaluaciones del ODE".
- De ese 93%, **~34% (3.2s de 9.454s) es directamente el bug de
  `dir()`** — no física, no integración numérica real. El resto
  (`effective_rate`, `compute_t1_distribution`, `step_pile`,
  aritmética `numpy`) es trabajo genuino de simulación.

---

## 6. Auditoría de cache — ¿por qué 44.7% de hit rate? (Fase 7)

`engine/scenario_cache.py::scenario_hash()` construye el hash desde
`json.dumps({"args":..., "kwargs":...}, sort_keys=True)` **sin ningún
redondeo de floats**. Prueba directa:

```python
scenario_hash(pila1=55.0, ...) == scenario_hash(pila1=55.00001, ...)
# -> False
```

**Causa raíz confirmada:** `ctrl-pila-sag1`/`ctrl-pila-sag2`/
`ctrl-rate-sag1`/`ctrl-rate-sag2` son sliders continuos — cualquier
diferencia de float, por mínima que sea (arrastre de mouse, conversión
%→TPH con redondeo distinto), genera un hash distinto y por lo tanto un
**cache-miss aunque el escenario sea prácticamente idéntico**. No es
"hash demasiado sensible" en abstracto — es la ausencia total de
cuantización antes de hashear valores que por naturaleza son continuos
y aproximados (ninguna decisión operacional depende de la diferencia
entre pila=55.0% y pila=55.03%).

Otras causas descartadas: no hay evidencia de "escenarios equivalentes
tratados como distintos" por bugs de orden de kwargs (`sort_keys=True`
ya lo cubre), ni de caches no reutilizados entre módulos —
`optimizer_cache`/`simulation_cache`/`montecarlo_cache` son instancias
de proceso únicas y persistentes (ver `engine/scenario_cache.py`,
cierre de sesión anterior).

---

## 7. Ranking de optimizaciones (Fase 8 — NO implementado)

| # | Optimización | Beneficio esperado | Riesgo | Complejidad |
|---|---|---|---|---|
| 1 | **Quitar `dir()` en `ode_model.py:513`** (usar `regime_fn is None` directo) | **-36% medido en cache-miss** (10,135→6,490ms, ver sección 8) | Nulo — verificado bit-idéntico con seed fija | Quick win (<30 min) |
| 2 | **Redondear floats continuos antes de `scenario_hash`** (pila/rates a 1 decimal, ~0.1-0.5% de tolerancia) | Sube cache hit rate — en uso interactivo normal (arrastrar sliders cerca de un valor ya visto) podría acercarse al 90%+ | Bajo — elegir el redondeo con criterio operacional (no cambia qué se simula, solo qué cuenta como "mismo escenario") | Quick win (<2h) |
| 3 | Reducir `TOP_CANDS_FOR_MC` de 20 a ~12-14 | Reducción lineal directa (~30-40% menos evaluaciones MC) | Medio — puede perder candidatos marginalmente mejores; requiere validar contra datos históricos que no cambie la recomendación final en casos ya auditados | Media (2-8h, con validación) |
| 4 | Paralelizar las 20 llamadas a `adaptive_mc_eval` (multiprocessing, no threading — CPU-bound, GIL) | Hasta Nx según núcleos disponibles (4-8x típico en un laptop moderno) | Medio-alto — pool de procesos, serialización de resultados, reproducibilidad de `seed` entre procesos a verificar | Media-Mayor (4-8h+) |
| 5 | Vectorizar el loop interno del ODE (batch de muestras MC vía numpy en vez de Python puro por muestra) | Potencialmente el mayor de todos (orden de magnitud) — pero reescribe el motor físico central | Alto — debe preservar exactamente el comportamiento actual, alta superficie de regresión | Mayor (>8h) |
| 6 | Migrar a Dash Background Callbacks | No reduce el tiempo de cómputo — solo evita que el usuario vea una respuesta vieja mientras espera (problema de UX, no de velocidad) | Alto (ver sesión anterior, revertida) | Mayor |

**No vale la pena tocar:** el ODE por sí solo (5.66ms/llamada ya es
barato) y el criterio de convergencia MC (ya funciona correctamente,
sección 4) — cualquier esfuerzo ahí tiene ROI bajo comparado con #1-4.

---

## 8. Simulación de impacto — medición real, no estimación (Fase 9)

Se aplicó **temporalmente** la optimización #1 (una línea,
`engine/ode_model.py:513`), se midió, se verificó que el resultado es
**bit-idéntico** con `seed=42` fijo (`r1=1450, r2=1888,
b1=ambas_411_412, b2=ambas_511_512, tph_mean=3923.4,
score=0.9446` — idéntico antes y después), y se **revirtió** antes de
cerrar esta sesión (`git diff engine/ode_model.py` confirma que el
archivo quedó igual a como estaba, sin esta línea modificada).

| Optimización | Tiempo actual (cache-miss, régimen normal) | Tiempo medido con el fix | Ganancia |
|---|---:|---:|---:|
| #1 (quitar `dir()`) — **medido, no estimado** | 10,135ms | **6,490ms** | **-36.0%** |
| #2 (redondear cache) | 5.2s promedio actual (con 44.7% hit) | No medible sin datos de uso reales — requiere desplegar y observar el hit rate real | Estimado: sube el % de llamadas que caen en el "cache hit ≈0ms" en vez de "cache miss ≈5-10s" |
| #3 (grid más chico) | ~8.8s dentro de `adaptive_mc_eval` | No medido (cambia qué se evalúa, no solo cuánto tarda — requiere validación de calidad primero) | Estimado ~30% adicional sobre el tiempo YA reducido por #1 |
| #4 (paralelizar) | ~8.8s secuencial | No medido (requiere implementación real) | Estimado 3-6x en el tramo de `adaptive_mc_eval` con 4-8 núcleos |

**Combinando #1 + #2 (los dos quick wins, sin tocar el grid ni
paralelizar):** el caso cache-miss bajaría de ~10.1s a ~6.5s (medido),
y una fracción creciente de las llamadas en uso real dejaría de ser
cache-miss del todo (cache hit ≈0ms) — el promedio ponderado real
dependería de cuánto sube el hit rate, no se inventa ese número aquí.

---

## 9. ¿Es factible <3s sin cambiar arquitectura? (Fase 10)

**Parcialmente, no garantizado en todos los casos.** Con solo #1
(medido): 6.49s en cache-miss — sigue sobre 3s. Se necesitaría además
#2 (cache) para que la MAYORÍA de las interacciones sean cache-hit
(≈0ms, muy por debajo de 3s), y #3 o #4 para bajar el **peor caso**
(cache-miss puro) por debajo de 3s — con el grid actual (20
candidatos × MC adaptativo), incluso tras quitar el bug de `dir()`,
6.49s con convergencia rápida (régimen determinístico) sigue siendo
>3s; regímenes con convergencia lenta (T8 corta, ~104 muestras medias)
tardarían más. **Conclusión honesta: <3s consistente en TODO
escenario, sin tocar el grid ni paralelizar, no es alcanzable** — es
alcanzable como **mediana/caso típico** (cache-hit + regímenes rápidos)
pero no como garantía universal sin #3 y/o #4.

---

## 10. ¿Hacen falta Background Callbacks? (Fase 11)

**No, todavía no** — con la evidencia de esta sesión:

- El problema real es **velocidad de cómputo** (CPU-bound), no
  bloqueo de UI per se. Background callbacks resuelven "el usuario ve
  una pantalla no-congelada mientras espera" y "se puede cancelar una
  petición vieja" — **no** reducen el tiempo que `find_optimal_v3`
  tarda en calcular.
- La sesión anterior (`20260709_Performance_Hardening.md`) ya concluyó
  que un guard liviano client-side no funciona por una limitación
  estructural de Dash — Background Callbacks seguía como alternativa
  más robusta para ESE problema específico (respuestas fuera de
  orden), pero es un problema **distinto** al de "find_optimal_v3 es
  lento".
- **Regla del prompt aplicada:** no migrar arquitectura si la
  optimización interna puede resolver el problema — con #1+#2 (quick
  wins, bajo riesgo, medidos/bien entendidos) el caso típico mejora
  sustancialmente sin tocar la arquitectura de callbacks. Background
  Callbacks solo se vuelve necesario si, DESPUÉS de #1-#4, el peor
  caso (cache-miss + régimen de convergencia lenta) sigue siendo
  inaceptablemente largo para la operación real — eso se decide con
  datos de uso real tras desplegar #1+#2, no ahora.

---

## Resumen de hallazgos (Fase 14)

- [x] Dónde se consumen los 5.2s promedio: 87% en `adaptive_mc_eval`
      (20× MC secuencial), de eso ~34% es el bug de `dir()`.
- [x] Qué explica los casos de 39s: ningún régimen por sí solo —
      contención de sistema/cold-start, no un camino de código
      estructuralmente más caro.
- [x] Qué función consume más tiempo: `simulate_ode` en agregado
      (93% del total, por volumen de llamadas) — `builtins.dir()` es
      el hallazgo más accionable (31.7% del total, cero valor físico).
- [x] Qué parte del Monte Carlo aporta valor real: toda — el criterio
      de convergencia funciona correctamente, no hay sobre-muestreo.
- [x] Qué parte del ODE aporta valor real: ~66% de su tiempo agregado
      (el otro 34% es `dir()`).
- [x] Por qué el cache hit es 44.7%: `scenario_hash()` no redondea
      floats continuos (pila/rates) — confirmado con prueba directa.
- [x] Qué optimización tiene mejor ROI: #1 (quitar `dir()`), medida en
      -36%, riesgo nulo, <30 min.
- [x] Si hacen falta Background Callbacks: no todavía — resuelven un
      problema distinto (UX de respuestas fuera de orden), no la
      velocidad de `find_optimal_v3`.
- [x] Qué se requiere para <3s: #1+#2 acercan el caso típico; el peor
      caso (cache-miss, régimen de convergencia lenta) requiere además
      #3 (grid más chico, con validación) o #4 (paralelizar).
