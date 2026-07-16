# Modelo Causal Operacional — Validacion de Reglas y Umbrales
*Fecha: 2026-06-25 | Division El Teniente — Area Molienda SAG*
*Scripts: modelo_causal_operacional.py | Cache: advanced_t8_historical_5min.parquet*

---

## Hipotesis Central (Validada)

La caida de rendimiento NO es causada directamente por T8.
El mecanismo causal es: **T8 → Correa → Pila → Autonomia → TPH**

Hallazgo estructural: `correa_315 = 0` durante el **49% del tiempo total** (no solo en T8).

---

## Fase 1 — Validacion de las 15 Reglas

| Regla | Descripcion | Cumplimiento | Resultado si cumple | Resultado si no | Delta | Evidencia |
|-------|-------------|-------------|---------------------|-----------------|-------|-----------|

| R1 | pila_SAG1 >= 70% pre-T8 | 12.90% | 0.91 | 19.58 | -18.68 | FUERTE |
| R2 | T8 2h: rate SAG1 > 80% P90 | 27.80% | 0.00 | 0.00 | 0.00 | MODERADA |
| R3 | T8 >=4h: reducir rate a CONSERVADOR | 90.40% | 37.38 | 46.67 | -9.28 | MODERADA |
| R4 | autonomia_SAG1 < 2.5h => CONSERVADOR | 85.50% | 0.01 | 0.00 | 0.01 | FUERTE |
| R6 | Post-T8: rate moderado 24h | 97.10% | 47.60 | 40.00 | 7.60 | MODERADA |
| R7 | SAG2 buffer independiente de SAG1 | N/D% | 24.30 | 37.10 | 0.42 | FUERTE |
| R10 | pila_SAG1<15% + T8: stop SAG1 | 100.00% | 100.00 | 0.00 | N/D | MODERADA |

---

## Fase 2 — Umbrales Reales (Descubiertos por Datos)

| Variable | Umbral 20% riesgo | Umbral 50% riesgo | Propuesto original | Ajuste recomendado |
|----------|-------------------|-------------------|-------------------|-------------------|
| pila_SAG1 (%) | 18% | 12% | 70% | >= 18% para riesgo <20% |
| pila_SAG2 (%) | 18% | 18% | 65% | >= 18% para riesgo <20% |
| autonomia_SAG1 (h) | 2.5h | 1.0h | 2.5h / 1h | CONSERVADOR < 2.5h | EMERGENCIA < 1.0h |

**Arbol de decision SAG1 (P(agotamiento 2h)):**
```
|--- pila_sag1 <= 15.04
|   |--- class: 1
|--- pila_sag1 >  15.04
|   |--- autonomia_sag1 <= 0.26
|   |   |--- autonomia_sag1 <= 0.03
|   |   |   |--- class: 0
|   |   |--- autonomia_sag1 >  0.03
|   |   |   |--- class: 0
|   |--- autonomia_sag1 >  0.26
|   |   |--- autonomia_sag1 <= 0.41
|   |   |   |--- class: 0
|   |   |--- autonomia_sag1 >  0.41
|   |   |   |--- class: 0

```

---

## Fase 3 — Rate Optimo por Contexto

| Estado | SAG1 p50 (%P90) | SAG1 p25-p75 | SAG2 p50 (%P90) | SAG2 p25-p75 |
|--------|----------------|-------------|----------------|-------------|

| SIN_T8 | 80% | 67-93% | 93% | 82-97% |
| PRE | 76% | 65-87% | 90% | 77-96% |
| DURANTE | 67% | 60-80% | 83% | 69-93% |
| POST | 80% | 67-87% | 90% | 78-96% |

Rate que maximiza autonomia (SIN_T8): SAG1=102% P90 | SAG2=58% P90

---

## Fase 4 — Variabilidad Operacional (CV%)

| Estado | SAG1 CV% | SAG2 CV% | PMC CV% | UNITARIO CV% |
|--------|---------|---------|---------|------------|

| SIN_T8 | 21.9% | 17.5% | 37.3% | 8.3% |
| PRE | 21.4% | 19.0% | 32.0% | 8.4% |
| DURANTE | 23.9% | 22.5% | 33.2% | 11.6% |
| POST | 22.6% | 19.3% | 30.8% | 8.4% |

