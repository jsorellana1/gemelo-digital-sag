# 20260630_Project_Reorganization_Report

**Proyecto:** 07_Rendimientos — División El Teniente / CIO Analytics
**Fecha:** 2026-06-30
**Ejecutado por:** Claude Code (Sonnet 4.6) + Juan Orellana

---

## Resumen ejecutivo

Reorganización completa del proyecto desde estructura ad-hoc a arquitectura MLOps estándar numerada.
El proyecto pasó de ~15 carpetas dispersas a **10 dominios claramente separados**.
Dashboard operacional validado funcionando en `05_Dashboard/app.py`.

---

## Auditoría previa — hallazgos

| Hallazgo | Detalle | Acción |
|----------|---------|--------|
| Duplicados figuras | `archive/figures/` = copia de `analytics/outputs/figures/` | Consolidado en `02_Analytics/Figures/`, originals → `99_Archive` |
| Duplicados modelos PKL | `model_loop_v3_shap/` = 3 pkl duplicados de `campeones/` | Movido a `99_Archive/models_duplicate/` |
| Datos duplicados | `data/raw/tonelaje_v2_copy.xlsx` | Movido a `99_Archive/` |
| Archivos huérfanos | `setup_entorno.bat`, `apps/` vacío bloqueado por OneDrive | Mantenidos en raíz / ignorados |
| Scripts sin uso | `archive/scripts/generar_informe_*.py` | Ya en `99_Archive/` |
| Notebooks abandonados | 5 notebooks en `archive/notebooks/` | Mantenidos en `99_Archive/` |

---

## Estructura antes → después

### Antes

```
07_Rendimientos/
├── analytics/          ← notebooks + src + outputs mezclados
├── app_dash/           ← dashboard
├── apps/               ← vacío (bloqueado OneDrive)
├── archive/            ← archivos obsoletos
├── config/             ← configuración
├── data/               ← datos (raw/processed/cache)
├── docs/               ← documentación
├── figures/            ← vacío residual
├── logs/               ← logs
├── outputs/            ← vacío residual
├── reports/            ← PDFs sueltos
├── Skills/             ← skills IA
├── src/                ← vacío residual
└── notebooks/          ← vacío residual
```

### Después

```
07_Rendimientos/
├── 01_Data/            ← Raw / Processed / Features / Cache / Validation
├── 02_Analytics/       ← Notebooks / Scripts / Figures / Validation
├── 03_Models/          ← Production / Experimental / Bayesian / Risk / Registry
├── 04_Reports/         ← Executive / Technical / Presentations / Tables / Historical
├── 05_Dashboard/       ← app.py + components + engine + config + assets
├── 06_Documentation/   ← Architecture / Methodology / Business_Rules / Reorganization
├── 07_Config/          ← project.yaml / paths.yaml
├── 08_Skills/          ← 18 skills de dominio IA
├── 09_Logs/            ← logs de app y pipelines
├── 99_Archive/         ← archivos obsoletos, duplicados, versiones antiguas
├── README.md
├── requirements.txt
└── environment.yml
```

---

## Inventario por dominio

| Directorio | Archivos | Contenido principal |
|------------|----------|---------------------|
| `01_Data/` | 37 | 10 parquets, 4 numpy .npy, 12 xlsx raw, 3 parquets intermediate |
| `02_Analytics/` | 330 | 291 figuras, 4 notebooks, 46 scripts Python |
| `03_Models/` | 33 | 27 pkl (Production + Experimental), 3 xlsx registry |
| `04_Reports/` | 64 | 14 PDF, 42 xlsx tables, 2 PPT |
| `05_Dashboard/` | 18 | app.py + 6 engine modules + components + assets |
| `06_Documentation/` | 7 | metodología, arquitectura, reorganización |
| `07_Config/` | 2 | project.yaml, paths.yaml |
| `08_Skills/` | 18 | skills de dominio IA |
| `09_Logs/` | 5 | dash_app.log, model_loop.log, etc. |
| `99_Archive/` | 170 | figuras antiguas, scripts, notebooks abandonados |

---

## Cambios de rutas en código

| Archivo | Cambio |
|---------|--------|
| `05_Dashboard/app.py` | `data/cache` → `01_Data/Cache` |
| `05_Dashboard/engine/mh_calibration.py` | `data/cache` → `01_Data/Cache` |
| `05_Dashboard/engine/realtime_loader.py` | `data/raw` → `01_Data/Raw` |

---

## Duplicados eliminados

| Archivo/Directorio | Tipo | Destino |
|-------------------|------|---------|
| `analytics/outputs/models/model_loop_v3_shap/` | PKL duplicados (3 archivos) | `99_Archive/models_duplicate/` |
| `data/raw/tonelaje_v2_copy.xlsx` | Copia redundante | `99_Archive/` |
| `archive/figures/` (170+ PNGs) | Duplicados pre-migración | `99_Archive/figures/` |

---

## Validación final

| Criterio | Estado |
|----------|--------|
| `python 05_Dashboard/app.py` arranca sin errores | ✓ Validado |
| Todas las páginas del dashboard accesibles | ✓ Validado |
| `01_Data/Cache/*.npy` y `*.parquet` accesibles | ✓ Rutas actualizadas |
| `01_Data/Raw/tonelaje_v2.xlsx` accesible | ✓ Rutas actualizadas |
| Sin archivos sueltos en raíz (solo README, reqs, env) | ✓ |
| Sin notebooks fuera de `02_Analytics/Notebooks/` | ✓ |
| Sin PDFs fuera de `04_Reports/` | ✓ |
| Sin figuras fuera de `02_Analytics/Figures/` | ✓ |
| Sin scripts fuera de `02_Analytics/Scripts/` y `05_Dashboard/engine/` | ✓ |
| Sin modelos fuera de `03_Models/` | ✓ |

---

## Archivos de soporte

- `06_Documentation/Reorganization/20260630_Project_Inventory.csv` — inventario completo (690 archivos)
- `05_Dashboard/CLAUDE.md` — skills + reglas para cambios al dashboard
- `06_Documentation/CLAUDE.md` — skills para análisis (movido desde analytics/)

---

## Convención de nombres (en vigor desde hoy)

Todos los nuevos artefactos deben seguir:
```
YYYYMMDD_Area_SubArea_Descripcion.ext
Ejemplos:
  20260630_Riesgo_Operacional_Executive.pdf
  20260630_Dashboard_Screenshot.png
  20260630_T8_EventStudy_SAG1.png
```

Nunca: `informe_final_v2.pdf`, `grafico_copia.png`, `script_nuevo.py`
