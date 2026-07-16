# Diagnóstico de causa — deriva temporal sistémica vs. PAM Mantto real

## 🟡 Verificación de la relación física CV315↔SAG1 con datos PI reales (2026-07-15, continuación)

**Origen:** tras confirmar que `CTR CV15` = `CTR 315` (Correa
Transportadora 315, aclarado por el usuario), y ante la sugerencia de
usar la relación física entre la correa y el rate del molino (validada
primero con el caso de referencia CV316↔SAG2, que nunca se rompió) para
mejorar la reconstrucción de `correa_315`, el usuario proporcionó un
segundo export directo del PI System: `01_Data/Raw/Tonelajes_pila/
data_rendimiento_sag1.txt` (tag `REND_TMS_SAG1_PI`, 120.618 registros,
**2025-08-01 a 2026-07-15** — mucho más largo que el export de
`correa_315`, resolución nativa ~10 min).

### Hallazgo 1 — confirma que el "outage" de enero-febrero es real, no un artefacto

El export directo de `REND_TMS_SAG1_PI` confirma con densidad de
muestra constante (~144-148/día, sin caída de densidad tipo compresión)
que **SAG1 estuvo genuinamente detenido (0 TMS) desde el 2026-01-08
hasta el 2026-02-20** — 44 días consecutivos, una mantención mayor
real, no un problema de la bandera `SAG1_operando` del cache derivado
(que ya lo reflejaba correctamente). Días activos por mes en todo el
histórico disponible:

```text
2025-08:  8/31   2025-09: 25/30   2025-10: 28/31   2025-11: 30/30
2025-12: 28/31   2026-01:  7/31   2026-02:  3/28   2026-03: 29/31
2026-04: 20/30   2026-05: 31/31   2026-06: 28/30   2026-07: 15/15
```

Esto explica por qué el intento anterior de calibrar `correa_315 ~
SAG1_tph` con enero-febrero como "período limpio" fallaba (solo 6 días
con SAG1 activo disponibles ahí) — no es un error de filtrado, es que
ese período realmente no tiene suficiente dato útil.

### Hallazgo 2 — con más datos (sep-dic 2025), la relación es real pero no estable en el tiempo

Usando **septiembre-diciembre 2025** como entrenamiento (111 días con
SAG1 genuinamente activo, mucho más robusto que los 6 días de
enero-febrero) y **marzo 2026** como validación fuera de muestra (29
días activos, régimen distinto y no usado para entrenar):

| Modelo | R² fuera de muestra | MAE fuera de muestra |
|---|---:|---:|
| Regresión lineal `correa_315 = -111.7 + 0.791·SAG1_tph` | **-0.454** | 181.9 TPH |
| Razón mediana `correa_315 = 0.738·SAG1_tph` | **-0.940** | 221.2 TPH |

Ambos peores que un modelo trivial (media). La correlación **dentro**
del set de entrenamiento es real (r=0.625, sep-dic 2025) pero **no se
sostiene entre ventanas temporales distintas** — la razón mediana
`correa_315/SAG1_tph` es **0.738 en sep-dic 2025 pero 0.537 en marzo
2026**, una deriva de ~27% en la misma relación física, con ambos
períodos genuinamente activos (no contaminados por SAG1 apagado).

**Control con el caso de referencia (CV316↔SAG2, nunca roto):** la
misma razón mediana en CV316↔SAG2 también deriva en el tiempo, pero
mucho menos — 0.984 (sep-dic 2025) → 1.082 (marzo 2026) → 0.882 (mayo
2026), variación de ±10%, vs. ~27% en CV315↔SAG1. Confirma que **hay
una deriva de proceso genérica y esperable** (cambios de blend de
mineral, T3, regímenes operacionales) que afecta a ambos circuitos,
pero el circuito SAG1 la exhibe con casi 3x más magnitud — consistente
con que `correa_315` es una medición más problemática en general, no
solo durante la ventana de falla ya identificada.

### Conclusión honesta

1. **La intuición física del usuario es correcta**: SAG1 sí consume
   aproximadamente lo que `correa_315` le alimenta — la correlación es
   real y del mismo orden que el caso de referencia sin problemas
   (CV316↔SAG2).
2. **No es utilizable como reconstrucción cuantitativa confiable
   todavía**: la razón entre ambas variables no es estable en el
   tiempo (~27% de deriva entre ventanas de pocos meses), así que
   **ninguna fórmula fija calibrada en un período específico generaliza
   de forma confiable a otro** — el mismo patrón de "buen ajuste en
   calibración, malo fuera de muestra" que ya se documentó para el
   resto del modelo.
3. **La reconstrucción por regresión multivariada ya construida
   (R²=0.127, sección más abajo) sigue siendo la mejor disponible** —
   no porque sea buena en términos absolutos, sino porque los intentos
   más simples (univariados, con más datos, con relación física
   directa) no la superan de forma robusta fuera de muestra.
