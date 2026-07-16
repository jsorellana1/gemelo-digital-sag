# Resumen Ejecutivo — Análisis de Rendimientos SAG / PMC / Unitario
## Evaluación Pre / Durante / Post Ventanas Teniente 8

---

## Alcance del Análisis

| Campo | Detalle |
|-------|---------|
| **Período** | Enero 2026 → Junio 2026 |
| **Activos** | SAG 1, SAG 2, PMC (Mol. 1-12), MUN (Mol. 13) |
| **Granularidad** | Cada 5 minutos (rendimientos reales) + datos diarios (PAM) |
| **Registros procesados** | ~47,500 registros de rendimiento real |
| **Meses de programa** | 6 archivos PAM Producción + 6 archivos PAM Mantto |

---

## Fuentes de Datos

| Fuente | Tipo | Contenido |
|--------|------|-----------|
| `PAM_Produccion/*.xlsx` | Excel mensual | Producción diaria programada por activo (TMS) |
| `PAM_Mantto/*.xlsx` | Excel mensual | Mantenimientos planificados — incluye ventanas T8 |
| `rendimientos_coef - copia.xlsx` | Excel único | TPH real cada 5 minutos: SAG1, SAG2, MUN, Convencional |

---

## Ventanas Teniente 8 Detectadas

Las ventanas se identificaron automáticamente desde la fila "TENIENTE 8" de cada archivo PAM Mantto (hoja "Ejecutivo Mensual"), columnas G en adelante (días del mes). Las horas registradas corresponden a mantención planificada de la Ventana Tunel Principal.

| Mes | Días con T8 | Horas planificadas |
|-----|-------------|-------------------|
| Enero 2026 | 15 días | ~68 h |
| Febrero 2026 | 11 días | ~50 h |
| Marzo 2026 | 14 días | ~108 h *(ventana mayor: días 17-20, 72 h)* |
| Abril 2026 | 10 días | ~60 h |
| Mayo 2026 | 11 días | ~52 h |
| Junio 2026 | 11 días | ~52 h |

---

## Preguntas Analíticas Respondidas

### ¿Qué molinos pierden más rendimiento después de una ventana T8?
→ Calculado en **Tabla 2** del notebook: `delta_pct = (TPH_post - TPH_pre) / TPH_pre`. Los activos con delta más negativo son los más afectados. La clasificación de impacto (Sin/Leve/Medio/Alto) permite priorización operacional.

### ¿Cuánto demora cada activo en recuperar su rendimiento normal?
→ **Tabla 3** del notebook: tiempo en horas hasta alcanzar el 80%, 90% y 95% del TPH pre-ventana. Se usa suavizado rolling de 1 hora para evitar falsos positivos.

### ¿Existe evidencia de consumo progresivo de pilas durante la ventana?
→ **Gráfico 5** y hoja `Stock_Pila` del Excel: el índice de stock desciende durante la ventana cuando el consumo de los molinos continúa sin reposición. La pendiente de caída varía según la duración de la ventana.

### ¿Qué activos son más sensibles a restricciones de alimentación?
→ **Gráfico 6 (Heatmap)** y **Tabla 5** del notebook: ranking de activos por delta TPH% promedio acumulado a través de todas las ventanas.

### ¿Cuánto se desvía la producción real respecto del programa?
→ **Tabla 4** del notebook: comparación toneladas reales vs programadas, por activo y en total. Desviación en TMS y porcentaje.

### ¿Qué ventanas generan mayor impacto operacional?
→ La ventana de Marzo 2026 (días 17-20, ~72 h) es la de mayor duración planificada y potencialmente la de mayor impacto. Confirmado en **Gráfico 8** (zoom ventana mayor).

---

## Supuestos Operacionales Clave

1. **TPH ≤ 50** → activo detenido (valores pequeños en el archivo de rendimientos corresponden a coeficientes, no a TPH real)
2. **Ventana PRE/POST**: 24 horas antes del inicio / 24 horas después del fin de cada ventana T8
3. **Agrupación de ventanas**: días separados por ≤ 2 días se consolidan en una misma ventana continua
4. **Modelo de pila**: alimentación = 0 durante T8; fuera de T8 = tasa histórica mediana del activo
5. **SAG1 y SAG2** → consumen pila SAG (mineral grueso)
6. **PMC y MUN** → consumen pila convencional (mineral fino)
7. **1 período = 5 min = 1/12 hora** → `ton_período = TPH × (5/60)`

---

## Entregables Generados

| Archivo | Descripción |
|---------|-------------|
| `analisis_rendimientos_sag_pmc_unitario.ipynb` | Notebook principal completo y reproducible |
| `output_rendimientos_pre_post_t8.xlsx` | Excel con 8 hojas de resultados |
| `figures_rendimientos/` | Carpeta con 8 gráficos ejecutivos en PNG |
| `resumen_ejecutivo_rendimientos.md` | Este documento |

### Hojas del Excel de salida

| Hoja | Contenido |
|------|-----------|
| `Resumen_Diario` | Producción real y programa diario por activo |
| `Ventanas_T8` | Análisis pre/durante/post por cada ventana |
| `Recuperacion` | Horas hasta 80%/90%/95% de recuperación |
| `Resumen_Global` | Estadísticas acumuladas por activo |
| `Prog_vs_Real` | Comparación programa vs producción real |
| `Rendimientos_5min` | Muestra de datos crudos con contexto asignado |
| `T8_Calendario` | Días con mantención T8 planificada |
| `Stock_Pila` | Serie de índice de stock estimado por ventana |

### Gráficos generados

