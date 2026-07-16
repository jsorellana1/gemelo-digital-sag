# CLAUDE.md — Laboratorio Analítico (analytics/)

> **OBLIGATORIO:** Antes de cualquier cambio en este directorio, revisa las skills relevantes en `../Skills/`.

## Skills requeridas por tarea

| Tarea | Skills a revisar |
|-------|-----------------|
| Análisis de eventos T8, historiales | `skill_series_temporales_industriales.md`, `skill_molienda_sag.md` |
| Modelos estadísticos / Bayesianos | `skill_estadistica_bayesiana_avanzada.md`, `skill_data_scientist_senior.md` |
| Modelos diferenciales / dinámicos | `skill_molienda_sag.md`, `skill_machine_learning_operacional.md` |
| Machine learning, SHAP, features | `skill_machine_learning_operacional.md`, `skill_explainable_ai_governance.md` |
| Informes y reportes | `skill_product_owner_analitica_minera.md`, `skill_data_quality_governance.md` |
| Optimización y forecasting | `skill_forecasting_industrial.md`, `skill_optimizacion_tokens_ia.md` |
| Causalidad operacional | `skill_process_mining_industrial.md`, `skill_molienda_sag.md` |

## Protocolo antes de trabajar

1. **Leer skills relevantes** — `Read ../Skills/<skill_name>.md` para las skills de la tabla anterior
2. **Verificar datos** — `data/` es compartido con `app_dash/`, no duplicar ni renombrar parquets
3. **Outputs** — resultados van a `analytics/outputs/{figures,excel,reports,models}/`
4. **No contaminar `app_dash/`** — este directorio es solo análisis/experimentación

## Estructura

```
analytics/
├── notebooks/         ← exploración interactiva (Jupyter)
├── src/               ← scripts Python por categoría
│   ├── event_study/
│   ├── causal_model/
│   ├── differential_equations/
│   ├── machine_learning/
│   ├── bayesian/
│   └── reporting/
└── outputs/           ← figuras, excels, reportes, modelos pkl
    ├── figures/
    ├── excel/
    ├── reports/
    └── models/
```

## Reglas de datos

- **`data/cache/`** — parquets y arrays `.npy` generados por notebooks, compartidos con app_dash
- **`data/raw/`** — datos fuente, NUNCA modificar
- **N=500 simulaciones MC** — suficiente para validación, no escalar sin justificación
