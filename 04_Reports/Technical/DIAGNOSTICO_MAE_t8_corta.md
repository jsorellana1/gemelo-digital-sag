# Diagnóstico del MAE de t8_corta (TAREA 1 — obligatoria antes de cerrar otras brechas)

**Fecha:** 2026-07-07
**Script:** `05_Dashboard/engine/diagnostics/diagnose_t8_short_mae.py`
**N eventos:** 63 (de 64 detectados por Prerequisito 0 — 1 evento sin dato de pila final utilizable)

---

## 1. Error con signo, bias, std, MAE

### Método original (`historical_backtesting.py` v1 — con bug de ventana temporal)

```
n=63   bias=+24.97 pp   std=28.98 pp   MAE=30.10 pp
```

### Método corregido (usa el registro POST más cercano a `h_rel_fin=0`, no el último de la ventana POST)

```
n=63   bias=+26.99 pp   std=25.04 pp   MAE=27.81 pp
```

**Hallazgo secundario (bug real, ya corregido):** `historical_backtesting.run_backtest()` (v1)
tomaba `fin["pila_sag1"].iloc[-1]` — el **último** registro de la ventana
POST. La ventana POST se extiende hasta **48h después del fin del
evento** (`h_rel_fin` va de 0 a 48), no solo el instante inmediato. Esto
comparaba la predicción del modelo (a duración = fin del T8) contra el
estado de la pila **48h después**, un momento que ya no tiene relación
causal directa con el evento. Se corrigió para tomar el registro con
`h_rel_fin` más cercano a 0. **El impacto de este bug fue moderado**
(MAE 30.1 → 27.8 pp, ~7% de reducción) — no explica la mayor parte del
error.

### Clasificación (árbol de decisión del prompt)

```
|bias| = 27.0 pp > 15 pp  →  ERROR ESTRUCTURAL
```

El motor (o, más precisamente, los **inputs** con los que se invocó el
motor en el backtest) sobreestima sistemáticamente la pila final: el
modelo predice **más inventario remanente** del que realmente hubo.

---

## 2. Hipótesis de causa (investigada, no solo enunciada)

Se comparó el nivel de alimentación real (`correa_315`/`correa_316`,
disponibles en `advanced_t8_event_windows.parquet`) entre periodos:

| Periodo | CV315 medio (TPH) | CV316 medio (TPH) |
|---|---|---|
| PRE (antes del T8) | 168.2 | 1770.5 |
| **DURANTE (T8 activo)** | **56.9** (−66%) | **794.6** (−55%) |
| POST | 147.3 | 1849.1 |

**Confirmado:** durante una ventana T8 real, la alimentación (CV315/CV316)
se reduce drásticamente — es, por definición, lo que un T8 significa
operacionalmente. El backtest (`historical_backtesting.run_backtest()`)
**no pasaba este dato real al motor**: invocaba
`simulate_scenario_cached(...)` con los valores por defecto
(`cv_mode="auto"`, `correa315_estado="activa"`, `correa316_estado="activa"`),
es decir, el modelo asumía **alimentación normal/plena** durante todo el
evento, mientras la realidad tenía alimentación restringida al 34-45% de
lo normal. Esto explica por qué el modelo predice más pila remanente que
la real: el modelo "rellena" la pila a tasa normal mientras la realidad
la vació más rápido por la restricción de alimentación real.

### Verificación cuantitativa de la hipótesis

Se repitió el backtest pasando `cv_mode="manual"` con
`cv315_manual_tph`/`cv316_manual_tph` = promedio real observado durante
`DURANTE`:

```
n=63   bias=-16.91 pp   std=19.92 pp   MAE=18.88 pp
```

El MAE cae de 27.8 pp a **18.9 pp** (−32%) y el bias **cambia de signo**
(de +27 a −17) — confirma que la alimentación asumida por defecto era el
principal contribuyente al error, pero **no el único**: el signo negativo
residual (el modelo ahora predice *menos* pila que la real) indica un
segundo factor de menor magnitud, probablemente:

- El backtest alimenta el ODE con la **tasa SAG1/SAG2 promedio** de todo
  el evento (`SAG1_tph.mean()` en `DURANTE`), no con la serie real
  minuto-a-minuto — un evento con arranque gradual y tasa creciente
  produce un promedio distinto a la trayectoria real, y el ODE con tasa
  constante no puede reproducir exactamente una trayectoria de tasa
  variable.
