# Plan de mejora — Simulador Operacional SAG

Fecha: 2026-07-15. Síntesis ejecutiva del programa de validación
estadística (37 secciones pedidas, 4 bloques ejecutados hoy) sobre el
Simulador Operacional SAG / Gemelo Digital. Consolida:

- `Analisis_Estadistico_Simulador.md` + `Validacion_Modelos_Regresion.md` (fidelidad física)
- `Validacion_Motor_Recomendaciones.md` (motor de recomendaciones)
- `Calibracion_Monte_Carlo.md` (sigmas + calibración de `p_safe`)
- `20260715_Diagnostico_Fidelidad_Historica.md` (sesión previa, mismo día)

Sigue el formato pedido en la sección 37 del prompt de validación:
modelo recomendado, evidencia, recomendaciones, riesgos, próximo paso
de mayor ROI. **No se modificó código de producción en ninguno de los
4 bloques** — todo lo que sigue es evidencia para decidir, no cambios
ya aplicados.

---

## 0. ACTUALIZACIÓN CRÍTICA (post-síntesis, misma fecha) — causa probable encontrada

Después de escribir este plan, se cruzó el hallazgo de la sección 1
contra `01_Data/Raw/PAM/PAM_Mantto/` (planes de mantención reales,
sugerido por el usuario) y se encontró un **quiebre de datos
confirmado, no una hipótesis**: `correa_315` (una de las dos
mediciones de alimentación que usa todo el sistema) cae a **exactamente
cero en el 100% de los 53 días** desde `2026-04-30` en adelante — la
misma fecha del corte de hold-out — mientras `SAG1_tph`/`SAG2_tph`
observados **suben** en ese mismo período. Esto es evidencia fuerte de
que la "deriva temporal sistémica" de la sección 1 **probablemente no
es un cambio del proceso físico real**, sino **un artefacto de
instrumentación/medición de feed que invalida el feed medido como
input de calibración desde esa fecha**. Ver detalle completo en
`Diagnostico_Causa_Deriva_Temporal_PAM.md`.

**Confirmado por el usuario** (criterio: si SAG1 siguió con rendimiento
real, el sensor estaba malo, no la correa fuera de servicio — y
`SAG1_tph` sube después del 2026-04-30, no baja).

**Reconstrucción final y re-ejecución completa (misma fecha,
continuación final):** se reconstruyó `cv315` con un modelo de
regresión (`cv315 ~ correa_316 + SAG1_tph + SAG2_tph`, validado fuera
de muestra R²=0.127 — débil, alta incertidumbre, pero el único de 3
métodos probados con R² positivo) sobre ambas fuentes de datos
afectadas, y se re-ejecutaron regresión y calibración de `p_safe`
completas sobre los datos corregidos:

| Resultado | Original (sensor roto) | Corregido |
|---|---:|---:|
| MAE `t8_corta` hold-out (univariado) | 36.63pp | **17.80pp (−51%)** |
| MAE `t8_corta` hold-out (regresión) | 11.63pp | **8.46pp (−27%)** |
| Brier de `p_safe` hold-out | 0.621 (muy mal calibrado) | **0.004 (casi perfecto)** |

**La calibración de `p_safe` — la señal que ve directamente el Jefe de
Sala — queda prácticamente resuelta.** La fidelidad de pila mejora
sustancialmente pero no se cierra del todo (sigue 1.6-2.2x peor que
calibración) — el residuo es consistente con los otros candidatos del
PAM Mantto (retorqueo trunnion + crash stop SAG1, estandarización de
alimentadores) y con la incertidumbre de la reconstrucción (R²=0.127,
no es un sustituto del sensor real). Detalle completo en
`Diagnostico_Causa_Deriva_Temporal_PAM.md`.

**Esto cambia la prioridad del plan otra vez**: el próximo paso de
mayor ROI ya no es "confirmar qué pasó" (confirmado) — es (a) mejorar
la reconstrucción de `cv315` más allá de una proporción fija, y (b)
investigar el ~74% de la brecha restante, para lo cual los candidatos
del PAM Mantto (retorqueo de trunnion + crash stop SAG1 en abril,
estandarización de placas en alimentadores en mayo) siguen siendo
relevantes y no se han descartado.

---

## 1. El hallazgo que domina todo lo demás: deriva temporal sistémica

Tres líneas de evidencia **independientes**, generadas con métodos
distintos, apuntan al mismo fenómeno: el simulador se comporta peor —
de forma sistemática, no aleatoria — sobre eventos posteriores a
**2026-04-30** que sobre eventos anteriores a esa fecha.

