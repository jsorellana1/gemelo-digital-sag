# Sábana Maestra SAG — Fase 2: Mapa causal del proceso

**Fecha:** 2026-07-13
**Base:** `05_Dashboard/engine/ode_model.py` (constantes calibradas verificadas
en código, no supuestas), `01_Data/Templates/generate_sabana_master.py`
(Hoja 01 — mismo campo, misma clasificación de disponibilidad).
**Complementa:** [Fase 10 — Loop de preguntas](20260713_Sabana_Maestra_Fase10_Loop_Respuestas.md),
[PI SCADA Integration Proposal](20260709_PI_SCADA_Integration_Proposal.md).

---

## 1. Diagrama de flujo

```text
Mina / T8 (ventana de detención programada aguas arriba)
   │  duracion_t8_h, correa315/316_estado
   ▼
Chancado Primario  (CH1, CH2)
   │  chancado_cap_total_tph = f(ch1_on, ch2_on)
   ▼
T1  (post-chancado, agregado)
   │  T1 = CV315 + CV316 + T3   ← balance de masa, Hoja 04 Reglas_Calidad
   ▼
┌──────────────┬──────────────┬──────────────┐
│   CV315      │   CV316      │      T3      │
│  (→ Pila SAG1)│ (→ Pila SAG2)│ (desvío, no  │
│               │              │  entra a SAG)│
└──────┬───────┴──────┬───────┴──────────────┘
       ▼               ▼
  Pila SAG1        Pila SAG2
  (inventario,     (inventario,
   S1 en ton/%)     S2 en ton/%)
       │               │
       ▼               ▼
  SAG1 / Molino 401  SAG2 / Molino 501
  (Qout = TPH real)  (Qout = TPH real)
       │               │
       ▼               ▼
  MoBos 411/412      MoBos 511/512
  (delta_tph aditivo, regla R16: n_mobos>=1 si SAG on)
       │               │
       └───────┬───────┘
               ▼
     Producción diaria / PAM
     (real_sagX_ton_dia vs pam_sagX_ton_dia)
```

Nodo transversal (no está en la cadena física, pero condiciona todo el mapa):
**Mantenciones** (`PAM_Mantto/*.xlsx`) puede apagar cualquier equipo de la
cadena (CH1/CH2, SAG1/SAG2, MoBos) — se modela como restricción dura en
`optimizer_v5`, no como flujo.

---

## 2. Tabla por etapa: flujo / inventario / estado / capacidad / restricción / alarma / setpoint / valor real

Convención de disponibilidad igual a la Hoja 01 de la sábana:
`ACTIVA_EN_MODELO` / `DISPONIBLE_NO_USADA` / `DISPONIBLE_CONTEXTO` / `NO_DISPONIBLE`.

### Etapa: Mina / T8

| Dimensión | Campo | Fuente / constante | Disponibilidad |
|---|---|---|---|
| Flujo | (no aplica — es un evento, no un flujo continuo) | — | — |
| Inventario | (no aplica) | — | — |
| Estado | `en_ventana_t8`, `regimen_operacional` | `advanced_t8_event_windows.parquet`, `regime_event_detector.py` | ACTIVA_EN_MODELO |
| Capacidad | (no aplica al nodo Mina; ver Chancado) | — | — |
| Restricción | `duracion_t8_h`, `hora_inicio_t8`/`hora_fin_t8` | `advanced_t8_official_events.parquet` | ACTIVA_EN_MODELO |
| Alarma | (implícita: inicio/fin de T8 es el evento mismo) | — | — |
| Setpoint | (no aplica) | — | — |
| Valor real | `correa315_estado`/`correa316_estado` (activa/reducida/inactiva) | Parámetro de escenario, `compute_qin()` factores {1.0, 0.4, 0.0} | DISPONIBLE_CONTEXTO |

### Etapa: Chancado Primario (CH1, CH2)

| Dimensión | Campo | Fuente / constante | Disponibilidad |
|---|---|---|---|
| Flujo | (el flujo de salida es T1, ver etapa siguiente) | — | — |
| Inventario | `nivel_tolva_ch1_pct`/`ch2_pct`, `nivel_buzon_grueso_pct`, `nivel_bins_517_522_pct` | NO EXTRAÍDO — visible en pantalla PI "Chancado Primario" | NO_DISPONIBLE |
| Estado | `ch1_on`/`ch2_on` | `estados_activos.xlsx` ('Chancador 1/2', PARAR/PARTIR) | DISPONIBLE_NO_USADA |
| Capacidad | `chancado_cap_total_tph` = 4000 (ambos) / 1500 (solo CH1) / 2500 (solo CH2) / 0 (ninguno) | `ode_model.py::CHANCADO_CAP` (constante calibrada) | ACTIVA_EN_MODELO |
| Restricción | `ch1_mantencion`/`ch2_mantencion` | `PAM_Mantto/*.xlsx` (nivel día) | DISPONIBLE_CONTEXTO |
| Alarma | `atollo_ch1`/`atollo_ch2` (CR-01/CR-02, "Nivel Alto Desc. Chancador") | NO EXTRAÍDO — alarma SCADA | NO_DISPONIBLE |
| Setpoint | `posicion_manto_ch1_pct`/`ch2_pct` (granulometría de salida) | NO EXTRAÍDO — visible en SCADA | NO_DISPONIBLE |
| Valor real | (implícito en `t1_tph`, ver etapa siguiente) | — | — |

