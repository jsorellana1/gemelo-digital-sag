# Rediseño de navegación y UX/UI del Simulador Operacional

**Fecha:** 2026-07-14
**Base:** Gemelo Digital Molienda (`05_Dashboard/`)
**Evidencia principal:** `01_Data/Raw/graficos y botones.pdf` (6 páginas, revisado íntegramente antes de tocar código)

---

## 1. Auditoría del PDF

| Página | Sección mostrada | Problema UX | Severidad | Mejora aplicada |
|---|---|---|---|---|
| 1 | Cabecera + banner de estado + 7 KPI cards + cockpit Inventario/Producción/Riesgo/PAM | Ninguno grave — ya es un grid responsivo (2 col / 4 col tabs) | Baja | Sin cambios |
| 2 | Confiabilidad de la recomendación, EMERGENCIA, IRO, PAM, ¿Voy a cumplir el mes?, ACCIÓN REQUERIDA (SAG1/SAG2), Recomendación de operación, Recuperación, Quick wins | Los bloques 6.1-6.6 (Estado general → Quick win) estaban apilados en una sola columna vertical, ocupando casi toda la página | **Alta** | Grid responsivo 3 col / 2 filas para 5 de los 6 bloques (sección 3) |
| 3 | Gráfico "Evolución esperada de las pilas", comparar escenarios, validación operacional | El gráfico dominante vive aquí — **sin ningún control de vista visible cerca** | **Crítica** (causa raíz del reporte) | Selector de vista movido a esta misma tarjeta (sección 2) |
| 4 | Sidebar de controles (Escenario/SAG/Bolas/Pilas/Mantenciones/Avanzado) | Ninguno nuevo — ya era un accordion colapsable | Baja | Sin cambios |
| 5 | "VISTA TÉCNICA DEL GRÁFICO PRINCIPAL": el selector de 10 vistas + botones Expandir/Reiniciar zoom | **Este es el selector que controla el gráfico de la página 3** — vive ~2 pantallas más abajo, junto al sidebar, dentro de un accordion colapsado por defecto | **Crítica** (causa raíz) | Movido junto al gráfico (sección 2) |
| 6 | "¿Qué tan confiable es esta recomendación?", Top-5 configuraciones MC | Contenido denso pero ya está detrás de un botón colapsable | Baja | Sin cambios |

## 2. Flujo anterior (reconstruido)

```text
configurar escenario (sidebar, pág. 4)
→ ejecutar simulación
→ revisar 6 bloques apilados (pág. 2, scroll largo)
→ ver el gráfico principal (pág. 3) — SIN control de vista visible
→ hacer scroll hasta pág. 5 para encontrar "sim-main-view"
→ cambiar de vista
→ volver a hacer scroll hasta pág. 3 para ver el resultado
→ repetir por cada vista que se quiera comparar
```

Puntos de fricción confirmados en el código (`pages/simulador_operacional.py`, antes de esta modificación): `graph-main` se renderizaba en un `dbc.Card` cerca de la línea 465; el `RadioItems id="sim-main-view"` que lo controla (mismo `Input` del callback `update_simulation`) vivía dentro de `dbc.AccordionItem(title="Ver detalle técnico", start_collapsed=True)`, junto al sidebar, en la línea ~511 — la misma distancia que separa la página 3 de la página 5 del PDF.

## 3. Nueva arquitectura

```text
┌─ barra de navegación sticky (Resumen · Operación · Gráficos · Escenario · Diagnóstico)
├─ section-summary   → sim-summary-bar + cockpit KPI (sin cambios, ya era grid)
├─ section-stockpiles→ Estado general (banner ancho completo) +
│                       grid 3×2 (Autonomía SAG1/SAG2, Recomendación, Recuperación, Quick win)
├─ section-charts    → Card "Análisis gráfico": selector de 10 vistas + Expandir/Reiniciar
│                       INMEDIATAMENTE ARRIBA de graph-main + comparar escenarios + feedback
├─ section-controls  → sidebar (sin cambios estructurales)
└─ section-diagnostics → accordion "Ver detalle técnico" (enlace "↑ Volver al gráfico" al inicio),
                          con el mismo contenido secundario que ya tenía (tabs Disponibilidad/
                          Autonomía/Alimentación/Bolas, sensibilidad, confiabilidad MC)

+ botón flotante "↑" (aparece tras ~480px de scroll, JS nativo, sin Store de Dash)
```

