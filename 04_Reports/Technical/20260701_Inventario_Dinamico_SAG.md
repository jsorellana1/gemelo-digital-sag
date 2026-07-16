# Inventario Dinámico SAG — KPI Dual Operacional

**Fecha:** 2026-07-01  
**Autor:** Análisis CIO-DET / Plataforma Analítica Rendimientos  
**Módulo afectado:** `05_Dashboard/components/graphs.py`, `05_Dashboard/components/cards.py`

---

## 1. Diagnóstico

### Síntoma observado

La curva de sensibilidad del SAG2 aparecía plana en prácticamente todo el rango operacional, impidiendo al operador extraer información útil.

### Causa raíz (dos componentes encadenados)

**Componente A — feed excede capacidad física:**

Con ambas correas CV315 y CV316 activas y distribución histórica 29/71%:

```
cv316_tph ≈ 0.71 × T1_total ≈ 0.71 × 4 200 TPH ≈ 2 982 TPH
```

El máximo físico operacional del SAG2 es ~2 800 TPH.  
Por lo tanto `cv316 > SAG2_PHYS_MAX` en la configuración de máxima capacidad.

**Componente B — capacidad de pila muy grande:**

```
CAP_TON["SAG2"] = 32 009 ton
```

Incluso a tasas superiores al equilibrio (2 982–3 311 TPH, fuera del rango físico), la autonomía resultante es de 40–746 horas, valores que el cap visual (`vis_cap ≈ 20h`) recorta uniformemente.

**Resultado:** el eje Y queda truncado en el mismo valor para todos los puntos → curva plana.

### Por qué SAG1 muestra la bañera correctamente

```
cv315_tph ≈ 0.29 × 4 200 ≈ 1 218 TPH  <  rate_sag1 típico (1 400 TPH)
```

La pila SAG1 drena normalmente (`rate > feed`), los valores de autonomía son finitos y en rango visible (4–15 h), la bañera aparece en la parte derecha del equilibrio.

---

## 2. Rediseño conceptual: KPI Dual de Inventario

### Problema conceptual del KPI anterior

El KPI anterior era:

```
Autonomía = (Pila - Crítico) / Tasa_drenaje_neta
```

Sólo tiene sentido cuando `rate > feed` (pila drenando). Cuando `feed > rate` (pila creciendo), la tasa neta es negativa → autonomía → ∞ → curva plana.

### Nuevo KPI unificado

```
                  ┌─ (Pila − Crítico) / dh_drain     si rate > feed  [DRENANDO]
KPI(rate) =  ─── ┤
                  └─ (100% − Pila)   / dh_fill        si feed > rate  [LLENANDO]
```

Donde:
```
dh_drain =  (rate − feed) / cap_ton × 100   [%/h]   positivo
dh_fill  =  (feed − rate) / cap_ton × 100   [%/h]   positivo
```

El resultado es siempre finito y tiene significado operacional:

| Régimen | KPI muestra | Pregunta respondida |
|---------|------------|---------------------|
| `rate > feed` | Horas hasta vaciado | ¿Cuánto tiempo tengo antes de que la pila se agote? |
| `rate = feed` | ∞ (equilibrio) | La pila está estable |
| `feed > rate` | Horas hasta overflow | ¿Cuánto tiempo antes de que la pila se llene? |

---

## 3. Diseño del gráfico

### Grid centrado en el equilibrio

El eje X se centra en `feed_tph` (punto de equilibrio), extendiendo `±42% × ref_tph` hacia ambos lados. Esto garantiza que **ambos brazos de la curva** (overflow a la izquierda, autonomía a la derecha) sean visibles.

### vis_cap separado por brazo

El escalado visual se calcula de forma independiente para el brazo de llenado y el de drenaje, luego se toma el máximo:

```python
vis_cap = max(_vc_arm(fill_values), _vc_arm(drain_values))
```

Esto evita que valores pequeños en un brazo compriman la escala del otro.

### Codificación visual

| Elemento | Significado |
|----------|-------------|
| Línea **discontinua** | Brazo izquierdo: tiempo hasta overflow |
| Línea **continua** | Brazo derecho: autonomía (vaciado) |
| Línea vertical gris punteada | Equilibrio (rate = feed) |
| Línea vertical color SAG | Rate actual |
| Marcador ● | Punto operacional actual con valor numérico |

