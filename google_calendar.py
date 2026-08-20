"""
Crea (y borra) eventos en Google Calendar cuando se agenda o cancela una
cita, para que el cliente reciba la invitacion por correo y Google le mande
el recordatorio solo - sin costo, sin plantillas que aprobar.

Todo aqui es "best effort": si algo falla (no conectado todavia, sin
internet, cliente sin correo) se regresa un error como texto y la cita
sigue guardandose normal - esto nunca debe tronar el agendado.
"""

import os

import google_calendar_config as config

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def configurado():
    return os.path.exists(config.ARCHIVO_TOKEN)


def _servicio():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(config.ARCHIVO_TOKEN, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(config.ARCHIVO_TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def crear_evento_cita(negocio_nombre, servicio_nombre, proveedor_nombre, cliente_nombre,
                       cliente_email, fecha, hora_inicio, hora_fin, notas=""):
    """Crea el evento y regresa (event_id, None), o (None, "razon") si no se pudo."""
    if not configurado():
        return None, "Google Calendar no esta conectado todavia (falta correr autorizar_google_calendar.py)"
    if not cliente_email:
        return None, "el cliente no tiene correo guardado"

    evento = {
        "summary": f"{servicio_nombre} - {cliente_nombre}",
        "description": f"Negocio: {negocio_nombre}\nCon: {proveedor_nombre}\n{notas}".strip(),
        "start": {"dateTime": f"{fecha}T{hora_inicio}:00", "timeZone": config.ZONA_HORARIA},
        "end": {"dateTime": f"{fecha}T{hora_fin}:00", "timeZone": config.ZONA_HORARIA},
        "attendees": [{"email": cliente_email}],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": config.MINUTOS_RECORDATORIO},
                {"method": "email", "minutes": config.MINUTOS_RECORDATORIO},
            ],
        },
    }

    try:
        servicio = _servicio()
        creado = servicio.events().insert(
            calendarId=config.CALENDAR_ID, body=evento, sendUpdates="all"
        ).execute()
        return creado.get("id"), None
    except Exception as e:
        return None, str(e)


def borrar_evento(evento_id):
    """Cancela el evento en Calendar (ej. cuando se cancela la cita).
    Silencioso si falla - no es critico."""
    if not configurado() or not evento_id:
        return
    try:
        servicio = _servicio()
        servicio.events().delete(
            calendarId=config.CALENDAR_ID, eventId=evento_id, sendUpdates="all"
        ).execute()
    except Exception:
        pass
