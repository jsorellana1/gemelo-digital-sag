# Propuesta de Mejora — Modelo Predictivo de Rendimientos Molienda T8

**Versión:** 1.0 | **Autor:** CIO Analítica | **Fecha:** 2026-07-01

---

## 1. Diagnóstico del estado actual

| Aspecto | Estado Actual | Observación |
|---------|--------------|-------------|
| Modelo core | XGBoost Regressor (Producción) | Ridge/ElasticNet como baseline |
| Challengers | LightGBM, CatBoost, RF, HistGradientBoosting | Solo en Experimental, no integrados |
| Features T8 | Binaria `en_ventana_t8` + `horas_t8` diaria | No se usa `horas_t8` continua como exógena en ML |
| Pilas | Modelo stock diferencial (no ML) | Nuevos datos CV315, CV316, nivel pilas disponibles |
| Efecto gaviota | Implementado en notebooks | No integrado como feature del modelo predictivo |
| Incertidumbre | Intervalo de credibilidad Bayesiano standalone | No acoplado al predictor XGBoost |
| Concept drift | No implementado | Modelo entrenado una vez, sin reentreno automático |
| Forecasting | Puntual, no probabilístico | Solo point forecast, sin intervalos de predicción |

---

## 2. Propuesta de mejoras priorizadas

### P1 — Ensemble stacking: XGBoost + LightGBM + CatBoost

**Problema:** XGBoost solo, los challengers están en `Experimental/` sin uso productivo.

**Solución:** Stacking regressor con meta-modelo Ridge (capa1 = base learners, capa2 = Ridge).

```python
from sklearn.ensemble import StackingRegressor
from sklearn.linear_model import Ridge

base_learners = [
    ('xgb', XGBRegressor(**params_xgb)),
    ('lgb', LGBMRegressor(**params_lgb)),
    ('cat', CatBoostRegressor(**params_cat, verbose=0)),
]
meta_model = Ridge(alpha=1.0)
stack = StackingRegressor(
    estimators=base_learners,
    final_estimator=meta_model,
    cv=TimeSeriesSplit(n_splits=5),
)
```

**Beneficio esperado:** Reducción de MAE 5–12% vs XGBoost individual (por diversidad de modelos).

**Riesgo:** Mayor latencia de inferencia (3x); aceptable para horizonte ≥ 1h.

---

### P2 — Features de pilas (CV315, CV316, nivel) en modelo predictivo

**Problema:** Datos de correas y nivel de pilas existen desde junio 2026 pero no alimentan el modelo ML.

**Solución:** Agregar features derivadas del balance de masa de pilas (skill_molienda_sag.md §9):

```python
# Balance de masa
df['consumo_sag'] = df['tph_sag'] * (5/60)
df['inventario_pila'] = df['inv_pila'].shift(1) + df['correa'] - df['consumo_sag']

# Features derivadas
df['pct_pila'] = df['inventario_pila'] / df['capacidad_pila']
df['pct_pila_lag_1h'] = df['pct_pila'].shift(12)
df['delta_pct_pila'] = df['pct_pila'].diff(12)
df['horas_restantes_pila'] = df['inventario_pila'] / df['consumo_sag'].clip(lower=1)
```

**Beneficio esperado:** Mejora en predicción de degradación de TPH en ventanas > 8h. Habilita alerta temprana de agotamiento.

**Requiere:** Pipeline de ingesta de `correas_ton.xlsx` integrado al `01_Data/Processed/`.

---

### P3 — Forecasting probabilístico con intervalos de predicción

**Problema:** Hoy se entrega solo point forecast; el operador no conoce la incertidumbre.

**Solución:** Quantile Regression sobre XGBoost (o LightGBM) para P10, P50, P90.

```python
model_p10 = XGBRegressor(objective='reg:quantileerror', quantile_alpha=0.10)
model_p50 = XGBRegressor(objective='reg:quantileerror', quantile_alpha=0.50)
model_p90 = XGBRegressor(objective='reg:quantileerror', quantile_alpha=0.90)
```

**Alternativa:** Conformal Prediction sobre el ensemble actual (no requiere reentreno).

**Beneficio:** El operador ve "TPH esperado 1800 [IC 80%: 1550–2050]" → decisión informada.

**Referencia skill:** `skill_forecasting_industrial.md` — Regla 1: "Intervalo de credibilidad, no punto único".

---

### P4 — Feature `horas_t8` continua con rezagos

