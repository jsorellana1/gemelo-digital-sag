# SAG2 - Capacidad Espacial Hold-out

Fecha: 2026-07-15

## Diagnostico

Se incorporo un candidato opcional para `SAG2` que ya no depende solo
de `n_canales_activos`, sino tambien de una capacidad espacial basada
en:

- `canal_min`
- `range_canales`

usando los niveles historicos reales por canal al inicio de cada evento.

Resultado:

```text
La capacidad espacial SI agrega señal para SAG2,
pero no de forma uniforme entre regimenes.
```

No es un candidato listo para produccion global, pero si valida que el
paso correcto ya no es seguir afinando la pura difusion lateral, sino
hacer la capacidad de `SAG2` sensible a la geometria.

## Evidencia

Script ejecutado:

- `05_Dashboard/engine/diagnostics/diagnose_sag2_spatial_capacity_holdout.py`

Artefacto:

- `04_Reports/Technical/20260715_sag2_spatial_capacity_holdout.csv`

Parametros del modelo espacial evaluado:

```text
factor =
clip(
  0.32183
  + 0.00918 * canal_min
  + 0.00517 * range_canales,
  0.35,
  1.00
)
```

Comparacion hold-out (`2026-05-01+`):

### t8_corta

- baseline agregado:
  - `MAE SAG1 = 36.63 pp`
  - `MAE SAG2 = 6.52 pp`
- Fase 1 multicelda:
  - `MAE SAG1 = 35.54 pp`
  - `MAE SAG2 = 6.52 pp`
- Fase 1 + capacidad espacial SAG2:
  - `MAE SAG1 = 35.54 pp`
  - `MAE SAG2 = 4.54 pp`

Lectura:

- mejora clara en `SAG2` (`-1.98 pp` vs baseline).

### inventario_critico

- baseline agregado:
  - `MAE SAG2 = 3.79 pp`
- Fase 1 multicelda:
  - `MAE SAG2 = 3.79 pp`
- Fase 1 + capacidad espacial SAG2:
  - `MAE SAG2 = 7.55 pp`

Lectura:

- degradacion fuerte (`+3.76 pp`).

### mantenimiento

- baseline agregado:
  - `MAE SAG2 = 7.16 pp`
- Fase 1 multicelda:
  - `MAE SAG2 = 6.87 pp`
- Fase 1 + capacidad espacial SAG2:
  - `MAE SAG2 = 6.40 pp`

Lectura:

- mejora moderada (`-0.76 pp` vs baseline).

### alimentacion_restringida

- baseline agregado:
  - `MAE SAG2 = 3.84 pp`
- Fase 1 multicelda:
  - `MAE SAG2 = 3.84 pp`
- Fase 1 + capacidad espacial SAG2:
  - `MAE SAG2 = 2.92 pp`

Lectura:

- mejora material (`-0.92 pp` vs baseline).

## Causa probable

La hipotesis confirmada es:

```text
la capacidad efectiva de SAG2 no depende solo del conteo de canales
activos; depende tambien de cuan "conectado" o "abierto" esta el
anillo de descarga.
```

Sin embargo, la misma parametrizacion no sirve para todos los regimenes:

- en `t8_corta` y `alimentacion_restringida`, la capacidad espacial
  ayuda;
- en `inventario_critico`, probablemente sobre-penaliza o penaliza con
  la forma equivocada.

Esto sugiere que `SAG2` necesita:

- o parametros por regimen;
- o un modelo jerarquico / partial pooling;
- o una variable espacial distinta para inventario critico.

## Accion

No activar esta capacidad espacial como default global.

Si continuaramos la calibracion, el candidato correcto seria:

```text
SAG2 spatial-cap por regimen
```

no un unico set global de coeficientes.

## Validacion

Cambios tecnicos dejados:

- inyeccion automatica de niveles historicos por canal al backtesting
  multicelda cuando no se entregan overrides manuales;
- capacidad espacial opcional para `SAG2` en
  `05_Dashboard/engine/stockpile_multicell.py`;
- propagacion completa a `simulate_scenario`, `simulate_ode` y router.

Pruebas ejecutadas:

- `pytest 05_Dashboard/tests/test_backtesting_multicell.py -q`
- `pytest 05_Dashboard/tests/test_stockpile_multicell.py -q`
- `pytest 05_Dashboard/tests/test_router_v2.py -q`

Todas pasaron.

## Riesgo

El principal riesgo ahora es usar una sola calibracion espacial de
`SAG2` para todos los regimenes.

La evidencia ya mostro que eso:

- mejora algunos casos;
- empeora otros;
- puede ocultar una estructura por regimen que hoy esta mezclada.

## Proximo paso

Unico paso recomendado de mayor ROI:

```text
calibrar la capacidad espacial de SAG2 por regimen
(al menos t8_corta / alimentacion_restringida / inventario_critico)
y validar cada variante en hold-out antes de cualquier activacion
productiva.
```
