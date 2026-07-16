# Mapeo Template TDA → Simulador de Distribución de Moliendas SAG DET

**Fecha:** 2026-07-07

---

## Limitación real encontrada (leer antes que el resto)

`Plataforma TDA_Diseño_Estructura_Elegido.html` (628 KB, 185 líneas) y
`Plataforma TDA_Diseño_Visual_Elegido.html` (1.6 MB) **no son HTML
estático** — son exports de tipo "bundler" (patrón típico de
herramientas Figma-to-code / v0 / bolt.new): un `<script>` que
descomprime y monta una aplicación React empaquetada/minificada en
tiempo de ejecución, con un thumbnail SVG de carga mientras tanto. **No
existe marcado DOM legible** (headers, cards, nav como HTML/CSS
plano) que se pueda leer y copiar — el árbol de componentes real vive
compilado dentro del bundle JS, no como texto.

**Lo que SÍ se pudo extraer** (búsqueda de patrones en el bundle +
lectura del SVG thumbnail de carga, que sí es marcado plano):

- **Paleta de color** (dark theme):
  `#061827` (fondo base), `#0b2c44` / `#123b59` (paneles/cards),
  acentos cian `#8fd9ef` / `#9fe0ff` / `#bcecff`, texto `#cdd9e3` /
  `#dbe8ff`, semáforo verde `#7fd18a`/`#37d67a`/`#46d957`, ámbar
  `#e6dc8a`/`#ffd9a8`/`#ff9d3c`, rojo `#e08a93`/`#ff8a80`/`#ff4d5e`.
- **Tipografía**: `--display: 'Saira', 'Segoe UI', system-ui, sans-serif`
  (para títulos/cabecera) y `--body: 'Barlow', 'Segoe UI', system-ui,
  sans-serif` (para texto de cuerpo) — dos familias, exactamente el
  límite que exige el skill UX/UI anterior ("máximo 2 familias
  tipográficas"). 'Saira' y 'Barlow' no están instaladas localmente ni
  se pueden traer sin depender de Google Fonts (CDN) — **Requisito 10
  de este mismo prompt prohíbe explícitamente CDN externos** — por lo
  tanto se adopta el patrón de 2 niveles pero con las fuentes de
  sistema ya declaradas como fallback (`Segoe UI`/`system-ui`), sin
  bloquear en la fuente de marca.
- **Estructura general** (inferida del SVG thumbnail, línea 23-33 del
  bundle): 1 barra de cabecera de ancho completo arriba, 2 paneles de
  igual ancho lado a lado debajo, con indicadores circulares de estado
  (semáforo) superpuestos en las esquinas de cada panel — consistente
  con "header + 2 columnas de cards con semáforo", no aporta nada
  nuevo respecto a la estructura que ya tiene el simulador (franja KPI
  + cockpit de 4 columnas).

**No se puede extraer honestamente**: jerarquía real de componentes,
espaciado exacto, iconografía, comportamiento de navegación, ni
ningún texto de la UI (solo sobrevivió la palabra "compressed" como
string legible en todo el bundle). Cualquier afirmación más específica
que la lista de arriba sería inventada, no leída del archivo.

---

## Decisión de adaptación

Dado lo anterior, **no se copia el template TDA literalmente** (no hay
nada literal que copiar — es un bundle compilado, no una plantilla de
código). Se adopta lo único verificable y compatible con las
restricciones ya vigentes (ISA-101 del skill anterior exige fondo
blanco en área operacional; el TDA es dark-theme — **conflicto
directo**, se resuelve documentando la decisión en vez de
silenciarla):

| Elemento Template TDA (verificado) | Uso en Simulador | Adaptación requerida |
|---|---|---|
| Paleta dark-navy (`#061827`/`#123b59`) + acentos cian | — | **No adoptada.** Contradice ISA-101 ("Blanco: fondo de área de trabajo", ya vigente en `skill_ux_ui_cio_operations_center.md`). Se documenta el conflicto en vez de romper la regla anterior sin decisión explícita del usuario. |
| Semáforo circular verde/ámbar/rojo superpuesto en cards | KPIs operacionales | **Ya implementado** (emoji 🟢🟡🔴 + borde de color en `make_exec_summary_bar`/cockpit, sesión anterior) — coincide con el patrón TDA sin cambios adicionales. |
| Tipografía de 2 niveles (display/body) | Cabecera vs. resto del texto | **Adoptada conceptualmente**: navbar/títulos con mayor peso (`font-weight:700-800`, ya vigente), cuerpo con peso normal — usando fuentes de sistema (`Segoe UI`/`system-ui`) en vez de 'Saira'/'Barlow' para no depender de CDN (Requisito 10). |
| Header de ancho completo | Cabecera ejecutiva | Ver Requisito 4 — se agregó Versión / Modo local / Última simulación / Estado del modelo al navbar existente (no se rediseñó desde cero, se extendió lo que ya había). |
| Paneles de igual ancho lado a lado | Cockpit (Inventario/Producción/Riesgo/PAM) | **Ya implementado** (`make_cockpit_row`, sesión anterior) — 4 columnas iguales, mismo patrón. |
| Navegación (no verificable en el bundle) | Vistas JdS / Ingeniero | Sin cambio — no hay evidencia real del bundle sobre cómo estructura su navegación; se mantiene la navbar + modo Rápido/Avanzado ya construidos. |

## Recomendación

Si el objetivo real es adoptar el estilo visual dark-navy del TDA
(no solo su estructura), eso es una **decisión de producto** (cambiar
la paleta base de todo el simulador, entrando en conflicto con la
regla ISA-101 "fondo blanco en área operacional" del skill anterior) —
no se tomó unilateralmente en esta sesión. Si se confirma que se
quiere ese theme, el siguiente paso es pedir el archivo fuente sin
bundlear (el `.tsx`/`.jsx` o el diseño en Figma) — desde un bundle
compilado no hay forma de recuperar más que paleta y tipografía.