**Problema:** Hoy `en_ventana_t8` es binaria y `horas_t8` solo se usa en análisis diario, no como feature ML.

**Solución (skill_series_temporales_industriales.md §8):**

```python
df['horas_t8_acum_3d'] = df['horas_t8'].rolling(3).sum()
df['horas_t8_acum_7d'] = df['horas_t8'].rolling(7).sum()
df['horas_t8_lag1'] = df['horas_t8'].shift(1)
df['horas_t8_lag2'] = df['horas_t8'].shift(2)
df['horas_t8_lag3'] = df['horas_t8'].shift(3)
df['dias_desde_ultima_t8'] = ...  # recency effect
```

**Beneficio:** Captura efecto acumulativo (ventanas consecutivas = estrés sobre pilas) y efecto rezagado.

---

### P5 — Concept drift monitoring

**Problema:** El modelo se entrenó una vez y no se monitorea si la relación T8→TPH cambia.

**Solución:** PSI (Population Stability Index) sobre predicciones vs reales con ventana rodante de 30 días.

```python
def psi(expected, actual, bins=10):
    expected_hist = np.histogram(expected, bins=bins, range=(0, 3000))[0] + 1
    actual_hist   = np.histogram(actual,   bins=bins, range=(0, 3000))[0] + 1
    expected_pct  = expected_hist / expected_hist.sum()
    actual_pct    = actual_hist / actual_hist.sum()
    return np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
```

**Umbral:** PSI > 0.25 → disparar reentreno o revisión de datos.

**Implementación:** Script semanal (`_drift_monitor.py`) que lee `01_Data/Processed/` y compara con predicciones del modelo productivo.

---

### P6 — Efecto Gaviota Inteligente como feature

**Problema:** La detección del centro del valle post-T8 (gaviota inteligente) está en notebooks pero no se traduce a feature del modelo.

**Solución:** Para cada ventana T8 detectada (con metodología skill_series_temporales_industriales.md §9), computar:

```python
features_gaviota = {
    'timestamp_minimo': ...,
    'tph_minimo': ...,
    'horas_hasta_minimo': ...,
    'horas_recuperacion_80': ...,
    'horas_recuperacion_95': ...,
    'delta_tph_max': ...,
}
```

Estas features alimentan el modelo de clasificación de criticidad de ventana y la regresión de tiempo de recuperación.

---

## 3. Roadmap sugerido

| Sprint | Mejora | Esfuerzo | Impacto estimado |
|--------|--------|----------|------------------|
| 1 | P3 — Forecasting probabilístico (quantile) | 2 días | Medio-alto (usabilidad) |
| 2 | P4 — Features horas_t8 + rezagos | 1 día | Medio (precisión) |
| 3 | P1 — Ensemble stacking | 3 días | Alto (precisión) |
| 4 | P2 — Features pilas (CV315, CV316) | 4 días | Alto (nuevo régimen) |
| 5 | P5 — Concept drift monitor | 2 días | Medio (mantenibilidad) |
| 6 | P6 — Gaviota features | 3 días | Medio (diagnóstico) |

**Orden recomendado:** P3 → P4 → P1 → P2 → P5 → P6

---

## 4. Criterio de éxito

| Métrica | Línea base (actual) | Target v3 |
|---------|-------------------|-----------|
| MAE (TPH) | ~120 | < 100 |
| MAPE | ~8% | < 6% |
| R² | ~0.85 | > 0.90 |
| Cobertura IC 80% | N/A | 75–85% |
| PSI semanal | N/A | < 0.25 |
| Tiempo reentreno | Manual | Semi-automático |

---

## 5. Archivos a modificar/crear

| Archivo | Acción | Propósito |
|---------|--------|-----------|
| `02_Analytics/Scripts/machine_learning/` | Modificar | Pipeline ensemble + quantile |
| `03_Models/Production/` | Agregar | `stacking_ensemble.pkl`, `model_p10/50/90.pkl` |
| `02_Analytics/Scripts/_drift_monitor.py` | Crear | Monitoreo PSI semanal |
| `01_Data/Features/` | Agregar | Features pilas y gaviota |
| `05_Dashboard/engine/` | Modificar | Consumir nuevos modelos + IC 80% |
| `07_Config/config.yaml` | Modificar | Sección `modelo_v3` con nuevos parámetros |

---

*Basado en skills: skill_machine_learning_operacional, skill_molienda_sag, skill_series_temporales_industriales, skill_forecasting_industrial, skill_data_scientist_senior.*
