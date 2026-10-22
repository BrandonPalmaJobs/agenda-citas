"""
Carga la DEMO "Clinica Dental Aika Solutions" en la base de datos de un
negocio: nombre, tipo, horario, logo, servicios dentales con precio,
dentistas, pacientes ficticios y citas de los ultimos 60 dias + las
proximas 2 semanas (para que la Agenda y las Estadisticas se vean vivas al
ensenarla a un cliente potencial).

OJO: BORRA todo lo que ese negocio tenga (servicios, personal, clientes y
citas). Antes de borrar guarda un respaldo completo en la carpeta
respaldos/ por si hay que recuperar algo.

Uso (o doble clic en cargar_demo.bat):
    python cargar_demo.py demo
         -> usa las credenciales de Turso de [negocios.demo] en
            .streamlit/secrets.toml (la base que ve la app en ?negocio=demo)
    python cargar_demo.py
         -> sin nombre: usa la base local (turso_config.py o agenda_citas.db)

Las fechas de las citas se calculan a partir de HOY: si la demo se ve
"vieja" en unas semanas, solo vuelve a correr esto.
"""

import base64
import json
import os
import random
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import db

ZONA = ZoneInfo("America/Mexico_City")

NEGOCIO = {
    "nombre": "Clínica Dental Aika Solutions",
    "tipo": "Consultorio dental",
    "hora_apertura": "09:00",
    "hora_cierre": "19:00",
    "dias_laborales": ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab"],
    "intervalo_min": 30,
    "descanso_inicio": "14:00",
    "descanso_fin": "15:00",
}

# (nombre, duracion_min, precio MXN)
SERVICIOS = [
    ("Valoracion y diagnostico", 30, 350),
    ("Limpieza dental", 45, 750),
    ("Resina (curacion)", 60, 950),
    ("Extraccion simple", 45, 1200),
    ("Blanqueamiento", 90, 3800),
    ("Endodoncia", 90, 4500),
    ("Ajuste de brackets", 30, 800),
    ("Valoracion de ortodoncia", 30, 400),
]

# (nombre, especialidad, servicios que atiende)
DENTISTAS = [
    ("Dra. Mariana Lopez", "Odontologia general",
     ["Valoracion y diagnostico", "Limpieza dental", "Resina (curacion)", "Extraccion simple", "Blanqueamiento"]),
    ("Dr. Alejandro Ruiz", "Ortodoncia",
     ["Ajuste de brackets", "Valoracion de ortodoncia", "Valoracion y diagnostico"]),
    ("Dra. Fernanda Castillo", "Endodoncia",
     ["Endodoncia", "Resina (curacion)", "Valoracion y diagnostico", "Limpieza dental"]),
]

# Pacientes ficticios. Telefonos de relleno (55 0000 0xxx) y SIN correo a
# proposito: asi ningun recordatorio de WhatsApp ni invitacion de Google
# Calendar le llega a una persona real.
PACIENTES = [
    "Ana Sofia Hernandez", "Luis Fernando Garcia", "Valeria Martinez", "Jorge Ramirez",
    "Daniela Torres", "Ricardo Flores", "Camila Gomez", "Diego Morales", "Paola Jimenez",
    "Andres Vargas", "Ximena Rojas", "Eduardo Mendoza", "Regina Castro", "Sebastian Ortiz",
    "Natalia Guzman", "Miguel Angel Reyes", "Fernanda Aguilar", "Carlos Medina",
    "Lucia Navarro", "Javier Salazar", "Mariana Rios", "Emilio Herrera", "Renata Cruz",
    "Pablo Dominguez", "Isabella Vega", "Hector Sanchez", "Andrea Molina", "Tomas Delgado",
]

DIAS_ATRAS = 60
DIAS_ADELANTE = 14


def _leer_toml_simple(texto):
    """Lector minimo de TOML para Python < 3.11 (sin tomllib): entiende
    secciones [a.b] y lineas clave = "valor", que es todo lo que usa
    secrets.toml."""
    datos, actual = {}, None
    actual = datos
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        if linea.startswith("[") and linea.endswith("]"):
            actual = datos
            for parte in linea[1:-1].strip().split("."):
                actual = actual.setdefault(parte.strip(), {})
            continue
        if "=" in linea:
            clave, valor = linea.split("=", 1)
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            actual[clave.strip()] = valor
    return datos


