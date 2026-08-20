"""
Credenciales para crear eventos en Google Calendar cuando se agenda una
cita - el cliente recibe la invitacion por correo y Google le manda el
recordatorio solo (sin costo, sin plantillas que aprobar como WhatsApp).

Como conectarlo (una sola vez):
1. Entra a https://console.cloud.google.com/ y crea un proyecto (o usa uno
   que ya tengas).
2. Busca "Google Calendar API" en el buscador de arriba y dale "Habilitar".
3. Ve a "APIs y servicios" > "Pantalla de consentimiento OAuth": tipo
   "Externo", agrega tu propio correo como "usuario de prueba" (no hace
   falta publicarla ni verificarla con Google para uso propio).
4. Ve a "Credenciales" > "Crear credenciales" > "ID de cliente de OAuth" >
   tipo de aplicacion "App de escritorio". Descarga el archivo JSON.
5. Guarda ese archivo en esta misma carpeta (agenda_citas/) con el nombre
   exacto google_client_secret.json - el .gitignore ya lo protege.
6. Corre, una sola vez:  python autorizar_google_calendar.py
   Se abre tu navegador para iniciar sesion con la cuenta de Google/Gmail
   donde quieres que aparezcan las citas del negocio. Eso genera
   google_token.json (tambien protegido), que despues se renueva solo.
"""

ARCHIVO_CLIENT_SECRET = "google_client_secret.json"
ARCHIVO_TOKEN = "google_token.json"
CALENDAR_ID = "primary"
ZONA_HORARIA = "America/Mexico_City"
MINUTOS_RECORDATORIO = 120
