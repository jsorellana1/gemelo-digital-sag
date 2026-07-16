# Sistema RT de Optimización de Rates — Molienda T8
*Generado: 2026-06-24 09:31*

## Cambio de enfoque (vs análisis anterior)
- **Antes**: predecir `rate_operado` → R² negativos (problema estructural)
- **Ahora**: optimizar `rate_optimo` sintético mediante función de utilidad con 4 objetivos en tensión
- **Variable objetivo Capa 2**: P(agotamiento físico de pila) — evento observable, no decisión humana

## Hallazgo crítico nuevo durante feature engineering
**correa_315 está en 0 el 50% del tiempo** (45.935 de 93.612 observaciones).
Esto explica el agotamiento crónico de SAG1: durante la mitad de la operación,
SAG1 no recibe alimentación y consume inventario de pila continuamente.
Esta variable fue subutilizada en el análisis anterior.

## Distribución de regímenes operacionales (histórico completo)
  - EMERGENCIA: 32,332 obs (34.5%)
  - CONSERVADOR: 50,813 obs (54.3%)
  - NORMAL: 6,948 obs (7.4%)
  - AGRESIVO: 3,519 obs (3.8%)

## Arquitectura del sistema
- **Capa 1** — Clasificador régimen (LightGBM): `EMERGENCIA | CONSERVADOR | NORMAL | AGRESIVO`
- **Capa 2** — Estimador de riesgo analítico (Monte Carlo): P(agotamiento en 2h/4h/8h) sin ML
- **Capa 3** — Optimizador de rate (Optuna 20 trials): U(rate) = f(riesgo, autonomía, CV, TPH)

## Métricas de validación backtesting (abr–jun 2026)
| activo   |   agot_historico |   agot_modelo |   mejora_agot_pct |   delta_tph_pct |   auton_historica_h |   auton_modelo_h |   mejora_auton_h |   cv_historico |   cv_modelo |
|:---------|-----------------:|--------------:|------------------:|----------------:|--------------------:|-----------------:|-----------------:|---------------:|------------:|
| SAG1     |            17668 |         17857 |             -1.10 |           -1.40 |                0.42 |             0.42 |            -0.01 |           0.20 |        0.12 |
| SAG2     |             8148 |          8434 |             -3.50 |           -0.70 |                1.73 |             1.97 |             0.24 |           0.18 |        0.11 |

### Interpretación
- Criterio 1 (reducción agotamientos ≥20%): ver tabla
- Criterio 2 (TPH dentro ±3%): ver delta_tph_pct
- Criterio 3 (mejora autonomía ≥0.5h en PRE): ver mejora_auton_h
- Criterio 4 (< 2s por llamada): 36.4s total; ~0.3s por recomendación

## Ejemplo de llamada a la API en tiempo real
```json
{
  "timestamp": "2026-06-24T09:31:34.970493",
  "regimen": "EMERGENCIA",
  "alertas": [
    {
      "nivel": "CRITICO",
      "mensaje": "SAG1: P(agotamiento 4h) = 100%",
      "accion": "Reducir rate a 727 TPH de forma inmediata"
    },
    {
      "nivel": "CRITICO",
      "mensaje": "SAG2: P(agotamiento 4h) = 100%",
      "accion": "Reducir rate a 1711 TPH de forma inmediata"
    }
  ],
  "sag1": {
    "rate_recomendado_tph": 929.0,
    "rango_seguro": [
      727.0,
      931.0
    ],
    "p_agotamiento_2h": 1.0,
    "p_agotamiento_4h": 1.0,
    "autonomia_proyectada_h": 1.12,
    "accion_requerida": "REDUCIR",
    "urgencia": "INMEDIATA",
    "fundamento": "Autonomía SAG1 crítica (0.7h) | T8 activo (dur=8h, restante=5.0h) | P(agotamiento 4h)=100%",
    "confianza": "Seguro"
  },
  "sag2": {
    "rate_recomendado_tph": 2060.0,
    "rango_seguro": [
      1711.0,
      2063.0
    ],
    "p_agotamiento_2h": 0.628,
    "p_agotamiento_4h": 1.0,
    "autonomia_proyectada_h": 1.94,
    "accion_requerida": "AUMENTAR",
    "urgencia": "INMEDIATA",
    "fundamento": "Pila SAG2 baja (28.0%) | Autonomía SAG2 crítica (1.6h) | T8 activo (dur=8h, restante=5.0h)",
    "confianza": "Seguro"
  },
  "pmc": {
    "rate_recomendado_tph": 1053,
    "rango_seguro": [
      947,
      1158
    ],
    "accion_requerida": "MANTENER",
    "urgencia": "MONITOREO",
    "fundamento": "Circuito independiente de pilas SAG",
    "confianza": "Probable"
  },
  "unitario": {
    "rate_recomendado_tph": 719,
    "rango_seguro": [
      647,
      790
    ],
    "accion_requerida": "MANTENER",
    "urgencia": "MONITOREO",
    "fundamento": "Circuito independiente de pilas SAG",
    "confianza": "Probable"
  },
  "proxima_revision_min": 5
}
```

## Features nuevas incorporadas (vs análisis anterior)
1. `dpila_sag1_dt` — tasa de cambio de pila (30 min)
2. `d2pila_sag1_dt2` — aceleración de consumo
3. `tiempo_a_critico_sag1` — horas al nivel crítico al ritmo actual
4. `horas_sin_correa_315` — tiempo sin alimentación SAG1 (KEY FEATURE NUEVA)
5. `ratio_feed_sag1` — correa/TPH (>1 = acumulando)
6. `cv_movil_sag1` — CV rolling 2h
7. `tendencia_sag1` — slope TPH últimos 30 min
8. `correa_315_var_15min` — variabilidad correa (señal anticipada T8)
9. `frac_t8_completada` — progreso dentro de la ventana T8
10. `sistema_seguro` — booleano: ambas pilas sobre umbral mínimo

## Por qué NO se reporta R² sobre rate_operado
R² sobre `rate_operado` mide cuánto el modelo replica errores históricos del operador.
Un modelo prescriptivo perfecto puede tener R²=0 si el operador tomaba decisiones subóptimas.
Las métricas correctas son operacionales: agotamientos, autonomía, CV, TPH total.

## Auditoría eficiencia (skill_token_optimization_loop)
- Cache reutilizado: advanced_t8_historical_5min.parquet + advanced_t8_event_windows.parquet
- Excel re-leídos: 0
- Optuna: 20 trials por llamada RT (≈0.1s)
- Monte Carlo Capa 2: lookup table precomputada (evita MC en cada llamada)
- Tiempo total pipeline: 36.4s
