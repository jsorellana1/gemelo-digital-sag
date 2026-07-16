# Modelo Robusto de Descarga de Pilas SAG
**División El Teniente — Codelco | 2026-06-22**

---

## Resumen Ejecutivo

Este informe documenta el modelo de 3 niveles para estimar la tasa de descarga de pilas SAG1
y SAG2 durante ventanas de mantención Teniente 8 (T8). El modelo reemplaza la única tasa
global promedio por estimaciones estratificadas por duración de ventana T8, con
corrección de shrinkage bayesiano para buckets de baja muestra.

**Skills aplicados:** `skill_estadistica_bayesiana_avanzada`, `skill_molienda_sag`,
`skill_data_scientist_senior`, `skill_series_temporales_industriales`

---

## 1. Metodología

### Datos
- **Fuente pile levels**: `correas_ton.xlsx` — resolución 5 minutos
- **Fuente T8 events**: `fact_eventos_t8.parquet` — 29 ventanas únicas
- **Período**: 2026-01-01 → 2026-06-14

### Cálculo de tasa de descarga
Para cada ventana T8, se extraen todos los registros de 5 minutos y se calcula:

```
tasa_inst = media(-dS/dt) para dS/dt < -0.01 %/min
```

donde `S` es el nivel de pila en % y el denominador convierte a %/hora.
Si no hay datos instantáneos, se usa la tasa bruta: `(nivel_inicio - nivel_fin) / duracion_h`.

### Buckets de duración T8
| Bucket     | Rango      |
|------------|-----------|
| Corta      | ≤ 2 horas  |
| Media      | 3–6 horas  |
| Larga      | 7–12 horas |
| Muy_larga  | > 12 horas |

### Shrinkage (James-Stein)
```
w = N / (N + k),   k = 5
tasa_final = w · tasa_bucket + (1-w) · tasa_global
```
**Umbral baja confianza**: N < 5 eventos → bucket marcado con ⚠

---

## 2. Nivel 1 — Tasa Global

| SAG  | Tasa Global (%/h) | N | IC90            | Referencia previa |
|------|-------------------|---|-------------------|-------------------|
| SAG1 | 23.7611 | 27 | [17.825, 29.697] | 25.2239 |
| SAG2 | 5.7306 | 27 | [4.867, 6.594] | 6.1987 |

> La tasa global es el promedio de todas las observaciones, sin distinción de duración T8.
> Es el prior para el shrinkage en Nivel 2.

---

## 3. Nivel 2 — Tasas por Bucket con Shrinkage

### SAG1

| Bucket | N | Tasa raw (%/h) | w | Tasa final (%/h) | IC90 | Confianza |
|--------|---|----------------|---|------------------|------|-----------|
| ≤2h | 2 | 40.753 | 0.29 | 28.616 | [-9.179, 66.411] | ⚠ baja |
| 3-6h | 4 | 18.075 | 0.44 | 21.234 | [8.151, 34.317] | ⚠ baja |
| 7-12h | 17 | 25.024 | 0.77 | 24.737 | [16.246, 33.228] | ✓ alta |
| >12h | 4 | 15.584 | 0.44 | 20.127 | [3.156, 37.098] | ⚠ baja |

### SAG2

| Bucket | N | Tasa raw (%/h) | w | Tasa final (%/h) | IC90 | Confianza |
|--------|---|----------------|---|------------------|------|-----------|
| ≤2h | 2 | 7.417 | 0.29 | 6.212 | [-4.434, 16.859] | ⚠ baja |
| 3-6h | 4 | 3.787 | 0.44 | 4.867 | [3.134, 6.600] | ⚠ baja |
| 7-12h | 17 | 6.317 | 0.77 | 6.184 | [5.138, 7.229] | ✓ alta |
| >12h | 4 | 4.338 | 0.44 | 5.112 | [1.043, 9.181] | ⚠ baja |

---

