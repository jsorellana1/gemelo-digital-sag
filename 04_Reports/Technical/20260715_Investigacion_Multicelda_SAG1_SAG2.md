# Investigacion Multicelda SAG1/SAG2

Fecha: 2026-07-15

## Diagnostico

La evidencia disponible **no es suficiente** para reemplazar hoy el
modelo agregado por un modelo multicelda en ambos activos.

El caso no es simetrico:

- `SAG1`: la evidencia fisica existe, pero la evidencia estadistica
  hold-out es debil o negativa.
- `SAG2`: existe evidencia fisica clara y evidencia estadistica parcial
  a favor del componente espacial, pero todavia no alcanza para una
  migracion productiva completa.

La decision recomendada hoy es:

```text
No reemplazar el modelo agregado actual como baseline productivo.
```

Si hubiera que priorizar un camino de migracion, la unica opcion con
soporte parcial es:

```text
Opcion E — migracion hibrida:
mantener baseline agregado en produccion
y continuar R&D multicelda focalizado en SAG2
y en regimenes t8_corta / inventario_critico.
```

## Evidencia

### 1. Evidencia fisica

Observacion de PI ProcessBook:

- `SAG1` muestra alimentacion lateral por `CV-315`, 4 canales en linea
  (`D-C-B-A`) y fuerte heterogeneidad local. Esto respalda la hipotesis
  de una pila **multicelda lineal**.
- `SAG2` muestra alimentacion por `CV-316`, 6 canales distribuidos en
  geometria radial y heterogeneidad sectorial marcada. Esto respalda la
  hipotesis de una pila **multicelda radial**.

Conclusion fisica:

- la hipotesis multicelda es **plausible** en ambos activos;
- `SAG2` tiene una firma geometrica mas claramente incompatible con una
  sola variable agregada;
- la evidencia visual por si sola **no** basta para migrar.

### 2. Evidencia estadistica sobre datos historicos espaciales

Fuente:

- `01_Data/Raw/Tonelajes_pila/pilas_rendimientos.xlsx`
- periodo: `2025-08-01` a `2026-06-30`
- split temporal real:
  - calibration: hasta `2026-04-30`
  - hold-out: desde `2026-05-01`

Variables espaciales evaluadas:

- `std_canales`
- `range_canales`
- `canal_min`
- `canal_max`
- `cv_canales`
- `gini_canales`
- `entropy_canales`
- `active_channels`
- `asym_longitudinal` / `asym_radial`

Resultados lineales hold-out (`TPH ~ pile_avg` vs `TPH ~ pile_avg + espaciales`):

#### SAG1

- Base:
  - `R2_hold = -0.987`
  - `MAE_hold = 442.6`
- Espacial:
  - `R2_hold = -1.841`
  - `MAE_hold = 513.8`
- Delta espacial vs base:
  - empeora `+71.2 TPH`

#### SAG2

- Base:
  - `R2_hold = -0.039`
  - `MAE_hold = 615.4`
- Espacial:
  - `R2_hold = 0.069`
  - `MAE_hold = 592.0`
- Delta espacial vs base:
  - mejora `-23.4 TPH`

Intervalo bootstrap por bloques diarios para `MAE_spatial - MAE_base`:

- `SAG1`: positivo, consistente con deterioro
- `SAG2`: negativo, consistente con mejora modesta

Resultados con controles operacionales:

#### SAG1

- `control_only`: `MAE_hold = 338.0`
- `control_plus_pile`: `339.2`
- `control_plus_spatial`: `369.5`

Interpretacion:

- una vez controlado por consigna operativa, la espacialidad no ayuda;
- incluso empeora hold-out.

#### SAG2

- `control_only`: `MAE_hold = 316.2`
- `control_plus_pile`: `306.1`
- `control_plus_spatial`: `307.0`

Interpretacion:

- `pile_avg` agrega algo por sobre la consigna;
- las variables espaciales agregan muy poco adicionalmente.

### 3. Evidencia logistica sobre proxy de capacidad degradada

Se evaluo un proxy de `low_capacity` basado en `TPH real / target`.

Resultados hold-out:

#### SAG1

- Base:
  - `AUC = 0.584`
  - `F1 = 0.253`
- Espacial:
  - `AUC = 0.581`
  - `F1 = 0.250`

#### SAG2

- Base:
  - `AUC = 0.800`
  - `F1 = 0.379`
- Espacial:
  - `AUC = 0.788`
  - `F1 = 0.357`

Interpretacion:

- bajo este proxy, las variables espaciales no mejoran la clasificacion;
- por tanto, la evidencia para STARVED/RESTRICTED sigue siendo
  insuficiente con los datos hoy integrados.

