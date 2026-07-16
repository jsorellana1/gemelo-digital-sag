# Plan de Reorganización — Analytics / App Dash
## Proyecto 07_Rendimientos | División El Teniente
**Fecha:** 2026-06-30 | **Estado:** PLAN — pendiente aprobación

---

## 1. Objetivo

Separar el proyecto en dos líneas de trabajo claras dentro de `07_Rendimientos/`:

| Línea | Carpeta | Responsabilidad |
|-------|---------|-----------------|
| Laboratorio analítico | `analytics/` | Explorar, modelar, calibrar, reportar |
| Producto operacional | `app_dash/` | Simular, visualizar, recomendar |

---

## 2. Estructura objetivo

```text
07_Rendimientos/
├── analytics/
│   ├── notebooks/
│   │   ├── 00_master/
│   │   ├── 01_event_study/
│   │   ├── 02_pilas/
│   │   ├── 03_modelos/
│   │   ├── 04_metropolis_hastings/
│   │   └── 99_historicos/
│   ├── src/
│   │   ├── ingestion/
│   │   ├── preprocessing/
│   │   ├── event_study/
│   │   ├── causal_model/
│   │   ├── differential_equations/
│   │   ├── machine_learning/
│   │   ├── bayesian/
│   │   └── reporting/
│   ├── outputs/
│   │   ├── figures/      ← copia de outputs/figures/
│   │   ├── excel/        ← copia de outputs/excel/
│   │   ├── models/       ← data/cache/model_loop_v3_shap/*.pkl
│   │   └── reports/      ← copia de outputs/reports/
│   └── README.md
│
├── app_dash/
│   ├── app.py            ← desde apps/dash_molienda_t8/app.py
│   ├── assets/
│   │   └── styles.css
│   ├── components/
│   │   ├── __init__.py
│   │   ├── cards.py
│   │   ├── controls.py
│   │   └── graphs.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── mh_calibration.py
│   │   ├── ode_model.py
│   │   ├── realtime_loader.py
│   │   ├── risk_engine.py
│   │   ├── rules_engine.py
│   │   └── simulator.py
│   ├── data/
│   │   └── rules_config.yaml
│   ├── config/
│   │   ├── app_config.yaml    ← NUEVO
│   │   ├── rules_config.yaml  ← desde apps/dash_molienda_t8/data/
│   │   └── thresholds.yaml    ← NUEVO
│   ├── outputs/
│   │   ├── screenshots/
│   │   └── logs/
│   └── README.md
│
├── data/                 ← SIN CAMBIOS (compartido)
│   ├── raw/
│   ├── processed/
│   ├── intermediate/
│   └── cache/
│
├── config/
│   ├── config.yaml       ← ya existe
│   └── paths.yaml        ← NUEVO
│
├── Skills/               ← SIN CAMBIOS
├── docs/
│   ├── reorganizacion_analytics_dash.md  ← este archivo
│   ├── estado_actual_proyecto.md
│   ├── inventario_proyecto.xlsx
│   └── trazabilidad.xlsx
├── logs/                 ← SIN CAMBIOS
├── requirements.txt      ← SIN CAMBIOS
├── environment.yml       ← SIN CAMBIOS
├── README.md             ← ACTUALIZAR
└── archive/              ← archivar lo obsoleto
```

---

## 3. Inventario de archivos — qué va a dónde

### 3.1 → `analytics/notebooks/`

| Archivo actual | Destino | Categoría |
|---------------|---------|-----------|
| `notebooks/00_master_analisis_rendimientos_t8.ipynb` | `analytics/notebooks/00_master/` | master |
| `notebooks/01_Estrategia_Operacional_Pilas.ipynb` | `analytics/notebooks/02_pilas/` | pilas |
| `notebooks/02_Modelo_Dinamico_Pilas_SAG.ipynb` | `analytics/notebooks/02_pilas/` | pilas |
| `notebooks/03_Modelo_Hibrido_EDO_DataScience.ipynb` | `analytics/notebooks/03_modelos/` | modelos |

### 3.2 → `analytics/src/`

