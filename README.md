> **Nota sobre este repositorio (GitHub):** este es un espejo de **código
> únicamente**. Los datos operacionales de planta (`01_Data/`) y los modelos
> calibrados con datos reales (`03_Models/`) NO se versionan aquí — viven
> solo en el repositorio interno de la organización. Para correr el
> simulador con datos reales, cloná este repo y copiá esas carpetas desde el
> entorno interno siguiendo `07_Config/paths.yaml`.

# Rendimientos Molienda — Impacto Teniente 8

## División El Teniente — Codelco | CIO Analytics

### Gemelo Digital Operacional | Actualizado 2026-07-09

---

## Descripción ejecutiva

**Qué problema resuelve:** las ventanas de mantenimiento Teniente 8 (T8)
interrumpen la alimentación de mineral a los molinos SAG1, SAG2, PMC y MUN,
generando riesgo de vaciado o desborde de pilas y pérdida de tonelaje. Este
proyecto responde, con evidencia cuantitativa y un simulador en vivo, dos
preguntas: *"¿cuánto se pierde por T8?"* (análisis histórico) y *"¿cómo debo
operar ahora mismo para minimizar el riesgo y maximizar producción?"*
(gemelo digital + optimizador).

El proyecto pasó de ser un análisis exploratorio a un **Gemelo Digital
Operacional**: un simulador ODE calibrado con datos reales, un optimizador
que recomienda rate y molinos de bolas respetando restricciones duras
(inventario, mantenciones, regla R16), y un dashboard tipo centro de
control que un Jefe de Sala puede leer en segundos.

---

## Inicio rápido

```bash
# Dashboard operacional (Gemelo Digital)
cd 05_Dashboard && python app.py
# → http://localhost:8050

# Análisis exploratorio
jupyter notebook 02_Analytics/Notebooks/00_master/
```

