"""
version.py — Fuente unica de verdad de version de release y version de
esquema de estado persistido.

Nunca hardcodear estos valores en otro archivo (app.py, utils/
state_schema.py, etc. importan desde aca). Son deliberadamente DOS
numeros independientes:

  APP_VERSION              — version de release. NO se duplica aca: se lee
                              en tiempo de import desde packaging/
                              VERSION.txt (linea "Version: X"), que ya es
                              la fuente unica de verdad usada por
                              scripts/generate_release_manifest.py y por
                              todo el proceso de build/QA. Si el archivo no
                              se encuentra (no deberia pasar ni en dev ni
                              en el .exe, ver build_portable.py que lo
                              copia siempre) cae a un default explicito,
                              nunca lanza.
  APP_STATE_SCHEMA_VERSION — version de la ESTRUCTURA de los datos
                              persistidos (dcc.Store de sesion y
                              outputs/state/*.json). Sube SOLO cuando
                              cambia la forma de esos datos (campos
                              agregados/renombrados/quitados) — permite
                              lanzar una nueva version de la app sin
                              invalidar sesiones en curso si el esquema de
                              estado no cambio. Independiente de
                              APP_VERSION a proposito (ver seccion 5 del
                              pedido que origino este modulo).
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASH_DIR = os.path.dirname(_HERE)

_APP_VERSION_FALLBACK = "1.3.0"


def _read_app_version() -> str:
    """Lee 'Version: X' desde packaging/VERSION.txt. Mismo patron de
    resolucion de ruta frozen/dev que utils/scenario_state.py:
    build_portable.py copia VERSION.txt junto al .exe (no dentro de una
    subcarpeta packaging/), en dev vive en 05_Dashboard/packaging/."""
    if getattr(sys, "frozen", False):
        candidates = [os.path.join(os.path.dirname(sys.executable), "VERSION.txt")]
    else:
        candidates = [os.path.join(_DASH_DIR, "packaging", "VERSION.txt")]

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            match = re.search(r"^Version:\s*(\S+)", text, re.MULTILINE)
            if match:
                return match.group(1)
        except Exception:
            continue
    return _APP_VERSION_FALLBACK


APP_VERSION = _read_app_version()
APP_STATE_SCHEMA_VERSION = 2

# Deteccion de modo de ejecucion — nunca hardcodear el texto en la UI.
# sys.frozen=True + sys._MEIPASS existe cuando corre empaquetado con
# PyInstaller (ver build_portable.py); en modo dev (python run_app.py o
# python app.py) ninguno de los dos existe.
IS_FROZEN = bool(getattr(sys, "frozen", False))
EXECUTION_MODE = "Modo local (.exe portátil)" if IS_FROZEN else "Modo desarrollo (Python)"


def version_label() -> str:
    """'v1.3.0 · Modo desarrollo (Python)' — string listo para la UI."""
    return f"v{APP_VERSION} · {EXECUTION_MODE}"
