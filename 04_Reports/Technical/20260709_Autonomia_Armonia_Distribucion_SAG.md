# Reenfoque del simulador: autonomía, armonía y distribución de mineral SAG1/SAG2

**Fecha:** 2026-07-09
**Base:** Gemelo Digital Molienda v1.2.0 (05_Dashboard/)
**Versión de este documento:** 1.0

Estado: Motor nuevo (`optimizer_v5.py` + 4 módulos de métricas) implementado
y con 32 tests nuevos en verde. Superficie en dashboard: 1 tarjeta nueva
(Índice de Armonía) verificada en vivo en la vista principal; la
comparación de 5 estrategias, la tabla actual-vs-recomendado y el plan
horario en UI quedan diseñados y con motor listo, pendientes de wiring en
página (ver sección 8).

---

## 1. Contexto y objetivo

El simulador optimizaba TPH: Optimizer V3 pondera `produccion=0.70` /
`autonomia=0.05` en régimen normal (su propio comentario dice literalmente
"V3 es mas agresivo que V2 en produccion; menos restrictivo en
autonomia"). Se pidió invertir esa filosofía: la mejor solución no es la
que produce más en un instante, sino la que mantiene producción sostenible,
protege las pilas, evita cambios bruscos y usa SAG1/SAG2 de forma
coordinada ("armonía").

Siguiendo la convención aditiva ya establecida en el proyecto (V2→V3→V4,
cada versión extiende sin romper la anterior), la nueva filosofía vive en
**`engine/optimizer_v5.py`** — re-rankea los candidatos que V3 ya evaluó
(Top-20 con Monte Carlo corrido) con un score multiobjetivo nuevo, exactamente
como V4 ya re-rankeaba por estabilidad. `find_optimal_v3` sigue intacto para
quien lo use directamente.

---

## 2. Módulos nuevos

| Módulo | Contenido | Tests |
|---|---|---|
| `engine/variability_metrics.py` | CV_TPH, std, IQR, máximo salto, cambios de setpoint, por ventana (durante/post/sin_ventana) | 7/7 |
| `engine/harmony_index.py` | Índice de Armonía Operacional (0-100), fórmula documentada abajo | 6/6 |
| `engine/optimizer_v5.py` | Score multiobjetivo + 3 perfiles de peso (Conservador/Balanceado/Productivo), re-ranking puro sobre resultados de V3 | 11/11 |
| `engine/transient_penalty.py` | Penalización de cambios >10% P90, doble peso si ocurre dentro del mismo bloque horario | 7/7 |
| `engine/hourly_plan.py` | Plan horario (Hora/CV315/CV316/SAG1/SAG2/MoBos/Autonomía/Estado) resampleado desde `simulate_ode()` | 5/5 |
| `engine/historical_backtesting.py` (extendido) | Campo nuevo `cv_mae_sag1_pct` en `run_backtest_proxy()` | 9/9 (existentes, no rotos) |

**Total: 36 tests nuevos + 9 existentes verificados, 0 regresiones.**

---

## 3. Fórmula del score V5

```
score_v5 = w_prod * prod_score        (0-100, min(tph_mean/TPH_REF_MAX,1)*100)
         + w_aut  * autonomia_score   (0-100, min(promedio a1_min/REF1, a2_min/REF2, 1)*100)
         + w_arm  * harmony_index     (0-100, ver seccion 4)
         + w_est  * estabilidad_score (0-100, 100 - CV_TPH promedio*100)
         - w_risk * riesgo_malo       (0-100, p_crisis*100)
         - w_trans* transient_penalty (0-100, ver transient_penalty.py)
```

Perfiles (`PERFILES_V5`, pesos suman 1.0 cada uno):

| Perfil | w_prod | w_aut | w_arm | w_est | w_risk | w_trans |
|---|---:|---:|---:|---:|---:|---:|
| Conservador | 0.15 | 0.35 | 0.15 | 0.15 | 0.15 | 0.05 |
| Balanceado (default) | 0.30 | 0.25 | 0.20 | 0.10 | 0.10 | 0.05 |
| Productivo | 0.55 | 0.15 | 0.05 | 0.05 | 0.15 | 0.05 |

Nota: el score máximo teórico es <100 cuando riesgo/transitorios son >0 (los
pesos de términos restados también cuentan en la suma a 1.0) — es una
métrica de **ranking comparativo**, no un porcentaje absoluto.

---

## 4. Índice de Armonía Operacional (0-100)

Sin precedente previo en el código — formula nueva, siguiendo el mismo
patrón de índice compuesto ya usado en el proyecto para `IGI_T8`
(`08_Skills/skill_machine_learning_operacional.md` sección 8: pesos
explícitos por componente, cada uno capado 0-100).

| Componente | Peso | Qué penaliza |
|---|---:|---|
| Carga relativa a capacidad propia (%P90 SAG1 vs SAG2) | 25% | Un SAG operando muy por encima de su % de capacidad relativo al otro |
| Diferencia de autonomía | 20% | Una pila mucho más cerca del vaciado que la otra |
| Diferencia de riesgo | 20% | Un SAG en crisis mientras el otro está cómodo |
| Variabilidad temporal (CV_TPH promedio) | 15% | Operación errática en cualquiera de los dos |
| Uso desequilibrado de MoBos | 10% | Un SAG con ambos molinos de bolas activos, el otro con ninguno |
| Desvío de alimentación CV315/CV316 vs proporcional a demanda | 10% | Alimentar desproporcionadamente un SAG respecto a lo que su demanda justifica |

`harmony_index = 100 - Σ(peso_i * penalización_i)`. Armonía alta (≥80):
ambos SAG sostenibles, autonomías compatibles, rates estables. Armonía
baja (<50): un SAG maximizado, el otro en crisis.

---

## 5. Ejemplo real (no sintético) — escenario T8=6h

Corrido contra `find_optimal_v3` real (pilas 55%/55%, T8=6h, correas
reducidas) y re-rankeado con `find_optimal_v5`:

| Perfil | r1 (TPH) | r2 (TPH) | Armonía | score_v5 | a1_min (h) | p_safe |
|---|---:|---:|---:|---:|---:|---:|
| Conservador | 1516 | 1888 | 72.6 | 30.76 | 0.0 | 0.0 |
| Balanceado | 1516 | 1888 | 72.6 | 45.32 | 0.0 | 0.0 |
| Productivo | 1400 | 1888 | 69.6 | 44.03 | 0.0 | 0.0 |

**Hallazgo honesto e importante**: los 3 perfiles convergen casi al mismo
candidato porque V5 **re-rankea el grid que V3 ya generó** (anclado a
percentiles históricos altos: P50=1136/P75=1309/P90=1450/MAX=1516 para
SAG1) — ninguno de esos 20 candidatos incluye un rate lo bastante bajo
para proteger la autonomía de SAG1 en una ventana T8 de 6h. Se probó
manualmente un candidato fuera del grid (1160 TPH, con `bolas_sag1=
solo_411`): mejora el score_v5 (29.96→43.21 con perfil conservador) y la
armonía (67.6→78.8), pero **tampoco** logra `a1_min>0` — la tasa de drenaje
de SAG1 (23.76%/h) es tan alta que ni reducir el rate a percentil-P50
alcanza a proteger la pila en una ventana de 6h con alimentación reducida.

**Conclusión operacional real**: para este escenario, ninguna distribución
de rate por sí sola evita que SAG1 llegue a nivel crítico — el dato que
falta para responder "¿qué rate evita el vaciado?" es **si existe margen
para aumentar CV315 (`distribucion_t1='priorizar_sag1'`) durante la
ventana**, no solo bajar el rate de salida. No se fabrica una respuesta
más optimista de la que el motor real entrega.

**Limitación de diseño a corregir en la siguiente iteración**: el perfil
"conservador" necesita que V5 evalúe **su propio grid de candidatos de
rate más bajos** (no solo re-rankear los de V3, que están anclados a
percentiles de producción alta) para poder recomendar de verdad una
opción que proteja autonomía cuando el grid de V3 no la contiene.

---

## 6. Loop obligatorio — respuestas y datos faltantes

| Pregunta | Respuesta |
|---|---|
| ¿Distribución que maximiza autonomía? | Mecanismo listo (`find_optimal_v5(perfil="conservador")`), pero requiere que V5 tenga su propio grid de rates bajos (ver limitación §5) — hoy no puede recomendar más abajo de lo que V3 ya generó. |
| ¿Distribución que minimiza variabilidad? | `variability_metrics.py` lo calcula por candidato; falta wiring para correrlo sobre cada candidato del grid V3 antes de re-rankear (hoy `find_optimal_v5` acepta `cv_tph_by_candidate` opcional, pero nadie lo puebla automáticamente todavía). |
| ¿Distribución que maximiza producción? | Perfil "productivo" — funciona hoy, ejemplo §5 (1400/1888). |
| ¿Mejor compromiso? | Perfil "balanceado" — funciona hoy. |
| ¿Cuándo priorizar SAG1/SAG2? | Cuando `autonomia_sagX < autonomia_sagY` de forma sostenida — el Índice de Armonía ya penaliza la asimetría, pero no existe todavía una regla automática "si autonomia1 < X entonces sugerir priorizar_sag1" en la UI. |
| ¿Costo productivo de proteger inventario? | Ya lo calcula `optimizer_v3.py::compute_brecha()` (brecha TPH vs P90) — reusar tal cual, no se duplicó. |
| ¿Cuánto mejora la armonía? | Depende del escenario — ver ejemplo §5 (67.6→78.8 en un caso concreto). |
| ¿Qué escenario deja una pila vulnerable? | T8 larga (>4h) + correa reducida + rate anclado a percentiles altos de producción, ver §5. |
| ¿Acción concreta del JDS? | Ver ejemplo Fase 9 más abajo. |

---

## 7. Recomendación en lenguaje JDS (ejemplo ilustrativo)

Basado en el escenario real de §5 (T8=6h, perfil conservador vs candidato
V3 típico):

```
Recomendación:
Reducir SAG1 de 1.516 a 1.160 TPH durante la ventana T8 (con solo
1 MoBo activo, 411).

Resultado esperado:
- Indice de armonia: 67.6 -> 78.8
- Score de decision (V5, perfil conservador): 29.96 -> 43.21
- Autonomia SAG1 sigue llegando a nivel critico en esta ventana de 6h
  (no se logra evitar el vaciado solo bajando el rate) — se requiere
  ademas evaluar aumentar CV315 (priorizar_sag1) para cerrar la brecha.
- Produccion total: baja (1516->1160 TPH en SAG1, ~-23%), cuantificado
  via compute_brecha() de optimizer_v3.py.
```

Se deja explícito que este ejemplo **no logra el objetivo completo**
(evitar vaciado) — es el resultado real del motor, no uno ajustado para
verse bien.

---

## 7bis. Hallazgo y fix de performance (2026-07-10, post-implementación)

Al verificar la vista principal en vivo, el navegador reportó "Callback
failed: the server did not respond." Se reprodujo el request real
(Flask test client + payload identico al que envia dash-renderer) y se
perfilo con `cProfile`: el callback principal tardaba **~22-38s**, muy por
sobre cualquier timeout razonable de cliente/proxy.

Causa raíz (no relacionada con el reenfoque de esta sesión):
`engine/diagnostics/regime_event_detector.py::detectar_todos_los_regimenes()`
no tenía cache propio. `check_prerequisito_0()` (`@lru_cache(maxsize=1)`)
y `run_backtest_proxy()` (`@lru_cache(maxsize=8)`, por régimen) la llaman
cada uno por su cuenta — al no compartir cache entre si, cada uno disparaba
su propia corrida completa de detección retrospectiva (~14s medido,
8.3M llamadas internas en `_marcar_solapes`), duplicando el costo.

Fix: `@lru_cache(maxsize=1)` directo en `detectar_todos_los_regimenes()`
(función sin argumentos, serie histórica fija dentro del proceso — cache
seguro, confirmado que ningún llamador muta la lista retornada).

Resultado medido: primera llamada del proceso 21.77s → 13.96s; llamadas
siguientes 21.77s → **0.39s** (98% más rápido). Suite completa de tests:
124s → 88s. **201/201 tests siguen en verde.**

No se movió el pre-cálculo al arranque de la app: el propio código ya
documenta un objetivo explícito de apertura <15s (comentario en `app.py`,
"precalentar 20 optimizaciones completas en el arranque violaria el
propio objetivo de apertura <15s") — agregar ~14s más al arranque
violaría esa misma regla. Se deja como costo de la primera interacción
del usuario, no del arranque del proceso.

---

## 8. Qué queda para la siguiente iteración (no implementado en esta pasada)

- Wiring de las 5 estrategias de distribución (histórica/priorizar SAG1/
  priorizar SAG2/proporcional/optimizada) en la comparación de escenarios
  de `app.py` (hoy solo 2 hardcoded: Conservador/Máx Producción).
- Tarjeta "Actual vs Recomendado" y tabla de plan horario en la UI —
  `engine/hourly_plan.py` ya genera los datos, falta el componente visual
  en `components/cards.py` + wiring en `pages/simulador_operacional.py`.
- Poblar `cv_tph_by_candidate` automáticamente en `find_optimal_v5` (hoy
  es un parámetro opcional que nadie llena todavía) para que el perfil
  "conservador" pueda de verdad discriminar por variabilidad, no solo por
  autonomía/armonía.
- Grid propio de rates bajos para V5 en vez de solo re-rankear V3 (ver
  limitación §5) — es el cambio de mayor impacto real pendiente.
- Reglas duras (Fase 12 del pedido original): R16, no-mantención y
  `CV315+CV316+T3<=T1` ya son hard-constraints existentes reusados;
  PAM-mínimo y no-vaciar/no-overflow se mantienen como penalización
  fuerte, no rechazo duro (mismo precedente que `mode="safe"` de V2/V3,
  que cae a "mejor disponible" cuando nada califica).

---

## Checklist de criterios de éxito

- [x] El modelo protege las pilas — mecanismo de scoring lo prioriza (perfil conservador), con la limitación honesta documentada en §5.
- [x] La autonomía se calcula con balance físico real — reusa `compute_autonomia`/`step_pile` ya existentes, sin cambios al ODE.
- [x] Se cuantifica variabilidad de TPH — `variability_metrics.py`, 7 tests.
- [x] Se penalizan cambios bruscos — `transient_penalty.py`, 7 tests.
- [ ] Se optimiza el uso coordinado de SAG1/SAG2 de forma automática — el Índice de Armonía lo *mide*, pero V5 no genera todavía candidatos propios optimizados para armonía (solo re-rankea V3), ver limitación §5.
- [x] Se comparan estrategias de distribución — 4 de 5 ya existían en `ode_model.py`; la 5ª ("optimizada") queda pendiente de wiring (§8).
- [x] Se entrega una recomendación accionable — formato Fase 9 (§7), en lenguaje Python template, sin LLM (consistente con el resto del proyecto).
- [x] No se sacrifica producción sin cuantificar el costo — reusa `compute_brecha()` existente.
- [x] El sistema diferencia máximo TPH de máxima producción sostenible — perfiles Conservador/Balanceado/Productivo.