Ver también: [`ROADMAP.md`](ROADMAP.md) (qué está implementado/en desarrollo),
[`CHANGELOG.md`](CHANGELOG.md) (evolución por hitos),
[`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) (árbol de carpetas comentado),
[`PROJECT_INDEX.md`](PROJECT_INDEX.md) (dónde está cada cosa),
[`08_Skills/skill_master_project.md`](08_Skills/skill_master_project.md)
(primer documento que debe leer cualquier IA o persona nueva).

---

## Empaquetado portable (.exe)

**`05_Dashboard/` es la única fuente de verdad.** El portable
(`05_Dashboard/dist/Gemelo_Digital_Molienda/`) se construye siempre desde
ahí — nunca al revés.

```text
Nunca editar directamente archivos dentro de dist/.
Todo cambio debe hacerse en 05_Dashboard/ y luego reconstruir portable.
```

- Código/motor/UI → `05_Dashboard/{app.py,pages/,components/,engine/}`
- Datos runtime → `05_Dashboard/{runtime_data/,assets/,config/}`
- Documentos de entrega (README de usuario, guía de validación, formulario
  de feedback, `VERSION.txt`, `QA_CHECKLIST.md`) → `05_Dashboard/packaging/`
- Build oficial: `python 05_Dashboard/scripts/build_portable.py`
- Detectar divergencia (¿alguien editó `dist/` a mano?):
  `python 05_Dashboard/scripts/sync_portable_to_dev.py`

**v1.2.0 (2026-07-09):** dos optimizaciones medidas (no estimadas) en el
optimizador (`find_optimal_v3`): eliminación de un `dir()` en el loop
caliente del ODE (-31.7% del tiempo, verificado bit-idéntico) y
normalización de valores antes de hashear el cache de escenarios (el
cache pasó de 44.7% a un hit ratio mayor al no invalidarse por ruido de
redondeo de sliders). Impacto conjunto medido: `find_optimal_v3` bajó de
~5.2s a ~2.2s promedio (benchmark de 9 escenarios, P90 3.06s). Detalle
completo en
[`04_Reports/Technical/20260709_Optimizer_V3_Production_Deployment.md`](04_Reports/Technical/20260709_Optimizer_V3_Production_Deployment.md).

---

## Arquitectura

```
07_Rendimientos/

├── 01_Data/            DATOS
│   ├── Raw/            ← PAM Mantto/Producción, tonelajes originales
│   ├── Processed/      ← datasets maestros Parquet
│   ├── Features/       ← features derivadas (ex intermediate/)
│   ├── Cache/          ← parquets y .npy precalculados (MH posteriors, event windows)
│   └── Validation/
│
├── 02_Analytics/       CIENCIA DE DATOS
│   ├── Notebooks/      ← Jupyter notebooks por fase (00_master → 08_MH)
│   ├── Scripts/        ← Python: event_study, causal_model, EDO, ML, reporting
│   └── Figures/        ← ~290 figuras organizadas por análisis
│
├── 03_Models/          MODELOS
│   ├── Production/     ← Ridge, ElasticNet, capa1/capa2 ACTIVOS
│   ├── Experimental/   ← challengers, historicos
│   ├── Bayesian/       ← (posteriors MH en 01_Data/Cache)
│   ├── Risk/
│   └── Registry/       ← model_registry_v3.xlsx, trazabilidad
│
├── 04_Reports/         ENTREGABLES
│   ├── Executive/      ← PDFs para jefaturas
│   ├── Technical/      ← reportes metodológicos MD/PDF
│   ├── Presentations/  ← PPT comités
│   └── Tables/         ← Excel analíticos (KPIs, datasets, simulaciones)
│
├── 05_Dashboard/       PRODUCTO OPERACIONAL (Gemelo Digital)
│   ├── app.py          ← entry point → http://localhost:8050; navbar y 4 paginas
│   │                      (Curvas Historicas, What-If, Que pasa si..., router)
│   ├── pages/           ← simulador_operacional.py: pagina "/" (default),
│   │                      Centro de Control con Gantt, semaforo, MC en vivo
│   ├── engine/          ← simulator, ode_model, optimizer_v2/v3, scheduler
│   │                      (turnos/mantenciones), risk_engine, rules_engine,
│   │                      mh_calibration, realtime_loader
│   ├── components/      ← graphs, cards, controls (UI reutilizable)
│   ├── assets/          ← CSS
│   └── config/          ← thresholds.yaml, app_config.yaml, rules_config.yaml
│
├── 06_Documentation/   CONOCIMIENTO
│   ├── Methodology/
│   ├── Operational_Rules/  ← reglas R01-R09, R16 (motivación, validación, estado)
│   └── Reorganization/ ← inventario y reportes de reorganización
│
├── 07_Config/          CONFIGURACIÓN
├── 08_Skills/          REGLAS IA (19 skills de dominio)
├── 09_Logs/            AUDITORÍA
├── 99_Archive/         HISTÓRICO (nunca eliminar)
│
├── README.md
├── requirements.txt
└── environment.yml
```

## Flujo de datos

```
01_Data/Raw/
    ↓ (ingestion scripts)
01_Data/Processed/
    ↓ (analytics notebooks)
02_Analytics/  →  03_Models/
    ↓ (reporting scripts)
04_Reports/
    ↓ (dashboard consumes cache + processed)
05_Dashboard/  →  usuarios operacionales
```

---

## Componentes

| Componente | Qué hace | Dónde vive |
|---|---|---|
| **Rendimientos** | KPIs operacionales, EDA, change points por activo (SAG1/SAG2/PMC/MUN) | `02_Analytics/Notebooks/00_master/`, `02_Analytics/Scripts/` |
| **Efecto Gaviota** | Cuantifica la caída de TPH pre/post ventana T8 y su recuperación | `02_Analytics/Scripts/event_study/` |
| **Modelo Causal** | Relaciona inventario de pilas con disponibilidad/decisión operacional | `02_Analytics/Scripts/causal_model/` |
| **EDO (Ecuaciones Diferenciales)** | Simula la dinámica de pilas SAG1/SAG2 minuto a minuto (balance de masa) | `05_Dashboard/engine/ode_model.py`, `02_Analytics/Scripts/differential_equations/` |
| **Monte Carlo adaptativo** | Cuantifica incertidumbre (pila, feed, T8) sobre cada configuración candidata, con parada temprana por convergencia | `05_Dashboard/engine/optimizer_v2.py` (`adaptive_mc_eval`) |
| **Metropolis-Hastings** | Calibra parámetros bayesianos del modelo de riesgo (P(sobrevive\|T8, pila)) | `05_Dashboard/engine/mh_calibration.py` |
| **Optimizer V3** | Grilla determinística (rate × bolas, por régimen) + Monte Carlo + Pareto → recomienda rate/bolas óptimo respetando restricciones duras (inventario, mantenciones, regla R16) | `05_Dashboard/engine/optimizer_v3.py`, `optimizer_v2.py` |
| **Dashboard (Gemelo Digital)** | Simulador operacional, Centro de Control (Gantt de disponibilidad, semáforo, MC en vivo), "¿Qué pasa si...?", What-If | `05_Dashboard/pages/simulador_operacional.py`, `app.py` |

---

## Flujo operacional (Gemelo Digital)

```
Inventario (pila SAG1/SAG2 %, turno)
    ↓
Alimentación (CH1/CH2 → T1/T3 → CV315/CV316, con mantenciones como restricción dura)
    ↓
Molienda (SAG1/SAG2 + molinos de bolas 411/412/511/512, regla R16: min. 1 bola activa por SAG)
    ↓
Optimización (Optimizer V3: grilla + Monte Carlo + Pareto, filtra escenarios físicamente imposibles)
    ↓
Simulación (ODE, Monte Carlo en vivo al mover cualquier slider) → recomendación + banda de confianza + riesgo por hora
```

Ver el detalle técnico de cada modelo en `06_Documentation/` (documentación
profunda por modelo pendiente, ver `ROADMAP.md`) y las reglas operacionales
vigentes en [`06_Documentation/Operational_Rules/README.md`](06_Documentation/Operational_Rules/README.md).

## Skills y CLAUDE.md

Antes de cualquier cambio, revisar el `CLAUDE.md` del subdirectorio correspondiente.
Skills en `08_Skills/` — 18 archivos de dominio (SAG, Bayesiano, MLOps, UX, etc.).

---

## Setup Rápido

### Opción 1: Script automático (recomendado)
```batch
setup_entorno.bat
```

### Opción 2: Manual
```bash
python -m venv sag
sag\Scripts\activate          # Windows
pip install -r requirements.txt
python -m ipykernel install --user --name=sag --display-name "Python (sag)"
jupyter lab
```

### Opción 3: Conda
```bash
conda env create -f environment.yml
conda activate sag
jupyter lab
```

---

## Uso

1. Activar entorno: `sag\Scripts\activate`
2. Abrir JupyterLab: `jupyter lab`
3. Abrir: `notebooks/01_Analisis_Rendimientos_Molienda.ipynb`
4. Ejecutar: **Kernel → Restart & Run All**

---

## Fuentes de Datos

| Fuente | Ubicación | Contenido |
|--------|-----------|-----------|
| PAM Producción | `data/raw/PAM_Produccion/*.xlsx` | Producción diaria programada |
| PAM Mantto | `data/raw/PAM_Mantto/*.xlsx` | Mantenciones planificadas |
| Rendimientos | `data/raw/Rendimientos/*.xlsx` | TPH cada 5 minutos |

**Nota:** El sistema también detecta los archivos en la raíz del proyecto (`PAM_Produccion/`, etc.)
para compatibilidad con la estructura anterior.

---

## Activos Analizados

| ID | Nombre | Tipo | Pila Alimentación |
|----|--------|------|-------------------|
| SAG1 | Molino SAG 1 | SAG | Pila SAG (mineral grueso) |
| SAG2 | Molino SAG 2 | SAG | Pila SAG (mineral grueso) |
| PMC | Molienda Convencional (Mol. 1-12) | Convencional | Pila Conv. |
| MUN | Molino Unitario (Mol. 13) | Unitario | Pila Conv. |

---

## Modelos Implementados

| # | Modelo | Técnica | Output |
|---|--------|---------|--------|
| 1 | KPIs Operacionales | Estadística descriptiva | Tabla resumen |
| 2 | Análisis Pre/Post T8 | Ventanas configurable | Delta TPH, impacto |
| 3 | Detección Change Points | `ruptures` PELT | Quiebres estructurales |
| 4 | Consumo Pilas | Modelo stock diferencial | Índice agotamiento |
| 5 | Anomaly Detection | Isolation Forest | Anomalías por activo |
| 6 | Clustering Operacional | KMeans | Régimen operacional |
| 7 | Predicción TPH | XGBoost Regressor | Forecast 1/4/12/24h |
| 8 | Probabilidad Bayesiana | Inferencia conjugada | P(caída\|T8) |
| 9 | SHAP Explainability | TreeExplainer | Drivers de caída |
| 10 | IGI T8 | Índice compuesto | Score impacto 0-100 |
| 11 | Dinámica de pilas (EDO) | Ecuaciones diferenciales, balance de masa | Trayectoria pila/TPH minuto a minuto |
| 12 | Monte Carlo adaptativo | Muestreo con parada por convergencia | P(seguro), bandas P10-P90 |
| 13 | Metropolis-Hastings | Calibración bayesiana | Posterior de riesgo P(sobrevive\|T8,pila) |
| 14 | Optimizer V3 | Grilla + Monte Carlo + Pareto | Rate/bolas recomendado por régimen |

Ver detalle de cada modelo (objetivo, entradas, salidas, supuestos,
limitaciones) — documentación profunda pendiente, ver `ROADMAP.md`.

---

## Skills del Dominio

Ubicados en `08_Skills/` (18 skills). **Empezar siempre por**
[`skill_master_project.md`](08_Skills/skill_master_project.md) — es el
primer documento que cualquier IA o persona nueva debe leer.

| Skill | Descripción |
|-------|-------------|
| skill_master_project | Vision general del proyecto, arquitectura, convenciones — leer primero |
| skill_molienda_sag | Proceso SAG, PMC, MUN. KPIs, pilas, T8 |
| skill_series_temporales_industriales | Preprocesamiento, features, change points |
| skill_machine_learning_operacional | XGBoost, clustering, SHAP, IGI T8 |
| skill_operaciones_mina_subterranea | Teniente 8, ferrocarril, tipos de ventana |
| skill_process_mining_industrial | Estados operacionales, star schema BI |
| skill_data_scientist_senior | ML avanzado, pipelines, validación |
| skill_estadistica_bayesiana_avanzada | Inferencia Bayesiana, intervalos credibilidad |
| skill_forecasting_industrial | Forecasting probabilístico industrial |

---

## Criterio de Éxito

El análisis responde cuantitativamente:

1. ¿Qué activo es más sensible a Teniente 8?
2. ¿Cuánto tarda cada activo en recuperarse?
3. ¿Existe evidencia de agotamiento de pilas?
4. ¿Cuánto pierde cada activo por ventana?
5. ¿Qué variables explican la caída?
6. ¿Puede predecirse la caída futura?
7. ¿Qué ventanas históricas fueron las más críticas?

---

*Proyecto: Analítica CIO DET — AA_CIO_DET / 07_Rendimientos*
*Contacto: juanorellana.g@gmail.com*
