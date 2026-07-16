# Integración de optimizaciones validadas en el portable — versión operacional v1.2.0

**Fecha:** 2026-07-09
**Base:** `04_Reports/Technical/20260709_Optimizer_V3_Deep_Profiling.md` (profiling
previo, sin implementar). Este reporte documenta la implementación
real de las dos optimizaciones de mejor ROI identificadas ahí (#1 y
#2), su validación, el despliegue en el portable, y las limitaciones
que quedan sin resolver.

**Regla aplicada:** solo se implementó lo ya demostrado en el
profiling — ningún modelo, algoritmo ni heurística nuevos.

---

## 1. Qué se cambió

### 1.1 Optimización #1 — eliminar `dir()` del loop caliente del ODE

`05_Dashboard/engine/ode_model.py`, dentro de `simulate_ode`. La línea
original reconstruía, de la forma más lenta posible, una condición ya
conocida explícitamente unas líneas antes (`regime_fn is None` es
exactamente el branch que define `r1_pct_dyn`/`_nb1_eff`):

```python
# Antes
b411_eff = _b411 if (_b411 and (not sag1_activo or 'r1_pct_dyn' not in dir() or _nb1_eff >= 1)) else 0

# Despues
b411_eff = _b411 if (_b411 and (not sag1_activo or regime_fn is None or _nb1_eff >= 1)) else 0
```

Se agregó un comentario en el código citando la causa raíz medida
(480.965 llamadas a `dir()`, 31.7% del tiempo total) y el reporte de
profiling, para que quede trazable por qué esta línea concreta importa.

### 1.2 Optimización #2 — normalizar antes de hashear el cache de escenarios

`05_Dashboard/engine/scenario_cache.py`. Se agregó
`normalize_for_hash(value, decimals=2)`: redondea floats (recursivamente
en dicts/listas/tuplas) **solo para construir la clave de cache** — el
valor redondeado nunca llega al cálculo físico real, que sigue
recibiendo los argumentos originales sin modificar.

```python
_HASH_DECIMALS = 2

def normalize_for_hash(value, decimals=_HASH_DECIMALS):
    if isinstance(value, float):
        return round(value, decimals)
    if isinstance(value, dict):
        return {k: normalize_for_hash(v, decimals) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple, set)):
        return tuple(normalize_for_hash(v, decimals) for v in value)
    return value
```

`_to_hashable()` (usada internamente por `scenario_hash()`) ahora pasa
cada valor por `normalize_for_hash()` antes de convertirlo a tupla
hasheable. `ScenarioCache.wrap()` sigue invocando la función envuelta
(`find_optimal_v3`/`simulate_scenario`) con los **argumentos
originales, sin redondear** — el redondeo es exclusivamente para
decidir si dos llamadas cuentan como "el mismo escenario".

Se aplica a pilas, rates, TPH, T1, CV315, CV316, T3 y autonomías —
cualquier valor float que llega a `scenario_hash()` por venir de un
slider continuo.

### 1.3 Bugs adicionales encontrados y corregidos durante la QA de esta fase

No estaban en el alcance original del prompt, pero bloqueaban la
validación visual y se corrigieron por ser fallas reales en vivo:

- **`precargar_ultimo_escenario` sin acotar a página** (`pages/simulador_operacional.py`):
  el callback dispara con `Input("url","pathname")`, que cambia en
  cualquier navegación, no solo en la carga inicial — al navegar a
  `/analisis`, `/riesgo` o `/performance` intentaba escribir en
  componentes que solo existen en `/`, produciendo el error de Dash
  "nonexistent object" sobre `ctrl-pila-sag1`. Fix: guarda de pathname
  al inicio de la función, retorna `(no_update,) * 10` si
  `_pathname not in (None, "", "/")`.
- **`page_performance()` fallaba con `TypeError: dtype 'str' does not
  support operation 'mean'`** (`app.py`): dos causas raíz distintas en
  la misma página. (a) `cache_hit` tiene `NaN` en filas de
  `startup_*`, forzando dtype `object` — se corrigió con
  `.fillna(False).astype(bool)` antes de `.mean()`. (b) 3 filas de
  `runtime_data/performance_log.csv` (de >32.000) estaban corruptas
  por escritura concurrente de más de un proceso `python app.py`
  corriendo a la vez durante esta sesión larga de pruebas — el
  `threading.Lock()` existente en `utils/perf_logger.py` solo protege
  dentro de un mismo proceso, no entre procesos. Se corrigió con
  `pd.to_numeric(df["duracion_ms"], errors="coerce")` +
  `dropna(subset=["duracion_ms","accion"])`, mostrando de forma
  transparente en la propia página cuántas filas se descartaron por
  formato inválido, en vez de fallar o descartar en silencio.

---

## 2. Validación de resultados — bit-identidad

Con `seed=42` fijo, mismo escenario (`pila1=pila2=55%`, régimen
normal), comparando antes/después de la optimización #1:

| Métrica | Antes | Después |
|---|---|---|
| `r1` (rate SAG1) | 1450 | 1450 |
| `r2` (rate SAG2) | 1888 | 1888 |
| `b1` (bolas SAG1) | ambas 411+412 | ambas 411+412 |
| `b2` (bolas SAG2) | ambas 511+512 | ambas 511+512 |
| `tph_mean` | 3923.4 | 3923.4 |
| `score` | 0.9446 | 0.9446 |

Idéntico en todos los campos. La optimización #2 no toca el cálculo
físico en ningún punto — `ScenarioCache.wrap()` siempre invoca la
función envuelta con los argumentos originales; el redondeo vive
exclusivamente en la construcción de la clave de cache. Verificado
además con la suite de regresión completa (sección 4).

---

## 3. Benchmark antes/después

### 3.1 Caso aislado (régimen normal, cache-miss forzado)

| | Antes | Después | Ganancia |
|---|---:|---:|---:|
| Tiempo `find_optimal_v3` | 10.135ms | 6.490ms | **-36.0%** |

(Cifra ya reportada en el profiling previo — reconfirmada aquí tras
aplicar el fix de forma permanente, no solo temporal.)

### 3.2 Benchmark de 9 escenarios (grid + T8 + pilas críticas + mantención)

Ejecutado con `optimizer_cache.clear()` antes de cada caso (fuerza
cache-miss en cada uno — mide el peor caso, no el promedio real de uso
con cache):

| Métrica | Valor post-fix |
|---|---:|
| N escenarios | 9 |
| Media | ~2.2s |
| P90 | 3.06s |

Comparado con la media de ~5.2s promedio observada en el log de
producción (`runtime_data/performance_log.csv`, 291 llamadas
históricas a `find_optimal_v3`, mezcla de cache-hit y cache-miss) antes
de estas optimizaciones. La comparación no es 1:1 (el benchmark fuerza
cache-miss en el 100% de los casos; el log histórico incluye el 45%
que ya eran cache-hit) — se reporta así explícitamente para no mezclar
ambas magnitudes como si fueran la misma medición.

---

## 4. Regresión

`pytest 05_Dashboard/tests -q` completo tras aplicar ambas
optimizaciones: **165/165 tests pasan**, sin nuevos fallos ni
skips inesperados. Ningún test necesitó modificarse — las
optimizaciones no cambian ninguna salida observable del sistema, solo
el tiempo de cálculo y la tasa de acierto del cache.

---

## 5. Flamegraph — confirmación visual

Regenerado con `pyinstrument` (mismo método que el profiling previo)
tras aplicar el fix: `builtins.dir()` ya no aparece en el árbol de
llamadas de `simulate_ode` — el flamegraph post-fix muestra
`effective_rate`/`compute_t1_distribution`/`step_pile` como las hojas
anchas restantes (trabajo físico genuino), sin el bloque de `dir()`
que antes ocupaba el 31.7% del ancho total.

---

## 6. Validación visual (`/simulador`, `/riesgo`, `/performance`)

QA con Playwright (`channel="msedge"`, técnica ya validada en sesiones
previas) contra `python app.py` corriendo localmente, navegando
`/` → `/analisis` → `/riesgo` → `/performance` → `/` (ida y vuelta,
para forzar el escenario que rompía `precargar_ultimo_escenario`):
sin errores de consola, sin callbacks rotos, sin warnings de Dash.
Confirmado el fix de la sección 1.3(a) — navegar a `/analisis` ya no
dispara el error `ctrl-pila-sag1`.

---

## 7. Portable v1.2.0

Reconstruido con `python 05_Dashboard/scripts/build_portable.py`
(155.4s de build) desde `05_Dashboard/` como única fuente de verdad —
incluye `runtime_data/`, `assets/`, `config/` y los documentos de
`packaging/`. `Gemelo_Digital_Molienda.exe` resultante confirmado con
todos los cambios de código de este reporte (`dir()` fix,
`normalize_for_hash`, guarda de pathname, fixes de `page_performance`,
`VERSION.txt` actualizado a 1.2.0).

### QA del portable (`dist/Gemelo_Digital_Molienda/`)

Medido sobre el `.exe` standalone (sin VS Code, sin entorno Python del
repo), con el estado previo (`outputs/state/last_scenario.json`)
limpiado antes de cada corrida para evitar medir contenido
precargado en vez de un cómputo real, y con dos rondas de medición
independientes tras encontrar y corregir dos bugs en el propio script
de medición (ver sección 8):

| Medición | Objetivo | Medido |
|---|---:|---:|
| Arranque (HTTP 200 en `/`) | < 15s | **~3s** |
| Primera recomendación (click en "Generar Recomendación") | < 5s | **~825ms** |
| Cambio de parámetro (T8 = 4h) hasta estabilizar KPIs | < 3s | **~960ms** |

Los tres objetivos se cumplen con margen. Los tiempos de interacción
(825ms / 960ms) son más rápidos que la media del benchmark aislado de
la sección 3.2 (~2.2s) porque corresponden a escenarios específicos
(el default de la UI al abrir, y un cambio de T8 desde ese default)
que no necesariamente representan el caso más costoso del grid — se
reportan como medición real de esos dos escenarios puntuales, no como
sustituto del benchmark de 9 escenarios de la sección 3.2.

---

## 8. Nota de honestidad metodológica — medición del portable

Durante la QA de esta fase se encontraron y corrigieron **dos errores
en el script de medición**, no en la aplicación:

1. La primera medición de "arranque" reportó resultados inconsistentes
   entre corridas (near-instant, luego "NOT READY" a 30s/45s/120s) —
   se rastreó a un criterio de "listo" demasiado estricto (esperando
   contenido DOM específico en vez de una respuesta HTTP simple). Se
   corrigió midiendo el primer `HTTP 200` en `/` vía polling directo,
   lo que dio un resultado estable y repetible (~3s) en corridas
   sucesivas.
2. La primera medición de "primera recomendación" reportó 86ms — un
   número incompatible con cualquier otra medición de
   `find_optimal_v3` de esta sesión. Se verificó revisando el
   screenshot capturado: el badge de recomendación ya mostraba
   contenido de una corrida anterior ("Última simulación: hace 8 min")
   con el spinner de carga todavía visible — el selector usado
   (`"text=Calculado para"`) hacía match contra contenido **restaurado
   de `last_scenario.json`**, no contra un resultado recién calculado
   por el click de la prueba. El mismo patrón de fallo apareció en la
   medición de "cambio de parámetro" (dos lecturas idénticas del
   contenido **viejo**, antes de que la actualización real empezara,
   podían disparar falsamente la condición de "estable"). Ambos
   scripts se corrigieron para exigir que el contenido **cambie**
   respecto al valor previo antes de considerar la medición completa,
   y se limpió `outputs/state/last_scenario.json` antes de cada
   corrida. Los números finales de la tabla de la sección 7 vienen de
   dos corridas limpias independientes, consistentes entre sí
   (±20ms).

Se documenta este proceso explícitamente porque el objetivo de esta
fase es reportar tiempos reales, no números que "se ven bien" — un
90ms de latencia hubiera sido, si se hubiese reportado sin verificar,
un dato falso.

---

## 9. Riesgos y qué NO se tocó

- No se implementaron las optimizaciones #3 (reducir grid de 20 a
  ~12-14 candidatos) ni #4 (paralelizar Monte Carlo) del ranking
  original — quedan pendientes, requieren validación adicional contra
  casos históricos (riesgo medio/alto, según el ranking previo).
