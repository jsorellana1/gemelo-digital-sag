# Optimizer v2 — Diseno Tecnico y Validacion

Fecha: 2026-07-01
Version: v2.0
Autor: Juan Orellana / AA_CIO_DET / Codelco El Teniente

---

## 1. Motivacion y Problema Resuelto

El optimizador legacy (v1) usaba score = TPH - deficit_autonomia * 2000. Esta penalizacion
dura hacia que SAG1 (pila 4575 ton, drenaje 23.76 %/h) entrara casi siempre en zona
infactible al activar bolas, aniquilando su score. Resultado: el boton Optimo segun pila
siempre recomendaba sin_bola para SAG1, independientemente de las condiciones de inventario.

El Optimizer v2 reemplaza la penalizacion dura por una funcion multicriterio ponderada
donde la autonomia es un componente suave (10%), no una barrera.

## 2. Funcion Objetivo Multicriterio

  score = 0.40 * prod_norm + 0.30 * p_safe + 0.20 * inv_norm + 0.10 * auton_norm

Donde:
  prod_norm  = TPH_total / 3970 (P90 SAG1+SAG2 como referencia)
  p_safe     = P(autonomia >= umbral) del Monte Carlo adaptativo
  inv_norm   = pila_final_promedio / 70%
  auton_norm = (a1/6h + a2/8h) / 2

Todos los componentes en [0, 1]. Autonomia contribuye solo el 10% -- SAG1 con bolas
recibe penalizacion parcial, no aniquilamiento.

## 3. Calibracion Historica DELTA_TPH Bolas

### Resultados

| SAG  | Delta TPH (1 bola) | Delta TPH (2 bolas) | n0 (sin bola) | Fuente         |
|------|--------------------|---------------------|---------------|----------------|
| SAG1 | 116.3 TPH         | 232.6 TPH          | 11         | Modelo legacy |
| SAG2 | 201.3 TPH         | 402.6 TPH          | N/A         | Modelo legacy |

### Notas de calibracion

SAG1: n_bolas=0 insuficiente (n0=11 < 200): no hay grupo de control para calibrar dTPH empiricamente. Se usa modelo de ingenieria BOLA_BONUS=0.08 (=8% de P90).
SAG2: n_bolas=0 insuficiente (n0=0 < 200): no hay grupo de control para calibrar dTPH empiricamente. Se usa modelo de ingenieria BOLA_BONUS=0.08 (=8% de P90).

Limite minimo para calibracion historica valida: n0 >= 200 (MIN_N0).
Cuando n0 < MIN_N0 se usa modelo de ingenieria legacy: BOLA_BONUS=0.08 * P90.
SAG1 P90=1454 TPH -> delta_legacy = 116.3 TPH/bola.
SAG2 P90=2516 TPH -> delta_legacy = 201.3 TPH/bola.

## 4. Monte Carlo Adaptativo

Parametros:
  - Perturbaciones: pilas +/-2.5%, feed CV +/-12%, T8 +/-1h
  - Lotes: 10 simulaciones por batch
  - Convergencia: |Delta_p_safe| < 1% durante 3 checks consecutivos Y n >= 30
  - Cap: 500 simulaciones maximas
  - Candidatos evaluados por MC: top-20 del grid deterministico (100 configs)

El MC adaptativo reemplaza el n_samples fijo (20/30/50). El estado de convergencia
se muestra en el dashboard: "Sim: N -- Convergente/No convergente".

## 5. Frente de Pareto

Tres objetivos: maximizar TPH, maximizar P(safe), maximizar inventario final.
Dominancia O(N^2) sobre N<=100 configuraciones.
Las configuraciones Pareto-optimas reciben badge "Pareto" en la tabla Top-5.

## 6. Modos del Optimizador

| Boton           | Modo        | Logica de seleccion                              |
|-----------------|-------------|--------------------------------------------------|
| Mejor Config    | balanced    | max score multicriterio                          |
| Max Produccion  | max_prod    | max TPH (riesgo ignorado)                        |
| Op. Segura      | safe        | filtra P(safe)>=0.95, max TPH; fallback: mayor P |
| Balance Optimo  | pareto      | top del frente Pareto                            |
| Reset           | --          | carga estado PI en tiempo real                   |

## 7. Preguntas de Validacion

Q1: Por que SAG1 siempre era sin_bola?
A: Penalizacion dura (deficit*2000) aplastaba el score cuando autonomia < 1.5h. SAG1
   con bolas a cualquier rate razonable y pila < 50% tiene autonomia < 1.5h. Corregido
   con componente suave 10% en multicriterio.

Q2: Son validos los DELTA_TPH calibrados?
A: Los datos muestran que los operadores NUNCA apagan las bolas (n0 ~0 para SAG2, n0=11
   para SAG1). Sin grupo de control valido (MIN_N0=200), el modelo de ingenieria legacy
   BOLA_BONUS=0.08 es el mejor estimado disponible. Los deltas historicos por OLS tienen
   sesgo de seleccion severo (se activan bolas cuando produccion ya es alta).

Q3: Cuantas simulaciones hace el MC?
A: Variable: entre 30 y 500. Para condiciones tipicas converge en 50-80 sims por config,
   evaluando 20 configs = 1000-1600 simulaciones totales por click.

Q4: Que pasa en modo Operacion Segura si ninguna config cumple P(safe)>=0.95?
A: El fallback retorna la configuracion con mayor P(safe) disponible. No crashea.

Q5: Los graficos nuevos que muestran?
A: Pareto scatter (TPH vs P(crisis), color=inventario): permite ver la frontera
   eficiente. Impacto bolas (3 subplots: DELTA_TPH, DELTA_Autonomia, DELTA_Inventario):
   cuantifica el trade-off de activar bolas para cada SAG.

## 8. Archivos Nuevos / Modificados

  02_Analytics/Scripts/calibrar_bola_delta_tph.py  [NUEVO]
  01_Data/Cache/bola_delta_tph.json               [GENERADO]
  02_Analytics/Figures/12_Optimizer_v2/            [DIRECTORIO NUEVO]
  05_Dashboard/engine/ode_model.py                 [MODIFICADO -- effective_rate aditivo]
  05_Dashboard/engine/optimizer_v2.py              [NUEVO -- 340 lineas]
  05_Dashboard/components/graphs.py                [MODIFICADO -- +2 funciones]
  05_Dashboard/components/cards.py                 [MODIFICADO -- +make_top5_card]
  05_Dashboard/components/controls.py              [MODIFICADO -- rm ctrl-mc-n]
  05_Dashboard/app.py                              [MODIFICADO -- +4 callbacks, +5 botones]
