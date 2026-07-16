# Skill: Especialista en Confiabilidad y Mantenimiento Predictivo — Contexto SAG

## Propósito

Guiar el diseño de modelos predictivos y la interpretación de resultados operacionales para
equipos críticos del proceso SAG (Molienda, Chancado, Correas) en el contexto del pipeline FRAG SAG.

---

# Principios

## Regla 1 — El RC define el modo de falla

Cada Riesgo Crítico (RC) en el catálogo corresponde a un modo de falla o escenario de accidente
con consecuencias graves. La clasificación RC del evento AT determina su contribución al FRAG.

```
RC04 = Atrapamiento LOTO    → eventos de mantención sin bloqueo
RC09 = Caída de objetos     → trabajos en altura / izaje
RC03 = Izaje sin control    → maniobras de grúa
```

## Regla 2 — Ventana temporal importa para mantenimiento

Los eventos AT relacionados a mantenimiento tienen estacionalidad:
- Picos en turno noche y fines de semana (RC22 fatiga)
- Picos en paradas programadas (RC04 LOTO, RC03 izaje)
- Ventana de 8 semanas captura 2 ciclos de mantención mayor típicos

## Regla 3 — Un evento precursor vale más que un accidente

Los hallazgos SOMS (casi-accidentes, condiciones inseguras) son señal temprana.
El peso α=0.15 en FRAG refleja que son señal, no evento consumado.
Si un RC tiene muchos SOMS y pocos AT → deterioro emergente = señal preventiva.

## Regla 4 — Confiabilidad es sistema, no equipo aislado

El FRAG integra riesgo de RC-AT considerando el sistema completo SAG:
- Molino SAG, Molinos de bolas, Chancadores, Correas, Sistemas auxiliares
- Un RC con alta lambda en correas puede bloquear toda la planta
- Priorizar RC con alta lambda Y alta consecuencia (lethality)

---

# RC Catalog — Mapeo Operacional SAG

| RC | Nombre | Equipos SAG asociados | Señal predictiva típica |
|----|--------|-----------------------|------------------------|
| RC01 | Caída al mismo nivel | Pisos correas, pasarelas molino | Limpieza insuficiente, agua/lodo |
| RC02 | Caída en altura | Plataformas, andamios, escaleras | Condiciones clima, prisa turno |
| RC03 | Izaje descontrolado | Grúas, tecles, aparejos | Rigging sin rigger designado |
| RC04 | Atrapamiento LOTO | Todos los equipos rotativos | Bloqueos no aplicados |
| RC06 | Energía no controlada | Correas transportadoras | Limpieza con equipo en marcha |
| RC09 | Caída de objetos | Molino SAG (liners), andamios | Orden y aseo deficiente |
| RC10 | Colisión vehículos | Caminos internos planta | Tráfico mixto, visibilidad |
| RC22 | Fatiga operacional | Equipos de transporte, grúas | Turno extendido, noche |
| RC25 | Temperatura extrema | Sala proceso, exterior | Verano, ventilación, EPP |

## Umbrales operacionales de lambda AT

```
lambda_at <= 0.05 ev/sem → BAJO   (< 1 evento cada 20 semanas)
0.05 < lambda_at <= 0.20  → MEDIO  (1 evento cada 5-20 semanas)
0.20 < lambda_at <= 0.50  → ALTO   (1-2 eventos cada 5 semanas)
lambda_at > 0.50           → CRITICO (> 2 eventos en 4 semanas)
```

---

# Integración con el Pipeline FRAG SAG

## Análisis de contribución RC

En `performance_metrics._model_stats()`:
```python
# FRA-RC Raw = probabilidad semanal de accidente tipo RC
fra_rc_raw = getattr(scoring, "fra_rc_raw", {})
# Lambda AT = tasa de ocurrencia AT en ventana
lambda_at = getattr(scoring, "lambda_at", {})
```

Un RC con `fra_rc_raw >= 0.15` se clasifica como "crítico" en el snapshot.
Umbral configurable en `anomaly_detector.run()`.

## Plan de rondas — PAM

El módulo PAM (`src/models/pam_strategy.py`) genera puntos de supervisión prioritarios
combinando:
- Lambda AT del RC
- Hallazgos SOMS recientes (RC-SOMS matching)
- Nivel histórico del RC (categorizer)
- Actividades de mantención programadas (MIPER)

Las rondas deben cubrir primero los RC con `fra_rc_raw` más alto.

## MIPER como prior estructural

El MIPER contiene programación de actividades de mantención mayor:
- Si hay actividad MIPER en RC04 esta semana → prior de riesgo LOTO elevado
- El prior MIPER se integra como factor multiplicativo en el forecasting
- Ver `src/models/apply_n1.py` y `src/models/miper_loader.py`

## Detección de anomalías en mantenimiento

`anomaly_detector.py` usa IsolationForest sobre `[frag, n_at, n_soms, n_n1, n_rc_criticos]`.
Una semana anómala puede indicar:
- Parada no programada (spike en AT)
- Evento mayor de mantención (spike en n_n1)
- Sub-reporte (todos los valores súbitamente bajos)

---

# FMEA Simplificado para RC SAG

| RC | Severidad (S) | Ocurrencia (O) | Detección (D) | RPN = S×O×D |
|----|--------------|----------------|---------------|------------|
| RC04 LOTO | 9 | 6 | 5 | 270 |
| RC03 Izaje | 9 | 4 | 6 | 216 |
| RC02 Altura | 8 | 5 | 5 | 200 |
| RC09 Obj caída | 7 | 6 | 4 | 168 |
| RC01 Nivel | 5 | 8 | 3 | 120 |
| RC22 Fatiga | 8 | 3 | 7 | 168 |

RPN > 200 → control crítico a verificar en rondas prioritarias.

---

# Anti-patrones

- **No** inferir causalidad de correlación lambda AT / SOMS sin contexto operacional
- **No** ignorar el contexto de turno en AT (noche vs. día, fines de semana)
- **No** usar FRAG como KPI único — siempre acompañar con n_at, n_soms, RC dominante
- **No** recomendar acción sin verificar si el RC corresponde al área SAG o es de otra planta
