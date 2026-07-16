# Estrategia de Mitigación del Impacto Operacional de Teniente 8
## Documento Ejecutivo — Analítica Prescriptiva

**Fecha:** 16/06/2026 12:58
**Período analizado:** 2026-01-01 a 2026-06-14 (5.5 meses)
**Eventos T8 analizados:** 72 (68 con datos de rendimiento)
**Audiencia:** CIO | Operaciones Planta | Optimización de Activos | PAM | Superintendencia Molienda

---

## 1. Contexto y Punto de Partida

**Teniente 8 es el ferrocarril que transporta mineral fino y grueso desde la mina hacia las pilas
de alimentación de los circuitos SAG, PMC y UNITARIO.** Durante una ventana de mantenimiento,
T8 deja de operar: no hay entrega de mineral a chancado primario ni secundario y, por lo tanto,
no hay oferta de mineral fresco hacia los molinos. Los molinos consumen el stock de pila hasta
agotarlo — y entonces cae el TPH.

El análisis Event Study Industrial cuantificó ese efecto sobre los rendimientos. Este documento no repite ese análisis.

**El efecto existe, está cuantificado y es estadísticamente significativo en SAG1, SAG2 y PMC.**

El objetivo ahora es responder: **¿Qué se puede hacer y cuánto vale hacerlo?**

---

## 2. Cuantificación del Impacto Económico

### Toneladas no producidas durante ventanas T8

| Activo   | Baseline (t/h) | Ton esperadas | Ton reales | Pérdida (kt) | Pérdida % |
|----------|---------------|---------------|------------|--------------|-----------|
| SAG1     |  1,078        | 131,503       | 108,285    |  **23.2 kt** | 17.7%     |
| SAG2     |  2,117        | 418,300       | 356,614    |  **61.7 kt** | 14.7%     |
| PMC      |  1,118        | 246,960       | 213,364    |  **33.6 kt** | 13.6%     |
| UNITARIO |    783        |  66,097       |  47,889    |  **18.2 kt** | 27.5%     |
| **TOTAL**|               |               |            | **136.7 kt** |           |

> **Referencial de valor:** A 1.2% Cu, 86% recuperación y $9,500/MT Cu:
> pérdida estimada de **1,411 ton Cu** = **USD 13,403K** en el período analizado.
> Anualizado: ~**USD 29,243K/año**.

### Pérdida por duración de ventana

| Duración | Eventos | Caída TPH | Pérd. media/evento | Pérd. total  |
|----------|---------|-----------|-------------------|--------------|
| 2h       | 18      | ~34.9%    | **540 ton**       | 9,720 ton    |
| 4h       | 46      | ~38.3%    | **2,507 ton**     | 115,322 ton  |
| 8h       |  1      | ~39%*     | **~5,375 ton***   | 5,375 ton    |
| 12h      |  7      | ~39.9%    | **8,242 ton**     | 57,694 ton   |

*Interpolado — solo 1 evento disponible.*

**Hallazgo clave:** pasar de ventana 4h a 12h multiplica la pérdida por **3.3×** por evento.

---

## 3. Diagnóstico de Vulnerabilidad por Activo

### KPI 1 — Índice de Vulnerabilidad Operacional (IVO = Caída% × Tiempo Recuperación)

| Activo   | Caída media | Rec. 90% | **IVO** | Categoría     |
|----------|-------------|----------|---------|---------------|
| PMC      | 39.3%       | 8.4h     | **606** | [CRITICO] Muy Alto   |
| SAG2     | 42.7%       | 11.4h    | **535** | [CRITICO] Muy Alto   |
| SAG1     | 37.3%       | 10.4h    | **433** | [ALTO] Alto          |
| UNITARIO | 19.4%       | 5.8h     | **211** | [BAJO] Bajo          |

> **PMC tiene el IVO más alto** porque combina caída severa con recuperación lenta.
> SAG2 cae más (42.7%) pero PMC tarda menos en llegar al mínimo — lo que amplifica el efecto total.

### KPI 2 — Índice de Resiliencia (IR = Tiempo Rec. / Caída%)

