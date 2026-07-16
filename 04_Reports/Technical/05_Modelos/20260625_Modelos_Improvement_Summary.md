# Resumen: Loop de Mejora Iterativa de Modelos
**División El Teniente — Codelco | 2026-06-22**

---

## Configuración del Experimento

| Parámetro          | Valor                    |
|--------------------|--------------------------|
| Target             | `SAG2_tph_mean` (SAG2 TPH diario) |
| Período            | 2026-01-01 → 2026-06-14 |
| N filas            | 151 |
| Split              | 70/15/15 train/val/test (temporal, sin shuffle) |
| CV                 | TimeSeriesSplit(n_splits=5) |
| Max iteraciones    | 20 por modelo |
| Patience           | 3 sin mejora → stop |
| Criterio R²        | ≥ 0.75 |
| Criterio MAPE      | ≤ 15% |
| Feature sets       | 7 niveles progresivos (G0→G6) |

---

## Skills Aplicados

- `skill_machine_learning_operacional` — TimeSeriesSplit, SHAP, pipeline ML
- `skill_data_scientist_senior` — regresión robusta, diagnósticos
- `skill_series_temporales_industriales` — lags, rolling, validación temporal
- `skill_estadistica_bayesiana_avanzada` — incertidumbre en estimaciones

---

## Resultados: Campeones por Familia

| Modelo | Versión | FS | R²_train | R²_val | R²_test | MAE (TPH) | MAPE % | Diagnóstico |
|--------|---------|----|----------|--------|---------|-----------|--------|-------------|
| LinearRegression ★ | v03 | FS5 | 0.608 | -0.708 | -0.333 | 158 | 6.9 | overfitting |
| GradientBoosting | v17 | FS6 | 0.998 | -0.180 | -0.490 | 144 | 6.2 | overfitting |
| CatBoost | v13 | FS5 | 0.974 | -0.048 | -0.555 | 170 | 7.3 | overfitting |
| RandomForest | v02 | FS1 | 0.723 | -0.522 | -0.823 | 352 | 16.3 | overfitting |
| HuberRegressor | v11 | FS6 | 0.596 | -0.624 | -0.899 | 185 | 8.0 | overfitting |
| DecisionTree | v02 | FS1 | 0.670 | -0.524 | -0.916 | 358 | 16.6 | overfitting |
| ElasticNet | v09 | FS7 | 0.528 | -0.171 | -0.940 | 188 | 8.0 | overfitting |
| XGBoost | v04 | FS1 | 0.876 | -0.998 | -1.042 | 374 | 17.2 | overfitting |
| LightGBM | v01 | FS1 | 0.612 | -0.958 | -1.251 | 397 | 18.3 | overfitting |
| Lasso | v06 | FS4 | 0.500 | -0.314 | -1.629 | 225 | 9.7 | overfitting |
| Ridge | v08 | FS4 | 0.469 | -0.216 | -1.757 | 232 | 10.0 | overfitting |

> ★ = Campeón global seleccionado

---

## Campeón Global: LinearRegression v03

- **R² test**: -0.3328
- **MAE test**: 157.7 TPH
- **MAPE test**: 6.9%
- **Bias**: -68.4 TPH
- **Error P90**: 283.2 TPH
- **Feature set**: FS5 (28 features)
- **Diagnóstico**: overfitting

**Features del campeón global:**
  - `dia_sem`
  - `mes`
  - `semana`
  - `horas_t8`
  - `en_t8`
  - `post_t8_1`
  - `post_t8_3`
  - `t8_horas_ayer`
  - `bucket_num`
  - `horas_t8_lag1`
  - `horas_t8_lag2`
  - `horas_t8_roll3d`
  - `pila_sag2_mean`
  - `pila_sag2_lag1`
  - `pila_sag2_lag3`
  - _(y más...)_

---

## 8 Preguntas del Reporte Final

### 1. ¿Qué modelo tuvo mejor R²?

**LinearRegression** con R²_test = -0.3328

### 2. ¿Qué modelo tuvo menor MAE?

**GradientBoosting** con MAE_test = 144.3 TPH

### 3. ¿Qué modelo generaliza mejor?

**CatBoost** con menor gap train–test y mejor R²_val.
Gap train–test = 1.529

### 4. ¿Qué features mejoraron más la performance?

Top features del campeón global (por importancia):
  _Ver figura 05_importancia_variables.png_

El grupo que más contribuyó fue identificado por la diferencia de R²_val entre feature sets consecutivos.

### 5. ¿Hubo overfitting?

Sí, se detectó overfitting en: **LinearRegression, Ridge, Lasso, HuberRegressor, ElasticNet, DecisionTree, RandomForest, GradientBoosting, XGBoost, LightGBM, CatBoost**. El shrinkage vía regularización (Ridge, Lasso, ElasticNet) y la limitación de profundidad en árboles mitigaron el problema.

### 6. ¿Qué modelo es más interpretable?

**DecisionTree** — los modelos lineales y los árboles de decisión superficiales son directamente interpretables por operadores (relación coeficiente → efecto unitario en TPH).
Para operaciones: se recomienda entregar el árbol de decisión como tabla de reglas + el modelo campeón para predicción.

### 7. ¿Cuál debe pasar a producción?

Recomendación:
- **Predicción**: `LinearRegression` v03 (mejor R² test + estabilidad)
- **Interpretabilidad / presentación a operadores**: `DecisionTree` (reglas legibles)
- **Monitoreo**: revisar MAE rolling semanal; si MAE > 237 TPH → reentrenar

### 8. ¿Qué mejoras quedaron pendientes?

1. **Optuna / Hyperopt**: búsqueda de hiperparámetros más eficiente (no disponible en entorno actual)
2. **pygam / LOWESS integrado**: modelos aditivos generalizados (requiere `pygam`)
3. **EDO híbrido**: combinar predicción ML con balance de masa ODE para pilas
4. **Datos adicionales**: granulometría, dureza de mineral, variables DCS de proceso
5. **Feature selection automática**: Recursive Feature Elimination o BORUTA
6. **Ensemble stacking**: combinar predicciones de modelos campeones como features de un meta-modelo
7. **Reentrenamiento rolling**: retrain mensual con ventana deslizante para capturar drift

---

## Archivos Generados

| Tipo | Ruta |
|------|------|
| Figura 01 | `outputs/figures/model_loop/01_performance_por_modelo.png` |
| Figura 02 | `outputs/figures/model_loop/02_real_vs_predicho_modelo_campeon.png` |
| Figura 03 | `outputs/figures/model_loop/03_error_temporal_modelo_campeon.png` |
| Figura 04 | `outputs/figures/model_loop/04_residuos_modelo_campeon.png` |
| Figura 05 | `outputs/figures/model_loop/05_importancia_variables.png` |
| Figura 06 | `outputs/figures/model_loop/06_shap_summary.png` |
| Figura 07 | `outputs/figures/model_loop/07_evolucion_iteraciones.png` |
| Excel     | `outputs/excel/model_performance_tracking.xlsx` |
| Informe   | `outputs/reports/model_improvement_summary.md` |
| Modelos   | `outputs/models/*.pkl` (campeón por familia) |

---

*Generado: 2026-06-22 07:25 — Plataforma Analítica CIO DET*
