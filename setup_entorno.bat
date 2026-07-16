@echo off
REM ============================================================
REM  Setup entorno virtual SAG — Plataforma Analítica Molienda
REM  División El Teniente — Codelco
REM ============================================================

echo ============================================================
echo  Creando entorno virtual 'sag'
echo ============================================================

python -m venv sag

echo.
echo Activando entorno...
call sag\Scripts\activate.bat

echo.
echo Actualizando pip...
python -m pip install --upgrade pip

echo.
echo ============================================================
echo  Instalando dependencias desde requirements.txt
echo ============================================================
pip install -r requirements.txt

echo.
echo ============================================================
echo  Registrando kernel Jupyter para entorno 'sag'
echo ============================================================
python -m ipykernel install --user --name=sag --display-name "Python (sag - Molienda)"

echo.
echo ============================================================
echo  Entorno listo. Para activar manualmente:
echo    sag\Scripts\activate
echo  Para abrir JupyterLab:
echo    jupyter lab
echo ============================================================

pause