Configuración centralizada en `components/navigation.py` (nuevo): `NAV_SECTIONS` (5 anclas), `CHART_TABS` (las 10 vistas, antes declaradas inline y ahora una única fuente que `pages/simulador_operacional.py` importa).

## 4. Archivos modificados

| Archivo | Cambio | Propósito |
|---|---|---|
| `components/navigation.py` (nuevo) | `NAV_SECTIONS`, `CHART_TABS`, `build_section_nav()`, `build_back_to_top_button()`, `build_back_to_chart_link()` | Centraliza la config de navegación (Fase 11, sección 30 del pedido) |
| `assets/back_to_top.js` (nuevo) | Listener JS nativo de scroll + click | Muestra/oculta el botón flotante sin usar el grafo reactivo de Dash (ver sección 5) |
| `pages/simulador_operacional.py` | Selector `sim-main-view` + botones expandir/zoom movidos al header de `graph-main`; anclas de sección (`id=SECTION_*`) agregadas a los contenedores existentes; 6 bloques (6.1-6.6) reagrupados en banner + grid 3×2; `build_section_nav()`/`build_back_to_top_button()` insertados | Fix estructural raíz + navegación sticky + reducción de scroll |
| `assets/styles.css` | Bloque nuevo al final: `.simulation-section-nav.sticky-nav` (aislado, no reutiliza `#sim-summary-bar`), `scroll-behavior: smooth`, `scroll-margin-top`, `.sim-chart-tabs` (overflow-x), `.sim-main-graph` (clamp de altura), `.sim-back-to-top*` | CSS responsivo + evitar repetir el bug de sticky de 2026-07-07 |
| `tests/test_ux_navigation.py` (nuevo) | 12 pruebas de estructura | Ver sección 7 |

Ningún `id` existente fue renombrado; ningún archivo de `engine/` fue tocado.

## 5. Cambios de callbacks: físicos vs. visuales

- **Ninguno físico.** `sim-main-view` sigue siendo el mismo `Input` del mismo callback (`update_simulation`, único que escribe `Output("graph-main","figure")`) — solo cambió su posición en el árbol DOM. Verificado por `grep`: `Input("sim-main-view", ...)` aparece exactamente una vez en el archivo (test `test_sim_main_view_input_wireado_una_sola_vez`).
- El botón "↑ Volver arriba" **no usa un callback de Dash** — se implementó como listener JS nativo (`assets/back_to_top.js`) a propósito: `app.py` ya documenta (línea ~380) un bug real, encontrado y revertido, de un contador clientside que interactuaba mal con el despacho de "snapshot único" de Dash. Un toggle de clase por `id`, sin leer/escribir ningún `dcc.Store`, no entra en ese grafo reactivo y evita esa clase de bug.
- El enlace "Volver al gráfico" y la barra de navegación sticky son anclas HTML (`<a href="#id">`) con `scroll-behavior: smooth` — no disparan ningún callback ni recargan la app.

## 6. Evidencia visual

**No generada en esta pasada** — no hay herramienta de navegador/captura disponible en este entorno de ejecución. Cubierto en su lugar por:
- CSS responsivo verificado por inspección (`clamp()` en la altura del gráfico, `overflow-x: auto` en la barra de pestañas y la barra de navegación para ≤1400px, grid Bootstrap `xs/md/lg` que colapsa de 3→2→1 columnas).
- 12 pruebas automatizadas de estructura (sección 7).

Esto queda declarado explícitamente como riesgo residual (sección 9), **no** como "validado visualmente".

## 7. Pruebas