4. **No se modifica ningún parámetro de producción ni la
   reconstrucción usada en `755e83a`** — es exploración adicional,
   documentada honestamente incluyendo el resultado negativo.

Archivos nuevos: `01_Data/Raw/Tonelajes_pila/data_rendimiento_sag1.txt`
(export PI proporcionado por el usuario), `01_Data/Cache/
pi_sag1_rendimiento_raw_parsed.parquet` (parseado, reproducible).

---

## 🟢 Historia real reconstruida desde PI System (2026-07-15, dato directo del usuario)

**Origen:** el usuario exportó directamente desde el PI System el tag
crudo `CH1:210_WIT2001` (`correa_315`) — `01_Data/Raw/Tonelajes_pila/
data_cv315.txt`, 51.181 registros, `2026-04-05` a `2026-05-20`,
resolución nativa ~1 min. Es la fuente más autoritativa disponible en
el proyecto (viene directo del historian, no de un cache derivado) y
pidió reconstruir la historia con ella.

**Metodología:** no se "rellenan" valores — el sensor real reporta 0
exacto, no hay dato oculto que recuperar en este archivo. Se
reconstruye la **línea de tiempo** de cuándo el sensor funcionó, falló
intermitentemente y murió en forma permanente, usando dos señales
independientes del propio export: (1) valor medio por bloque de 4h, y
(2) densidad de muestras — el PI comprime por excepción, así que un
tag "vivo" y variable genera cientos de registros por bloque de 4h,
mientras uno plano en 0 genera solo ~4-5 (el "keep-alive" de
compresión). Script reproducible: `02_Analytics/Scripts/
statistical_validation/reconstruir_historia_pi_cv315.py`.

**Cronología reconstruida (fracción de bloques de 4h "muertos" por
día):**

```text
2026-04-05 a 04-10   0%    Funcionamiento normal continuo
2026-04-11 a 04-18   17-50% Degradación INTERMITENTE (alterna OK/caída)
2026-04-19 a 04-23   67-100% Degradación severa (casi todo el día caído)
2026-04-24 a 04-29   0%    RECUPERACIÓN COMPLETA (6 días normales)
2026-04-30 en adelante  100%  Falla PERMANENTE (sin recuperación hasta
                              el fin del export, 2026-05-20)
```

**Cruce con PAM Mantto real — dos candidatos, con distinto nivel de
confianza:**

1. **`CTR 315` (la correa/instrumento mismo, no solo el molino)** tuvo
   `Mtto Mensual` de 12h programado el **2026-04-16** — coincide con el
   inicio de la ventana de degradación intermitente (04-11 a 04-18).
   Es un candidato más directo que el retorqueo de trunnion de SAG1
   (que es el molino, no el instrumento de la correa).
2. El retorqueo de trunnion + crash stop de SAG1 (**2026-04-21 a
   04-23**, ya documentado en la sección siguiente) coincide con la
   ventana de degradación más severa (67-100% muerto esos días).
3. **La falla permanente del 2026-04-30 sigue sin una entrada de PAM
   inequívocamente asociada.** Existe una entrada `CTR CV15` (`Mtto
   Mensual`, 12h) el **2026-04-29**, un día antes — nombre
   suficientemente parecido a `CTR 315` como para ser sospechoso, pero
   **no se pudo confirmar si es la misma correa o una distinta** (podría
   ser literalmente "CV-15", un equipo diferente). No se trata como
   causa confirmada.

**Lo más importante — la recuperación completa del 04-24 al 04-29 es
una pieza nueva de evidencia:** el sensor funcionó perfectamente bien
durante 6 días justo antes de morir en forma permanente. Esto descarta
que la falla del 30 de abril sea la culminación gradual de un deterioro
continuo desde el 16 de abril — es un evento nuevo y distinto, separado
por casi una semana de operación normal. La búsqueda de su causa exacta
(diferente del `CTR 315` del 16 de abril) sigue abierta.

**Lo que este archivo NO permite hacer:** recuperar los valores reales
de `correa_315` después del 2026-04-30 — el sensor mismo reporta 0
exacto en la fuente más autoritativa disponible, así que la
reconstrucción numérica sigue dependiendo de la regresión estadística
ya construida (R²=0.127, sección más abajo), no de este archivo. Lo que
sí aporta es una cronología mucho más precisa y confiable de cuándo el
sensor era válido, que puede usarse para excluir con más precisión los
períodos del 11-23 de abril (parcialmente corruptos) del entrenamiento
de cualquier modelo futuro que use ese rango como "período limpio".

---

## 🔴 Hallazgo mayor (2026-07-15, continuación posterior a `755e83a`) — contaminación de eventos con SAG1 apagado

