"""
state_schema.py — Versionado y normalizacion de estado persistido.

Cubre dos mecanismos de persistencia usados en el dashboard, ambos con el
mismo problema potencial (datos de una version anterior de la app
sobreviven a un reinicio del servidor o a una recarga forzada y entran a
callbacks/layouts actuales con una estructura incompatible):

  1. dcc.Store(storage_type="session"/"local") — vive en el navegador
     (sessionStorage/localStorage), sobrevive a reinicios del servidor y a
     Ctrl+Shift+R (NO sobrevive a modo incognito nuevo ni a borrar
     almacenamiento del sitio).
  2. Archivos JSON en disco (ver utils/scenario_state.py) — sobreviven a
     CUALQUIER cosa: reinicio de servidor, recarga, nueva pestana,
     incognito, y actualizacion de la app a una version nueva.

Estrategia de invalidacion elegida: cada estructura persistida se envuelve
en un sobre {"schema_version": APP_STATE_VERSION, "data": {...}}.
normalize_persisted_state() es el UNICO punto que decide si un estado
sobrevive o se descarta — nunca se reutiliza silenciosamente una
estructura de otra version, y nunca se lanza una excepcion hacia el
callback que la llama (un estado corrupto se trata igual que uno ausente).
"""
from __future__ import annotations

import logging
import math
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from utils.version import APP_STATE_SCHEMA_VERSION

logger = logging.getLogger("dashboard.state_schema")

# Alias local — subir utils/version.py::APP_STATE_SCHEMA_VERSION invalida
# automaticamente TODO el estado persistido de versiones anteriores
# (dcc.Store de sesion y outputs/state/*.json) en el proximo load, sin
# requerir ninguna accion manual del usuario.
APP_STATE_VERSION = APP_STATE_SCHEMA_VERSION


def make_json_safe(value: Any) -> Any:
    """Convierte recursivamente un valor a algo JSON-serializable de forma
    segura para persistir en dcc.Store/archivo: np.integer/np.floating a
    int/float nativos, arrays NumPy y tuplas a listas, NaN/Inf a None,
    datetime/date a ISO 8601. dict/list/tuple se recorren recursivamente;
    cualquier otro tipo desconocido se intenta tal cual (json.dumps fallara
    de forma visible en vez de silenciosa si de verdad no es serializable).
    """
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(v) for v in value]
    # numpy escalares/arrays sin importar numpy directamente aqui (evita
    # acoplar este modulo utilitario a una dependencia pesada) — se
    # detectan por los metodos que numpy expone.
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return make_json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "tolist") and callable(getattr(value, "tolist")):
        try:
            return make_json_safe(value.tolist())
        except Exception:
            pass
    return value


def make_envelope(data: dict) -> dict:
    """Envuelve `data` en el sobre versionado que se persiste (dcc.Store.data
    o archivo JSON). Usar siempre para ESCRIBIR estado, nunca escribir el
    dict "pelado". Sanitiza con make_json_safe() antes de envolver — un
    dcc.Store con un np.float64/NaN/Inf sin convertir puede fallar la
    serializacion a mitad de camino y dejar el store parcialmente
    actualizado; aca se convierte todo de una vez, antes de escribir."""
    return {"schema_version": APP_STATE_VERSION, "data": make_json_safe(deepcopy(data))}


def normalize_persisted_state(
    raw_state: Any,
    default_data: dict,
    required_keys: tuple[str, ...] = (),
    kind: str = "unknown",
) -> dict:
    """Valida/migra un estado persistido antes de usarlo. Nunca lanza.

    Retorna SIEMPRE un dict {"schema_version": ..., "data": {...}} valido:
    - Si raw_state es None, no es un dict, no trae schema_version vigente,
      no trae 'data' como dict, o le faltan required_keys -> se descarta
      por completo y se retorna el default envuelto (con logging que
      distingue cada caso).
    - Si es valido, se completan campos opcionales faltantes con el
      default (merge seguro que nunca sobreescribe lo que si vino) y se
      retorna una copia profunda (nunca el objeto original) para evitar
      mutaciones accidentales entre requests.
    """
    default_env = make_envelope(default_data)

    if raw_state is None:
        logger.info("Estado persistido ausente (kind=%s) — usando estado inicial.", kind)
        return default_env

    if not isinstance(raw_state, dict):
        logger.warning(
            "Estado persistido con tipo invalido (kind=%s, tipo=%s) — se restablece.",
            kind, type(raw_state).__name__,
        )
        return default_env

    found_version = raw_state.get("schema_version")
    if found_version != APP_STATE_VERSION:
        logger.warning(
            "Estado persistido incompatible (kind=%s). Version encontrada=%r, "
            "version esperada=%r. Se restablecera automaticamente.",
            kind, found_version, APP_STATE_VERSION,
        )
        return default_env

    data = raw_state.get("data")
    if not isinstance(data, dict):
        logger.warning("Estado persistido sin 'data' valido (kind=%s) — se restablece.", kind)
        return default_env

    missing = [k for k in required_keys if k not in data]
    if missing:
        logger.warning(
            "Estado persistido con campos faltantes (kind=%s): %s — se restablece.",
            kind, missing,
        )
        return default_env

    merged = deepcopy(default_data)
    merged.update(data)
    logger.debug("Estado persistido valido y vigente (kind=%s).", kind)
    return {"schema_version": APP_STATE_VERSION, "data": merged}


