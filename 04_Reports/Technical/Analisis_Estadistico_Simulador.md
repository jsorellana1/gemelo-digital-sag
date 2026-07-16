# Análisis estadístico del simulador — EDA de errores de pila por evento

Fecha: 2026-07-15. Primer entregable del programa de validación
estadística pedido (secciones 6-8), continuación directa de
`04_Reports/Technical/20260715_Diagnostico_Fidelidad_Historica.md`. No
modifica código de producción — solo análisis.

**Fuente de datos:** `event_variable_table.csv` (generado por
`02_Analytics/Scripts/statistical_validation/build_event_variable_table.py`,
que reusa exactamente `historical_backtesting.py`/`regime_event_detector.py`
sin reimplementar la detección de eventos ni la llamada al motor —
ver ese script para el detalle de cada columna). Unidad de análisis:
**un registro por evento**, no por fila de 5 min (sección 2.4/10 del
prompt de validación — evita pseudo-replicación).

**Verificación de reproducción antes de confiar en el análisis:** los
conteos por régimen (t8_corta=63, alimentación_restringida=1.477,
inventario_crítico=221, mantenimiento=239, overflow=97) y el ratio de
error entre eventos que cruzan/no cruzan el breakpoint del 35% de
`_pile_feedback_factor` reproducen **exactamente** los números ya
publicados en el diagnóstico causal de esta misma fecha (ej. t8_corta:
4.00pp/25.80pp, N=20/43). Esto confirma que la tabla de eventos es
consistente con el trabajo previo antes de construir cualquier modelo
nuevo sobre ella.

## 1. Distribución de `pila_error_pp` por régimen (N=2.097 eventos)

| Régimen | N | Media (bias) | Std | Mín | Máx |
|---|---:|---:|---:|---:|---:|
| `alimentacion_restringida` | 1.477 | −11.82 | 12.82 | −62.66 | 30.34 |
| `inventario_critico` | 221 | −11.02 | 18.77 | −98.22 | 84.32 |
| `mantenimiento` | 239 | +0.27 | 20.81 | −79.74 | 74.43 |
| `overflow` | 97 | +3.47 | 4.65 | −6.91 | 14.65 |
| `t8_corta` | 63 | −16.91 | 20.08 | −65.01 | 13.46 |

**Lectura:** `overflow` es el único régimen con distribución de error
razonablemente concentrada (std=4.65). Los otros 4 tienen colas largas
(std 12.8-20.8, rangos que llegan a ±60-98pp) — el error no es un
sesgo constante, hay un subconjunto de eventos con error extremo que
arrastra la media, consistente con el hallazgo P90 ya reportado en el
diagnóstico causal (mediana ≪ media en varios regímenes).

## 2. Missingness

Cero valores faltantes en la tabla construida — se descartan eventos
sin `pila_ini`/`pila_fin` observados antes de calcular el error (mismo
criterio que `historical_backtesting.py`, no se imputa).

## 3. Variables candidatas evaluadas

Ver `build_event_variable_table.py` para la definición exacta de cada
una. Resumen:

| Variable | Definición | Nota |
|---|---|---|
| `cruza_35pct`/`cruza_25pct`/`cruza_crit5pct` | La trayectoria SIMULADA de `pile_sag1` cruza cada breakpoint de `_pile_feedback_factor` en algún instante del evento | Ya confirmadas como causales (diagnóstico previo) |
| `pila_ini_pct` | % de pila al inicio del evento | — |
| `duracion_evento_h` | Duración del evento (T8 real o ventana detectada) | — |
| `rate_gap_tph` | `P90["SAG1"] (1454) − TPH observado promedio del evento` | Mide cuánto el motor "debía" reducir vs. el objetivo nominal |
| `feed_restriction_pct` | `(CV315+CV316 observados) / (P90 SAG1+SAG2) × 100` | Proxy de restricción de alimentación normalizada por demanda total, no una capacidad de chancado dedicada (no existe esa constante en el motor) |
| `hora_dia` | Hora del día de inicio del evento | — |
| `regimen`, `asset` | Dummies categóricas | `asset` distingue SAG1/SAG2 dentro de `mantenimiento` (heterogeneidad ya confirmada) |

**Variable descartada explícitamente por falta de fuente:** `turno`
(C/A/B). No existe en el repo una función que mapee timestamp histórico
→ letra de turno con una fuente de rotación confiable — agregarla
habría significado fabricar una regla de turno sin evidencia
(sección 2.3 del prompt: "no usar modelos estadísticos para ocultar
errores físicos" / no fabricar). Queda como variable candidata futura
si se consigue el roster real de turnos.

## 4. Correlación / colinealidad esperada

`cruza_35pct` ⊇ `cruza_25pct` ⊇ `cruza_crit5pct` por construcción
(cruzar un umbral más profundo implica haber cruzado los más
superficiales) — colinealidad esperada y confirmada en el VIF del
modelo multivariado (`cruza_25pct` VIF=5.29, el resto <4.2). Ver
`Validacion_Modelos_Regresion.md` para el detalle completo y la lectura
correcta (los 3 coeficientes se interpretan mejor como una curva
dosis-respuesta conjunta, no aisladamente).

## 5. Próximo documento

Los resultados del modelo de regresión (hipótesis H0/H1, coeficientes,
hold-out) están en `Validacion_Modelos_Regresion.md`.
