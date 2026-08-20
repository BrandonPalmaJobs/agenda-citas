"""
Capa de datos de la app de citas: crea la base de datos SQLite (un solo
archivo, agenda_citas.db) y expone funciones simples para leer/escribir
negocio, servicios, personal, clientes y citas. Sirve igual para un
consultorio medico, dental o una barberia - todo lo especifico del negocio
(nombre, tipo, servicios, horario) se configura desde la app, no esta
fijo en el codigo.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "agenda_citas.db"

TIPOS_NEGOCIO = ["Consultorio medico", "Consultorio dental", "Barberia", "Otro"]
DIAS_SEMANA = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
ESTADOS_CITA = ["Agendada", "Completada", "Cancelada", "No asistio"]


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS negocio (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                nombre TEXT NOT NULL,
                tipo TEXT NOT NULL,
                hora_apertura TEXT NOT NULL DEFAULT '09:00',
                hora_cierre TEXT NOT NULL DEFAULT '18:00',
                dias_laborales TEXT NOT NULL DEFAULT 'Lun,Mar,Mie,Jue,Vie',
                intervalo_min INTEGER NOT NULL DEFAULT 30
            );

            CREATE TABLE IF NOT EXISTS servicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                duracion_min INTEGER NOT NULL,
                precio REAL,
                activo INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                especialidad TEXT,
                activo INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                email TEXT,
                notas TEXT
            );

            CREATE TABLE IF NOT EXISTS citas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL REFERENCES clientes(id),
                proveedor_id INTEGER NOT NULL REFERENCES proveedores(id),
                servicio_id INTEGER NOT NULL REFERENCES servicios(id),
                fecha TEXT NOT NULL,
                hora_inicio TEXT NOT NULL,
                hora_fin TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Agendada',
                notas TEXT,
                creada_el TEXT NOT NULL
            );
        """)
        if conn.execute("SELECT 1 FROM negocio WHERE id = 1").fetchone() is None:
            conn.execute(
                "INSERT INTO negocio (id, nombre, tipo) VALUES (1, ?, ?)",
                ("Mi negocio", TIPOS_NEGOCIO[0]),
            )
        columnas_citas = {row["name"] for row in conn.execute("PRAGMA table_info(citas)")}
        if "recordatorio_enviado" not in columnas_citas:
            conn.execute(
                "ALTER TABLE citas ADD COLUMN recordatorio_enviado INTEGER NOT NULL DEFAULT 0"
            )
        if "evento_calendar_id" not in columnas_citas:
            conn.execute("ALTER TABLE citas ADD COLUMN evento_calendar_id TEXT")


# ---------- Negocio ----------

def get_negocio():
    with get_conn() as conn:
        return dict(conn.execute("SELECT * FROM negocio WHERE id = 1").fetchone())


def set_negocio(nombre, tipo, hora_apertura, hora_cierre, dias_laborales, intervalo_min):
    with get_conn() as conn:
        conn.execute(
            """UPDATE negocio SET nombre=?, tipo=?, hora_apertura=?, hora_cierre=?,
               dias_laborales=?, intervalo_min=? WHERE id=1""",
            (nombre, tipo, hora_apertura, hora_cierre, ",".join(dias_laborales), intervalo_min),
        )


# ---------- Servicios ----------

def list_servicios(solo_activos=False):
    with get_conn() as conn:
        q = "SELECT * FROM servicios" + (" WHERE activo=1" if solo_activos else "") + " ORDER BY nombre"
        return [dict(r) for r in conn.execute(q)]


def add_servicio(nombre, duracion_min, precio):
    with get_conn() as conn:
        conn.execute("INSERT INTO servicios (nombre, duracion_min, precio) VALUES (?, ?, ?)",
                     (nombre, duracion_min, precio))


def update_servicio(servicio_id, nombre, duracion_min, precio, activo):
    with get_conn() as conn:
        conn.execute(
            "UPDATE servicios SET nombre=?, duracion_min=?, precio=?, activo=? WHERE id=?",
            (nombre, duracion_min, precio, int(activo), servicio_id),
        )


# ---------- Proveedores (personal) ----------

def list_proveedores(solo_activos=False):
    with get_conn() as conn:
        q = "SELECT * FROM proveedores" + (" WHERE activo=1" if solo_activos else "") + " ORDER BY nombre"
        return [dict(r) for r in conn.execute(q)]


