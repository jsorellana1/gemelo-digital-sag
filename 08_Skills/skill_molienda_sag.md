# Skill: Especialista en Molienda SAG y Convencional — Codelco División El Teniente

## Propósito

Guiar el análisis técnico, interpretación operacional y modelamiento de los circuitos de molienda
SAG, convencional (PMC) y Molino Unitario (MUN), en el contexto de la Planta Concentradora
de División El Teniente de Codelco.

---

## 1. Descripción del Proceso

### Circuito SAG
Los molinos SAG (Semi-Autogenous Grinding) reciben mineral directamente desde las pilas de mineral
grueso abastecidas por Teniente 8 y el ferrocarril subterráneo.

- **SAG 1**: molienda primaria, mayor capacidad, alimentado desde pila SAG 1
- **SAG 2**: molienda primaria, paralela a SAG 1, alimentado desde pila SAG 2
- Capacidad típica: 1,500 – 2,400 TPH por molino cuando operando

### Circuito Convencional (PMC)
Los Molinos 1 al 12 operan en circuito convencional de bolas y barras. Reciben mineral del
circuito de chancado convencional.

- Capacidad típica: 80–200 TPH por molino (sumados: 600–1,700 TPH)
- Alta sensibilidad a granulometría de alimentación

### Molino Unitario (MUN / Molino 13)
Molino individual que puede operar como SAG reducido o convencional, según configuración.

- Puede aparecer como: `MUN`, `Molino Unitario`, `Molino 13`, `Molino MUN`
- Capacidad típica: 700–900 TPH cuando operando

---

## 2. Pilas de Mineral

| Pila | Abastece | Fuente |
|------|----------|--------|
| Pila SAG 1 | SAG 1 | Teniente 8 + Ferrocarril |
| Pila SAG 2 | SAG 2 | Teniente 8 + Ferrocarril |
| Pila Convencional | PMC + MUN | Sistema de chancado primario |

**Hipótesis operacional clave:** Cuando Teniente 8 detiene su operación (ventana de mantenimiento),
deja de abastecer mineral a las pilas. Las pilas compensan durante horas/días según stock disponible.
Cuando el stock se agota, el rendimiento de los molinos cae.

---

## 3. KPIs Operacionales

| KPI | Fórmula | Unidad |
|-----|---------|--------|
| Utilización | horas_op / horas_total × 100 | % |
| TPH medio | promedio(TPH) cuando TPH > umbral | TPH |
| TPH p50 | mediana(TPH) cuando operando | TPH |
| TPH p90 | percentil 90 cuando operando | TPH |
| Toneladas acumuladas | Σ(TPH × Δt) | TMS |
| Horas detenidas | Σ(periodos con TPH ≤ umbral) | h |
| Variabilidad | std(TPH) cuando operando | TPH |

**Umbral de detención:** TPH ≤ 50 → activo detenido o dato inválido.

---

## 4. Interpretación de Datos de Rendimiento

El archivo de rendimientos puede contener valores pequeños (~0.2–0.9) en lugar de TPH reales.
Estos valores son coeficientes de estado (no TPH) y deben filtrarse con el umbral.

```python
TPH_THRESHOLD = 50  # valores <= 50 = detenido o dato inválido
operando = df['tph'] > TPH_THRESHOLD
```

---

## 5. Efectos de Ventana T8

### Fase Pre-ventana
- Acumulación de stock en pila si el operador anticipa la detención
- TPH puede aumentar ligeramente por mayor disponibilidad de mineral

### Fase Durante-ventana
- Stock de pila se consume sin reposición
- TPH inicialmente estable, luego puede degradarse si el stock se agota
- La duración crítica varía por activo: SAG típicamente > 24h, MUN y PMC < 12h

### Fase Post-ventana
- Restablecimiento de alimentación
- Recuperación progresiva de TPH
- Tiempo hasta 80%: 2–8 horas (referencia operacional)
- Tiempo hasta 95%: 6–24 horas (referencia operacional)

---

## 6. Reglas de Análisis

1. **No comparar TPH absoluto entre activos sin normalizar** — capacidades son distintas
2. **Ventanas T8 frecuentes** (semanales) = estrés acumulativo sobre pilas
3. **La ventana de Marzo suele ser la más crítica** por mayor duración planificada (MGA)
4. **Delta TPH post-pre negativo = impacto real** — clasificar según magnitud:
   - < 5%: Sin impacto
   - 5–15%: Leve
   - 15–30%: Medio
   - > 30%: Alto

