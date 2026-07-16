# Análisis de Integración — `Datos Producción.xlsx`

**Archivo:** `01_Data/Raw/Datos Producción.xlsx`
**Fecha de análisis:** 2026-07-06
**Analista:** Analítica CIO-DET (asistido)

---

## Resumen de una línea

Es un **reporte diario oficial PAM (plan) vs Real de toda la cadena de valor** —
mina → chancado → molienda (SAG1/SAG2/convencional/unitaria) → Sewell →
fundición — con **2.6 años de historia** (943 días, 2024-01-01 → 2026-07-31,
Real hasta 2026-07-05). **Sí vale la pena integrarlo**, pero no como dato de
simulación (es diario, el Gemelo opera en ventanas de horas/minutos) sino como
**ground truth de calibración y como nueva capa de negocio (recuperación/ley)
que hoy el Gemelo no modela en absoluto**.

---

## Fase 1 — Perfilado del archivo

Una sola hoja (`Hoja1`), header de 2 filas (grupo + subcampo), 52 columnas,
943 registros diarios. Sin duplicados de fecha, sin huecos de días (delta = 1
día en el 100% de los casos).

| Grupo | Campo | Tipo | % Nulos | Frecuencia | Comentario |
|---|---|---|---:|---|---|
| — | Fecha | datetime | 0% | Diaria | 2024-01-01 → 2026-07-31; Real solo hasta 2026-07-05, resto es PAM (plan) a futuro |
| ACARREO | PAM/Real TT8 | float | 0% | Diaria | Tonelaje total acarreado desde el sector Teniente 8 |
| ACARREO | PAM/Real CHPRI | float | 0% | Diaria | Tonelaje a chancado primario |
| ACARREO | PAM/Real CHST | float | 0% | Diaria | Tonelaje a chancado secundario/terciario |
| GPTA | PAM/Real CHST | float | 0% | Diaria | Throughput chancado (vista planta) |
| GPTA | PAM/Real MUN | float | 0% | Diaria | Molienda "unitaria" (línea no-SAG) |
| GPTA | PAM/Real MCONV | float | 0% | Diaria | Molienda convencional |
| GPTA | **PAM/Real SAG 1** | float | 0% | Diaria | **Tonelaje diario procesado SAG1 — línea que modela el Gemelo** |
| GPTA | **PAM/Real SAG 2** | float | 0% | Diaria | **Tonelaje diario procesado SAG2 — línea que modela el Gemelo** |
| SEWELL | PAM/Real AC/MOL SEWELL | float | 0% | Diaria | Acarreo/molienda planta Sewell (fuera del circuito SAG1/SAG2) |
| GFUN | PAM/Real FILTRO/TRANSFERIDO/FUNDIDO/MOLDEO/SECADO | float | 0% | Diaria | Fundición — etapas aguas abajo de concentración |
| Convencional | PAM/Real Ley Concentrado | float | **9.1%** | Diaria | **Nulo desde 2025-08-01 en adelante** — dejó de reportarse hace ~11 meses |
| Convencional | PAM Rec Cu, retratamiento | float | 0% | Diaria | Recuperación de cobre, concentrado a retratamiento |
| SAG | PAM/Real REC SW, REC GLOBAL, PAM MOLIENDA | float | **19.3%** | Diaria | Nulo antes de 2024-07-01 — campo agregado a mitad de la serie |
| SAG | Real Recuperación, Ley Concentrado | float | 0% | Diaria | Recuperación/ley específica de la línea SAG |

**Chequeo de consistencia interno (mass-balance, ya que el proyecto exige
validar antes de confiar en datos nuevos):** `TT8 ≈ CHPRI + CHST` se cumple
con desviación media de 571 t sobre ~120.000 t/día (<0.5%), pero con outliers
puntuales de hasta 91.500 t en días específicos — **a confirmar con el equipo
de Planificación (PAM)** si son errores de digitación o corresponden a
definiciones distintas de corte de turno/acumulado.

**Cruce de magnitud con el modelo ya calibrado:** `GPTA Real SAG1` promedia
~30.000 t/día y `GPTA Real SAG2` ~50-56.000 t/día — consistente con
P90_SAG1=1.454 TPH×24h≈34.900 t/día y P90_SAG2=2.516 TPH×24h≈60.400 t/día ya
calibrados en `outputs/models/campeones/`. Esto es una **señal fuerte de que
el archivo es confiable como ground truth diario**, no un dataset paralelo
desconectado.

---

## Fase 2 — Comprensión operacional

