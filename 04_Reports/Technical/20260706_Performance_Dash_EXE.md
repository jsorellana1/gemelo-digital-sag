# Performance Dash/.exe — Medición de callbacks lentos (Fase 1-2)

Fecha: 2026-07-06

## Método

No fue posible ejecutar el `.exe` empaquetado ni conducir un navegador en este
entorno (sin GUI/headless-browser disponible). La medición real de este
documento se hizo **llamando directamente al motor** (`engine/simulator.py`,
`engine/optimizer_v3.py`) con `utils/perf_logger.py` ya instrumentado —
mismo código que ejecutan los callbacks de `app.py` y
`pages/simulador_operacional.py`, sin el overhead/latencia de Dash+navegador.
Los números de esta tabla son un piso razonable del tiempo de cómputo puro;
el tiempo percibido en el navegador será algo mayor por serialización
Plotly/red. Ver Fase 16 para la validación pendiente en el `.exe` real.

Script: `perf_smoke_test.py` (scratchpad de sesión, no se guardó en el repo).
Log crudo: `05_Dashboard/outputs/logs/performance.log`.

## Resultados

| Callback / función | n | Media | P95 | Max | Causa probable |
|---|---:|---:|---:|---:|---|
| `simulate_scenario` (cacheado, 1er hit) | 2 | 0.6 ms | — | 1.1 ms | Integración ODE de 288 pasos (24h/5min) — barata. |
| `adaptive_mc_eval` (dentro de find_optimal_v3) | 40 | 335.5 ms | 753.4 ms | 810.6 ms | Top-20 candidatos × Monte Carlo adaptativo (hasta 500 muestras c/u, parada por convergencia). |
| `find_optimal_v3` (escenario nuevo) | 3 | 4,545.8 ms | 6,612.4 ms | 7,024.9 ms | Suma de sus ~20 `adaptive_mc_eval` internos (grid determinístico + MC solo sobre top-20, Regla 19/21 de `skill_token_optimization_loop.md`). |
| `find_optimal_v3` (mismo escenario repetido) | — | 0.1 ms | — | 0.1 ms | Cache hit (Fase 5, `engine/scenario_cache.py`) — sin recomputar. |

## Lectura

- **`simulate_scenario` nunca es el problema.** Es sub-milisegundo; las
  tarjetas/curvas deterministas (balance, TPH, autonomía) pueden actualizarse
  en cada movimiento de slider sin costo perceptible — confirma que no hace
  falta gatear estos outputs.
- **El costo real está 100% concentrado en `find_optimal_v3`**, y dentro de
  él, en sus ~20 llamadas a `adaptive_mc_eval` (una por candidato top-20).
  7.0s en el peor caso medido cae justo en el borde del objetivo de
  performance (`< 8 s` optimización, tabla del prompt original).
- **El cache por escenario (Fase 5) es la palanca de mayor impacto**: un
  escenario ya visto en la sesión pasa de ~7,000 ms a ~0.1 ms. Esto no
  cambia la reactividad (Monte Carlo sigue recalculando en cada slider
  *nuevo*, por decisión ya documentada en
  `20260702_UX_UI_Operational_Control_Center.md`) — solo evita
  recalcular cuando el usuario repite o vuelve a un valor.
- No se detectó ningún callback que recalcule datos ya cargados
  (`DF_HIST` se carga una sola vez a nivel de módulo en `app.py`, ver Fase
  12-13 en el reporte final).

## Limitación reconocida

Esta medición no captura: tiempo de arranque del proceso Dash/Flask, carga de
assets JS/CSS, ni tiempo de renderizado/interactividad en el navegador real
(o Chromium embebido si el `.exe` usara webview). Para cerrar Fase 16
(validación en `.exe`) se requiere que alguien con acceso a
`dist/Gemelo_Digital_Molienda/` cronometre manualmente los 7 pasos listados
en el prompt original y anote los tiempos en el reporte final.