**Origen:** el usuario, al revisar el hallazgo de `correa_315`,
preguntó si los archivos PAM de mantenimiento podían explicar que los
equipos estuvieran detenidos esos días/horas, y observó correctamente
que "si hay mantenimientos para los SAG 1 o SAG 2, las correas cv315 y
cv316 deben estar sin alimentación, es decir detenidas". Se verificó
esa hipótesis directamente contra el dato real (`SAG1_operando`/
`SAG2_operando`, ya presentes en `advanced_t8_historical_5min.parquet`)
para las ventanas exactas de mantención del PAM, y **se encontró algo
más grande de lo que la pregunta buscaba**: no solo las ventanas de
mantención del PAM tienen SAG detenido (confirmado, ver tabla abajo) —
**el propio conjunto de 72 eventos oficiales usados para calibrar y
validar `t8_corta` está desbalanceado en la misma variable**, y eso
por sí solo explica la mayor parte de la "deriva temporal" atribuida
hasta ahora a `correa_315` y al PAM.

### Paso 1 — confirmación directa de la hipótesis del usuario

`SAG1_operando`/`SAG2_operando` promedio durante cada ventana de
mantención real del PAM (`advanced_t8_historical_5min.parquet`):

| Ventana PAM | SAG1 operando | SAG2 operando |
|---|---:|---:|
| Retorqueo trunnion SAG1, 2026-04-21 a 04-23 (crash stop) | **0.000** | 0.955 |
| Retorqueo trunnion SAG1, 2026-04-16 (parcial) | 0.378 | 0.993 |
| Alimentador 522 estandarización, 05-01 a 05-08 | 0.899 | 0.983 |
| Alimentador 518 estandarización, 05-11 a 05-25 | 0.943 | 0.859 |
| SAG2 cambio revestimiento, 05-25 a 05-29 | 0.993 | **0.315** |

Confirmado: el crash stop de SAG1 (21-23 abril) sí aparece como parada
real y completa en el dato (`SAG1_operando=0`, `correa_315≈3 TPH`) —
el PAM es una fuente confiable. El cambio de revestimiento de SAG2
también aparece como parada real y parcial. Las estandarizaciones de
alimentadores 518/522, en cambio, **no detuvieron el molino** (SAG1/
SAG2 siguieron operando >85% del tiempo) — coincidencia de fecha con
el inicio del hold-out, pero no explican el patrón por sí solas.

### Paso 2 — el hallazgo real: el set de 72 eventos oficiales T8 está contaminado

Se extendió la misma verificación a los **72 eventos oficiales T8**
(`advanced_t8_official_events.parquet`, la fuente que usa
`_run_backtest_t8` para calibración y hold-out), no solo a las 5
ventanas de mantención puntuales:

| | N eventos | `SAG1_operando` promedio | Eventos con SAG1 apagado (<50%) |
|---|---:|---:|---:|
| Calibración (`<2026-04-30`) | 50 | **0.310** | **34/50 (68%)** |
| Hold-out (`≥2026-04-30`) | 20 | **0.906** | 2/20 (10%) |

**El set de calibración tiene 6.5x más eventos donde SAG1 estaba
apagado que el hold-out.** Nueve eventos de calibración (2026-01-12 a
01-16, 01-28, 03-17 a 03-19) tienen **ambos** SAG1 y SAG2 apagados —
paradas de planta completas, no eventos T8 de drenaje real.

Cruzando esto con el error de pila que `_run_backtest_t8('t8_corta')`
ya calcula por evento (script reproducible:
`02_Analytics/Scripts/statistical_validation/
test_sag1_operando_composition.py`):

| Subgrupo | N | MAE pila SAG1 |
|---|---:|---:|
| Calibración, SAG1 apagado (evento trivial, sin drenaje real) | 28 | **2.70pp** |
| Calibración, SAG1 realmente operando | 16 | **26.12pp** |
| Hold-out, SAG1 apagado | 2 | 11.54pp |
| Hold-out, SAG1 realmente operando | 17 | **39.58pp** |

Correlación entre fracción de tiempo SAG1 operando y error de pila,
solo dentro de calibración: **r=0.865** — cuanto más tiempo estuvo
SAG1 realmente drenando la pila durante el evento, más grande el
error. Cuando SAG1 está apagado, la pila casi no se mueve y el motor
la predice casi perfectamente (trivial, no evidencia de buen ajuste).

**Reinterpretación del "3.3x peor en hold-out":** el MAE de calibración
reportado hasta ahora (11.21pp) es un promedio que mezcla 64% de
eventos triviales (error ~2.7pp) con 36% de eventos reales (error
~26pp) — está artificialmente bajo. El hold-out (36.63pp) es casi puro
evento real (90%). Comparando **como para como** (solo eventos con
SAG1 genuinamente operando en ambos lados): calibración 26.12pp vs.
hold-out 39.58pp — la brecha se reduce de "3.3x" a "1.5x", y **ambos
números ya están muy por sobre la tolerancia de 5pp**, no solo el
hold-out.

### Conclusión honesta

