"""
Credenciales de WhatsApp (Meta WhatsApp Business Cloud API) para los
recordatorios automaticos de citas. Mientras estos campos esten vacios,
enviar_recordatorios.py no manda nada (solo lo avisa en el log) - es seguro
dejar esto en blanco y programar la tarea desde ya.

Como llenarlo:
1. Crea una cuenta de Meta Business y una app en developers.facebook.com con
   el producto "WhatsApp" agregado.
2. En el panel de WhatsApp de esa app veras el "Phone number ID" y el
   "WhatsApp Business Account ID" - copia el Phone number ID abajo.
3. Genera un token de acceso permanente (Configuracion del negocio > Usuarios
   del sistema > crear un "System User", asignarle la app de WhatsApp, y
   generar su token con permiso whatsapp_business_messaging).
4. Crea y manda a aprobar una plantilla de mensaje (Meta no deja mandar texto
   libre para avisos que tu iniciaste, tiene que ser una plantilla aprobada).
   Ejemplo de cuerpo de plantilla:
       "Hola {{1}}, te recordamos tu cita en {{2}} el {{3}} a las {{4}}."
   Copia el nombre EXACTO de la plantilla (no el texto) en
   WHATSAPP_TEMPLATE_NAME.
"""

WHATSAPP_PHONE_NUMBER_ID = ""
WHATSAPP_ACCESS_TOKEN = ""
WHATSAPP_TEMPLATE_NAME = "recordatorio_cita"
WHATSAPP_TEMPLATE_IDIOMA = "es_MX"

# Se antepone a los telefonos guardados en Clientes si no empiezan ya con un
# '+' o con este mismo codigo (asume numeros mexicanos de 10 digitos).
CODIGO_PAIS = "52"
