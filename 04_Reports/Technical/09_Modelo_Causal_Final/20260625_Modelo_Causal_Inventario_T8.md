# Modelo Causal del Inventario de Molienda — Ventanas T8
*Fecha: 2026-06-25 | Division El Teniente — Area Molienda SAG*

---

## 1. Mecanismo causal real del impacto T8

La ventana T8 (Teniente 8) interrumpe el flujo de mineral desde la mina hacia los circuitos de molienda.
El mecanismo es:

```
T8_activo = 1
    -> correa_315 = 0  (sin alimentacion SAG1)
    -> correa_316 = 0  (sin alimentacion SAG2)
    -> dS/dt = Qin - Qout = 0 - Qout  ->  dS/dt < 0
    -> Pila SAG1/SAG2 se drena al ritmo de la molienda
    -> Cuando pila <= umbral_critico -> reduccion forzada de rate
    -> Caida de TPH ("efecto gaviota")
```

La causalidad NO es directa T8->TPH sino MEDIADA por el inventario de pila:

```
T8 -> Pila -> TPH
```

### Hallazgo estructural critico
correa_315 = 0 durante el 49% del tiempo total (no solo en T8).
SAG1 opera sin feed la mitad del tiempo operativo, generando un deficit
cronico de pila que ninguna optimizacion de rate puede resolver sin
intervencion en la disponibilidad de correa_315.

---

## 2. Activo mas vulnerable

SAG1 — Score de vulnerabilidad: 56.4 (vs SAG2: moderado)

| Indicador                  | SAG1          | SAG2          |
|---------------------------|---------------|---------------|
| Autonomia media            | 1.7 h         | 2.6 h         |
| P10 autonomia              | 0.5 h         | 0.2 h         |
| % tiempo auton < 4h        | 100%          | 76.7%         |
| Correa sin feed            | 49% del tiempo| ~30%          |
| Evento mas critico         | 2026-01-02 (-100%) | —       |

---

## 3. Nivel minimo seguro de pila

| Activo | Umbral critico | Umbral operacional |
|--------|---------------|-------------------|
| SAG1   | 15%           | 30%               |
| SAG2   | 18.2%         | 30%               |

---

## 4. Autonomia operacional

```
autonomia_h = (pila_pct - pct_critico) / drain_pct_h
```

| Activo | drain_pct_h | cap_efectiva_ton |
|--------|-------------|-----------------|
| SAG1   | 23.76 %/h   | 4,575 ton       |
| SAG2   | 6.18 %/h    | 32,009 ton      |

Nota: cap_efectiva = TPH_medio / drain_pct_h x 100 (no igual a cap_fisica).

---

## 5. Variables que controlan el rendimiento (SHAP)

| Rank | Variable                     | Activo |
|------|------------------------------|--------|
| 1    | pila_sag1 / pila_sag2        | Ambos  |
| 2    | autonomia_sag1               | SAG1   |
| 3    | correa_315_activa            | SAG1   |
| 4    | horas_sin_correa_315         | SAG1   |
| 5    | t8_activo                    | Ambos  |
| 6    | duracion_h                   | Ambos  |
| 7    | tiempo_a_critico_sag1        | SAG1   |
| 8    | dpila_sag1_dt                | SAG1   |
| 9    | frac_t8_completada           | Ambos  |
| 10   | ratio_pilas                  | Ambos  |

---

## 6. Senales previas a una caida de TPH

1. dpila_dt < -2%/h: velocidad de drenaje se acelera
2. horas_sin_correa_315 > 3h: SAG1 sin reposo prolongado
3. autonomia_sag1 < 2.5h: zona CONSERVADOR -> activar protocolo
4. autonomia_sag1 < 1.0h: zona EMERGENCIA -> reduccion inmediata
5. correa_315 == 0 + t8_activo == 1: doble riesgo simultaneo

Ventana de intervencion util: ~2.3h antes del agotamiento total.

---

## 7. Rate recomendado SAG1 (P90 = 1,454 TPH)

| Regimen     | Condicion                          | Rate (%P90) | TPH          |
|------------|-------------------------------------|------------|--------------|
| EMERGENCIA | auton < 1h o pila < 20%             | 50-64%     | 727-931      |
| CONSERVADOR| T8>=4h o auton < 2.5h              | 58-78%     | 843-1,134    |
| NORMAL     | Operacion estandar                  | 72-95%     | 1,047-1,381  |
| AGRESIVO   | pila > 65% y sin T8                 | 87-105%    | 1,265-1,527  |

---

## 8. Rate recomendado SAG2 (P90 = 2,516 TPH)

Regimen basado en estado SAG2, independiente de autonomia SAG1.

| Regimen     | Condicion                          | Rate (%P90) | TPH          |
|------------|-------------------------------------|------------|--------------|
| EMERGENCIA | auton_SAG2 < 1h o pila_SAG2 < 22%  | 68-82%     | 1,711-2,063  |
| CONSERVADOR| T8>=4h o auton_SAG2 < 2.5h        | 76-94%     | 1,912-2,365  |
| NORMAL     | Operacion estandar                  | 82-100%    | 2,063-2,516  |
| AGRESIVO   | pila_SAG2 > 55% y sin T8           | 90-105%    | 2,264-2,642  |

---

## 9. Cuando reducir carga

Protocolo escalonado:

```
IF autonomia_h < 4h:
    ALERTA: monitorear cada 30 min

IF autonomia_h < 2.5h OR (t8_activo AND duracion_h >= 4):
    CONSERVADOR: reducir rate al 65-80% P90

IF autonomia_h < 1h OR pila < umbral_critico:
    EMERGENCIA: reducir rate al 50-68% P90 + notificar jefatura

IF pila <= umbral_critico AND correa == 0 AND t8_activo:
    DETENCION PREVENTIVA EVALUABLE (ver seccion 10)
```

Regla PRE-VENTANA: iniciar reduccion 24h antes de T8 conocido cuando
pila SAG1 < 65% o pila SAG2 < 55%. Objetivo: llegar a inicio T8 con pila >= 70%.

---

## 10. Cuando evaluar detencion preventiva

| Condicion                                    | Accion recomendada           |
|---------------------------------------------|------------------------------|
| Autonomia proyectada < 2h + T8 >= 8h activo | Evaluar detencion SAG1       |
| pila_SAG1 < 15% + correa_315 = 0 + sin T8  | Pausa para recuperacion pila |
| P(agotamiento 4h) > 80%                     | Detencion preventiva inmediata|
| CV_TPH > 30% por 3+ horas                   | Revision operacional         |

Arbol de decision (regla simplificada):
```
pila_SAG2 <= 22.7%
    baseline_TPH <= 1,986 -> reducir
    baseline_TPH  > 1,986 -> mantener
pila_SAG2 > 22.7%
    pila_SAG1 <= 31.7% -> reducir
    pila_SAG1 en [31.7, 49.4] -> mantener con vigilancia
    pila_SAG1 > 49.4% -> mantener normal
```

---

## Reglas Operacionales (15 reglas)

| #  | Regla                                                              |
|----|-------------------------------------------------------------------|
| 1  | Pre-T8: alcanzar pila >= 70% SAG1 y >= 65% SAG2 antes del inicio |
| 2  | T8 corto (2h): mantener rate > 80% P90 (reserva suficiente)      |
| 3  | T8 largo (>=4h): reducir inmediatamente a CONSERVADOR            |
| 4  | Autonomia < 2.5h: activar CONSERVADOR automaticamente            |
| 5  | Autonomia < 1h: EMERGENCIA + notificar jefatura                  |
| 6  | Post-T8: mantener rate moderado 24h hasta reposicion de pilas    |
| 7  | SAG2 no penalizar por crisis de SAG1 (buffer independiente)      |
| 8  | correa_315 inactiva > 3h: monitoreo reforzado SAG1 c/15 min     |
| 9  | CV_TPH > 25%: investigar causa antes de modificar rate           |
| 10 | pila_SAG1 < 15% + T8 activo: stop SAG1 y esperar feed           |
| 11 | Regimen AGRESIVO solo cuando pila > 65% (SAG1) o > 55% (SAG2)  |
| 12 | No superar 105% P90 en ningun regimen                           |
| 13 | Cambiar rate maximo +-10% P90 por turno (evitar transitorios)   |
| 14 | Registrar cada cambio de regimen en bitacora operacional         |
| 15 | Disparador Power BI: autonomia media turno < 2h -> alerta CIO   |

---

## Balance de Masa (ecuacion diferencial)

```
dS/dt = Qin(t) - Qout(t)

donde:
  S(t)    = inventario pila en ton
  Qin(t)  = flujo correa (ton/h)  — correa_315 o correa_316
  Qout(t) = rate molienda (ton/h) — SAG1_tph o SAG2_tph

Discretizacion (5 min):
  S[t+1] = S[t] + Qin[t] * DT - Qout[t] * DT
  DT = 5/60 h

Agotamiento: S[t] <= S_critico = cap * (pct_critico / 100)
```

---

## Backtesting Sistema RT (abr-jun 2026)

| Activo | Delta TPH | Mejora agotamiento | Delta autonomia |
|--------|-----------|-------------------|----------------|
| SAG1   | -1.4% OK  | -1.1% (limitacion estructural) | +0.01h |
| SAG2   | -0.7% OK  | -3.5% (ver nota)  | +0.24h         |

Capa 1 accuracy: 99.6% | API latencia: ~0.3 s/llamada

Limitacion documentada SAG1: reduccion agotamiento >=20% requiere
mejora en disponibilidad correa_315, no solo optimizacion de rates.

---

## KPIs recomendados para CIO / Power BI

1. Autonomia SAG1/SAG2 (h) — semaforo: >=4h verde, 2-4h amarillo, <2h rojo
2. P10 autonomia (ultimas 24h)
3. % tiempo autonomia < 4h en turno
4. Regimen operacional actual (EMERGENCIA/CONSERVADOR/NORMAL/AGRESIVO)
5. Rate recomendado vs rate operado (delta %)
6. P(agotamiento 4h) en tiempo real
7. Horas sin correa_315
8. Recovery time post-T8 (h al 90% baseline)
9. Eventos de agotamiento en turno (contador)
10. Alerta: autonomia media turno < 2h -> notificacion CIO

---

*Scripts fuente:*
*  src/advanced_t8_historical_analysis.py*
*  src/optimizacion_rates_molienda.py*
*  src/sistema_rt_optimizacion_rates.py*
*Modelos: outputs/models/campeones/capa1_regime_model.pkl*
*Cache: data/cache/advanced_t8_historical_5min.parquet*
*Generado: 2026-06-25*