| Archivo actual | Destino | Descripción |
|---------------|---------|-------------|
| `src/advanced_t8_historical_analysis.py` | `analytics/src/event_study/` | análisis histórico T8 |
| `src/efecto_gaviota.py` | `analytics/src/event_study/` | efecto gaviota |
| `src/event_study_t8.py` | `analytics/src/event_study/` | event study |
| `src/estrategia_pilas.py` | `analytics/src/differential_equations/` | estrategia pilas |
| `src/modelo_dinamico.py` | `analytics/src/differential_equations/` | modelo dinámico |
| `src/modelo_dinamico_pilas.py` | `analytics/src/differential_equations/` | modelo dinámico pilas |
| `src/modelo_hibrido.py` | `analytics/src/differential_equations/` | modelo híbrido |
| `src/modelo_descarga_robusto.py` | `analytics/src/differential_equations/` | modelo descarga |
| `src/modelo_causal_operacional.py` | `analytics/src/causal_model/` | modelo causal |
| `src/modelo_adaptativo_decisional.py` | `analytics/src/causal_model/` | modelo adaptativo |
| `src/fase2_mecanismo_causal.py` | `analytics/src/causal_model/` | mecanismo causal |
| `src/shap_autonomia_kpi.py` | `analytics/src/machine_learning/` | SHAP |
| `src/model_loop_v3.py` | `analytics/src/machine_learning/` | model loop v3 |
| `src/model_advanced_loop.py` | `analytics/src/machine_learning/` | model loop avanzado |
| `src/model_improvement_loop.py` | `analytics/src/machine_learning/` | model improvement |
| `src/model_master_loop.py` | `analytics/src/machine_learning/` | model master loop |
| `src/informe_estrategico.py` | `analytics/src/reporting/` | informe estratégico |
| `src/export_model_loop_v3_pdf.py` | `analytics/src/reporting/` | export PDF |
| `src/generar_ppt_prescriptivo.py` | `analytics/src/reporting/` | PPT prescriptivo |
| `src/matriz_decision_operacional.py` | `analytics/src/reporting/` | matriz decisión |
| `src/optimizacion_rates_molienda.py` | `analytics/src/reporting/` | optimización rates |
| `src/sistema_rt_optimizacion_rates.py` | `analytics/src/reporting/` | sistema RT |
| `src/refactoring_utils.py` | `analytics/src/` | utils |
| `src/claude_utils.py` | `analytics/src/` | utils |
| `src/__init__.py` | `analytics/src/` | init |
| `_audit_fase2.py` | `analytics/src/` | script auditoría |
| `_check_libs.py` | `analytics/src/` | script libs |
| `_extract_metrics.py` | `analytics/src/` | script métricas |
| `_patch_gaviota.py` | `analytics/src/event_study/` | patch gaviota |
| `_skill_audit_informe.py` | `analytics/src/` | script auditoría |

### 3.3 → `analytics/outputs/`

Todo el directorio `outputs/` actual se mueve a `analytics/outputs/`:

| Origen | Destino |
|--------|---------|
| `outputs/figures/` | `analytics/outputs/figures/` |
| `outputs/excel/` | `analytics/outputs/excel/` |
| `outputs/reports/` | `analytics/outputs/reports/` |
| `figures_rendimientos/` | `analytics/outputs/figures/rendimientos_historicos/` |

**Nota:** `data/cache/model_loop_v3_shap/*.pkl` → `analytics/outputs/models/`

### 3.4 → `app_dash/`

Todo el directorio `apps/dash_molienda_t8/` se mueve a `app_dash/`:

| Origen | Destino |
|--------|---------|
| `apps/dash_molienda_t8/app.py` | `app_dash/app.py` |
| `apps/dash_molienda_t8/assets/` | `app_dash/assets/` |
| `apps/dash_molienda_t8/components/` | `app_dash/components/` |
| `apps/dash_molienda_t8/engine/` | `app_dash/engine/` |
| `apps/dash_molienda_t8/data/rules_config.yaml` | `app_dash/config/rules_config.yaml` |

### 3.5 → `archive/`

Archivos obsoletos o logs temporales:

| Archivo | Motivo |
|---------|--------|
| `C:Usersjorel038AppDataLocalTemp*.txt` | archivos temporales mal ruteados |
| `catboost_info/` | output de entrenamiento CatBoost (obsoleto) |
| `resumen_ejecutivo_rendimientos.md` | versión antigua, cubierto por outputs/reports |
| `output_rendimientos_pre_post_t8.xlsx` | archivo raíz, mover a analytics/outputs/excel/ |
| `rendimientos_coef - copia.xlsx` | copia sin usar |
| `src/reorganizar_proyecto.py` | script anterior de reorganización |

### 3.6 → SIN MOVER

| Ruta | Motivo |
|------|--------|
| `data/raw/` | datos fuente compartidos, no duplicar |
| `data/processed/` | compartido analytics + app |
| `data/cache/` (parquets y npy) | consumido por app_dash Y analytics |
| `Skills/` | skills del proyecto, sin cambio |
| `config/config.yaml` | config existente |
| `requirements.txt`, `environment.yml` | raíz del proyecto |
| `.claude/`, `.env` | configuración de entorno |

---

## 4. Cambios de imports requeridos en `app_dash/`

La app actualmente usa rutas calculadas desde su propio directorio:

```python
# ACTUAL (apps/dash_molienda_t8/app.py líneas 12-17):
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
# _ROOT = 07_Rendimientos/
```

