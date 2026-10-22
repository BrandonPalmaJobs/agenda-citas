"""
Configura la LISTA CENTRAL de clinicas (el "registro") - se corre UNA vez.

Uso: doble clic en configurar_registro.bat (o: python configurar_registro.py)

1. Crea la base del registro en Turso (automatico si llenaste aika_config.py;
   si no, te pide pegar la URL y el token de una base creada a mano).
2. Copia ahi las clinicas que ya tengas en .streamlit/secrets.toml ([negocios.X]).
3. Agrega la seccion [registro] a .streamlit/secrets.toml de esta carpeta y te
   la muestra para pegarla en Secrets de la app de la demo (tu panel de admin).
4. Te dice como dar al "despertador" de GitHub acceso a la lista, para que
   visite solo las apps de las clinicas nuevas.
"""

import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import registro
from nuevo_cliente import URL_APP, crear_base_turso, leer_secrets, preguntar

REPO = "BrandonPalmaJobs/agenda-citas"


def main():
    linea = "=" * 62
    print(f"{linea}\n  LISTA CENTRAL DE CLINICAS - Aika Solutions\n{linea}")

    ruta_secrets, texto_secrets, datos = leer_secrets()
    if registro.configurado():
        url, token = registro.credenciales()
        print(f"Ya esta configurada ({url}). Solo se van a copiar las clinicas que falten.")
    else:
        print("\nCreando la base del registro en Turso...")
        url, token = crear_base_turso("aika-registro")
        if url:
            print(f"  Listo: {url}")
        else:
            print("  (Para que esto sea automatico, llena aika_config.py - ver aika_config.example.py)")
            print("  Crea una base a mano en https://app.turso.tech (nombre sugerido: aika-registro),")
            print("  luego 'Generate Token' (Read & Write) y pega aqui los datos:")
            url = preguntar("  URL de la base (empieza con libsql://)")
            token = preguntar("  Token")

    # Probar la conexion y crear la tabla
    registro.listar(url=url, token=token)

    # Copiar las clinicas que ya existen en Secrets locales
    copiadas = 0
    for slug, d in (datos.get("negocios") or {}).items():
        if not (d.get("turso_database_url") and d.get("turso_auth_token")):
            continue
        if registro.obtener(slug, url=url, token=token):
            continue
        registro.guardar(slug, slug, "", d.get("url_app", ""), d["turso_database_url"],
                         d["turso_auth_token"], url=url, token=token)
        copiadas += 1
        print(f"  Copiada: {slug}")
    print(f"Clinicas copiadas a la lista: {copiadas}")

    bloque = f'\n[registro]\nturso_database_url = "{url}"\nturso_auth_token = "{token}"\n'
    if "[registro]" not in texto_secrets:
        os.makedirs(".streamlit", exist_ok=True)
        with open(ruta_secrets, "a", encoding="utf-8") as f:
            if texto_secrets and not texto_secrets.endswith("\n"):
                f.write("\n")
            f.write(bloque)

    print(f"""
{linea}
  LISTO. Faltan 2 pasos:
{linea}
PASO 1 - Tu panel de administrador
  En la app de la demo ({URL_APP}) -> Manage app -> Settings -> Secrets,
  pega esto AL FINAL y guarda:
{linea}{bloque}{linea}

PASO 2 - El despertador (para que visite solas las apps nuevas)
  En GitHub: repositorio {REPO} -> Settings -> Secrets and variables ->
  Actions -> "New repository secret". Crea estos dos:
     Nombre: REGISTRO_TURSO_URL     Valor: {url}
     Nombre: REGISTRO_TURSO_TOKEN   Valor: (el token de arriba)

Desde ahora, nuevo_cliente.bat anota cada clinica nueva en la lista solo.
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(1)
