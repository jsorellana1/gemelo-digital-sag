# Sábana Maestra SAG — Fase 10: Loop obligatorio de preguntas

**Fecha:** 2026-07-13
**Documento base:** `01_Data/Templates/generate_sabana_master.py` → `sabana_master_sag_5min.xlsx`
(Hojas 01-06 ya generadas y verificadas contra fuentes reales, ver docstring del
script para el detalle de columnas leídas por `pandas.read_excel`/`read_parquet`).
**Documento complementario:** `04_Reports/Technical/20260709_PI_SCADA_Integration_Proposal.md`
(inventario SCADA de 2 pantallas PI reales, 12 candidatas visuales).

Este documento cierra la Fase 10 del prompt de diseño de la sábana maestra:
responde explícitamente las 10 preguntas obligatorias, citando la hoja/fuente
que sustenta cada respuesta. Donde la pregunta no tiene respuesta cerrada, se
deja la brecha explícita en vez de forzar una respuesta.

---

## 1. ¿Qué datos faltan para calcular autonomía con menor error?

**Respuesta:** ningún dato crudo nuevo es estrictamente necesario para bajar
el error de autonomía en el corto plazo — el mayor error hoy no viene de
falta de datos sino de que `autonomia_sag1_h`/`autonomia_sag2_h` **nunca se
calculó sobre la serie histórica real completa** (Hoja 01, campo
`autonomia_sag1_h`: "NO CALCULADO historicamente — `compute_autonomia()`
solo se aplica en simulación"). Aplicar retroactivamente
`historical_backtesting.py::_tiempo_hasta_umbral` sobre todo el histórico
2025-08+ (no solo por evento T8) permitiría medir el MAE real de autonomía
por primera vez.

Con eso resuelto, los datos que sí reducirían el error del **modelo físico**
(no solo la validación) son, en orden de impacto (Hoja 05):
1. `sag1_potencia_mw` / `sag2_potencia_mw` — techo real de Qout, hoy asumido constante.
2. `nivel_tolva_ch1_pct` / `nivel_tolva_ch2_pct` / `nivel_bins_517_522_pct` — dan
   visibilidad de Qin con más anticipación que el nivel de pila solo.
3. `sag1_pebbles_tph` / `sag2_pebbles_tph` (PAC) — reduce el Qin neto real vs. nominal.

**Brecha explícita:** ninguna de las tres tiene tag PI confirmado ni serie
histórica extraída (Hoja 03, columna `disponible`="No"). No se puede
cuantificar la mejora de MAE sin al menos 2-4 semanas de datos reales.

---

## 2. ¿Qué datos faltan para anticipar vaciado?

**Respuesta:** el modelo ya calcula `riesgo_vaciado_sag1`/`sag2` vía
`optimizer_v2.py::adaptive_mc_eval` (Hoja 01, ACTIVA_EN_MODELO), pero solo
**por escenario simulado**, nunca corrido retrospectivamente contra el
histórico real — no existe una serie `riesgo_vaciado_sagX` calculada día a día
para comparar contra los vaciados que efectivamente ocurrieron.

Dato faltante de mayor apalancamiento: **alarma de atollo del chancador**
(`atollo_ch1`/`atollo_ch2`) y **estado de la bomba PPZ-058** — son las dos
restricciones aguas arriba que hoy el simulador no ve y que, si ocurren,
cortan Qin sin que el modelo lo anticipe (ver
`20260709_PI_SCADA_Integration_Proposal.md` sección 3, "Restricciones
operacionales"). Ambas están en el 1er lote recomendado de ese documento por
tener matriz de impacto Alto/Alto/Alto.

**Brecha explícita:** no existe tag PI confirmado para ninguna de las dos
(Hoja 03: "POR CONFIRMAR"). Se puede cerrar en el corto plazo como **input
manual del JdS** (ver pregunta 10) mientras se solicita el tag real.

---

## 3. ¿Qué datos faltan para anticipar overflow?

**Respuesta:** misma situación que vaciado — `riesgo_overflow_sag1`/`sag2`
existe (`optimizer_v2.py`, `pct_overflow_sag1`) pero **nunca se usó como
filtro duro**, solo como penalización blanda en el score (Hoja 01, nota
explícita: "ver hallazgo 2026-07-09 en el reporte técnico"). El dato que
falta no es una variable física nueva sino **historificar la salida del
modelo** para poder comparar predicción de overflow vs. overflow real
observado (`pila_sag1_pct`/`pila_sag2_pct` ya cruzando el umbral superior).

Dato físico nuevo de mayor valor: `sag1_tph_setpoint`/`sag2_tph_setpoint`
(consigna vs. real) — un overflow casi siempre empieza como una consigna que
no baja a tiempo cuando Qin cae; sin la serie de setpoint no se puede
distinguir "el operador no bajó el rate" de "el modelo predijo mal".

**Brecha explícita:** `sag1_tph_setpoint`/`sag2_tph_setpoint` marcados
`NO_DISPONIBLE` en Hoja 01 — no existe tag PI de consigna separado del valor
medido en ninguna fuente actual.

---

## 4. ¿Qué datos faltan para explicar la variabilidad?

**Respuesta:** el cálculo ya existe y está calibrado
(`engine/variability_metrics.py`, 2026-07-09) pero **solo se aplica a
simulaciones**, nunca sobre la serie real continua (Hoja 01,
`cv_tph_sag1_1h`: "NO CALCULADO historico"). Esto es Hoja 05 fila 1,
`IMPLEMENTAR AHORA`, score más alto de toda la matriz de priorización —
no requiere ningún dato nuevo, solo aplicar el código existente sobre
`advanced_t8_historical_5min.parquet`.

Para **explicar la causa** de la variabilidad (no solo medirla), el dato que
falta es `n_cambios_setpoint_sag1`/`sag2` — hoy no hay forma de distinguir
variabilidad causada por el proceso (T8, mantención) de variabilidad causada
por cambios de consigna del operador, porque no existe la serie de setpoint
(ver pregunta 3).

**Brecha explícita:** sin `sag1_tph_setpoint`, la variabilidad explicada
queda incompleta — se puede medir el efecto (CV del TPH real) pero no
atribuir la causa completa.

---

## 5. ¿Qué datos faltan para distribuir mejor CV315/CV316/T3?

**Respuesta:** el dato más crítico ya existe pero no se usa:
`t1_tph` (Hoja 01: `DISPONIBLE_NO_USADA`, `tonelaje_v2.xlsx` columna T1,
con valores negativos observados que requieren clip — Hoja 04). Ingestarlo
con la regla de calidad ya documentada es Hoja 05 fila 4, `IMPLEMENTAR AHORA`.

Lo que falta y **no existe en ninguna fuente**: `t3_tph` como serie real
(hoy el motor solo usa `t3_frac` como parámetro manual de escenario, Hoja 01)
y `distribucion_t1` — la estrategia de reparto CV315/CV316 realmente usada
en cada momento **nunca se registró** ("no existe log de decisiones
operacionales, closed-loop hoy no existe", Hoja 01). Sin esto no se puede
aprender de qué estrategia de distribución funcionó mejor en la práctica,
solo simular estrategias hipotéticas.

**Brecha explícita:** `t3_tph` y `distribucion_t1` reales requieren
extracción PI nueva + un logger de decisiones que hoy no existe en ningún
componente del dashboard.

---

## 6. ¿Qué dato mejora más la simulación?

**Respuesta (Hoja 05, score más alto):** aplicar `variability_metrics.py` y
`harmony_index.py` sobre el histórico real completo (no solo simulaciones en
vivo). Score 70-80 en impacto autonomía/distribución con disponibilidad y
facilidad de captura en 90-100% — el código ya existe, calibrado, documentado
el 2026-07-09; el "dato faltante" no es una variable física sino la corrida
retrospectiva que nunca se hizo. Es la mejora de mayor ROI porque **no
requiere ninguna extracción PI nueva**.

En variables físicas nuevas (con extracción PI pendiente), el mayor impacto
esperado es `sag1_potencia_mw`/`sag2_potencia_mw` (score 60 en Hoja 05, único
dato de "condición de molienda" que valida si un rate recomendado es
físicamente alcanzable, no solo matemáticamente óptimo).

---

## 7. ¿Qué dato aporta poco y debe descartarse?

**Respuesta (Hoja 05 y Hoja 07 del prompt, ya aplicada):**
`pH`, `ley (Cu%)`, `reactivos`, `molibdeno`, `relaves`, `espesadores`, `agua
de proceso` — descartados explícitamente con evidencia, no por omisión: el
propio proyecto ya midió la correlación (r=0.02 ley, r=-0.15 recuperación,
ver `20260706_Reenfoque_Simulador_Basado_Evidencia.md` citado en Hoja 05) y
es nula-a-débil con TPH. `es_feriado` también queda en `EVALUAR` y no
`IMPLEMENTAR AHORA` — fácil de agregar pero sin impacto físico demostrado
en el modelo (Hoja 05: "evaluar como covariable de contexto, no como input
crítico").

`temperatura_rodamientos_ch1/ch2`, `estado_colectores_polvo`, `corriente
motores CV-10/CV-11`, `CEE SAG I/II (kWh/ton)` quedan en prioridad Media/Baja
en `20260709_PI_SCADA_Integration_Proposal.md` sección 1 — indicadores
secundarios de riesgo de detención, no restricciones directas de Qin/Qout.

---

## 8. ¿Qué tags PI deben solicitarse primero?

**Respuesta (matriz de impacto Alto/Alto/Alto, sección 5 del reporte PI/SCADA,
más Hoja 05):**

1. **Nivel Tolva CH1 / CH2 (%)** — buffer de alimentación fina pre-SAG.
2. **Nivel bins Distrib. 2500 ton (517-522)** — tolva intermedia directa a CTR-516/CTR-461.
3. **Alarma Atollo Chancador (CR-01/CR-02)** — restricción binaria aguas arriba.
4. **Potencia SAG1/SAG2 (MW)** — techo real de Qout, valida factibilidad de la recomendación.

Los 4 están marcados "POR CONFIRMAR" en Hoja 03 (`03_Catalogo_PI_Tags`) con
la pantalla SCADA de origen ya identificada (`Chancado Primario`,
`Diagrama Principal Concentrador`) pero sin tag PI exacto — el siguiente paso
concreto es una solicitud formal al Especialista PI System con esas 4
variables, no las 12 completas del inventario SCADA.

---

## 9. ¿Qué frecuencia mínima se necesita?

**Respuesta:** **5 minutos**, igual que el resto de la sábana — es la
frecuencia nativa de `tonelaje_v2.xlsx`, `estados_activos.xlsx` y los
parquets ya en producción (`advanced_t8_historical_5min.parquet`). No hay
justificación para pedir mayor frecuencia (1min) porque el ODE
(`engine/ode_model.py`) y el horizonte de simulación (`max(24h, t8+8h)`)
operan a paso de 5min; pedir más resolución que la que consume el modelo
solo agrega volumen sin valor.

**Excepción documentada:** las alarmas binarias (`atollo_ch1/ch2`, alarma de
colectores) pueden tener frecuencia "evento" en vez de 5min continuo (Hoja
01, columna `frecuencia`) — se necesita el timestamp del cambio de estado,
no un valor repetido cada 5min sin cambios.

**Brecha explícita:** `es_feriado` y variables diarias del PAM
(`pam_sag1_ton_dia`, etc.) son de frecuencia diaria por naturaleza — no
aplica pedir 5min para esas.

---

## 10. ¿Qué variables pueden ser ingresadas manualmente por el JdS mientras no exista integración automática?

**Respuesta:** las 12 candidatas de `20260709_PI_SCADA_Integration_Proposal.md`
sección 4 cumplen la regla de admisión ya validada en ese documento — **el
JDS debe poder leerlas en menos de 10 segundos desde una pantalla PI ya
abierta**, sin historiador ni cálculo adicional:

| Input manual | Tipo | Prioridad de carga manual |
|---|---|---|
| Potencia SAG1 / SAG2 (MW) | Numérico | Alta |
| RPM SAG1 / SAG2 | Numérico | Alta |
| Nivel Tolva CH1 / CH2 (%) | Numérico | Alta |
| Nivel bins Distrib. 2500 ton (%) | Numérico | Alta |
| Estado PAC / pebbles (tmh) | Numérico | Alta |
| Alarma Atollo Chancador | Binario Sí/No | Alta |
| Estado Bomba PPZ-058 | Binario Operando/Detenida | Alta |
| Posición Manto CR-01/CR-02 (%) | Numérico | Media |
| Buzón Grueso Línea 2 (%) | Numérico | Media |
| Temperatura Rodamientos Chancador (°C) | Numérico | Media |
| Estado Colectores de Polvo | Binario Normal/Alarma | Media |

De estas, las **4 de prioridad de carga "Alta" cruzadas con la matriz de
impacto Alto/Alto/Alto** (Nivel Tolva CH1/CH2, bins Distrib. 2500 ton, Alarma
Atollo Chancador) son las que deberían implementarse primero como campo de
entrada manual en el dashboard — mismo orden que la pregunta 8, porque son
las mismas 4 variables mientras no exista el tag PI automático.

**Brecha explícita:** ninguna variable de Bloque J/L/M (PAM, riesgo,
recomendación) es candidata a ingreso manual — son todas salidas calculadas
del modelo, no lecturas de campo; cargarlas manualmente rompería la
trazabilidad de qué fue medido vs. qué fue calculado.

---

## Resumen ejecutable (qué hacer primero, sin esperar nueva extracción PI)

Estas 5 acciones **no requieren ningún tag PI nuevo** — usan código o datos
que ya existen (Hoja 05, filas `IMPLEMENTAR AHORA`):

1. Aplicar `variability_metrics.py` sobre el histórico real completo.
2. Aplicar `harmony_index.py` sobre el histórico real completo.
3. Agregar logging de `rate_recomendado_sagX_tph` + `accion_recomendada`
   (closed-loop, similar a `utils/perf_logger.py`).
4. Ingestar `t1_tph` real con el clip de valores negativos (regla ya en Hoja 04).
5. Ingestar `ch1_on/ch2_on/mobo_41X/51X_on` reales en vez de parámetro manual
   del usuario (ya disponibles en `estados_activos.xlsx`).

Estas 4 requieren solicitud a Especialista PI System (preguntas 8 y 10, en
paralelo se pueden habilitar como input manual del JdS):

1. Nivel Tolva CH1 / CH2 (%)
2. Nivel bins Distrib. 2500 ton (517-522) (%)
3. Alarma Atollo Chancador
4. Potencia SAG1 / SAG2 (MW)
