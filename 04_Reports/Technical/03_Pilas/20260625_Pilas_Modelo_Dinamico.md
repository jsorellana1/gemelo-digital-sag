# Reporte: Modelo Dinamico Simple de Pilas SAG

**Proyecto:** Rendimientos Molienda — Division El Teniente, Codelco
**Fecha:** 2026-06-18
**Modelo:** Balance de masa ODE: dS/dt = Qin - Qout

---

## 1. Ecuaciones del modelo

### Escenario A — Operacion normal (sin ventana T8)
```
dS_i/dt = Qin_i(t) - Qout_i(t)
```
La pila es aproximadamente estable: Qin ~ Qout (equilibrio operacional).

### Escenario B — Ventana T8 activa (Qin = 0)
```
dS_i/dt = -rate_i   [%/h]
rate_i = TPH_SAG_i / Cap_i * 100
```

---

## 2. Parametros calibrados

| Parametro | SAG1 | SAG2 |
|-----------|------|------|
| Capacidad pila (ton) | 38,685 | 98,401 |
| Tasa P25 (%/h) | 2.393 | 1.975 |
| Tasa P50 (%/h) | 2.776 | 2.270 |
| Tasa P75 (%/h) | 3.286 | 2.465 |
| Tasa P90 (%/h) | 3.529 | 2.518 |
| TPH P50 (base) | 1074 | 2234 |

---

## 3. Zonas operacionales

| Zona | SAG1 | SAG2 |
|------|------|------|
| Verde (operacion normal) | > 60% | > 48% |
| Amarillo (monitoreo) | 30% - 60% | 40% - 48% |
| Naranja (reducir carga) | 26% - 30% | 18% - 40% |
| Rojo (evaluar detencion) | < 26% | < 18% |

---

## 4. Respuestas a preguntas operacionales (P50)

### Q1. Cuanto consume la pila por hora durante una ventana T8?
- **SAG1:** 2.776%/h (equivalente a 1074 TPH, Cap=38,685 ton)
- **SAG2:** 2.270%/h (equivalente a 2234 TPH, Cap=98,401 ton)

### Q2. Desde 100%, cuando llega la pila a nivel critico?
- **SAG1:** 21.6h hasta 40% | 28.8h hasta 20%
- **SAG2:** 26.4h hasta 40% | 35.2h hasta 20%

### Q3. Nivel minimo recomendado antes de ventana T8 (para terminar en >= 20%)
| Duracion | SAG1 | SAG2 |
|----------|------|------|
| 2h | 26% | 25% |
| 4h | 31% | 29% |
| 8h | 42% | 38% |
| 12h | 53% | 47% |

### Q4. Autonomia total desde 100% (hasta vaciarse)
- **SAG1 P50:** 36.0h | P75: 30.4h | P90: 28.3h
- **SAG2 P50:** 44.1h | P75: 40.6h | P90: 39.7h

### Q5. Cuando reducir tasa SAG?
- **SAG1:** Al caer bajo 30% (Zona Amarillo) — comenzar reduccion gradual
- **SAG2:** Al caer bajo 40% (Zona Amarillo)

### Q6. Cuando evaluar detencion SAG?
- **SAG1:** Al caer bajo 26% (Zona Roja)
- **SAG2:** Al caer bajo 18% (Zona Roja)

### Q7. Inventario minimo para absorber ventana de 12h sin entrar a Zona Roja?
- **SAG1:** >= 60% (= Rojo + consumo 12h P50)
- **SAG2:** >= 45%

### Q8. Diferencia entre SAG1 y SAG2 en autonomia?
- SAG1 tiene menor capacidad (38,685 ton) pero similar tasa porcentual.
- SAG2 mayor capacidad (98,401 ton) con tasa porcentual menor.
- Autonomia comparable (SAG1 P50: 36.0h vs SAG2 P50: 44.1h desde 100%).

### Q9. Impacto de variabilidad de carga (P25 vs P90)?
- **SAG1:** P25 consume 2.393%/h vs P90 3.529%/h (factor 1.5x)
- **SAG2:** P25 consume 1.975%/h vs P90 2.518%/h (factor 1.3x)

### Q10. Tiempo de recuperacion estimado post-ventana?
- Depende de la tasa de llenado (CV315/CV316). No modelado en Escenario A (requiere datos de alimentacion total).
- Referencia: CV315 nominal 588 TPH contribuye 1.52%/h a SAG1.
- Referencia: CV316 nominal 1898 TPH contribuye 1.93%/h a SAG2.

---

## 5. Figuras generadas

| Figura | Nombre | Contenido |
|--------|--------|-----------|
| 01 | 01_balance_pila_sag1_sin_ventana.png | Balance historico SAG1 + CV315 |
| 02 | 02_balance_pila_sag2_sin_ventana.png | Balance historico SAG2 + CV316 |
| 03 | 03_deplecion_pila_sag1_ventana_t8.png | Curvas deplecion SAG1 por duracion ventana |
| 04 | 04_deplecion_pila_sag2_ventana_t8.png | Curvas deplecion SAG2 por duracion ventana |
| 05 | 05_autonomia_por_nivel_inicial_sag1.png | Autonomia SAG1 por nivel inicial |
| 06 | 06_autonomia_por_nivel_inicial_sag2.png | Autonomia SAG2 por nivel inicial |
| 07 | 07_matriz_riesgo_sag1.png | Heatmap nivel final SAG1 (nivel x duracion) |
| 08 | 08_matriz_riesgo_sag2.png | Heatmap nivel final SAG2 (nivel x duracion) |
| 09 | 09_umbral_critico_pila_sag1.png | Inventario minimo pre-ventana SAG1 |
| 10 | 10_umbral_critico_pila_sag2.png | Inventario minimo pre-ventana SAG2 |

---

## 6. Limitaciones del modelo

1. **Capacidad calibrada con Michaelis-Menten:** Las capacidades (38,685 y 98,401 ton) provienen de la calibracion ODE de Fase 8, con RMSE de 22% y 10%.
2. **CV315/CV316 son alimentacion parcial:** Solo capturan contribucion de T8. No representan toda la alimentacion de las pilas SAG.
3. **Modelo lineal:** La tasa de consumo se asume constante. En operacion real varia con el nivel de pila (modelado en Fase 8 con Michaelis-Menten).
4. **Sin recuperacion:** El modelo Escenario B no incluye reposicion post-ventana.