| Archivo | Descripción |
|---------|-------------|
| `01_serie_temporal_tph.png` | Serie TPH por activo con ventanas T8 sombreadas |
| `02_produccion_vs_programa.png` | Barras diarias: real vs programa |
| `03_tph_pre_durante_post.png` | Boxplot distribución TPH por contexto |
| `04_toneladas_acumuladas.png` | Curvas acumuladas de producción |
| `05_indice_stock_pila.png` | Evolución estimada del stock de pila |
| `06_heatmap_impacto.png` | Heatmap activo × ventana |
| `07_ranking_desviacion.png` | Ranking desviación programa vs real |
| `08_zoom_ventana_mayor.png` | Zoom en ventana T8 de mayor duración |

---

## Cómo Reproducir el Análisis

```bash
# 1. Abrir Jupyter
jupyter notebook analisis_rendimientos_sag_pmc_unitario.ipynb

# 2. Ejecutar todas las celdas
# Kernel > Restart & Run All

# 3. Los resultados se actualizan automáticamente si se agregan
#    nuevos archivos en PAM_Produccion/ o PAM_Mantto/
```

Para agregar nuevos meses: copiar el Excel en la carpeta correspondiente y re-ejecutar el notebook completo. No se requiere ningún cambio de código.

---

*Análisis generado el 2026-06-15. Contacto: juanorellana.g@gmail.com*

---

## Nueva Seccion Critica - Modelamiento de Teniente 8 como Variable Operacional

En esta version del analisis, **Teniente 8 deja de modelarse solo como evento binario** y pasa a tratarse como una variable continua diaria:

```text
fecha | horas_t8
```

La serie maestra cubre el periodo **2026-01-01 a 2026-06-14** y conserva tanto los dias sin ventana (`0h`) como los dias con intensidad positiva (`2h`, `4h`, `6h`, `8h`, `12h`, `16h`, `24h`).

### Hallazgos ejecutivos

1. **Elasticidad lineal mismo dia (`TPH ~ horas_t8`)**
   - SAG1: **-8.17 TPH/h**
   - SAG2: **-17.66 TPH/h**
   - PMC: **-16.70 TPH/h**
   - MUN: **-2.32 TPH/h**
   - La relacion lineal simple es direccionalmente negativa en los cuatro activos, pero con baja explicacion (`R2` entre `0.009` y `0.022`), lo que sugiere comportamiento no lineal y/o diferido.

2. **Modelo temporal con exogena T8 (SARIMAX, TPH diario equivalente)**
   - SAG1: **-19.99 TPH/h** (`p=0.0005`)
   - SAG2: **-27.38 TPH/h** (`p=0.0019`)
   - PMC: **-16.88 TPH/h** (`p=0.0447`)
   - MUN: **-3.50 TPH/h** (`p=0.3712`)
   - Con control temporal, la senal exogena de T8 aparece mas clara en **SAG1, SAG2 y PMC**.

3. **Efecto diferido y recuperacion operacional**
   - SAG1 muestra arrastre negativo hasta **lag 2**, equivalente a una recuperacion estimada de **72 h**
   - SAG2, PMC y MUN no muestran evidencia robusta de arrastre mayor a **24 h** en los lags 1-3
   - En SAG2 aparece una senal fuerte en **lag 7**, pero debe interpretarse con cautela porque puede mezclar efecto real con periodicidad semanal

4. **Umbral critico**
   - El ajuste spline detecta para **SAG1** un umbral de deterioro cercano a **10 h de T8** para una perdida esperada de `~5%` a `~10%`
   - En SAG2, PMC y MUN **no aparece un umbral estable** con la muestra actual

5. **Impacto operativo por intensidad**
   - SAG1: frente a `0h`, una ventana de `12h` baja el TPH promedio en **-210.86 TPH** y reduce las toneladas diarias en **-8,796 TMS/dia**
   - SAG2: frente a `0h`, una ventana de `12h` baja el TPH promedio en **-239.64 TPH** y reduce las toneladas diarias en **-18,803.79 TMS/dia**
   - PMC: entre `0h` y `4h` cae **-106.76 TPH** y **-3,495.85 TMS/dia**
   - MUN: el impacto promedio es menor y mas volatil, salvo en eventos de `12h`

6. **Probabilidad bayesiana de caida >10% vs baseline 0h**
   - SAG1: `2h -> 10.5%`, `4h -> 32.5%`, `12h -> 40.0%`
   - SAG2: `2h -> 15.8%`, `4h -> 27.5%`, `12h -> 60.0%`
   - PMC: `2h -> 36.8%`, `4h -> 52.5%`, `12h -> 40.0%`
   - MUN: `2h -> 5.3%`, `4h -> 7.5%`, `12h -> 40.0%`

7. **Nuevo KPI estrategico - IST8**
   - PMC: **54.05 TPH perdidos por hora T8**
   - SAG2: **50.00 TPH/h**
   - SAG1: **21.41 TPH/h**
   - MUN: **4.94 TPH/h**

### Lectura ejecutiva

- **Activo mas vulnerable por IST8:** `PMC`
- **Activo con mayor costo esperado en ventanas severas:** `SAG2`
- **Activo con recuperacion mas lenta:** `SAG1`
- **Activo menos sensible en promedio:** `MUN`

### Entregables complementarios

- `outputs/excel/Analisis_T8_Intensidad.xlsx`
- `outputs/reports/Analisis_T8_Intensidad.md`
- `outputs/figures/T8_dosis_respuesta.png`
- `outputs/figures/T8_efecto_lags.png`

### Cautelas metodologicas

- Los niveles `12h`, `16h` y `24h` tienen baja frecuencia muestral
- El `Indice_Consumo_Pila` generado es un **proxy operacional**, no una medicion directa de stock fisico
- La relacion T8 -> rendimiento no es puramente lineal y conviene mantener ambos enfoques: lineal explicativo + temporal/exogeno
