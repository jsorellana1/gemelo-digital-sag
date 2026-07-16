# Reglas Operacionales — Gemelo Digital Molienda SAG T8

Fuente de verdad del texto de cada regla: `05_Dashboard/config/rules_config.yaml`
(R01-R09) y el reporte técnico específico de R16. Este documento no
reescribe esas reglas — las cita textualmente y agrega motivación, estado
de implementación y validación histórica.

---

## R01 — Iniciar T8 con pila > 40%

- **Severidad:** verde
- **Texto:** *"Pila SAG1 y SAG2 sobre 40% garantiza autonomia minima de 4h
  en SAG2 y 1.05h en SAG1 para T8 larga."*
- **Motivación:** dar margen de autonomía suficiente antes de iniciar una
  ventana T8 larga, evitando vaciado.
- **Estado actual:** informativa — mostrada como recomendación en la UI
  (`rules_engine.py`), no es una restricción dura del optimizador.

## R02 — Rate óptimo: 82-95% P90

- **Severidad:** verde
- **Texto:** *"Operar en banda 82-95% P90 maximiza tonelaje total y
  minimiza riesgo critico de pila."*
- **Motivación:** balance entre maximizar tonelaje y no operar tan cerca
  del máximo histórico que el riesgo de crisis se dispare.
- **Estado actual:** informativa. El Optimizer V3 busca en una grilla
  anclada a percentiles P50/P75/P90/MAX que cubre esta banda, pero no la
  fuerza como restricción explícita.

## R03 — Ambas correas activas durante T8 prolongado

- **Severidad:** verde
- **Texto:** *"Si T8 > 4h, mantener correa 316 activa para alimentacion
  alternativa a SAG2."*
- **Motivación:** SAG2 depende de CV316; sin ella, queda sin alimentación
  alternativa durante T8 largo.
- **Estado actual:** informativa.

## R04 — Correa 315 inactiva ~49% del tiempo

- **Severidad:** naranjo
- **Texto:** *"Restriccion estructural: planificar T8 preferentemente
  cuando correa 315 esta activa."*
- **Motivación:** restricción estructural observada en datos históricos
  (CV315 sin flujo el 49% del tiempo operativo — ver
  `04_Reports/Technical/20260701_Roadmap_Gemelo_Digital.md`).
- **Estado actual:** informativa/diagnóstico.

## R05 — SAG1 se drena rápido (23.76%/h)

- **Severidad:** naranjo
- **Texto:** *"SAG1 tiene autonomia critica muy corta. Reducir rate al
  llegar a 25% de pila."*
- **Motivación:** SAG1 tiene la tasa de drenaje más alta del sistema —
  requiere intervención temprana comparado con SAG2 (6.18%/h).
- **Estado actual:** informativa; los umbrales de `_autonomia_color()`
  (`05_Dashboard/components/cards.py`) usan cortes asimétricos entre SAG1
  y SAG2 consistentes con esta regla.

## R06 — Activar bolas para compensar caída T8

- **Severidad:** naranjo
- **Texto:** *"Molinos de bola aportan +8% TPH por circuito; activar en
  cuanto inicia T8 > 2h."*
- **Motivación:** compensar la caída de alimentación durante T8 con la
  capacidad adicional de los molinos de bolas.
- **Estado actual:** el Optimizer V3 evalúa activamente configuraciones
  con bolas dentro de su grilla; **superseded parcialmente por R16** (ver
  abajo), que ahora exige al menos 1 molino activo en todo momento que el
  SAG esté encendido, no solo durante T8.

## R07 — No operar SAG1 bajo 15% de pila

- **Severidad:** rojo
- **Texto:** *"Nivel critico: opera en minimo tecnico o detener para
  evitar dano a revestimiento."*
- **Motivación:** protección de equipo — daño físico al revestimiento del
  molino si opera con pila crítica.
- **Estado actual:** **restricción dura** — el umbral crítico SAG1 (15.0%)
  es usado directamente en `engine/optimizer_v2.py` (`min_auton_sag1`) y
  en la métrica `pct_vacia_sag1` del Monte Carlo.

## R08 — Impacto severo SAG1 a partir de 4h T8

- **Severidad:** rojo
- **Texto:** *"SAG1 cae a 69% P90 a las 4h; planificar compensacion con
  SAG2 si esta disponible."*
- **Motivación:** dato empírico de degradación de SAG1 en ventanas T8
  largas (>4h) — define el corte de régimen "T8 larga" en el optimizador.
- **Estado actual:** informativa; el corte de 4h para régimen "t8_larga"
  en `optimizer_v2.py::get_regime()` es consistente con esta regla.

## R09 — Autonomía SAG2 < 1h requiere acción inmediata

- **Severidad:** rojo
- **Texto:** *"SAG2 bajo 1h de autonomia: detener alimentacion
  discrecional y escalar a operaciones."*
- **Motivación:** umbral de escalamiento — por debajo de 1h de autonomía
  en SAG2, ya no es una decisión de rate, es una alerta operacional.
- **Estado actual:** informativa; el umbral de 1h coincide con el corte
  rojo de `_autonomia_color()` en `cards.py`.

---

## R16 — Restricción de molinos de bolas (al menos 1 activo por SAG)

- **Severidad:** rojo (restricción dura)
- **Texto:** para cada línea de molienda (SAG1: 411/412, SAG2: 511/512) se
  permite ambos ON o exactamente uno OFF — **nunca ambos OFF**
  simultáneamente mientras el SAG esté encendido.
- **Motivación:** validada por Operaciones como restricción física real,
  no solo una recomendación de eficiencia (a diferencia de R06, que la
  motivaba solo como compensación durante T8).
- **Estado actual:** **restricción dura implementada** en
  `engine/optimizer_v2.py::run_deterministic_grid()` (filtra `"sin_bola"`
  de la grilla cuando el SAG está activo), con detección de conflictos de
  planificación (`engine/scheduler.py::r16_conflicto_mantencion`) y
  advertencia en la UI manual si el usuario fuerza la configuración
  inválida.
- **Validación histórica:** sobre 93,601 registros de 5 min
  (`01_Data/Raw/estados_activos.xlsx`, 2025-08-01 → 2026-06-21), se
  encontraron **216 registros (34 bloques) en violación real para SAG1**
  y **9 registros (7 bloques) para SAG2** — la regla se respeta >99.7% del
  tiempo histórico; los bloques encontrados son candidatos a transiciones
  de conmutación entre molinos, no un patrón sistemático de
  incumplimiento.
- **Documento completo:**
  `04_Reports/Technical/20260702_Regla_R16_Molinos_Bolas.md`.

---

## Gap conocido: R10-R15

**No existen definidas en ningún lugar del repositorio.** No hay
numeración asignada, ni en `rules_config.yaml`, ni en reportes técnicos, ni
en el motor de reglas (`rules_engine.py`). Este documento no inventa
contenido para rellenar el rango — queda como gap explícito hasta que
Operaciones defina si corresponde completarlo y con qué reglas.

---

## Resumen de estado

| Rango | Definidas | Restricción dura | Solo informativa |
|---|---|---|---|
| R01-R06 | Sí | No | Sí |
| R07-R09 | Sí | R07 (umbral crítico SAG1) | R08, R09 |
| R10-R15 | **No** | — | — |
| R16 | Sí | **Sí** | No |
