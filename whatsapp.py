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


def enviar_texto(telefono, texto):
    """Texto libre: solo funciona si el paciente escribio en las ultimas 24 h."""
    return _enviar({"to": normalizar_telefono(telefono), "type": "text", "text": {"body": texto}})
