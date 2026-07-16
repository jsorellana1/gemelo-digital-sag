@echo off
REM release_portable.bat - Pipeline de release en un clic: tests -> build ->
REM manifiesto -> verificacion de sync. Correr desde 05_Dashboard/ (o
REM doble-click, se ubica solo via %~dp0).
REM
REM Aborta sin generar build si los tests fallan. Nunca reemplaza a
REM build_portable.py ni a sync_portable_to_dev.py: solo los encadena.

cd /d "%~dp0"

echo ============================================================
echo  1/4 Tests (gate obligatorio antes del build)
echo ============================================================
REM test_portable_smoke.py y test_performance_portable.py NO son suites
REM pytest: a nivel de modulo hacen
REM   PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8050
REM Bajo "python -m pytest tests", sys.argv[1] es el primer argumento de
REM pytest (ej. "tests"), no un puerto -> sin --ignore, pytest CRASHEA
REM (ValueError) al importar estos archivos durante la coleccion, no
REM simplemente "no encuentra tests". Son scripts standalone para correr
REM contra el .exe ya levantado (ver sus propios docstrings).
python -m pytest tests --ignore=tests/test_portable_smoke.py --ignore=tests/test_performance_portable.py -q
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  ABORTADO: los tests fallaron. NO se genera el build portable.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  2/4 Build portable (PyInstaller + runtime_data + packaging)
echo ============================================================
python scripts\build_portable.py
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  ABORTADO: build_portable.py fallo.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  3/4 Manifiesto de release trazable
echo ============================================================
python scripts\generate_release_manifest.py --tests-passed true
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  ABORTADO: no se pudo generar release_manifest.json.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  4/4 Verificacion de sincronizacion dist vs fuente
echo ============================================================
python scripts\sync_portable_to_dev.py
set SYNC_RESULT=%ERRORLEVEL%
if %SYNC_RESULT% NEQ 0 (
    echo.
    echo ************************************************************
    echo  ADVERTENCIA: sync_portable_to_dev.py encontro diferencias
    echo  justo despues de un build recien hecho. Esto es una senal de
    echo  alerta: build_portable.py deberia dejar dist/ identico a la
    echo  fuente. Revisar 05_Dashboard\outputs\logs\sync_portable_to_dev.log
    echo ************************************************************
)

echo.
echo ============================================================
echo  Release portable generado.
echo  Carpeta: dist\Gemelo_Digital_Molienda
echo  Zip para distribuir/copiar a OneDrive: dist\Gemelo_Digital_Molienda.zip
echo  (version y git hash: ver release_manifest.json en esa carpeta)
echo ============================================================
pause
exit /b %SYNC_RESULT%
