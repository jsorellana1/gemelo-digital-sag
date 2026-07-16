"""
test_portable_smoke.py — Fase 3 QA: smoke test HTTP contra el portable
`.exe` YA CORRIENDO (no levanta el proceso, no requiere el codigo fuente
Python — corre contra cualquier instancia en http://127.0.0.1:<puerto>).

Uso:
    python tests/test_portable_smoke.py [puerto]

Sale con exit code 0 si todo pasa, 1 si algo falla. No usa pytest (pytest
esta explicitamente excluido del build PyInstaller, ver build_exe.bat) ni
librerias externas (solo stdlib) para poder correr contra el portable sin
depender del entorno de desarrollo.
"""
import sys
import json
import urllib.request
import urllib.error

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8050
BASE = f"http://127.0.0.1:{PORT}"

results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"excepcion: {e}"
    results.append((name, ok, detail))
    print(f"[{'OK' if ok else 'FAIL'}] {name} — {detail}")
    return ok


def _get(path, timeout=5):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read()


def check_root():
    status, body = _get("/")
    return status == 200 and b"<div" in body, f"status={status} len={len(body)}"


def check_riesgo_route():
    # Dash es SPA: cualquier ruta valida debe devolver el mismo shell 200,
    # no un 404 de Flask (confirma que no hay conflicto de routing).
    status, body = _get("/riesgo")
    return status == 200 and b"<div" in body, f"status={status}"


def check_simulador_route():
    status, body = _get("/")  # "/" ES el simulador operacional (ver CLAUDE.md)
    return status == 200, f"status={status}"


def check_assets():
    status, body = _get("/assets/styles.css")
    return status == 200 and len(body) > 0, f"status={status} len={len(body)}"


def check_dash_layout():
    status, body = _get("/_dash-layout")
    try:
        json.loads(body)
        valid_json = True
    except Exception:
        valid_json = False
    return status == 200 and valid_json, f"status={status} json_valido={valid_json}"


def check_dash_dependencies():
    status, body = _get("/_dash-dependencies")
    try:
        deps = json.loads(body)
    except Exception:
        deps = []
    return status == 200 and isinstance(deps, list) and len(deps) > 5, f"status={status} n_callbacks={len(deps) if isinstance(deps, list) else '?'}"


def check_no_500_on_favicon():
    # No debe reventar aunque no exista favicon custom.
    try:
        status, _ = _get("/favicon.ico")
    except urllib.error.HTTPError as e:
        status = e.code
    return status in (200, 404), f"status={status}"


if __name__ == "__main__":
    checks = [
        ("Servidor responde en /", check_root),
        ("Ruta /riesgo responde (SPA shell)", check_riesgo_route),
        ("Pagina simulador (/) responde", check_simulador_route),
        ("Assets (styles.css) cargan", check_assets),
        ("/_dash-layout devuelve JSON valido", check_dash_layout),
        ("/_dash-dependencies lista callbacks registrados", check_dash_dependencies),
        ("/favicon.ico no causa 500", check_no_500_on_favicon),
    ]
    all_ok = True
    for name, fn in checks:
        if not check(name, fn):
            all_ok = False

    print()
    print(f"Resultado: {'TODOS LOS CHECKS PASARON' if all_ok else 'HAY FALLOS'}")
    sys.exit(0 if all_ok else 1)
