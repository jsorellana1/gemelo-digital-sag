# Estructura del Proyecto

*Verificado contra el filesystem real el 2026-07-02 — no es un diagrama
aspiracional.*

```
07_Rendimientos/
│
├── 01_Data/                    DATOS
│   ├── Raw/                    ← PAM Producción/Mantto, tonelajes, estados_activos.xlsx
│   │                              (única fuente con estado ON/OFF por molino de bolas individual)
│   ├── Processed/               ← datasets maestros Parquet (dataset_master, fact_*, dim_*)
│   ├── Features/                 ← features derivadas (eventos_t8, ventanas_t8, rendimientos_clean)
│   ├── Cache/                    ← precalculados: posteriors MH, ventanas de eventos, cache del optimizer
│   └── Validation/
│
├── 02_Analytics/                CIENCIA DE DATOS (exploración, no producción)
│   ├── Notebooks/                ← Jupyter por fase (00_master, 02_pilas, 03_modelos)
│   ├── Scripts/                  ← event_study/, causal_model/, differential_equations/,
│   │                                machine_learning/, reporting/, ingestion/
│   └── Figures/                  ← figuras generadas por los notebooks/scripts
│
├── 03_Models/                    MODELOS ENTRENADOS
│   ├── Production/               ← modelos activos (Ridge, ElasticNet, capa1/capa2)
│   ├── Experimental/              ← challengers, históricos
│   ├── Bayesian/                  ← referencia (posteriors reales viven en 01_Data/Cache)
│   ├── Risk/
│   └── Registry/                  ← trazabilidad de modelos (Excel)
│
├── 04_Reports/                    ENTREGABLES
│   ├── Executive/                  ← PDFs para jefaturas
│   ├── Technical/                   ← reportes metodológicos .md (EDA, EventStudy, Pilas,
│   │                                   Modelos, SHAP, Optimizer, MH, R16, UX/UI — ver PROJECT_INDEX.md)
│   ├── Presentations/                ← PPT para comités
│   └── Tables/                        ← Excel analíticos
│
├── 05_Dashboard/                  PRODUCTO OPERACIONAL — Gemelo Digital
│   ├── app.py                      ← entry point (`python app.py` → :8050); navbar,
│   │                                   ruteo, páginas Curvas Históricas / What-If / ¿Qué pasa si...?
│   ├── pages/                       ← simulador_operacional.py: página "/" (default),
│   │                                   Centro de Control (Gantt, semáforo, MC en vivo)
│   ├── engine/                       ← simulator.py, ode_model.py, optimizer_v2.py,
│   │                                   optimizer_v3.py, scheduler.py (turnos/mantenciones),
│   │                                   risk_engine.py, rules_engine.py, mh_calibration.py,
│   │                                   realtime_loader.py
│   ├── components/                    ← graphs.py, cards.py, controls.py (UI reutilizable)
│   ├── assets/                         ← styles.css
│   ├── config/                          ← app_config.yaml, rules_config.yaml (R01-R09),
│   │                                        thresholds.yaml
│   ├── outputs/                          ← logs de la app
│   └── README.md, CLAUDE.md               ← protocolo de trabajo para esta carpeta
│
├── 06_Documentation/                CONOCIMIENTO
│   ├── README.md, CLAUDE.md            ← protocolo de trabajo para 02_Analytics/
│   ├── estado_actual_proyecto.md        ← snapshot de estado (2026-06-18)
│   ├── reorganizacion_analytics_dash.md  ← propuesta PENDIENTE de aprobación
│   ├── propuesta_mejora_modelo_v3.md
│   ├── Methodology/                       ← arquitectura_proyecto.md
│   ├── Reorganization/                     ← inventario y reporte de reorganización (2026-06-30)
│   ├── Operational_Rules/                   ← documentación de reglas R01-R09, R16
│   ├── Architecture/, Decisions/, Diagrams/,  ← scaffolding vacío, sin contenido aún
│   │   limites_tecnicos/, presentaciones/,
│   │   referencias_operacionales/
│   └── inventario_proyecto.xlsx, trazabilidad.xlsx
│
├── 07_Config/                        CONFIGURACIÓN GLOBAL
│   ├── config.yaml
│   └── paths.yaml
│
├── 08_Skills/                         REGLAS/CONTEXTO PARA IA (19 archivos tras esta sesión)
│   ├── skill_master_project.md          ← NUEVO: leer primero
│   └── skill_*.md                        ← 18 skills de dominio (SAG, Bayesiano, MLOps, UX, etc.)
│
├── 09_Logs/                            AUDITORÍA (logs de app, inventario, reorganización)
├── 99_Archive/                          HISTÓRICO (nunca eliminar)
├── AA_DET_Pilas_SAG/                     clon de referencia del repo remoto (ver .gitignore)
│
├── README.md, ROADMAP.md, CHANGELOG.md,   ← capa de navegación (esta actualización)
│   PROJECT_STRUCTURE.md, PROJECT_INDEX.md
├── requirements.txt, environment.yml, setup_entorno.bat
└── .env, .env.template, .gitignore
```

## Propósito de cada carpeta numerada

| Carpeta | Propósito | Audiencia |
|---|---|---|
| `01_Data` | Fuente única de verdad de los datos, en sus distintas etapas de procesamiento | Analistas, scripts de ingestión |
| `02_Analytics` | Exploración y desarrollo de modelos (notebooks + scripts), no es lo que corre en producción | Data scientists |
| `03_Models` | Artefactos de modelos entrenados y su trazabilidad | MLOps |
| `04_Reports` | Entregables — lo que se comparte fuera del equipo técnico | Jefaturas, Operaciones |
| `05_Dashboard` | Único producto en producción — el Gemelo Digital que usan los Jefes de Sala | Operadores, Jefes de Sala |
| `06_Documentation` | Conocimiento institucional: metodología, reglas de negocio, decisiones | Cualquier persona nueva |
| `07_Config` | Configuración global del proyecto (rutas, parámetros compartidos) | Todos los scripts |
| `08_Skills` | Contexto que cualquier IA (o persona) debe leer antes de trabajar en una carpeta | Claude / IA / onboarding |
| `09_Logs` | Auditoría técnica (logs de ejecución, inventarios) | DevOps/soporte |
| `99_Archive` | Todo lo que se reemplaza pero no se elimina | Referencia histórica |
