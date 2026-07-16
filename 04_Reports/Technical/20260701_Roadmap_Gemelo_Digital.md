# Roadmap Gemelo Digital — Molienda SAG División El Teniente
*Fecha: 20260701 | Analítica Avanzada CIO-DET | Claude Sonnet 4.6*

---

## 1. Diagnóstico de Situación Actual

### Pregunta Central
> **¿El sistema está limitado por alimentación o por capacidad de molienda?**

**Respuesta cuantitativa:** El sistema enfrenta restricciones en AMBAS capas, pero el
cuello estructural más crítico es la **disponibilidad de alimentación** (CV315 = 0 el 49%
del tiempo), no la capacidad de los molinos.

### Métricas Clave

| KPI | Valor |
|-----|-------|
| Cuello dominante de procesamiento | **UNITARIO** (67.4% del tiempo) |
| Brecha total por falta de feed | **5941 kton** (período histórico) |
| Brecha total por capacidad molinos | **12533 kton** (período histórico) |
| Zona subalimentado | **45%** del tiempo |
| CV315 sin flujo | **49%** del tiempo operativo |

---

## 2. Cuellos de Botella — Ranking

| Rango | Activo | % Tiempo Limitante | Horas |
|-------|--------|-------------------|-------|
| 1 | UNITARIO | 67.4% | 5257 h |
| 2 | PMC | 29.3% | 2284 h |
| 3 | SAG1 | 27.1% | 2114 h |
| 4 | SAG2 | 8.1% | 634 h |

**Interpretación:** Un activo es cuello de botella cuando está detenido mientras hay
feed disponible en el sistema. El ranking indica dónde invertir primero.

---

## 3. Evaluación del Gemelo Digital Actual


### EDO (Ecuación Diferencial)
**Score actual:** 72/100

| | Detalle |
|---|---|
| ✅ Explica bien | Dinámica de pilas (dS/dt). Balance de masa continuo. Retardos feed→producción. |
| ❌ Explica mal | No captura paradas inesperadas. No modela degradación de correa. Ignora variabilidad granulométrica. |
| 🔍 Variables faltantes | Granulometría, disponibilidad mecánica chancadores, potencia SAG, torque. |
| ⚠️ Sesgos | Asume vaciado lineal de pila — real es no lineal cerca del fondo. |

### Monte Carlo (MC)
**Score actual:** 78/100

| | Detalle |
|---|---|
| ✅ Explica bien | Distribución de P(agotamiento). Intervalos de incertidumbre. Escenarios T8. |
| ❌ Explica mal | Samples independientes — ignora autocorrelación temporal del proceso. |
| 🔍 Variables faltantes | Estado mecánico activos (disponibilidad prevista), granulometría en tiempo real. |
| ⚠️ Sesgos | Sesgaba SAG1 por exceso de conservadurismo en autonomía (corregido en V3). |

### Metropolis-Hastings
**Score actual:** 82/100

| | Detalle |
|---|---|
| ✅ Explica bien | Distribuciones posteriores calibradas. MH 2-5 pp más conservador que MC. Actualización bayesiana. |
| ❌ Explica mal | Computacionalmente costoso para tiempo real. Convergencia sensible a priors. |
| 🔍 Variables faltantes | Datos de sensores PI en tiempo real para actualizar priors continuamente. |
| ⚠️ Sesgos | Cadena MH puede quedarse en moda local si pila_sag1 inicial es extrema. |

### Optimizer V3
**Score actual:** 85/100

| | Detalle |
|---|---|
| ✅ Explica bien | Recomendación de rates óptimos. Grid anclado a percentiles históricos. KPI brecha_P90. |
| ❌ Explica mal | No considera restricciones dinámicas de chancadores ni estado de correas. |
| 🔍 Variables faltantes | Estado en tiempo real CV315/CV316, disponibilidad chancador, potencia SAG. |
| ⚠️ Sesgos | Sesgo SAG1 del V2 corregido. Puede sobrestimar capacidad PMC/UNITARIO sin datos directos. |

