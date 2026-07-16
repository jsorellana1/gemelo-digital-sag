# Reporte de Explicabilidad — Modelo HistGradientBoosting
**División El Teniente — Codelco | 2026-06-22**

---

## Modelo Campeón: HistGradientBoosting

- **R²_train**: 0.8721
- **R²_val**:   0.1284
- **R²_test**:  -0.1498
- **MAE_test**: 137.6 TPH
- **MAPE_test**: 6.0%
- **GPU**: No aplica

---

## Top Features por SHAP

| Rank | Feature | mean(|SHAP|) | Interpretación |
|------|---------|-------------|----------------|
| 1 | `tph_roll_3d` | 63.9191 | Variable contribuye a la predicción de TPH |
| 2 | `pila_lag1` | 31.8525 | Variable contribuye a la predicción de TPH |
| 3 | `pila_sag2_mean` | 29.6382 | Nivel de pila: efecto sobre TPH cuando está muy baja |
| 4 | `tph_lag_2d` | 28.6554 | Variable contribuye a la predicción de TPH |
| 5 | `dia_sem` | 19.9035 | Variable contribuye a la predicción de TPH |

---

## Modos Operacionales Descubiertos

| Modo | N días | TPH medio | Descripción |
|------|--------|-----------|-------------|
| Normal | 38 | 1972 | Operación estándar: util 75-90%, pila 25-35% |
| Ventana_T8 | 26 | 2274 | Detención planificada: T8 activo, TPH reducido |
| Normal | 10 | 2196 | Operación estándar: util 75-90%, pila 25-35% |
| Ventana_T8 | 31 | 2203 | Detención planificada: T8 activo, TPH reducido |
| Ventana_T8 | 20 | 1938 | Detención planificada: T8 activo, TPH reducido |


---

## Reglas Operacionales Derivadas del Modelo

Traducción del modelo a reglas de decisión para operadores:

```
SI util_pct >= 95% Y pila >= 35%:
    → Modo Alta Producción → TPH esperado > 2400 TPH

SI horas_t8 > 0 O t8_acum_7d > 10h:
    → Modo Ventana T8 → TPH esperado 1200–1800 TPH

SI pila_sag2 < 22%:
    → ALERTA Baja Pila → autonomia_h < 0.3h hasta zona crítica

SI util_pct < 70% Y pila < 25%:
    → Modo Bajo Rendimiento → revisar causa de detenciones
```

---

## Change Points Detectados

| Señal | Fecha breakpoint | Interpretación |
|-------|-----------------|----------------|


---

*Generado: 2026-06-22 09:00 — Plataforma Analítica CIO DET*