### Etapa: T1 (post-chancado, agregado)

| Dimensión | Campo | Fuente / constante | Disponibilidad |
|---|---|---|---|
| Flujo | `t1_tph` | `tonelaje_v2.xlsx` (columna T1) — **valores negativos observados, requiere clip** (Hoja 04) | DISPONIBLE_NO_USADA |
| Inventario | (no aplica — T1 es un nodo de flujo puro, sin acumulación) | — | — |
| Estado | `t1_disponible_tph` = t1_tph × (1 − t3_frac) | Derivado, `compute_t1_distribution()` | DISPONIBLE_CONTEXTO |
| Capacidad | = `chancado_cap_total_tph` (T1 no tiene capacidad propia distinta del chancado que lo alimenta) | Derivado de la etapa anterior | ACTIVA_EN_MODELO |
| Restricción | **Balance de masa duro:** T1 = CV315 + CV316 + T3, tolerancia documentada en Hoja 04 (±50 TPH) | `ode_model.py::compute_t1_distribution` (alerta_restriccion ya en dashboard) | ACTIVA_EN_MODELO |
| Alarma | "Asignación inválida: CV315+CV316 supera T1 disponible" | Ya implementada en dashboard (tarjeta Transferencia T1) | ACTIVA_EN_MODELO |
| Setpoint | `distribucion_t1` (balanceado / priorizar_sag1 / priorizar_sag2 / proporcional / optimizada) | Parámetro de escenario — **nunca se registró qué estrategia se usó en cada momento real** | NO_DISPONIBLE |
| Valor real | `frac_cv315` = 0.29 histórico (29% a CV315, 71% a CV316) | `ode_model.py::T1_FRAC_CV315` (calibrado con `tonelaje_v2.xlsx`, 93.600 filas, 2025-08-01→2026-06-21) | ACTIVA_EN_MODELO |

### Etapa: CV315 → Pila SAG1 / CV316 → Pila SAG2

| Dimensión | Campo | Fuente / constante | Disponibilidad |
|---|---|---|---|
| Flujo | `cv315_tph`, `cv316_tph` | `tonelaje_v2.xlsx` (CV_315/CV_316) / parquet (correa_315/316) | ACTIVA_EN_MODELO |
| Inventario | (el flujo mismo, sin acumulación en la correa) | — | — |
| Estado | `cv315_estado`/`cv316_estado` (activa/reducida/inactiva) | Derivable de `cv315_tph` vs. histórico propio; no existe como campo explícito | DISPONIBLE_CONTEXTO |
| Capacidad | `cv315_cap_tph`/`cv316_cap_tph` | NO DISPONIBLE — no hay capacidad por correa documentada separada del chancado total | NO_DISPONIBLE |
| Restricción | Factor T8: {activa: 1.0, reducida: 0.4, inactiva: 0.0} × flujo nominal | `ode_model.py::compute_qin()` | ACTIVA_EN_MODELO |
| Alarma | (comparte la alarma de balance T1 de la etapa anterior) | — | — |
| Setpoint | (no aplica — la correa no tiene consigna propia, hereda de T1) | — | — |
| Valor real | = `qin_sag1_tph` / `qin_sag2_tph` (entrada efectiva a la pila) | `ode_model.py::compute_qin()` | ACTIVA_EN_MODELO |

### Etapa: Pila SAG1 / Pila SAG2

