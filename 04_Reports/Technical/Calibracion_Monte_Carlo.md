# Calibración de Monte Carlo — auditoría de sigmas asumidos

Fecha: 2026-07-15. Ejecuta las secciones 18-19 del programa de
validación estadística pedido sobre los 3 sigmas de incertidumbre que
usa `adaptive_mc_eval` (`05_Dashboard/engine/optimizer_v2.py`,
líneas ~444-447), ya confirmados como "sin fuente citada" en el
diagnóstico de fidelidad histórica (`20260715_Diagnostico_Fidelidad_
Historica.md`, sección 4.1). No modifica código de producción.

**Reproducible:** `02_Analytics/Scripts/statistical_validation/
calibrate_monte_carlo_sigmas.py` → `04_Reports/Technical/
monte_carlo_calibration.csv`.

## Los 3 sigmas actuales (código, sin cambios)

```python
p1  = clip(Normal(pila1,  sigma=2.5), 5, 95)      # pp
p2  = clip(Normal(pila2,  sigma=2.5), 5, 95)      # pp — mismo sigma que SAG1
ff  = clip(Normal(1.0,    sigma=0.12), 0.55, 1.50) # factor multiplicativo sobre CV315/CV316
dt8 = clip(Normal(duracion_t8, sigma=1.0), 0, duracion_t8+3)  # h
```

## Resultado: los 3 sigmas parecen subestimar la incertidumbre real

| Parámetro | Sigma asumido | Proxy empírico (real) | Ratio real/asumido | N |
|---|---:|---:|---:|---:|
| `duracion_t8_h` | 1.0h | std=2.07h (dist. muy asimétrica, skew=5.0) | **2.07x** | 72 eventos |
| `pila_sag1_pct` | 2.5pp | std=2.94pp (cambios 5-min) | **1.18x** | 93.520 |
| `pila_sag2_pct` | 2.5pp | std=0.98pp (cambios 5-min) | **0.39x** | 93.545 |
| `feed_factor` | 0.12 (12%) | CV mediano=0.342 en ventanas de 4h | **2.85x** | 80.754 |

**Importante — advertencia metodológica explícita antes de leer la
tabla:** ninguno de estos 3 proxies mide *exactamente* la misma
cantidad estadística que el sigma del código (que representa
incertidumbre sobre la **condición inicial/nivel asumido** de un
escenario, no volatilidad continua). Son las mejores aproximaciones
disponibles con los datos existentes — se documentan como evidencia
direccional fuerte, no como reemplazo directo y automático del valor
en producción.

### 1. Duración de T8 (ratio 2.07x — subestimación clara)

`duracion_h` (columna del dataset oficial) es la clasificación
"bucket" del evento (2h/4h/8h/12h — los mismos valores que ofrece el
selector del simulador); `horas_t8_raw` es la duración real observada.
La diferencia (`raw - bucket`) es el mejor proxy disponible de "cuánto
puede desviarse la duración real de lo que el usuario declaró/asumió".

- **Media**: +0.53h (sesgo hacia ventanas más largas de lo declarado).
- **Std**: 2.07h — más del doble del sigma asumido (1.0h).
- **Skew=5.0**: distribución **muy asimétrica**, no gaussiana — la
  mayoría de eventos coincide con su bucket (mediana del diff = 0),
  pero hay una cola larga de eventos que se extienden mucho más
  (máximo +12h). Un `Normal(duracion_t8, 1.0)` truncado **no captura
  esta cola** — subestima tanto la dispersión total como,
  específicamente, el riesgo de eventos anormalmente largos (que son
  justamente el escenario operacionalmente más peligroso).
- **Recomendación de forma de distribución** (sección 18 del prompt):
  no usar Normal — mejor candidato es una mixtura (masa puntual cerca
  de 0 + cola exponencial/gamma para la extensión) o, más simple y sin
  fabricar una familia paramétrica sin evidencia adicional, **bootstrap
  empírico** directo sobre los 72 diffs observados.

### 2. Pila SAG1/SAG2 (resultado divergente por activo — hallazgo nuevo)

El código usa el **mismo sigma=2.5pp para ambos SAG**, pero el proxy de
volatilidad de corto plazo (dispersión de cambios pila a pila cada 5
min) muestra una asimetría real:

