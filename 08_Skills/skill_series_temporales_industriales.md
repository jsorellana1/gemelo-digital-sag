# Skill: Series Temporales Industriales — Análisis Operacional Minero

## Propósito

Guiar el análisis, modelamiento y detección de patrones en series temporales de procesos
industriales mineros, con énfasis en datos de alta frecuencia (1 min a 1 hora),
eventos de detención, recuperación operacional y análisis pre/post intervención.

---

## 1. Características de Datos Industriales Mineros

### Propiedades típicas
- **Alta frecuencia**: 1–5 minutos por registro
- **Valores cero o muy pequeños**: indican detención, no ausencia de dato
- **No estacionariedad**: el proceso cambia con turnos, mantenciones, estaciones
- **Datos mezclados**: coeficientes de estado junto a valores TPH reales
- **Outliers funcionales**: valores extremos son operativamente posibles
- **Datos faltantes**: huecos por fallas de instrumentación, no necesariamente detención

### Regla de oro
```
Antes de modelar → identificar tipos de registros:
1. Operando normal: TPH > umbral, baja variabilidad
2. Aceleración: TPH creciente post-detención
3. Degradación: TPH decreciente (posible agotamiento pila)
4. Detención: TPH ≤ umbral
5. Dato inválido: valor fuera de rango físico posible
```

---

## 2. Preprocesamiento Estándar

```python
# 1. Filtrar valores inválidos (coeficientes vs TPH)
df['tph_valid'] = df['tph'].where(df['tph'] > TPH_THRESHOLD, other=np.nan)

# 2. Flag de operación
df['operando'] = df['tph'] > TPH_THRESHOLD

# 3. Calcular toneladas (5 min = 1/12 hora)
df['ton'] = df['tph_valid'].fillna(0) * (5/60)

# 4. Rolling stats (ventana 1 hora = 12 períodos)
df['tph_roll_mean'] = df['tph_valid'].rolling(12, min_periods=4).mean()
df['tph_roll_std']  = df['tph_valid'].rolling(12, min_periods=4).std()
df['tph_roll_cv']   = df['tph_roll_std'] / df['tph_roll_mean']  # variabilidad relativa

# 5. Z-score local
df['zscore'] = (df['tph_valid'] - df['tph_roll_mean']) / df['tph_roll_std']
```

---

## 3. Detección de Change Points

Usar `ruptures` para detectar quiebres estructurales:

```python
import ruptures as rpt

# Método recomendado para series industriales
signal = df['tph_valid'].fillna(0).values
model = rpt.Pelt(model="rbf", min_size=12, jump=1)  # min 1 hora entre quiebres
model.fit(signal)
breakpoints = model.predict(pen=10)  # pen=penalización (ajustar según señal)
```

**Interpretación de quiebres:**
- Quiebre con caída de nivel → detención o degradación
- Quiebre con subida de nivel → recuperación o cambio de set-point
- Quiebre en varianza → cambio de estabilidad operacional

---

## 4. Análisis Pre/Post Evento

Ventanas estándar para análisis de impacto:

| Ventana | Propósito |
|---------|-----------|
| PRE 24h | Baseline inmediato antes del evento |
| PRE 48h | Baseline extendido (captura efectos anticipatorios) |
| PRE 72h | Baseline de referencia operacional |
| POST 24h | Impacto inmediato post evento |
| POST 48h | Recuperación parcial |
| POST 72h | Recuperación completa o nuevo estado base |

```python
for n_horas in [24, 48, 72]:
    td = timedelta(hours=n_horas)
    mask_pre  = (df['fecha'] >= evento_inicio - td) & (df['fecha'] < evento_inicio)
    mask_post = (df['fecha'] >= evento_fin) & (df['fecha'] < evento_fin + td)
    
    tph_pre  = df.loc[mask_pre  & operando, 'tph'].mean()
    tph_post = df.loc[mask_post & operando, 'tph'].mean()
    delta    = (tph_post - tph_pre) / tph_pre  # delta relativo
```

---

## 5. Features para Machine Learning