## 4. Nivel 3 — Regresión OLS

La regresión relaciona la tasa de descarga con tres predictores:
`tasa = β₀ + β₁·rate_sag + β₂·duracion_h + β₃·nivel_inicio`

### SAG1

**R² = 0.1107  |  R²adj = -0.0945  |  N = 17  |  AIC = 139.2**

| Variable | Coeficiente | p-valor | Significancia |
|----------|-------------|---------|---------------|
| const | -11.625581 | 0.7106 | ns |
| rate_sag | 0.018755 | 0.5001 | ns |
| duracion_h | 0.223625 | 0.4070 | ns |
| nivel_inicio | 0.145531 | 0.3992 | ns |

### SAG2

**R² = 0.3791  |  R²adj = 0.2981  |  N = 27  |  AIC = 123.0**

| Variable | Coeficiente | p-valor | Significancia |
|----------|-------------|---------|---------------|
| const | -4.365929 | 0.1376 | ns |
| rate_sag | 0.004026 | 0.0254 | * |
| duracion_h | 0.036740 | 0.2794 | ns |
| nivel_inicio | 0.059141 | 0.3677 | ns |

---

## 5. Interpretación: 8 Preguntas Clave

### P1. ¿La tasa de descarga es la misma en todos los tipos de ventana T8?

**No.** Los datos muestran variación entre buckets, aunque parte de esta variación se debe
a ruido muestral (especialmente en buckets con N < 5). El shrinkage modera las estimaciones
extremas acercándolas al prior global cuando el N es bajo. 
- **SAG1**: rango shrinkage [20.13, 28.62] %/h (mínimo >12h, máximo ≤2h)
- **SAG2**: rango shrinkage [4.87, 6.21] %/h (mínimo 3-6h, máximo ≤2h)

### P2. ¿Qué bucket tiene la tasa más confiable estadísticamente?

- **SAG1**: bucket **7-12h** (N=17, tasa=24.737%/h, confianza=alta)
- **SAG2**: bucket **7-12h** (N=17, tasa=6.184%/h, confianza=alta)

### P3. ¿Importa el rate SAG (TPH) para predecir la tasa de descarga?

La regresión Nivel 3 evalúa si el TPH del molino durante el T8 es un predictor significativo.
Un coeficiente positivo y significativo indicaría que molinos más rápidos drenan la pila más rápido,
lo que es físicamente esperado (más consumo = más vaciado).

- **SAG1**: coef rate_sag = 0.01876, p = 0.500 → **NO significativo**
- **SAG2**: coef rate_sag = 0.00403, p = 0.025 → **significativo**

### P4. ¿Cuántas horas de autonomía tiene cada SAG desde su P50 histórico antes de entrar en zona roja?

Zona crítica = zona naranja inferior (riesgo alto).
Usando tasa shrinkage del bucket más frecuente:

- **SAG1** desde P50=50.3% hasta zona naranja (26.4%): **1.0h** (bucket 7-12h, tasa=24.74%/h)
- **SAG2** desde P50=27.8% hasta zona naranja (18.2%): **1.6h** (bucket 7-12h, tasa=6.18%/h)

### P5. ¿Qué sucede si la tasa real en una ventana larga es la del bucket Larga vs la global?

- **SAG1** (8h desde P50=50.3%): bucket Larga → 0.0%  |  global → 0.0%  (diferencia 0.0 pp)
- **SAG2** (8h desde P50=27.8%): bucket Larga → 0.0%  |  global → 0.0%  (diferencia 0.0 pp)

### P6. ¿Cuáles buckets tienen baja confianza y qué recomienda usar en su lugar?

**SAG1** — Buckets con baja confianza:
  - ≤2h (N=2): usar tasa global 23.761%/h como estimador de respaldo
  - 3-6h (N=4): usar tasa global 23.761%/h como estimador de respaldo
  - >12h (N=4): usar tasa global 23.761%/h como estimador de respaldo

