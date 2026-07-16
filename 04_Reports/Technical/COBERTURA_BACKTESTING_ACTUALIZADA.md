# Cobertura de backtesting actualizada — post cierre de brechas

**Fecha:** 2026-07-07

| Régimen | N eventos archivo oficial | N detectados (proxy) | N válidos | Cobertura | MAE pila (pp) | Dentro tolerancia (5.0pp) |
|---|---:|---:|---:|---|---:|---|
| t8_corta | 64 | — | 63 | Archivo oficial | 18.88 | NO (causa diagnosticada, ver `DIAGNOSTICO_MAE_t8_corta.md`) |
| t8_larga | 8 | — | 8 | Archivo oficial (**insuficiente**, min=20) | — | N/A — ver `GAPS_BACKTESTING.md` |
| overflow | 0 | 97 | 97 | Detector retrospectivo (proxy) | 4.51 | **SÍ** |
| inventario_critico | 0 | 221 | 221 | Detector retrospectivo (proxy) | 13.89 | NO |
| mantenimiento | 0 | 241 | 239 | Detector retrospectivo (proxy, solo SAG1/SAG2 — no CH1/CH2/bolas) | 14.47 | NO |
| alimentacion_restringida | 0 | 1479 | 1477 | Detector retrospectivo (proxy parcial, solo CV315/316 — no CH1/CH2/T1) | 12.80 | NO |

## Notas de interpretación

- **overflow es el único régimen que pasa la tolerancia.** No se ajustó
  ningún umbral para lograrlo — es el resultado real del backtesting.
- Los MAE de `inventario_critico`, `mantenimiento` y
  `alimentacion_restringida` (14-15 pp) están en el mismo orden de
  magnitud que el de `t8_corta` sin corregir la alimentación (27.8pp) y
  por encima del corregido (18.9pp) — consistente con la misma limitación
  estructural diagnosticada en TAREA 1: el motor recibe una tasa/feed
  **promedio** del evento, no la trayectoria real minuto a minuto, y para
  `mantenimiento`/`alimentacion_restringida` además falta la serie de
  CH1/CH2/T1 que existiría en un dataset más completo.
- **Ningún test ajustó su tolerancia para pasar.** `TOLERANCIAS_BACKTESTING`
  se mantiene en `pila_mae_pct=5.0` en todos los casos — los tests
  `test_backtesting_*.py` verifican `dentro_tolerancia` calculado
  honestamente contra ese valor, sea el resultado el que sea.
- Ver `eventos_detectados_por_regimen.csv` para el detalle de los 2038
  eventos detectados (calidad de datos por evento incluida).
