# Skill: Machine Learning Operacional — Predicción y Diagnóstico en Procesos Industriales

## Propósito

Guiar la aplicación de modelos de machine learning en contextos operacionales mineros:
predicción de rendimiento, detección de anomalías, clustering operacional y explicabilidad
orientada a decisiones de turno.

---

## 1. Principios de ML en Contexto Operacional

1. **Interpretabilidad primero**: un modelo que el operador no entiende no se usa
2. **Latencia de predicción**: horizonte 1-4h es accionable; 24h es estratégico
3. **Datos desbalanceados**: las detenciones son infrecuentes → usar técnicas de rebalanceo
4. **Leakage temporal**: nunca usar información futura en features de entrenamiento
5. **Validación temporal**: usar TimeSeriesSplit, no KFold aleatorio

---

## 2. Pipeline Estándar de Modelamiento

```python
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import xgboost as xgb

# Split temporal (nunca aleatorio en series de tiempo)
tscv = TimeSeriesSplit(n_splits=5)

# Modelo base recomendado para TPH industrial
model = xgb.XGBRegressor(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    early_stopping_rounds=20,
)
```

---

## 3. Horizontes de Predicción

| Horizonte | N° períodos (5min) | Caso de uso |
|-----------|--------------------|-------------|
| 1 hora    | 12 períodos        | Alerta operacional inmediata |
| 4 horas   | 48 períodos        | Planificación de turno |
| 12 horas  | 144 períodos       | Planificación de guardia |
| 24 horas  | 288 períodos       | Planificación diaria |

---

## 4. Clustering Operacional (KMeans)

Identificar regímenes operacionales:

```python
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

features_cluster = ['tph_valid', 'tph_roll_std', 'tph_roll_cv', 'en_ventana_t8']
X = df[features_cluster].dropna()
X_scaled = StandardScaler().fit_transform(X)

kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
df.loc[X.index, 'cluster_op'] = kmeans.fit_predict(X_scaled)

# Interpretar clusters por centroide:
# - Cluster con TPH alto + std bajo = operación normal
# - Cluster con TPH medio + std alto = operación inestable
# - Cluster con TPH bajo + any std = operación degradada/detenida
# - Cluster con TPH ascendente = recuperación
```

**Etiquetas sugeridas:**
- 0 = Normal
- 1 = Inestable
- 2 = Degradado
- 3 = Recuperación

---

## 5. SHAP Explainability

```python
import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

# Gráfico de importancia global
shap.summary_plot(shap_values, X_test, plot_type="bar")

# Análisis de un evento específico (waterfall)
shap.waterfall_plot(shap.Explanation(
    values=shap_values[idx],
    base_values=explainer.expected_value,
    data=X_test.iloc[idx],
))

# Dependence plot para variable clave
shap.dependence_plot('en_ventana_t8', shap_values, X_test)
```

**Interpretación para operaciones:**
- SHAP positivo → feature aumenta predicción de TPH
- SHAP negativo → feature reduce predicción de TPH
- Magnitud = importancia en TPH reales (misma unidad que target)

---

## 6. Evaluación y Validación

```python
def evaluar_modelo(y_true, y_pred, nombre='Modelo'):
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2   = r2_score(y_true, y_pred)
    mape = np.mean(np.abs((y_true - y_pred) / (y_true + 1e-6))) * 100
    print(f'{nombre}: MAE={mae:.1f} TPH | RMSE={rmse:.1f} | R²={r2:.3f} | MAPE={mape:.1f}%')
    return {'mae': mae, 'rmse': rmse, 'r2': r2, 'mape': mape}
```

---

## 7. Anti-patrones a Evitar

| Anti-patrón | Consecuencia | Solución |
|-------------|--------------|----------|
| KFold aleatorio en series de tiempo | Data leakage temporal | Usar TimeSeriesSplit |
| Normalizar antes de split | Leakage de estadísticas futuras | Normalizar dentro del fold |
| Usar TPH_t como feature para predecir TPH_t | Leakage trivial | Usar lags t-n |
| Ignorar detenciones en evaluación | MAE artificialmente bajo | Evaluar por separado |
| Entrenar con toda la serie | Sobreajuste al pasado reciente | Validación en período holdout |

---

## 8. Índice Global de Impacto T8 (IGI_T8)

```python
def calcular_igi_t8(delta_tph_pct, horas_recuperacion_95, desv_programa_pct, duracion_ventana_h):
    '''
    IGI_T8: índice 0-100 donde 100 = impacto máximo
    Pesos: caída TPH 40%, recuperación lenta 30%, desviación programa 20%, duración 10%
    '''
    score_caida = min(abs(delta_tph_pct) / 50 * 100, 100) * 0.40
    score_rec   = min(horas_recuperacion_95 / 48 * 100, 100) * 0.30
    score_desv  = min(abs(desv_programa_pct) / 30 * 100, 100) * 0.20
    score_dur   = min(duracion_ventana_h / 72 * 100, 100) * 0.10
    return score_caida + score_rec + score_desv + score_dur
```
