"""
Envio de recordatorios de citas por WhatsApp usando la Meta WhatsApp
Business Cloud API. Las credenciales viven en recordatorios_config.py
(no se sube a git - ver ese archivo para como llenarlo).

Este modulo no hace nada por si solo: enviar_recordatorios.py lo llama una
vez por cada cita que necesita aviso.
"""

import requests

import recordatorios_config as config

GRAPH_API_URL = "https://graph.facebook.com/v20.0/{phone_number_id}/messages"


def credenciales_configuradas():
    return bool(config.WHATSAPP_PHONE_NUMBER_ID and config.WHATSAPP_ACCESS_TOKEN)


def normalizar_telefono(telefono):
    """Deja el telefono en formato internacional (solo digitos, con codigo
    de pais) que espera la API de WhatsApp. Asume numeros de Mexico si el
    telefono no trae ya un codigo de pais."""
    digitos = "".join(c for c in telefono if c.isdigit())
    if digitos.startswith(config.CODIGO_PAIS):
        return digitos
    return config.CODIGO_PAIS + digitos


def enviar_recordatorio(telefono, cliente_nombre, negocio_nombre, fecha_legible, hora):
    """Manda la plantilla de recordatorio a un telefono. Regresa (True, None)
    si se mando, o (False, "razon") si no - nunca lanza una excepcion, para
    que el script que llama a esto pueda seguir con la siguiente cita."""
    if not credenciales_configuradas():
        return False, "credenciales de WhatsApp no configuradas (recordatorios_config.py)"

    url = GRAPH_API_URL.format(phone_number_id=config.WHATSAPP_PHONE_NUMBER_ID)
    headers = {"Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": normalizar_telefono(telefono),
        "type": "template",
        "template": {
            "name": config.WHATSAPP_TEMPLATE_NAME,
            "language": {"code": config.WHATSAPP_TEMPLATE_IDIOMA},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": cliente_nombre},
                    {"type": "text", "text": negocio_nombre},
                    {"type": "text", "text": fecha_legible},
                    {"type": "text", "text": hora},
                ],
            }],
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
    except requests.RequestException as e:
        return False, f"error de conexion: {e}"

    if resp.status_code == 200:
        return True, None
    return False, f"WhatsApp API respondio {resp.status_code}: {resp.text[:300]}"
