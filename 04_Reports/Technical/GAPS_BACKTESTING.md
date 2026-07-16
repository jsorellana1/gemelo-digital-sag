# GAPS_BACKTESTING.md — Brechas de backtesting remanentes

**Fecha:** 2026-07-07

Tras TAREA 2/3 del prompt "CIERRE DE BRECHAS POST ROUTER v2", los 4
regímenes sin dataset de eventos oficial (`overflow`,
`inventario_critico`, `mantenimiento`, `alimentacion_restringida`) SÍ
alcanzaron N suficiente vía detección retrospectiva
(`engine/diagnostics/regime_event_detector.py`) sobre la serie continua
de 5 min. Queda **una sola brecha remanente**:

## `t8_larga` — N insuficiente

```
N eventos = 8   (minimo requerido = 20)
Fuente: advanced_t8_official_events.parquet (eventos oficiales, no proxy)
```

**Por qué no se puede resolver con datos actuales:** a diferencia de
`overflow`/`inventario_critico`/`mantenimiento`/`alimentacion_restringida`
(que se pueden re-detectar retrospectivamente con umbrales sobre una
serie continua), `t8_larga` depende de una **decisión operacional
externa real** (cuándo Planificación programa una ventana T8 de más de
4h) — no es un patrón que se pueda re-derivar de la serie de pila/TPH sin
inventar el criterio de "por qué fue programada". El dataset oficial de
eventos T8 (`advanced_t8_official_events.parquet`, 72 eventos totales,
2025-08-01 a 2026-06-21, ~11 meses) solo registró 8 eventos de duración
>4h en ese periodo — es la tasa real de ocurrencia de T8 largas, no un
problema de instrumentación.

## Qué datos adicionales cerrarían el gap

- **PI/SAP:** el dataset ya cubre PI (correa_315/316, pila, TPH) a 5 min
  con calidad alta. No hay una fuente adicional en PI que aumente la
  tasa de eventos T8 largos — esos eventos ocurren cuando ocurren.
- Lo único que cerraría el gap es **más tiempo de operación real**
  acumulando más eventos T8 largos, o una fuente externa (SAP/bitácora de
  Planificación) que reclasifique retroactivamente ventanas T8 cortas mal
  etiquetadas como largas — no verificado, requeriría acceso a SAP que
  no está disponible en este proyecto.

## Fecha estimada para alcanzar N=20

Con una tasa observada de 8 eventos T8>4h en 11 meses (~0.73 eventos T8
largos/mes), se necesitan 12 eventos adicionales para llegar a N=20:

```
12 eventos / 0.73 eventos-mes ≈ 16.4 meses adicionales
```

**Fecha estimada:** ~noviembre de 2027 (asumiendo tasa constante — no
se ajusta por estacionalidad ni por posibles cambios en la política de
programación de T8, que podrían acelerar o retrasar esto).

## Estado mientras tanto

`route_and_simulate()` para escenarios `t8_larga` continúa reportando
`historica_disponible=False` con esta razón explícita — nunca "OK". La
tarjeta del router v2 debe mostrar **confianza BAJA** para este régimen
(ver TAREA 5).