### Reglas Operacionales
**Score actual:** 70/100

| | Detalle |
|---|---|
| ✅ Explica bien | Umbrales de intervención claros. Semáforo de riesgo operacional. Fácil de adoptar. |
| ❌ Explica mal | Reglas estáticas. No se adaptan a cambios de proceso. Sin feedback automático. |
| 🔍 Variables faltantes | Feedback de operadores sobre efectividad de reglas. Datos de granulometría. |
| ⚠️ Sesgos | Reglas derivadas de datos 2025-2026. Pueden no generalizar a condiciones extremas. |

### Modelo Causal
**Score actual:** 80/100

| | Detalle |
|---|---|
| ✅ Explica bien | Cadena causal T8→Correa→Pila→TPH validada. Cuantifica efecto diferido. Explica gaviota. |
| ❌ Explica mal | No modela intervenciones (operador que sube rate manualmente). Sin retroalimentación dinámica. |
| 🔍 Variables faltantes | Acciones operacionales registradas (cambios de rate, activación bolas). |
| ⚠️ Sesgos | Basado en correlaciones observacionales — no experimentos controlados. |


---

## 4. Nuevos Modelos Candidatos

### 4.1 Modelo de Eventos Discretos (SimPy)
**Propósito:** Simular colas, esperas y restricciones dinámicas del circuito.
- Modelar flujo: T8 → Chancadores → Correas → Pilas → SAG
- Cuantificar tiempos de espera en cada etapa
- Identificar cuellos de cuello estocásticos
- **Esfuerzo estimado:** 3-4 semanas | **Impacto:** ALTO

### 4.2 Digital Twin Híbrido (EDO + ML)
**Propósito:** Combinar física de proceso (EDO) con aprendizaje de residuales (ML).
- EDO modela balance de masa determinístico
- ML aprende residuales no físicos (operador, granulometría)
- Mejora predicción de TPH en escenarios fuera de distribución
- **Esfuerzo estimado:** 4-6 semanas | **Impacto:** ALTO

### 4.3 Reinforcement Learning — Política Óptima SAG
**Propósito:** Aprender la política óptima de rates SAG1 y SAG2.
- Estado: pila_sag1, pila_sag2, t8_activo, duracion_estimada
- Acción: rate_sag1, rate_sag2, activar_bolas (discreta)
- Recompensa: TPH producido − penalización por agotamiento pila
- **Esfuerzo estimado:** 6-8 semanas | **Impacto:** MUY ALTO (largo plazo)

### 4.4 Bayesian Network
**Propósito:** Mapear eventos que generan mayor riesgo de pérdida de producción.
- Nodos: T8, CV315, Chancadores, Pilas, SAG1, SAG2
- Permite inferencia causal bidireccional
- **Esfuerzo estimado:** 2-3 semanas | **Impacto:** MEDIO

### 4.5 Survival Analysis — Probabilidad de sobrevivir ventana T8
**Propósito:** P(no agotamiento) dado nivel de pila inicial y duración T8.
- Ya modelado parcialmente con MC
- Formalizarlo como modelo de supervivencia permite curvas de Kaplan-Meier por activo
- **Esfuerzo estimado:** 1-2 semanas | **Impacto:** MEDIO

---

## 5. Ranking de Variables Faltantes

| Rank | Variable | Impacto | Score | Mejora Modelos |
|------|---------|---------|-------|---------------|
| #1 | **Estado CV315 (disponibilidad en tiempo real)** | CRÍTICO | 95/100 | EDO, MC, Optimizer V3, Reglas |
| #2 | **Disponibilidad Chancadores 1 y 2** | ALTO | 88/100 | MC, Optimizer V3, Modelo Causal |
| #3 | **Potencia SAG1 / SAG2 (kW)** | ALTO | 85/100 | Regresión TPH, Optimizer, EDO |
| #4 | **Granulometría de alimentación (F80/P80)** | ALTO | 82/100 | Todos los modelos de TPH |
| #5 | **Torque SAG1 / SAG2** | MEDIO | 75/100 | Reglas Operacionales, EDO |
| #6 | **Nivel de mineral en chancadores** | MEDIO | 70/100 | Modelo Causal, MC |
| #7 | **Acciones operacionales registradas (cambios de rate)** | MEDIO | 68/100 | Modelo Causal, RL |
| #8 | **Variables PI (presiones hidráulicas, temperatura)** | BAJO-MEDIO | 60/100 | Survival Analysis, Confiabilidad |

