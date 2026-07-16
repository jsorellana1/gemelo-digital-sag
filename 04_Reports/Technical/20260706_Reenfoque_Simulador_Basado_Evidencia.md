# Reenfoque del Simulador Basado en Evidencia — Optimizer V4

**Fecha:** 2026-07-06
**Contexto:** reemplaza la línea de "Optimización Metalúrgica" (ley/recuperación)
propuesta inicialmente, descartada por falta de evidencia — ver hallazgo
en la sección 0.

---

## 0. Por qué se abandonó la línea metalúrgica

El análisis de `Datos Producción.xlsx` (943 días, 2024-01-01 → 2026-07-05)
mostró que, tras excluir 32 días de parada total (que inflaban
artificialmente la correlación a r≈0.54), **no existe relación real entre
TPH y ley/recuperación de cobre**:

| Relación | Correlación (excluyendo paradas) |
|---|---:|
| TPH vs Ley Concentrado | 0.017 |
| TPH vs Recuperación Cu | -0.147 |
| TPH vs Ley (línea Convencional) | -0.051 |

Además, ley/recuperación son métricas **globales de planta**, no
desagregadas por SAG1/SAG2 ni conectadas con CV315/CV316/T3 en el dato
fuente. Construir una "frontera eficiente TPH vs CuFino" o un
"Optimizer V4 metalúrgico" habría significado presentar una relación
causal ficticia. Se reenfocó el esfuerzo hacia lo que **sí** tiene
soporte empírico: la asimetría de variabilidad SAG1 vs SAG2.

---

## 1. Principio rector adoptado

El simulador sigue respondiendo *"¿cómo maximizar toneladas?"* pero ahora
también *"¿cómo mantener producción estable y minimizar riesgo ante
restricciones de alimentación e inventario?"* — no *"¿cómo modificar la
ley mediante los SAG?"* (sin base empírica).

---

## 2. Hallazgos reales de los 917 días (excluyendo paradas totales)

| Activo | CV diario | CV semanal | P10 (t/día) | P50 (t/día) | P90 (t/día) |
|---|---:|---:|---:|---:|---:|
| **SAG1** | **0.444** | 0.395 | 0 | 27.354 | 32.328 |
| **SAG2** | **0.310** | 0.270 | 26.348 | 53.070 | 59.218 |
| MCONV | 0.484 | 0.423 | 20 | 29.049 | 38.389 |
| MUN | 0.700 | 0.624 | 0 | 17.197 | 20.002 |

**SAG1 es ~43% más variable que SAG2** (CV 0.444 vs 0.310) — esto
**confirma con datos independientes** lo que el modelo ya asumía
estructuralmente (`DRAIN_PCT_H`: SAG1=23.76%/h vs SAG2=6.18%/h,
`AUTONOMY_THRESHOLDS` asimétricos). No es un hallazgo nuevo, es una
**validación cruzada** del supuesto existente con 2.6 años de datos
oficiales de producción.

También se confirmó (r=0.695) que el **acarreo desde Teniente 8 (TT8)**
correlaciona de forma moderada-fuerte con el total procesado SAG1+SAG2 —
consistente con que la mina es, en ciertos períodos, un cuello de botella
real aguas arriba del circuito (a diferencia de la relación TPH-ley, que
no lo era).

Se detectaron además meses con concentración de días de parada total
(agosto 2025: 9 días; enero 2025: 6 días; mayo 2024: 6 días) — útil como
contexto histórico, no modelado activamente en esta iteración.

---

## 3. Qué se construyó

### `engine/production_stats.py`
Carga `01_Data/Cache/produccion_diaria_gpta.parquet` (generado por
`02_Analytics/Scripts/ingestion/load_produccion_diaria.py`) y expone
`get_asset_stats(asset)` / `get_all_stats()` — CV y percentiles reales por
activo, excluyendo días de forecast (PAM futuro) y paradas totales.
Sigue el mismo patrón `sys.frozen` de `mh_calibration.py` (dev:
`01_Data/Cache/`, empaquetado: `runtime_data/Cache/` — ya copiado).