| Grupo | ¿Qué representa? | ¿Dónde ocurre? | ¿Qué equipo afecta? | ¿Qué decisión influye? | Clasificación |
|---|---|---|---|---|---|
| ACARREO | Tonelaje extraído/transportado desde el sector Teniente 8 hacia chancado | Mina → Chancado primario/secundario | Camiones, correas de acarreo, CHPRI, CHST | Cuánto mineral hay disponible para alimentar molienda ese día | Alimentación / Restricciones |
| GPTA SAG1/SAG2 | Tonelaje diario efectivamente molido por cada línea SAG | Molienda | Molino SAG1 (401), SAG2 (501) | Validación de rate operado real vs recomendado | Producción |
| GPTA MUN/MCONV | Tonelaje de líneas de molienda no-SAG | Molienda convencional/unitaria | Molinos convencionales | Redistribución de carga si SAG está restringido | Producción / Restricciones |
| SEWELL | Tonelaje planta Sewell | Otra instalación productiva | N/A para el Gemelo (fuera de alcance SAG1/SAG2) | Contexto de capacidad global de la división | Producción (fuera de alcance) |
| GFUN | Filtrado/fundido/moldeo/secado | Fundición (aguas abajo de concentración) | Fundición | Cuello de botella aguas abajo, no aguas arriba | Producción (fuera de alcance directo) |
| Convencional/SAG — Ley y Recuperación | Calidad del concentrado (% Cu) y % de cobre recuperado | Planta de flotación/concentración | Todo el circuito, resultado metalúrgico | Si hay pérdida de valor aunque el TPH esté OK | **Calidad mineral — dimensión nueva, no modelada hoy** |

---

## Fase 3 — Mapa causal

```
Acarreo TT8 (mina)
     ↓
CHPRI / CHST (chancado)
     ↓
GPTA SAG1 / SAG2 (tonelaje diario molido)   ←→   [cruce] TPH 5-min ya modelado (pila_sag1/2, autonomía)
     ↓
Ley Concentrado + Recuperación Cu (SAG / Convencional)
     ↓
Cobre fino producido (valor económico real, no solo TPH)
     ↓
Brecha PAM vs Real (ya existe como "brecha_p90" en Optimizer V3, pero a nivel TPH instantáneo)
     ↓
Decisión: ¿el rate recomendado hoy realmente se tradujo en más cobre, o solo en más toneladas de menor ley?
```

El archivo cierra un ciclo que hoy está abierto: el Gemelo optimiza **TPH**,
pero el negocio se mide en **cobre fino** (TPH × recuperación × ley). Esta es
la brecha conceptual más importante que este archivo permite empezar a cerrar.

---

## Fase 4 — Valor por caso de uso

| Grupo | Simulación | Optimización | Riesgo | Control operacional | Predicción |
|---|:-:|:-:|:-:|:-:|:-:|
| ACARREO (TT8/CHPRI/CHST) | No (granularidad diaria) | **Sí** — restricción de disponibilidad de mineral aguas arriba | **Sí** — riesgo de falta de alimentación | No | **Sí** — predecir feed disponible por día |
| GPTA SAG1/SAG2 (tonelaje diario) | No directo | **Sí** — ground truth para recalibrar P50/P75/P90 | No | **Sí** — comparación PAM vs Real ya operado | **Sí** — recalibración periódica del modelo |
| MUN/MCONV | No | Parcial — redistribución de carga | No | No | No |
| SEWELL, GFUN | No | No (fuera de alcance del circuito SAG) | No | No | No |
| Ley Concentrado / Recuperación Cu | No | **Sí** — nueva función objetivo económica | **Sí** — riesgo metalúrgico | **Sí** — nuevo KPI de calidad | **Sí** — modelo de recuperación vs rate/T8 |

---

## Fase 5 — Nuevas preguntas de negocio (mínimo 10)

1. ¿El rate más alto que recomienda el Optimizer V3 mantiene la ley de
   concentrado, o la diluye?
2. ¿Cuánto cobre fino (no solo TPH) se pierde en un evento T8 de 12h vs uno
   de 4h?
3. ¿La brecha PAM vs Real de SAG1/SAG2 es sistemática (todos los días) o
   solo en eventos T8?
4. ¿El acarreo TT8 (mina) es alguna vez el cuello de botella real, en vez de
   la capacidad de molienda?
5. ¿Cuándo conviene desviar carga hacia molienda convencional (MCONV) en vez
   de forzar SAG1/SAG2?
6. ¿Existe correlación entre recuperación de cobre y duración de ventanas T8
   (pérdida metalúrgica por operación transitoria)?
7. ¿Cuál es el costo en cobre fino (USD) de la brecha P90 que ya reporta el
   Optimizer V3, no solo en toneladas?
8. ¿La caída de recuperación coincide con cambios de configuración de bolas
   (411/412/511/512)?
9. ¿Sewell o Fundición limitan alguna vez la capacidad de procesar más
   mineral aunque SAG1/SAG2 tengan margen?
