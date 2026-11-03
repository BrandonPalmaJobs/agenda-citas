"""
WhatsApp (Meta WhatsApp Business Cloud API) para Aika Solutions.

Credenciales (la primera que exista):
  1. Variables de entorno: WHATSAPP_TOKEN y WHATSAPP_PHONE_NUMBER_ID
     (asi corre en GitHub Actions, con secretos del repositorio)
  2. recordatorios_config.py local (WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID)

Plantilla de recordatorio (se crea y aprueba en Meta, ver GUIA_WHATSAPP.md):
  nombre: recordatorio_cita · idioma: es_MX · categoria: Utilidad
  cuerpo: "Hola {{1}}, te recordamos tu cita en {{2}} el {{3}} a las {{4}} con {{5}}.
           ¿Nos confirmas tu asistencia?"
  botones de respuesta rapida: "Confirmo" y "Necesito cancelar"
"""

import os

import requests

GRAPH = "https://graph.facebook.com/v21.0"
PLANTILLA = os.environ.get("WHATSAPP_PLANTILLA", "recordatorio_cita")
IDIOMA = os.environ.get("WHATSAPP_IDIOMA", "es_MX")
CODIGO_PAIS = "52"


def credenciales():
    token = os.environ.get("WHATSAPP_TOKEN")
    numero = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if token and numero:
        return token, numero
    try:  # app de Streamlit: Secrets
        import streamlit as st
        token, numero = st.secrets.get("WHATSAPP_TOKEN"), st.secrets.get("WHATSAPP_PHONE_NUMBER_ID")
        if token and numero:
            return token, str(numero)
    except Exception:
        pass
    try:
        import recordatorios_config as c
        return (c.WHATSAPP_ACCESS_TOKEN or None), (c.WHATSAPP_PHONE_NUMBER_ID or None)
    except ImportError:
        return None, None


def credenciales_configuradas():
    return all(credenciales())


def normalizar_telefono(telefono):
    """Formato internacional sin '+': 52 + 10 digitos para Mexico."""
    digitos = "".join(c for c in (telefono or "") if c.isdigit())
    if len(digitos) == 10:
        return CODIGO_PAIS + digitos
    return digitos


def _enviar(payload):
    token, numero = credenciales()
    if not (token and numero):
        return False, "credenciales de WhatsApp no configuradas"
    try:
        r = requests.post(f"{GRAPH}/{numero}/messages", json={"messaging_product": "whatsapp", **payload},
                          headers={"Authorization": f"Bearer {token}"}, timeout=20)
    except requests.RequestException as e:
        return False, f"error de conexion: {e}"
    if r.status_code == 200:
        return True, None
    return False, f"WhatsApp respondio {r.status_code}: {r.text[:300]}"


def enviar_recordatorio(telefono, cliente_nombre, negocio_nombre, fecha_legible, hora,
                        doctor="nuestro equipo", ref=""):
    """Manda la plantilla con botones. `ref` (ej. 'demo:123') viaja escondido
    en los botones para que el bot sepa que cita confirmar o cancelar."""
    componentes = [{
        "type": "body",
        "parameters": [{"type": "text", "text": str(v)} for v in
                       (cliente_nombre, negocio_nombre, fecha_legible, hora, doctor)],
    }]
    for i, accion in enumerate(("confirmar", "cancelar")):
        componentes.append({"type": "button", "sub_type": "quick_reply", "index": str(i),
                            "parameters": [{"type": "payload", "payload": f"{accion}:{ref}"}]})
    return _enviar({"to": normalizar_telefono(telefono), "type": "template",
                    "template": {"name": PLANTILLA, "language": {"code": IDIOMA}, "components": componentes}})


def enviar_recordatorio_simulado(telefono, cliente_nombre, negocio_nombre, fecha_legible, hora,
                                 doctor="nuestro equipo", ref=""):
    """Igual que el recordatorio pero sin plantilla (mensaje con botones).
    Solo para pruebas: funciona si el paciente escribio en las ultimas 24 h."""
    texto = (f"Hola {cliente_nombre}, te recordamos tu cita en {negocio_nombre} el {fecha_legible} "
             f"a las {hora} con {doctor}. ¿Nos confirmas tu asistencia?")
    botones = [{"type": "reply", "reply": {"id": f"{a}:{ref}", "title": t}}
               for a, t in (("confirmar", "Confirmo"), ("cancelar", "Necesito cancelar"))]
    return _enviar({"to": normalizar_telefono(telefono), "type": "interactive",
                    "interactive": {"type": "button", "body": {"text": texto}, "action": {"buttons": botones}}})


def enviar_texto(telefono, texto):
    """Texto libre: solo funciona si el paciente escribio en las ultimas 24 h."""
    return _enviar({"to": normalizar_telefono(telefono), "type": "text", "text": {"body": texto}})


MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def fecha_bonita(fecha_iso):
    from datetime import date
    f = date.fromisoformat(fecha_iso)
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month]}"


# Avisos cuando la CLINICA cancela o cambia una cita (plantillas cita_cancelada y
# cita_reprogramada; si Meta aun no las aprueba, se intenta como texto normal,
# que solo llega si el paciente escribio en las ultimas 24 h).
AVISOS = {
    "cancelada": ("cita_cancelada",
                  "Hola {0}, te avisamos que tu cita en {1} del {2} a las {3} fue cancelada. "
                  "Si quieres agendar otra fecha, responde a este mensaje o escribe hola."),
    "reprogramada": ("cita_reprogramada",
                     "Hola {0}, tu cita en {1} cambió de fecha. Nueva cita: {2} a las {3} con {4}. "
                     "Si no te acomoda, responde a este mensaje o escribe hola."),
}


def avisar_cambio(tipo, telefono, *valores):
    plantilla, texto = AVISOS[tipo]
    valores = [str(v) for v in valores]
    ok, error = _enviar({"to": normalizar_telefono(telefono), "type": "template",
                         "template": {"name": plantilla, "language": {"code": IDIOMA}, "components": [
                             {"type": "body", "parameters": [{"type": "text", "text": v} for v in valores]}]}})
    if ok:
        return True, None
    ok2, error2 = enviar_texto(telefono, texto.format(*valores))
    return (True, None) if ok2 else (False, error)
