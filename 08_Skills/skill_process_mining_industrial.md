# Skill: Process Mining Industrial — Análisis de Flujos Operacionales

## Propósito

Guiar el análisis de procesos operacionales industriales mediante técnicas de process mining
y análisis de trayectorias de estado, aplicado a circuitos de molienda SAG y convencional.

---

## 1. Estados Operacionales

Definición de estados para cada activo de molienda:

```python
ESTADOS_OPERACIONALES = {
    'NORMAL'      : 'TPH > umbral y variabilidad baja (CV < 0.15)',
    'INESTABLE'   : 'TPH > umbral y variabilidad alta (CV >= 0.15)',
    'DEGRADADO'   : 'TPH > 0 pero < 50% del promedio histórico',
    'DETENIDO'    : 'TPH <= umbral (detención o dato inválido)',
    'RECUPERACION': 'TPH creciente post-detención (slope > 0, ventana 1h)',
    'ACELERACION' : 'TPH en subida rápida (post-evento, slope alto)',
}
```

---

## 2. Máquina de Estados

Transiciones válidas entre estados:

```
NORMAL      → INESTABLE    (aumento de variabilidad)
NORMAL      → DEGRADADO    (caída de nivel sostenida)
NORMAL      → DETENIDO     (caída brusca a cero)
INESTABLE   → NORMAL       (estabilización)
INESTABLE   → DEGRADADO    (deterioro)
INESTABLE   → DETENIDO     (detención desde estado inestable)
DEGRADADO   → RECUPERACION (inicio de recuperación)
DEGRADADO   → DETENIDO     (detención desde estado degradado)
DETENIDO    → RECUPERACION (reinicio)
RECUPERACION→ NORMAL       (recuperación completa)
RECUPERACION→ INESTABLE    (recuperación parcial)
```

---

## 3. Cálculo de Estado

```python
def asignar_estado(tph, tph_roll_mean, tph_roll_cv, tph_hist_median, threshold=50):
    if tph <= threshold:
        return 'DETENIDO'
    
    pct_hist = tph / tph_hist_median
    
    if pct_hist < 0.50:
        return 'DEGRADADO'
    
    if tph_roll_cv is not None and tph_roll_cv >= 0.15:
        return 'INESTABLE'
    
    return 'NORMAL'

# Detección de RECUPERACIÓN: requiere análisis de secuencia
# Estado previo = DETENIDO y TPH actual > threshold y creciente
```

---

## 4. KPIs de Proceso

```python
# Tiempo en cada estado
tiempo_por_estado = df.groupby(['activo', 'estado'])['fecha'].count() * (5/60)  # horas

# Número de ciclos DETENIDO→NORMAL (frecuencia de reinicio)
cambios_estado = df['estado'] != df['estado'].shift(1)
reinicios = ((df['estado'] == 'RECUPERACION') & cambios_estado).sum()

# Duración media de cada detención
detenciones = df[df['estado'] == 'DETENIDO'].groupby(
    (df['estado'] != df['estado'].shift()).cumsum()
)['fecha'].count() * (5/60)
duracion_media_detencion = detenciones.mean()

# Tasa de disponibilidad
disponibilidad = (df['estado'] != 'DETENIDO').mean() * 100
```

---

## 5. Análisis de Secuencias Pre/Post T8

Objetivo: identificar si las ventanas T8 cambian la distribución de estados.

```python
# Frecuencia de estados pre vs post T8
for contexto in ['pre', 'durante', 'post', 'normal']:
    dist = df.loc[df['contexto'] == contexto, 'estado'].value_counts(normalize=True)
    print(f'\n{contexto.upper()}:')
    print(dist)
```

---

## 6. Star Schema para BI

Para preparar migración a Power BI / Databricks / Fabric:

```python
# Fact_Rendimiento (granularidad: 5 minutos x activo)
fact_rendimiento = df[['fecha', 'activo_id', 'tph', 'ton', 'estado', 'contexto', 
                        'ventana_id', 'anomalia', 'cluster_op']].copy()

# Fact_Eventos_T8 (granularidad: ventana x activo)
fact_eventos_t8 = df_ventanas[['ventana_id', 'inicio', 'fin', 'duracion_h',
                                'activo_id', 'tph_pre', 'tph_post', 'delta_pct',
                                'impacto', 'igi_t8']].copy()

# Fact_Produccion (granularidad: día x activo)
fact_produccion = df_diario[['fecha', 'activo_id', 'ton_real', 'ton_prog', 
                              'desv_abs', 'desv_pct', 'horas_op']].copy()

# Dim_Fecha
dim_fecha = pd.DataFrame({'fecha': pd.date_range(inicio, fin, freq='5T')})
dim_fecha['año']      = dim_fecha['fecha'].dt.year
dim_fecha['mes']      = dim_fecha['fecha'].dt.month
dim_fecha['dia']      = dim_fecha['fecha'].dt.day
dim_fecha['hora']     = dim_fecha['fecha'].dt.hour
dim_fecha['semana']   = dim_fecha['fecha'].dt.isocalendar().week
dim_fecha['turno']    = pd.cut(dim_fecha['hora'], bins=[0,8,16,24], 
                                labels=['Noche','Dia','Tarde'])

# Dim_Activo
dim_activo = pd.DataFrame([
    {'activo_id': 'SAG1', 'nombre': 'Molino SAG 1', 'tipo': 'SAG',  'pila': 'SAG'},
    {'activo_id': 'SAG2', 'nombre': 'Molino SAG 2', 'tipo': 'SAG',  'pila': 'SAG'},
    {'activo_id': 'PMC',  'nombre': 'Molienda Convencional (1-12)', 'tipo': 'Convencional', 'pila': 'Conv'},
    {'activo_id': 'MUN',  'nombre': 'Molino Unitario (13)', 'tipo': 'Unitario', 'pila': 'Conv'},
])

# Dim_Evento
dim_evento = pd.DataFrame([
    {'tipo_evento': 'VENTANA_T8',     'descripcion': 'Mantención Teniente 8'},
    {'tipo_evento': 'DETENCIÓN',      'descripcion': 'Detención de activo'},
    {'tipo_evento': 'RECUPERACION',   'descripcion': 'Recuperación post evento'},
    {'tipo_evento': 'ANOMALIA',       'descripcion': 'Comportamiento anómalo detectado'},
])
```
