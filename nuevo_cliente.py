"""
Da de alta una clinica/negocio NUEVO en la plataforma Aika Solutions.

Uso: doble clic en nuevo_cliente.bat (o: python nuevo_cliente.py)

Te pregunta nombre, giro, color y logo, y entonces:
  1. Crea su base de datos en Turso:
       - automatico, si llenaste aika_config.py con tu token de la API de Turso
       - o te pide pegar la URL y el token de una base que crees a mano
  2. La deja lista: nombre, giro, horario base, color, logo y PRUEBA GRATIS
     de 14 dias (se bloquea sola al vencer; la extiendes desde ?panel=admin).
  3. Genera sus contrasenas (personal y dueno).
  4. Te da los pasos para crear SU PROPIA app de Streamlit (mismo codigo,
     su propia direccion: <nombre>.streamlit.app) con sus Secrets, y el
     bloque para registrarla en tu panel de administrador.
  5. Guarda una ficha con sus links y contrasenas en clientes/<nombre>.txt
     (esa carpeta no se sube a GitHub).
"""

import base64
import os
import re
import secrets as aleatorio
import sys
import unicodedata
from datetime import date, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import requests

import db
import registro
import suscripcion

# App de la demo: ahi vive tu panel de administrador (?panel=admin) y ahi se
# registra cada clinica para que aparezca en tu lista.
URL_APP = "https://clinicadentalaikasolutions.streamlit.app/"
REPO = "BrandonPalmaJobs/agenda-citas"
TIPOS = db.TIPOS_NEGOCIO  # ["Consultorio medico", "Consultorio dental", "Barberia", "Otro"]
PALABRAS = ["sol", "luna", "mar", "rio", "cielo", "nube", "roca", "flor", "pino", "lago",
            "brisa", "faro", "puma", "oso", "lince", "halcon", "coral", "jade", "onix", "ambar"]


# ---------------------------------------------------------------- utilidades
def preguntar(texto, defecto=None, obligatorio=True):
    sufijo = f" [{defecto}]" if defecto not in (None, "") else ""
    while True:
        r = input(f"{texto}{sufijo}: ").strip()
        if not r and defecto is not None:
            return defecto
        if r or not obligatorio:
            return r
        print("  (este dato es obligatorio)")


def a_slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    for palabra in ["clinica-dental-", "consultorio-", "clinica-", "barberia-", "dental-"]:
        if t.startswith(palabra) and len(t) > len(palabra) + 2:
            t = t[len(palabra):]
    return t[:30].strip("-") or "negocio"


def clave_nueva(prefijo):
    return f"{prefijo}-{aleatorio.choice(PALABRAS)}-{aleatorio.randbelow(9000) + 1000}"


def leer_secrets():
    ruta = os.path.join(".streamlit", "secrets.toml")
    if not os.path.exists(ruta):
        return ruta, "", {}
    texto = open(ruta, encoding="utf-8").read()
    try:
        import tomllib
        datos = tomllib.loads(texto)
    except ImportError:
        from cargar_demo import _leer_toml_simple
        datos = _leer_toml_simple(texto)
    return ruta, texto, datos


def config_turso_api():
    try:
        import aika_config as c
        token = getattr(c, "TURSO_API_TOKEN", "")
        org = getattr(c, "TURSO_ORGANIZACION", "")
        grupo = getattr(c, "TURSO_GRUPO", "default") or "default"
        return (token, org, grupo) if token and org else (None, None, None)
    except ImportError:
        return None, None, None


def crear_base_turso(nombre_base):
    """Crea la base y un token de acceso con la API de Turso. Regresa
    (url, token) o (None, None) si no hay configuracion o algo falla."""
    api_token, org, grupo = config_turso_api()
    if not api_token:
        return None, None
    h = {"Authorization": f"Bearer {api_token}"}
    base = f"https://api.turso.tech/v1/organizations/{org}/databases"
    try:
        r = requests.post(base, headers=h, json={"name": nombre_base, "group": grupo}, timeout=60)
        if r.status_code not in (200, 201):
            print(f"  Turso no creo la base ({r.status_code}): {r.text[:300]}")
            return None, None
        hostname = r.json()["database"]["Hostname"]
        r2 = requests.post(f"{base}/{nombre_base}/auth/tokens", headers=h,
                           params={"authorization": "full-access"}, timeout=60)
        if r2.status_code not in (200, 201):
            print(f"  Turso no genero el token ({r2.status_code}): {r2.text[:300]}")
            return None, None
        return f"libsql://{hostname}", r2.json()["jwt"]
    except Exception as e:
        print(f"  No se pudo hablar con la API de Turso: {e}")
        return None, None