```python
# Temporales
df['hora']          = df['fecha'].dt.hour
df['dia_semana']    = df['fecha'].dt.dayofweek
df['dia_mes']       = df['fecha'].dt.day
df['mes']           = df['fecha'].dt.month

# Lags (períodos de 5 min)
for lag in [1, 3, 6, 12, 24, 48, 144, 288]:  # 5min, 15min, 30min, 1h, 2h, 4h, 12h, 24h
    df[f'tph_lag_{lag}'] = df['tph_valid'].shift(lag)

# Rolling windows
for w in [12, 24, 48, 144, 288]:  # 1h, 2h, 4h, 12h, 24h
    df[f'tph_roll_{w}'] = df['tph_valid'].rolling(w).mean()
    df[f'tph_std_{w}']  = df['tph_valid'].rolling(w).std()

# Contexto evento
df['minutos_desde_t8_inicio'] = (df['fecha'] - t8_inicio).dt.total_seconds() / 60
df['en_ventana_t8']            = (df['fecha'] >= t8_inicio) & (df['fecha'] < t8_fin)
df['post_ventana_t8']          = df['fecha'] >= t8_fin
```

---

## 6. Evaluación de Modelos de Forecast

| Métrica | Cuándo usar | Interpretación |
|---------|-------------|----------------|
| MAE | siempre | error absoluto promedio en unidad original (TPH) |
| RMSE | cuando outliers importan | penaliza errores grandes |
| MAPE | comparación relativa | sensible a valores cercanos a 0 |
| R² | bondad de ajuste global | 1 = perfecto, < 0 = peor que la media |

**Umbral de aceptación para TPH industrial:**
- MAE < 10% del TPH medio = modelo aceptable
- MAE < 5% = modelo bueno

---

## 7. Anomaly Detection Industrial

```python
from sklearn.ensemble import IsolationForest

features = ['tph_valid', 'tph_roll_mean', 'tph_roll_std', 'hora', 'dia_semana']
X = df[features].dropna()

iso = IsolationForest(contamination=0.05, random_state=42, n_estimators=100)
df.loc[X.index, 'anomalia_iso'] = iso.fit_predict(X)  # -1 = anomalía
df.loc[X.index, 'score_anomalia'] = iso.score_samples(X)
```

**Interpretación:**
- Score < -0.5: anomalía severa (posible falla o evento operacional crítico)
- Score -0.3 a -0.5: anomalía moderada (investigar contexto)
- Score > -0.3: operación normal
---

## 8. Exogenas T8 a Nivel Diario

Cuando el analisis sea diario, incluir explicitamente:

```python
df['horas_t8'] = ...
df['horas_t8_lag1'] = df['horas_t8'].shift(1)
df['horas_t8_lag2'] = df['horas_t8'].shift(2)
df['horas_t8_lag3'] = df['horas_t8'].shift(3)
df['horas_t8_lag7'] = df['horas_t8'].shift(7)
df['horas_t8_roll3'] = df['horas_t8'].rolling(3, min_periods=1).mean()
df['horas_t8_roll7'] = df['horas_t8'].rolling(7, min_periods=1).mean()
```

Uso esperado:

- regresiones lineales de elasticidad
- SARIMAX con exogena `horas_t8`
- XGBoost temporal con lags y rolling
- analisis de recuperacion a `24h`, `48h`, `72h`

---

## 9. Efecto Gaviota Inteligente

Cuando PAM Mantto entrega solo `fecha | horas_t8` y no hora exacta de inicio:

1. usar PAM para definir el evento oficial diario
2. no asumir inicio a medianoche como centro de la gaviota
3. buscar el efecto real en la serie 5 min

Secuencia recomendada:

```python
ventana_busqueda = 48h_pre + dia_evento + 48h_post
baseline_pre = promedio_24h_previas
rolling_mean = serie.rolling(12, min_periods=4).mean()
rolling_std = serie.rolling(12, min_periods=4).std()
```

### Detecciones minimas

- `timestamp_inicio_efecto`
- `timestamp_minimo`
- `timestamp_recuperacion_80`
- `timestamp_recuperacion_90`
- `timestamp_recuperacion_95`
- `timestamp_recuperacion_100`

### Centro de alineamiento

El agregado gaviota debe usar:

```text
t = 0 en timestamp_minimo
```

y no en el inicio del dia PAM.

### Change points

- usar `ruptures` si esta disponible
- si no esta disponible, aplicar fallback con rolling mean/std y caida sostenida
- siempre registrar el metodo efectivo de deteccion

### Restriccion operacional

El valle debe buscarse en el tramo mas plausible del efecto, no en cualquier minimo lejano
de la ventana ampliada, para no mezclar el evento T8 con detenciones no relacionadas.

---

## Changelog

- 2026-06-15: Se agregan lags y rolling diarios de `horas_t8` para modelamiento exogeno de Teniente 8 y analisis de efecto diferido.
- 2026-06-15: Se agrega metodologia de efecto gaviota inteligente centrada en el minimo observado y fallback de deteccion cuando `ruptures` no esta disponible.
