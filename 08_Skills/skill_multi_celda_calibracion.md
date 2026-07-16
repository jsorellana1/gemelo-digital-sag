---
name: multi-celda-calibracion
description: Audita, diagnostica, calibra y valida modelos multirrégimen o multicelda del Simulador Operacional SAG, priorizando fidelidad histórica, separación temporal train/validation/hold-out, conservación de masa, trazabilidad y uso eficiente de codebase-memory-mcp 0.9.0.
version: 1.0.0
project: Data_Science_JO
language: es
---

# Skill: Multi-celda / Calibración del Simulador Operacional SAG

## 1. Propósito

Esta skill guía el diagnóstico, calibración, comparación y validación de modelos del Simulador Operacional cuando existen:

- múltiples regímenes operacionales;
- múltiples circuitos o celdas de análisis;
- diferencias entre SAG1 y SAG2;
- ventanas T8 de distinta duración;
- alimentación restringida;
- inventario crítico;
- mantenimiento;
- overflow;
- estados de equipos diferentes;
- parámetros calibrados y supuestos coexistiendo;
- necesidad de separar calibración, validación y hold-out.

La skill debe producir mejoras físicamente interpretables, estadísticamente defendibles y reproducibles.

No debe utilizarse para realizar un refactor visual o arquitectónico amplio antes de resolver brechas P0 de fidelidad del modelo.

---

## 2. Cuándo activar esta skill

Usar esta skill cuando el usuario solicite cualquiera de las siguientes tareas:

- calibrar el simulador;
- recalibrar constantes o curvas;
- investigar MAE, RMSE o bias altos;
- comparar comportamiento por régimen;
- validar el modelo contra datos históricos;
- separar train, validation y hold-out;
- analizar diferencias entre SAG1 y SAG2;
- construir modelos por celda, régimen o circuito;
- evaluar factores de alimentación;
- ajustar `DRAIN_PCT_H`;
- ajustar `_pile_feedback_factor`;
- calibrar `ONE_BALL_CAPACITY_FACTOR`;
- calibrar incertidumbre Monte Carlo;
- analizar `historical_backtesting.py`;
- diagnosticar errores por ventana T8;
- comparar modelo global frente a modelos segmentados;
- crear una matriz multicelda de calibración;
- definir criterios de aceptación del gemelo digital.

No activar para:

- cambios exclusivamente UX/UI;
- redacción general;
- limpieza de archivos sin relación con calibración;
- refactor arquitectónico sin análisis de fidelidad;
- cambios de estilo o documentación sin evaluación del modelo.

---

## 3. Principios obligatorios

### 3.1 Fidelidad antes que arquitectura

Si el modelo falla su tolerancia histórica en uno o más regímenes relevantes:

```text
detener refactor amplio
→ diagnosticar error
→ recalibrar
→ validar hold-out
→ recién después refactorizar
```

### 3.2 No ajustar parámetros para ocultar errores

Toda modificación debe vincularse a una causa física, operacional o estadística identificada.

No utilizar machine learning residual para ocultar:

- alimentación mal modelada;
- desfases temporales;
- doble penalización;
- errores de unidades;
- mala conversión nivel–tonelaje;
- estados de equipos incorrectos;
- filtraciones entre calibración y validación.

### 3.3 Separación temporal real

Nunca usar split aleatorio por filas para eventos operacionales.

Separar por:

- fecha;
- evento;
- campaña operacional;
- bloque temporal.

Todos los registros de un mismo evento deben pertenecer al mismo conjunto.

### 3.4 Conservación de masa inmutable

Toda recalibración debe preservar:

```text
|mass_balance_error_sag1| < 1e-6 t
|mass_balance_error_sag2| < 1e-6 t
```

Preferentemente, el error debe mantenerse en el orden de `1e-10 t`.

### 3.5 Comparar contra baseline

Ningún modelo candidato reemplaza al actual sin una comparación explícita:

