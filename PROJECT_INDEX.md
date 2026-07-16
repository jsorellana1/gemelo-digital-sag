# Índice Maestro — ¿Dónde está cada cosa?

*Todas las rutas de este documento fueron verificadas contra el filesystem
real el 2026-07-02.*

---

## Modelos (código)

| Modelo | Ruta |
|---|---|
| Dinámica de pilas (EDO) | `05_Dashboard/engine/ode_model.py` |
| Simulador de escenario | `05_Dashboard/engine/simulator.py` |
| Optimizer V2 (grilla + MC base) | `05_Dashboard/engine/optimizer_v2.py` |
| Optimizer V3 (producción) | `05_Dashboard/engine/optimizer_v3.py` |
| Motor de riesgo (IRO) | `05_Dashboard/engine/risk_engine.py` |
| Motor de reglas operacionales | `05_Dashboard/engine/rules_engine.py` |
| Calibración Metropolis-Hastings | `05_Dashboard/engine/mh_calibration.py` |
| Turnos / mantenciones (scheduler) | `05_Dashboard/engine/scheduler.py` |
| Carga de datos en tiempo real | `05_Dashboard/engine/realtime_loader.py` |
| Modelo causal (exploración) | `02_Analytics/Scripts/causal_model/` |
| Event Study T8 / Efecto Gaviota | `02_Analytics/Scripts/event_study/` |
| ML (XGBoost, clustering, SHAP) | `02_Analytics/Scripts/machine_learning/` |
| Ecuaciones diferenciales (exploración) | `02_Analytics/Scripts/differential_equations/` |

## Dashboard (Gemelo Digital)

| Página | Ruta | Archivo |
|---|---|---|
| Simulador Operacional / Centro de Control (default `/`) | `05_Dashboard/pages/simulador_operacional.py` | página + callbacks |
| Curvas Históricas | `/historico` | `05_Dashboard/app.py` (`page_historico`) |
| What-If | `/analisis` | `05_Dashboard/app.py` (`page_analisis`) |
| ¿Qué pasa si...? | `/riesgo` | `05_Dashboard/app.py` (`page_riesgo_operacional`) |
| Componentes UI reutilizables | `05_Dashboard/components/{graphs,cards,controls}.py` | — |
| Configuración de umbrales/reglas | `05_Dashboard/config/{thresholds,rules_config,app_config}.yaml` | — |
| Documentos de entrega del portable (README usuario, guía validación, feedback, VERSION, QA checklist) | `05_Dashboard/packaging/` | — |
| Build oficial del portable `.exe` | `05_Dashboard/scripts/build_portable.py` | única fuente: `05_Dashboard/` |
| Detección de divergencia portable vs. fuente | `05_Dashboard/scripts/sync_portable_to_dev.py` | — |

**Correr el dashboard:** `cd 05_Dashboard && python app.py` → `http://localhost:8050`

## Skills (contexto para IA)

Carpeta: `08_Skills/` (19 archivos). Empezar por
`08_Skills/skill_master_project.md`. Índice completo por tema:

| Tema | Skill |
|---|---|
| Visión general del proyecto (leer primero) | `skill_master_project.md` |
| Proceso SAG/PMC/MUN, T8, pilas | `skill_molienda_sag.md` |
| UX/UI, Centro de Control | `skill_ux_ui_cio_operations_center.md` |
| ML operacional (XGBoost, clustering, SHAP) | `skill_machine_learning_operacional.md` |
| Estadística bayesiana / Metropolis-Hastings | `skill_estadistica_bayesiana_avanzada.md` |
| Series temporales industriales | `skill_series_temporales_industriales.md` |
| Operaciones mina subterránea / T8 | `skill_operaciones_mina_subterranea.md` |
| Process mining / star schema BI | `skill_process_mining_industrial.md` |
| Forecasting industrial | `skill_forecasting_industrial.md` |
| Arquitectura de producto analítico | `skill_data_product_architect.md` |
| Product ownership analítica minera | `skill_product_owner_analitica_minera.md` |
| Gobernanza / explicabilidad IA | `skill_explainable_ai_governance.md` |
| Mantenimiento predictivo / confiabilidad | `skill_confiabilidad_mantenimiento_predictivo.md` |
| Calidad y gobernanza de datos | `skill_data_quality_governance.md` |
| Data scientist senior | `skill_data_scientist_senior.md` |
| Ingeniería LLM | `skill_ai_llm_engineer.md` |
| Optimización de tokens (uso de IA) | `skill_optimizacion_tokens_ia.md` |
| Loop de optimización de tokens (Optimizer V3/MC/MH) | `skill_token_optimization_loop.md` |
| Sistemas de recomendación | `skill_recommendation_systems_engineer.md` |

## Reportes técnicos recientes (2026-06/07)