```text
comando: python -m pytest tests/test_ux_navigation.py tests/test_layout_smoke.py -v
resultado: 15 passed
  (12 nuevas: anclas de seccion, selector adyacente al grafico, ausencia
   del selector en el panel de diagnostico, CHART_TABS centralizado,
   accordion colapsado por defecto, boton volver arriba, enlace volver
   al grafico, wiring unico de sim-main-view, reglas CSS presentes
   + 3 preexistentes de test_layout_smoke.py, sin regresion)

comando: python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
resultado: 331 passed in 206s (319 preexistentes + 12 nuevas), cero regresiones

comando: python -c "import app"
resultado: OK — carga historico, precomputa figuras estaticas, sin errores
```

## 8. Limpieza posterior a la modificación

```text
archivos temporales eliminados:       ninguno (no se generaron)
reportes consolidados:                este mismo archivo (unico reporte del tema, no se creo uno nuevo por separado)
reportes archivados:                  ninguno
imagenes/HTML/PDF eliminados:         ninguno
logs eliminados:                      ninguno
scripts temporales eliminados:        ninguno
imports/codigo muerto eliminado:      2 lineas de codigo muerto propias
                                       (artefactos de redaccion en
                                       tests/test_ux_navigation.py, "if False
                                       else None") detectadas y corregidas
                                       antes de correr las pruebas
```

`git status --short` tras el cambio: solo los 7 archivos listados en la sección 4 (2 nuevos módulos, 1 test nuevo, 1 asset JS nuevo, 3 modificados) — sin artefactos fuera de lugar.

Pruebas ejecutadas después de la limpieza: las mismas de la sección 7 (331 passed).

## 9. Riesgos residuales

- **Confirmación visual real pendiente del usuario**: el CSS cubre 1920×1080/1600×900/1366×768 por diseño (`clamp()`, `overflow-x`, grid Bootstrap), pero no fue confirmado abriendo un navegador real en esas tres resoluciones — este entorno no tiene esa herramienta. Se recomienda abrir `python run_app.py` y verificar visualmente antes de dar por cerrado el rediseño.
- **Modo claro incompleto** (limitación preexistente, no introducida por este cambio, ya documentada en `04_Reports/Technical/20260707_Modo_Claro_Oscuro.md`): la barra de navegación sticky y el botón "Volver arriba" son CSS puro con colores fijos del tema oscuro — se ven correctos en modo oscuro (default), modo claro completo requeriría el mismo trabajo pendiente ya declarado para el resto de tarjetas/sidebar.
- **Selector de circuito Ambos/SAG1/SAG2** (Fase 7 del pedido) y **transformación completa del sidebar en drawer** (Fase 5, sección 15) quedaron fuera de alcance de esta pasada — declarado en el plan aprobado antes de implementar, no una omisión silenciosa.
- El grid 3×2 de los bloques 6.1-6.6 asume que su contenido seguirá siendo compacto (1-5 líneas por tarjeta, confirmado en `components/cards.py` al momento de este cambio) — si alguno de esos bloques crece significativamente en una modificación futura, revisar si sigue cabiendo bien en una celda de grid antes de agregar contenido.

---

## Segunda iteración (2026-07-14) — jerarquía de decisión

Pedido explícito de continuar la primera iteración con foco en **jerarquía de
decisión** (no navegación): que un Jefe de Sala entienda estado→riesgo→acción
en <10s, que SAG1/SAG2 se distingan sin ambigüedad, y que el gráfico traiga
interpretación y comparación por circuito. Plan aprobado antes de implementar
(ver decisión de alcance abajo); ningún cambio tocó el motor físico.

### Qué se implementó

1. **Bloque de decisión principal** (`components/cards.py::make_decision_banner`):
   una sola conclusión operacional arriba de todo — estado, circuito afectado
   (con chip `SAG1 · Molino 401`/`SAG2 · Molino 501`), horizonte, causa,
   acción sugerida, severidad, confianza — con botones `Aplicar recomendación`
   / `Ver detalle`. Se arma 100% con datos que `update_simulation` ya
   calculaba (`_estado_global`, `current_metrics`, `router_v2_result`,
   `quick_wins_list`, `restriction_reason_sagX` de `sim`) — cero lógica física
   nueva. El botón `btn-aplicar-recomendacion` no duplica la lógica de
   "Óptimo según pila": encadena hacia `btn-params-ideales.n_clicks` (mismo
   patrón de "un callback, múltiples triggers" ya usado por
   `btn-generar-recomendacion` en este mismo archivo).
