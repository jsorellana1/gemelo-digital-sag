# Validación de modelos de regresión — error de pila final

Fecha: 2026-07-15. Continuación de
`04_Reports/Technical/20260715_Diagnostico_Fidelidad_Historica.md` y
`Analisis_Estadistico_Simulador.md`. Ejecuta las secciones 5 (hipótesis)
y 8 (regresión multivariada) del programa de validación estadística
sobre el target correcto: `pila_error_pp` (bias con signo del evento).
Reproducible vía `02_Analytics/Scripts/statistical_validation/
regression_pila_error.py` (`event_variable_table.csv` como entrada).
No se modificó código de producción.

## Hipótesis (sección 5 del prompt)

**H0 (física general):** el modelo agregado actual (representado aquí
por el cruce de breakpoints de `_pile_feedback_factor`, la única causa
ya confirmada) explica suficientemente el error de pila.

**H1:** existen variables adicionales (nivel inicial, duración,
alimentación, hora, régimen, activo) que mejoran significativamente la
fidelidad.

**Resultado: H0 rechazada, H1 soportada — con matices importantes que
se detallan abajo** (mejora fuerte en calibración, mucho más débil en
hold-out real).

## 1. Modelo pooled (todos los regímenes con dummy, excluye `overflow`)

`overflow` se excluyó del modelo pooled: sus 3 variables de cruce de
breakpoint tienen varianza cero (0/97 eventos cruzan, ya confirmado
como control positivo) — incluirlas produce un número de condición de
la matriz de diseño ~4×10¹⁹ (rank-deficiente), matemáticamente inválido
para interpretar coeficientes conjuntos.

| Modelo | R² | R² ajustado | AIC | MAE calibración (pp) | MAE hold-out (pp) |
|---|---:|---:|---:|---:|---:|
| Base (solo cruces de breakpoint) | 0.234 | 0.233 | 14382.8 | 9.79 | 11.73 |
| Multivariado (+ candidatas) | **0.591** | 0.589 | 13272.0 | **7.02** | **10.23** |

**Likelihood-ratio test** (modelo multivariado vs. base, 9 grados de
libertad de diferencia): estadístico=1128.75, **p=2.9×10⁻²³⁷** — mejora
estadísticamente inequívoca en calibración.

**Pero la brecha calibración→hold-out no se cierra con las variables
nuevas**: el modelo multivariado reduce el MAE de hold-out de 11.73pp a
solo 10.23pp (13% de mejora), muy por debajo de la reducción en
calibración (9.79→7.02pp, 28% de mejora). **Esto es el hallazgo más
importante de esta pasada**: las variables nuevas explican varianza
real dentro de la muestra de calibración, pero gran parte del error en
datos genuinamente fuera de muestra sigue sin explicarse por ninguna de
las variables evaluadas aquí — consistente con la hipótesis, ya
planteada en el diagnóstico previo, de que hay un cambio de régimen o
mecanismo no capturado entre el período de calibración y el de
hold-out (`> 2026-04-30`), no solo variables faltantes de nivel medio.

### Multicolinealidad (VIF)

| Variable | VIF |
|---|---:|
| `cruza_25pct` | 5.29 |
| `cruza_crit5pct` | 4.11 |
| `cruza_35pct` | 2.94 |
| `pila_ini_pct` | 1.88 |
| `feed_restriction_pct` | 1.52 |
| `rate_gap_tph` | 1.45 |
| `C(regimen)[mantenimiento]` | 1.40 |
| `C(regimen)[inventario_critico]` | 1.35 |
| `C(asset)[SAG2]` | 1.30 |
| `duracion_evento_h` | 1.05 |
| `hora_dia` | 1.02 |

VIF moderado-alto en los 3 indicadores de cruce (esperado — son
ordinalmente anidados por construcción: cruzar el umbral más profundo
implica haber cruzado los más superficiales). Ningún VIF supera el
umbral de preocupación severa (~10) — los coeficientes individuales
siguen siendo interpretables, pero se leen mejor como una curva
dosis-respuesta conjunta que como 3 efectos independientes.

