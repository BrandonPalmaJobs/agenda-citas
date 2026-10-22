@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   CARGAR DEMO: Clinica Dental Aika Solutions
echo ============================================================
echo.
echo Esto convierte el negocio "demo" (la base que ve la app en
echo ?negocio=demo) en la demo dental, con dentistas, pacientes y
echo citas ficticias. BORRA lo que ese negocio tenga, pero antes
echo guarda un respaldo en la carpeta respaldos\.
echo.
echo Te va a pedir que escribas SI para confirmar.
echo.
pause

python cargar_demo.py demo

echo.
echo ============================================================
echo   Termino. Revisa arriba si dijo "Listo". Presiona una tecla
echo   para cerrar esta ventana.
echo ============================================================
pause >nul