1. **La hipótesis del usuario es correcta y confirmada**: los eventos
   de mantención real del PAM sí muestran SAG detenido en el dato
   (`SAG1_operando=0`/`SAG2_operando=0`), consistente con lo esperado.
2. **El hallazgo más importante no es el PAM en sí, es un problema de
   criterio de validez de eventos**: `_run_backtest_t8` no excluye
   eventos donde SAG1 estuvo mayormente apagado durante la ventana T8
   — los trata igual que un evento real de drenaje. Como el 68% de los
   eventos de calibración caen en ese caso (vs. 10% en hold-out), el
   MAE de calibración reportado hasta ahora **no es comparable** al de
   hold-out — están midiendo mezclas de dificultad muy distintas, no
   solo períodos de tiempo distintos.
3. **La "deriva temporal sistémica" reportada en pasadas anteriores
   queda parcialmente reexplicada**: una parte importante de la
   diferencia calibración/hold-out es composicional (eventos triviales
   vs. reales), no necesariamente un cambio físico del proceso ni
   (solo) el sensor `correa_315` roto. Los tres hallazgos (sensor,
   contaminación de eventos, candidatos PAM de abril/mayo) son
   complementarios, no excluyentes.
4. **No se modifica ningún criterio de selección de eventos ni
   parámetro de producción en esta pasada** — es un hallazgo
   diagnóstico. El siguiente paso natural es decidir, con criterio de
   producto, si `es_valido_para_backtesting`/el filtro de eventos T8
   debe excluir formalmente ventanas donde SAG1 estuvo mayormente
   apagado (p. ej. `SAG1_operando` promedio < 50% durante `DURANTE`),
   y re-calibrar/re-validar `DRAIN_PCT_H` y demás parámetros solo sobre
   eventos genuinamente comparables.

---

## 🔵 Verificación adicional (2026-07-15, misma continuación) — PAM Productivo como proxy independiente

**Origen:** el usuario propuso una segunda forma de verificar/reconstruir
`correa_315`: cruzar el rendimiento histórico real de SAG1 con las
**metas diarias del PAM Productivo** (`01_Data/Raw/PAM/PAM_Produccion/
Pro{Mes}2026.xlsx`), independientes del sensor. Se probó.

**Fuente encontrada:** hoja `DATOS DÍA` tiene el programa diario de
`CV 315 S/PAC` y `CV 316` (TMS/día); hoja `Planta` tiene el programa
diario de `SAG 1`/`SAG 2` (TMS/día). Extraídos para los 6 meses
disponibles (script: `02_Analytics/Scripts/statistical_validation/
build_pam_produccion_daily_program.py`).

**Hallazgo 1 — confirmación cualitativa independiente, importante:**
el PROGRAMA de `CV 315` **nunca cae a cero** después del 2026-04-30
(media 675 TPH programados, min 28.8, max 1143 TPH en los 53 días
post-ruptura) — mientras el sensor real está en 0.0 exacto el 100% del
tiempo. Esto es evidencia independiente adicional (no estadística, es
el plan real de producción) de que la caída a cero es una **falla de
instrumentación**, no una decisión operacional de dejar de alimentar
por esa correa. Refuerza, con una fuente completamente distinta, la
conclusión ya alcanzada con el criterio del usuario sobre `SAG1_tph`.

**Hallazgo 2 (efecto secundario, no buscado):** el programa de `SAG 1`
también es mayor después del 2026-04-30 (936.6 TPH vs. 618.5 TPH
antes) — el aumento observado de `SAG1_tph` real (+60%, ya reportado
en la sección de abajo) **coincide con un aumento planificado**, no es
enteramente atribuible a una compensación por el sensor roto. Matiza
(no invalida) la interpretación anterior.

**Hallazgo 3 — como reconstrucción cuantitativa, no mejora el modelo
existente:** se agregó `cv315_prog_tph`/`sag1_prog_tph` (programa
diario, repetido en cada registro de 5 min del día) como predictores
extra a la regresión de reconstrucción ya validada (entrenada
enero-febrero, validada fuera de muestra en marzo limpio). Resultado:
R² fuera de muestra prácticamente no cambia (0.175 sin programa →
0.179 con programa) y el MAE empeora levemente (345.9 → 347.3 TPH). La
correlación programa-vs-real es moderada (r=0.67 para CV315, r=0.70
para SAG1) pero el programa es una meta **diaria**, sin la variación de
5 minutos que domina el error de reconstrucción — no aporta información
nueva más allá de la ya capturada por `correa_316`/`SAG1_tph`/`SAG2_tph`
reales.

**Conclusión honesta:** el PAM Productivo es útil como **verificación
cualitativa independiente** (confirma sensor roto, no proceso
detenido) pero no como insumo cuantitativo adicional para mejorar la
reconstrucción de `correa_315` ya construida (R²=0.127, sección más
abajo) — esa reconstrucción sigue siendo la mejor disponible sin datos
de Instrumentación. No se modifica ningún parámetro de producción ni
la reconstrucción ya usada en `755e83a`.