| Activo   | **IR**  | Interpretación                                |
|----------|---------|-----------------------------------------------|
| UNITARIO | 0.466   | Más resiliente — recuperación rápida y caída menor |
| PMC      | 0.379   | Recuperación relativa razonable dada la caída |
| SAG2     | 0.116   | Baja resiliencia — cae mucho y tarda en recuperar |
| SAG1     | 0.044   | **El menos resiliente** — caída severa y recuperación muy lenta |

### KPI 3 — Índice de Amortiguación de Pilas (IAP = h_hasta_mínimo / duración_ventana)

| Activo   | **IAP** | Autonomía estimada       | Interpretación                     |
|----------|---------|--------------------------|------------------------------------|
| SAG2     | 2.90    | 2.9× la duración         | Pilas amortiguan fuertemente       |
| SAG1     | 2.75    | 2.75× la duración        | Pilas amortiguan fuertemente       |
| PMC      | 2.45    | 2.45× la duración        | Amortiguación parcial              |
| UNITARIO | 1.85    | 1.85× la duración        | Amortiguación mínima               |

> **Conclusión pilas:** todos los activos tienen IAP > 1, lo que significa que el mínimo de rendimiento
> ocurre *después* de terminada la ventana — las pilas efectivamente absorben parte del impacto
> durante la ventana. La caída visible en producción es un efecto **diferido**, no inmediato.
>
> SAG2 tiene el IAP más alto: su pila tiene la mayor capacidad de absorción relativa.
> UNITARIO tiene el menor IAP (1.85): es el que menos se beneficia de stock de pila.

---

## 4. Elasticidad Operacional

**¿Cuánto % cae el rendimiento por cada hora adicional de ventana?**

| Activo   | Elasticidad (% / hora) | Mayor impacto en...   |
|----------|------------------------|-----------------------|
| SAG2     | **13.73 %/h**          | Ventanas 2h (22.4%/h) |
| SAG1     | **12.22 %/h**          | Ventanas 2h (20.4%/h) |
| PMC      | **11.45 %/h**          | Ventanas 2h (14.3%/h) |
| UNITARIO |  **5.62 %/h**          | Ventanas 4h (5.6%/h)  |

> La elasticidad es **decreciente con la duración**: la primera hora de ventana tiene el mayor impacto
> marginal porque coincide con el agotamiento inicial de pila. Las horas siguientes generan pérdidas
> absolutas mayores en toneladas pero menores en % marginal.
>
> SAG2 es el activo con mayor elasticidad: **cada hora de ventana T8 cuesta ~13.7% de su rendimiento**.

---

## 5. Simulación de Escenarios

Los escenarios parten desde el estado actual (137k ton perdidas en el período).

| Escenario | Descripción | Ahorro (ton) | Ahorro (%) | Val. Cu (USD/año) |
|-----------|-------------|--------------|------------|--------------------|
| **A** — Eliminar 12h | Reasignar tareas de 12h a paradas programadas | **24.7 kt** | 18% | **$5,289K** |
| **B** — Reducir 12h → 8h | Optimizar ejecución, reducir MTTR | **8.6 kt** | 6% | **$1,840K** |
| **C** — Reducir 8h → 4h | Donde viable, ventanas menores | **14.7 kt** | 11% | **$3,144K** |
| **D** — Mover a turno noche | Relocalizar inicio ventana 2h antes del valle | **34.2 kt** | 25% | **$7,311K** |

