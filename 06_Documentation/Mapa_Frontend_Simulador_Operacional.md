# Cómo está armada la página del Simulador Operacional

> Guía de orientación para alguien que recién abre
> `05_Dashboard/pages/simulador_operacional.py` y quiere ubicarse: qué
> bloque es cada cosa, qué `id` de Dash le corresponde, y si tocar un
> control ahí vuelve a correr la simulación o solo cambia la vista.
>
> Describe la estructura del código (2026-07-14, tras el rediseño de
> navegación). No reemplaza abrir la app real con `python run_app.py`.

## Leyenda

| Color en este doc | Significa |
|---|---|
| 🟠 **físico** | Dispara `update_simulation` — vuelve a calcular el escenario |
| 🟢 **visual** | Solo navegación / cambia qué se muestra, no re-simula |
| ⚪ **estático** | No reactivo |

---

## 1. Orden real de la página (scroll de arriba hacia abajo)

```text
┌─ Barra de navegación sticky ──────────────────────────────┐
│ simulation-section-nav — fija arriba, 5 anclas <a href="#..">│
│ 🟢 Resumen · Operación · Gráficos · Escenario · Diagnóstico │
└────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ 1 · Resumen ────────────────────────── id: section-summary ┐
│ Cabecera de estado + cockpit 4 columnas                     │
│ 🟠 sim-summary-bar   🟠 kpi-column                           │
│   (Inventario · Producción · Riesgo · PAM)                  │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌─ 2 · Operación ──────────────────── id: section-stockpiles ┐
│ Banner ancho completo + grilla de hasta 3 columnas          │
│ 🟠 div-estado-general        (banner, ancho completo)       │
│ 🟠 div-autonomia-sag1/2                                     │
│ 🟠 div-recomendacion-corta   } grilla 3 col / 2 filas        │
│ 🟠 div-recuperacion                                          │
│ 🟠 div-quick-win                                             │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌─ 3 · Gráficos ───────────────────────── id: section-charts ┐
│ EL BLOQUE CLAVE: selector y gráfico en la MISMA tarjeta      │
│ 🟢 sim-main-view       (10 vistas: Inventario/TPH/Riesgo/…)  │
│ 🟢 btn-expand-main · btn-reset-zoom                          │
│ 🟠 graph-main          ← lo que controla sim-main-view       │
│ 🟢 graph-qin-qout      (colapsable, "¿Por qué crece/drena?") │
│ 🟠 div-scenario-compare                                      │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌─ 4 · Escenario ───────┬─ 5 · Diagnóstico ───────────────────┐
│ id: section-controls  │ id: section-diagnostics             │
│                       │                                     │
│ Sidebar de controles: │ Acordeón "Ver detalle técnico"       │
│ ctrl-duracion-t8      │ (colapsado por defecto):             │
│ ctrl-pila-sag1/2      │ 🟢 enlace "↑ Volver al gráfico"      │
│ ctrl-rate-sag1/2      │ 🟢 tabs Disponibilidad/Autonomía/    │
│ ctrl-bolas-sag1/2     │    Alimentación/Bolas                │
│ Acordeón "Avanzado"   │ 🟢 Sensibilidad Rate→Autonomía       │
│ (no calibrado,        │ 🟠 confiabilidad Monte Carlo         │
│  colapsado)           │                                     │
└───────────────────────┴─────────────────────────────────────┘

  ⬤↑  Botón flotante "Volver arriba" — fuera del flujo normal,
      aparece tras ~480px de scroll. JS puro en
      assets/back_to_top.js, no pasa por Dash.
```

---

## 2. Cómo circula un cambio: de un control a la pantalla

Casi todo lo que se ve en **Resumen**, **Operación** y **Gráficos** lo
escribe un único callback gigante, `update_simulation`. Cambiar de
pestaña de gráfico es la excepción notable: **no** vuelve a simular,
solo redibuja.

```text
Controles del sidebar                update_simulation()              Resultado en pantalla
(ctrl-pila-sag1,          ─────▶     corre                  ─────▶    graph-main, las 5
 ctrl-duracion-t8,                   simulate_scenario_cached(...)     tarjetas de Operación,
 ctrl-rate-sag2, ...)                 (el motor físico) y arma          div-scenario-compare...
                                       todas las tarjetas/gráficos       todo junto
                                       de una sola vez


sim-main-view                        ...pero NO re-simula
(cambiar la pestaña       ─────▶     reusa el resultado ya calculado
 de vista también es un               y solo cambia qué figura de
 Input de update_simulation)          graph-main se muestra
```

---

## 3. Vocabulario mínimo para leer el código

| Término | Qué es |
|---|---|
| `dbc.Card` / `dbc.CardBody` | La "caja" visual con borde y fondo que envuelve cada tarjeta — de Dash Bootstrap Components |
| `id="…"` | El nombre único de un componente. Los callbacks lo usan para saber qué leer o qué escribir — lo primero que hay que buscar con Ctrl+F |
| `@app.callback(...)` | Una función de Python que se re-ejecuta cuando cambia alguno de sus `Input`, y escribe en sus `Output` |
| `Input` vs `State` | `Input` dispara el callback al cambiar. `State` se lee pero no dispara nada por sí solo |
| `dcc.Graph` | Un gráfico Plotly interactivo. Su contenido vive en la prop `figure`, que un callback reemplaza entera |
| `dbc.Accordion` | Panel colapsable. `start_collapsed=True` significa que arranca cerrado la primera vez que se abre la página |

---

**Fuente:** `05_Dashboard/pages/simulador_operacional.py`,
`05_Dashboard/components/navigation.py`,
`05_Dashboard/assets/styles.css` — rediseño de navegación 2026-07-14
(ver `04_Reports/Technical/20260714_Rediseno_Navegacion_UX_Simulador.md`).
