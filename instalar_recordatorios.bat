@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Instalar recordatorios automaticos de WhatsApp
echo ============================================================
echo.
echo Esto crea una tarea programada de Windows ("AgendaCitasRecordatorios")
echo que revisa cada 15 minutos si hay citas en las proximas 2 horas y
echo manda el recordatorio de WhatsApp. No manda nada de verdad hasta que
echo llenes recordatorios_config.py con tus credenciales de Meta.
echo.
echo Para quitarla despues: abre el "Programador de tareas" de Windows y
echo borra la tarea "AgendaCitasRecordatorios" (o corre:
echo   schtasks /delete /tn "AgendaCitasRecordatorios" /f
echo ).
echo.
pause

schtasks /create /tn "AgendaCitasRecordatorios" /tr "\"C:\Users\alang\AppData\Local\Microsoft\WindowsApps\python.exe\" \"%~dp0enviar_recordatorios.py\"" /sc minute /mo 15 /f

echo.
echo ============================================================
echo   Listo. Para probarla ahora mismo:
echo   schtasks /run /tn "AgendaCitasRecordatorios"
echo   Y revisa el archivo recordatorios.log en esta carpeta.
echo ============================================================
pause
