# Reporte Ejecutivo — Plataforma Analítica de Rendimientos de Molienda
## División El Teniente — Codelco
### Evaluación Pre / Durante / Post Ventanas Teniente 8

---

## 1. Resumen Ejecutivo

Esta plataforma analítica evalúa el impacto operacional de las ventanas de mantenimiento
de Teniente 8 sobre los circuitos de molienda SAG 1, SAG 2, PMC (Molinos 1-12) y MUN
(Molino Unitario/13), utilizando datos reales de rendimiento a 5 minutos y programas
PAM de producción y mantenimiento.

---

## 2. Alcance y Fuentes de Datos

| Fuente | Cobertura | Granularidad |
|--------|-----------|--------------|
| PAM Producción | Enero–Junio 2026 | Diaria (TMS/día por activo) |
| PAM Mantto | Enero–Junio 2026 | Diaria (horas T8 planificadas) |
| Rendimientos reales | Ene 1 – Jun 14 2026 | 5 minutos (TPH) |

**Total registros:** ~47,500 observaciones de 5 minutos × 4 activos

---

## 3. Ventanas Teniente 8 Identificadas

El sistema detecta automáticamente días con mantenimiento T8 desde PAM Mantto
(hoja "Ejecutivo Mensual", fila "TENIENTE 8", columnas G+ = días del mes).

**Resumen por mes:**

| Mes | Días con T8 | Horas planificadas | Evento mayor |
|-----|-------------|-------------------|--------------|
| Enero 2026 | 15 | ~68 h | — |
| Febrero 2026 | 11 | ~50 h | — |
| Marzo 2026 | 14 | ~108 h | MGA días 17-20 (72h) |
| Abril 2026 | 10 | ~60 h | — |
| Mayo 2026 | 11 | ~52 h | — |
| Junio 2026 | 11 | ~52 h | — |

---

## 4. Modelos Implementados

### Modelo 1 — KPIs Operacionales
Calcula utilización, TPH p50/p75/p90, horas operativas/detenidas, toneladas acumuladas.

### Modelo 2 — Análisis Pre/Post T8
Para cada ventana y horizonte (24h/48h/72h): delta TPH%, toneladas pre vs post,
clasificación de impacto (Sin/Leve/Medio/Alto).

### Modelo 3 — Detección de Change Points
Usa `ruptures` (PELT + RBF) para detectar quiebres estructurales en la serie TPH.
Si `ruptures` no está instalado, usa z-score como proxy.

### Modelo 4 — Consumo de Pilas
Modelo diferencial: `stock(t) = Σ(alimentación - consumo)`.
Durante T8: alimentación = 0. Genera índice 0-100 de stock relativo.

### Modelo 5 — Anomaly Detection (Isolation Forest)
Detecta comportamientos anómalos en TPH, rolling mean, rolling std.
`contamination = 5%` como referencia inicial.

### Modelo 6 — Clustering Operacional (KMeans k=4)
Clasifica cada período en: Normal / Inestable / Degradado / Recuperación.
Centroides interpretados por nivel de TPH.

### Modelo 7 — Predicción TPH (XGBoost)
Entrena modelos por activo para horizontes 1h/4h/12h/24h.
Validación con TimeSeriesSplit (5 folds). Features: lags, rolling, contexto T8, temporales.

### Modelo 8 — Probabilidad Bayesiana
`P(Caída > 10% | Ventana T8)` con prior Beta(1,1) y posterior actualizado por datos.
Genera intervalos de credibilidad al 90%.

### Modelo 9 — SHAP Explainability
Explica los drivers de TPH por activo. Identifica si `en_ventana_t8` y `h_desde_inicio_t8`
aparecen entre los features más importantes.

### Modelo 10 — IGI T8 (Índice Global de Impacto)
Score compuesto 0-100:
- 40% caída TPH
- 30% tiempo de recuperación al 95%
- 20% desviación del programa
- 10% duración de ventana

---

## 5. Criterios de Éxito — Respuestas Cuantitativas

| Pregunta | Dónde encontrar la respuesta |
|----------|------------------------------|
| ¿Qué activo es más sensible? | IGI T8 promedio + P(caída) Bayesiana — Sección 11 |
| ¿Cuánto tarda en recuperarse? | Columna `*_h_rec_95` en df_igi — Sección 11 |
| ¿Agotamiento de pilas? | Índice stock + pendiente durante T8 — Sección 08 |
| ¿Pérdida por ventana? | `delta_pct` por activo × ventana — Sección 07 |
| ¿Variables que explican la caída? | SHAP values o Feature Importance — Sección 11 |
| ¿Puede predecirse? | Métricas XGBoost (MAE, R²) — Sección 10 |
| ¿Ventanas más críticas? | IGI_total = promedio IGI activos — Sección 11 |

---

## 6. Arquitectura de Datos

### Star Schema (Parquet en `data/processed/`)

```
Fact_Rendimiento     ──── Dim_Activo
     │                        
     ├── activo_id             
     ├── fecha                Dim_Fecha
     ├── tph                       
     ├── ton               Dim_Evento
     ├── contexto
     └── ventana_id ──── Fact_Eventos_T8
```

Compatible con Power BI, Databricks, Microsoft Fabric.

---

## 7. Cómo Usar Esta Plataforma

### Setup inicial
```batch
setup_entorno.bat
```

### Ejecución del análisis
```bash
sag\Scripts\activate
jupyter lab
# Abrir: notebooks/01_Analisis_Rendimientos_Molienda.ipynb
# Ejecutar: Kernel > Restart & Run All
```

### Agregar nuevos meses
Copiar Excel en `PAM_Produccion/` y `PAM_Mantto/`.
Re-ejecutar el notebook completo. Sin cambios de código necesarios.

---

## 8. Skills del Dominio Aplicados

| Skill | Aplicación |
|-------|-----------|
| `skill_molienda_sag` | KPIs, interpretación TPH, estructura PAM |
| `skill_series_temporales_industriales` | Rolling, lags, features, change points |
| `skill_machine_learning_operacional` | XGBoost, clustering, SHAP, IGI T8 |
| `skill_operaciones_mina_subterranea` | Contexto T8, tipos de ventana, pilas |
| `skill_process_mining_industrial` | Star schema, estados operacionales |
| `skill_estadistica_bayesiana_avanzada` | P(caída\|T8), intervalos credibilidad |

---

## 9. Decisiones de Diseño Documentadas

| Decisión | Justificación |
|----------|---------------|
| `TPH_THRESHOLD = 50` | Valores menores son coeficientes de estado, no TPH reales |
| PRE/POST = 24/48/72h | Captura efectos inmediatos, de turno y de guardia |
| Gap máx. 2 días para agrupar ventanas | Ventanas separadas por 1 día comparten contexto operacional |
| Mediana como tasa histórica de pila | Robusta a outliers operacionales |
| TimeSeriesSplit (no KFold) | Evita leakage temporal en predicción |
| Parquet como formato intermedio | Compatible con BI, Spark, Pandas; compresión eficiente |

---

*Generado: 2026-06-15 | Proyecto: AA_CIO_DET / 07_Rendimientos*