| Dimensión | Campo | Fuente / constante | Disponibilidad |
|---|---|---|---|
| Flujo | `qin_sag1/2_tph` (entrada), `qout_sag1/2_tph` (salida = TPH real SAG) | Derivado / `advanced_t8_historical_5min.parquet` | ACTIVA_EN_MODELO |
| Inventario | `pila_sag1_pct`/`pila_sag2_pct` (S1, S2 — estado del ODE) | `tonelaje_v2.xlsx` (SAG:Nivel_Pila/SAG2:Nivel_Pila) / parquet (pila_sag1/2) | ACTIVA_EN_MODELO |
| Estado | `pila_sag1_ton`/`pila_sag2_ton` | Derivado: `pct/100 × CAP_TON` | DISPONIBLE_CONTEXTO |
| Capacidad | `CAP_TON = {SAG1: 4575.0, SAG2: 32009.0}` ton | `ode_model.py::CAP_TON` (constante calibrada) — **SAG2 tiene ~7× la capacidad de SAG1** | ACTIVA_EN_MODELO |
| Restricción | `CRITICAL_PCT = {SAG1: 15.0, SAG2: 18.2}` (%), `WARNING_PCT = {SAG1: 18.0, SAG2: 21.2}` (crit+3pp) | `ode_model.py` (constantes calibradas) | ACTIVA_EN_MODELO |
| Alarma | Autonomía (`compute_autonomia()`: horas hasta nivel crítico), riesgo de overflow (tope 100%) | `ode_model.py::compute_autonomia()`, `step_pile()` (clip [0,100]) | ACTIVA_EN_MODELO |
| Setpoint | (no aplica — la pila no tiene consigna, es un inventario resultante) | — | — |
| Valor real | `DRAIN_PCT_H = {SAG1: 23.76, SAG2: 6.18}` pp/h — **velocidad de drenaje calibrada, SAG1 drena ~4× más rápido que SAG2 en términos de %** | `ode_model.py::DRAIN_PCT_H` | ACTIVA_EN_MODELO |

### Etapa: SAG1 / Molino 401, SAG2 / Molino 501

| Dimensión | Campo | Fuente / constante | Disponibilidad |
|---|---|---|---|
| Flujo | `sag1_tph_real`/`sag2_tph_real` (= Qout de la pila) | `advanced_t8_historical_5min.parquet` (SAG1_tph/SAG2_tph) — DUPLICADA con `tonelaje_v2.xlsx` (REND_TMS_SAGx_PI) | DUPLICADA (preferir el parquet, ya usado en producción) |
| Inventario | (no aplica — el molino no acumula, procesa) | — | — |
| Estado | `sag1_on`/`sag2_on` | `estados_activos.xlsx` ('SAG1'/'SAG 2', PARAR/PARTIR) | DISPONIBLE_NO_USADA |
| Capacidad | `P90 = {SAG1: 1454.0, SAG2: 2516.0}` TPH (P90 histórico de rate) | `ode_model.py::P90` | ACTIVA_EN_MODELO |
| Restricción | `sag1_potencia_mw`/`sag2_potencia_mw` (techo real de Qout físicamente alcanzable) | NO EXTRAÍDO — visible en SCADA (MW 16.72 observado en captura 2026-07-09) | NO_DISPONIBLE |
| Alarma | (ninguna alarma propia del molino identificada aún — ver `sag1_rpm` como proxy de "fuera de velocidad operativa") | — | NO_DISPONIBLE |
| Setpoint | `sag1_tph_setpoint`/`sag2_tph_setpoint` (consigna, distinta del valor medido) | NO DISPONIBLE — no hay serie de setpoint separada del TPH real en ninguna fuente | NO_DISPONIBLE |
| Valor real | `sag1_rpm`/`sag2_rpm`, `sag1_pebbles_tph`/`sag2_pebbles_tph` (recirculación PAC) | NO EXTRAÍDO — visibles en SCADA | NO_DISPONIBLE |

### Etapa: MoBos 411/412 (SAG1), 511/512 (SAG2)

| Dimensión | Campo | Fuente / constante | Disponibilidad |
|---|---|---|---|
| Flujo | `delta_tph_mobos_sag1`/`sag2` (aditivo, no multiplicativo) | `01_Data/Cache/bola_delta_tph.json` (calibrado), fallback `BOLA_BONUS_LEGACY=0.08` en `ode_model.py` | ACTIVA_EN_MODELO |
| Inventario | (no aplica) | — | — |
| Estado | `mobo_411_on`/`412_on`/`511_on`/`512_on` | `estados_activos.xlsx` ('mobo 411/412/511/512', PARAR/PARTIR) | DISPONIBLE_NO_USADA |
| Capacidad | `n_mobos_sag1`/`sag2` ∈ {0,1,2} → `effective_rate() = P90 × rate_pct/100 + DELTA_TPH(n_bolas)` | `ode_model.py::effective_rate()`, `BOLA_CONFIG_SAG1/2` | ACTIVA_EN_MODELO |
| Restricción | **Regla R16 dura:** `n_mobos_sag1 >= 1` si SAG1 operativo (ídem SAG2) | `check_bola_rule()` | ACTIVA_EN_MODELO |
| Alarma | `mobo_411_mantencion`/etc. | `PAM_Mantto/*.xlsx` (nivel día) | DISPONIBLE_CONTEXTO |
| Setpoint | `mobo_recomendado_sag1`/`sag2` (config. recomendada por optimizador) | Output en vivo, nunca historificado | NO_DISPONIBLE |
| Valor real | `BOLA_THRESHOLD_TPH = {SAG1: 1000.0, SAG2: 1600.0}` (umbral de rate para activar regla) | `ode_model.py::BOLA_THRESHOLD_TPH` | ACTIVA_EN_MODELO |

