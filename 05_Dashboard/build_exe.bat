@echo off
REM build_exe.bat — Genera el ejecutable standalone del Gemelo Digital de
REM Molienda con PyInstaller. Correr desde 05_Dashboard/ (o doble-click,
REM el script se ubica solo via %~dp0).
REM
REM NOTA: runtime_data/, assets/ y config/ NO se embeben dentro del .exe
REM (serian re-empaquetados en cada build). Se copian como carpetas
REM hermanas del .exe en el paso de "carpeta portable" (ver
REM 04_Reports/Technical/20260702_Construccion_EXE.md).
REM
REM NOTA: se usa consola (sin --windowed) a proposito, para que el splash
REM y los mensajes de error de run_app.py sean visibles al usuario final.
REM
REM NOTA (2026-07-06): se cambio de --onefile a --onedir. --onefile
REM descomprime todo en una carpeta temporal (%TEMP%) EN CADA apertura,
REM lo que hacia el arranque notoriamente mas lento para usuarios externos.
REM --onedir deja los archivos ya extraidos en dist/, el .exe solo carga
REM la DLL/py compartida sin descomprimir nada -> apertura mucho mas rapida
REM a costa de distribuir una carpeta en vez de un solo archivo (ya se
REM distribuye como carpeta portable de todos modos, ver nota mas abajo).

cd /d "%~dp0"

REM IMPORTANTE: el entorno Python de desarrollo tiene instaladas librerias
REM de entrenamiento ML de otras partes del proyecto (02_Analytics/) que
REM NO usa el dashboard en runtime (torch, sklearn, numba, etc. — ver
REM auditoria en 04_Reports/Technical/20260702_Construccion_EXE.md).
REM PyInstaller las detecta por analisis estatico de imports transitivos
REM (incluso dentro de try/except no ejecutados) e infla el .exe a varios
REM GB si no se excluyen explicitamente.
python -m PyInstaller --onedir --console --noconfirm --name "Gemelo_Digital_Molienda" ^
  --collect-all dash ^
  --collect-all dash_bootstrap_components ^
  --collect-all plotly ^
  --hidden-import pandas ^
  --hidden-import numpy ^
  --hidden-import scipy ^
  --hidden-import scipy.stats ^
  --hidden-import pyarrow ^
  --hidden-import openpyxl ^
  --exclude-module torch ^
  --exclude-module torchvision ^
  --exclude-module torchaudio ^
  --exclude-module sklearn ^
  --exclude-module numba ^
  --exclude-module llvmlite ^
  --exclude-module tensorflow ^
  --exclude-module keras ^
  --exclude-module xgboost ^
  --exclude-module lightgbm ^
  --exclude-module catboost ^
  --exclude-module statsmodels ^
  --exclude-module shap ^
  --exclude-module ruptures ^
  --exclude-module matplotlib ^
  --exclude-module jupyter ^
  --exclude-module notebook ^
  --exclude-module ipykernel ^
  --exclude-module IPython ^
  --exclude-module pytest ^
  --exclude-module tkinter ^
  run_app.py

echo.
echo Build terminado. Ejecutable en dist\Gemelo_Digital_Molienda\Gemelo_Digital_Molienda.exe