---

## ⚠️ Actualización — causa confirmada con certeza (no solo correlación temporal)

Después de identificar los candidatos del PAM Mantto (sección
siguiente), se ejecutó la prueba cuantitativa directa recomendada como
"próximo paso" y **se encontró un quiebre estructural confirmado, no
una hipótesis**:

```text
Serie diaria de correa_315 (advanced_t8_historical_5min.parquet):
  2026-04-25: 333.0 TPH promedio
  2026-04-26: 401.8 TPH
  2026-04-27: 397.2 TPH
  2026-04-28: 257.9 TPH
  2026-04-29: 101.0 TPH
  2026-04-30:   0.0 TPH   <-- cae a cero exactamente aquí
  2026-05-01 a 2026-06-21:  0.0 TPH en el 100% de los 53 días restantes
                             (fin del dataset disponible)
```

`correa_315` pasa de un promedio histórico de 449 TPH (con máximos de
hasta 1.950 TPH) a **exactamente cero, sin una sola excepción, en los
53 días que quedan del dataset** — no es un declive gradual ni datos
faltantes esporádicos, es un escalón perfecto en `2026-04-30`, la
misma fecha usada como corte de hold-out (elegida en la sesión
anterior por disponibilidad de eventos `t8_corta`, sin relación
previa con este hallazgo — la coincidencia de fecha es notable pero no
buscada).

**Más importante aún — esto no es solo una correa que se apagó, es una
medición que dejó de representar el feed real:**

| Período | `correa_316` medio | `correa_315+316` medio | `SAG1_tph` medio | `SAG2_tph` medio |
|---|---:|---:|---:|---:|
| Antes (`<2026-04-30`) | 1.858,9 | 2.309,7 | 651,9 | 1.823,2 |
| Después (`≥2026-04-30`) | 1.659,0 | **1.659,0** (−28%) | **1.045,0** (+60%) | 2.004,4 (+10%) |

`correa_316` sola **no compensa** la pérdida de `correa_315` (el feed
medido total cae 28%), pero el TPH real consumido por SAG1 **sube 60%**
y SAG2 también sube. Esto es físicamente inconsistente si
`correa_315+correa_316` siguiera siendo la medición completa del feed
real — la conclusión más plausible es que **la medición de alimentación
(`correa_315`, posiblemente también parte de `correa_316`) dejó de
representar correctamente el feed real de la planta a partir del
2026-04-30**, ya sea por un cambio físico real (redistribución de
correas, transferencia por una ruta no instrumentada) o por una falla/
cambio de instrumentación — coincide en fecha con la intervención de
`ALIMENTADOR 522 "estandarización de placas"` que arranca el
2026-05-01 (sección siguiente).

**Por qué esto explica el patrón de error ya documentado:** todo el
backtesting (`historical_backtesting.py`) y el Monte Carlo alimentan el
motor con `cv315_manual_tph`/`cv316_manual_tph` = el feed medido. Si
ese feed está **subestimado** a partir de esta fecha mientras el
consumo real (`SAG1_tph`/`SAG2_tph`) siguió siendo alto, el motor
simulado recibe "menos entrada de la que realmente hubo" y por
construcción **drena la pila simulada más rápido de lo que realmente
ocurrió** — exactamente el signo y la magnitud del sesgo ya reportado
(`pila_bias_sag1_pp` negativo en los 3 regímenes con mayor N:
`t8_corta` −16.91pp, `alimentacion_restringida` −11.82pp,
`inventario_critico` −11.02pp, ver `20260715_Diagnostico_Fidelidad_
Historica.md`). No es una coincidencia de timing — es un mecanismo
causal directo y verificable en el código.

---

## Candidatos del PAM Mantto (contexto operacional, sección original)

Fecha: 2026-07-15. Responde directamente el "próximo paso de mayor
ROI" de `Plan_Mejora_Simulador_2026-07-15.md`: investigar si hubo un
cambio operacional real entre el período de calibración (≤2026-04-30)
y el hold-out (>2026-04-30) que explique la deriva temporal sistémica
confirmada por 3 líneas de evidencia independientes (backtesting,
regresión, calibración de `p_safe`).

**Fuente:** `01_Data/Raw/PAM/PAM_Mantto/Programa Mantenciones {Enero..
Junio} 2026.xlsx`, hoja `Ejecutivo Mensual`, sección `MOLIENDA SAG`
(filas 113-138 aprox., varía levemente por mes). No se había parseado
esta sección antes en el proyecto — el loader existente
(`02_Analytics/Scripts/ingestion/loader.py::cargar_pam_mantto`) solo
extrae horas de ventana T8 desde la hoja `Ejecutivo Mensual` buscando
la palabra clave "Teniente 8", no el detalle de actividades de
mantenimiento por equipo.

