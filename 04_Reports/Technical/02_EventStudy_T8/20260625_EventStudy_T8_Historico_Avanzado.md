# Análisis Avanzado T8 | Histórico ampliado
*Generado: 2026-06-23 15:08*

## Cobertura utilizada
- Serie histórica principal: `tonelaje_v2.xlsx`
- Rango 5-min: **2025-08-01 00:00:00** → **2026-06-21 23:55:00**
- Eventos oficiales reutilizados y recanonizados: **72**
- Eventos con ventana completa analizable (-24h / fin+48h): **70**
- Ventanas oficiales consideradas: 2h=14:00-16:00, 4h=12:00-16:00, 8h=08:00-16:00, 12h=08:00-20:00

## Hallazgos principales
- Activo más vulnerable: **SAG1** con score 56.4.
- Recuperación más lenta: **UNITARIO** con 23.1 h al 90%.
- Mayor impacto por duración: **12h**.

## Elasticidad Pila → TPH
- Quiebres SAG1 estimados: [50.0, 85.0]
- Quiebres SAG2 estimados: [30.0, 60.0]

## Autonomía operacional
- SAG1: media=1.7h | min=0.0h | p10=0.5h | p25=1.1h | %<4h=100.0%
- SAG2: media=2.6h | min=0.0h | p10=0.2h | p25=1.2h | %<4h=76.7%

## Respuestas finales
- **1. ¿Qué activo es más vulnerable?** SAG1
- **2. ¿Qué activo se recupera más lento?** UNITARIO
- **3. ¿Qué duración T8 genera mayor impacto?** 12h
- **4. ¿Existe un nivel crítico de pila?** SAG1 ≈ 50.0% | SAG2 ≈ 30.0%
- **5. ¿Cuál es la autonomía operacional real?** SAG1 media=1.7h, p10=0.5h | SAG2 media=2.6h, p10=0.2h
- **6. ¿Qué porcentaje del tiempo se opera cerca del límite?** SAG1 <4h: 100.0% | SAG2 <4h: 76.7%
- **7. ¿Qué eventos históricos fueron más críticos?** SAG1 | 2026-01-02 | caída 100.0%
- **8. ¿Cuándo debería reducirse carga?** Cuando la autonomía esperada baje de 4h o la pila SAG2 entre bajo el primer quiebre con T8 >=4h.
- **9. ¿Cuándo debería evaluarse una detención preventiva?** Cuando la autonomía proyectada baje de 2h y el árbol marque riesgo alto con pilas bajas y ventana larga.
- **10. ¿Qué KPI deberían incorporarse al CIO y Power BI?** Autonomía SAG1/SAG2, p10 autonomía, % tiempo <4h, riesgo T8, caída promedio por activo, recovery 90%, cluster del evento.

## Reglas operacionales sugeridas
```text
|--- pile_sag2_t0 <= 22.73
|   |--- baseline_tph <= 1986.20
|   |   |--- class: 0
|   |--- baseline_tph >  1986.20
|   |   |--- class: 1
|--- pile_sag2_t0 >  22.73
|   |--- pile_sag1_t0 <= 42.13
|   |   |--- pile_sag1_t0 <= 31.70
|   |   |   |--- class: 0
|   |   |--- pile_sag1_t0 >  31.70
|   |   |   |--- class: 1
|   |--- pile_sag1_t0 >  42.13
|   |   |--- pile_sag1_t0 <= 49.36
|   |   |   |--- class: 0
|   |   |--- pile_sag1_t0 >  49.36
|   |   |   |--- class: 1
```

## Clustering de eventos
|   cluster_id |   eventos |   drop_pct_prom |   drop_pct_max |   rec90_prom_h | categoria   |
|-------------:|----------:|----------------:|---------------:|---------------:|:------------|
|            0 |         8 |           23.95 |          34.18 |          15.24 | Moderadas   |
|            1 |        28 |           70.26 |          98.47 |          22.02 | Críticas    |
|            2 |        23 |           81.55 |          98.63 |          17.62 | Críticas    |
|            3 |         7 |           82.58 |          99.97 |          33.65 | Críticas    |

## Limitaciones reales del dataset
- UNITARIO fue reconstruido parcialmente desde `rendimientos_clean.parquet` y sólo aporta hasta 2026-06-14; eventos con cobertura útil: 26.
- El histórico ampliado comienza el 2025-08-01, pero los eventos T8 oficiales disponibles en PAM reutilizado siguen concentrados en 2026-01 a 2026-06.
- La autonomía es un KPI proxy en horas basado en nivel de pila (%) y tasas históricas calibradas; no reemplaza la capacidad física real en toneladas.

## Auditoría de eficiencia
- Archivos reutilizados: `ventanas_t8.parquet`, `rendimientos_clean.parquet`
- Cache generado: `advanced_t8_historical_5min.parquet`, `advanced_t8_event_windows.parquet`
- Joins evitados: no se releen PAM Producción ni se recalcula la capa diaria legacy.
- Tiempo total de ejecución: 46.2 s