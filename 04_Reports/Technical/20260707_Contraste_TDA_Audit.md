# Auditoría de Contraste — Tema TDA (oscuro)

**Fecha:** 2026-07-07
**Evidencia:** capturas de pantalla reales enviadas por el usuario tras la conversión a tema oscuro TDA (turno anterior de esta sesión).

---

## Regla de prueba usada

> ¿Se puede leer claramente a 1 metro de distancia sin esfuerzo visual?

Aplicada por inspección directa de las capturas + lectura de código (no hay navegador en este entorno para medir contraste real con una herramienta — ver limitación en la Fase 6 más abajo).

---

## Bugs de contraste encontrados y corregidos

| # | Elemento | Problema real (evidencia en captura) | Causa raíz | Corrección |
|---|---|---|---|---|
| 1 | Tarjeta "Estado del Escenario" | Bloque blanco enorme, texto casi invisible | `dbc.Card` sin `backgroundColor` — caía al blanco por defecto de Bootstrap | `backgroundColor: BG_CARD` + borde |
| 2 | Barras IRO (Inventario/Autonomía/Rate/T8/Correa) | Invisibles / **rompían el callback con error 500** al renderizarse | `dbc.Progress(..., bar_style=...)` — prop inexistente en dash-bootstrap-components 2.0.4, lanzaba `TypeError` en cada carga | Cambiado a `color="success"/"warning"/"danger"` (nombres Bootstrap válidos) |
| 3 | Opciones de RadioItems/Switch en sidebar ("Ventana T8", "Turno inicial", "SAG1/SAG2", etc.) | Texto de las opciones prácticamente invisible — solo se veían los círculos/toggles, no las etiquetas | Bootstrap 5 no hereda `color` de `body` en `.form-check-label` — usa su propia variable `--bs-body-color` con mayor especificidad, aún en tema claro por defecto | Override de `--bs-body-color`, `--bs-form-check-label-color` y `.form-check-label { color: ... !important }` en `:root` |
| 4 | Headers de accordion colapsados ("Bolas", "Pilas", "Mantenciones") | Texto muy tenue, casi ilegible | Mismo problema: `--bs-accordion-btn-color` de Bootstrap no leía la variable custom `--azul` | Override de `--bs-accordion-*` en `:root` + filtro CSS para invertir el ícono chevron (por defecto oscuro, invisible en fondo oscuro) |
| 5 | Filas de la tabla "Actual vs Recomendado" (MoBo, Autonomía, Pila Final, Toneladas aparecían más tenues que SAG1 TPH/SAG2 TPH/Riesgo) | Contraste inconsistente entre filas | `dbc.Table` sin `color` explícito por celda usa `--bs-table-color`/`--bs-table-striped-*`, no configuradas para tema oscuro | Override de `--bs-table-*` en `:root` |
| 6 | Tabla "Planificador de Turno" (gráfico Plotly `go.Table`) | Contenido "lavado"/apenas visible | Celdas con `fill_color="white"` literal + encabezado `fill_color=AZUL` (ya reasignado a color claro tras la conversión TDA) + `font=dict(color="white")` → **texto blanco sobre fondo casi blanco en el encabezado** | Celdas y encabezado recoloreados con la paleta oscura (`PLOT_BG`, `#123059`, texto `AZUL` claro) |
| 7 | Gráfico "¿Cuándo podría aparecer un problema?" (casi vacío en la captura) | Solo se ve una línea roja fina abajo | **Investigado — no es bug de contraste.** Los colores de las 4 series están correctamente diferenciados (rojo/naranja/azul claro/azul, sólido/punteado); el escenario capturado simplemente tiene probabilidad de vaciado/overflow cercana a 0% durante casi todo el horizonte — la curva real es plana cerca del eje X. Confirmado revisando el código de trazado, no se encontró ningún color coincidiendo con el fondo. |

---

## Elementos que SÍ tenían buen contraste (no se tocaron)

- "Mapa de Cuellos de Botella" (barras verde/rojo con texto legible) — correcto de fábrica.
- Franja KPI superior (Producción/PAM/Autonomía/Riesgo/Confiabilidad/Cuello de botella) — semáforo y valores grandes ya legibles tras el trabajo de la sesión anterior.
- "¿Por qué puedo confiar en esta recomendación?" y el gráfico de rango P10-P90 — colores explícitos ya correctos.

---

## Causa raíz común (para prevenir recurrencia)

Los bugs #3, #4 y #5 comparten la misma causa: **Bootstrap 5 no propaga el color de `body` a sus componentes** — cada familia de componentes (`form-check`, `accordion`, `table`, `card`) lee sus propias variables CSS (`--bs-*`), definidas por el tema `dbc.themes.BOOTSTRAP` para modo claro. Un simple `body { color: ... }` no alcanza. La corrección de raíz fue sobreescribir ese set completo de variables Bootstrap en `:root` (ver `assets/styles.css`), en vez de parchar componente por componente — evita que aparezcan más bugs de este mismo tipo en partes del código no auditadas todavía (ej. `page_riesgo_operacional` en `app.py`, que sigue en tema claro, ver limitación abajo).

---

## Limitaciones declaradas

- **No se generaron capturas antes/después reales** (Fase 11) — no hay navegador en este entorno. La verificación se hizo leyendo las capturas que el usuario proporcionó (evidencia real) y confirmando cada corrección contra el servidor Dash corriendo vía HTTP (no visualmente).
- **No se midió el ratio WCAG exacto** (Fase 6) — no hay herramienta de cálculo de contraste en este entorno. Los pares de color usados (`#F0F4FA` sobre `#0F2647`, `#8896AF` sobre `#0F2647`) son de alto contraste a simple vista (texto casi blanco sobre azul muy oscuro), pero esto es una estimación visual, no una medición certificada.
- **`page_riesgo_operacional()`** (página "¿Qué pasa si...?", dentro de `app.py`) no fue auditada en esta pasada — sigue con estilos de tema claro. No hay evidencia (captura) de que tenga los mismos bugs, pero tampoco se confirmó que no los tenga.