```text
baseline actual
vs
modelo candidato
vs
hold-out
```

---

## 4. Uso obligatorio de Codebase Memory MCP

Utilizar `codebase-memory-mcp 0.9.0` como herramienta primaria para ahorrar tokens y localizar impacto estructural.

### Orden recomendado

```text
search_graph
→ query_graph
→ trace_path
→ get_architecture
→ get_code_snippet
→ lectura puntual del working tree
```

### Consultas mínimas

Investigar callers, callees y consumidores de:

```text
historical_backtesting
simulate_scenario
simulate_scenario_cached
simulate_ode
compute_qin
effective_rate
compute_autonomia
calculate_stockpile_autonomy
_t8_factor_sag1
_t8_factor_sag2
_pile_feedback_factor
DRAIN_PCT_H
ONE_BALL_CAPACITY_FACTOR
BOLA_DELTA_TPH
adaptive_mc_eval
find_optimal_v3
find_optimal_v4
find_optimal_v5
```

### Limitación conocida

El MCP puede representar el commit `HEAD` y no todo el working tree no commiteado.

Por ello:

- usar MCP como mapa base;
- verificar cambios nuevos con `grep`, lectura puntual y ejecución real;
- documentar discrepancias;
- no declarar una función sin uso solo por `in_degree=0`;
- para closures Dash usar `query_graph` con `CALLS|USAGE`.

---

## 5. Estructura multicelda de análisis

La calibración debe organizarse mediante una matriz de celdas.

Cada celda corresponde a una combinación relevante de:

```text
activo
× régimen
× duración
× estado operacional
× período
```

### Dimensiones mínimas

#### Activo

```text
SAG1 / SAC1
SAG2 / SAC2
```

#### Régimen

```text
normal
t8_corta
t8_larga
inventario_critico
overflow
mantenimiento
alimentacion_restringida
sag_off
bola_off
recuperacion
```

#### Duración de ventana

```text
0 h
2 h
4 h
8 h
12 h
```

#### Estado de bolas

```text
2 bolas
1 bola
0 bolas
```

#### Nivel inicial

```text
bajo
medio
alto
```

Los cortes deben derivarse de datos o umbrales operacionales documentados.

---

## 6. Tabla maestra multicelda

Construir una tabla con, al menos:

| Celda | Activo | Régimen | N eventos | Período | MAE pp | RMSE pp | Bias pp | P90 AE | Error mínimo | Error tiempo mínimo | Estado |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|

Estados permitidos:

```text
SIN DATOS
INSUFICIENTE
NO CALIBRADA
CALIBRADA
VALIDADA
FALLA TOLERANCIA
DRIFT
```

No combinar celdas heterogéneas únicamente para aumentar `N`.

---

## 7. Línea base obligatoria

Antes de modificar el modelo:

1. registrar branch y commit;
2. registrar working tree;
3. versionar datasets;
4. calcular hashes;
5. guardar parámetros activos;
6. ejecutar backtesting completo;
7. guardar resultados por evento y régimen.

Crear:

```text
04_Reports/Technical/backtesting_baseline_manifest.json
04_Reports/Technical/backtesting_summary_by_regime.csv
04_Reports/Technical/backtesting_results_by_event.csv
```

El manifiesto debe incluir:

```json
{
  "branch": "",
  "head_commit": "",
  "working_tree_dirty": true,
  "audit_date": "",
  "dataset_hashes": {},
  "parameter_version": "",
  "model_version": "",
  "regimes": {}
}
```

---

## 8. Validación de la métrica

Antes de recalibrar, comprobar:

- signo del error;
- unidad;
- timestamp;
- timezone;
- interpolación;
- resolución;
- suavizado;
- datos faltantes;
- longitud del horizonte;
- punto inicial;
- punto final;
- criterio de inclusión;
- criterio de exclusión;
- agrupación por evento.

Definir:

\[
e_t = M^{predicho}_t - M^{real}_t
\]