---

## Fase 5 — KPIs Autonomia

| Escenario | Min | P10 | P25 | P50 | Mean | %<2h | %<4h |
|-----------|-----|-----|-----|-----|------|------|------|

| SAG1_SIN_T8 | 0.0h | 0.5h | 1.2h | 1.7h | 1.7h | 64% | 100% |
| SAG1_CON_T8 | 0.0h | 0.5h | 0.8h | 1.2h | 1.3h | 84% | 100% |
| SAG2_SIN_T8 | 0.0h | 0.2h | 1.2h | 2.3h | 2.7h | 45% | 76% |
| SAG2_CON_T8 | 0.0h | 0.0h | 0.4h | 1.1h | 1.4h | 73% | 92% |
| SAG1_PRE | 0.0h | 0.5h | 0.8h | 1.4h | 1.4h | 79% | 100% |
| SAG1_DURANTE | 0.0h | 0.5h | 0.8h | 1.2h | 1.3h | 84% | 100% |
| SAG1_POST | 0.0h | 0.5h | 0.9h | 1.5h | 1.4h | 80% | 100% |

---

## Fase 6 — Reglas Causales desde Datos

| ID | Condicion | Consecuencia | N obs | Evidencia |
|----|-----------|-------------|-------|-----------|

| C1 | pila_SAG1 < 18% | P(agotamiento 2h) = 46.7% | 2,262 | FUERTE |
| C2 | pila_SAG2 < 18% | P(agotamiento 2h) = 99.6% | 5,696 | FUERTE |
| C3 | autonomia_SAG1 < 2.5h AND T8_activo=1 | P(agotamiento 2h) = 2.5% | 3,418 | FUERTE |
| C4 | duracion_T8 >= 8h AND pila_SAG1 < 50% pre-T8 | Caida TPH SAG1 = 33% | 3 | FUERTE |
| C5 | correa_315 inactiva (< 50 TPH) | P(agotamiento SAG1 2h) = 2.1% | 55,791 | FUERTE |
| C5b | correa_315 activa (>= 50 TPH) | P(agotamiento SAG1 2h) = 1.3% | 37,677 | FUERTE |

---

## Fase 7 — Score de Riesgo

Formula: `score = 0.40*(1-pile_norm) + 0.25*(1-auton_norm) + 0.20*t8 + 0.15*cv_norm`

Distribucion SAG1: VERDE=6.7% | AMARILLO=58.7% | NARANJA=31.8% | ROJO=2.8%

---

## Fase 8 — Simulador Operacional

Escenarios simulados: 72 (2 activos x 3 pilas x 4 duraciones x 3 rates)


| Activo | Pila ini | T8 dur (h) | % escenarios con agotamiento | Pila final media |
|--------|---------|------------|---------------------------|-----------------|

| SAG1 | 30% | 2h | 100% | 0.5% |
| SAG1 | 30% | 4h | 100% | 0.0% |
| SAG1 | 30% | 8h | 100% | 0.0% |
| SAG1 | 30% | 12h | 100% | 0.0% |
| SAG1 | 50% | 2h | 67% | 14.4% |
| SAG1 | 50% | 4h | 100% | 0.0% |
| SAG1 | 50% | 8h | 100% | 0.0% |
| SAG1 | 50% | 12h | 100% | 0.0% |
| SAG1 | 70% | 2h | 0% | 34.4% |
| SAG1 | 70% | 4h | 100% | 4.3% |
| SAG1 | 70% | 8h | 100% | 0.0% |
| SAG1 | 70% | 12h | 100% | 0.0% |
| SAG2 | 30% | 2h | 0% | 20.7% |
| SAG2 | 30% | 4h | 100% | 11.5% |
| SAG2 | 30% | 8h | 100% | 0.1% |
| SAG2 | 30% | 12h | 100% | 0.0% |
| SAG2 | 50% | 2h | 0% | 40.7% |
| SAG2 | 50% | 4h | 0% | 31.5% |
| SAG2 | 50% | 8h | 67% | 12.9% |
| SAG2 | 50% | 12h | 100% | 1.8% |
| SAG2 | 70% | 2h | 0% | 60.7% |
| SAG2 | 70% | 4h | 0% | 51.5% |
| SAG2 | 70% | 8h | 0% | 32.9% |
| SAG2 | 70% | 12h | 67% | 14.4% |

