@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   AGENDA DE CITAS
echo ============================================================
echo.
echo Esto abre la app en tu navegador (se abre solo). La primera
echo vez puede tardar un poco mas porque instala lo necesario.
echo.
echo Para CERRAR la app: regresa a esta ventana negra y presiona
echo Ctrl+C, o simplemente cierrala. Cerrar solo la pestana del
echo navegador NO apaga la app.
echo.

python -c "import streamlit" 2>nul
if errorlevel 1 (
    echo Instalando lo necesario la primera vez, un momento...
    pip install -r requirements.txt
    echo.
)

streamlit run app.py

echo.
echo ============================================================
echo   La app se cerro. Presiona una tecla para cerrar esta ventana.
echo ============================================================
pause >nul
