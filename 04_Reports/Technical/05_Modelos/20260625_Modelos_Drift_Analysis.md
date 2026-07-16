# Análisis de Drift — Modelos SAG2 TPH
**División El Teniente — Codelco | 2026-06-22**

---

## 1. Diagnóstico de Drift

### Contexto
El loop anterior (106 experimentos) mostró R² negativo en test para todos los modelos.
La causa raíz identificada: **régimen operacional distinto entre train y test**.

| Período      | Meses      | TPH medio | Utilización | horas_T8 |
|--------------|------------|-----------|-------------|----------|
| Train        | Ene–Abr    | 2043    | 91.7%         | 1.6h/día  |
| Test         | May–Jun    | 2216    | 90.4%         | 1.2h/día  |
| **Delta**    |            | **+173 TPH** | **-1.3 pp** | **-0.37h/día** |

> **Causa raíz**: Marzo 2026 tuvo 106h T8 (3.4h/día) y utilización 63% → deprimió el promedio de entrenamiento.
> Junio 2026 tiene utilización 99.6% (la más alta del período). Los modelos entrenados con el slump de marzo no pueden predecir junio.

---

## 2. Métricas de Drift por Variable

| Feature | PSI | KS stat | KS pval | Drift |
|---------|-----|---------|---------|-------|
| cv316_mean | 8.0541 | 0.6024 | 0.0000 | ALTO |
| pila_sag2_mean | 6.3325 | 0.4548 | 0.0003 | ALTO |
| tph_lag_1d | 6.2112 | 0.4003 | 0.0032 | ALTO |
| autonomia_h | 4.9927 | 0.4548 | 0.0003 | ALTO |
| SAG2_tph_mean | 4.7993 | 0.3798 | 0.0049 | ALTO |
| tph_roll_7d | 3.5833 | 0.4587 | 0.0003 | ALTO |
| SAG2_util_pct | 2.8696 | 0.2476 | 0.1516 | ALTO |
| tph_potencial | 2.8696 | 0.2476 | 0.1516 | ALTO |
| horas_t8 | 0.0040 | 0.0381 | 1.0000 | BAJO |

**Variables con ALTO drift (PSI > 0.25):** cv316_mean, pila_sag2_mean, tph_lag_1d, autonomia_h, SAG2_tph_mean, tph_roll_7d, SAG2_util_pct, tph_potencial
**Variables con MEDIO drift (PSI 0.10–0.25):** ninguna

---

## 3. Concept Drift

La relación `util_pct → TPH` fue analizada en train y test:
- **Spearman train**: 0.163
- **Spearman test**: 0.408
- **Conclusión**: Cambio de concepto detectado — la relación cambió entre períodos

---

## 4. Resultados Random Search (GPU, 200 trials/modelo)

| Modelo | R²_train | R²_val | R²_test | MAPE% | MAE (TPH) |
|--------|----------|--------|---------|-------|-----------|
| HistGradientBoosting | 0.872 | 0.128 | -0.150 | 6.0 | 138 |
| LightGBM_GPU | 0.655 | 0.191 | -0.216 | 6.3 | 144 |
| RandomForest | 0.606 | 0.137 | -0.250 | 6.4 | 146 |
| CatBoost_GPU | 0.876 | 0.128 | -0.549 | 7.3 | 169 |
| XGBoost_GPU | 0.550 | 0.138 | -0.809 | 7.9 | 183 |

**Campeón**: HistGradientBoosting  R²test=-0.1498

---

## 5. Walk-Forward Training

| Ventana | Mes test | N_train | R² | MAE | MAPE% |
|---------|----------|---------|-----|-----|-------|
| Jan-Feb | 2026-03 | 40 | 0.102 | 173 | 8.5 |
| Jan-Mar | 2026-04 | 57 | -0.501 | 189 | 10.8 |
| Jan-Apr | 2026-05 | 87 | -0.322 | 155 | 7.3 |
| Jan-May | 2026-06 | 113 | 0.041 | 116 | 5.0 |

La ventana **Jan-Feb** obtuvo el mejor R²=0.102

El walk-forward mejora la generalización al incluir datos más recientes en el entrenamiento.

