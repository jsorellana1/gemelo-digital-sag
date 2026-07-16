# Roadmap — Gemelo Digital Molienda SAG T8

*Última actualización: 2026-07-02*

Consolida el estado del proyecto. Para el diagnóstico técnico detallado
(cuellos de botella, evaluación de cada modelo, score de calidad) ver
[`04_Reports/Technical/20260701_Roadmap_Gemelo_Digital.md`](04_Reports/Technical/20260701_Roadmap_Gemelo_Digital.md),
que este documento resume y mantiene al día.

---

## ✓ Implementado

- **Análisis histórico** — KPIs operacionales, EDA, detección de change
  points, efecto gaviota (caída/recuperación TPH pre-post T8).
- **Modelo causal basado en inventario** — relación pila/decisión
  operacional (`02_Analytics/Scripts/causal_model/`).
- **Ecuaciones diferenciales (EDO)** — simulación de dinámica de pilas
  SAG1/SAG2 (`05_Dashboard/engine/ode_model.py`).
- **Monte Carlo adaptativo** — con parada por convergencia
  (`engine/optimizer_v2.py::adaptive_mc_eval`).
- **Metropolis-Hastings** — calibración bayesiana de riesgo
  (`engine/mh_calibration.py`).
- **Optimizer V3** — grilla determinística + MC + Pareto, filtra
  escenarios con restricciones duras (`engine/optimizer_v3.py`).
- **Dashboard Operacional / Gemelo Digital**:
  - Simulador manual con recomendación automática ("Óptimo según pila").
  - Página "¿Qué pasa si...?" (`/riesgo`) con comparador de 3 escenarios.
  - What-If comparador (`/analisis`).
  - Curvas históricas (`/historico`).
- **Turnos y mantenciones programables** — turno C/A/B, eje "hora del día"
  real, mantenciones para SAG1/SAG2/411/412/511/512 + CH1/CH2/CV315/CV316/
  T1/T3, todas como restricción dura sobre el optimizador.
- **Gantt operacional** — disponibilidad ON/OFF/MANTTO de los 12 equipos
  críticos por hora.
- **Regla R16** — al menos 1 molino de bolas activo por SAG, restricción
  dura en el optimizador y Monte Carlo; validada contra datos históricos
  reales (216/93601 registros SAG1, 9/93601 SAG2 en violación —
  ver [`04_Reports/Technical/20260702_Regla_R16_Molinos_Bolas.md`](04_Reports/Technical/20260702_Regla_R16_Molinos_Bolas.md)).
- **Centro de Control Operacional** — Monte Carlo recalculado en vivo al
  mover cualquier parámetro (ya no solo al apretar el botón), fan chart de
  confianza, tarjeta "¿por qué confiar?", riesgo por hora, semáforo "Estado
  del Escenario" —
  ver [`04_Reports/Technical/20260702_UX_UI_Operational_Control_Center.md`](04_Reports/Technical/20260702_UX_UI_Operational_Control_Center.md).

---

## ○ En desarrollo / diagnosticado, pendiente de implementar

- **Optimizador por tramos horarios** — hoy el optimizador devuelve una
  config estática para todo el horizonte; falta re-optimizar en cada
  cambio de turno/mantención/T8 dentro de la misma corrida (plan de
  fondo scopeado, no implementado).
- **Tarjeta "Plan Operacional Recomendado"**, gráfico "Estrategia
  Recomendada" (subir/bajar/mantener) y "Producción acumulada" —
  dependen del optimizador por tramos.
- **Monte Carlo consciente de mantenciones/turnos** — hoy asume
  disponibilidad constante dentro del horizonte simulado.
- **Documentación profunda por modelo** (objetivo/entradas/salidas/
  supuestos/limitaciones/casos de uso) en `06_Documentation/Models/` y por
  página del dashboard en `06_Documentation/Dashboard/` — priorizado
  después de esta capa de gobernanza (ver `CHANGELOG.md`).
- **Reglas operacionales R10-R15** — no existen definidas en ningún lugar
  del repo; el rango R01-R09 y R16 está implementado y documentado, pero
  hay un hueco de numeración sin contenido — pendiente de que Operaciones
  defina si corresponde completarlo.
- **Reorganización `analytics/` vs `app_dash/`** — propuesta en
  `06_Documentation/reorganizacion_analytics_dash.md`, estado "PLAN —
  pendiente de aprobación", no ejecutada.

---

## ○ Futuro (no diagnosticado en detalle)

- Reinforcement Learning para políticas de operación.
- Optimización estocástica multi-periodo (más allá de Monte Carlo puntual).
- Control predictivo (MPC) integrado al simulador ODE.
- Variables faltantes identificadas en el diagnóstico técnico: granulometría,
  disponibilidad mecánica de chancadores, potencia/torque SAG (ver reporte
  técnico de roadmap para el detalle completo por modelo).
