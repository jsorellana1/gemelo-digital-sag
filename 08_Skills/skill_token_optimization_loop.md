# skill_token_optimization_loop.md

## Propósito

Reducir al máximo el consumo de tokens, tiempo de cómputo y costo computacional durante proyectos de Ciencia de Datos, Machine Learning, Analítica Avanzada, Optimización, Simulación y Generación de Reportes.

Este skill debe ejecutarse automáticamente antes de cualquier:

* EDA
* Entrenamiento
* Simulación
* GridSearch
* Optuna
* SHAP
* Generación de PDF
* Notebook
* Script Python

---

# Principio Fundamental

Antes de ejecutar una tarea preguntarse:

```text
¿Existe una forma más barata de obtener el mismo resultado?
```

Si la respuesta es sí:

```text
usar la opción más eficiente
```

---

# Regla 1 — Pensar antes de ejecutar

Prohibido ejecutar:

```text
100 modelos
1000 simulaciones
500 trials Optuna
```

sin antes justificar:

```text
por qué son necesarios
```

---

# Regla 2 — Reutilizar resultados

Antes de entrenar:

Buscar:

```text
outputs/models/
```

Si existe un modelo previamente entrenado:

```text
evaluarlo primero
```

antes de volver a entrenar.

---

# Regla 3 — Cache obligatorio

Toda salida costosa debe almacenarse:

```text
data/cache/
```

Ejemplos:

* joins complejos
* datasets maestros
* SHAP values
* embeddings
* simulaciones

---

# Regla 4 — Evitar recalcular

Si existe:

```text
dataset_master.parquet
```

NO volver a:

```text
leer 20 excels
hacer joins nuevamente
```

Utilizar el dataset consolidado.

---

# Regla 5 — Muestreo Inteligente

Durante exploración:

Usar:

```python
df.sample()
```

o

```python
head()
```

antes de procesar el dataset completo.

---

# Regla 6 — EDA Progresivo

Fase 1

```text
1000 filas
```

Fase 2

```text
10000 filas
```

Fase 3

```text
dataset completo
```

Solo si las fases anteriores justifican continuar.

---

# Regla 7 — Entrenamiento Escalonado

Orden obligatorio:

```text
LinearRegression

↓

DecisionTree

↓

RandomForest

↓

XGBoost

↓

Optuna
```

Nunca partir por modelos complejos.

---

# Regla 8 — Early Stopping Universal

Activar:

## XGBoost

```python
early_stopping_rounds
```

## LightGBM

```python
early_stopping
```

## CatBoost

```python
od_type="Iter"
```

---

# Regla 9 — Loop Inteligente

Detener búsqueda cuando:

```text
Mejora < 1%
durante 3 iteraciones consecutivas
```

No seguir buscando.

---

# Regla 10 — GridSearch Prohibido

Por defecto:

NO usar:

```python
GridSearchCV
```

Usar:

```python
RandomizedSearchCV
```

o

```python
Optuna
```

---

# Regla 11 — Optuna Eficiente

Comenzar con:

```text
20 trials
```

Luego:

```text
50 trials
```

Luego:

```text
100 trials
```

Solo escalar si existe mejora.

Nunca partir en:

```text
500+
```

trials.

---

# Regla 12 — SHAP Inteligente

Nunca calcular SHAP sobre:

```text
100%
del dataset
```

Usar:

```python
sample(1000)
sample(5000)
```

según tamaño.

---

# Regla 13 — Gráficos

Antes de crear un gráfico:

Preguntar:

```text
¿Existe ya uno equivalente?
```

Si sí:

```text
reutilizar
```

---

# Regla 14 — PDFs

Generar PDF solamente cuando:

```text
modelo final aprobado
```

No generar PDFs intermedios.

---

# Regla 15 — Notebooks

Máximo:

```text
1 notebook maestro
```

por línea analítica.

Evitar proliferación de notebooks.

---

# Regla 16 — GPU

Usar GPU solo cuando:

```text
n_filas > 100000
```

o

```text
Optuna > 100 trials
```