### 4. Evidencia operacional sobre el gemelo digital

Backtesting hold-out real del candidato multicelda Fase 1 contra el
baseline agregado:

#### t8_corta

- `N = 19`
- baseline: `36.63 pp`
- multicelda: `34.41 pp`
- delta medio: `-2.22 pp`
- IC95% bootstrap: `[-3.16, -1.29]`
- share de eventos que mejora: `89.5%`

#### inventario_critico

- `N = 29`
- baseline: `24.62 pp`
- multicelda: `22.86 pp`
- delta medio: `-1.77 pp`
- IC95% bootstrap: `[-2.58, -1.02]`
- share que mejora: `41.4%`

#### mantenimiento

- `N = 36`
- baseline: `19.18 pp`
- multicelda: `18.50 pp`
- delta medio: `-0.68 pp`
- IC95% bootstrap: `[-1.23, -0.14]`
- share que mejora: `16.7%`

#### alimentacion_restringida

- `N = 109`
- baseline: `16.02 pp`
- multicelda: `15.92 pp`
- delta medio: `-0.10 pp`
- IC95% bootstrap: `[-0.21, -0.02]`
- share que mejora: `6.4%`

Lectura operacional:

- el candidato multicelda **si mejora** hold-out en los regimenes mas
  sensibles;
- la mejora mas robusta esta en `t8_corta`;
- pero los MAE siguen muy por encima de la tolerancia de `5 pp`;
- `overflow` no tuvo evidencia hold-out despues del corte temporal.

## Causa probable

### SAG1

La geometria lineal existe, pero la formulacion Fase 1 actual parece
demasiado simple para capturar el mecanismo real:

- falta transferencia lateral;
- el canal `C` esta degradado y reduce observabilidad;
- la consigna operativa explica mas que la heterogeneidad espacial
  contemporanea;
- la espacialidad medida no generaliza bien out-of-sample.

### SAG2

La espacialidad radial parece real y parcialmente util, pero todavia no
explica suficiente varianza adicional una vez incorporadas las
consignas:

- la radialidad agrega algo sobre `pile_avg`;
- ese extra estadistico es moderado;
- la mejora operacional del gemelo existe pero no cierra la tolerancia.

## Accion

No migrar aun el modelo productivo.

Accion recomendada:

1. Mantener el modelo agregado como baseline activo.
2. Tratar el multicelda como candidato experimental.
3. Focalizar la siguiente calibracion en:
   - `SAG2`
   - `t8_corta`
   - `inventario_critico`
4. No avanzar a multicelda productivo en `SAG1` hasta demostrar mejora
   hold-out reproducible.

## Validacion

Reproducibilidad dejada en:

- `05_Dashboard/engine/diagnostics/investigate_multicell_evidence.py`
- `04_Reports/Technical/20260715_multicell_linear_models.csv`
- `04_Reports/Technical/20260715_multicell_logistic_models.csv`
- `04_Reports/Technical/20260715_multicell_holdout_deltas.csv`
- `04_Reports/Technical/20260715_multicell_backtest_summary.csv`
- `04_Reports/Technical/20260715_multicell_backtest_delta_vs_baseline.csv`

## Riesgo

Riesgos de migrar ahora:

- sobreajuste por geometria mal especificada;
- falsa sensacion de realismo por evidencia visual fuerte;
- degradacion en `SAG1`;
- complejidad extra sin cierre real de MAE;
- falta de evidencia fuerte para STARVED/RESTRICTED reales;
- `overflow` hold-out aun sin cobertura posterior al corte.

## Recomendacion final

Decision cuantitativa:

- `Opcion A - Mantener agregado`: recomendable hoy para produccion.
- `Opcion B - Migrar solo SAG1`: no recomendable.
- `Opcion C - Migrar solo SAG2`: todavia prematuro, aunque es el mejor
  candidato.
- `Opcion D - Migrar ambos`: no recomendable.
- `Opcion E - Migracion hibrida`: **recomendada** como estrategia de
  I+D, no como reemplazo productivo inmediato.

ROI tecnico estimado:

- `SAG1`: bajo por ahora.
- `SAG2`: medio como linea de investigacion.
- `Ambos`: bajo si se intenta reemplazo completo hoy.

## Proximo paso

Unico paso recomendado de mayor ROI:

```text
calibrar y validar un multicelda de segunda generacion SOLO para SAG2,
con transferencia radial/lateral explicita y evaluacion hold-out en
t8_corta + inventario_critico antes de considerar cualquier migracion
productiva.
```
