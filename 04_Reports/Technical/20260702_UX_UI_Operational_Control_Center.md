# Centro de Control Operacional — Mejoras UX/UI del Simulador

## División El Teniente — Codelco | AA_CIO_DET | 2026-07-02

---

## 1. Objetivo

Transformar el dashboard de un simulador analítico a un centro de control
operacional: que un Jefe de Sala entienda el estado completo de la planta y
el impacto de un cambio en segundos, sin interpretar estadística. Se revisó
`08_Skills/skill_token_optimization_loop.md` antes de implementar (regla
obligatoria del prompt) — su principio de "reusar/cachear antes que
recalcular" se aplicó donde no chocaba con requisitos explícitos del usuario
(ver sección 4, decisión de recompute-en-vivo).

No se modificó el modelo matemático (`engine/ode_model.py`); todos los
cambios usan datos que `simulate_scenario()` ya calculaba, o el mismo patrón
de restricción dura ya validado en la sesión de la regla R16.

---

## 2. Mejoras UX

| # | Cambio | Descripción |
|---|---|---|
| 1 | Mantenciones extendidas | CH1, CH2, CV315, CV316, T1, T3 ahora programables con ventana horaria, igual que SAG1/SAG2/411/412/511/512. |
| 2 | Gantt de disponibilidad | Pasa a ser el primer tab visible (antes era "Autonomía") — responde la primera pregunta del centro de control: "¿qué equipos estarán disponibles?". |
| 3 | Fan chart de confianza | Reemplaza el frontier plot estadístico por una banda de confianza (P10-P90) por SAG con lenguaje operacional. |
| 4 | "¿Por qué confiar?" | Nueva tarjeta con % de simulaciones que cumplen producción, vacían SAG1/SAG2, cumplen autonomía. |
| 5-6 | Fix "gráfico congelado" | Ver sección 3 — causa raíz identificada y corregida. |
| 7 | Riesgo por hora | Nuevo gráfico P(vaciado)/P(overflow) por SAG vs hora del día, desde las trayectorias Monte Carlo reales. |
| 8 | Semáforo | Tarjeta "Estado del Escenario" (🟢/🟡/🟠/🔴) visible sin scroll, combina IRO + P(seguro) MC + autonomía. |
| 9 | Narrativa | Títulos de gráficos reformulados como preguntas operacionales. |
| 10 | Auto-integración | Mover cualquier slider relevante recalcula Monte Carlo automáticamente. |
| 11 | Centro de control | Gantt + semáforo + resumen ejecutivo + fan chart visibles en la primera pantalla, sin cambiar de tab. |

---

## 3. Problema corregido: "gráfico congelado"

**Diagnóstico:** `/riesgo` (`app.py`) ya era 100% reactivo — todos sus
outputs cuelgan de `Input`, no `State`. El congelado real estaba en
`pages/simulador_operacional.py`: la pestaña "Robustez MC"/"Mapa Producción
vs Riesgo" leía `store-mc-results`, poblado **solo** al apretar el botón
"Simular Monte Carlo", mientras el resto de los parámetros del escenario
eran `State` (no `Input`) en el callback `run_monte_carlo` — es decir,
cambiar la pila o el rate no disparaba un recálculo.

**Decisión informada:** el usuario, tras conocer el trade-off (Monte Carlo
puede correr hasta 500 simulaciones, `skill_token_optimization_loop.md`
recomienda evitar cómputo pesado innecesario), decidió explícitamente
recalcular Monte Carlo completo en cada cambio de slider relevante, en vez
de solo mostrar un punto vivo sobre la nube cacheada. Mitigación de costo:
se mantiene el early-stop adaptativo ya existente en `adaptive_mc_eval`
(converge normalmente bajo los 500 samples) y el `dcc.Loading` que envuelve
la sección para dar feedback visual durante el recálculo. `dcc.Slider`
dispara su `value` en `mouseup`, no en cada pixel de arrastre, evitando
recálculo continuo durante el drag.

**Cambio:** en `run_monte_carlo`, los 27 parámetros de escenario (pilas,
T8, SAG on/off, chancado, correas, T1/T3, horizonte, turno, 12 ventanas de
mantención) pasaron de `State(...)` a `Input(...)`. Verificado vía
`/_dash-dependencies`: `ctrl-pila-sag1` ahora es Input de `run_monte_carlo`.

---

## 3.1 Reversión de la decisión (2026-07-06)