### Coeficientes (calibración, con corrección Benjamini-Hochberg, α=0.05)

| Variable | Coef (pp) | IC95 | p (BH) | Significativo |
|---|---:|---|---:|:---:|
| `cruza_35pct` | −12.66 | [−14.23, −11.10] | <0.0001 | ✅ |
| `cruza_25pct` | −4.88 | [−7.19, −2.57] | <0.0001 | ✅ |
| `cruza_crit5pct` | −6.47 | [−8.66, −4.28] | <0.0001 | ✅ |
| `pila_ini_pct` | −0.41 | [−0.44, −0.38] | <0.0001 | ✅ |
| `duracion_evento_h` | +0.035 | [0.019, 0.051] | <0.0001 | ✅ |
| `rate_gap_tph` | +0.0073 | [0.0063, 0.0082] | <0.0001 | ✅ |
| `C(asset)[SAG2]` | −2.04 | [−3.07, −1.02] | 0.0001 | ✅ |
| `C(regimen)[mantenimiento]` | +7.17 | [5.49, 8.85] | <0.0001 | ✅ |
| `C(regimen)[inventario_critico]` | +0.72 | [−0.98, 2.43] | 0.406 | ❌ |
| `C(regimen)[t8_corta]` | −2.48 | [−5.48, 0.52] | 0.140 | ❌ |
| `feed_restriction_pct` | −0.015 | [−0.035, 0.006] | 0.188 | ❌ |
| `hora_dia` | −0.039 | [−0.107, 0.029] | 0.284 | ❌ |

**Lectura por variable:**

- **`pila_ini_pct` (confirmada, efecto grande):** cada punto porcentual
  adicional de pila inicial se asocia a −0.41pp de bias — pilas que
  parten más llenas tienden a terminar con más subestimación del
  motor. Es la variable candidata nueva con mayor tamaño de efecto.
- **`rate_gap_tph` y `duracion_evento_h` (confirmadas, efecto pequeño
  pero real):** ambas empujan el bias hacia valores menos negativos
  (más gap de rate o más duración → menos subestimación), efecto
  estadísticamente claro pero operacionalmente modesto en magnitud
  comparado con `pila_ini_pct` o los cruces de breakpoint.
- **`asset=SAG2` (confirmada):** SAG2 tiene 2.04pp más de bias negativo
  que SAG1 controlando por lo demás — consistente y cuantifica
  formalmente la heterogeneidad SAG1/SAG2 ya detectada cualitativamente
  en `mantenimiento` (+8.30pp vs. −10.50pp) en el diagnóstico previo.
- **`regimen=mantenimiento` (confirmada):** una vez controlado por
  cruce de breakpoints, pila inicial, asset, etc., `mantenimiento`
  tiene un offset positivo de +7.17pp respecto del régimen de
  referencia (`alimentacion_restringida`) — coherente con su bias
  agregado casi nulo ya reportado (cancela con el resto de efectos).
- **`regimen=t8_corta` e `inventario_critico` (H0 NO rechazada):**
  tras controlar por las demás variables, ya **no hay evidencia de que
  estos regímenes tengan una causa distintiva propia** más allá de lo
  que explican `pila_ini_pct`, los cruces de breakpoint y las demás
  covariables. Esto es relevante: el MAE crudo más alto de `t8_corta`
  (18.88pp) no requiere una explicación específica de "por qué T8 es
  distinto" — es consistente con que sus eventos simplemente tienden a
  partir con pila más baja / cruzar más breakpoints, no con un
  mecanismo exclusivo de la ventana T8.
- **`feed_restriction_pct` y `hora_dia` (H0 no rechazada):** sin
  evidencia de efecto tras corrección por múltiples comparaciones. No
  hay señal de que la hora del día del evento influya en el error —
  descarta una hipótesis plausible (turnos/operación nocturna vs.
  diurna) sin necesidad de la variable `turno` que se decidió no
  fabricar.

## 2. Modelos por régimen (candidatas, sin `C(regimen)`; con `C(asset)` solo si el régimen tiene ambos activos)

