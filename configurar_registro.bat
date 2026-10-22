@echo off
setlocal
cd /d "%~dp0"
python configurar_registro.py
echo.
echo Presiona una tecla para cerrar esta ventana.
pause >nul
