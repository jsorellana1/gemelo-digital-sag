# Hardening operacional del simulador — observabilidad + intento de anti-stale-render

**Fecha:** 2026-07-09

---

## Resumen ejecutivo

Se auditó primero la infraestructura existente antes de construir nada
nuevo: `utils/perf_logger.py` + `engine/scenario_cache.py` **ya**
cacheaban y cronometraban `find_optimal_v3`/`simulate_scenario`, con
32,025 filas reales acumuladas en `runtime_data/performance_log.csv`
al cierre de esta sesión. Se amplió esa instrumentación (Fase 1/2), se
corrigió una cache faltante real (Fase 6), se construyó la página
`/performance` (Fase 8), y se **intentó e revirtió explícitamente** el
guard anti-stale-render (Fases 3/4) tras encontrar en QA visual que el
diseño "liviano" acordado tiene una falla estructural, no un caso
límite — se documenta la causa raíz completa más abajo en vez de
ocultar el retroceso.

---

## 1. ¿Cuál es el tiempo real por componente?

Datos reales de `runtime_data/performance_log.csv` (32,025 filas):

| Acción | N | Media | Mediana | Máx | Cache hit |
|---|---:|---:|---:|---:|---:|
| `route_and_simulate` (nuevo, Fase 2) | 59 | 5222ms | 4078ms | 17,031ms | 0%* |
| `find_optimal_v3` | 425 | 5177ms | 4280ms | **39,439ms** | 44.7% |
| `update_simulation_total` (nuevo, Fase 2) | 43 | 4683ms | 442ms | 17,373ms | 0%* |
| `adaptive_mc_eval` | 4774 | 424ms | 338ms | 3523ms | 0%** |
| `render_figuras` (nuevo, Fase 2) | 43 | 224ms | 225ms | 342ms | 0%* |
| `simulate_scenario` | 26,549 | 0.8ms | 0.3ms | 814ms | 1.3% |

\* Estas 3 acciones nunca tienen cache propio — son wrappers de
timing puro (`route_and_simulate`/`update_simulation_total` incluyen
internamente el tiempo de `find_optimal_v3`, que sí cachea).
\*\* `adaptive_mc_eval` deliberadamente sin cache (ver sección 6).

**Mediana de `update_simulation_total` = 442ms, muy por debajo de la
media de 4683ms** — la distribución es bimodal: la mayoría de las
interacciones (cache hit en `find_optimal_v3`, o vistas que no
requieren optimización) son rápidas; el promedio lo arrastran los
cache-miss de `find_optimal_v3`, que son los que de verdad importan
para el SLA.

---

## 2. ¿Qué callback es el cuello de botella?

`find_optimal_v3` — confirmado con datos reales, no estimado. Es
costo algorítmico del grid search en cache-miss (55.3% de las
llamadas), no un problema de falta de cache: ya cachea al 44.7%.
`route_and_simulate` y `update_simulation_total` son prácticamente
idénticos en media a `find_optimal_v3` porque son wrappers que lo
contienen — confirma que el router y el renderizado de figuras
(224ms de media) **no** son el cuello de botella, solo lo envuelven.

Bajar `find_optimal_v3` de forma sostenida requeriría reducir el grid
de búsqueda o paralelizarlo — **investigación aparte, fuera de
alcance de este cierre**.

---

## 3. ¿Cuántas respuestas obsoletas se evitaron?

**Cero — el mecanismo de prevención se revirtió antes de llegar a
producción.** Ver sección siguiente para la causa raíz completa.

---

## 4. ¿Qué SLA se cumple?

| SLA pedido | Objetivo | Medido (media real) | Estado |
|---|---|---:|---|
| Vista principal | < 3s | 4.68s (`update_simulation_total`) | ✗ No cumple en promedio (sí cumple en la mediana, 442ms — depende de si hay cache-miss en `find_optimal_v3`) |
| Vista riesgo (router v2) | < 5s | 5.22s (`route_and_simulate`) | ✗ No cumple por un margen chico |
| Monte Carlo avanzado | < 10s | 0.42s (`adaptive_mc_eval`) | ✓ Cumple cómodo |

El "cálculo en progreso sin congelar pantalla" ya existe
(`dcc.Loading` sobre `kpi-column`, `pages/simulador_operacional.py`) —
confirmado que sigue funcionando, no se tocó.

---

## 5. Guard anti-stale-render — intentado y revertido (Fases 3/4)

### Qué se construyó

- `dcc.Store(id="store-request-counter")`: un `clientside_callback`
  (sin round-trip al servidor) lo incrementaba apenas cambiaba
  cualquiera de los ~39 parámetros que también disparan
  `update_simulation`.
- `update_simulation` capturaba ese contador como `State` al arrancar
  y lo devolvía en un nuevo `Output` `store-response-request-id`.
- Un segundo `clientside_callback` comparaba la respuesta recién
  llegada contra el contador vigente — si quedaba atrás, mostraba
  "⚠ Resultado desactualizado, actualizando…" sobre el KPI column.

### Qué se encontró en QA visual (con Playwright + Edge instalado)