El usuario revirtió explícitamente la decisión de la sección 3: en
`04_Reports/Technical/20260706_Performance_Optimization_EXE.md` (Fase 6),
tras confirmárselo directamente en conversación, pidió volver a gatear
Monte Carlo/optimizador detrás del botón — los 27 parámetros de escenario
en `run_monte_carlo` volvieron de `Input(...)` a `State(...)`, dejando
`Input("btn-monte-carlo", "n_clicks")` como único disparador. Motivo
declarado: priorizar que la app "no se sienta congelada" para usuarios
externos por sobre la reactividad en vivo. Además se agregó un selector
"Modo rápido / Modo avanzado" (`ctrl-app-mode` en `components/controls.py`)
que en modo rápido (default) oculta el botón "Monte Carlo" y la vista
"Robustez MC" por completo, para no exponer la opción a usuarios no
técnicos (validador, jefe de sala).

Esta sección 3 queda como registro histórico de por qué existía la
reactividad en vivo; ya no refleja el comportamiento actual del código.

---

## 4. Cambios de interacción

- `store-mc-results` ahora guarda el candidato ganador (`best`, un dict)
  en vez de la lista completa de 20 candidatos — es lo único que consumen
  el fan chart y la tarjeta de confianza, y simplifica el flujo.
- `adaptive_mc_eval()` (`engine/optimizer_v2.py`) captura, sin simulaciones
  adicionales (reusa el `sim` que cada muestra ya calculaba y antes
  descartaba), TPH por SAG, % de vaciado/overflow por pila, y probabilidad
  de vaciado/overflow por hora — todo expuesto en el dict `best`.
- Título del botón/sección: "Monte Carlo: Robustez" → "¿Qué tan confiable es
  esta recomendación?", abierto por defecto (antes colapsado).

---

## 5. Validaciones realizadas

Todas las pruebas se ejecutaron simulando las llamadas reales de Dash
(`_dash-update-component`), levantando la app localmente.

**Caso 1 — CH2 OFF (mantención 08:00-16:00, turno A inicia 08:00):**
confirmado. `store-plant-state` pasa de `cv315=928, cv316=2272` (CH2 activo)
a `cv315=348, cv316=852` (CH2 forzado OFF, capacidad de chancado reducida en
consecuencia).

**Caso 2 — CV315 OFF:** confirmado, **con una precisión importante**: el
modelo (`ode_model.py:520-523`, preexistente) solo aplica el factor de
correa (`activa/reducida/inactiva`) **durante una ventana T8 activa** — es
el mecanismo original diseñado para modelar la caída de correas durante T8,
no un toggle general de disponibilidad. Con T8=0h, forzar CV315 a
"inactiva" por mantención no tiene efecto visible (comportamiento correcto
del modelo, no un bug). Con T8=4h: `cv315` cae de 928 → 0 TPH, afectando
específicamente la alimentación de SAG1. Documentado como limitación
heredada, no se modificó el ODE para resolverla (fuera del alcance
acordado: "no modificar modelos matemáticos salvo necesario").

**Caso 3 — CV316 OFF:** análogo al Caso 2, confirmado con T8 activo:
`cv316` cae de 2272 → 0 TPH, afecta específicamente SAG2.

**Caso 4 — Pila SAG1 80% → 20%:** el sistema **sí responde** — IRO cambia de
79.3 a 51.6, y las trayectorias de pila e inventario difieren claramente
desde t=0 (pila inicial 79.7% vs 20.0%, autonomía inicial 2.72h vs 0.21h).
**Hallazgo:** con horizonte de 24h y rate de SAG1 sostenido por encima del
punto de equilibrio, ambos escenarios convergen al mismo piso de inventario
(~18.9%) hacia el final de la ventana — por eso la tarjeta semáforo, que usa
la autonomía **mínima en todo el horizonte**, clasificó ambos casos como
"Riesgo Alto" pese a que el estado inicial es muy distinto. No es un bug de
conexión (los datos subyacentes cambian correctamente, verificado), sino una
limitación de diseño del indicador semáforo: usa el peor punto del
horizonte completo en vez de una ventana más cercana (ej. próximas 4-8h).
**Recomendado como mejora de seguimiento**, no corregido en esta iteración
para no alterar el criterio de riesgo ya usado en el resto del dashboard sin
validación de Operaciones.

**Caso 5 — T8 0h → 12h:** confirmado. `p_safe` cambia de 1.000 a 0.000 y
`tph_mean` de 3469 a 3309 TPH; `hourly_risk` se recalcula con 25 puntos
horarios en ambos casos (contenido distinto).

**Regresión `/riesgo`:** confirmado sin cambios — `/`, `/historico`,
`/analisis`, `/riesgo` responden HTTP 200, sin errores en el log del
servidor durante toda la sesión de pruebas.

---

## 6. Seguimiento recomendado (no incluido en esta iteración)

- Recalibrar la ventana de evaluación del semáforo "Estado del Escenario"
  (Caso 4) para que use un horizonte de riesgo más cercano en vez del
  mínimo sobre las 24h completas.
- Extender el factor de correa T8-condicional (`ode_model.py:520-523`) a
  un modo genérico de disponibilidad si Operaciones confirma que CV315/CV316
  deben poder quedar fuera de servicio también sin T8 activo.
