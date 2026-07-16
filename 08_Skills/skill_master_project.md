# Skill: Visión Maestra del Proyecto — Gemelo Digital Molienda SAG T8

## Propósito

Ser el **primer documento** que cualquier IA (o persona nueva) lee antes de
tocar cualquier carpeta de este proyecto. Da el mapa completo: qué problema
resuelve el proyecto, cómo está organizado, qué modelos existen, y qué
convenciones/buenas prácticas hay que respetar. No reemplaza los skills de
dominio específico (`skill_molienda_sag.md`, `skill_ux_ui_cio_operations_center.md`,
etc.) — los referencia y da el contexto para saber cuál leer después.

---

## 1. Objetivo del proyecto

División El Teniente (Codelco) necesita operar los molinos SAG1, SAG2, PMC
y MUN minimizando el impacto de las ventanas de mantenimiento Teniente 8
(T8), que interrumpen la alimentación de mineral. El proyecto responde dos
preguntas:

1. **Histórica:** ¿cuánto se pierde por T8, en qué activo, y por qué?
   (`02_Analytics/`, `04_Reports/`).
2. **Operacional en vivo:** ¿cómo debo operar ahora mismo (rate, molinos de
   bolas, chancado) para minimizar riesgo y maximizar producción, dado el
   estado actual de la planta? (`05_Dashboard/`, el **Gemelo Digital**).

Ver `README.md` para la descripción ejecutiva completa y
`ROADMAP.md` para qué está implementado vs. pendiente.

---

## 2. Arquitectura (resumen)

```
Datos (01_Data)
    ↓
Procesamiento / Exploración (02_Analytics)
    ↓
Modelos (03_Models, engine/ del dashboard)
    ↓
Gemelo Digital: ODE + Optimizer V3 + Monte Carlo + reglas duras
    ↓
Dashboard (05_Dashboard) → decisión operacional
```

Detalle completo de carpetas: `PROJECT_STRUCTURE.md`.
Detalle de dónde vive cada componente: `PROJECT_INDEX.md`.

---

## 3. Modelos — resumen (documentación profunda pendiente, ver ROADMAP.md)

| Modelo | Qué hace | Dónde vive |
|---|---|---|
| Efecto Gaviota / Event Study | Cuantifica caída y recuperación de TPH pre/post T8 | `02_Analytics/Scripts/event_study/` |
| Modelo causal | Relaciona inventario de pilas con decisión operacional | `02_Analytics/Scripts/causal_model/` |
| EDO (ecuaciones diferenciales) | Simula dinámica de pilas (balance de masa) minuto a minuto | `05_Dashboard/engine/ode_model.py` |
| Monte Carlo adaptativo | Incertidumbre (pila/feed/T8) con parada por convergencia | `05_Dashboard/engine/optimizer_v2.py::adaptive_mc_eval` |
| Metropolis-Hastings | Calibración bayesiana de P(sobrevive\|T8,pila) | `05_Dashboard/engine/mh_calibration.py` |
| Optimizer V3 | Grilla + MC + Pareto → recomendación de rate/bolas | `05_Dashboard/engine/optimizer_v3.py` |
| Motor de riesgo (IRO) | Índice compuesto de riesgo operacional | `05_Dashboard/engine/risk_engine.py` |
| Motor de reglas | Reglas operacionales duras (R01-R09, R16) | `05_Dashboard/engine/rules_engine.py`, `05_Dashboard/config/rules_config.yaml` |

**Regla de oro:** el simulador ODE (`simulate_scenario`) es la fuente única
de verdad para toda proyección — nunca duplicar su lógica en un componente
de UI. El optimizador siempre debe pasar por `run_deterministic_grid`
(`optimizer_v2.py`) para heredar automáticamente las restricciones duras
(mantenciones, regla R16) ya centralizadas ahí.

---

## 4. Convenciones y buenas prácticas

- **Nunca ejecutar Metropolis-Hastings en tiempo real** — solo consumir
  parámetros pre-calculados de `01_Data/Cache/mh_post_*.npy`.
- **Restricciones operacionales duras** (mantenciones, regla R16, SAG
  forzado OFF) se filtran **antes** del cálculo del score, en la grilla
  determinística — nunca como post-filtro sobre resultados ya calculados.
  Ver `05_Dashboard/engine/scheduler.py` como referencia del patrón.
- **`use_reloader=False`** siempre en `app.run()` — evita procesos Python
  duplicados en Windows.
- **Matar el proceso en el puerto 8050** antes de reiniciar el dashboard.
- **`allow_duplicate=True`** en callbacks Dash cuando varios callbacks
  comparten el mismo `Output`.
- **Recalcular vs. cachear:** por defecto, evitar recómputo pesado
  innecesario (ver `skill_token_optimization_loop.md`); cuando el usuario
  pide explícitamente que algo sea "reactivo en vivo" aunque sea costoso
  (ej. Monte Carlo en cada cambio de slider), documentar el trade-off y la
  mitigación (early-stop adaptativo, `dcc.Loading`) en vez de negociar el
  requisito silenciosamente.
- **No modificar el modelo matemático (ODE) salvo que sea estrictamente
  necesario** — la mayoría de las restricciones operacionales nuevas se
  pueden resolver forzando parámetros de entrada (ej. `ch1_on=False`) sin
  tocar `ode_model.py`.
- **Reportes técnicos** van en `04_Reports/Technical/`, con nombre
  `YYYYMMDD_Tema.md` — es el registro permanente de cada cambio de modelo o
  regla operacional significativo (ver ejemplos: regla R16, centro de
  control).

---

## 5. Skills relacionados — cuándo leer cada uno

| Si vas a trabajar en... | Lee además |
|---|---|
| UI/UX del dashboard, layouts | `skill_ux_ui_cio_operations_center.md` |
| Simulación, motor ODE | `skill_molienda_sag.md` |
| Calibración bayesiana, MH, riesgo | `skill_estadistica_bayesiana_avanzada.md` |
| Reglas operacionales (`rules_engine.py`) | `skill_operaciones_mina_subterranea.md`, `skill_molienda_sag.md` |
| Carga de datos en tiempo real | `skill_series_temporales_industriales.md`, `skill_data_quality_governance.md` |
| Arquitectura de producto analítico | `skill_data_product_architect.md`, `skill_product_owner_analitica_minera.md` |
| Performance de callbacks / cómputo costoso | `skill_token_optimization_loop.md`, `skill_optimizacion_tokens_ia.md` |
| ML operacional (XGBoost, clustering, SHAP) | `skill_machine_learning_operacional.md` |

También revisar el `CLAUDE.md` del subdirectorio específico
(`05_Dashboard/CLAUDE.md`, `06_Documentation/CLAUDE.md`) antes de trabajar
ahí — tienen el protocolo operativo detallado (qué skills leer, comandos
para correr la app, reglas de no-hacer).

---

## 6. Estructura de carpetas (referencia rápida)

Ver `PROJECT_STRUCTURE.md` para el árbol completo comentado. Resumen:

```
01_Data/          datos en sus distintas etapas
02_Analytics/      exploración y desarrollo de modelos (no producción)
03_Models/          artefactos de modelos entrenados
04_Reports/           entregables (reportes .md, PDFs)
05_Dashboard/          ÚNICO producto en producción — el Gemelo Digital
06_Documentation/       conocimiento institucional, reglas de negocio
07_Config/               configuración global
08_Skills/                este archivo y los demás skills
09_Logs/                   auditoría técnica
99_Archive/                 histórico, nunca se elimina
```