def add_proveedor(nombre, especialidad):
    with get_conn() as conn:
        conn.execute("INSERT INTO proveedores (nombre, especialidad) VALUES (?, ?)", (nombre, especialidad))


def update_proveedor(proveedor_id, nombre, especialidad, activo):
    with get_conn() as conn:
        conn.execute("UPDATE proveedores SET nombre=?, especialidad=?, activo=? WHERE id=?",
                     (nombre, especialidad, int(activo), proveedor_id))


# ---------- Clientes ----------

def list_clientes(busqueda=None):
    with get_conn() as conn:
        if busqueda:
            like = f"%{busqueda}%"
            rows = conn.execute(
                "SELECT * FROM clientes WHERE nombre LIKE ? OR telefono LIKE ? ORDER BY nombre",
                (like, like),
            )
        else:
            rows = conn.execute("SELECT * FROM clientes ORDER BY nombre")
        return [dict(r) for r in rows]


def buscar_clientes(termino):
    """Busca clientes existentes por nombre, telefono O correo - para que un
    cliente que regresa pueda encontrarse con un solo dato, sin tener que
    volver a llenar todo el registro."""
    with get_conn() as conn:
        like = f"%{termino}%"
        rows = conn.execute(
            """SELECT * FROM clientes WHERE nombre LIKE ? OR telefono LIKE ? OR email LIKE ?
               ORDER BY nombre""",
            (like, like, like),
        )
        return [dict(r) for r in rows]


def add_cliente(nombre, telefono, email, notas):
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO clientes (nombre, telefono, email, notas) VALUES (?, ?, ?, ?)",
                            (nombre, telefono, email, notas))
        return cur.lastrowid


def update_cliente(cliente_id, nombre, telefono, email, notas):
    with get_conn() as conn:
        conn.execute("UPDATE clientes SET nombre=?, telefono=?, email=?, notas=? WHERE id=?",
                     (nombre, telefono, email, notas, cliente_id))


# ---------- Citas ----------

def _hora_a_minutos(hora_str):
    h, m = hora_str.split(":")
    return int(h) * 60 + int(m)