> **Escenario de mayor impacto:** D — Mover a turno noche (deman
> ahorra 34.2k ton, equivalente a ~USD 7,311K/año.

> **Nota sobre Escenario A:** No implica eliminar el mantenimiento, sino redistribuirlo en paradas
> programadas mayores donde el costo de producción parada ya está contemplado.

---

## 6. Optimización de Stock de Pilas

**¿Cuántas horas de autonomía se necesitan para retrasar la caída >10%?**

Cuando T8 se detiene, los molinos consumen el stock de pila. El IAP mide cuántas veces la
duración de la ventana alcanza a mantener el TPH antes de que la caída sea evidente.
Para una ventana 4h (la más frecuente), el mínimo llega ~10h después del inicio.

Estimación de stock mínimo recomendado:

| Activo   | Duración típica | IAP  | Buffer necesario | Stock recomendado |
|----------|-----------------|------|------------------|-------------------|
| SAG2     | 4h              | 2.90 | 11.6h            | +20% sobre operativo |
| SAG1     | 4h              | 2.75 | 11.0h            | +20% sobre operativo |
| PMC      | 4h              | 2.45 | 9.8h             | +15% sobre operativo |
| UNITARIO | 4h              | 1.85 | 7.4h             | +10% sobre operativo |

> Mayor stock previo a la ventana = más horas de autonomía antes de que la caída sea visible.
> El stock NO elimina el impacto post-ventana (la recuperación no depende del nivel de pila).
> La palanca es el stock **al momento de inicio** de la ventana T8.

---

## 7. Curvas Estratégicas y Punto de Quiebre

La curva Duración vs Caída muestra un patrón crítico:

- Entre **2h y 4h**: la caída sube solo 3.4pp (34.9% → 38.3%) — **bajo costo marginal**
- Entre **4h y 12h**: la caída escala con el tiempo — **alto costo marginal absoluto**
- El **punto de quiebre operacional** está en **4h**:
  - Hasta 4h: caída ≈38%, pérdida ≈2,507 ton/evento, recuperación ≈7-10h
  - De 4h a 12h: pérdida salta a 8,242 ton/evento (+3.3×), recuperación ≈14h

**Duración máxima recomendable operacionalmente: 4 horas.**

---

## 8. Forecast de Impacto por Evento Futuro

Si se programa una ventana T8, la pérdida esperada es:

| Duración | SAG1     | SAG2      | PMC      | UNITARIO |
|----------|----------|-----------|----------|----------|
| 2h       | ~881 ton | ~1,906 ton| ~330 ton | ~99 ton  |
| 4h       | ~1,567 ton| ~3,365 ton| ~986 ton | ~705 ton |
| 8h       | ~3,201 ton| ~5,750 ton| ~2,005 ton| ~1,234 ton |
| 12h      | ~4,826 ton| ~8,138 ton| ~3,560 ton| ~1,378 ton |

> Cálculo: Baseline × Duración × Caída%.
> Usar estos valores para priorizar la programación y el aviso anticipado a operaciones.

---

## 9. Respuestas Cuantitativas a las 8 Preguntas Clave

### 1. ¿Cuál es el verdadero costo operacional de Teniente 8?
**137k toneladas perdidas en 5.5 meses (≈0.30M ton/año).**
Valor referencial: USD 13,403K en el período / **USD 29,243K anualizados**.
Las 72 ventanas T8 costan un promedio de **2.01k ton por evento**.

### 2. ¿Qué activo merece atención prioritaria?
**SAG2** por volumen absoluto (61.7k ton perdidas, 42.7% caída promedio) y alta elasticidad (13.7%/h).
**PMC** por IVO (máxima vulnerabilidad combinada: alta caída + lenta recuperación).
Monitoreo dual: SAG2 para volumen, PMC para continuidad operacional.

### 3. ¿Qué ventanas deberían evitarse?
**Ventanas de 12h en cualquier activo.** Representan el 9.7% de los eventos pero generan
pérdidas de 8,242 ton/evento vs 2,507 ton en ventanas de 4h.
Específicamente: **ventanas 12h en SAG2** son las más destructivas (hasta 88.7% de caída en el peor evento).

### 4. ¿Qué duración es operacionalmente aceptable?
**≤ 4 horas.** El punto de quiebre en la curva duración-pérdida está en 4h.
Hasta 4h la relación caída/hora es manejable (~38% caída, 7-10h recuperación).

### 5. ¿Cuál es el máximo tiempo de ventana recomendable?
**4 horas como estándar. 8 horas como máximo excepcional con protocolo activo.**
Para ventanas >8h, evaluar alternativa de parada programada mayor (con menor impacto relativo).

### 6. ¿Qué beneficio tendría aumentar stock de pila?
**Reducción de la caída durante la ventana** (efecto amortiguador).
Con +20% de stock previo a cada ventana: se estima una reducción de 5-10% en la caída durante la
ventana activa. El stock no reduce el tiempo de recuperación post-ventana.
**Beneficio más alto en SAG2 y SAG1** (IAP más alto = más sensibles al nivel de pila).

### 7. ¿Cuál es la mejor estrategia para mitigar pérdidas?
**Estrategia combinada (prioridad de implementación):**
1. Eliminar/redistribuir ventanas 12h → mayor ROI, menor esfuerzo operacional (Escenario A)
2. Programar inicio de ventana en turno noche cuando operativamente posible (Escenario D)
3. Asegurar nivel máximo de pila antes de cada ventana programada conocida
4. Reducir MTTR en trabajos de mantenimiento para acortar duración efectiva de ventana

### 8. ¿Qué acciones generarían el mayor retorno operacional?
**Acción 1 (mayor impacto):** Redistribuir las 7 ventanas de 12h anuales a paradas mayores.
Impacto estimado: **+34k ton recuperadas / año** =
~USD 7,311K/año.

**Acción 2 (más rápida de implementar):** Protocolo de nivel de pila previo a ventana T8 ≥4h.
Impacto estimado: reducción 5-10% en la caída durante la ventana = +5-10k ton/año.

**Acción 3 (mejora estructural):** Monitoreo en tiempo real de TPH durante ventana con alerta
temprana si caída supera 30% — permite activar compensación desde otro circuito.

---

## 10. Recomendaciones por Audiencia

### Para Operaciones Planta
- Implementar **protocolo de pila llena** previo a toda ventana T8 ≥4h programada
- Monitorear SAG2 y PMC con mayor frecuencia durante ventana y en las 12h posteriores
- Activar circuito alternativo de compensación si caída supera 35% durante ventana
- Registrar nivel de pila al inicio de cada ventana (dato no disponible actualmente)

### Para Planificación
- Priorizar ventanas ≤4h en la programación de mantenimiento Teniente 8
- Para trabajos que requieren ≥12h: agrupar en paradas programadas mayores (no ventanas T8)
- Considerar inicio de ventana a las **10:00** (vs actual 12:00 para 4h) para reducir
  impacto en turno de mayor demanda (14:00-16:00)
- Evitar ventanas 12h en SAG2 — el peor evento registrado fue 88.7% de caída

### Para PAM Mantto
- Documentar duración real efectiva de cada ventana (para calibrar modelos)
- Evaluar si es posible reducir MTTR en trabajos típicos 12h → objetivo 8h
- Identificar qué tareas de 12h son realmente inevitables vs planificables en parada mayor
- Proporcionar aviso previo de ventana con **≥48h de anticipación** para que operaciones
  prepare nivel de pila

### Para Optimización de Activos
- Analizar por qué UNITARIO tiene menor IAP (1.85) — posible diseño de pila diferente
  o menor capacidad de almacenamiento: evaluar si una inversión en capacidad de pila tiene ROI
- PMC: el IVO más alto sugiere evaluar si hay oportunidad de mejora en configuración
  operacional para acelerar recuperación post-ventana
- Cuantificar el costo de aumentar capacidad de pila en SAG1/SAG2 vs beneficio anual

### Para CIO
- El costo anualizado de las ventanas T8 es **USD 29,243K/año** (referencial)
- La oportunidad de mejora más alta con menor inversión: redistribuir ventanas 12h
  → **USD 7,311K/año de valor recuperable**
- La acción de mayor ROI no requiere inversión capital — requiere coordinación PAM-Operaciones
- Recomendación inmediata: establecer **límite operacional de 8h para ventanas T8**,
  con excepción documentada para casos que requieran 12h

---

## Anexo: Figuras disponibles

Las siguientes figuras se encuentran en `outputs/figures/prescriptivo/`:

| Archivo | Contenido |
|---------|-----------|
| P1_IVO_Resiliencia.png | Ranking IVO, IR y mapa de vulnerabilidad |
| P2_Toneladas_Perdidas.png | Pérdida en ton por activo y duración |
| P3_Curvas_Estrategicas.png | Duración vs caída / recuperación / toneladas |
| P4_Elasticidad.png | %TPH perdido por hora de ventana |
| P5_Escenarios.png | Simulación escenarios A-D |
| P6_Amortiguacion_Pilas.png | IAP — evidencia de amortiguación |
| P7_Forecast_Impacto.png | Tabla y heatmap de pérdida esperada |
| P8_Panel_Ejecutivo.png | Panel diagnóstico integrado |

---

*Generado automáticamente — 16/06/2026 12:58*
*Sistema: Event Study Industrial T8 / Analítica Prescriptiva — Plataforma CIO DET*