**SAG2** — Buckets con baja confianza:
  - ≤2h (N=2): usar tasa global 5.731%/h como estimador de respaldo
  - 3-6h (N=4): usar tasa global 5.731%/h como estimador de respaldo
  - >12h (N=4): usar tasa global 5.731%/h como estimador de respaldo


### P7. ¿Qué modelo usar operacionalmente?

**Regla de decisión práctica:**

1. Si se conoce el bucket de la ventana T8 programada Y N ≥ 5: usar **Nivel 2 (shrinkage)**
2. Si N < 5 en ese bucket: usar **Nivel 1 (global)** con buffer de seguridad +20%
3. Si se conoce el TPH estimado de operación: usar **Nivel 3 (regresión)** como ajuste fino

```
tasa_op = tasa_shrinkage_bucket   # si confianza = alta
tasa_op = tasa_global * 1.20      # si confianza = baja (buffer conservador)
```

### P8. ¿Este modelo cambia la autonomía operacional calculada en informes anteriores?

La tasa global calculada en este modelo vs la referencia previa:

- **SAG1**: nueva=23.7611%/h vs previa=25.2239%/h  Δ=-1.4628%/h (menor velocidad de descarga en esta recalculación)
- **SAG2**: nueva=5.7306%/h vs previa=6.1987%/h  Δ=-0.4681%/h (menor velocidad de descarga en esta recalculación)

El cambio es relevante operacionalmente.
Los informes anteriores siguen siendo válidos en sus conclusiones generales.

---

## 6. Supuestos y Limitaciones

1. **Fechas T8 sin hora exacta**: `inicio`/`fin` en `fact_eventos_t8.parquet` son fechas-día.
   Se expanden a 00:00–23:55 del día respectivo. Esto puede incluir horas fuera del T8 real.
2. **Datos PAM sintetizados**: los datos actuales son simulados para entrenamiento analítico.
   Los resultados numéricos deben validarse con datos históricos reales de DCS/PI.
3. **N bajo en buckets cortos**: la mayoría de eventos T8 son >6h, haciendo que los buckets
   Corta y Media tengan N < 5. El shrinkage los lleva hacia el global.
4. **Regresión lineal**: Nivel 3 asume linealidad. Con más datos podría implementarse
   regresión robusta (Huber) o LOWESS.
5. **Tasa instantánea vs bruta**: se prefiere `tasa_inst` (media de dS/dt < 0) sobre
   `tasa_bruta` (Δnivel/duración). Si el SAG se detiene a mitad de ventana, `tasa_bruta`
   subestimaría la tasa real de consumo.

---

## 7. Archivos Generados

| Tipo | Ruta |
|------|------|
| Figura F1 | `outputs/figures/descarga_robusto/F1_distribucion_tasas_bucket.png` |
| Figura F2 | `outputs/figures/descarga_robusto/F2_tasa_vs_duracion.png` |
| Figura F3 | `outputs/figures/descarga_robusto/F3_comparacion_niveles.png` |
| Figura F4 | `outputs/figures/descarga_robusto/F4_shrinkage_weights.png` |
| Figura F5 | `outputs/figures/descarga_robusto/F5_regresion_rate_sag.png` |
| Figura F6 | `outputs/figures/descarga_robusto/F6_regresion_nivel_inicial.png` |
| Figura F7 | `outputs/figures/descarga_robusto/F7_error_bars_bucket.png` |
| Figura F8 | `outputs/figures/descarga_robusto/F8_curvas_supervivencia.png` |
| Figura F9 | `outputs/figures/descarga_robusto/F9_dashboard_calidad.png` |
| Excel     | `outputs/excel/modelo_descarga_pilas_robusto.xlsx` |
| Informe   | `outputs/reports/modelo_descarga_pilas_robusto.md` |

---

*Generado: 2026-06-22 07:02 — Plataforma Analítica CIO DET*