def get_data(raw_state: Any, default_data: dict, required_keys: tuple[str, ...] = (),
             kind: str = "unknown") -> dict:
    """Atajo: normaliza y retorna directamente el 'data' interno (lo que
    la mayoria de los callbacks realmente necesita)."""
    return normalize_persisted_state(raw_state, default_data, required_keys, kind)["data"]


# ── Defaults por store (Fase 1 del inventario, ver reporte tecnico) ──────────
# Cada entrada documenta: para que se usa, quien la escribe/lee, y el
# default seguro si no hay estado o es incompatible.

PLANT_STATE_DEFAULT = {
    "pila_sag1": 55.0, "pila_sag2": 55.0,
    "rate_sag1": 1236.0, "rate_sag2": 2214.0,
    "cv315": 0.0, "cv316": 0.0,
}
"""store-plant-state (session) — escrito por update_simulation, leido por
run_monte_carlo como State para el escenario base de Monte Carlo."""

MC_RESULTS_DEFAULT: dict = {}
"""store-mc-results (session) — el candidato 'best' de la ultima corrida
Monte Carlo. Escrito por run_monte_carlo, leido por update_simulation
(p_safe) y por el toggle de graficos MC. Vacio = 'sin Monte Carlo corrido
en esta sesion', ya manejado explicitamente en el codigo existente."""

RECOMENDACION_ID_DEFAULT = {"rec_id": None}
"""store-ultima-recomendacion-id (session) — id corto de la ultima
recomendacion generada, usado para asociar el feedback del JdS."""

SNAPSHOT_CASO_DEFAULT: dict = {}
"""store-ultimo-snapshot-caso (session) — snapshot del escenario para el
formulario de validacion operacional."""

RECOMMENDATION_HASH_DEFAULT = {"hash": None}
"""store-recommendation-scenario-hash (session) — hash del escenario en el
momento de la ultima 'GENERAR RECOMENDACION', para detectar si el
escenario actual ya diverge de la recomendacion vigente."""

RECOMMENDATION_PARAMS_DEFAULT: dict = {}
"""store-recommendation-scenario-params (session) — parametros congelados
de la ultima recomendacion (modo 'Recomendacion vigente')."""

RECOMMENDATION_PARAMS_REQUIRED = (
    "duracion_t8", "pila1", "pila2", "rate_sag1_tph", "rate_sag2_tph",
    "bolas_sag1", "bolas_sag2", "sag1_on", "sag2_on", "ch1_on", "ch2_on",
    "c315", "c316", "horizonte", "cv_mode", "t1_mode", "distribucion_t1",
)
"""Campos que utils.scenario_hash.build_scenario_dict() siempre incluye —
si al leer store-recommendation-scenario-params falta alguno (esquema de
una version anterior), se descarta el estado completo en vez de acceder
con corchetes a una clave que puede no existir."""

RECOMMENDATION_CONTEXTO_DEFAULT: dict = {}
"""store-recommendation-contexto (session) — contexto adicional mostrado
junto a la recomendacion vigente."""

LAST_SCENARIO_DEFAULT = {
    "pila1": 55, "pila2": 55, "duracion_t8": 0,
    "rate1_tph": 1236, "rate2_tph": 2214,
    "bolas_sag1": "solo_411", "bolas_sag2": "solo_511",
    "turno": "A", "regimen_activo": None,
}
"""outputs/state/last_scenario.json (utils/scenario_state.py) — archivo en
disco, sobrevive a reinicios del servidor y actualizaciones de version.
Es la causa raiz confirmada del bug 'grafico en blanco tras actualizar la
app': un archivo sin schema_version (de una version anterior) se descarta
automaticamente en vez de precargar valores de control incompatibles
(ej. duracion_t8 fuera de las 5 opciones fijas actuales)."""
