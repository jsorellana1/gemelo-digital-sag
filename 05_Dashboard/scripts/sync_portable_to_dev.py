"""
sync_portable_to_dev.py — Detecta divergencia entre el portable construido
(`dist/Gemelo_Digital_Molienda/`) y la fuente de desarrollo (`05_Dashboard/`
+ `05_Dashboard/packaging/`).

Importante sobre alcance: el codigo Python (app.py, pages/, components/,
engine/) NO puede divergir de forma silenciosa porque el portable se
COMPILA desde ese mismo codigo en cada build (ver build_portable.py) — no
existe una copia editable separada dentro de `_internal/` (es un bundle
PyInstaller, no archivos .py sueltos). Por eso este script compara:

  1. Datos runtime: runtime_data/, assets/, config/ (copiados 1:1 al portable)
  2. Documentos de entrega: packaging/* (copiados 1:1 al portable)

y reporta cualquier archivo que exista SOLO en el portable (indicio de que
alguien edito dist/ a mano, saltandose build_portable.py) o cuyo hash no
coincida con la fuente.

Uso:
    python 05_Dashboard/scripts/sync_portable_to_dev.py           # solo reporta
    python 05_Dashboard/scripts/sync_portable_to_dev.py --apply   # copia devuelta
                                                                    (con backup)
"""
import hashlib
import os
import shutil
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DASH_DIR = os.path.dirname(_HERE)
DIST_DIR = os.path.join(DASH_DIR, "dist", "Gemelo_Digital_Molienda")
PACKAGING_DIR = os.path.join(DASH_DIR, "packaging")
BACKUP_DIR = os.path.join(DASH_DIR, "dist", "_backups")
LOG_PATH = os.path.join(DASH_DIR, "outputs", "logs", "sync_portable_to_dev.log")

# (carpeta/archivo en el portable, carpeta/archivo equivalente en la fuente)
SYNC_TARGETS = [
    ("runtime_data", os.path.join(DASH_DIR, "runtime_data")),
    ("assets", os.path.join(DASH_DIR, "assets")),
    ("config", os.path.join(DASH_DIR, "config")),
    # Documentos de entrega: cada archivo top-level del portable que
    # coincide por nombre con algo en packaging/ se compara ahi.
]

DOC_NAMES = [
    "README_USUARIO.md", "README_USUARIO.pdf",
    "GUIA_RAPIDA_VALIDACION.md", "GUIA_RAPIDA_VALIDACION.pdf",
    "FORMULARIO_FEEDBACK_VALIDACION.md", "FORMULARIO_FEEDBACK_VALIDACION.xlsx",
    "VERSION.txt", "QA_CHECKLIST.md",
]


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_files(base: str):
    for root, _dirs, files in os.walk(base):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base)
            yield rel, full


def _log(lines: list[str]):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n=== sync_portable_to_dev — {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        for line in lines:
            f.write(line + "\n")


def compare_folder(name: str, dist_sub: str, src_sub: str):
    diffs = []
    if not os.path.isdir(dist_sub):
        return diffs
    if not os.path.isdir(src_sub):
        diffs.append(("SOLO_EN_DIST_CARPETA_FALTA_EN_FUENTE", name, ""))
        return diffs
    src_files = dict(_walk_files(src_sub))
    dist_files = dict(_walk_files(dist_sub))
    for rel, dist_full in dist_files.items():
        if rel not in src_files:
            diffs.append(("SOLO_EN_DIST", f"{name}/{rel}", dist_full))
        elif _hash_file(dist_full) != _hash_file(src_files[rel]):
            diffs.append(("HASH_DISTINTO", f"{name}/{rel}", dist_full))
    for rel in src_files:
        if rel not in dist_files:
            diffs.append(("SOLO_EN_FUENTE", f"{name}/{rel}", src_files[rel]))
    return diffs


def compare_docs():
    diffs = []
    for doc in DOC_NAMES:
        dist_path = os.path.join(DIST_DIR, doc)
        src_path = os.path.join(PACKAGING_DIR, doc)
        if not os.path.isfile(dist_path):
            continue
        if not os.path.isfile(src_path):
            diffs.append(("SOLO_EN_DIST", doc, dist_path))
        elif _hash_file(dist_path) != _hash_file(src_path):
            diffs.append(("HASH_DISTINTO", doc, dist_path))
    return diffs


def main():
    apply_changes = "--apply" in sys.argv

    if not os.path.isdir(DIST_DIR):
        print(f"No existe {DIST_DIR} — nada que comparar (correr build_portable.py primero).")
        return 0

    all_diffs = []
    for name, src_sub in SYNC_TARGETS:
        dist_sub = os.path.join(DIST_DIR, name)
        all_diffs.extend(compare_folder(name, dist_sub, src_sub))
    all_diffs.extend(compare_docs())

    if not all_diffs:
        print("Sin diferencias — portable y fuente (05_Dashboard/ + packaging/) sincronizados.")
        _log(["Sin diferencias."])
        return 0

    print(f"Se encontraron {len(all_diffs)} diferencia(s):")
    log_lines = [f"{len(all_diffs)} diferencia(s) encontradas:"]
    for kind, rel, path in all_diffs:
        line = f"  [{kind}] {rel}"
        print(line)
        log_lines.append(line)

    if apply_changes:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        copied = 0
        for kind, rel, dist_path in all_diffs:
            if kind not in ("SOLO_EN_DIST", "HASH_DISTINTO"):
                continue
            # Determinar destino en la fuente
            if rel in DOC_NAMES:
                target = os.path.join(PACKAGING_DIR, rel)
            else:
                target = os.path.join(DASH_DIR, rel)
            if os.path.isfile(target):
                backup_name = f"{os.path.basename(target)}.bak_{time.strftime('%Y%m%d%H%M%S')}"
                shutil.copy2(target, os.path.join(BACKUP_DIR, backup_name))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(dist_path, target)
            copied += 1
            log_lines.append(f"  COPIADO dist -> fuente: {rel} (backup creado si existia)")
        print(f"\n{copied} archivo(s) copiados de dist/ hacia la fuente, con backup en {BACKUP_DIR}.")

    _log(log_lines)
    return 1


if __name__ == "__main__":
    sys.exit(main())