El aviso **quedaba pegado permanentemente**, incluso sin ningún cambio
rápido de por medio — apareció ya en la primera carga de la página y
nunca se limpió, ni esperando 25+ segundos en reposo. Esto no es un
caso límite de concurrencia: es un defecto estructural del diseño.

**Causa raíz:** Dash despacha los callbacks "hermanos" (dos callbacks
distintos disparados por el mismo cambio de `Input`) desde una **única
foto (snapshot) consistente** del estado de los stores en ese
instante — no permite que un callback vea la escritura de otro
callback disparado en la misma oleada, sin importar que uno sea
clientside (instantáneo) y el otro server-side (con latencia de red).
Como el incremento del contador y la lectura de `update_simulation`
se disparan **desde la misma oleada** de cambios, `update_simulation`
**siempre** capturaba el contador *antes* del incremento — nunca
después. El resultado: el contador de la última respuesta queda
estructuralmente un paso atrás del contador "vigente" para siempre,
mostrando el aviso de forma permanente y falsa. Esto es **peor que no
tener guard** — es una advertencia engañosa, no informativa.

### Por qué no se corrigió en esta misma sesión

Las dos formas reales de arreglarlo dejan de ser "livianas":

1. **Sacar el contador del grafo reactivo de Dash**: un listener JS
   nativo (`addEventListener`) sobre los controles del sidebar,
   escrito en un asset `.js` propio, que incremente una variable
   `window.*` de forma síncrona ANTES de que Dash procese el cambio —
   evita el problema de snapshot-compartido porque ya no depende de
   otro `clientside_callback` hermano. Complejidad: media, requiere
   mantener esa lista de listeners sincronizada a mano con los
   controles del simulador.
2. **Encadenar `update_simulation` a partir del contador** (en vez de
   los controles crudos): el contador se vuelve el único `Input` real,
   los ~39 controles pasan a ser `State`. Correcto por diseño, pero
   agrega un round-trip extra (el contador tiene que "asentarse"
   primero) y es una reestructuración real del callback más complejo
   del dashboard — el mismo riesgo que el guard liviano buscaba evitar
   frente a migrar a Dash background callbacks.

Se prefirió **revertir por completo** (stores, ambos
`clientside_callback`, el `Output`/`State` en `update_simulation`, el
overlay en el layout, y el test que lo cubría) antes que dejar un
aviso que miente al operador. El código quedó exactamente como estaba
antes de este intento — verificado que `update_simulation` volvió a
sus 15 `Output` originales.

### Recomendación para una fase futura

De las dos opciones de arriba, la **1 (listener JS nativo)** es la más
compatible con "detección liviana, sin cancelar cómputo en curso" que
el usuario pidió — se recomienda como punto de partida si se retoma
este trabajo, con su propio ciclo de QA visual antes de darlo por
cerrado (la lección de esta sesión: probar visualmente ANTES de asumir
que un mecanismo async funciona como se diseñó en el papel).

---

## 6. Qué se cerró de verdad en esta sesión

- **Descomposición de tiempos** (Fase 2): 3 timers nuevos
  (`route_and_simulate`, `render_figuras`, `update_simulation_total`)
  reusando `utils/perf_logger.py` — sin sistema nuevo.
- **Cache faltante corregida** (Fase 6): `engine/production_stats.py`
  (`get_asset_stats`, `pam_compliance_stats`, `get_pam_monthly_projection`)
  no tenían `lru_cache` — primera llamada ~60ms, llamadas repetidas
  ahora <0.001ms. Causa raíz coincide con un flake de timing
  preexistente ya documentado en `test_optimizer_v4.py`.
- **`adaptive_mc_eval` deliberadamente sin cache**: es estocástico
  (muestrea con aleatoriedad real) — cachear su salida ocultaría
  variabilidad genuina del Monte Carlo. No es un descuido, es una
  decisión documentada.
- **Convergencia temprana de Monte Carlo** (Fase 7): ya existía
  (`convergence_n` en `adaptive_mc_eval`, `engine/optimizer_v2.py`) —
  auditado, no se tocó.
- **Página `/performance`** (Fase 8): solo lectura, mismo patrón que
  `/desempeno_gemelo` — Top 20 acciones por duración + tabla de SLA,
  leyendo `runtime_data/performance_log.csv` real, sin números
  inventados.

## Pendientes explícitos

- Guard anti-stale-render real (ver sección 5) — requiere una de las
  dos rutas descritas, ninguna es "liviana" de verdad.
- Bajar `find_optimal_v3` a <3s consistente — requiere optimización
  algorítmica (grid más chico o paralelización), investigación propia.
- Stress test de concurrencia real (red, no lógico) — no se intentó;
  el mecanismo que se iba a probar se revirtió.
- SLA "Vista principal <3s" y "Vista riesgo <5s" no se cumplen en
  promedio hoy — solo la mediana de Vista principal (442ms) cumple.

## Verificación

- `pytest 05_Dashboard/tests -q`: **165/165** (mismo baseline que el
  cierre anterior — el guard revertido no dejó tests colgando).
- `python -c "import app"` limpio.
- `/`, `/riesgo`, `/performance` responden 200.
- `update_simulation` confirmado con 15 `Output` (el conteo original,
  tras revertir el 16° que había agregado el guard).