10. ¿El acumulado mensual PAM vs Real predice con anticipación un
    incumplimiento de meta antes de fin de mes?
11. *(extra)* ¿Los ~11 meses sin reporte de "Real Ley Concentrado" ocultan un
    problema de instrumentación o un cambio de sistema de reporte?

---

## Fase 6 — Impacto por nivel

| Grupo | Nivel |
|---|---|
| SEWELL, GFUN | **Nivel 1 — Informativa** (contexto, no accionable desde el Gemelo) |
| ACARREO (TT8/CHPRI/CHST), MUN/MCONV | **Nivel 2 — KPI** (disponibilidad de feed aguas arriba) |
| GPTA SAG1/SAG2 (tonelaje diario PAM/Real) | **Nivel 3 — Predictiva** (recalibración periódica de P50/P75/P90) |
| Ley Concentrado / Recuperación Cu | **Nivel 4 — Prescriptiva** (nueva función objetivo económica para el optimizador) |
| — | **Nivel 5 — Física: ninguna variable de este archivo aplica** (ver Fase 7) |

---

## Fase 7 — Impacto en ecuaciones diferenciales

**Ninguna variable de este archivo debe entrar directamente a
`dPilaSAG1/dt` / `dPilaSAG2/dt`.** Motivo: el ODE opera a paso de 5 minutos
sobre inventario de pila (%); este archivo es un **acumulado diario
post-hoc** — mezclar granularidades rompería la interpretación física del
balance de masa (`Qin - Qout`) que ya está validado.

| | Actual | Propuesto | Beneficio |
|---|---|---|---|
| Ecuación | `S[t+1] = S[t] + (Qin_5min - Qout_5min)·DT` | **Sin cambio en la ecuación** | Preserva validación existente |
| Uso del archivo | Ninguno | **Restricción de contorno diaria**: `∫(Qin_5min)dt` en una ventana de 24h debería reconciliar con `GPTA Real SAG{1,2}` de ese día (±tolerancia) | Detecta drift del modelo 5-min sin tocar su estructura — un chequeo de integridad, no una ecuación nueva |
| Calibración | P50/P75/P90 fijos desde `advanced_t8_historical_5min.parquet` | Recalibración trimestral usando los 2.6 años de `GPTA Real SAG1/2` como serie larga independiente | Anclas de percentil más robustas (menos sensibles a la ventana de datos 5-min disponible) |

---

## Fase 8 — Impacto en Optimizer V3

| Variable | Impacto Optimizer |
|---|---|
| GPTA Real SAG1/SAG2 (histórico 2.6 años) | **Alto** — recalibra R1_CANDS_V3/R2_CANDS_V3 (percentiles P50/P75/P90/MAX) con serie 5x más larga que la actual |
| Ley Concentrado + Recuperación Cu | **Alto** — permite agregar función objetivo "cobre fino" en `compute_multi_criteria_score`, no solo TPH/autonomía |
| ACARREO TT8/CHPRI/CHST | **Medio** — restricción dura nueva: si el acarreo del día está limitado, no recomendar rates que asumen feed ilimitado |
| MUN/MCONV | **Bajo-Medio** — candidato a "modo de escape" cuando SAG está en regimen EMERGENCIA (desviar a convencional) |
| SEWELL/GFUN | **Ninguno** — fuera del alcance del optimizador de molienda SAG |

---

## Fase 9 — Impacto en Monte Carlo

- **No reduce la incertidumbre de pila/autonomía** — es un dato diario
  agregado, no aporta información dentro del horizonte de simulación
  (horas). No reemplaza el rol del Monte Carlo actual.
- **Sí explica variabilidad estructural**: la serie de 2.6 años de
  PAM-vs-Real permite estimar la distribución empírica real del "error de
  cumplimiento de plan" — hoy el `t3_frac`/incertidumbre de CV se asume
  (±12%), este archivo podría **calibrar esa magnitud con datos reales**
  en vez de un supuesto.
- **Nueva distribución posible**: recuperación de cobre vs duración T8,
  para simular escenarios "P(pérdida de recuperación > X%) dado T8=Yh" —
  hoy no existe esa dimensión en el Monte Carlo.

---

## Fase 10 — Impacto en Riesgo Operacional

Riesgos nuevos que este archivo permite modelar (que hoy el IRO no cubre):

- **Riesgo de brecha PAM sostenida**: no un evento puntual (T8 de hoy),
  sino un patrón de incumplimiento de varios días/semanas — el IRO actual
  es instantáneo, no tiene memoria de tendencia.
- **Riesgo metalúrgico**: caída de ley/recuperación aunque el TPH esté en
  meta — un escenario "verde en TPH, rojo en cobre fino" que hoy es
  invisible para el semáforo.
