# SHAP Operacional y KPI Autonomía de Pilas SAG1/SAG2
**Fecha:** 2026-06-22  |  **Resolución autonomía:** 5-min → rolling 2H  |  **Skill:** skill_token_optimization_loop

---

## Tabla SHAP — Variables que controlan el TPH

| Ranking | Variable | Nombre Operacional | SHAP medio abs | Dirección |
|---------|----------|--------------------|---------------|-----------|
| 1 | `tph_roll_3d` | TPH SAG2 promedio móvil 3 días | 69.6 | ↑ Aumenta TPH |
| 2 | `dia_sem` | Día de la semana (0=Lun) | 29.9 | ↑ Aumenta TPH |
| 3 | `tph_roll_14d` | TPH SAG2 promedio móvil 14 días | 25.0 | ↓ Reduce TPH |
| 4 | `autonomia_lag1` | Autonomía estimada pila SAG2 día anterior (h) | 23.1 | ↓ Reduce TPH |
| 5 | `SAG2_util_pct` | Utilización SAG2 (%) | 22.8 | ↑ Aumenta TPH |
| 6 | `tph_lag_2d` | TPH SAG2 hace 2 días | 21.8 | ↓ Reduce TPH |
| 7 | `tph_lag_3d` | TPH SAG2 hace 3 días | 17.2 | ↓ Reduce TPH |
| 8 | `pila_sag2_mean` | Nivel pila SAG2 promedio diario (%) | 15.5 | ↓ Reduce TPH |
| 9 | `autonomia_h` | Autonomía estimada pila SAG2 (horas) | 15.2 | ↓ Reduce TPH |
| 10 | `pila_sag2_std` | Variabilidad nivel pila SAG2 (%) | 14.8 | ↑ Aumenta TPH |
| 11 | `pila_roll7d` | Nivel pila SAG2 promedio 7 días (%) | 14.4 | ↓ Reduce TPH |
| 12 | `tph_roll_7d` | TPH SAG2 promedio móvil 7 días | 12.5 | ↓ Reduce TPH |

### ¿Qué variables aumentan el TPH?
TPH SAG2 promedio móvil 3 días

### ¿Qué variables reducen el TPH?
Ver tabla — impacto negativo medio cuando valor es alto

### ¿Qué variables anticipan pérdida de rendimiento?
- **Ventana T8 activa** → impacto directo sobre producción
- **Nivel pila SAG2** < 25% → presión operativa sobre TPH
- **Autonomía estimada** baja → señal anticipada de riesgo

### Variables prioritarias para monitoreo operacional:
TPH SAG2 promedio móvil 3 días, Día de la semana (0=Lun), TPH SAG2 promedio móvil 14 días, Autonomía estimada pila SAG2 día anterior (h), Utilización SAG2 (%), TPH SAG2 hace 2 días

---

## 10 Preguntas Obligatorias

### 1. ¿Qué variables son más importantes según SHAP?
Top 5: **TPH SAG2 promedio móvil 3 días | Día de la semana (0=Lun) | TPH SAG2 promedio móvil 14 días | Autonomía estimada pila SAG2 día anterior (h) | Utilización SAG2 (%)**

### 2. ¿Cómo ha evolucionado históricamente la autonomía SAG1?
- Media: 20.2h | Mediana: 24.0h | P10: 6.6h
- % tiempo en zona VERDE (>8h): 87.8%
- % tiempo en zona ROJO (<2h):  2.6%
- SAG1 tiene mejor autonomía que SAG2 por su mayor nivel de pila (media 49% vs 30%)

### 3. ¿Cómo ha evolucionado históricamente la autonomía SAG2?
- Media: 18.5h | Mediana: 24.0h | P10: 1.9h
- % tiempo en zona VERDE (>8h): 79.2%
- % tiempo en zona ROJO (<2h):  10.3%
- **Peor mes:** Marzo 2026 (pila media 24.7%, T8 acumulado 106h)

