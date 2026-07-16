# Mapeo Estructural y Visual — Templates TDA

**Fecha:** 2026-07-07
**Fuentes:** `Plataforma TDA_Diseño_Visual_Elegido.html`, `Plataforma TDA_Diseño_Estructura_Elegido.html` (ambos en la raíz del proyecto).

Complementa `20260707_Template_TDA_Mapping.md` (primer análisis, sesión anterior). Este documento cierra la Fase 2 del prompt de auditoría de contraste: qué se pudo extraer de cada archivo y cómo se mapeó a la implementación real.

---

## 1. `Plataforma TDA_Diseño_Estructura_Elegido.html` — NO LEGIBLE

Confirmado nuevamente: es un bundle JS compilado (build de un framework moderno, minificado, sin fuente ni mapas), servido junto a un placeholder SVG de carga. No contiene marcado HTML/CSS legible más allá de ese SVG. No aporta información estructural nueva sobre navegación, grillas o breakpoints — se descarta como fuente para esta fase, tal como se documentó en el análisis anterior.

## 2. `Plataforma TDA_Diseño_Visual_Elegido.html` — parcialmente legible (SVG de carga)

Único contenido legible: un `<svg>` de pantalla de carga con paleta de color embebida directamente como atributos `fill`/`stroke`. De ahí se extrajo la paleta ya en uso desde la sesión anterior:

| Token | Valor | Uso en el SVG |
|---|---|---|
| Fondo | `#07162F` | rect de fondo completo |
| Panel/tarjeta | `#0F2647` | rects secundarios, "tarjetas" del mock de carga |
| Borde | `#1a3a6c` | stroke de los rects de panel |
| Texto principal | `#F0F4FA` | texto/ícono central |
| Texto secundario | `#8896AF` | elementos de menor jerarquía |
| Verde (éxito/OK) | `#4FCE82` | indicador de estado positivo |
| Ámbar (alerta) | `#E5BB3E` | indicador de estado de atención |
| Rojo (crítico) | `#E94A4A` | indicador de estado crítico |
| Naranja (secundario) | `#E8935A` | acento secundario |
| Azul acento | `#4FB0E5` | elementos interactivos/enlaces |
| Tipografía | "Plus Jakarta Sans" (declarada en un `<style>` embebido, sin CDN — se usa como intento de `font-family` con fallback a Segoe UI/system-ui) | — |

No hay información estructural extraíble (grillas, tamaños de card, espaciados) de este archivo — solo paleta y tipografía. Cualquier decisión de layout (franja KPI, cockpit horizontal, tablas, etc.) se tomó en las fases anteriores de la sesión según los lineamientos ISA-101/ASM del Skill v2, no desde este archivo.

---

## 3. Mapa de aplicación: paleta TDA → componentes reales

| Token TDA | Constante Python | Dónde se usa |
|---|---|---|
| `#07162F` | `BG` | fondo general de página (`app.py`, `styles.css`) |
| `#0F2647` | `PLOT_BG` / `BG_CARD` / `CARD_BG` | fondo de gráficos Plotly, fondo de tarjetas `dbc.Card` |
| `#1a3a6c` | `GRID` / `BORDE_CARD` | grillas de ejes Plotly, bordes de tarjetas |
| `#F0F4FA` | `AZUL` (renombrada, ver nota) | texto principal en tarjetas, ejes, leyendas |
| `#8896AF` | `TEXTO_MUTED` | texto secundario, subtítulos, ticks de ejes |
| `#4FCE82` | `VERDE` | estado OK / KPI positivo |
| `#E5BB3E` | `AMARILLO` | estado de atención |
| `#E94A4A` | `ROJO` | estado crítico |
| `#E8935A` | `NARANJA` | acento secundario / advertencia |
| `#4FB0E5` | `AZUL_MED` | enlaces, botones, elementos interactivos |
| `#0B1E3F` | `NAVBAR_BG` | fondo de la barra de navegación (más oscuro que `BG` para diferenciarla) |

**Nota de nomenclatura:** la constante `AZUL` mantiene su nombre histórico del código (heredado de la paleta corporativa original, azul oscuro sobre fondo blanco) pero en el tema TDA pasó a representar el **color de texto** (`#F0F4FA`, casi blanco), no un azul de fondo — es la inversión de rol típica al migrar de tema claro a oscuro. Esto se documenta explícitamente porque fue la fuente del bug #6 (tabla Planificador de Turno) descrito en `20260707_Contraste_TDA_Audit.md`: código que asumía `AZUL` = fondo oscuro con texto blanco encima dejó de tener sentido una vez `AZUL` pasó a ser un color de texto claro.

---

## 4. Conclusión de la Fase 2

Con dos archivos de referencia, solo uno aportó información utilizable (paleta + tipografía), ya incorporada en el turno anterior. No hay mapeo estructural adicional posible desde los archivos TDA — las decisiones de estructura (franja KPI, cockpit, Vista 1-4) provienen del Skill v2/v3 (ISA-101/ASM), no de estos archivos.