| Reporte | Ruta |
|---|---|
| Roadmap Gemelo Digital (diagnóstico técnico) | `04_Reports/Technical/20260701_Roadmap_Gemelo_Digital.md` |
| Inventario Dinámico SAG | `04_Reports/Technical/20260701_Inventario_Dinamico_SAG.md` |
| Metropolis-Hastings — Ejecutivo | `04_Reports/Technical/20260630_Metropolis_Hastings_Ejecutivo.md` |
| Metropolis-Hastings — Evaluación | `04_Reports/Technical/20260630_Metropolis_Hastings_Evaluacion.md` |
| Regla R16 (molinos de bolas) | `04_Reports/Technical/20260702_Regla_R16_Molinos_Bolas.md` |
| Centro de Control Operacional (UX/UI) | `04_Reports/Technical/20260702_UX_UI_Operational_Control_Center.md` |

Reportes históricos por tema (EDA, EventStudy T8, Pilas, Autonomía,
Modelos, SHAP, Optimización de Rates, Modelo Causal, Optimizer v2/v3):
`04_Reports/Technical/{01_EDA,02_EventStudy_T8,03_Pilas,04_Autonomia,05_Modelos,06_SHAP,07_Optimizacion_Rates,08_Modelo_Causal,09_Modelo_Causal_Final,10_Optimizer_v2,11_Optimizer_V3}/`.
Reportes anteriores a la reorganización: `04_Reports/Technical/99_Historicos/`.

## PDFs entregables

| PDF | Ruta |
|---|---|
| Balance Alimentación vs Molienda (ejecutivo) | `04_Reports/Executive/20260701_Balance_Alimentacion_vs_Molienda.pdf` |
| Anexo Técnico Modelos | `04_Reports/Technical/Anexo_Tecnico_Modelos.pdf` |
| Informe Estratégico Operación Molienda | `04_Reports/Technical/Informe_Estrategico_Operacion_Molienda.pdf` |
| Manual Decisión Operacional Molienda | `04_Reports/Technical/Manual_Decision_Operacional_Molienda.pdf` |
| Manual Operacional Pilas Molienda | `04_Reports/Technical/Manual_Operacional_Pilas_Molienda.pdf` |
| Modelo Dinámico Pilas SAG | `04_Reports/Technical/Modelo_Dinamico_Pilas_SAG.pdf` |
| Modelo Híbrido Pilas T8 | `04_Reports/Technical/Modelo_Hibrido_Pilas_T8.pdf` |
| Manual Operación Molienda (Optimización Rates) | `04_Reports/Technical/07_Optimizacion_Rates/20260625_ManualOperacion_Molienda_Ejecutivo.pdf` |
| Modelo Causal Operación Molienda (ejecutivo) | `04_Reports/Technical/09_Modelo_Causal_Final/20260625_Modelo_Causal_Operacion_Molienda_Ejecutivo.pdf` |
| Optimizer v2 (ejecutivo) | `04_Reports/Technical/10_Optimizer_v2/20260701_Optimizer_v2_Executive.pdf` |

## Datos

| Dataset | Ruta | Contenido |
|---|---|---|
| Histórico 5-min (SAG/PMC/UNITARIO) | `01_Data/Cache/advanced_t8_historical_5min.parquet` | 93,601 filas, 2025-08-01 → 2026-06-21 |
| Estado individual de molinos de bolas | `01_Data/Raw/estados_activos.xlsx` | única fuente con `mobo 411/412/511/512` por separado |
| Ventanas T8 oficiales | `01_Data/Cache/advanced_t8_official_events.parquet` | — |
| Posteriors Metropolis-Hastings | `01_Data/Cache/mh_post_*.npy` | calibración bayesiana |
| Dataset maestro (features) | `01_Data/Processed/dataset_master.parquet` | consolidado |
| Config global de rutas | `07_Config/paths.yaml`, `07_Config/config.yaml` | — |

## Documentación de conocimiento

| Documento | Ruta |
|---|---|
| Reglas operacionales (R01-R09, R16) | `06_Documentation/Operational_Rules/README.md` |
| Metodología / arquitectura | `06_Documentation/Methodology/arquitectura_proyecto.md` |
| Estado del proyecto (snapshot) | `06_Documentation/estado_actual_proyecto.md` |
| Protocolo de trabajo — Analytics | `06_Documentation/CLAUDE.md` |
| Protocolo de trabajo — Dashboard | `05_Dashboard/CLAUDE.md` |
| Inventario de reorganización | `06_Documentation/Reorganization/20260630_Project_Inventory.csv` |

## Capa de navegación (este documento y hermanos)

`README.md` · `ROADMAP.md` · `CHANGELOG.md` · `PROJECT_STRUCTURE.md` ·
`PROJECT_INDEX.md` (este archivo) · `08_Skills/skill_master_project.md`