def _minutos_a_hora(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def hay_conflicto(proveedor_id, fecha, hora_inicio, hora_fin, excluir_cita_id=None):
    """True si el proveedor ya tiene una cita (no cancelada) ese dia que se
    encima con el horario [hora_inicio, hora_fin) que se quiere agendar."""
    with get_conn() as conn:
        q = """SELECT hora_inicio, hora_fin FROM citas
               WHERE proveedor_id=? AND fecha=? AND estado != 'Cancelada'"""
        params = [proveedor_id, fecha]
        if excluir_cita_id:
            q += " AND id != ?"
            params.append(excluir_cita_id)
        existentes = conn.execute(q, params).fetchall()
    nuevo_ini, nuevo_fin = _hora_a_minutos(hora_inicio), _hora_a_minutos(hora_fin)
    for e in existentes:
        e_ini, e_fin = _hora_a_minutos(e["hora_inicio"]), _hora_a_minutos(e["hora_fin"])
        if nuevo_ini < e_fin and nuevo_fin > e_ini:
            return True
    return False


def agendar_cita(cliente_id, proveedor_id, servicio_id, fecha, hora_inicio, duracion_min, notas=""):
    """Regresa el id de la cita recien creada (se usa para despues guardarle
    el id del evento de Google Calendar, si aplica)."""
    hora_fin = _minutos_a_hora(_hora_a_minutos(hora_inicio) + duracion_min)
    if hay_conflicto(proveedor_id, fecha, hora_inicio, hora_fin):
        raise ValueError("El proveedor ya tiene una cita en ese horario.")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO citas (cliente_id, proveedor_id, servicio_id, fecha, hora_inicio,
               hora_fin, notas, creada_el) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (cliente_id, proveedor_id, servicio_id, fecha, hora_inicio, hora_fin, notas,
             datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def guardar_evento_calendar(cita_id, evento_id):
    with get_conn() as conn:
        conn.execute("UPDATE citas SET evento_calendar_id = ? WHERE id = ?", (evento_id, cita_id))


def horarios_disponibles(proveedor_id, fecha, duracion_min, horarios):
    """De una lista de horas candidatas ('HH:MM'), regresa solo las que no
    chocan con una cita existente (no cancelada) del proveedor ese dia.
    Se usa tanto para que el negocio agende como para que el cliente se
    autoagende, asi ambos ven exactamente lo mismo disponible."""
    disponibles = []
    for h in horarios:
        h_fin = _minutos_a_hora(_hora_a_minutos(h) + duracion_min)
        if not hay_conflicto(proveedor_id, fecha, h, h_fin):
            disponibles.append(h)
    return disponibles


def citas_finalizadas(fecha_inicio=None, fecha_fin=None):
    """Citas con un resultado final (Completada/Cancelada/No asistio) en un
    rango de fechas, con el precio del servicio - para las estadisticas de
    ganancias del dueno."""
    with get_conn() as conn:
        q = """SELECT citas.fecha, citas.estado, COALESCE(servicios.precio, 0) AS precio,
                      servicios.nombre AS servicio_nombre
               FROM citas
               JOIN servicios ON servicios.id = citas.servicio_id
               WHERE citas.estado IN ('Completada', 'Cancelada', 'No asistio')"""
        params = []
        if fecha_inicio:
            q += " AND citas.fecha >= ?"
            params.append(fecha_inicio)
        if fecha_fin:
            q += " AND citas.fecha <= ?"
            params.append(fecha_fin)
        q += " ORDER BY citas.fecha"
        return [dict(r) for r in conn.execute(q, params)]


# ---------- Recordatorios (WhatsApp) ----------

def citas_para_recordar(ahora_iso, limite_iso):
    """Citas 'Agendada' que empiezan entre ahora y el limite (normalmente
    ahora + 2 horas) y que todavia no recibieron su recordatorio."""
    with get_conn() as conn:
        q = """SELECT citas.*, clientes.nombre AS cliente_nombre, clientes.telefono AS cliente_telefono,
                      proveedores.nombre AS proveedor_nombre, servicios.nombre AS servicio_nombre
               FROM citas
               JOIN clientes ON clientes.id = citas.cliente_id
               JOIN proveedores ON proveedores.id = citas.proveedor_id
               JOIN servicios ON servicios.id = citas.servicio_id
               WHERE citas.estado = 'Agendada' AND citas.recordatorio_enviado = 0
                 AND (citas.fecha || 'T' || citas.hora_inicio) BETWEEN ? AND ?
               ORDER BY citas.fecha, citas.hora_inicio"""
        return [dict(r) for r in conn.execute(q, (ahora_iso, limite_iso))]


def marcar_recordatorio_enviado(cita_id):
    with get_conn() as conn:
        conn.execute("UPDATE citas SET recordatorio_enviado = 1 WHERE id = ?", (cita_id,))


def find_cliente_por_telefono(telefono):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clientes WHERE telefono = ?", (telefono,)).fetchone()
        return dict(row) if row else None


def editar_cita(cita_id, cliente_id, proveedor_id, servicio_id, fecha, hora_inicio, duracion_min, notas=""):
    hora_fin = _minutos_a_hora(_hora_a_minutos(hora_inicio) + duracion_min)
    if hay_conflicto(proveedor_id, fecha, hora_inicio, hora_fin, excluir_cita_id=cita_id):
        raise ValueError("El proveedor ya tiene una cita en ese horario.")
    with get_conn() as conn:
        conn.execute(
            """UPDATE citas SET cliente_id=?, proveedor_id=?, servicio_id=?, fecha=?, hora_inicio=?,
               hora_fin=?, notas=? WHERE id=?""",
            (cliente_id, proveedor_id, servicio_id, fecha, hora_inicio, hora_fin, notas, cita_id),
        )


def list_citas(fecha=None, proveedor_id=None):
    with get_conn() as conn:
        q = """SELECT citas.*, clientes.nombre AS cliente_nombre, clientes.telefono AS cliente_telefono,
                      proveedores.nombre AS proveedor_nombre, servicios.nombre AS servicio_nombre
               FROM citas
               JOIN clientes ON clientes.id = citas.cliente_id
               JOIN proveedores ON proveedores.id = citas.proveedor_id
               JOIN servicios ON servicios.id = citas.servicio_id
               WHERE 1=1"""
        params = []
        if fecha:
            q += " AND citas.fecha = ?"
            params.append(fecha)
        if proveedor_id:
            q += " AND citas.proveedor_id = ?"
            params.append(proveedor_id)
        q += " ORDER BY citas.fecha, citas.hora_inicio"
        return [dict(r) for r in conn.execute(q, params)]


def cambiar_estado_cita(cita_id, estado):
    with get_conn() as conn:
        conn.execute("UPDATE citas SET estado=? WHERE id=?", (estado, cita_id))
