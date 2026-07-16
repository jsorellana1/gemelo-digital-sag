# Regla R16 — Restricción de Molinos de Bolas

## División El Teniente — Codelco | AA_CIO_DET | 2026-07-02

---

## 1. Regla incorporada

Para cada línea de molienda debe existir siempre **al menos un molino de
bolas operativo**:

- **SAG1** (molinos 411 / 412): se permite ambos ON, o exactamente uno OFF.
  **No** se permite 411 OFF + 412 OFF simultáneamente.
- **SAG2** (molinos 511 / 512): misma lógica con 511 / 512.

En el modelo actual, "ambos OFF" se codifica como el estado `"sin_bola"`.
R16 prohíbe ese estado como recomendación del optimizador/Monte Carlo
mientras el SAG correspondiente esté activo, y lo señaliza como
configuración inválida cuando el usuario lo fuerza manualmente.

---

## 2. Validaciones implementadas

| Componente | Comportamiento nuevo |
|---|---|
| Optimizador V2/V3 (grilla determinística) | `"sin_bola"` se filtra de la lista de candidatos antes del cálculo del score, cuando el SAG está encendido. Restricción dura, no post-filtro. |
| Monte Carlo | Sin cambios de código: MC hereda la config de bola fija del candidato determinístico padre (no resamplea bola), por lo que queda protegido automáticamente al filtrar la grilla. |
| Simulador manual (UI) | `"sin_bola"` sigue siendo seleccionable (transparencia: el usuario puede ver el impacto de una config inválida), pero dispara un banner rojo "[R16] Configuración no permitida..." y el badge "R16 ✗" en el sidebar. |
| Slicers de mantención | Nueva función `r16_conflicto_mantencion()`: si 411 y 412 (o 511 y 512) quedan en mantención simultánea, se emite "Error de planificación" explícito en vez de fallar silenciosamente. |
| Gantt "Estado Operacional por Hora" | Anotación visual "🔴 R16" sobre los tramos donde ambos molinos de un mismo SAG están OFF (no MANTTO) a la vez. |
| Página "¿Qué pasa si...?" (`/riesgo`) | Nuevo indicador "R16 ✓ Cumple" / "R16 ✗ Violación regla" junto a las métricas del escenario. |

---

## 3. Archivos modificados

- `05_Dashboard/engine/optimizer_v2.py` — filtro duro en `run_deterministic_grid()`.
- `05_Dashboard/engine/scheduler.py` — nueva `r16_conflicto_mantencion()`.
- `05_Dashboard/pages/simulador_operacional.py` — `check_bola_alert`,
  `update_simulation`, `apply_ideal_params`, `run_monte_carlo`.
- `05_Dashboard/components/controls.py` — badge `r16-status-badge` en el sidebar.
- `05_Dashboard/components/graphs.py` — anotación R16 en `make_gantt_operacional`.
- `05_Dashboard/app.py` — indicador R16 en `page_riesgo_operacional` / `update_riesgo_sim`.

`optimizer_v3.py` no requirió cambios: delega en `run_deterministic_grid()`
de `optimizer_v2.py`, así que hereda el filtro automáticamente.
`risk_engine.py` tampoco: R16 se resolvió como comprobación de UI/optimizador,
no como un campo nuevo dentro de `compute_iro()`.

---

## 4. Escenarios descartados por el optimizador

Antes de R16, la grilla determinística de SAG1 evaluaba
`["sin_bola", "solo_411", "solo_412", "ambas_411_412"]` (4 opciones cuando se
usa la grilla per-mill) o `["sin_bola", "ambas_411_412"]` (2 opciones en la
grilla original de `/riesgo` y Monte Carlo). Con R16, `"sin_bola"` queda
excluido en ambos casos mientras el SAG esté encendido:

- Grilla per-mill (simulador operacional, turno/mantención): 4 → 3 opciones por SAG.
- Grilla original (`/riesgo`, "Simular Monte Carlo"): 2 → 1 opción por SAG
  (queda solo `"ambas_411_412"` / `"ambas_511_512"`, ya que esa grilla nunca
  tuvo las variantes de un solo molino).

