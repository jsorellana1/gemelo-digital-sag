"""
build_portable.py — Build oficial del portable Gemelo Digital Molienda.

Unico camino soportado para generar `dist/Gemelo_Digital_Molienda/`.
NUNCA editar archivos dentro de esa carpeta a mano — se pierden en el
proximo build. Todo cambio va en:

  - Codigo/motor/UI          -> 05_Dashboard/{app.py,pages/,components/,engine/}
  - Datos runtime            -> 05_Dashboard/{runtime_data/,assets/,config/}
  - Documentos de entrega    -> 05_Dashboard/packaging/
      (README_USUARIO.md, GUIA_RAPIDA_VALIDACION.md, FORMULARIO_FEEDBACK_
      VALIDACION.md/.xlsx, VERSION.txt, QA_CHECKLIST.md — los .pdf se
      regeneran con _build_manual_pdf.py)

Pasos:
  1. PyInstaller --onedir (mismos args que build_exe.bat).
  2. Copia runtime_data/, assets/, config/ desde 05_Dashboard/.
  3. Copia todo el contenido de 05_Dashboard/packaging/ al portable.
  4. Limpia artefactos de test (outputs/ generado en runs previos).
  5. Comprime dist/Gemelo_Digital_Molienda/ en dist/Gemelo_Digital_Molienda.zip.

El build --onedir genera ~3.700 archivos sueltos (DLLs de pandas/numpy/
scipy/pyarrow, etc.). Copiar esa carpeta directo a una ruta sincronizada
por OneDrive (ej. Simulador_CIO/) es muy lento porque OneDrive sincroniza
archivo por archivo. Por eso el build SIEMPRE termina en un .zip: para
distribuir/copiar a OneDrive, usar el .zip (1 solo archivo), no la carpeta
suelta.

Uso:
    python 05_Dashboard/scripts/build_portable.py
"""
import os
import shutil
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DASH_DIR = os.path.dirname(_HERE)
DIST_NAME = "Gemelo_Digital_Molienda"
DIST_DIR = os.path.join(DASH_DIR, "dist", DIST_NAME)
PACKAGING_DIR = os.path.join(DASH_DIR, "packaging")

PYINSTALLER_ARGS = [
    sys.executable, "-m", "PyInstaller",
    "--onedir", "--console", "--noconfirm", "--name", DIST_NAME,
    "--collect-all", "dash",
    "--collect-all", "dash_bootstrap_components",
    "--collect-all", "plotly",
    "--hidden-import", "pandas",
    "--hidden-import", "numpy",
    "--hidden-import", "scipy",
    "--hidden-import", "scipy.stats",
    "--hidden-import", "pyarrow",
    "--hidden-import", "openpyxl",
    "--exclude-module", "torch",
    "--exclude-module", "torchvision",
    "--exclude-module", "torchaudio",
    "--exclude-module", "sklearn",
    "--exclude-module", "numba",
    "--exclude-module", "llvmlite",
    "--exclude-module", "tensorflow",
    "--exclude-module", "keras",
    "--exclude-module", "xgboost",
    "--exclude-module", "lightgbm",
    "--exclude-module", "catboost",
    "--exclude-module", "statsmodels",
    "--exclude-module", "shap",
    "--exclude-module", "ruptures",
    "--exclude-module", "matplotlib",
    "--exclude-module", "jupyter",
    "--exclude-module", "notebook",
    "--exclude-module", "ipykernel",
    "--exclude-module", "IPython",
    "--exclude-module", "pytest",
    "--exclude-module", "tkinter",
    "run_app.py",  # relativo: subprocess.run(cwd=DASH_DIR) -> mismo patron que build_exe.bat
]


def log(msg):
    print(f"[build_portable] {msg}")


def _rmtree_with_retry(path: str, attempts: int = 10, delay_s: float = 3.0):
    """OneDrive puede mantener un lock transitorio sobre archivos recien
    sincronizados (PermissionError WinError 5) justo despues de un build
    anterior. Reintenta con espera en vez de fallar de inmediato."""
    for i in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except PermissionError as e:
            if i == attempts - 1:
                raise
            log(f"  rmtree bloqueado (intento {i+1}/{attempts}): {e}. Reintentando en {delay_s}s...")
            time.sleep(delay_s)


def step1_pyinstaller():
    log("Paso 1/3: PyInstaller --onedir ...")
    if os.path.isdir(DIST_DIR):
        _rmtree_with_retry(DIST_DIR)
    result = subprocess.run(PYINSTALLER_ARGS, cwd=DASH_DIR)
    if result.returncode != 0:
        raise SystemExit(f"PyInstaller fallo con codigo {result.returncode}")
    log("PyInstaller OK.")


def step2_copy_runtime():
    log("Paso 2/3: copiando runtime_data/, assets/, config/ ...")
    for folder in ("runtime_data", "assets", "config"):
        src = os.path.join(DASH_DIR, folder)
        dst = os.path.join(DIST_DIR, folder)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
            log(f"  {folder}/ copiado.")
        else:
            log(f"  ADVERTENCIA: {folder}/ no existe en {DASH_DIR}, se omite.")


def step3_copy_packaging():
    log("Paso 3/4: copiando documentos de packaging/ ...")
    if not os.path.isdir(PACKAGING_DIR):
        log(f"  ADVERTENCIA: {PACKAGING_DIR} no existe, no se copia documentacion.")
        return
    for name in os.listdir(PACKAGING_DIR):
        src = os.path.join(PACKAGING_DIR, name)
        dst = os.path.join(DIST_DIR, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            log(f"  {name} copiado.")


def step4_zip():
    log("Paso 4/4: comprimiendo a .zip (para distribuir via OneDrive) ...")
    zip_path = shutil.make_archive(DIST_DIR, "zip", root_dir=os.path.dirname(DIST_DIR), base_dir=DIST_NAME)
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    log(f"  {zip_path} ({size_mb:.1f} MB)")
    return zip_path


def main():
    t0 = time.perf_counter()
    step1_pyinstaller()
    step2_copy_runtime()
    step3_copy_packaging()
    # Limpiar artefactos que la app pudo generar en corridas de prueba previas
    stray_outputs = os.path.join(DIST_DIR, "outputs")
    if os.path.isdir(stray_outputs):
        shutil.rmtree(stray_outputs)
    zip_path = step4_zip()
    dt = time.perf_counter() - t0
    log(f"Build completo en {dt:.1f}s -> {DIST_DIR}")
    log(f"Para copiar a OneDrive/Simulador_CIO, usar el .zip: {zip_path}")


if __name__ == "__main__":
    main()