### `engine/bottleneck.py` — Detector de Cuello de Botella
Capa de diagnóstico **sin relaciones causales nuevas**: inspecta los
campos que `simulate_scenario` ya calcula (`t1_restriccion`,
`chancado_cap_tph`, estado de correas, autonomía mínima, alertas de
regla de bolas) y devuelve el factor más limitante, priorizado por
severidad. Wireado en `components/cards.py::make_bottleneck_card` y
mostrado en la columna de KPIs del simulador (todas las vistas).

### `engine/optimizer_v4.py` — Extensión aditiva de V3
**No reemplaza ni recalcula V3** — re-rankea el Top-20 que V3 ya evaluó
(incluyendo su Monte Carlo), agregando una **penalización de
estabilidad** basada en el CV real medido:

```
penalización = share_SAG1 × CV_SAG1_real + share_SAG2 × CV_SAG2_real
score_V4 = score_V3 - peso_estabilidad × penalización
```

Con `peso_estabilidad = 0`, V4 es **idénticamente igual a V3** (verificado
por test). Presets de "Tolerancia de riesgo": Conservador (0.30),
Balanceado (0.15), Agresivo (0.0). Costo computacional: **despreciable**
(<1ms, re-ranking puro, sin nuevas simulaciones) — cumple Regla 1/2 de
`skill_token_optimization_loop.md`.

Selector **"Tolerancia de riesgo (V4)"** agregado al sidebar
(`components/controls.py`). Cuando V4 recomienda un split distinto al de
V3 (prioriza SAG2), aparece una línea adicional en el badge de "Óptimo
según pila" mostrando la alternativa — sin ocultar ni reemplazar la
recomendación V3 original.

### 6 nuevos tests
`tests/test_bottleneck_and_stats.py` (8) + `tests/test_optimizer_v4.py`
(8) — incluyen verificación explícita de que V4 con peso=0 coincide
exactamente con V3, y que SAG1 real mide más CV que SAG2. Suite completa:
**59/59 tests pasan**.

---

## 4. Qué NO se construyó, y por qué

| Capa del prompt original | Estado | Motivo |
|---|---|---|
| Capa 2 (distribución óptima por ley) | **Descartada** | Sin evidencia causal (sección 0) |
| Capa 6 (escenarios preconfigurados: T8 12h, CH2 fuera) | **Ya existía** | `/riesgo` ya tiene botones "T8 2h/4h/8h/12h" y "Falla Chancador 2" desde antes de esta sesión |
| Capa 6 (CV315 restringida como preset) | No agregado | `/riesgo` no expone control de estado de correa (solo el simulador principal lo tiene, vía `ctrl-correa315`) — agregarlo requiere una UI nueva en esa página, no un preset trivial |
| Capa 7 (planificador de turno) | No agregado | La infraestructura de turno (A/B/C, hora real) ya existe; un "planificador" adicional es una feature nueva, no una corrección basada en evidencia — se deja para una iteración futura si se solicita explícitamente |
| Capa 9 (pestaña "Salud Operacional" dedicada) | **Parcial** | Se integró como tarjeta en la columna de KPIs existente (Cuello de Botella) en vez de una pestaña nueva — autonomía, riesgo T8 (IRO) y riesgo overflow (Monte Carlo) ya son visibles en tarjetas/gráficos existentes; una pestaña dedicada duplicaría información ya visible |
| Capa 11 (Monte Carlo refocus: T1/CH1/CH2/CV/duración T8) | **Ya existía** | `adaptive_mc_eval` ya perturba pila (±2.5%), CV feed (±12%) y duración T8 (±1h) — es exactamente lo pedido, sin cambios necesarios |

---

## 5. Preservación de lo validado

No se modificó: `ode_model.py` (ecuaciones diferenciales), `optimizer_v2.py`/
`optimizer_v3.py` (scoring/grid original), `rules_engine.py`, `risk_engine.py`,
ni el tuning de Monte Carlo (`MC_MAX_N`, `MC_BATCH`, etc.). Optimizer V4 es
un módulo nuevo que **consume** los resultados de V3 sin tocarlos.

---

## Conclusión

El simulador no evolucionó hacia "optimizar cobre fino" (sin base en los
datos disponibles), sino hacia **explotar la evidencia real que sí
apareció**: la asimetría de estabilidad SAG1/SAG2, ahora medida con 2.6
años de datos oficiales en vez de solo el análisis de eventos T8. Esto es
consistente con el principio rector: no incorporar causalidades no
demostradas.
