# Modo Claro / Oscuro — Arquitectura del Toggle de Tema

**Fecha:** 2026-07-07

Documenta la implementación de las Fases 3, 4 y 5 del prompt de auditoría de contraste: modo oscuro (por defecto, basado en TDA), modo claro (paleta corporativa ejecutiva previa), y el mecanismo de cambio persistente.

---

## 1. Resumen

- **Modo oscuro (default):** paleta TDA extraída de `Plataforma TDA_Diseño_Visual_Elegido.html` (ver `20260707_TDA_Contrast_Mapping.md`). Fondo `#07162F`, tarjetas `#0F2647`, texto `#F0F4FA`.
- **Modo claro:** paleta corporativa original del proyecto (previa a la conversión TDA de este mismo día), reutilizada como "modo claro ejecutivo" — fondo `#F5F7FA`, tarjetas blancas, texto `#1F3864`.
- **Persistencia:** `runtime_data/user_preferences.json`, formato `{"theme": "dark"}` o `{"theme": "light"}`, ruta pedida explícitamente por el usuario.
- **Control:** botón 🌙/☀️ en la barra de navegación (`btn-theme-toggle`).

---

## 2. El problema arquitectónico

La app no usa CSS puro para colorear: los gráficos Plotly generan JSON con colores ya "horneados" en el momento en que Python construye la figura, y las tarjetas (`components/cards.py`) usan `style={...}` inline con colores literales, que tienen la máxima especificidad CSS posible — ningún selector `[data-theme="light"] .card {...}` puede sobrescribirlos. Un enfoque "solo CSS" no podía funcionar para gran parte de la interfaz.

## 3. Solución: recolorización en tiempo de callback, vía scoping de Python (LEGB)

Cada módulo (`components/graphs.py`, `components/cards.py`, `components/controls.py`, `pages/simulador_operacional.py`, `app.py`) define constantes de color a nivel de módulo (`AZUL`, `VERDE`, `BG`, etc.). Todas las funciones de ese módulo las leen **por nombre en cada llamada**, no las capturan una sola vez al definirse — es el comportamiento normal de resolución de variables en Python (LEGB: Local → Enclosing → Global → Built-in).

Esto permite que `utils/theme_state.py::apply_theme_to_module(module.__dict__, theme)` reasigne esas constantes **desde afuera**, y que la próxima vez que cualquier función de ese módulo se ejecute (construir una tarjeta, un gráfico), use los nuevos valores — sin tener que tocar cada función individualmente.

```python
def apply_theme_to_module(module_globals: dict, theme: str | None = None) -> None:
    theme = theme or get_theme()
    pal = PALETTE_LIGHT if theme == "light" else PALETTE_DARK
    for key, value in pal.items():
        if key in module_globals:
            module_globals[key] = value
```

### Dónde se invoca

- **`pages/simulador_operacional.py::update_simulation`** (callback principal de la Vista Principal): al inicio, antes de construir cualquier tarjeta o gráfico, aplica el tema a `graphs`, `cards`, `controls` y a su propio namespace, y llama `apply_plotly_theme()`.
- **`app.py::serve_layout()`**: aplica el tema a `controls` (sidebar construido al cargar la página) y reconstruye navbar/footer con `_build_navbar_and_footer()`.

## 4. Gráficos Plotly: doble template registrado

`components/graphs.py` registra dos templates globales al importar el módulo:

```python
pio.templates["tda_dark"] = _build_template(BG, PLOT_BG, GRID, AZUL, TEXTO_MUTED)   # paleta oscura
pio.templates["tda_light"] = _build_template(...)                                    # paleta clara
```

`utils/theme_state.py::apply_plotly_theme(theme)` muta el template activo in-place (colores de fondo, grilla, fuente de ejes/leyenda) y fija `pio.templates.default` al nombre correspondiente, de forma que cualquier `go.Figure()` creada después respeta el tema sin tener que pasar `template=` explícitamente en cada gráfico.

