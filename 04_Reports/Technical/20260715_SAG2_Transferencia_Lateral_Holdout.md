# SAG2 - Transferencia Lateral Hold-out

Fecha: 2026-07-15

## Diagnostico

Se implemento una segunda generacion **opcional** del multicelda con
transferencia lateral/radial entre celdas vecinas para `SAG2`.

Resultado:

```text
No hubo mejora medible en hold-out.
```

El coeficiente de transferencia lateral barrido entre `0.00` y `0.80`
`1/h` produjo exactamente las mismas metricas de backtesting hold-out.

## Evidencia

Script ejecutado:

- `05_Dashboard/engine/diagnostics/diagnose_sag2_lateral_transfer_holdout.py`

Artefacto:

- `04_Reports/Technical/20260715_sag2_lateral_transfer_holdout.csv`

Grid evaluada:

- `0.00`
- `0.05`
- `0.10`
- `0.20`
- `0.40`
- `0.80`

Split temporal:

- hold-out desde `2026-05-01`

Metricas observadas para todos los coeficientes:

### t8_corta

- `N = 19`
- `MAE SAG1 = 34.41 pp`
- `MAE SAG2 = 6.52 pp`

### inventario_critico

- `N = 29`
- `MAE SAG1 = 22.86 pp`
- `MAE SAG2 = 3.79 pp`

### mantenimiento

- `N = 36`
- `MAE SAG1 = 18.50 pp`
- `MAE SAG2 = 7.16 pp`

### alimentacion_restringida

- `N = 109`
- `MAE SAG1 = 15.92 pp`
- `MAE SAG2 = 3.84 pp`

No hubo diferencia ni en `SAG1` ni en `SAG2`.

Evidencia estructural adicional sobre la serie espacial hold-out de
`SAG2`:

- `1 canal activo`: `0.73%`
- `2 canales activos`: `14.27%`
- `3 canales activos`: `59.83%`
- `4 canales activos`: `25.17%`

Es decir, aproximadamente `85%` del hold-out ya opera con `3-4`
canales activos.

## Causa probable

La transferencia lateral implementada **si cambia la forma espacial**
de la pila, pero casi no cambia la metrica que hoy gobierna la
capacidad:

```text
n_canales_activos -> rate_cap
```

Como la tabla actual de `SAG2` satura en:

- `3 activos -> 2516 TPH`
- `4 activos -> 2516 TPH`
- `5 activos -> 2516 TPH`

la difusion radial no altera la capacidad efectiva mientras el sistema
permanezca en `>= 3` canales activos, que es justo lo dominante en
hold-out.

En otras palabras:

```text
la nueva fisica si existe
pero la funcion de salida actual no es sensible a esa fisica
en la mayor parte del hold-out.
```

## Accion

No seguir calibrando el coeficiente lateral aisladamente bajo la tabla
actual.

Antes de eso, hace falta cambiar la representacion de capacidad desde:

```text
solo n_canales_activos
```

hacia algo sensible a geometria, por ejemplo:

- `canal_min`
- `range_canales`
- `asimetria_radial`
- `masa_vecina_disponible`
- `desbalance angular`

## Validacion

Cambios implementados:

- transferencia lateral opcional en `05_Dashboard/engine/stockpile_multicell.py`
- propagacion al motor y router
- backtesting proxy ahora reporta tambien `pila_mae_sag2_pp` cuando hay
  observacion

Pruebas ejecutadas:

- `pytest 05_Dashboard/tests/test_stockpile_multicell.py -q`
- `pytest 05_Dashboard/tests/test_router_v2.py -q`
- `pytest 05_Dashboard/tests/test_backtesting_overflow.py -q`

Todas pasaron.

## Riesgo

El principal riesgo ahora no es la transferencia lateral en si, sino
seguir optimizando un parametro que la funcion de capacidad no
“escucha”.

Eso llevaria a:

- tiempo de calibracion perdido;
- falsa conclusion de que la geometria radial “no importa”;
- subestimar un mecanismo real por una capa de salida demasiado gruesa.

## Proximo paso

Unico paso recomendado de mayor ROI:

```text
recalibrar SAG2 con una funcion de capacidad espacialmente sensible
(no solo por conteo de canales activos) y recien despues volver a
evaluar la transferencia lateral en hold-out.
```
