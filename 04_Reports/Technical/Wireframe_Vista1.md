# Wireframe — Vista 1 (Decisión Operacional, Usuario A)

**Fecha:** 2026-07-07
**Regla:** ≤6 elementos, toda la información crítica above the fold en 1920x1080, sin scroll.

---

## Layout (ASCII, proporciones relativas)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Simulador de Distribución de Moliendas SAG DET      Inteligencia Op. DET │ ← navbar (existe, sin cambios)
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  🔴  RÉGIMEN ACTIVO: T8 CORTA (4h) — INVENTARIO CRÍTICO           │    │  ← Elemento 1
│  │      (texto operacional, NUNCA el slug "t8_corta")                │    │     (100% ancho, altura ~15%)
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│  ┌────────────────────────────┐  ┌────────────────────────────────┐      │
│  │                            │  │                                  │      │
│  │   TIEMPO HASTA EVENTO      │  │   RECOMENDACIÓN PRINCIPAL         │      │  ← Elementos 2 y 3
│  │   CRÍTICO                  │  │                                  │      │     (2 columnas, ~35% alto)
│  │                            │  │   "Reducir SAG1 a 1200 TPH y      │      │
│  │      35 min                │  │    activar 2do MoBo en SAG2       │      │
│  │   hasta autonomía crítica  │  │    para proteger inventario"      │      │
│  │   SAG1                     │  │                                  │      │
│  │                            │  │   (1 sola oración, lenguaje       │      │
│  │   [fuente gigante, color   │  │    operacional, sin jerga)        │      │
│  │    semáforo]                │  │                                  │      │
│  └────────────────────────────┘  └────────────────────────────────┘      │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  🟡 CONFIABILIDAD: MEDIA                                          │    │  ← Elemento 4
│  │     Basado en eventos históricos similares — backtesting          │    │     (100% ancho, ~15% alto)
│  │     disponible pero fuera de tolerancia esperada                  │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  [ ▶ Ver comparación Actual vs Recomendado ]   [ Ver más detalle ]│    │  ← Elemento 5 y 6
│  └──────────────────────────────────────────────────────────────────┘    │     (botones, navegan a Vista 2/3/4)
│                                                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Especificación por elemento

| # | Elemento | Contenido | Color semáforo | Tamaño relativo |
|---|---|---|---|---|
| 1 | Régimen activo | Texto traducido (`REGIMEN_LABEL_JDS`, ya existe) + duración si aplica | Fondo del color del estado global (🔴 rojo = acción inmediata, 🟡 amarillo = atención, 🟢 verde = normal) | Franja completa, ~15% alto |
| 2 | Tiempo hasta evento crítico | Número grande + unidad (min/h) + qué evento (ej. "hasta autonomía crítica SAG1") | Rojo si <1h, amarillo si <4h, verde si no hay evento próximo | 50% ancho, ~35% alto |
| 3 | Recomendación principal | 1 oración en lenguaje operacional (no "SAG1=1200 TPH" crudo — frasear como acción: "Reducir SAG1 a...") | Neutro (azul de referencia), no es un estado de alarma | 50% ancho, ~35% alto |
| 4 | Confiabilidad | Semáforo (ya existe, `make_router_v2_card` simplificado) + 1 línea de razón (no "Basado en: N eventos · MAE...", sino "Datos históricos suficientes" / "Datos históricos insuficientes para este escenario") | 🟢🟡🔴 según backtesting real (regla ya implementada: nunca ALTA si MAE fuera de tolerancia) | 100% ancho, ~15% alto |
| 5 | Botón "Ver comparación" | Navega a Vista 2 (Actual vs Recomendado) | Azul (acción de navegación, no alarma) | Botón, ~10% alto |
| 6 | Botón "Ver más detalle" | Navega a Vista 3/4 (explicación + técnico) | Gris/azul (secundario) | Botón, ~10% alto |

---

## Qué se saca de Vista 1 (vs. lo que existe hoy en la página única actual)

```
Franja KPI completa de 7 tarjetas       → se reduce a los 2 valores críticos (tiempo + recomendación)
Badge "V3 Óptimo [...] / P(safe)..."    → fuera, va a Vista 4 tras click
Badge "MC V3: P(seg)=..."               → fuera, va a Vista 4 tras click
Cockpit (Inventario/Producción/etc.)    → fuera, va a Vista 3
Tabla Actual vs Recomendado             → fuera, va a Vista 2 (botón dedicado)
Top-5 Configuraciones                   → fuera, va a Vista 4
Gráficos (pila, TPH, MC, sensibilidad)  → fuera, van a Vista 3/4
Sidebar de controles completo           → fuera de Vista 1; Vista 1 es de solo lectura,
                                           los controles viven en Vista 2 (modo "ajustar y comparar")
```

---

## Validación pendiente (no se puede hacer en este entorno)

Este wireframe **no está validado con el test de 10 segundos real** — ver `UX_Audit_Report.md` Sección 5. Es una propuesta estructurada según las reglas explícitas del skill (≤6 elementos, jerarquía por tamaño/color, sin jerga), no una vista ya probada con un Jefe de Sala real.