## 5. Navbar y footer: de constantes de módulo a función

El navbar y el footer (`version_status_bar`) originalmente eran valores construidos una sola vez al importar `app.py` — un patrón incompatible con un toggle en tiempo de ejecución, porque nunca se re-evalúan. Se refactorizaron a una función:

```python
def _build_navbar_and_footer():
    apply_theme_to_module(globals(), get_theme())
    navbar = ...      # construido con las constantes ya actualizadas
    version_status_bar = ...
    return navbar, version_status_bar
```

Llamada dentro de `serve_layout()`, que Dash ya invoca en cada carga completa de página — el mecanismo de "aplicar y luego recargar" (sección 6) se apoya en este re-render completo.

## 6. Flujo del toggle (botón 🌙/☀️)

1. Usuario hace clic en `btn-theme-toggle`.
2. Callback servidor `toggle_theme`: lee el tema actual (`get_theme()`), calcula el opuesto, lo persiste con `set_theme(nuevo)` en `runtime_data/user_preferences.json`, y devuelve el nuevo valor a un `dcc.Store(id="store-theme-trigger")`.
3. Callback **clientside** encadenado (dispara al cambiar el Store):
   ```js
   function(theme) { if (theme) { window.location.reload(); } return window.dash_clientside.no_update; }
   ```
   Fuerza una recarga completa del navegador.
4. Al recargar, `serve_layout()` se ejecuta de nuevo desde cero, lee el tema ya persistido (`get_theme()`), y reconstruye toda la interfaz (sidebar, navbar, footer) con la paleta correcta desde el primer render — sin parpadeo de "flash del tema incorrecto" porque no hay hidratación parcial, es un layout server-rendered completo.

Esta secuencia server-side-guarda-luego-cliente-recarga se eligió en vez de un cambio de tema puramente clientside porque la mayor parte del coloreado (tarjetas, gráficos) se genera en Python en cada callback, no en CSS — un cambio de tema real requiere que el próximo render del servidor use la paleta nueva, no solo alternar una clase CSS en el navegador.

---

## 7. Formato de persistencia

`runtime_data/user_preferences.json`:
```json
{"theme": "dark"}
```
Ruta consistente con el patrón ya usado por `utils/perf_logger.py`, `utils/usage_logger.py` y `utils/scenario_state.py`: detecta si corre como `.exe` congelado (`sys.frozen`) y usa el directorio del ejecutable, o la raíz del proyecto en desarrollo. Escritura defensiva (nunca lanza excepción; si falla, se usa `DEFAULT_THEME = "dark"`).

---

## 8. Bug encontrado y corregido durante la redacción de este documento

Al documentar la sección 6 se detectó que el bloque `:root, [data-bs-theme="dark"] { --bs-* ... }` de `styles.css` aplicaba **siempre**, porque `:root` coincide sin condición — el modo claro heredaría los mismos `--bs-*` oscuros y reproduciría el bug de contraste original (form-check/accordion/table invisibles) sobre un fondo ahora claro. Corregido:

1. Se agregó un bloque `[data-bs-theme="light"]` en `styles.css` con la paleta clara completa (tokens `--azul`/`--bg`/`--card-bg`/etc. y el set `--bs-*`).
2. `app.py::serve_layout()` ahora escribe el atributo `data-bs-theme` en el `html.Div` raíz del layout según `get_theme()`, para que las custom properties de CSS se resuelvan correctamente por herencia hacia todos los componentes Bootstrap descendientes.

## 9. Limitación restante (declarada, no oculta)

No se hizo una pasada de QA visual con capturas reales sobre el modo claro (no hay navegador en este entorno) — la corrección de la sección 8 se validó por revisión de código y por el mismo mecanismo de herencia de custom properties que ya se usa en modo oscuro, no por inspección visual. Se recomienda una ronda de captura de pantalla en modo claro antes de considerarlo production-ready.