- **Riesgo de cuello de botella cruzado**: Sewell o Fundición saturados
  limitando el valor de producir más TPH en SAG1/SAG2 (sobreproducción sin
  capacidad de procesarlo aguas abajo).
- **Riesgo de restricción de acarreo**: mina no entrega suficiente TT8 —
  hoy el modelo asume feed disponible ilimitado salvo por T8.

---

## Fase 11 — Impacto en Dashboard

- **Nuevos KPIs**: Cobre fino producido (TPH × ley × recuperación),
  Cumplimiento PAM acumulado (mes/trimestre), Ley promedio vs meta.
- **Nuevas tarjetas**: "Brecha PAM vs Real — 30 días" (tendencia, no solo
  hoy), "Recuperación Cu actual vs histórico".
- **Nuevos gráficos**: serie diaria PAM vs Real (SAG1/SAG2) de los 2.6
  años — contexto histórico que hoy no existe en ninguna pestaña; scatter
  Ley vs Duración T8.
- **Nuevo semáforo**: estado metalúrgico (ley/recuperación), independiente
  del semáforo operacional (IRO) actual.
- **Nueva pestaña**: "Desempeño Diario" (vista mensual/trimestral, PAM vs
  Real, complementaria a la vista horaria del simulador operacional).

---

## Fase 12 — Priorización

| Variable/Grupo | Valor Operacional | Complejidad | Prioridad |
|---|---|---|---|
| GPTA SAG1/SAG2 (recalibración P50-P90) | Alta | Baja | **Alta** |
| Gráfico histórico PAM vs Real (dashboard) | Media | Baja | **Alta** |
| Ley Concentrado + Recuperación Cu (KPI dashboard) | Alta | Media | **Alta** |
| Función objetivo "cobre fino" en Optimizer V3 | Alta | Alta | Media |
| ACARREO TT8 como restricción dura | Media | Media | Media |
| MUN/MCONV como modo de escape | Baja-Media | Alta | Baja |
| SEWELL / GFUN | Baja (fuera de alcance) | — | Baja |

---

## Fase 13 — Roadmap de integración

### Quick Wins (1-2 días)
- Cargar el archivo a `01_Data/Cache/` como parquet limpio (fechas, tipos,
  nombres de columna normalizados) — **prerequisito de todo lo demás**.
- Gráfico "PAM vs Real SAG1/SAG2 — histórico diario" en una nueva pestaña
  o sección del dashboard (solo lectura, sin tocar el motor).
- Tarjeta "Cumplimiento PAM del mes" (% Real/PAM acumulado).

### Fase 2 (1 semana)
- Recalibrar P50/P75/P90 de `R1_CANDS_V3`/`R2_CANDS_V3` usando los 2.6 años
  de `GPTA Real SAG1/SAG2` — comparar contra los anclas actuales (del
  dataset 5-min) y decidir si se actualizan o se promedian.
- KPI "Cobre fino producido" (requiere reconciliar unidades de ley/
  recuperación, y decidir tratamiento de los 11 meses sin dato de Ley Real).

### Fase 3 (2-4 semanas)
- Función objetivo económica en Optimizer V3 (`compute_multi_criteria_score`
  con término de cobre fino, no solo TPH) — requiere validación con
  Ingeniería de Procesos antes de cambiar recomendaciones operacionales.
- Restricción dura de ACARREO TT8 en el optimizador (feed disponible
  limitado por acarreo, no solo por T8/mantenciones).
- Modelo de recuperación vs duración T8 (nueva capa predictiva, análogo al
  Metropolis-Hastings ya usado para riesgo de autonomía).

---

## Conclusión

**¿Vale la pena integrar este archivo? Sí**, pero como capa de
**calibración y contexto de negocio (cobre fino, cumplimiento de plan)**,
no como insumo directo del simulador de 5 minutos. Su mayor valor es
cerrar la brecha entre "el Gemelo optimiza TPH" y "el negocio se mide en
cobre fino producido" — algo que ningún dato existente en el proyecto
cubre hoy.

**Dónde aporta valor:** recalibración de Optimizer V3 (alto), nuevo KPI de
dashboard (alto), nueva dimensión de riesgo metalúrgico (medio-alto).
**Dónde no aporta valor directo:** ecuaciones diferenciales (granularidad
incompatible), Sewell/Fundición (fuera del alcance del circuito SAG1/SAG2).

**Plan recomendado:** empezar por el Quick Win de cargarlo y graficarlo
(sin riesgo, sin tocar motores validados), luego recalibrar percentiles con
la serie larga, y solo en una tercera fase — con validación explícita de
Ingeniería de Procesos — introducir cobre fino como función objetivo del
optimizador.