Calcular:

```text
MAE
RMSE
bias
mediana del error absoluto
P90 del error absoluto
desviación estándar
error en nivel mínimo
error en hora del mínimo
error final
error de recuperación
```

No cambiar parámetros hasta confirmar que el backtesting mide lo esperado.

---

## 9. Descomposición causal del error

Utilizar:

\[
M^{pred}_T-M^{real}_T =
(M^{pred}_0-M^{real}_0)
+
\int_0^T
\left[
(F^{pred}_{in}-F^{real}_{in})
-
(F^{pred}_{out}-F^{real}_{out})
\right]dt
\]

Descomponer por evento:

| Evento | Error inicial | Error alimentación | Error consumo | Error capacidad | Error temporal | Residual |
|---|---:|---:|---:|---:|---:|---:|

Determinar si la causa dominante corresponde a:

```text
M0
F_in
F_out
CAP_TON
nivel→masa
desfase
clasificación de régimen
ruido de sensor
```

---

## 10. Diagnóstico por régimen

### 10.1 Alimentación restringida

Investigar:

- factor fijo `0.4`;
- severidad real de reducción;
- diferencias CV315/CV316;
- cambios intraventana;
- T1/T3;
- split 29/71;
- doble reducción;
- recuperación;
- desfases.

Estimar:

\[
f^{real}_{feed} =
\frac{F^{observado}_{in}}{F^{baseline}_{in}}
\]

Comparar la distribución real con el factor del código.

### 10.2 Inventario crítico

Investigar:

- `_pile_feedback_factor`;
- doble penalización;
- `STARVED`;
- clipping;
- capacidad;
- geometría de pila;
- relación nivel–tonelaje;
- retraso PI;
- recuperación.

### 10.3 T8 corta y larga

Separar:

- error de alimentación;
- error de consumo;
- dose-response;
- tiempo de inicio;
- duración efectiva;
- recuperación;
- ventanas superpuestas.

No recalibrar `_t8_factor_sag1/2` antes de separar estos componentes.

### 10.4 Mantenimiento

No tratar mantenimiento como régimen único si combina:

```text
SAG_OFF
BALL_MILL_OFF
CHANCADO_OFF
CV_OFF
ARRANQUE
DETENCION
```

Crear subregímenes cuando exista `N` suficiente.

### 10.5 Overflow

Usar como control positivo.

No degradar un régimen que ya cumple tolerancia para corregir otro.

---

## 11. Separación train / validation / hold-out

### Regla

No puede existir solapamiento temporal entre datos usados para calibrar y datos usados para validar.

Aplicar:

```text
train: período inicial
validation: período intermedio
hold-out: período final
```

También puede usarse validación rolling-origin.

Crear:

```text
calibration_split_manifest.csv
```

Columnas:

```text
event_id
asset
regime
start_time
end_time
split
dataset_version
```

Verificar explícitamente leakage en:

```text
DRAIN_PCT_H
dose-response T8
P50/P75/P90
BOLA_DELTA_TPH
factor alimentación
pile_feedback
Monte Carlo sigma
```

---

## 12. Modelos candidatos

Evaluar incrementalmente.

### Modelo A — Baseline

Sin cambios.

### Modelo B — Parámetros por activo

Ejemplo:

```text
feed_factor_restricted_sag1
feed_factor_restricted_sag2
```

### Modelo C — Parámetros por régimen

Ejemplo:

```text
pile_feedback_normal
pile_feedback_t8
pile_feedback_critical
```

### Modelo D — Modelo por celda

Solo si existe `N` suficiente.

Aplicar shrinkage hacia un parámetro global para evitar sobreajuste.

### Modelo E — Jerárquico / partial pooling

Modelo recomendado cuando existen muchas celdas con distinto tamaño muestral.

Conceptualmente:

\[
\theta_{celda} \sim \mathcal{N}(\theta_{global}, \tau^2)
\]