# ---------------------------------------------------------------- flujo
def main():
    print("=" * 62)
    print("  ALTA DE CLIENTE NUEVO - Aika Solutions")
    print("=" * 62)

    ruta_secrets, texto_secrets, datos_secrets = leer_secrets()
    existentes = set(datos_secrets.get("negocios", {}).keys())

    nombre = preguntar("Nombre del negocio (como lo veran sus pacientes)")
    print("Giro:")
    for i, t in enumerate(TIPOS, 1):
        print(f"  {i}. {t}")
    tipo = TIPOS[int(preguntar("Elige el numero", "2")) - 1]

    slug = a_slug(nombre)
    while True:
        slug = a_slug(preguntar("Identificador interno corto (sin espacios)", slug))
        if slug in existentes:
            print(f"  Ya existe un negocio '{slug}'. Elige otro.")
            continue
        break

    # Cada clinica tiene SU PROPIA app de Streamlit (mismo codigo de GitHub):
    # https://<subdominio>.streamlit.app
    sugerido = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore")
                      .decode().lower())[:40] or slug.replace("-", "")
    while True:
        subdominio = preguntar("Direccion de su app (solo letras, numeros y guiones) -> ____.streamlit.app",
                               sugerido).lower().replace(".streamlit.app", "").strip("/ ")
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", subdominio):
            break
        print("  Usa solo letras minusculas, numeros y guiones (minimo 3).")
    url_app_clinica = f"https://{subdominio}.streamlit.app/"

    color = preguntar("Color de la marca en formato #RRGGBB (Enter = verde azulado de Aika)", "", False)
    if color and not color.startswith("#"):
        color = "#" + color
    if color and not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        print("  Color no valido, se usa el de Aika.")
        color = ""

    logo_b64 = None
    ruta_logo = preguntar("Ruta del logo PNG/JPG (Enter = sin logo; puedes arrastrar el archivo aqui)",
                          "", False).strip('"').strip("'")
    if ruta_logo:
        if os.path.exists(ruta_logo):
            with open(ruta_logo, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode("ascii")
        else:
            print("  No encontre ese archivo; se da de alta sin logo (lo pueden subir desde su panel).")

    dias = int(preguntar("Dias de prueba gratis", str(suscripcion.DIAS_PRUEBA)))
    precio = float(preguntar("Precio mensual que le vas a cobrar (MXN)", "500"))

    # ---- Base de datos
    print("\nCreando su base de datos en Turso...")
    url, token = crear_base_turso(f"aika-{slug}")
    if url:
        print(f"  Listo: {url}")
    else:
        print("  (Para que esto sea automatico, llena aika_config.py - ver aika_config.example.py)")
        print("  Crea la base a mano en https://app.turso.tech -> Create Database, y luego")
        print("  'Generate Token' (Read & Write). Pega aqui los datos:")
        url = preguntar("  URL de la base (empieza con libsql://)")
        token = preguntar("  Token")

    print("Preparando el negocio...")
    db.usar_turso(url, token)
    db.init_db()
    if db.list_servicios() or db.list_proveedores():
        if preguntar("  OJO: esa base ya tiene datos. Escribe SI para usarla de todos modos", "") .upper() != "SI":
            print("Cancelado.")
            return
    db.set_negocio(nombre, tipo, "09:00", "18:00", ["Lun", "Mar", "Mie", "Jue", "Vie"], 30)
    if logo_b64:
        db.set_logo(logo_b64)
    if color:
        db.set_color(color)
    hoy = date.today()
    vence = hoy + timedelta(days=dias)
    db.set_suscripcion(plan="prueba", vence_el=vence.isoformat(), precio_mensual=precio,
                       alta_el=hoy.isoformat())

    clave_staff = clave_nueva("staff")
    clave_dueno = clave_nueva("dueno")
    contacto = datos_secrets.get("contacto_aika", "")

    # BLOQUE 1 - Secrets de la app PROPIA de la clinica (solo sus datos)
    bloque_app = (
        f'turso_database_url = "{url}"\n'
        f'turso_auth_token = "{token}"\n'
        f'staff_password = "{clave_staff}"\n'
        f'dueno_password = "{clave_dueno}"\n'
        + (f'contacto_aika = "{contacto}"\n' if contacto else "")
    )
    # BLOQUE 2 - registro en la app de la demo, para tu panel de administrador
    # (sin contrasenas: desde la demo nadie puede entrar al panel de la clinica)
    bloque_registro = (
        f"\n[negocios.{slug}]\n"
        f'turso_database_url = "{url}"\n'
        f'turso_auth_token = "{token}"\n'
        f'url_app = "{url_app_clinica}"\n'
    )

    # Lista central: si esta configurada, la clinica se anota sola (sin pegar
    # nada en los Secrets de la demo ni tocar despertar_urls.txt)
    en_lista_central = False
    if registro.configurado():
        try:
            registro.guardar(slug, nombre, tipo, url_app_clinica, url, token)
            en_lista_central = True
        except Exception as e:
            print(f"  No se pudo anotar en la lista central ({e}); usa los pasos manuales de abajo.")
    if not en_lista_central:
        os.makedirs(".streamlit", exist_ok=True)
        with open(ruta_secrets, "a", encoding="utf-8") as f:
            if texto_secrets and not texto_secrets.endswith("\n"):
                f.write("\n")
            f.write(bloque_registro)

    ficha = (
        f"{nombre} ({tipo})\n"
        f"Alta: {hoy.strftime('%d/%m/%Y')} · Prueba gratis hasta: {vence.strftime('%d/%m/%Y')} · "
        f"Precio: ${precio:,.0f}/mes\n\n"
        f"Link para sus pacientes:  {url_app_clinica}\n"
        f"Panel (personal y dueño): {url_app_clinica}?panel=staff\n"
        f"Contraseña personal:      {clave_staff}\n"
        f"Contraseña dueño:         {clave_dueno}\n"
    )
    os.makedirs("clientes", exist_ok=True)
    ruta_ficha = os.path.join("clientes", f"{slug}.txt")
    with open(ruta_ficha, "w", encoding="utf-8") as f:
        f.write(ficha + "\n--- Secrets de su app ---\n" + bloque_app)

    linea = "=" * 62
    faltan = "1 paso" if en_lista_central else "3 pasos"
    pasos_manuales = ("YA QUEDO EN TU LISTA CENTRAL: aparece sola en tu panel de administrador\n"
                      "y el despertador la visitara solo. No hay que pegar nada mas.\n"
                      if en_lista_central else f"""PASO 2 - Registrarla en TU panel de administrador
  En la app de la demo ({URL_APP}) -> Manage app -> Settings -> Secrets,
  pega esto AL FINAL y guarda:
{linea}{bloque_registro}{linea}
  (Esto ya quedo agregado tambien en .streamlit/secrets.toml de esta carpeta.)

PASO 3 - Que nunca se duerma
  En GitHub abre el archivo despertar_urls.txt del repositorio, dale al lapiz
  (editar), agrega esta linea y guarda ("Commit changes"):
      {url_app_clinica}
""")
    print(f"\n{linea}\n  SU BASE YA QUEDO LISTA. Falta(n) {faltan} (unos 5 minutos):\n{linea}")
    print(f"""
PASO 1 - Crear SU app en Streamlit
  a) Entra a https://share.streamlit.io y dale "Create app"
     -> "Deploy a public app from GitHub".
  b) Repository: {REPO}   Branch: main   Main file path: app.py
  c) App URL: {subdominio}
  d) "Advanced settings": Python 3.12, y en "Secrets" pega ESTO:
{linea}
{bloque_app}{linea}
  e) Dale "Deploy" y espera 1-2 minutos.

{pasos_manuales}""")
    print(linea)
    print(ficha)
    print(f"(Ficha y Secrets guardados en {ruta_ficha} - esa carpeta no se sube a GitHub)")
    print("Al vencer la prueba, la agenda se bloquea sola. Para extenderla o")
    print(f"marcar que ya pago: {URL_APP}?panel=admin")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(1)