2. **Grid reagrupado por circuito**: `div-estado-general` se retiró de la
   vista (su conclusión ya la cubre el Decision Banner, evita repetir el
   mismo mensaje) pero **su `Output` no se eliminó** — sigue existiendo
   oculto (`display:none`) para no reproducir el bug ya corregido esta
   sesión ("A nonexistent object was used in an Output"). Fila 1:
   `SAG1 | SAG2 | Recomendación`. Fila 2: `Recuperación | Quick win |
   Confianza` (tarjeta nueva y compacta, `make_confianza_card`, reusa el
   mismo semáforo ALTA/MEDIA/BAJA que ya usaba "Confiabilidad de la
   Recomendación").
3. **Selector de circuito** `[Ambos] [SAG1 · 401] [SAG2 · 501]`
   (`components/navigation.py::build_circuit_selector`, id `ctrl-circuito`):
   filtra **solo** `trace.visible` (`"legendonly"`) de `graph-main` ya
   calculado, vía `components/graphs.py::apply_circuit_filter`. Verificado
   por test que `Input("ctrl-circuito"...)` aparece una sola vez en el
   archivo (mismo patrón que el test equivalente de la primera iteración)
   — no dispara `simulate_scenario_cached`.
4. **Categorías de gráfico**: las 10 vistas de `CHART_TABS` se agrupan en 3
   categorías (`Operación`/`Riesgo`/`Análisis`) vía `CHART_CATEGORIES`;
   cambiar de categoría filtra las opciones de `sim-main-view` con un
   callback nuevo y puramente visual (`filtrar_vistas_por_categoria`), sin
   tocar `update_simulation`. "Equipos" no tiene categoría propia aquí
   porque esas vistas (disponibilidad/molinos de bolas) ya viven en los
   tabs de Diagnóstico — no se duplican.
5. **Marcas de evento completadas** en `make_master_pile_chart`: SAG OFF,
   molino de bolas inactivo, alimentación rechazada — usan campos que `sim`
   ya traía (`operational_state_sagX`, `dependency_message_sagX`,
   `rejected_feed_sagX`).
6. **`hovertemplate` enriquecido** en las trazas SAG1/SAG2 con balance neto,
   autonomía, estado y ventana T8 activa por punto (vía `customdata`),
   reusando series que `sim` ya calculaba (`cv315/cv316`, `tph_sag1/2`,
   `autonomia_sag1/2`) — sin cálculo físico nuevo.
7. **Semáforo de 5 niveles** (`OPERATIONAL_STATE_SEMAFORO`): mapea los 6
   `operational_state` reales del kernel (`OFF/STARTING/RUNNING/
   RESTRICTED/STARVED/STOPPING`) a `{nivel, color, icono}` — nunca depende
   solo del color.
8. **Catálogo `RESTRICTION_REASON_LABEL_JDS`**: traduce los 12 motivos de
   restricción del kernel (`engine/circuit_state.py`) a lenguaje de sala,
   reusado tanto por el Decision Banner como por los tooltips del gráfico.
9. **Navegación renombrada**: `Operación`→`Decisión`, `Escenario`→
   `Simulación` (mismos `id`/anclas, solo cambia el rótulo visible).
10. **Verificación de contraste WCAG AA real** (script en scratchpad, no
    commiteado): de 6 pares texto/fondo iniciales, 1 (`ROJO` en texto
    pequeño, 3.99:1) no alcanzaba el umbral de 4.5:1 para texto normal —
    se corrigió agregando `ROJO_TEXTO_PEQUENO` (`#F0605C`, 4.70:1) para los
    únicos dos usos de rojo en texto pequeño (`Severidad: Alto` del banner,
    `Baja` de la tarjeta de confianza). Los otros 6 pares ya pasaban.
    Resultado final: **7/7 pares pasan AA**.
11. **Smoke check de la app real** (Fase 1 del pedido, sin navegador
    disponible en este entorno): se detectó un proceso ya escuchando en el
    puerto 8050 (PID ajeno, no tocado) — se levantó una instancia nueva y
    aislada en el puerto 8051, se confirmó `HTTP 200` en `/`, `_dash-layout`
    serializa como JSON válido (sin excepciones de renderizado), y
    `_dash-dependencies` confirma los 28 callbacks registrados sin error,
    incluyendo `div-decision-banner`, `ctrl-circuito` y
    `sim-chart-category` correctamente enlazados. El proceso de prueba se
    detuvo por su PID específico al terminar; el proceso preexistente en
    8050 quedó intacto.

### Decisión de alcance — qué se difirió (declarado en el plan aprobado)

- **Fusión completa de `sim-summary-bar` (7 KPI cards) con el grid de
  decisión** en un único 3×3 literal — son dos componentes con historia
  y consumidores distintos (`make_exec_summary_bar` vs. los bloques 6.x);
  fusionarlos de verdad es un refactor propio. Se tomó prestada su función
  para la tarjeta de confianza únicamente.
- **Reagrupación completa del sidebar por circuito** (fundir 3
  `AccordionItem` en 2 bloques "SAG1 completo"/"SAG2 completo") — el
  sidebar (`components/controls.py`) no se tocó en esta pasada; sigue
  agrupado por tipo (SAG/Bolas/Pilas), no por circuito.
- **Modo claro completo** para los componentes nuevos — brecha preexistente
  y ya documentada, fuera de alcance de una pasada de UX.
- **Capturas reales en 1920/1600/1366 + PDF antes/después** — sin
  navegador disponible; cubierto por CSS responsivo ya extendido en la
  primera iteración más el smoke check HTTP del punto 11.
- **Pruebas reales de teclado/lector de pantalla** — no simuladas sin
  navegador.

### Archivos modificados/creados (segunda iteración)

| Archivo | Cambio |
|---|---|
| `components/cards.py` | `OPERATIONAL_STATE_SEMAFORO`, `RESTRICTION_REASON_LABEL_JDS`, `ROJO_TEXTO_PEQUENO`, `make_circuit_chip`, `make_confianza_card`, `make_decision_banner`, `build_initial_decision_banner` |
| `components/graphs.py` | marcas SAG OFF/molino OFF/alimentación rechazada, `hovertemplate` enriquecido con `customdata`, `apply_circuit_filter` |
| `components/navigation.py` | `NAV_SECTIONS` renombrado, `CHART_CATEGORIES`, `build_circuit_selector`, `build_chart_category_selector` |
| `pages/simulador_operacional.py` | banner en `section-summary`, grid reagrupado, selectores nuevos, 3 callbacks nuevos (`filtrar_vistas_por_categoria`, `aplicar_recomendacion_desde_banner`, más `ctrl-circuito`/2 Outputs en `update_simulation`) |
| `assets/styles.css` | estilos del banner/chip/tarjeta de confianza/selectores |
| `tests/test_decision_hierarchy.py` (nuevo) | 15 pruebas |

### Pruebas

```text
python -m pytest tests/test_decision_hierarchy.py -q → 15 passed
python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
  → 346 passed (331 preexistentes + 15 nuevas), cero regresiones
```

### Limpieza

Ningún archivo temporal quedó en el repositorio (script de contraste WCAG
y servidor de smoke test vivieron solo en el scratchpad de la sesión, ya
descartados). `git status` tras el cambio muestra únicamente los archivos
de la tabla de arriba. Reporte consolidado en este mismo documento (no se
creó un archivo nuevo).

### Riesgos residuales (segunda iteración)

- Confirmación visual humana en 1920×1080/1600×900/1366×768 sigue
  pendiente — el smoke check de esta pasada confirma que el servidor
  arranca y sirve sin errores, pero no reemplaza abrir un navegador.
- El sidebar sigue agrupado por tipo, no por circuito — diferenciación de
  SAG1/SAG2 mejorada en el área de decisión/gráfico, no en los controles.
- La fusión de `sim-summary-bar` con el grid de decisión, si se decide
  hacer, debe tratarse como una tarea dedicada (dos componentes con
  historia distinta), no una extensión rápida de esta pasada.
