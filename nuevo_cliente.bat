@echo off
setlocal
cd /d "%~dp0"
python nuevo_cliente.py
echo.
echo Presiona una tecla para cerrar esta ventana.
pause >nul