| Línea de evidencia | Calibración (≤2026-04-30) | Hold-out (>2026-04-30) | Fuente |
|---|---|---|---|
| MAE de pila (`t8_corta`) | 11.21pp | **36.63pp** (3.3x peor) | `20260715_Diagnostico_Fidelidad_Historica.md`, Fase 6 |
| Regresión multivariada (`t8_corta`) | MAE modelo 3.79pp (R²=0.869) | **11.63pp** (3.1x peor) | `Validacion_Modelos_Regresion.md`, sección 2 |
| % eventos que cruzan breakpoint 35% (`t8_corta`) | 54.5% | **100%** | `Validacion_Modelos_Regresion.md`, sección 4 |
| Calibración de `p_safe` (Brier score) | 0.180 (mejor que baseline) | **0.621** (mucho peor que baseline) | `Calibracion_Monte_Carlo.md` |

**Ya se descartó, con evidencia experimental real, que sea explicable
por:**
- Eventos hold-out más severos en las variables medidas — al
  contrario, tienen en promedio *menos* restricción de alimentación
  (`Validacion_Modelos_Regresion.md`, sección 4).
- `DRAIN_PCT_H` mal calibrado — recalibrarlo con el split real no
  mueve el MAE de pila (`20260715_Diagnostico_Fidelidad_Historica.md`,
  Fase 6).
- `_pile_feedback_factor` sobreactuando — debilitarlo empeora el
  hold-out de forma monótona (Fase 6.1 del mismo diagnóstico).
- Confusión de la validación de `p_safe` por rate mal parametrizado —
  se corrigió metodológicamente y el patrón persiste igual de fuerte.

**No se ha identificado la causa física.** Es sistémica (aparece,
más leve, también en `alimentacion_restringida`), lo que sugiere algo
que afecta a toda la planta entre mayo y junio de 2026, no un
mecanismo exclusivo de T8. Candidatos plausibles sin confirmar:
mantención mayor de algún equipo, recalibración de instrumentos,
cambio real de procedimiento operacional, o un cambio en el mineral/
proceso aguas arriba.

---

## 2. Modelo recomendado

**Mantener el motor agregado (`ode_model.py`/`simulate_scenario`)
como única fuente de verdad productiva.** No hay evidencia para
reemplazarlo por:

- **Multicelda** (ya evaluado en sesión previa): mejora real pero
  insuficiente incluso en el mejor caso (SAG2 + `t8_corta`), todos los
  MAE resultantes siguen sobre la tolerancia de 5pp. Confirmado como
  línea de I+D, no como reemplazo (`20260715_Investigacion_Multicelda_
  SAG1_SAG2.md` y siguientes).
- **Modelo puramente estadístico** (regresión sin física): el modelo
  de regresión de hoy alcanza buen ajuste en calibración pero **no
  generaliza mejor que el motor físico** en el régimen con el peor MAE
  (`t8_corta`) — sufre la misma deriva temporal. Un modelo estadístico
  puro no habría sido inmune a este problema.
- **V4/V5** (`optimizer_v4.py`/`optimizer_v5.py`): sin consumidores de
  producción (`in_degree=0` confirmado vía MCP), decisión ya tomada de
  no conectar sin definición de producto sobre qué filosofía de
  recomendación se prefiere.

El motor de recomendaciones (`recommend_action`) se mantiene como
motor principal — validado 4/5 en escenarios dorados.

---

## 3. Recomendaciones concretas

### 3.1 Qué motor usar
- **Grid determinístico + Monte Carlo actuales** (`optimizer_v2.py`),
  con el dual score ya agregado hoy en la Fase 3.6 (`p_dynamic_safe`)
  como señal complementaria — no reemplazar la selección oficial
  todavía (no hay evidencia suficiente de qué candidato es realmente
  mejor, solo evidencia de que a veces divergen).
- **`recommend_action`** como motor único de recomendación operacional.

### 3.2 Qué reglas mantener
- `_pile_feedback_factor`: **no tocar** — la evidencia hold-out dice
  que debilitarlo empeora el modelo, aunque no esté formalmente
  calibrado con una fuente citada.
- Reglas de escenarios dorados (autonomía dinámica, cruce de niveles
  críticos): 4/5 validadas correctamente, mantener sin cambios.

### 3.3 Qué cambiar (con evidencia, ninguno aplicado todavía)
1. **Motor de recomendaciones**: agregar cobertura para "SAG apagado +
   pila subiendo hacia el límite" — hoy retorna `OPERACION_NORMAL` sin
   ninguna escalación (`Validacion_Motor_Recomendaciones.md`). Requiere
   decisión de producto sobre la acción/mensaje correcto, no solo
   ingeniería.