| Régimen | N calib | N hold-out | R² | R² adj | MAE calib (pp) | MAE hold-out (pp) |
|---|---:|---:|---:|---:|---:|---:|
| `t8_corta` | 44 | 19 | **0.869** | 0.844 | 3.79 | **11.63** |
| `alimentacion_restringida` | 1.365 | 112 | 0.665 | 0.662 | 5.59 | **5.76** |
| `inventario_critico` | 186 | 35 | 0.632 | 0.613 | 8.16 | 12.52 |
| `mantenimiento` | 202 | 37 | 0.452 | 0.426 | 10.46 | 17.62 |
| `overflow`* | 97 | 0 | 0.364 | 0.329 | 2.85 | N/A |

*`overflow`: mismo problema de rank-deficiencia que en el modelo pooled
(3 columnas de cruce con varianza cero) — el R²/MAE reportado usa
efectivamente solo las 5 variables restantes (statsmodels resuelve vía
pseudo-inversa sin error, pero el resultado no debe leerse como
validación de las variables de cruce para este régimen). Sin eventos en
hold-out (todo el régimen detectado cae antes de `2026-04-30`) — no hay
forma de validar generalización para `overflow` con el corte actual.

**Hallazgo más importante de esta tabla — dos patrones opuestos de
generalización:**

1. **`alimentacion_restringida` generaliza bien**: MAE calibración
   5.59pp ≈ MAE hold-out 5.76pp (diferencia de 0.17pp). Con N=1.477
   eventos, el modelo multivariado deja el error casi dentro de la
   tolerancia de 5pp de forma genuinamente fuera de muestra — el
   régimen de mayor volumen de datos es también el que mejor valida.
2. **`t8_corta` generaliza muy mal**: R²=0.869 en calibración (el
   modelo explica el 87% de la varianza del error dentro de muestra)
   pero el MAE se **triplica** en hold-out (3.79pp → 11.63pp). Esto
   reproduce y refina el hallazgo ya reportado con `DRAIN_PCT_H` y
   `_pile_feedback_factor` (MAE univariado hold-out 36.63pp): incluso
   controlando simultáneamente por todas las variables candidatas de
   esta pasada, `t8_corta` tiene algo estructuralmente distinto entre
   calibración y hold-out que ninguna variable medida aquí captura. No
   se identifica la causa en esta pasada — queda como el hallazgo
   negativo más relevante para la siguiente iteración (candidatos a
   investigar: cambio de régimen operacional real después de
   `2026-04-30`, tamaño de muestra insuficiente en hold-out para T8
   corta de N=19, o una variable omitida correlacionada con el tiempo).
3. `inventario_critico` y `mantenimiento` quedan en un punto intermedio
   (la brecha calibración/hold-out crece pero no se triplica).

## 3. Conclusión de esta pasada

- **H1 confirmada de forma agregada** (ΔR²=0.357, p≈0): las variables
  candidatas nuevas sí mejoran la fidelidad explicada, especialmente
  `pila_ini_pct`, `asset` y el régimen `mantenimiento`.
- **Pero la mejora no es uniforme ni resuelve el P0**: en el régimen de
  mayor volumen (`alimentacion_restringida`) el modelo multivariado
  prácticamente cierra la brecha calibración/hold-out; en `t8_corta`
  (el régimen con el MAE crudo más alto reportado) la brecha se
  mantiene casi intacta — el problema de `t8_corta` no es
  "variables faltantes de nivel medio", es más profundo.
- **`hora_dia` y `feed_restriction_pct` no muestran efecto** tras
  corrección por múltiples comparaciones — H0 no rechazada para
  ambas, no se fuerza una narrativa positiva donde no la hay.
- **No se ha resuelto el P0** (`04_Reports/Technical/
  20260715_Roadmap_Cierre_Simulador_Operacional.md`, sección 10): el
  hallazgo de `t8_corta` refuerza que la investigación debe seguir
  ahí, no en las 4 variables descartadas o parcialmente confirmadas
  aquí.

## 4. Investigación inmediata — por qué `t8_corta` no generaliza (misma fecha, continuación)