- La configuración de bolas (`bolas_sag1`/`bolas_sag2`) se dejó en su
  valor por defecto (`"sin_bola"`) en vez de la configuración real activa
  durante el evento (no registrada en el dataset disponible).

---

## 3. ¿Es corregible con los datos actuales?

**Parcialmente, sí.** El dataset `advanced_t8_event_windows.parquet` YA
tiene `correa_315`/`correa_316` por evento a 5 min — permite alimentar el
motor con la restricción real de feed (reduce el MAE en un 32%, como se
demostró arriba). Esto se aplicó como corrección en
`historical_backtesting.py` (ver más abajo).

**No es corregible por completo** con la API actual del motor: `simulate_scenario_cached`
recibe un **rate escalar constante** por llamada, no una serie temporal.
Para eliminar el segundo factor (tasa variable dentro del evento) se
necesitaría una versión del simulador que acepte una trayectoria de tasa
minuto-a-minuto — **no existe hoy** y construirla está fuera del alcance
de este diagnóstico (es una limitación de arquitectura, no un ajuste de
tolerancia). Se documenta como trabajo futuro, no se fabrica una solución.

---

## 4. Acción aplicada

`historical_backtesting.py::run_backtest()` se corrigió para:
1. Usar el registro POST más cercano a `h_rel_fin=0` (no el último de la ventana de 48h).
2. Alimentar el motor con `cv_mode="manual"` usando el CV315/CV316 real observado durante el evento, en vez de dejar el modelo asumir alimentación plena por defecto.

Con ambas correcciones: **MAE=18.9 pp**. Se mantiene la tolerancia
original (`TOLERANCIAS_BACKTESTING["pila_mae_pct"]=5.0`) sin modificarla
— el resultado **sigue fuera de tolerancia** y así se reporta
honestamente (`dentro_tolerancia=False`). No se ajustó la tolerancia
para que el test pasara.

## 4.1 Seguimiento 2026-07-15 — el remanente se concentra cuando actúa `_pile_feedback_factor`

Se extendió el script `05_Dashboard/engine/diagnostics/diagnose_t8_short_mae.py`
para reproducir también la ruta actual del backtest corregido
(`cv_mode="manual"` con CV315/CV316 observados) **conservando la
trayectoria completa** de `pile_sag1`, no solo el estado final. Con eso
se puede marcar si la simulación cruza los breakpoints de
`_pile_feedback_factor` (35%, 25%, `CRITICAL_PCT+5%` = 20%) y comparar
el error final entre eventos que sí/no cruzan:

```text
Breakpoint cruzado en la   N (no/sí)    Error medio (pp)   Error mediana (pp)
simulación
< 35% (conservador)         20 / 43      4.00 / 25.80        2.87 / 27.39
< 25% (mínimo técnico)      29 / 34      3.81 / 31.73        1.73 / 31.45
< CRITICAL_PCT+5% (emerg.)  33 / 30      6.58 / 32.41        1.80 / 32.60
```

**Interpretación nueva y más fuerte**: la explicación de 2026-07-07
(feed real vs. feed asumido) sigue siendo válida para la primera gran
caída del MAE, pero **no explica por sí sola** el remanente de 18.9pp.
Ese error queda muy concentrado en los eventos donde el modelo activa su
feedback fijo por pila baja: **4.9-8.3x más error** cuando cruza los
breakpoints que cuando no. En `t8_corta`, de hecho, el subconjunto que
no cruza 35% queda prácticamente dentro de tolerancia (4.00pp), así que
`_pile_feedback_factor` pasa a ser la hipótesis principal para el error
residual de este régimen. La tasa variable dentro del evento y la
configuración real de bolas siguen siendo hipótesis secundarias
razonables, pero ya no son la explicación más fuerte disponible.

## 5. Conclusión

- Tipo de error: **estructural**, causado principalmente por un **gap de
  mapeo de inputs** en el backtest (alimentación asumida vs real), no por
  un defecto en el ODE validado.
- Corregible parcialmente con datos ya disponibles (aplicado).
- El remanente (~19pp MAE) queda hoy **fuertemente asociado al cruce de
  breakpoints de `_pile_feedback_factor`**; la necesidad de una
  simulación con tasa variable en el tiempo sigue vigente como hipótesis
  complementaria, pero dejó de ser la explicación principal más fuerte.
- **La "Validación histórica" de t8_corta se reporta como "fuera de
  tolerancia, causa diagnosticada" — nunca como "OK".**