---

## 5. Impacto sobre la optimización

- **Tamaño de grilla:** reducción marginal (25-50% menos combinaciones de
  bola por SAG, según la página). El costo dominante del optimizador sigue
  siendo la fase Monte Carlo sobre el top-20 de candidatos determinísticos,
  no la enumeración de la grilla — sin degradación de tiempo de respuesta
  esperable.
- **Calidad de recomendación:** el optimizador ya no puede converger a una
  solución donde el ahorro de desgaste de bolas se logre apagando ambos
  molinos de un SAG; esa opción — que hoy es matemáticamente atractiva en
  ciertos regímenes de pila alta / rate bajo — queda descartada por regla
  operacional, no por resultado del score.
- **Caso borde:** si el planificador programa mantención simultánea de
  ambos molinos de un SAG, el optimizador no tiene ninguna opción válida
  bajo R16; el sistema no fallla silenciosamente — cae al fallback
  `"sin_bola"` de forma explícita y lo señaliza como "Error de
  planificación" tanto en el badge como en el banner de alerta.

---

## 6. Validación histórica

Se contaba con datos reales de estado individual por molino en
`01_Data/Raw/estados_activos.xlsx` (columnas `mobo 411/412/511/512`,
consumidas activamente por `engine/realtime_loader.py`), lo que permitió
responder la pregunta con datos reales en vez de dejarla pendiente.

**Metodología:** sobre 93,601 registros de 5 minutos (2025-08-01 →
2026-06-21), se filtró por: (a) el SAG correspondiente **operando**
(`SAG1`/`SAG2 = "PARTIR"`), Y (b) ambos molinos de ese SAG en estado
`"PARAR"` simultáneamente. Esto excluye los períodos en que el SAG completo
está detenido (donde "ambos molinos apagados" es trivialmente cierto y no
constituye una violación de R16).

**Resultado:**

| SAG | Registros en violación (SAG operando, ambos molinos OFF) | % sobre registros con SAG operando | Bloques temporales discontinuos |
|---|---|---|---|
| SAG1 (411/412) | 216 | ~0.23% | 34 |
| SAG2 (511/512) | 9 | ~0.01% | 7 |

**Interpretación:** la regla se respeta en la práctica en más del 99.7% del
tiempo operado. Los 34 + 7 bloques encontrados son candidatos a corresponder
a transiciones de conmutación entre molinos (capturadas por la resolución de
muestreo de 5 minutos, que puede registrar un instante intermedio con ambos
molinos momentáneamente detenidos durante el cambio) o mantenciones
puntuales no capturadas por otra bandera del dataset. No se identifica un
patrón sistemático que sugiera que la regla haya sido ignorada de forma
recurrente. No se realizó una revisión caso a caso de cada uno de los 41
bloques contra bitácoras de mantención — se recomienda como trabajo de
seguimiento si Operaciones requiere trazabilidad completa de cada evento.

---

## 7. Preguntas del sistema — estado

| Pregunta | Respuesta |
|---|---|
| ¿Existe al menos un molino de bolas operativo por SAG? | Verificado por el optimizador (filtro duro) y expuesto en UI (badges R16). |
| ¿El plan propuesto viola la regla R16? | El optimizador nunca lo permite; la UI manual lo advierte si el usuario fuerza la config. |
| ¿Hay mantenimientos incompatibles? | Detectado por `r16_conflicto_mantencion()`, con mensaje de error explícito. |
| ¿La simulación generó estados físicamente imposibles? | Solo si el usuario fuerza `"sin_bola"` manualmente con el SAG activo — queda visualmente marcado como inválido, no oculto. |
| ¿El optimizador está respetando la restricción? | Sí, verificado (ver sección de verificación en el plan de implementación). |
| ¿La configuración propuesta es operacionalmente ejecutable? | Sí, para toda recomendación del optimizador/Monte Carlo. Para la simulación manual, solo si el usuario no fuerza una config inválida. |
