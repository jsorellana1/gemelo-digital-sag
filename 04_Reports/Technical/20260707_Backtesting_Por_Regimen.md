# Backtesting por régimen — reporte consolidado

**Fecha:** 2026-07-07
**Contexto:** cierre de brechas sobre `20260707_Arquitectura_Simulacion_Router_v2.md`
tras auditar ese router contra un prompt de arquitectura más detallado.
Este reporte consolida en una sola tabla lo que antes estaba repartido
entre `COBERTURA_BACKTESTING_ACTUALIZADA.md`, `GAPS_BACKTESTING.md` y
`DIAGNOSTICO_MAE_t8_corta.md`, y agrega dos métricas que el router v2
tenía definidas pero sin calcular: **MAE TPH** y **error de tiempo hasta
el umbral crítico** (vaciado o overflow, según el régimen). Todos los
números de este reporte salen de correr `run_backtest()`/
`run_backtest_proxy()` (`engine/historical_backtesting.py`) contra datos
reales — ninguno fue ajustado ni fabricado para "hacer pasar" nada.

---

## Tabla consolidada

| Régimen | N eventos | MAE pila SAG1 (pp) | MAE pila SAG2 (pp) | MAE TPH SAG1 (%) | Error hasta crítico (h) | Dentro tolerancia (5.0pp) | Estado |
|---|---:|---:|---:|---:|---:|---|---|
| t8_corta | 63 | 18.88 | 4.42 | 30.6 | 3.98 | NO | Datos oficiales (`advanced_t8_official_events.parquet`), N suficiente. Ver causa raíz del MAE en `DIAGNOSTICO_MAE_t8_corta.md`. |
| t8_larga | 8 | — | — | — | — | N/A | **No disponible** — N=8 eventos oficiales, bajo el mínimo (20). No se fabricó un backtesting con N insuficiente. |
| overflow | 97 | 4.51 | — | 0.0 | 0.45 | **SÍ** | Detección retrospectiva (proxy, `regime_event_detector.py`). Único régimen que pasa la tolerancia de pila. |
| inventario_critico | 221 | 13.89 | — | 29.1 | 0.46 | NO | Detección retrospectiva (proxy). |
| mantenimiento | 239 | 14.47 | — | 69.0 | — | NO | Proxy, cobertura parcial (solo SAG1/SAG2, sin serie de CH1/CH2/bolas). Sin umbral de tiempo definido (no aplica vaciado/overflow). |
| alimentacion_restringida | 1477 | 12.80 | — | 9.8 | — | NO | Proxy, cobertura parcial (solo CV315/CV316, sin serie de CH1/CH2/T1). Sin umbral de tiempo definido. |

`MAE pila` y `dentro_tolerancia` reproducen exactamente los números ya
publicados en `COBERTURA_BACKTESTING_ACTUALIZADA.md` (no se recalcularon
distinto) — esta tabla solo les agrega las dos columnas nuevas.

---

## MAE TPH — qué mide y su limitación honesta

El motor (`simulate_scenario_cached`) recibe como **entrada** el TPH
promedio observado durante el evento real (`SAG1_tph.mean()` en la
ventana), no una serie independiente. El "MAE TPH" de esta tabla compara
el TPH promedio que el ODE termina simulando contra ese mismo promedio de
entrada — por diseño, mide la fidelidad de la dinámica interna del ODE
alrededor del punto de operación fijado, **no** una predicción
independiente del TPH. Valores altos (mantenimiento 69%, inventario
crítico/t8_corta ~29-31%) reflejan que el ODE ajusta el rate real
efectivo por restricciones internas (arranques, capacidad de chancado,
bola SAG) incluso cuando se le pide una tasa fija — es información
diagnóstica sobre el modelo, no un error de "predicción de demanda".
overflow con 0.0% es consistente con que ese régimen ya corre en modo
`max_prod`/capacidad, donde el rate efectivo queda pegado al límite
físico casi sin ajuste.

## Error hasta crítico — qué mide

Compara, para los regímenes con un umbral de tiempo bien definido
(`t8_corta`, `t8_larga`, `inventario_critico`: tiempo hasta autonomía
< 1h; `overflow`: tiempo hasta pila ≥ 95%), el instante en que la serie
**observada** cruza ese umbral contra el instante en que la serie
**simulada** lo cruza, ambos medidos desde el inicio de la ventana del
evento. Solo se promedia sobre los eventos donde **ambas** series
cruzan el umbral dentro de la ventana disponible — si una de las dos no
cruza, ese evento no aporta al promedio (no se imputa un valor).
`mantenimiento` y `alimentacion_restringida` no tienen un umbral de
tiempo único y comparable (no representan un proceso de
llenado/vaciado direccional), así que el campo queda `None` con la razón
explícita — mismo criterio de honestidad que el resto del proyecto: no
se fabrica el número.

---

## Qué NO se pudo medir y por qué (gaps declarados, no resueltos)

- **Error de cumplimiento PAM:** requiere una fuente de datos de meta
  PAM por turno/día que no está conectada a este módulo — no es un
  cálculo que falte, es una fuente de datos que no existe en el
  pipeline actual. Fuera de alcance de este cierre de brechas.
- **Tasa de falsas alarmas / tasa de crisis no detectadas:** requeriría
  correr el `CriticalityScorer` sobre el estado *previo* a cada evento
  detectado (y sobre ventanas donde NO hubo evento, para medir falsos
  positivos) a lo largo de los 11 meses de serie continua — un trabajo
  de una magnitud distinta al resto de este reporte (barrido completo
  de la serie, no solo los eventos ya detectados). Se deja como
  pendiente explícito, no como número inventado.
- **t8_larga:** sigue sin backtesting por N insuficiente (8 < 20). No
  cambia con este cierre de brechas — requeriría más datos históricos
  reales, no más código.

---

## Decisión sobre el orden de prioridad del router

El prompt de arquitectura pedía un orden de prioridad fijo de 7 pasos
(mantención primero siempre). El router v2 (`route_and_simulate`,
`engine/simulation_router.py`) usa en cambio un score de urgencia
dinámico (`CriticalityScorer`). Se decidió **no reordenar** esto: la
intención real detrás de "mantención siempre primero" —nunca recomendar
un equipo que está fuera de servicio— ya estaba garantizada físicamente
(los flags on/off que ve el motor vienen del estado real del equipo, no
de qué estrategia "ganó" el scoring) y se reforzó explícitamente en este
mismo cierre de brechas: `physics_validation.py` ahora compara
`equipos_en_mantencion` contra los flags realmente usados para invocar
el motor y marca violación dura si un equipo en mantención quedó
configurado activo (antes ese parámetro se aceptaba pero nunca se
usaba).