- **SAG1**: std=2.94pp por paso de 5 min — 18% más que el sigma
  asumido. Consistente con que SAG1 es el activo estructuralmente más
  sensible (`CAP_TON["SAG1"]=4575t`, drenaje 23.76%/h — ya documentado
  en `rules_engine.py`).
- **SAG2**: std=0.98pp por paso de 5 min — **61% menos** que el sigma
  asumido (`CAP_TON["SAG2"]=32009t`, mucho más inercia).
- **Implicación**: usar un sigma compartido de 2.5pp probablemente
  **sobrestima la incertidumbre de SAG2 y subestima la de SAG1** — el
  Monte Carlo hoy trata a ambos circuitos como igualmente inciertos
  cuando la evidencia dice que no lo son. Esto es coherente con el
  hallazgo ya confirmado en la regresión (`Validacion_Modelos_
  Regresion.md`): `asset=SAG2` tiene un efecto propio significativo
  sobre el error de fidelidad, controlando por lo demás.

### 3. Factor de alimentación (ratio 2.85x — subestimación clara)

El sigma=0.12 (±12%) se aplica como un factor multiplicativo único por
escenario sobre CV315/CV316. El proxy más comparable disponible —
coeficiente de variación de la alimentación real dentro de ventanas
móviles de 4h (mismo horizonte típico de un escenario simulado) — da
CV mediano=0.342, **casi 3 veces mayor**. Esto **refina** (no
contradice) la nota direccional ya documentada en el diagnóstico de
fidelidad ("CV real de producción diaria SAG1=0.44/SAG2=0.31 es 3-4x
mayor que ±12%, pero no directamente comparable por escalas de
tiempo distintas") — aquí se midió al **mismo horizonte temporal**
que usa el propio Monte Carlo (4h), y el ratio (2.85x) es del mismo
orden de magnitud que la comparación direccional anterior. La señal es
consistente en dos mediciones independientes.

## Lo que esto NO significa (sin sobreinterpretar)

- **No implica que `p_safe` esté mal calibrado en la dirección
  esperada** (la sección 19 del prompt pide comparar probabilidad
  predicha vs. frecuencia observada — **no se ejecutó esta pasada**,
  requiere correr Monte Carlo retrospectivamente sobre escenarios
  históricos reales y comparar contra el desenlace real, un trabajo de
  mayor alcance que esta auditoría de sigmas). Sigmas más angostos que
  la realidad generalmente **subestiman el riesgo** (`p_safe` optimista)
  porque el MC explora un rango de escenarios más angosto del real,
  pero esto es una hipótesis razonable, no un resultado medido.
- **No se recalibran los sigmas en esta pasada** — mismo criterio
  aplicado a `DRAIN_PCT_H`/`_pile_feedback_factor`: no cambiar un
  parámetro de producción sin (a) confirmar el efecto en la validación
  de calibración real (`p_safe` vs. frecuencia observada) y (b) que
  el cambio no empeore el hold-out, tal como se hizo con `DRAIN_PCT_H`.

## Validación de calibración real de `p_safe` (sección 19, ejecutada en esta misma pasada)

**Método:** para los 63 eventos reales `t8_corta`, se simuló con el
mismo modelo de ruido de `adaptive_mc_eval` (pila±2.5pp, feed
`Normal(1,0.12)`, T8±1h, N=150 muestras/evento) usando
`simulate_scenario_cached` directamente — no se reutilizó
`adaptive_mc_eval` porque requiere una config de bolas por candidato
que no existe en los datos históricos (fabricarla habría confundido el
resultado). `p_safe` = fracción de muestras donde `pile_sag1` nunca
baja del umbral crítico (15%). Se comparó contra si el evento real
**realmente** cruzó ese umbral, leído directamente de la serie 5-min
observada (`periodo` DURANTE+POST).

**Primer intento (descartado, documentado por transparencia, no
oculto):** usando `rate_sag1_pct=100%` fijo (literal como hace
`adaptive_mc_eval` en producción) sobre el feed **ya restringido**
observado durante el evento real, el modelo predijo `p_safe≈0.08` para
62/63 eventos (Brier=0.76, peor que adivinar 0.5 siempre) — pero en la
realidad 87-95% de esos eventos SÍ fueron seguros. Se investigó la
causa: al forzar el motor a apuntar al 100% del rate nominal (1454 TPH)
contra un feed ya reducido por el T8 real, el balance neto simulado es
masivamente negativo en casi todas las muestras — **no es necesariamente
un error del código en su uso de producción** (ahí `cv315_nom` viene de
un candidato del grid, no de un promedio histórico crudo), pero sí
invalida esta forma de probar la calibración: mezclar "feed ya reducido
por el operador real" con "rate objetivo sin reducir" no representa
ningún escenario real.

**Segundo intento (metodología corregida):** se reemplazó el 100% fijo
por el rate **efectivamente observado** (`tph1_mean/P90×100`, mismo
criterio que usa `historical_backtesting.py::_run_backtest_t8` para
fidelidad física) — es decir, replicar la reducción de rate que el
operador real ya aplicó, no solo el feed restringido.

| Split | N | `p_safe` medio predicho | Frecuencia real segura | Brier score |
|---|---:|---:|---:|---:|
| Calibración | 44 | 0.728 | 0.841 | **0.180** (mejor que el baseline ingenuo 0.25) |
| Hold-out | 19 | 0.248 | 0.947 | **0.621** (mucho peor que el baseline ingenuo) |
| **Global** | 63 | — | — | 0.313 |

**Reliability (predicho vs. observado, todos los eventos):**

| `p_safe` predicho | N | Predicho medio | Frecuencia real |
|---|---:|---:|---:|
| <0.50 | 27 | 0.115 | **0.815** |
| 0.50-0.70 | 3 | 0.602 | 0.667 |
| 0.70-0.85 | 1 | 0.780 | 1.000 |
| 0.85-0.95 | 8 | 0.884 | 0.875 |
| ≥0.95 | 24 | 1.000 | 0.958 |

**Hallazgo principal — triangula exactamente con `Validacion_Modelos_
Regresion.md` sección 4:** en calibración, `p_safe` está razonablemente
bien calibrado (Brier 0.18, mejor que el baseline). En hold-out, el
modelo predice sistemáticamente **mucho más riesgo del que realmente
se materializa** (`p_safe` medio 0.248 vs. frecuencia real 0.947) — la
misma deriva temporal sistémica ya encontrada con la regresión del
error de pila (100% de cruces de breakpoint en hold-out vs. 54.5% en
calibración) se traduce directamente en una probabilidad de seguridad
mal calibrada en el período más reciente. **Esta es ahora la tercera
línea de evidencia independiente** (backtesting de fidelidad, regresión
del error, calibración de `p_safe`) que apunta al mismo fenómeno: algo
cambió estructuralmente entre el período de calibración
(2026-01 a 2026-04-30) y el hold-out (2026-05 a 2026-06-25) que ningún
modelo probado hoy explica.

**No se recalibran los sigmas ni el motor en esta pasada** — el
patrón de deriva temporal es más urgente y de mayor impacto que ajustar
sigmas, y cualquier recalibración hecha sobre datos de calibración
sin resolver la deriva se repetiría el mismo problema que ya se
descartó con `DRAIN_PCT_H` (mejora en calibración, sin mejora real en
hold-out).

## Próximos pasos concretos (no ejecutados esta pasada)

1. **Máxima prioridad**: investigar la causa de la deriva temporal
   sistémica (ver `Validacion_Modelos_Regresion.md`, sección 4, y esta
   sección) antes de seguir iterando sigmas, parámetros o modelos — es
   la causa raíz que explica tanto el error de fidelidad como la mala
   calibración de `p_safe` en el período reciente.
2. Repetir esta validación de `p_safe` para los 4 regímenes proxy
   (requiere definir un umbral de "seguro" apropiado para cada uno, no
   solo el cruce del nivel crítico usado aquí para `t8_corta`).
3. Separar el sigma de pila por activo (`SAG1`≠`SAG2`) — solo si la
   deriva temporal se resuelve primero, para no confundir dos causas.
4. Evaluar una distribución no-gaussiana para `duracion_t8_h` (mixtura
   o bootstrap empírico) en vez de ampliar ciegamente el sigma actual.
