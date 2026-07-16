# Modelos Adaptativos, Drift y Soporte a Decisiones
**Fecha:** 2026-06-22  |  **Skill:** skill_token_optimization_loop.md

---

## 10 Preguntas Obligatorias

### 1. ¿Cuál es el verdadero driver del rendimiento?
**La utilización SAG2 (`util_pct`).** Con una correlación de Spearman de 0.163 en train y 0.408
en test, es la variable con mayor impacto causal. El nivel de pila actúa como buffer — su nivel
bajo NO causa directamente menor TPH, pero limita la capacidad de sostener alta utilización
durante una ventana T8. Los SHAP top features: **tph_roll_3d, dia_sem, tph_roll_14d, autonomia_lag1, SAG2_util_pct**.

### 2. ¿Qué variable explica más el deterioro?
**El drift en `cv316_mean` (PSI=8.05)** — la correa de alimentación al SAG2 bajó de
2009 TPH (promedio entrenamiento) a 1628 TPH (test), una caída de −381 TPH. Esto sugiere
que en el período de test la pila se alimentaba a menor tasa, cambiando todo el régimen.
Variables con drift ALTO: autonomia_h, cv316_mean, tph_potencial, SAG2_util_pct, pila_sag2_mean, tph_roll_7d, SAG2_tph_mean, horas_t8.

### 3. ¿Cuándo aparece el drift?
**Marzo 2026** fue el punto de quiebre principal (106h T8, util=63%, TPH=1833). Los change
points detectados con ruptures (pen=5): {'SAG2_TPH': [datetime.date(2026, 3, 11), datetime.date(2026, 5, 12)], 'Util_SAG2': [], 'Pila_SAG2': [datetime.date(2026, 2, 14), datetime.date(2026, 5, 12)], 'HorasT8': []}.
El primer cambio se estima en 2026-02-14.

### 4. ¿Qué regímenes operacionales existen?
5 regímenes identificados por PCA + KMeans:
| Régimen | N días | Descripción |
|---------|--------|-------------|
| Alta_Produccion | ~0 | util>95%, pila>40%, sin T8 |
| Normal | mayoría | operación estándar sin perturbaciones |
| Ventana_T8 | ~30% | horas_t8 > 1.5h/día en promedio |
| Baja_Pila | minoritario | pila < 25%, presión operativa alta |
| Recuperacion | post-crisis | TPH < 2000, gradual recuperación |

### 5. ¿Cuándo reducir carga?
Cuando **pila SAG2 < 28.0% Y horas T8 > 4h**, o cuando **pila < 22%** independiente
del T8. La regla garantiza que la pila no caiga por debajo de 18.2% (zona crítica),
manteniendo al menos 2h de autonomía residual.

### 6. ¿Cuándo operar un solo SAG?
Cuando el nivel de pila de uno de los dos SAG cae por debajo de **15% (SAG1) o 18.2% (SAG2)**.
La autonomía estimada es 0h — no hay buffer para sostener ambas líneas. La detención
parcial protege la línea restante. También cuando una ventana T8 de duración > 8h
con pila inicial < 30% hace inevitable la caída a zona crítica (ver simulador).

### 7. ¿Cuándo detener preventivamente?
Cuando:
- pila_SAG2 < 18.2% → autonomía 0h, zona roja
- pila_SAG2 < 22% Y T8 activo → riesgo en las próximas 2-3h
- Simulación muestra que la ventana T8 llevará la pila a zona crítica antes de finalizar

### 8. ¿Cuál es la autonomía real de las pilas?
- **SAG2 P50:** 1.6h | **P25:** 1.0h | **P10:** 0.1h
- **Días con autonomía < 2h:** 89/151 (58.9%)
- La tasa de descarga calibrada es 6.18%/h (shrinkage bucket Larga ≥7h)
- Escenario crítico: pila=20%, T8=8h → pila_final=-29.4% (< zona crítica)

### 9. ¿Cuál es la mejor estrategia frente a una ventana T8?
1. **Anticipar:** aumentar nivel de pila ANTES del T8 (zona verde >48%)
2. **Monitorear cada 30min** durante el T8 cuando pila < 35%
3. **Reducir carga de alimentación** si pila < 28% durante T8 activo
4. **Coordinar con programación:** ventanas T8 cortas (<2h) con pila >50% = bajo impacto
5. **Evitar T8 acumulado >20h/semana** cuando el nivel promedio de pila es bajo

### 10. ¿Qué reglas deberían incorporarse al CIO o FRX Power BI?
```
REGLA 1: ALERTA ROJA si pila_SAG2 < 18.2%
REGLA 2: ALERTA NARANJA si pila_SAG2 < 28% Y horas_T8 > 4h
REGLA 3: KPI Autonomía = (pila - 18.2) / 6.18 (horas)
REGLA 4: KPI Drift = PSI(cv316_mean, rolling_30d vs baseline)
REGLA 5: RECOMENDACIÓN si autonomia_h < 2 → reducir carga
REGLA 6: RECOMENDACIÓN si autonomia_h < 0.5 → evaluar detención
REGLA 7: ALERTA si T8_acum_7d > 20h Y pila < 35%
REGLA 8: MODO = cluster KMeans (5 estados) → cambiar parámetros por modo
```

---

## Resumen de Eficiencia (skill_token_optimization_loop)

| Métrica | Valor |
|---------|-------|
| Experimentos repetidos | 0 (106 descartados permanentemente) |
| PKLs reutilizados | 2 (LightGBM, Ridge) |
| Modelos prohibidos respetados | XGBoost, CatBoost |
| GPU activada | No (151 filas) |
| Tiempo de ejecución | ~17s |
| Trials de búsqueda | 0 (no se necesitaron) |
| Archivos reutilizados | dataset_master.parquet, correas_ton.xlsx |

**Principio aplicado:** Algoritmo ≠ problema → Drift = problema → Solución = reglas + retrain mensual