## Candidatos encontrados, con fecha y evidencia directa del PAM

### 1. SAG1 — mantención mayor con Crash Stop, 16 al 23 de abril

```text
MOLINO SAG 1 | Retorqueo Trunnion - Grind Out / Mtto bimestral - Crash Stop
  2026-04-16: 14h | 2026-04-21: 15h | 2026-04-22: 24h | 2026-04-23: 11h
  (total 64h, replicado en MOLINO 411/412 individualmente: 62h c/u)
```

Un **retorqueo de trunnion** (ajuste estructural del soporte rotante
del molino) combinado con un **crash stop** (parada no programada/de
emergencia) justo 1 semana antes del corte de hold-out. Después de
esta intervención, SAG1 vuelve a operar con el trunnion recién
ajustado — un cambio mecánico real que puede alterar el comportamiento
de vibración/desgaste que el modelo no ve como variable.

### 2. Alimentador 522 — "estandarización de placas", 1 al 8 de mayo

```text
ALIMENTADOR 522 | Mtto horometros / estandarización de placas
  2026-05-01 a 2026-05-08 (188h totales, ~24h/día)
```

**Coincide casi exactamente con el inicio del hold-out** (>2026-04-30).
"Estandarización de placas" en un alimentador de correa es un cambio
real al mecanismo de control de alimentación — directamente relevante
al hallazgo ya confirmado de que el sigma de `feed_factor` en Monte
Carlo (`Calibracion_Monte_Carlo.md`) subestima la variabilidad real
por 2.85x.

### 3. Alimentador 518 — misma intervención, 11 al 25 de mayo

```text
ALIMENTADOR 518 | Mtto horometros / estandarización de placas
  2026-05-11 a 2026-05-25 (336h totales)
```

Segunda intervención de estandarización de placas, en el otro
alimentador del circuito SAG2, extendida por 2 semanas más de mayo.

### 4. SAG2 — cambio de revestimiento (liner), 25 al 29 de mayo

```text
MOLINO SAG 2 / MOLINO 511/512 | Cambio revestimiento MOL-511 + Bimestral SAG 2
  2026-05-25 a 2026-05-29 (55-90h según equipo)
```

Cambio de revestimiento interno del molino — geometría y desgaste de
la superficie de molienda cambian físicamente. Nota: esta actividad
estaba **planificada para abril y quedó en 0h ejecutadas** (diferida),
apareciendo recién ejecutada en mayo — es decir, el ciclo bimestral
normal de SAG2 se corrió de abril a mayo, coincidiendo con el inicio
del hold-out.

## Correlación temporal con los eventos de hold-out ya analizados

Los 19 eventos `t8_corta` del hold-out (`Validacion_Modelos_Regresion.
md`, sección 4) caen así respecto a estas intervenciones:

| Evento hold-out | Relación con las intervenciones |
|---|---|
| 2026-05-04, 05-05, 05-07 | **Durante** la estandarización de Alimentador 522 |
| 2026-05-12, 05-14, 05-15, 05-18, 05-20, 05-22 | **Durante** la estandarización de Alimentador 518 |
| 2026-05-28 | **Durante** el cambio de revestimiento SAG2 |
| 06-01 en adelante (7 eventos) | **Después** de las 4 intervenciones — régimen ya cambiado, no transitorio |

**Ningún evento del hold-out ocurre antes de la primera intervención**
(Alimentador 522, iniciada el mismo 2026-05-01) — el corte de
`2026-04-30` recomendado por el diagnóstico anterior separa,
accidentalmente pero de forma limpia, el período "antes de estas 4
intervenciones" del período "durante y después".

## Interpretación (evidencia real, no prueba de causalidad)

Esto **no demuestra** que alguna de estas 4 intervenciones sea la
causa del error — es correlación temporal fuerte con una fuente de
datos independiente (PAM Mantto real, no inferida), que es exactamente
el tipo de evidencia que ningún análisis puramente estadístico sobre
la serie de 5 min podía producir por sí solo. Dos hipótesis compiten,
ambas plausibles con esta evidencia:

1. **Los alimentadores 518/522 cambiaron el comportamiento real de
   alimentación** (la "estandarización de placas" pudo cambiar la
   relación entre apertura/estado de correa y TPH real entregado) —
   coincide con que el hallazgo de la regresión ya mostró que el
   hold-out tiene `feed_restriction_pct` *menor* en promedio pero aun
   así el modelo falla más: si el mecanismo de entrega cambió, el
   dato "correa reducida/activa" podría ya no significar lo mismo
   antes y después de la estandarización.
2. **El SAG1 retorqueado + crash stop de abril alteró la dinámica de
   pila** de forma persistente (nuevo estado de desgaste), afectando
   todos los eventos posteriores independientemente de la
   alimentación.

## Confirmación del usuario + prueba cuantitativa de corrección (2026-07-15, continuación)

