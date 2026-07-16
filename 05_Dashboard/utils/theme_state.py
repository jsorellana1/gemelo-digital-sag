"""
theme_state.py — Preferencia de tema claro/oscuro (Fase 5, Skill UX/UI —
Auditoria de Contraste TDA, 2026-07-07).

Persiste en runtime_data/user_preferences.json (ruta pedida
explicitamente). Ver limitacion arquitectonica documentada en
04_Reports/Technical/20260707_Modo_Claro_Oscuro.md: los graficos
Plotly SI cambian de tema (via plantilla global, ver
components/graphs.py), pero las tarjetas/sidebar construidas en Python
(components/cards.py, controls.py) usan constantes de color fijas al
importar el modulo — modo claro completo para esos elementos requeriria
convertir esas constantes en funciones dependientes del tema, no hecho
en esta sesion.
"""
from __future__ import annotations

import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if getattr(sys, "frozen", False):
    _RUNTIME_DATA_DIR = os.path.join(os.path.dirname(sys.executable), "runtime_data")
else:
    _RUNTIME_DATA_DIR = os.path.join(_ROOT, "runtime_data")

_PREFS_PATH = os.path.join(_RUNTIME_DATA_DIR, "user_preferences.json")

VALID_THEMES = ("dark", "light")
DEFAULT_THEME = "dark"


def get_theme() -> str:
    try:
        with open(_PREFS_PATH, "r", encoding="utf-8") as f:
            prefs = json.load(f)
        theme = prefs.get("theme", DEFAULT_THEME)
        return theme if theme in VALID_THEMES else DEFAULT_THEME
    except Exception:
        return DEFAULT_THEME


def set_theme(theme: str) -> None:
    if theme not in VALID_THEMES:
        return
    try:
        os.makedirs(_RUNTIME_DATA_DIR, exist_ok=True)
        prefs = {}
        if os.path.exists(_PREFS_PATH):
            try:
                with open(_PREFS_PATH, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
            except Exception:
                prefs = {}
        prefs["theme"] = theme
        with open(_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False)
    except Exception:
        pass


# ── Paletas ────────────────────────────────────────────────────────────────
# Oscuro = TDA (Plataforma TDA_Diseño_Visual_Elegido.html). Claro = paleta
# corporativa original del proyecto (previa a la conversion a tema TDA,
# 2026-07-07), reutilizada como "modo claro ejecutivo" (Fase 4).
PALETTE_DARK = {
    "AZUL": "#F0F4FA", "AZUL_MED": "#4FB0E5", "VERDE": "#4FCE82",
    "NARANJA": "#E8935A", "ROJO": "#E94A4A", "AMARILLO": "#E5BB3E",
    "BG": "#07162F", "PLOT_BG": "#0F2647", "GRID": "#1a3a6c",
    "TEXTO_MUTED": "#8896AF", "BG_CARD": "#0F2647", "BORDE_CARD": "#1a3a6c",
    "CARD_BG": "#0F2647", "NAVBAR_BG": "#0B1E3F",
}
PALETTE_LIGHT = {
    "AZUL": "#1F3864", "AZUL_MED": "#1A5E99", "VERDE": "#27AE60",
    "NARANJA": "#E67E22", "ROJO": "#C0392B", "AMARILLO": "#F39C12",
    "BG": "#F5F7FA", "PLOT_BG": "#FFFFFF", "GRID": "#eeeeee",
    "TEXTO_MUTED": "#7F8C8D", "BG_CARD": "white", "BORDE_CARD": "#D6E0E8",
    "CARD_BG": "white", "NAVBAR_BG": "#1F3864",
}


def apply_theme_to_module(module_globals: dict, theme: str | None = None) -> None:
    """Reasigna las constantes de color (AZUL/VERDE/BG/etc) en el
    namespace global de OTRO modulo (components/graphs.py,
    components/cards.py, components/controls.py,
    pages/simulador_operacional.py, app.py). Funciona porque esas
    constantes se leen por nombre en cada llamada a las funciones de ese
    modulo (scoping normal de Python) — no hace falta tocar ninguna
    funcion individual, solo reasignar el valor del nombre en el modulo
    antes de construir figuras/tarjetas."""
    theme = theme or get_theme()
    pal = PALETTE_LIGHT if theme == "light" else PALETTE_DARK
    for key, value in pal.items():
        if key in module_globals:
            module_globals[key] = value


def apply_plotly_theme(theme: str | None = None) -> None:
    """Actualiza el template Plotly global (tda_dark/tda_light) in-place
    con los colores de la paleta activa — se llama junto con
    apply_theme_to_module al inicio de los callbacks que construyen
    figuras, para que los graficos SI respeten el toggle."""
    import plotly.io as pio
    theme = theme or get_theme()
    pal = PALETTE_LIGHT if theme == "light" else PALETTE_DARK
    template_name = "tda_light" if theme == "light" else "tda_dark"
    if template_name not in pio.templates:
        return
    tpl = pio.templates[template_name]
    tpl.layout.paper_bgcolor = pal["BG"]
    tpl.layout.plot_bgcolor = pal["PLOT_BG"]
    tpl.layout.font.color = pal["AZUL"]
    tpl.layout.xaxis.gridcolor = pal["GRID"]
    tpl.layout.xaxis.linecolor = pal["GRID"]
    tpl.layout.xaxis.zerolinecolor = pal["GRID"]
    tpl.layout.xaxis.tickfont.color = pal["TEXTO_MUTED"]
    tpl.layout.yaxis.gridcolor = pal["GRID"]
    tpl.layout.yaxis.linecolor = pal["GRID"]
    tpl.layout.yaxis.zerolinecolor = pal["GRID"]
    tpl.layout.yaxis.tickfont.color = pal["TEXTO_MUTED"]
    tpl.layout.legend.font.color = pal["AZUL"]
    pio.templates.default = template_name