y:

\[
y_{evento} \sim p(y\mid\theta_{celda})
\]

Permite:

- compartir información;
- evitar parámetros extremos;
- modelar SAG1/SAG2;
- producir incertidumbre.

### Modelo F — Residual estadístico

Solo después de corregir errores físicos.

Ejemplos:

```text
Ridge
Elastic Net
Gradient Boosting
modelo bayesiano jerárquico
```

No sustituir el balance físico.

---

## 13. Criterios de suficiencia por celda

Clasificar:

```text
N < 20       → insuficiente
20 ≤ N < 50  → exploratoria
50 ≤ N < 100 → calibrable con regularización
N ≥ 100      → calibrable
```

Estos umbrales son una guía y deben adaptarse a:

- autocorrelación;
- cantidad de eventos independientes;
- heterogeneidad;
- ruido.

No confundir número de filas de 5 minutos con número de eventos independientes.

La unidad efectiva de muestra debe ser el evento.

---

## 14. Función objetivo de calibración

Evitar optimizar únicamente MAE global.

Ejemplo:

\[
L =
w_1 MAE_{trayectoria}
+
w_2 |Bias|
+
w_3 Error_{mínimo}
+
w_4 Error_{tiempo\ mínimo}
+
w_5 Error_{recuperación}
\]

Agregar penalización por complejidad:

\[
L_{total}=L+\lambda\|\theta-\theta_{baseline}\|^2
\]

Documentar todos los pesos.

No ajustar pesos silenciosamente.

---

## 15. Criterios de aceptación

Criterios iniciales sugeridos:

```text
MAE por régimen ≤ 5 pp
|bias| por régimen ≤ 3 pp
error tiempo de mínimo ≤ 30 min
overflow no debe superar MAE 5 pp
conservación de masa intacta
```

Si no son alcanzables por ruido observacional:

1. estimar el piso de error del sensor;
2. documentar incertidumbre;
3. proponer nueva tolerancia;
4. obtener aprobación.

No cambiar la tolerancia porque el modelo falla.

---

## 16. Validación de robustez

Evaluar por:

```text
activo
régimen
duración
mes
turno
nivel inicial
rate
bolas
estado de chancado
```

Aplicar:

- bootstrap por eventos;
- intervalos de confianza;
- análisis de outliers;
- rolling validation;
- drift temporal;
- sensibilidad.

Reportar intervalos, no solo estimaciones puntuales.

---

## 17. Incertidumbre Monte Carlo

Calibrar:

```text
sigma_pila
sigma_alimentacion
sigma_duracion_t8
```

desde residuos históricos.

Verificar:

- normalidad;
- asimetría;
- colas;
- dependencia entre variables;
- diferencias por régimen.

Si Normal truncada no es adecuada, evaluar:

```text
lognormal
beta
empírica bootstrap
mixturas
```

Comparar:

```text
p_safe proyectado
vs
frecuencia observada
```

---

## 18. Impacto operacional

Toda calibración debe evaluarse también sobre:

```text
autonomía dinámica
vulnerabilidad histórica
STARVED
RESTRICTED
IRO
recomendación
ranking
p_safe
```

Crear matriz:

| Modelo | Cambio recomendación | FP críticos | FN críticos | Anticipación | MAE |
|---|---:|---:|---:|---:|---:|

No seleccionar un modelo solo por menor MAE si empeora eventos críticos.

---

## 19. Implementación segura

Cuando exista causa raíz confirmada:

1. modificar el parámetro mínimo;
2. versionar calibración;
3. preservar baseline;
4. usar feature flag si aplica;
5. agregar tests;
6. ejecutar backtesting;
7. ejecutar hold-out;
8. comparar resultados;
9. documentar impacto;
10. limpiar artefactos.

No mezclar calibración con refactor arquitectónico.

---

## 20. Archivos recomendados

Crear o mantener:

```text
05_Dashboard/config/calibration/
    calibration_registry.yaml
    feed_factors.yaml
    pile_feedback.yaml
    t8_response.yaml
    monte_carlo_uncertainty.yaml

05_Dashboard/engine/calibration/
    dataset_split.py
    error_decomposition.py
    fit_feed_factor.py
    fit_pile_feedback.py
    evaluate_calibration.py
```

No crear estos archivos si ya existe una estructura equivalente.

Primero consultar MCP y reutilizar la arquitectura vigente.

---

## 21. Registro de calibración

Cada parámetro debe tener:

```text
nombre
valor
unidad
activo
régimen
dataset
fecha mínima
fecha máxima
N eventos
método
métrica train
métrica validation
métrica hold-out
autor
versión
estado
```

Estados:

```text
EXPERIMENTAL
VALIDATED
ACTIVE
DEPRECATED
REJECTED
```

---

## 22. Entregables obligatorios

Generar:

```text
04_Reports/Technical/Diagnostico_Fidelidad_Historica.md
04_Reports/Technical/Recalibracion_Multicelda.md
04_Reports/Technical/Validacion_Holdout_Simulador.md
```

Datos derivados:

```text
backtesting_results_by_event.csv
backtesting_summary_by_cell.csv
calibration_split_manifest.csv
calibration_registry.yaml
```

Gráficos:

```text
error por régimen
bias por régimen
predicho vs real
error acumulado
residuos por tiempo
mínimo predicho vs real
recovery predicha vs real
```

---

## 23. Pruebas obligatorias

- split sin leakage;
- eventos no divididos entre splits;
- parámetros cargados;
- baseline reproducible;
- conservación de masa;
- backtesting por régimen;
- hold-out;
- overflow no degradado;
- Monte Carlo reproducible;
- recomendaciones coherentes;
- ausencia de doble penalización;
- compatibilidad de claves;
- limpieza posterior.

---

## 24. Limpieza después de cada modificación

Flujo obligatorio:

```text
modificar
→ prueba específica
→ backtesting afectado
→ revisar artefactos
→ limpiar
→ regresión completa
→ actualizar reporte
```

Eliminar:

- notebooks temporales;
- CSV duplicados;
- imágenes intermedias;
- dumps MCP;
- parámetros rechazados sin registro;
- scripts exploratorios no reproducibles.

Conservar:

- código reproducible;
- manifiestos;
- resultados finales;
- parámetros versionados;
- evidencia hold-out.

---

## 25. Criterio final de cierre

La calibración multicelda se considera terminada cuando:

- existe separación temporal real;
- cada parámetro activo tiene trazabilidad;
- no hay leakage;
- las celdas principales cumplen tolerancia;
- las celdas con pocos datos usan regularización o parámetro global;
- overflow no se degrada;
- conservación de masa se mantiene;
- Monte Carlo está calibrado o etiquetado como heurístico;
- recomendaciones no empeoran;
- existe reporte hold-out;
- el estado es reproducible desde un commit limpio.

---

## 26. Formato de respuesta al usar esta skill

Responder siempre con:

### Diagnóstico

Qué celda o régimen falla.

### Evidencia

N, período, MAE, bias, intervalos.

### Causa probable

Alimentación, consumo, estado inicial, geometría, tiempo o datos.

### Acción

Experimento o cambio mínimo.

### Validación

Train, validation, hold-out y efecto operacional.

### Riesgo

Sobreajuste, leakage, regresión o falta de datos.

### Próximo paso

Único paso recomendado de mayor ROI.

---

## 27. Regla final

No considerar calibrado un modelo porque ajusta bien el conjunto completo.

Un modelo queda aceptado cuando generaliza en hold-out, mantiene coherencia física y mejora decisiones operacionales.

La secuencia correcta es:

```text
diagnosticar
→ segmentar
→ calibrar
→ regularizar
→ validar
→ comparar decisiones
→ versionar
```