---

## 7. Relación con PAM Producción y PAM Mantto

- **PAM Producción / Hoja "Planta"**: producción diaria programada en TMS por activo
  - Columna C = SAG 1 | D = SAG 2 | E = MOL 1-12 (PMC) | F = MOL 13 (MUN)
  - Filas 6-36: días del mes (leer con `data_only=True`)
- **PAM Mantto / Hoja "Ejecutivo Mensual"**: horas de mantención por día
  - Fila con "TENIENTE 8" → columnas G+ = horas planificadas por día
---

## 8. Modelamiento Continuo de Teniente 8

Teniente 8 no debe tratarse solo como bandera binaria `en_ventana_t8`.

La variable maestra obligatoria es:

```text
fecha | horas_t8
```

Reglas:

1. `horas_t8` representa intensidad operacional diaria de la fila `TENIENTE 8 / Ventana Tunel Principal`
2. Los dias sin ventana deben quedar explicitamente con `0`
3. El analisis comparativo debe trabajar al menos con grupos `0h`, `2h`, `4h`, `12h`
4. Si existen valores mayores (`16h`, `24h`) deben conservarse para curva dosis-respuesta y umbrales
5. Las tablas diarias deben unirse con:
   - rendimientos reales
   - produccion programada
   - horas operando
   - detenciones
   - indicadores de recuperacion

### Elasticidad Operacional T8

Para cada activo (`SAG1`, `SAG2`, `PMC`, `MUN`) estimar:

```text
TPH ~ horas_t8
```

Interpretacion esperada:

```text
Cada hora adicional de T8 cambia X TPH en el activo.
```

### Indice de Sensibilidad Teniente 8

Definicion operativa recomendada:

```text
IST8 = perdida_tph_atribuible / horas_t8
```

Mayor `IST8` implica mayor vulnerabilidad del activo frente a restricciones de alimentacion desde T8.

### Umbrales

Buscar explicitamente:

- punto de quiebre entre `0-4h`
- zona de impacto severo `> 8h`
- diferencias entre circuito SAG y circuito Convencional

---

---

## 9. Correas de Alimentación de Pilas

Archivo fuente: `data/raw/Tonelajes_pila/correas_ton.xlsx`
- Resolución: 5 minutos | Rango: 2026-01-01 a 2026-06-16 | Filas: 48,108
- Columnas: `fecha`, `CV316`, `CV315`, `SAG2:Nivel_Pila`, `SAG:Nivel_Pila`

| Correa | Alimenta | Unidad |
|--------|----------|--------|
| CV315  | Pila SAG 1 | TPH (toneladas/hora) |
| CV316  | Pila SAG 2 | TPH (toneladas/hora) |
| SAG:Nivel_Pila | Nivel Pila SAG 1 | % |
| SAG2:Nivel_Pila | Nivel Pila SAG 2 | % |

Según diagramas de proceso:
- CV315 llega desde Alimentadores 3 y 4 → Pila SAG 1
- CV316 llega desde Alimentadores 5, 6 y 7 → Pila SAG 2

**Hipótesis física validable**: T8 detiene → correas bajan → pilas bajan → TPH cae (retardos medibles).

### Balance de Masa de Pila

```
Inventario(t) = Inventario(t-1) + Correa(t) - Consumo_SAG(t)
```

Consumo_SAG estimado = TPH_SAG × (5/60)  [toneladas en 5 minutos]

### Retardos esperados (a validar)

- `retardo_correa_pila`: tiempo entre caída de correa y caída de % pila
- `retardo_pila_tph`: tiempo entre caída de % pila y caída de TPH molino

### Umbrales críticos (a determinar)

- `umbral_critico_sag1`: % pila por debajo del cual TPH comienza a caer (SAG1)
- `umbral_critico_sag2`: % pila por debajo del cual TPH comienza a caer (SAG2)

---

## Changelog

- 2026-06-15: Se agrega modelamiento continuo de `horas_t8`, definicion de `IST8` y regla explicita de no tratar Teniente 8 como variable binaria.
- 2026-06-18: Se agrega sección 9 con datos de correas CV315/CV316 y nivel de pilas. Rutas, mapeo físico y fórmulas de balance de masa.
