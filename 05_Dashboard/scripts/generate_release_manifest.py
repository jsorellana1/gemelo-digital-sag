"""
generate_release_manifest.py — Genera release_manifest.json trazable para un
build portable ya construido (ver build_portable.py).

Requiere que dist/Gemelo_Digital_Molienda/ ya exista (correr build_portable.py
antes). Lee la version desde packaging/VERSION.txt (fuente unica de verdad),
el commit actual via git y si el working tree estaba limpio al momento del
build.

Uso:
    python 05_Dashboard/scripts/generate_release_manifest.py --tests-passed true
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
DASH_DIR = os.path.dirname(_HERE)
REPO_ROOT = os.path.dirname(DASH_DIR)
DIST_NAME = "Gemelo_Digital_Molienda"
DIST_DIR = os.path.join(DASH_DIR, "dist", DIST_NAME)
PACKAGING_DIR = os.path.join(DASH_DIR, "packaging")
VERSION_PATH = os.path.join(PACKAGING_DIR, "VERSION.txt")
MANIFEST_PATH = os.path.join(DIST_DIR, "release_manifest.json")

SCHEMA_VERSION = 1


def log(msg):
    print(f"[generate_release_manifest] {msg}")


def _parse_version() -> str:
    with open(VERSION_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    match = re.search(r"^Version:\s*(\S+)", text, re.MULTILINE)
    if not match:
        raise SystemExit(
            f"No se encontro una linea 'Version: X' en {VERSION_PATH}. "
            "El manifiesto no puede generarse sin una version valida."
        )
    return match.group(1)


def _git_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        log(f"ADVERTENCIA: git rev-parse fallo: {result.stderr.strip()}")
    except FileNotFoundError:
        log("ADVERTENCIA: git no esta disponible en PATH.")
    return "unknown"


def _git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except FileNotFoundError:
        pass
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-passed", choices=["true", "false"], required=True)
    args = parser.parse_args()

    if not os.path.isdir(DIST_DIR):
        raise SystemExit(
            f"No existe {DIST_DIR}. Correr build_portable.py antes de generar el manifiesto."
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "version": _parse_version(),
        "build_date": datetime.now(timezone.utc).isoformat(),
        "git_hash": _git_hash(),
        "git_dirty": _git_dirty(),
        "tests_passed": args.tests_passed == "true",
    }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    log(
        f"version={manifest['version']} git_hash={manifest['git_hash']} "
        f"git_dirty={manifest['git_dirty']} tests_passed={manifest['tests_passed']} "
        f"-> {MANIFEST_PATH}"
    )


if __name__ == "__main__":
    sys.exit(main())