**Confirmado por el usuario, con criterio verificable:** "si hay
rendimiento del SAG1, entonces el sensor de la correa estaba malo; si
ambos están detenidos, entonces en efecto estaba fuera de servicio."
Ya se había confirmado en la sección anterior que `SAG1_tph` observado
**sube** de 651,9 a 1.045,0 TPH promedio después del 2026-04-30 (no
baja, no se detiene) — por el propio criterio del usuario, esto
confirma que `correa_315` es un **sensor roto**, no una correa
realmente fuera de servicio.

El usuario proporcionó `01_Data/Raw/Tonelajes_pila/correas_ton.xlsx`
(datos cada 15 min, con columna `T3` nueva) como intento de corrección.
**Verificado que el tag crudo `CH1:210_WIT2001` (`cv315`) sigue en
0.0 exacto desde 2026-04-29 23:00 hasta el final del archivo
(2026-06-30) en este archivo también** — el sensor sigue sin
reportar valores útiles ahí, y `T3` no compensa la caída (se mantiene
~150-165 TPH antes y después, no absorbe los ~450 TPH perdidos). No
hay una reconstrucción numérica directa disponible en los datos
crudos — hubo que inferirla.

### Reconstrucción por proporción histórica (probada, no aplicada a producción)

Se calculó la proporción histórica `cv315 / (cv315+cv316)` en el
período `<2026-04-30` con ambas correas activas (`>50 TPH`):
**mediana 0.277** (rango intercuartílico 0.215-0.337, N=11.517
registros de 15 min). Se usó esta proporción para reconstruir
`cv315_estimado = cv316_observado × (0.277/0.723)` **solo** en eventos
donde `cv315` cruda = 0 y `cv316` > 50 TPH (patrón de sensor roto), y
se re-corrió el backtesting de `t8_corta` con este valor reconstruido
en vez del crudo.

| Split | MAE con `cv315` cruda | MAE con `cv315` reconstruida | Mejora |
|---|---:|---:|---:|
| Calibración (sin cambios, `cv315` ya era válida) | 11.21pp | 11.21pp | — |
| Hold-out | 36.63pp | **27.26pp** | **−25.6%** |

**Conclusión honesta — mejora real pero no cierra la brecha
completa:** el sensor roto de `correa_315` **explica una parte
sustancial y real** de la deriva temporal (un cuarto del error
desaparece con una reconstrucción simple), pero el hold-out corregido
(27.26pp) **sigue siendo 2.4x peor que calibración** (11.21pp) y muy
por encima de la tolerancia de 5pp. Esto es evidencia de que:

1. El sensor roto de `correa_315` es un **contribuyente real
   confirmado**, no la explicación completa.
2. La proporción histórica fija (0.277) es una reconstrucción
   **aproximada** (desviación estándar 0.139 en el período de
   referencia) — probablemente subestima o sobreestima `cv315` según
   el evento específico, dejando ruido residual.
3. **Los hallazgos del PAM Mantto siguen siendo relevantes**: el
   retorqueo de trunnion + crash stop de SAG1 (16-23 abril) y las
   intervenciones de "estandarización de placas" en los alimentadores
   518/522 (mayo) pueden explicar el resto de la brecha — no se
   descartan por este resultado, se suman como causas parciales.

## Reconstrucción final con regresión + re-ejecución completa (2026-07-15, continuación final)

**Pedido del usuario**: reconstruir la tabla completa de eventos con
`cv315` corregida y re-correr regresión + calibración de `p_safe`
sobre datos limpios, usando "matemática simple, interpolación o algún
método numérico" para las brechas.

### Metodología de reconstrucción (mejorada sobre la proporción fija)

Se probaron 3 métodos de reconstrucción de `cv315` post-2026-04-30,
validados **fuera de muestra en una ventana limpia** (marzo 2026,
entrenando con enero-febrero — la ventana 25-29 abril se descartó por
estar contaminada: el sensor ya declinaba ahí, dando R² negativo para
los tres métodos incluida la mediana simple):

| Método | R² fuera de muestra | MAE fuera de muestra |
|---|---:|---:|
| Regresión lineal (`cv315 ~ correa_316 + SAG1_tph + SAG2_tph`) | **0.127** | 336 TPH |
| Proporción histórica `cv315/cv316` | −0.657 | 445 TPH |
| Mediana simple | −1.303 | 542 TPH |

Se usó la regresión lineal (único método con R² positivo, aunque débil
— **advertencia explícita: ~87% de la varianza no se explica**, esto
es una reconstrucción de alta incertidumbre, no un sustituto confiable
del sensor real). Entrenada con los 78.288 registros de 5 min
`<2026-04-30`, aplicada a los 15.264 registros posteriores. Brechas
cortas preexistentes (≤12 NaN por columna, no relacionadas con el
sensor roto) rellenadas con interpolación temporal simple (límite 15
min, sin rellenar huecos largos a ciegas). `T3` (dato nuevo del
usuario) agregado por remuestreo de 15 a 5 min.