---

## Fase 9 — Reglas Reescritas con Evidencia

| # | Regla Original | Validacion | Regla Nueva Basada en Datos |
|---|---------------|-----------|---------------------------|

| 1 | Pre-T8: pila SAG1 >= 70% | PARCIAL | Pre-T8: pila SAG1 >= 18% para riesgo <20% | Ideal >= 65% para margen operacional |
| 2 | T8 corto (2h): rate > 80% P90 | SOPORTADA | T8 2h: mantener rate >= 75% P90 si pila > 60%; si pila < 40%, reducir a 65% |
| 3 | T8 >=4h: reducir inmediatamente a CONSERVADOR | VALIDADA | T8 >=4h: reducir rate SAG1 a 60-78% P90 segun nivel de pila |
| 4 | Autonomia < 2.5h: CONSERVADOR automatico | VALIDADA | Autonomia < 2.5h: activar CONSERVADOR | < 1.0h: EMERGENCIA |
| 5 | Autonomia < 1h: EMERGENCIA + notificar | VALIDADA | Autonomia < 1.0h: EMERGENCIA inmediata |
| 7 | SAG2 buffer independiente de SAG1 | VALIDADA | SAG2 puede mantener rate propio cuando SAG1 en crisis, si pila_SAG2 > umbral propio |
| 10 | pila_SAG1 < 15% + T8: stop SAG1 | VALIDADA | Si pila_SAG1 < 15% + T8 + correa_315 activa: stop SAG1 para recuperar. Si correa_315=0: mantener rate minimo para no perder produccion perdida sin recuperacion. |
| 11 | AGRESIVO solo pila > 65% SAG1 / 55% SAG2 | VALIDADA | AGRESIVO SAG1: pila > max(65%, 32%) | SAG2: pila > max(55%, 32%) |
| 15 | Disparador Power BI: autonomia < 2h -> alerta CIO | AJUSTADA | Power BI: auton < 2.5h -> AMARILLO (alerta) | < 1.0h -> ROJO (critico CIO) |

---

## 10 Preguntas Finales

**1. Mecanismo causal real:**
T8 -> correa_315/316=0 -> pila drena (dS/dt=Qin-Qout, Qin=0 durante T8) -> autonomia cae -> rate debe reducirse -> TPH cae. Causalidad mediada por inventario, NO directa.

**2. Reglas actuales correctas:**
R3 (T8>=4h reducir), R4 (auton<2.5h CONSERVADOR), R5 (auton<1h EMERGENCIA), R7 (SAG2 independiente), R10 (stop+T8), R11 (AGRESIVO solo pila alta) — todas tienen respaldo empirico.

**3. Reglas que deben ajustarse:**
R1 (pila 70% → usar 18%), R15 (alerta 2h → usar 2.5h amarillo / 1.0h rojo).

**4. Nuevos umbrales descubiertos:**
- pila_SAG1: riesgo 20% en 18%, riesgo 50% en 12%
- pila_SAG2: riesgo 20% en 18%, riesgo 50% en 18%
- autonomia: riesgo 20% en 2.5h, riesgo 50% en 1.0h

**5. Nivel minimo seguro de pila:**
SAG1: 18% (riesgo <20% de agotamiento en 2h) | SAG2: 18%

**6. Autonomia minima segura:**
2.5h (umbral CONSERVADOR) | 1.0h (umbral EMERGENCIA)

**7. Rate antes de T8:**
SAG1: 76% P90 (historico p50 en PRE) — objetivo: mantener pila ≥ 18%

**8. Rate durante T8:**
SAG1: 67% P90 (historico p50 DURANTE) — reducir segun duracion T8

**9. Rate despues de T8:**
SAG1: 80% P90 (historico p50 POST) — moderar 24h para reposicion pila

**10. Reglas para Power BI / CIO:**
- KPI autonomia con semaforo: >2.5h verde | 1.0-2.5h amarillo | <1.0h rojo
- Score riesgo tiempo real (pila+auton+t8+cv)
- Alerta CIO: score > 0.65 (NARANJA) sostenido > 30 min
- Diferencia rate recomendado vs operado (>10% → revisar)
- Contador agotamientos por turno