def _credenciales_de_secrets(slug):
    ruta = os.path.join(".streamlit", "secrets.toml")
    if not os.path.exists(ruta):
        sys.exit(f"No encuentro {ruta} en esta carpeta.")
    try:
        import tomllib
        with open(ruta, "rb") as f:
            secretos = tomllib.load(f)
    except ImportError:
        with open(ruta, encoding="utf-8") as f:
            secretos = _leer_toml_simple(f.read())
    datos = secretos.get("negocios", {}).get(slug)
    if not datos:
        disponibles = ", ".join(secretos.get("negocios", {}).keys()) or "(ninguno)"
        sys.exit(f"No hay [negocios.{slug}] en {ruta}. Negocios disponibles: {disponibles}")
    url, token = datos.get("turso_database_url"), datos.get("turso_auth_token")
    if not (url and token):
        sys.exit(f"[negocios.{slug}] no tiene turso_database_url / turso_auth_token.")
    return url, token


def _respaldar(etiqueta):
    os.makedirs("respaldos", exist_ok=True)
    respaldo = {}
    with db.get_conn() as conn:
        for tabla in ["negocio", "servicios", "proveedores", "clientes", "citas"]:
            respaldo[tabla] = [dict(r) for r in conn.execute(f"SELECT * FROM {tabla}")]
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = os.path.join("respaldos", f"respaldo_antes_demo_{etiqueta}_{marca}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(respaldo, f, ensure_ascii=False, indent=2)
    return ruta, {t: len(v) for t, v in respaldo.items()}


def _insertar_varios(conn, tabla, columnas, filas, por_lote=40):
    """INSERT de muchas filas en pocas llamadas (en Turso cada llamada es una
    peticion por internet, asi que de una en una seria muy lento)."""
    for i in range(0, len(filas), por_lote):
        lote = filas[i:i + por_lote]
        marcadores = ", ".join("(" + ", ".join("?" * len(columnas)) + ")" for _ in lote)
        params = [v for fila in lote for v in fila]
        conn.execute(f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES {marcadores}", params)


def _min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _generar_citas(ids_servicio, servicios_por_id, ids_dentista, ids_pacientes):
    rnd = random.Random(2026)
    ahora = datetime.now(ZONA)
    hoy = ahora.date()
    ahora_min = ahora.hour * 60 + ahora.minute
    apertura, cierre = _min(NEGOCIO["hora_apertura"]), _min(NEGOCIO["hora_cierre"])
    d_ini, d_fin = _min(NEGOCIO["descanso_inicio"]), _min(NEGOCIO["descanso_fin"])
    citas = []

    for offset in range(-DIAS_ATRAS, DIAS_ADELANTE + 1):
        dia = hoy + timedelta(days=offset)
        if db.DIAS_SEMANA[dia.weekday()] not in NEGOCIO["dias_laborales"]:
            continue
        es_sabado = dia.weekday() == 5
        for nombre, _esp, servicios_dentista in DENTISTAS:
            prov_id = ids_dentista[nombre]
            if offset < 0:
                cuantas = rnd.randint(2, 4) if es_sabado else rnd.randint(3, 6)
            elif offset == 0:
                cuantas = rnd.randint(4, 6)
            else:
                # la agenda futura esta mas llena cerca y mas vacia lejos
                cuantas = max(0, rnd.randint(1, 5) - offset // 4)
            ocupados = []
            intentos = 0
            while len(ocupados) < cuantas and intentos < 60:
                intentos += 1
                serv_nombre = rnd.choice(servicios_dentista)
                serv_id = ids_servicio[serv_nombre]
                dur = servicios_por_id[serv_id]
                ini = apertura + 30 * rnd.randint(0, (cierre - apertura) // 30 - 1)
                fin = ini + dur
                if fin > cierre or (ini < d_fin and fin > d_ini):
                    continue
                if any(ini < f and fin > i for i, f in ocupados):
                    continue
                ocupados.append((ini, fin))

                ya_paso = offset < 0 or (offset == 0 and fin <= ahora_min)
                if ya_paso:
                    estado = rnd.choices(["Completada", "Cancelada", "No asistio"], [78, 12, 10])[0]
                else:
                    estado = "Agendada"
                creada = datetime.combine(dia, datetime.min.time()) - timedelta(days=rnd.randint(1, 10))
                notas = rnd.choice(["", "", "", "Primera visita", "Sensibilidad en muela", "Seguimiento"])
                citas.append((
                    rnd.choice(ids_pacientes), prov_id, serv_id, dia.isoformat(),
                    _hhmm(ini), _hhmm(fin), estado, notas, creada.isoformat(timespec="seconds"),
                    1,  # recordatorio_enviado=1: nunca mandar WhatsApp a pacientes ficticios
                ))
    return citas


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else ""
    if slug:
        db.usar_turso(*_credenciales_de_secrets(slug))
        destino = f"la base del negocio '{slug}' (Turso)"
    else:
        url, token = db.turso_adapter.credenciales_turso()
        destino = "la base de Turso de turso_config.py" if url and token else "el archivo local agenda_citas.db"

    db.init_db()
    actual = db.get_negocio()
    print("=" * 60)
    print(f"  Destino: {destino}")
    print(f"  Negocio actual: {actual['nombre']} ({actual['tipo']})")
    print(f"  Se va a convertir en: {NEGOCIO['nombre']}")
    print("=" * 60)
    print("Esto BORRA sus servicios, personal, clientes y citas (antes se")
    print("guarda un respaldo en la carpeta respaldos/).")
    if input("Escribe SI para continuar: ").strip().upper() != "SI":
        print("Cancelado, no se toco nada.")
        return

    ruta, conteos = _respaldar(slug or "local")
    print(f"Respaldo guardado en {ruta}  {conteos}")

    with db.get_conn() as conn:
        for tabla in ["citas", "clientes", "servicios", "proveedores"]:
            conn.execute(f"DELETE FROM {tabla}")
        try:
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('citas','clientes','servicios','proveedores')")
        except Exception:
            pass

    db.set_negocio(NEGOCIO["nombre"], NEGOCIO["tipo"], NEGOCIO["hora_apertura"], NEGOCIO["hora_cierre"],
                   NEGOCIO["dias_laborales"], NEGOCIO["intervalo_min"],
                   NEGOCIO["descanso_inicio"], NEGOCIO["descanso_fin"])
    if os.path.exists("logo_aika.png"):
        with open("logo_aika.png", "rb") as f:
            db.set_logo(base64.b64encode(f.read()).decode("ascii"))
    else:
        db.set_logo(None)

    for nombre, dur, precio in SERVICIOS:
        db.add_servicio(nombre, dur, precio)
    for nombre, esp, _ in DENTISTAS:
        db.add_proveedor(nombre, esp)

    with db.get_conn() as conn:
        _insertar_varios(conn, "clientes", ["nombre", "telefono", "email", "notas"],
                         [(n, f"550000{i + 1:04d}", "", "") for i, n in enumerate(PACIENTES)])

    servicios = db.list_servicios()
    ids_servicio = {s["nombre"]: s["id"] for s in servicios}
    servicios_por_id = {s["id"]: s["duracion_min"] for s in servicios}
    ids_dentista = {p["nombre"]: p["id"] for p in db.list_proveedores()}
    ids_pacientes = [c["id"] for c in db.list_clientes()]

    citas = _generar_citas(ids_servicio, servicios_por_id, ids_dentista, ids_pacientes)
    with db.get_conn() as conn:
        _insertar_varios(conn, "citas",
                         ["cliente_id", "proveedor_id", "servicio_id", "fecha", "hora_inicio", "hora_fin",
                          "estado", "notas", "creada_el", "recordatorio_enviado"], citas)

    print(f"Listo: {len(SERVICIOS)} servicios, {len(DENTISTAS)} dentistas, "
          f"{len(PACIENTES)} pacientes y {len(citas)} citas cargadas.")


if __name__ == "__main__":
    main()
