# CLAUDE.md — Producto Operacional (app_dash/)

> **OBLIGATORIO:** Antes de cualquier cambio en este directorio, revisa las skills relevantes en `../08_Skills/`.

## Skills requeridas por tarea

| Tarea | Skills a revisar |
|-------|-----------------|
| UI/UX del dashboard, layouts, componentes | `skill_ux_ui_cio_operations_center.md` |
| Lógica de simulación, ODE engine | `skill_molienda_sag.md`, `skill_machine_learning_operacional.md` |
| Calibración MH, riesgo operacional | `skill_estadistica_bayesiana_avanzada.md`, `skill_molienda_sag.md` |
| Reglas operacionales (rules_engine) | `skill_operaciones_mina_subterranea.md`, `skill_molienda_sag.md` |
| Carga de datos realtime | `skill_series_temporales_industriales.md`, `skill_data_quality_governance.md` |
| Arquitectura de producto analítico | `skill_data_product_architect.md`, `skill_product_owner_analitica_minera.md` |
| Callbacks, performance Dash | `skill_optimizacion_tokens_ia.md` |

## Protocolo antes de trabajar

1. **Leer skills relevantes** — `Read ../Skills/<skill_name>.md` para las skills de la tabla anterior
2. **Nunca ejecutar MH en tiempo real** — solo consumir parámetros pre-calculados de `data/cache/`
3. **`use_reloader=False`** — SIEMPRE en `app.run()`, evita procesos duplicados en Windows
4. **`allow_duplicate=True`** — requerido cuando múltiples callbacks comparten el mismo Output ID
5. **Matar proceso en 8050** antes de iniciar nuevo: `taskkill //F //IM python.exe` o buscar PID

## Cómo correr la app

```bash
cd app_dash
python app.py
# → http://localhost:8050
```

## Páginas del dashboard

| Ruta | Nombre | Audiencia |
|------|--------|-----------|
| `/` | Resumen Ejecutivo | CIO, Superintendencia |
| `/pilas` | Estado Pilas | Jefe de Sala |
| `/eventos` | Análisis T8 | Analista, PAM |
| `/modelo` | Modelo Dinámico | Analista |
| `/riesgo` | ¿Qué pasa si...? | Jefe de Turno, PAM |

## Reglas críticas del simulador `/riesgo`

- Unidades visibles al operador: **TPH, %, h** — NUNCA pp/h, estadística, Weibull
- P(survive) se calcula internamente desde tabla MH calibrada, NO se expone la metodología
- 3 escenarios de comparación: Configurado / Conservador / Máx Producción
- Horizonte simulación = `max(24h, t8_dur + 8h)`

## Estructura

```
app_dash/
├── app.py             ← entry point, callbacks principales
├── assets/            ← CSS
├── components/        ← graphs.py, cards.py, controls.py
├── engine/            ← simulator.py, ode_model.py, mh_calibration.py, ...
├── config/            ← rules_config.yaml, app_config.yaml, thresholds.yaml
└── outputs/           ← screenshots, logs de app
```