### Etapa: Producción diaria / PAM

| Dimensión | Campo | Fuente / constante | Disponibilidad |
|---|---|---|---|
| Flujo | `real_sag1_ton_dia`/`sag2_ton_dia` | `produccion_diaria_gpta.parquet` (real_sag1/sag2) | ACTIVA_EN_MODELO |
| Inventario | `sag1_ton_acum_turno`/`sag2_ton_acum_turno` | Derivado, `= tph × 5/60` acumulado | DISPONIBLE_CONTEXTO |
| Estado | `adherencia_pam_sag1_pct`/`sag2_pct` | Derivado: `real/pam × 100` | DISPONIBLE_CONTEXTO |
| Capacidad | `pam_sag1_ton_dia`/`sag2_ton_dia`/`sag_total_ton_dia` | `produccion_diaria_gpta.parquet` (pam_sag1/sag2/sag_total) | ACTIVA_EN_MODELO |
| Restricción | (mantenciones ya cubiertas como nodo transversal — ver sección 1) | — | — |
| Alarma | `riesgo_incumplimiento_pam` = 1 − `prob_cumplimiento_pam_sagX` | Derivado de `get_pam_monthly_projection()` | DISPONIBLE_CONTEXTO |
| Setpoint | (no aplica — el PAM es la meta, no una consigna de proceso) | — | — |
| Valor real | `prob_cumplimiento_pam_sag1`/`sag2` (probabilidad de cumplir meta del mes) | `engine/production_stats.py::get_pam_monthly_projection()` — ya expuesto en dashboard (`make_pam_probability_card`) | ACTIVA_EN_MODELO |

---

## 3. Lectura del mapa: dónde está el modelo hoy vs. dónde faltan datos

**Cadena completamente instrumentada y activa en el modelo** (sin brechas de
dato, solo de aplicación retroactiva — ver Fase 10 pregunta 1 y 4):
T1 → CV315/CV316 → Pila SAG1/SAG2 → SAG1/SAG2 → MoBos → PAM.

**Dos puntos ciegos estructurales del mapa**, en orden de aguas arriba a
aguas abajo:

1. **Chancado Primario (inventario y alarmas)** — el modelo salta
   directamente de "T8 activo/inactivo" a "T1 tiene tal flujo", sin ver los
   buffers intermedios (tolvas CH1/CH2, bins 517-522, buzón grueso) ni las
   restricciones que los vacían (atollo, bomba PPZ-058). Es el hueco más
   grande del mapa: toda la cadena aguas abajo depende de este nodo y hoy es
   una caja negra.
2. **SAG1/SAG2 (restricción física de potencia y setpoint vs. real)** — el
   modelo conoce el Qout medido pero no el techo físico (MW) ni si el Qout
   medido responde a una consigna que ya cambió (setpoint) o todavía no
   (retraso operador). Esto limita la capacidad de validar si una
   recomendación es *ejecutable*, no solo *óptima* en el balance de masa.

Estos dos puntos ciegos son exactamente los mismos identificados de forma
independiente en la Hoja 05 (`Variables_Prioridad`) y en
`20260709_PI_SCADA_Integration_Proposal.md` — el mapa causal no agrega
variables nuevas, **confirma con la vista de flujo end-to-end** que la
priorización ya hecha por impacto (Fase 4) coincide con dónde el proceso
físico realmente tiene menos visibilidad.

---

## 4. Checklist de criterios de éxito (Fase 2)

- [x] Mapa causal completo Mina/T8 → Chancado → T1 → T3 → CV315/CV316 → Pilas → SAG → MoBos → PAM/Producción.
- [x] Cada etapa con flujo, inventario, estado, capacidad, restricción, alarma, setpoint, valor real (o brecha explícita si no aplica/no existe).
- [x] Constantes citadas desde código real (`ode_model.py`), no supuestas.
- [x] Cruce explícito con Hoja 05 y el reporte PI/SCADA — confirma prioridades, no las contradice.
- [x] Puntos ciegos identificados y ordenados (Chancado Primario, condición SAG).
