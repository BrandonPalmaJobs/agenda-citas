"""
Revisa agenda_citas.db por citas 'Agendada' que empiecen en las proximas
2 horas y les manda un recordatorio de WhatsApp (solo si ya llenaste
recordatorios_config.py con credenciales reales de Meta - si no, no hace
nada y lo anota en el log).

Uso manual:
    python enviar_recordatorios.py

Pensado para correr solo cada 15-20 minutos via el Programador de tareas de
Windows - ver instalar_recordatorios.bat.
"""

import os
from datetime import datetime, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import db
import whatsapp

LOG_PATH = "recordatorios.log"
VENTANA_HORAS = 2

MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _fecha_legible(fecha_iso):
    f = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month]}"


def _log(mensaje):
    linea = f"{datetime.now().isoformat(timespec='seconds')}  {mensaje}"
    print(linea)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def main():
    db.init_db()

    if not whatsapp.credenciales_configuradas():
        _log("Sin credenciales de WhatsApp configuradas todavia (recordatorios_config.py) - nada que hacer.")
        return

    ahora = datetime.now()
    limite = ahora + timedelta(hours=VENTANA_HORAS)
    citas = db.citas_para_recordar(
        ahora.strftime("%Y-%m-%dT%H:%M"), limite.strftime("%Y-%m-%dT%H:%M")
    )

    if not citas:
        _log("Sin citas por recordar en este momento.")
        return

    negocio = db.get_negocio()
    for c in citas:
        if not c["cliente_telefono"]:
            _log(f"Cita {c['id']}: el cliente no tiene telefono guardado, se omite.")
            continue
        ok, error = whatsapp.enviar_recordatorio(
            telefono=c["cliente_telefono"],
            cliente_nombre=c["cliente_nombre"],
            negocio_nombre=negocio["nombre"],
            fecha_legible=_fecha_legible(c["fecha"]),
            hora=c["hora_inicio"],
        )
        if ok:
            db.marcar_recordatorio_enviado(c["id"])
            _log(f"Cita {c['id']} ({c['cliente_nombre']}, {c['fecha']} {c['hora_inicio']}): recordatorio enviado.")
        else:
            _log(f"Cita {c['id']} ({c['cliente_nombre']}): NO se pudo enviar - {error}")


if __name__ == "__main__":
    main()