Se comparó la distribución de covariables entre calibración y hold-out
de `t8_corta` para descartar la hipótesis más simple ("el hold-out
tiene eventos más severos en las variables ya medidas").

| Variable | Calibración (N=44) | Hold-out (N=19) |
|---|---:|---:|
| `pila_ini_pct` (media) | 45.44 | 49.42 |
| `rate_gap_tph` (media) | 1080.56 | 544.75 |
| `feed_restriction_pct` (media) | 26.83 | 17.36 |
| `duracion_evento_h` (media) | 3.45 | 3.37 |
| `cruza_35pct` (% eventos) | 54.5% | **100.0%** |

**Hallazgo contraintuitivo**: el hold-out **no** tiene eventos con pila
inicial más baja ni con mayor restricción de alimentación — al
contrario, `rate_gap_tph` y `feed_restriction_pct` son *menores* en
promedio (menos restrictivos) que en calibración. Aun así, **100% de
los 19 eventos de hold-out cruzan el breakpoint del 35%** (vs. 54.5%
en calibración), y los errores son grandes y consistentemente negativos
(rango −19.9pp a −65.0pp, incluyendo un evento que partió con
`pila_ini_pct=94.4%` y terminó con error de −65.0pp). Esto **descarta**
que el modelo multivariado esté fallando por no controlar
suficientemente por nivel/restricción — controla por esas variables y
aun así no cierra la brecha.

**El corrimiento es sistémico, no exclusivo de `t8_corta`**: el mismo
patrón de "más cruces de breakpoint en hold-out" aparece en
`alimentacion_restringida` (39.6% calibración → 58.9% hold-out), pero
mucho más leve — y ese régimen sí generaliza bien (sección 2). En
`t8_corta` el corrimiento es extremo (54.5%→100%) y el error no se
absorbe pese a que la regresión ya incluye `pila_ini_pct`/`rate_gap_tph`.

**Interpretación (sin sobreinterpretar):** hay evidencia de una deriva
temporal real entre el período de calibración (2026-01 a 2026-04-30) y
el hold-out (2026-05 a 2026-06-25) que afecta a todo el sistema, no
solo a `t8_corta` — pero `t8_corta` es desproporcionadamente sensible a
ella. **No se identifica la causa física en esta pasada** (no hay en
los datasets usados una señal de condición de equipos, cambios de
geometría de pila, o eventos de mantenimiento mayor que explique por
qué mayo-junio se comporta distinto a enero-abril). Se documenta como
hallazgo real, no como conclusión — investigar la causa raíz requiere
datos operacionales fuera del alcance de esta tabla (bitácora de
mantenciones mayores, cambios de calibración de instrumentos, o
confirmación con Jefe de Sala/Metalurgista de algún cambio operacional
conocido en ese período).

## Próximos pasos concretos (no ejecutados esta pasada)

1. ~~Investigar por qué `t8_corta` no generaliza~~ — **ejecutado en esta
   misma pasada (sección 4)**: descartada la hipótesis de covariables
   más severas en hold-out (de hecho son *menos* severas en promedio);
   confirmado un corrimiento sistémico hacia más cruces de breakpoint
   entre calibración y hold-out (presente también en `alimentacion_
   restringida`, mucho más leve). Causa física raíz **no identificada**
   — requiere datos operacionales (bitácora de mantenciones/cambios de
   calibración) fuera del alcance de esta tabla. Consultar con
   Jefe de Sala/Metalurgista si hubo algún cambio conocido entre
   2026-05 y 2026-06.
2. Repetir el modelo pooled con efectos mixtos (sección 9 del prompt,
   intercepto aleatorio por régimen/activo) en vez de dummies fijas —
   más apropiado dado el N heterogéneo entre regímenes (63 a 1.477).
3. Extender a `t8_larga` si se acumula N suficiente (hoy 8 eventos,
   bajo el mínimo de 20).
4. Modelo de error absoluto (no solo signado) para capturar mejor la
   cola pesada (P90) en vez de solo la media condicional (considerar
   regresión cuantílica).
