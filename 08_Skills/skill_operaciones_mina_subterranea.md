# Skill: Operaciones Mina Subterránea — Teniente 8 y Sistema de Transporte

## Propósito

Guiar la interpretación operacional del sistema de transporte de mineral desde el interior
de la mina subterránea hasta las pilas de molienda, con foco en el rol de Teniente 8,
el ferrocarril y los impactos sobre el abastecimiento de mineral a los circuitos de molienda.

---

## 1. Sistema de Transporte — División El Teniente

### Teniente 8 (T8)
Nivel de extracción y transporte principal de mineral en la mina subterránea.

- Opera con ferrocarril de trocha métrica para transporte de mineral
- Alimenta principalmente las pilas de mineral grueso (SAG 1 y SAG 2)
- También aporta mineral fino a los circuitos convencionales (PMC y MUN)
- Realiza ventanas de mantenimiento planificadas (tipicamente 2-12 h cada 2-3 días)
- Ventanas mayores (MGA): 16-72 horas, generalmente en Marzo (MGA anual)

### Tipos de Ventana T8

| Tipo | Duración típica | Frecuencia |
|------|-----------------|------------|
| Ventana rutina | 2-4 h | 2-3 veces por semana |
| Ventana extendida | 6-12 h | 1-2 veces por mes |
| MGA (Mantención Mayor) | 16-72 h | 1 vez al año (Marzo) |

### Impacto por Tipo de Ventana

- **Ventana rutina (≤4h)**: pila absorbe, rendimiento molinos no varía significativamente
- **Ventana extendida (6-12h)**: stock de pila baja, posible leve caída en TPH
- **MGA (>16h)**: agotamiento de pila probable, caída severa de rendimiento esperable

---

## 2. Pilas de Mineral y Stock

Las pilas actúan como buffer entre la mina y la molienda.

### Capacidad operacional estimada
- **Pila SAG**: capacidad suficiente para 24-48 h de operación continua
- **Pila Convencional**: capacidad suficiente para 12-24 h de operación continua

### Indicadores de agotamiento
- TPH empieza a oscilar (mayor variabilidad)
- TPH cae sostenidamente por más de 2 horas
- Operadores reducen velocidad de alimentación manualmente

---

## 3. Ferrocarril Subterráneo

El ferrocarril transporta mineral desde los puntos de extracción hasta la planta de mineral.

- Puede operar de forma independiente a T8 en algunas configuraciones
- Cuando T8 está detenido, el ferrocarril también se detiene en la mayoría de los casos
- Distinción en PAM Mantto: buscar también filas con "FERROCARRIL" para completar análisis

---

## 4. Interpretación de PAM Mantto para T8

```python
# Palabras clave para identificar filas T8 en PAM Mantto
T8_KEYWORDS = [
    'teniente 8', 'teniente8', 't-8', 'teniente  8',
    'ferrocarril', 'tren mineral', 'ventana tunel'
]

# La fila T8 tiene horas planificadas por día en columnas G+ (índice 6+)
# valor = horas de mantención ese día
# 0 o None = sin mantención T8 ese día
```

---

## 5. Contexto Operacional para Modelos

Al construir features para predicción de TPH, incluir:

```python
# Horas desde última ventana T8
df['h_desde_ultima_t8'] = (df['fecha'] - df['ultima_t8_fin']).dt.total_seconds() / 3600

# Horas hasta próxima ventana T8 (si se conoce por PAM)
df['h_hasta_proxima_t8'] = (df['proxima_t8_inicio'] - df['fecha']).dt.total_seconds() / 3600

# Flag si hay ventana T8 en las próximas 24h
df['t8_proximas_24h'] = df['h_hasta_proxima_t8'] <= 24

# Duración de la última ventana T8 (proxy de severidad)
df['duracion_ultima_t8_h'] = ultima_ventana_duracion_horas
```

---

## 6. Glosario Operacional

| Término | Significado |
|---------|-------------|
| T8 | Teniente 8: nivel de extracción principal |
| MGA | Mantención General Anual (o Mayor) |
| PAM | Programa de Actividades de Mantenimiento |
| TPH | Toneladas por hora (Tons Per Hour) |
| TMS | Toneladas métricas secas |
| Pila | Stock de mineral previo a la molienda |
| Ventana | Período planificado de detención de un sistema |
| Corte | Detención no planificada |
| SAG | Semi-Autogenous Grinding |
| PMC | Planta de Molienda Convencional |
| MUN | Molino Unitario (Molino 13) |
---

## 7. Intensidad Diaria de T8

Ademas del contexto de ventana, construir la serie:

```text
fecha | horas_t8
```

desde la hoja `Ejecutivo Mensual` de PAM Mantto, usando la fila operacional:

```text
TENIENTE 8 | TENIENTE 8 | Ventana Tunel Principal
```

Regla critica:

- `horas_t8` es intensidad diaria continua
- no modelar Teniente 8 solo como `0/1`
- los dias sin ventana deben persistirse con `0`

Valores tipicos:

- `0h`
- `2h`
- `4h`
- `12h`
- en ventanas mayores tambien pueden aparecer `16h` o `24h`

### Hipotesis operacional

La senal relevante no es solo la ocurrencia de la ventana, sino su duracion efectiva:

- mas `horas_t8` implica menor reposicion de mineral
- mayor consumo relativo de pilas
- mayor probabilidad de caida de TPH
- recuperacion mas lenta en dias posteriores

### Fuente oficial para efecto gaviota

Cuando el objetivo sea monitoreo visual pre/post o "efecto gaviota":

1. usar PAM Mantto como fuente oficial de fechas y duraciones T8
2. leer la hoja `Ejecutivo Mensual`
3. detectar la fila por texto robusto:
   - `TENIENTE 8`
   - `VENTANA`
   - `TUNEL PRINCIPAL`
4. no hardcodear fechas
5. no inferir ventanas desde la caida de rendimiento
6. explicitar cuando un evento oficial queda fuera del rango analitico de rendimientos

Supuesto operacional permitido para esta iteracion visual:

- si el PAM entrega solo horas diarias, la ventana se puede representar como inicio a `00:00`
- la duracion usada para sombreado y alineamiento es `horas_t8`
- la interpretacion debe declararse en el resumen ejecutivo

### Regla para gaviota inteligente

Si el objetivo es detectar el comportamiento real en rendimientos:

- PAM define el dia del evento
- la serie 5 min define el retardo, el valle y la recuperacion
- el centro de la gaviota debe ser el `timestamp_minimo`
- una ventana corta puede no generar caida detectable si la pila amortigua el sistema
- una caida muy tardia debe revisarse como posible evento no relacionado si ocurre fuera del tramo plausible del efecto

---

## Changelog

- 2026-06-15: Se formaliza `horas_t8` como variable operacional continua diaria extraida desde PAM Mantto y se prohibe tratar T8 solo como evento binario.
- 2026-06-15: Se establece PAM Mantto como fuente oficial para el efecto gaviota y se prohibe inferir ventanas T8 desde rendimientos.
- 2026-06-15: Se formaliza que el centro del efecto gaviota debe alinearse al minimo observado en la serie temporal y no al inicio del dia PAM.