**Se corrigieron ambas fuentes afectadas**: `advanced_t8_historical_
5min.parquet` (serie continua, usada por los regímenes proxy) y
`advanced_t8_event_windows.parquet` (usada específicamente por el
backtesting "oficial" de `t8_corta`/`t8_larga` — tenía el mismo
problema, no detectado hasta ahora). Copias guardadas con sufijo
`_corrected`, originales sin modificar.

Scripts: `rebuild_corrected_historical_series.py`,
`build_event_variable_table_corrected.py` (monkeypatch de
`regime_event_detector._load_serie`, sin tocar código de producción).

### Resultado — mejora sustancial en fidelidad, resolución casi completa en `p_safe`

**Fidelidad física (`t8_corta`, `Validacion_Modelos_Regresion.md`
recalculado):**

| Métrica | Original (sensor roto) | Corregido | Mejora |
|---|---:|---:|---:|
| MAE hold-out (regresión multivariada) | 11.63pp | **8.46pp** | −27% |
| MAE hold-out (univariado, solo breakpoints) | 36.63pp | **17.80pp** | −51% |
| % eventos que cruzan breakpoint 35% en hold-out | 100% | 84.2% | — |

Los demás regímenes también mejoran o se mantienen: `alimentacion_
restringida` 5.76→6.33pp (estable), `inventario_critico` 12.52→11.57pp,
`mantenimiento` 17.62→13.46pp. **Los coeficientes y variables
significativas de la regresión no cambian cualitativamente** — mismo
patrón, menor magnitud de error.

**Calibración de `p_safe` — mejora dramática, casi resuelta:**

| Split | Brier original | Brier corregido |
|---|---:|---:|
| Calibración | 0.180 | 0.180 (sin cambio, no afectado por el sensor) |
| Hold-out | 0.621 (muy mal calibrado) | **0.004** (casi perfecto — mejor que calibración) |

`p_safe` medio predicho en hold-out pasa de 0.248 (pesimista, casi
siempre "no seguro") a 0.919, casi exactamente la frecuencia real
observada (0.947).

### Conclusión honesta

**El sensor roto explica la gran mayoría del problema de calibración
de `p_safe`** (que es la señal que ve directamente el Jefe de Sala) —
prácticamente resuelto con la corrección. **Explica una parte
sustancial pero no completa del error de fidelidad de pila en `t8_corta`**
(MAE hold-out sigue en 17.8-8.46pp según el modelo, 1.6-2.2x peor que
calibración, todavía sobre la tolerancia de 5pp) — el residuo restante
es consistente con los otros candidatos del PAM Mantto ya identificados
(retorqueo trunnion + crash stop SAG1 16-23 abril, estandarización de
alimentadores mayo), y con la incertidumbre propia de una
reconstrucción con R²=0.127.

**No se recalibra ningún parámetro de producción todavía** — la
reconstrucción de `cv315` es de alta incertidumbre (R²=0.127) y no
reemplaza al sensor real. El siguiente paso correcto es obtener la
serie real corregida desde Instrumentación (no una reconstrucción
estadística) antes de tratar estos números como definitivos para
recalibración.

## Próximo paso concreto

**Confirmado: sensor roto (criterio del usuario + evidencia), con una
reconstrucción simple que explica ~26% de la brecha, no el 100%.**
Pendiente:

1. **Confirmar con Instrumentación** desde cuándo y por qué falló el
   tag `CH1:210_WIT2001` — sigue sin reportar valores útiles incluso en
   el archivo corregido que trajo el usuario, así que la corrección
   tuvo que ser inferida estadísticamente, no leída directamente.
2. **Mejorar la reconstrucción de `cv315`** más allá de una proporción
   histórica fija: usar una proporción condicionada por régimen/nivel
   de pila/hora, o un modelo de regresión `cv315 ~ cv316 + SAG1_tph +
   contexto`, entrenado solo con datos `<2026-04-30` donde el sensor
   era válido.
3. **Investigar el 74% de la brecha que la reconstrucción no explica**
   — candidatos ya identificados en el PAM Mantto real: retorqueo de
   trunnion + crash stop de SAG1 (16-23 abril) y estandarización de
   placas en alimentadores 518/522 (mayo). Ninguno descartado, ninguno
   confirmado como causa cuantitativa todavía.
4. **Reconstruir `event_variable_table.csv` con `cv315` corregida** y
   re-correr los 3 bloques de análisis de hoy (regresión, calibración
   de `p_safe`) para ver cuánto de la "deriva temporal sistémica" ya
   reportada persiste con el feed corregido — no ejecutado esta pasada
   por alcance, es la extensión natural de este hallazgo.
5. **No recalibrar ningún parámetro de producción** hasta completar 2-4
   — la corrección actual (proporción fija) es solo para diagnóstico,
   no para producción.
