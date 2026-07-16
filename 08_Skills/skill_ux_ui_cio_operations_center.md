# skill_ux_ui_cio_operations_center

## Rol
Especialista en UX/UI para Centros Integrados de Operaciones (CIO) y dashboards de monitoreo industrial — División El Teniente.

## Principios de diseño CIO

### Jerarquía visual
1. **FRAG actual** — número prominente, color según severidad, arriba izquierda
2. **Top RC** — máximo 5, nombre + valor + tendencia
3. **Tendencia** — gráfico lineal secundario, no protagonista
4. **Detalles** — tablas con hover, accesibles sin sobrecargar la vista

### Semáforo FRAG (umbrales del modelo)
| FRAG | Severidad | Color hex | Texto |
|------|-----------|-----------|-------|
| >= 40% | ALTO | `#C13832` | Rojo — acción inmediata |
| 25–39% | MEDIO | `#F4AA00` | Amarillo — atención |
| < 25% | BAJO | `#168980` | Verde — normal |

### Layout tipo CIO
```
┌──────── sidebar 56px ─┬──────── header 56px charcoal ────────────────┐
│ Logo Codelco (orange) │ Título módulo            Usuario  Notif  Grid │
│ ⊞ Dashboard           ├─────────────────────────────────────────────────┤
│ ≡ RC Ranking          │                                                 │
│ ◎ Rondas              │  CONTENIDO PRINCIPAL (fondo #F5F5F5)           │
│ ↗ Historial           │                                                 │
│ ⚡ Explicabilidad      │                                                 │
│ ♥ Salud Modelo        │                                                 │
└───────────────────────┴─────────────────────────────────────────────────┘
```

### Componentes prohibidos
- Tablas > 8 columnas sin scroll horizontal
- Tooltips que bloquean lectura del dato
- Colores inventados fuera de la paleta Codelco/BI
- Decimales innecesarios (FRAG: 1 decimal, lambda: 3 decimales máx)

### Terminología operacional SAG obligatoria
Usar nombres reales del modelo, nunca inventar sectores:
- Molino SAG, Chancador Pebbles, Correas transportadoras
- Alimentación SAG, Descarga SAG, Sistema de lubricación
- Rajo Norte/Sur, Planta SAG

### Estado "Pipeline no ejecutado"
Cuando el pipeline FRAG no ha corrido, mostrar `<PipelineNotReady />`:
- Icono ⚙, texto explicativo en español, comando para ejecutar el pipeline
- NO mostrar datos en cero, NOT loading infinito

### Audiencia target
- **Supervisores HSEC** — no técnicos, leen el resultado, no el modelo
- **Analistas CIO** — necesitan drill-down y trazabilidad
- **Gerencia** — solo dashboard principal, KPI único FRAG

---

## Aplicación al Gemelo Digital Molienda SAG T8 (05_Dashboard)

Caso concreto de los principios anteriores, implementado en
`05_Dashboard/pages/simulador_operacional.py` — usar como referencia de
patrón, no reinventar desde cero:

### Centro de Control Operacional
Primera pantalla sin cambiar de tab: Gantt de disponibilidad (equivalente
al "Top RC" — qué está disponible ahora) + tarjeta semáforo "Estado del
Escenario" (equivalente al FRAG actual, pero calculado desde IRO + P(seguro)
Monte Carlo + autonomía mínima) + resumen ejecutivo (`sim-summary-bar`) +
banda de confianza de la recomendación (fan chart).

### Semáforo "Estado del Escenario" (equivalente al semáforo FRAG)
4 niveles en vez de 3, mapeados a `components/cards.py::make_estado_escenario_card`:
🟢 Seguro / 🟡 Atención / 🟠 Riesgo Moderado / 🔴 Riesgo Alto — combina IRO,
P(seguro) del último Monte Carlo, y autonomía mínima. **Limitación
conocida** (ver `04_Reports/Technical/20260702_UX_UI_Operational_Control_Center.md`,
sección "Caso 4"): usa el mínimo de autonomía sobre todo el horizonte
simulado, lo que puede converger a la misma categoría para pilas iniciales
muy distintas bajo rate sostenido — pendiente de recalibrar ventana de
evaluación.

### Riesgo Operacional dinámico
Nunca mostrar un gráfico de riesgo "congelado": todo output que dependa de
sliders del escenario debe colgar de `Input`, no `State`, en el callback
Dash correspondiente (lección aprendida: `run_monte_carlo` tenía los
parámetros de escenario como `State`, lo que hacía parecer "roto" el
gráfico de robustez — ver reporte citado arriba).

### Planificación por Turnos (Gantt + mantenciones)
Selector de turno (C 00-08 / A 08-16 / B 16-00) determina la hora de
reloj real (`engine/scheduler.py::TURNO_START_HOUR`) usada para re-etiquetar
todos los ejes "hora relativa" a "hora del día" real
(`hour_of_day_ticks`). Mantenciones programables por equipo se muestran en
el Gantt como estado `MANTTO` (naranjo/rojo según severidad), distinto de
`OFF` — nunca fusionar ambos estados visualmente, son causas distintas
(planificado vs. resultado del optimizador).