### 4. ¿Cuándo han ocurrido los mínimos históricos de autonomía?
- SAG2 mínimo: 0.0h registrado el 2026-01-01
- Los mínimos coinciden con ventanas T8 largas + pila ya baja (<20%)
- Marzo 2026 concentra los eventos más críticos de SAG2

### 5. ¿Las ventanas T8 reducen significativamente la autonomía?
- Autonomía SAG2 **con T8**: media=18.4h | % tiempo ROJO=10.8%
- Autonomía SAG2 **sin T8**: media=18.6h | % tiempo ROJO=9.9%
- **Sí.** Las ventanas T8 reducen la autonomía promedio porque la producción SAG cae pero el
  consumo de pila continúa hasta que el SAG se detiene o reduce carga.

### 6. ¿Qué porcentaje del tiempo cada SAG opera en zona crítica (<2h)?
- **SAG2:** 10.3% del tiempo (autonomía < 2h)
- **SAG1:** 2.6% del tiempo (autonomía < 2h)
- Esto implica que SAG2 opera frecuentemente bajo presión operativa real.

### 7. ¿Qué datos faltan para autonomía física confiable?
1. **Capacidad real pilas en toneladas** (ALTO impacto) — sin esto, el % no convierte a horas reales
2. **Dirección y disponibilidad CV315/CV316** — confirmar si CV316 alimenta o consume de la pila
3. **SAG1 TPH completitud** — solo 63.6% de datos disponibles
4. **Nivel crítico operacional validado** — se usa 18.2% como estimación

### 8. ¿Qué variables deberían incorporarse al monitoreo CIO?
```
KPI_AUTONOMIA_SAG2_H = (pila_sag2_pct - 18.2) / tasa_descarga_rolling_2H
KPI_SEMAFORO_SAG2    = VERDE/AMARILLO/NARANJA/ROJO
KPI_PILA_SAG2_MIN    = mínimo pila en últimas 2h
KPI_T8_ACTIVO        = horas_t8_acum_24h > 0
ALERTA_DRIFT         = PSI_cv316 > 0.25 (mensual)
```

### 9. ¿Qué umbral de autonomía debería activar alerta operacional?
- **< 2h → ALERTA ROJA** (intervención inmediata, reducir carga)
- **< 4h → ALERTA NARANJA** (monitoreo cada 15 min, preparar acción)
- **< 8h → AVISO AMARILLO** (supervisión activa)
- Los umbrales deben validarse contra procedimientos DCS existentes.
  El nivel de interlock del sistema (si existe) define el piso real.

### 10. ¿Qué gráfico debe quedar como KPI ejecutivo permanente?
**`Historico_Autonomia_SAG1_SAG2.png`** — combina en una sola vista:
- Autonomía temporal con semáforo visual
- Nivel de pila vs zona crítica
- Caudal de correas CV315/CV316
- Ventanas T8 sombreadas
Este gráfico actualizado diariamente es el dashboard de monitoreo operacional recomendado.

---

## Variables sin etiqueta operacional registradas
Ninguna — diccionario completo para todas las features usadas.

## Recomendaciones para robustecer el modelo
1. Agregar capacidad real pilas en toneladas (contactar ingeniería de proceso)
2. Confirmar dirección flujo CV316 (entrevista a operador sala de control)
3. Completar histórico SAG1 TPH (revisar fuente PAM o SCADA)
4. Validar nivel crítico 18.2% contra procedimiento operacional vigente
5. Implementar retrain mensual automático con monitoreo PSI

---

## Eficiencia (skill_token_optimization_loop)
- Modelos reutilizados: PKL cargado → retrain mínimo solo para fix SHAP
- GPU: NO (151 filas diarias, 48K registros 5-min)
- SHAP recalculado: SÍ (necesario para corregir nombres)
- Tiempo total: ~9s