### Zonas de color (eje Y)

| Zona | Color | Significado |
|------|-------|-------------|
| 0–6 h | Rojo | Crítico: acción inmediata |
| 6–24 h | Naranja | Alerta: monitoreo activo |
| >24 h | Verde | Seguro: margen operacional amplio |

Las mismas zonas aplican para ambos modos (overflow y autonomía).

---

## 4. Tarjeta de inventario dual (`make_inventario_card`)

Se agrega una nueva tarjeta KPI en el panel derecho del simulador que muestra:

```
Estado:    DRENANDO / EQUILIBRIO / LLENANDO
Valor:     X.X h autonomía  ó  X.X h overflow
Tendencia: ⬇ / ◆ / ⬆
```

La tarjeta reemplaza `make_autonomia_card` en `make_kpi_column`, eliminando la autonomía de drenaje-only que era incorrecta cuando la pila estaba creciendo.

---

## 5. Ejemplo numérico verificado

### Escenario SAG2 con ambas CVs activas

```
T1_total   = 4 200 TPH  (ch1 + ch2)
cv316      = 4 200 × 0.71 = 2 982 TPH
rate_sag2  = 2 200 TPH
pila_sag2  = 60%
CAP_SAG2   = 32 009 ton
```

**Cálculo KPI en modo LLENANDO:**
```
net_fill   = 2 982 − 2 200 = 782 TPH  (feed > rate → pila crece)
dh_fill    = 782 / 32 009 × 100 = 2.44 %/h
remaining  = 100 − 60 = 40%
T_overflow = 40 / 2.44 = 16.4 h  → ZONA NARANJA (alerta)
```

El operador ve: `⬆ 16.4 h overflow` y puede actuar subiendo el rate.

**Punto de equilibrio:** a rate = 2 982 TPH la pila no varía.

**Brazo derecho (drain, fuera de rango físico):**
```
rate = 3 311 TPH → net_drain = 329 TPH → dh = 1.03 %/h
T_drain = (60 − 18.2) / 1.03 = 40.6 h  → ZONA VERDE
```

### Escenario SAG1 (sin cambio)

```
cv315      = 4 200 × 0.29 = 1 218 TPH
rate_sag1  = 1 400 TPH  (rate > feed → pila drena)
pila_sag1  = 60%
CAP_SAG1   = 4 575 ton
```

```
net_drain  = 1 400 − 1 218 = 182 TPH
dh_drain   = 182 / 4 575 × 100 = 3.98 %/h
T_drain    = (60 − 15) / 3.98 = 11.3 h  → ZONA NARANJA
```

La bañera SAG1 sigue visible y sin cambios.

---

## 6. Preguntas respondidas por el nuevo KPI

| # | Pregunta | Respuesta del gráfico |
|---|----------|----------------------|
| 1 | ¿La pila se vacía o se llena? | Subtítulo + ícono ⬆/⬇/◆ |
| 2 | ¿En cuánto tiempo? | Valor numérico en el marcador |
| 3 | ¿Cuál es el punto de equilibrio? | Línea vertical gris + anotación |
| 4 | ¿Qué rate elimina el riesgo de overflow? | Brazo izquierdo cruza 24h |
| 5 | ¿Qué rate genera vaciado? | Brazo derecho, cualquier punto |
| 6 | ¿Qué ocurre si cambia cv316? | El equilibrio se desplaza en X |
| 7 | ¿Zona operacional recomendada? | Entre 24h overflow y 24h autonomía |

---

## 7. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `05_Dashboard/components/graphs.py` | `make_sensitivity_chart` reescrita con KPI dual |
| `05_Dashboard/components/cards.py` | `make_inventario_card` agregada, `make_kpi_column` actualizada |

### Funciones no modificadas (compatibilidad mantenida)

- `make_autonomia_card` — permanece en cards.py para uso futuro
- `simulate_scenario`, `ode_model`, `risk_engine` — sin cambios
- Todos los callbacks de app.py — sin cambios