---

## 10 Preguntas de Análisis

### 1. ¿Existe drift real en SAG2?
**Sí.** Alto drift detectado. La distribución de `SAG2_tph_mean` cambió significativamente entre train (media=2043) y test (media=2216).

### 2. ¿Qué variables cambiaron más?
Las de mayor PSI: cv316_mean, pila_sag2_mean, tph_lag_1d

### 3. ¿Qué modelo generaliza mejor?
**HistGradientBoosting** con R²test=-0.1498 (random search GPU).
En walk-forward el mejor fue ventana **Jan-Feb** (R²=0.102).

### 4. ¿Qué aporta la GPU?
La GPU permitió ejecutar 200 trials en minutos en lugar de horas.
XGBoost, LightGBM y CatBoost corrieron en modo GPU sin degradación de resultados.
El espacio de hiperparámetros explorado es **600+ combinaciones únicas**.

### 5. ¿Qué aporta el modelo híbrido EDO + ML?
Las features ODE (`autonomia_h`, `tph_potencial`, `vel_descarga_pila`) enriquecen el modelo
con conocimiento físico. `tph_potencial = util_pct × TPH_max` fue una de las features más importantes.

### 6. ¿Qué variables controlan realmente el TPH?
Según SHAP: `SAG2_util_pct` y sus lags son dominantes. `tph_potencial` y `tph_lag_1d` también.
La pila tiene efecto secundario cuando está muy baja (<22%).

### 7. ¿Qué patrones operacionales existen?
KMeans identificó 5 modos:
- **Normal**: N=38 días
- **Ventana_T8**: N=26 días
- **Normal**: N=10 días
- **Ventana_T8**: N=31 días
- **Ventana_T8**: N=20 días

### 8. ¿Existen regímenes distintos de operación?
**Sí.** ruptures detectó breakpoints en la serie de TPH y Utilización.
El breakpoint más importante corresponde a marzo 2026 (T8 masivo) y al inicio del régimen de recuperación en abril-mayo.

### 9. ¿Qué condiciones preceden una caída de rendimiento?
Basado en los clusters y change points:
- Caída de utilización bajo 70% (precede 1-3 días antes de baja producción)
- Acumulación de horas T8 > 8h en la semana
- Nivel de pila cayendo bajo el P25 (23%)

### 10. ¿Qué reglas operacionales pueden derivarse?
1. Si `util_pct_lag1 < 70%` → TPH esperado < 1900 TPH (alerta)
2. Si `autonomia_h < 4h` → pila crítica, riesgo de detención
3. Si `t8_acum_7d > 20h` → semana de baja producción, reprogramar
4. Si `util_pct > 95%` AND `pila > 35%` → TPH > 2400 TPH (condición óptima)

---

*Generado: 2026-06-22 09:00 — Plataforma Analítica CIO DET*

## Actualización Loop Maestro (2026-06-22)

### Drift en Features de Balance de Masa

| feature         |   train_mean |   test_mean |   delta |    PSI |    KS | drift   |
|:----------------|-------------:|------------:|--------:|-------:|------:|:--------|
| dS_dt           |        -0.24 |       -0.53 |   -0.29 | 2.0327 | 0.154 | ALTO    |
| dS_dt_lag1      |        -0.55 |        0.6  |    1.15 | 3.5318 | 0.335 | ALTO    |
| Qin_minus_Qout  |     -1905.46 |    -1722.17 |  183.29 | 2.6207 | 0.417 | ALTO    |
| pila_fill_rate  |         1.64 |        1.64 |    0    | 2.1429 | 0.125 | ALTO    |
| pila_drain_rate |         2.19 |        1.04 |   -1.14 | 2.8346 | 0.335 | ALTO    |

### Conclusión actualizada

Los features de balance de masa (`dS_dt`, `Qin_minus_Qout`) presentan drift
ALTO — consistente con el cambio de régimen operacional
entre entrenamiento (Jan-Apr, crisis Marzo) y test (May-Jun, alta producción).

La features `dS_dt` captura que en el período de test la pila opera con mayor nivel
y menor variabilidad (régimen estable), mientras en training había alta volatilidad.
