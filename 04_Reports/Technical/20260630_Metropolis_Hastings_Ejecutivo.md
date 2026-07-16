# Informe Ejecutivo — Evaluación Metropolis-Hastings
## Gemelo Digital Molienda SAG — División El Teniente
**Fecha:** 30 junio 2026 | **Clasificación:** Interno CIO-DET

---

## VEREDICTO

> **SÍ — Incorporar MH como módulo de calibración mensual del gemelo digital**
>
> No reemplaza el Monte Carlo tiempo real; lo complementa.

---

## ¿Qué es Metropolis-Hastings?

Metropolis-Hastings (MH) es un algoritmo bayesiano que aprende distribuciones de probabilidad sobre los **parámetros del modelo** (no solo sobre los resultados). Cada nuevo evento T8 actualiza las creencias sobre el comportamiento del sistema.

La diferencia con el Monte Carlo actual:

| | Monte Carlo (actual) | Metropolis-Hastings |
|--|--|--|
| ¿Qué modela? | Variabilidad de resultados | Variabilidad de resultados + incertidumbre de parámetros |
| ¿Aprende con datos? | No | **Sí** |
| Intervalos | Frecuentistas | Bayesianos (directamente interpretables) |

---

## ¿Qué encontramos?

Analizando **70 eventos T8** (ago-2025 → jun-2026):

### Hallazgo 1: El consumo real de pila es el doble de la media bruta

El modelo MC usa la media histórica cruda: **0.99 pp/h SAG1 / 0.90 pp/h SAG2**.

El posterior MH identifica que cuando los SAG están activamente operando durante T8, el consumo real es **1.88 pp/h SAG1 / 1.46 pp/h SAG2** — casi el doble. La diferencia se explica porque la media bruta incluye eventos donde la correa CV315 llenaba la pila simultáneamente.

### Hallazgo 2: Los riesgos estimados por MH son más altos

| Riesgo | Monte Carlo | MH Bayesiano | Diferencia |
|--------|-------------|--------------|-----------|
| P(pila SAG1 < 15%) | 5.6% | **7.8%** | +39% relativo |
| P(pila SAG2 < 18.2%) | 24.0% | **29.2%** | +22% relativo |
| P(emergencia doble) | 1.8% | **2.8%** | +55% relativo |
| P(agotamiento SAG1) | 1.2% | 2.0% | — |

En eventos de **T8=12h**: P(inventario SAG1 crítico) pasa de 31% (MC) a **42% (MH)**.

### Hallazgo 3: Las distribuciones son estadísticamente distintas

Test KS pila SAG1: **p=0.024 < 0.05** → Los dos métodos producen predicciones significativamente diferentes para SAG1.

---

## ¿Cuánto tiempo tarda?

| Uso | Tiempo |
|-----|--------|
| MH calibración (3.000 iteraciones, 4 variables) | ~450ms offline |
| ODE Simulator (dashboard, 1 sim) | 13-24ms |
| MC optimización (90 escenarios) | ~3.1s |

El MH **no** está diseñado para tiempo real. Es una calibración periódica.

---

## Recomendación de implementación

```
ARQUITECTURA PROPUESTA:

┌─────────────────────────────────────────────────┐
│  DASHBOARD (tiempo real)                        │
│  ODE Simulator → MC Robustez                    │
│  Parámetros fijos del gemelo                    │
└──────────────┬──────────────────────────────────┘
               │ calibración mensual
               ▼
┌─────────────────────────────────────────────────┐
│  MÓDULO MH (offline, mensual)                   │
│  Actualiza: μ_consumo, σ_consumo, μ_autonomía   │
│  Entrada: nuevos eventos T8 del mes             │
│  Salida: parámetros posterior → dashboard       │
└─────────────────────────────────────────────────┘
```

**Esfuerzo estimado:** 2-3 días desarrollo Python + 1 día integración dashboard.

---

## Respuesta a las 10 preguntas

| # | Pregunta | Respuesta |
|---|----------|-----------|
| 1 | ¿MH mejora la precisión? | Sí, más conservador y calibrado |
| 2 | ¿Distribuciones significativamente distintas? | Sí (KS p=0.024 para SAG1) |
| 3 | ¿Mejor distribución para consumo SAG1? | Beta (datos positivos) |
| 4 | ¿Mejor distribución para autonomía? | Beta/Gamma según SAG |
| 5 | ¿P(agotamiento pila \| T8=4h)? | ~0% MC y MH |
| 6 | ¿P(agotamiento pila \| T8=12h)? | MC=14%, MH=22% |
| 7 | ¿P(inventario < 15% SAG1)? | MC=5.6%, MH=7.8% |
| 8 | ¿P(emergencia doble)? | MC=1.8%, MH=2.8% |
| 9 | ¿Reduce incertidumbre predictiva? | No; la aumenta (ahora incluye incert. paramétrica) |
| 10 | ¿Reemplaza el MC del dashboard? | No — complementa como calibrador |

---

## Archivos generados

| Archivo | Descripción |
|---------|-------------|
| `outputs/excel/metropolis_hastings_results.xlsx` | 9 hojas: variables, distribuciones, posteriors, comparación MC/MH, riesgo por duración, métodos, convergencia |
| `outputs/reports/20260630_Metropolis_Hastings_Evaluacion.md` | Informe técnico completo (fases 1-6) |
| `data/cache/mh_post_c1.npy` | Posterior MH consumo SAG1 (2.500 muestras) |
| `data/cache/mh_post_c2.npy` | Posterior MH consumo SAG2 |
| `data/cache/mh_post_a1.npy` | Posterior MH autonomía SAG1 |
| `data/cache/mh_post_a2.npy` | Posterior MH autonomía SAG2 |

---

*División El Teniente | Analítica Avanzada CIO-DET | 2026-06-30*