o

```text
SHAP masivo
```

De lo contrario:

```text
CPU
```

---

# Regla 17 — Drift

Antes de reentrenar:

Evaluar:

```text
Data Drift
Concept Drift
```

Si no existe drift:

```text
no reentrenar
```

---

# Regla 18 — Feature Engineering

Agregar variables nuevas únicamente si:

```text
aportan mejora medible
```

No agregar features por intuición.

---

# Regla 19 — Ranking de Acciones

Siempre intentar en este orden:

```text
1. Reutilizar

2. Cache

3. Muestreo

4. Modelo simple

5. Modelo complejo

6. Optimización

7. SHAP

8. PDF
```

---

# Regla 20 — Auditoría Final

Antes de finalizar cualquier tarea:

Generar:

```text
Costo computacional estimado
Tiempo ejecución
Tokens ahorrados
Archivos reutilizados
Modelos reutilizados
```

---

# Regla 21 — Aplicado a Optimizer V3 / Monte Carlo adaptativo / Metropolis-Hastings

Estos tres motores del Gemelo Digital (`05_Dashboard/engine/`) ya implementan
varias de las reglas anteriores — no reinventar, extender:

## Metropolis-Hastings

```text
Regla 2 (reutilizar) aplicada literalmente:
NUNCA correr MH en tiempo real dentro del dashboard.
Solo consumir posteriors pre-calculados de 01_Data/Cache/mh_post_*.npy
```

## Monte Carlo adaptativo (`optimizer_v2.py::adaptive_mc_eval`)

```text
Ya implementa Regla 9 (loop inteligente):
para cuando |Delta P(seguro)| < tolerancia por N checks consecutivos,
en vez de correr siempre las 500 simulaciones maximas.
```

Al agregar nuevas métricas al Monte Carlo (ej. riesgo por hora, TPH por
SAG), **capturarlas de la simulación que ya se ejecuta por muestra**
(`sim = simulate_scenario(...)`) en vez de lanzar simulaciones adicionales
— así se cumple Regla 1 sin sacrificar funcionalidad nueva.

## Optimizer V3 (`optimizer_v3.py`)

```text
Regla 19 (ranking de acciones) aplicada:
1. Grilla deterministica (barata) primero
2. Top-20 candidatos -> Monte Carlo (caro) solo sobre esos 20
3. Nunca correr Monte Carlo sobre el total de la grilla
```

**Excepción histórica (revertida 2026-07-06):** entre 2026-07-02 y
2026-07-06 este documento recomendaba mantener Monte Carlo reactivo en
cada cambio de slider por decisión explícita del usuario. Esa decisión fue
revertida — ver `04_Reports/Technical/20260706_Performance_Optimization_EXE.md`
sección Fase 6. Estado actual: `run_monte_carlo` (`pages/simulador_operacional.py`)
solo corre al presionar el botón "Monte Carlo" (`Input("btn-monte-carlo",
"n_clicks")`); los 27 parámetros de escenario son `State`. Regla 2
(reutilizar) y Regla 19 (ranking de acciones) vuelven a aplicar sin
excepción: no recalcular Monte Carlo/optimizador salvo acción explícita
del usuario. Antes de asumir reactividad en vivo en este flujo, verificar
el estado real del código — esta nota puede volver a quedar desactualizada
si la decisión se revierte otra vez.

---

# Modo Loop

Antes de cada iteración ejecutar:

```text
1. ¿Puedo reutilizar algo?

2. ¿Puedo reducir datos?

3. ¿Puedo reducir modelos?

4. ¿Puedo reducir gráficos?

5. ¿Puedo detener el loop?

6. ¿La mejora justifica el costo?
```

Si la respuesta es:

```text
NO
```

detener inmediatamente.

---

# Objetivo Final

Maximizar:

```text
Valor analítico
```

y minimizar:

```text
Tokens
CPU
GPU
Tiempo
Costo
Complejidad
```

Manteniendo:

```text
Trazabilidad
Reproducibilidad
Interpretabilidad
```
