"""
Corre esto UNA SOLA VEZ, despues de poner google_client_secret.json en esta
carpeta (ver instrucciones en google_calendar_config.py):

    python autorizar_google_calendar.py

Abre tu navegador para que autorices el acceso a tu Google Calendar y
genera google_token.json - la app lo reutiliza y renueva sola despues.
"""

import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from google_auth_oauthlib.flow import InstalledAppFlow

import google_calendar_config as config

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main():
    if not os.path.exists(config.ARCHIVO_CLIENT_SECRET):
        print(f"No encuentro '{config.ARCHIVO_CLIENT_SECRET}' en esta carpeta.")
        print("Descargalo desde Google Cloud Console (instrucciones en "
              "google_calendar_config.py) y vuelve a correr esto.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(config.ARCHIVO_CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(config.ARCHIVO_TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print(f"Listo - se guardo '{config.ARCHIVO_TOKEN}'.")
    print("Ya puedes agendar citas normalmente y se van a crear en ese Google Calendar.")


if __name__ == "__main__":
    main()