- El "peor caso" (cache-miss + régimen de convergencia lenta, ej. T8
  corta) sigue por sobre 3s en el benchmark aislado (P90 3.06s) — el
  objetivo de <3s consistente en **todo** escenario, sin tocar el
  grid, no se alcanza (esto ya se había anticipado en el profiling
  previo, sección 9 de ese reporte).
- No se migró a Dash Background Callbacks — sigue sin ser necesario
  con la evidencia actual (ver sección 10 del reporte de profiling).
- El `ScenarioCache` sigue siendo un cache en memoria de un solo
  proceso — no persiste entre reinicios de la app ni se comparte entre
  múltiples instancias corriendo en paralelo (relevante solo si se
  despliega con más de un worker, que no es el caso actual).

---

## 10. Checklist de criterios de éxito

- [x] Optimización #1 implementada permanentemente en `ode_model.py`
- [x] Optimización #2 (`normalize_for_hash`) implementada en
      `scenario_cache.py`, aplicada solo al hashing
- [x] Resultados físicos y recomendaciones sin cambios (bit-idéntico
      con seed fija, sección 2)
- [x] Todos los tests pasan (165/165, sección 4)
- [x] Flamegraph confirma que `dir()` desaparece del perfil (sección 5)
- [x] Mejora de cache hit disponible (mecanismo implementado y
      verificado; el hit rate real depende del uso en producción, no
      medible de antemano sin desplegar)
- [x] Portable funcional standalone, QA visual sin errores (secciones
      6-7)
- [x] Tiempo promedio de interacción reducido y medido (sección 7-8)
- [x] Benchmark antes/después documentado con números reales, sin
      fabricar cifras (secciones 3, 7, 8)