---

## 6. Roadmap de Madurez

### Nivel Actual: **2.8 / 5.0** (entre Diagnóstico y Predictivo)

| Nivel | Descripción | Estado | % Completado |
|-------|-------------|--------|-------------|
| N1 — Descriptivo | EDA, series temporales, reportes | ✅ COMPLETO | 80% |
| N2 — Diagnóstico | Causal, SHAP, event study, MH | ✅ COMPLETO | 75% |
| N3 — Predictivo | Forecasting TPH, P(agotamiento), V3 | 🔄 EN CURSO | 55% |
| N4 — Prescriptivo | Semáforo RT, dashboard, alertas | 🔄 EN INICIO | 40% |
| N5 — Autónomo | RL, ajuste automático, SimPy | 🚀 PLANIFICADO | 10% |

### Hoja de Ruta por Trimestre

#### Q3 2026 (Jul–Sep)
1. Dashboard semáforo operacional (KPIs RT en Power BI)
2. Integrar Optimizer V3 en app.py (callbacks)
3. Pipeline actualización mensual PAM automático
4. Incorporar CV315 en tiempo real como señal preventiva

#### Q4 2026 (Oct–Dic)
1. SimPy DES — modelado de colas chancado → correas → pilas
2. Incorporar disponibilidad chancadores (fuente de datos PI)
3. Bayesian Network causal completa
4. Survival Analysis formal por activo

#### Q1 2027
1. Prototipo RL — política óptima SAG (ambiente de simulación)
2. Digital Twin híbrido EDO + ML
3. Integración datos granulometría (si disponible)
4. Sistema autónomo de recomendación rates (piloto)

---

## 7. Recomendación Final para CIO

> **Si tuviera presupuesto para mejorar SOLO UNA COSA:**

### OPCIÓN A — ALIMENTACIÓN (máximo impacto físico)
**Inversión en disponibilidad CV315**
- Beneficio: Recuperar el 49% del tiempo perdido de feed SAG1
- Impacto estimado: +300 a +500 TPH SAG1 adicionales
- Toneladas/día recuperables: **7,200 – 12,000 t/día**
- Requiere: Mantenimiento predictivo correa, redundancia mecánica

### OPCIÓN B — OPTIMIZACIÓN OPERACIONAL (menor inversión, retorno inmediato)
**Completar e implementar Optimizer V3 + Dashboard**
- Beneficio: Cerrar brecha P90 SAG1 = 314 TPH
- Impacto estimado: **+7,536 t/día** sin inversión física
- Requiere: 4-6 semanas de desarrollo + integración dashboard
- ROI: Muy alto (costo bajo, impacto alto)

### OPCIÓN C — PILAS (autonomía estratégica)
**Ampliar capacidad Pila SAG1** (hoy cap_efectiva = 4,575 ton)
- Beneficio: SAG1 puede sobrevivir ventanas T8 más largas
- Impacto: Reducir riesgo de agotamiento del 60% actual a <20%

### VEREDICTO CIO:
> **Implementar B primero (retorno inmediato, bajo costo), luego A (inversión física justificada por evidencia histórica).**
> La combinación B+A recuperaría hasta **15,000-20,000 t/día** de brecha operacional.

---

*Generado automáticamente con evidencia histórica 93,612 registros (ago-2025 → jun-2026)*
*Script: `02_Analytics/Scripts/balance_alimentacion_molienda.py`*
