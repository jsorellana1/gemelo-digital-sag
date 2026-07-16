# Skill: Forecasting Industrial — Modelos Probabilísticos para Seguridad Operacional

## Propósito

Guiar el diseño, calibración e interpretación de modelos de forecasting de riesgo en contextos
industriales y mineros, específicamente aplicado al pipeline FRAG SAG (Frecuencia de Accidentes
de Riesgo en planta de chancado y molienda SAG).

---

# Principios

## Regla 1 — Intervalo de credibilidad, no punto único

En minería, un pronóstico puntual ("FRAG = 23.4%") es menos útil que un intervalo creíble
("FRAG 80%: [14%, 45%]"). El IC comunica incertidumbre y evita falsa precisión.

## Regla 2 — El modelo Poisson-Bayes es correcto, no el más sofisticado

Para eventos raros con historial corto (< 20 semanas), el modelo Poisson con prior Beta
es estadísticamente correcto. LLMs, redes neuronales o Hawkes sin datos suficientes
producen overfitting.

## Regla 3 — No confundir riesgo con probabilidad

FRAG = P(al menos 1 AT con RC en la semana)
Esto NO significa que habrá exactamente 1 accidente.
Es la probabilidad de que el nivel de exposición al riesgo materialice un evento.

## Regla 4 — El modelo necesita al menos 4 semanas para ser confiable

Con < 4 semanas de historia:
- El prior domina completamente
- El IC 80% puede ser [0%, 95%] → no informativo
- Comunicar explícitamente esta limitación en el reporte

## Regla 5 — Validación por backtesting, no solo por métricas de entrenamiento

El modelo FRAG se valida si en semanas históricas con FRAG alto hubo más eventos AT.
Esta validación requiere >= 26 semanas de historial (MP-6 del roadmap).

---

# Modelo FRAG SAG — Detalle Técnico

## Arquitectura probabilística

```
FRAG = 1 - prod( 1 - FRA_RC(k) )   para k en RC activos

FRA_RC(k) = 1 - exp( -lambda_total(k) )

lambda_total(k) = lambda_at(k) + alpha_hal * lambda_hal(k)
               = (n_at_k / rolling_weeks) + 0.15 * (n_hal_k / rolling_hal_weeks)
```

Código: `src/models/rc_scorer.compute_scoring()`

## Prior bayesiano

```python
# Prior Beta(alpha, beta) sobre lambda AT por RC
# alpha = prior_events (default 0.3)
# Se actualiza con datos observados via conjugación Beta-Poisson
posterior_alpha = prior_events + n_at_k
posterior_beta  = rolling_weeks
lambda_at_k     = posterior_alpha / (posterior_beta + prior_events)
```

Prior débil (0.3) → datos dominan rápidamente con >= 5 eventos observados.

## Intervalo de credibilidad (IC 80%)

Implementado via Monte Carlo:
```python
# Muestreo MC de lambda AT para cada RC (10,000 simulaciones)
lambda_samples = np.random.gamma(alpha_k, 1/beta_k, size=10000)
frag_samples   = 1 - np.prod(np.exp(-lambda_samples_combined), axis=1)
ic_lo  = np.percentile(frag_samples, 10)  # IC 80%
ic_hi  = np.percentile(frag_samples, 90)
frag_cv = np.std(frag_samples) / np.mean(frag_samples)
```

CV > 1.0 indica alta incertidumbre — comunicar esto en el reporte.

---

# Proceso de Hawkes (Módulo experimental)

## Qué es

El proceso de Hawkes modela auto-excitación: un evento AT aumenta temporalmente la
probabilidad de otro evento del mismo tipo. Útil para capturar clustering temporal.

```
lambda_hawkes(t) = mu + sum_i( alpha * exp(-beta*(t - t_i)) )
mu    = tasa base (baseline)
alpha = intensidad del efecto de auto-excitación
beta  = decaimiento del efecto
```

## Estado actual

Implementado en `src/models/hawkes_process.py`.
**Deshabilitado por defecto** (`hawkes.enabled: false` en config.yaml).

## Condiciones para activar

- >= 12 semanas de historial con timestamps de eventos AT
- Estimación MLE de (mu, alpha, beta) convergió (MP-1 del roadmap)
- Validación walk-forward muestra mejora vs modelo Poisson simple

## Riesgo de activar prematuramente

Con < 10 eventos por RC, los parámetros Hawkes son inestables.
alpha/beta pueden colapsar al prior inicial.
Mantener deshabilitado hasta tener backtesting validado.

---

# Forecasting Categórico por RC

El pipeline genera categorías operacionales por RC:
- `nivel`: Bajo, Medio, Alto, Crítico (basado en lambda y fra_rc_raw)
- `tendencia`: ascendente, estable, descendente (regresión lineal sobre últimas 4 sem)
- `señal`: "Deterioro emergente", "Presión AT crónica", etc.

Implementado en `src/forecasting/categorizer.py`.

## Reglas de nivel

```python
if fra_rc_raw >= 0.40:    nivel = "Crítico"
elif fra_rc_raw >= 0.20:  nivel = "Alto"
elif fra_rc_raw >= 0.08:  nivel = "Medio"
else:                     nivel = "Bajo"
```

## Reglas de señal operacional

| Condición | Señal |
|-----------|-------|
| lambda_at alto + lambda_hal bajo | "Presión AT crónica" |
| lambda_at bajo + lambda_hal alto | "Señal HAL preventiva" |
| Ambas lambdas altas | "Presión combinada" |
| Tendencia ascendente en FRAG | "Deterioro emergente" |
| Todo bajo umbral | "Riesgo bajo vigilancia" |

---

# Calibración y Backtesting

## Métricas de calibración (cuando hay historial)

Con >= 12 semanas de historial, verificar:
1. **Sharpness**: IC 80% no debe ser tan amplio que sea no informativo
2. **Coverage**: En 80% de las semanas, el FRAG observado debe estar dentro del IC 80%
3. **Skill Score**: Brier Score del modelo vs naive baseline (FRAG = lambda histórico)

## Drift detection implementado

PSI implementado en `performance_metrics._psi()`.
Se calcula sobre los últimos 4 snapshots vs referencia.
Si PSI > 0.25 → revisar si hubo cambio real en operaciones o error de datos.

## Seasonal baseline (pendiente — MP-6)

El FRAG puede ser estacional (más AT en verano por calor, más en invierno por lluvia).
MP-6 implementará un baseline por semana del año una vez acumuladas >= 52 semanas.

---

# Anti-patrones de Forecasting

- **No** interpretar FRAG < 10% como "operación segura" — puede ser escasez de datos
- **No** usar el CV como único indicador de confiabilidad sin revisar n_at_window
- **No** activar Hawkes sin backtesting validado
- **No** ajustar prior_events sin entender el impacto en todas las semanas previas
- **No** comparar FRAG entre plantas distintas sin normalizar por exposición (horas-hombre)
- **No** mostrar el IC como "error de medición" — es incertidumbre del modelo, no del dato