2. **Sigmas de Monte Carlo**: evidencia de subestimación en los 3
   (T8 2.07x, feed 2.85x, pila con asimetría SAG1/SAG2 no capturada
   por un sigma compartido) — **no aplicar todavía**: primero resolver
   la deriva temporal, porque cualquier recalibración hecha sobre datos
   contaminados por ese problema repetiría el error ya visto con
   `DRAIN_PCT_H` (mejora en calibración, sin mejora real fuera de
   muestra).

### 3.4 Qué calibrar
- `ONE_BALL_CAPACITY_FACTOR` — sigue sin fuente, ruta concreta ya
  identificada (adaptar `calibrar_bola_delta_tph.py`), no ejecutada.
- Sigmas de Monte Carlo — **después** de resolver la deriva temporal
  (ver 3.3.2).
- `VENTANA_FACTOR_ESTADO`, pesos de `optimizer_v5.py` — sin evidencia
  nueva generada hoy, siguen en la lista de auditoría previa.

---

## 4. Riesgos

| Riesgo | Impacto | Mitigación propuesta |
|---|---|---|
| **La deriva temporal se repite o empeora** en datos futuros sin causa identificada | Alto — cualquier recalibración basada en datos hasta hoy podría no generalizar a julio en adelante | Priorizar la investigación de causa raíz (sección 5) antes de cualquier ajuste de parámetros |
| Recalibrar sigmas de MC sobre datos con deriva no resuelta | Medio — repetiría el patrón ya visto con `DRAIN_PCT_H` (mejora aparente, sin mejora real) | No recalibrar hasta resolver 1. |
| Gap de overflow en `recommend_action` sin corregir | Medio — un escenario real de SAG apagado + pila llena no generaría alerta escalada | Decisión de producto pendiente, mitigación parcial ya existe (nota informativa en el mensaje) |
| Ningún hallazgo de hoy fue validado con el Jefe de Sala/Metalurgista | Alto para cualquier decisión de producto (2 pendientes: overflow, valor final de tolerancia RESTRICTED) | Agendar sesión de revisión de estos 5 reportes antes de la siguiente iteración de código |
| El resto del programa de 37 secciones no se ejecutó (efectos mixtos, supervivencia, GAM, motor causal DAG, sistemas de recomendación causales) | Bajo-medio — son extensiones, no bloqueantes del P0 actual | Quedan documentadas como próximos pasos, no como brechas ocultas |

---

## 5. Próximo paso de mayor ROI (una sola acción) — ACTUALIZADO (3ra vez, final)

**Ejecutado y resuelto en gran parte** (sección 0): la reconstrucción
completa + re-ejecución de regresión y `p_safe` muestra que el sensor
roto explica prácticamente toda la mala calibración de `p_safe`
(Brier 0.62→0.004) y una parte sustancial pero no total del error de
fidelidad de pila (MAE hold-out 36.63→17.8pp, sigue sobre tolerancia).
La acción de mayor ROI ahora es:

1. **Obtener la serie real corregida de `correa_315` desde
   Instrumentación** (no la reconstrucción estadística de hoy, que
   tiene R²=0.127 y alta incertidumbre) — es el único paso que puede
   cerrar el residuo de fidelidad que queda (8.46-17.8pp según el
   modelo, vs. tolerancia 5pp).
2. **Investigar el residuo restante** con los candidatos del PAM
   Mantto ya identificados (retorqueo trunnion + crash stop SAG1
   16-23 abril, estandarización de placas en alimentadores 518/522
   mayo) — no descartados, podrían explicar parte de lo que la
   reconstrucción de `cv315` no cierra.
3. **`p_safe` puede tratarse como sustancialmente resuelto** para
   efectos prácticos inmediatos (Brier casi perfecto en hold-out
   corregido) — no bloquea decisiones operacionales del Jefe de Sala
   mientras se resuelve el punto 1.

**Aún no recalibrar sigmas de Monte Carlo ni ningún parámetro físico de
producción con datos de este período** hasta tener la serie real de
Instrumentación (punto 1) — la reconstrucción de hoy es diagnóstica,
no apta para calibración de producción.

---

## 6. Estado de las 37 secciones del prompt original

**Ejecutadas hoy (4 bloques):** fidelidad física/regresión (secc. 6-9),
motor de recomendaciones (secc. 24-30, parcial), calibración de Monte
Carlo (secc. 18-19).

**No ejecutadas — quedan como backlog explícito, no como omisión
oculta:** modelos de efectos mixtos (secc. 9), regresión logística/
Poisson/supervivencia (secc. 10-12), series de tiempo dinámicas
(secc. 13), modelos no lineales/SHAP (secc. 14), modelos bayesianos
jerárquicos (secc. 15), diseño factorial completo de escenarios
(secc. 20-23), sensibilidad global Sobol/Morris (secc. 23), modelo
estadístico/causal de recomendación (secc. 27-28), comparación
multicriterio formal de simuladores (secc. 31).