Al mover a `app_dash/app.py`, la lógica cambia:

```python
# NUEVO (app_dash/app.py):
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)   # ← un nivel menos (era 2)
```

**Afecta:**
- `app.py` líneas 12-17: `_HERE` y `_ROOT`
- `engine/mh_calibration.py` líneas 18-20: `_ROOT` y `_CACHE`
- `engine/realtime_loader.py`: rutas a `data/cache/`
- `engine/ode_model.py`: si tiene rutas hardcodeadas (verificar)

**Cantidad de cambios de import:** 2-4 archivos, ~5 líneas en total.

---

## 5. Nuevo archivo: `config/paths.yaml`

```yaml
# Rutas centrales del proyecto 07_Rendimientos
root: .
data_raw: data/raw
data_processed: data/processed
data_intermediate: data/intermediate
data_cache: data/cache
analytics_outputs: analytics/outputs
analytics_src: analytics/src
analytics_notebooks: analytics/notebooks
dash_root: app_dash
dash_cache: app_dash/outputs
dash_config: app_dash/config
```

---

## 6. Orden de ejecución recomendado

**Paso 1 — Crear estructura vacía** (sin mover nada)
```bash
mkdir analytics/ analytics/notebooks analytics/src analytics/outputs
mkdir analytics/notebooks/00_master analytics/notebooks/01_event_study
mkdir analytics/notebooks/02_pilas analytics/notebooks/03_modelos
mkdir analytics/notebooks/04_metropolis_hastings analytics/notebooks/99_historicos
mkdir analytics/src/ingestion analytics/src/preprocessing
mkdir analytics/src/event_study analytics/src/causal_model
mkdir analytics/src/differential_equations analytics/src/machine_learning
mkdir analytics/src/bayesian analytics/src/reporting
mkdir analytics/outputs/figures analytics/outputs/excel
mkdir analytics/outputs/models analytics/outputs/reports
mkdir app_dash/ app_dash/assets app_dash/components
mkdir app_dash/engine app_dash/data app_dash/config
mkdir app_dash/outputs app_dash/outputs/screenshots app_dash/outputs/logs
```

**Paso 2 — Mover archivos analíticos** (notebooks, src/, outputs/)
- No tiene dependencias. Seguro.

**Paso 3 — Mover app_dash y actualizar 2-4 rutas internas**
- Actualizar `_ROOT` en app.py y mh_calibration.py
- Validar con `python -c "import app"` desde app_dash/

**Paso 4 — Crear READMEs y config/paths.yaml**
- No afecta código

**Paso 5 — Archivar obsoletos**
- Mover a archive/

**Paso 6 — Validación**
- `cd app_dash && python app.py` → debe arrancar sin errores
- Verificar que `data/cache/` siga accesible desde ambos lados
- Ejecutar smoke test del notebook master

---

## 7. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| Rutas rotas en app_dash | MEDIA | Solo 2-4 líneas cambian; validar inmediatamente |
| Notebooks con imports absolutos | BAJA | Los notebooks usan `sys.path.insert` relativo |
| Datos duplicados | BAJA | `data/` queda compartido; NO copiar |
| Git history perdido | ALTA | Usar `git mv` en vez de `mv` para preservar historial |

---

## 8. Archivos que NO existen todavía (crear en la migración)

| Archivo | Contenido |
|---------|-----------|
| `analytics/README.md` | Guía de análisis, notebooks principales, flujo |
| `app_dash/README.md` | Cómo correr Dash, páginas, configuración |
| `README.md` (actualizar) | Vista general, diferencia analytics vs app_dash |
| `config/paths.yaml` | Rutas centrales del proyecto |
| `app_dash/config/app_config.yaml` | Config del dashboard: puerto, thresholds clave |
| `app_dash/config/thresholds.yaml` | SAG1 crit=15%, SAG2 crit=18.2%, etc. |

---

## 9. Criterio de éxito

```
✓ python app_dash/app.py  → arranca en puerto 8050 sin errores
✓ Todas las páginas del dashboard responden
✓ analytics/ contiene notebooks, src, outputs
✓ data/raw/ no duplicado
✓ git log en app_dash/app.py preserva historial (git mv)
✓ README.md raíz explica la arquitectura
✓ config/paths.yaml existe
```

---

## 10. Estimado de esfuerzo

| Tarea | Tiempo |
|-------|--------|
| Crear estructura directorios | 5 min |
| Mover analytics (notebooks, src, outputs) | 10 min |
| Mover app_dash + fix rutas | 15 min |
| Crear READMEs + configs | 20 min |
| Validación y smoke test | 10 min |
| **Total estimado** | **~60 min** |

---

*Generado: 2026-06-30 | Proyecto: AA_CIO_DET/07_Rendimientos*
