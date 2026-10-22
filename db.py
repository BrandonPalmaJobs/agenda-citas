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

import turso_adapter

DB_PATH = "agenda_citas.db"

TIPOS_NEGOCIO = ["Consultorio medico", "Consultorio dental", "Barberia", "Otro"]
DIAS_SEMANA = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
ESTADOS_CITA = ["Agendada", "Completada", "Cancelada", "No asistio"]


def usar_turso(url, token):
    """Le dice a esta sesion (este hilo) que use esta base de datos de Turso
    en particular - lo llama app.py al principio de cada peticion, para
    cuando una sola app atiende varios negocios distintos."""
    turso_adapter.establecer_credenciales(url, token)


@contextmanager
def get_conn():
    """Usa la base de datos permanente en Turso si hay credenciales
    disponibles (turso_config.py o variables de entorno); si no, cae en el
    archivo SQLite local - asi el resto de este archivo no le importa cual
    de las dos esta usando."""
    turso_url, turso_token = turso_adapter.credenciales_turso()
    if turso_url and turso_token:
        conn = turso_adapter.TursoConn(turso_url, turso_token)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_BASES_INICIALIZADAS = set()


def init_db():
    """Crea/actualiza las tablas. Solo hace el trabajo la primera vez por
    base de datos en este proceso (antes corria ~8 consultas en CADA clic)."""
    clave = turso_adapter.credenciales_turso()[0] or DB_PATH
    if clave in _BASES_INICIALIZADAS:
        return
    _init_db()
    _BASES_INICIALIZADAS.add(clave)


def _init_db():
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
        columnas_negocio = {row["name"] for row in conn.execute("PRAGMA table_info(negocio)")}
        if "descanso_inicio" not in columnas_negocio:
            conn.execute("ALTER TABLE negocio ADD COLUMN descanso_inicio TEXT")
        if "descanso_fin" not in columnas_negocio:
            conn.execute("ALTER TABLE negocio ADD COLUMN descanso_fin TEXT")
        if "logo_base64" not in columnas_negocio:
            conn.execute("ALTER TABLE negocio ADD COLUMN logo_base64 TEXT")
        if "color_marca" not in columnas_negocio:
            conn.execute("ALTER TABLE negocio ADD COLUMN color_marca TEXT")
        # Suscripcion (la administra Aika Solutions desde su panel):
        #   plan: 'demo' | 'prueba' | 'activa' | 'suspendida' (vacio = sin vencimiento)
        #   vence_el: 'YYYY-MM-DD' - desde el dia siguiente la agenda se bloquea
        for columna, tipo in [("plan", "TEXT"), ("vence_el", "TEXT"), ("precio_mensual", "REAL"),
                              ("alta_el", "TEXT"), ("notas_admin", "TEXT")]:
            if columna not in columnas_negocio:
                conn.execute(f"ALTER TABLE negocio ADD COLUMN {columna} {tipo}")


# ---------- Memoria (cache) de lo que casi no cambia ----------
# Datos del negocio, servicios y personal se leen en CADA clic pero casi nunca
# cambian: se guardan en memoria unos segundos por base de datos, y cualquier
# cambio hecho desde la app (set_negocio, add_servicio, ...) borra la memoria
# de ESE negocio al instante, asi que nunca se ve informacion vieja tras editar.
import threading
import time

_CACHE_SEGUNDOS = 120
_cache = {}
_cache_lock = threading.Lock()


def _base_actual():
    return turso_adapter.credenciales_turso()[0] or DB_PATH


def _cacheado(nombre, calcular):
    clave = (_base_actual(), nombre)
    ahora = time.monotonic()
    with _cache_lock:
        guardado = _cache.get(clave)
        if guardado and ahora - guardado[0] < _CACHE_SEGUNDOS:
            return _copiar(guardado[1])
    valor = calcular()
    with _cache_lock:
        _cache[clave] = (ahora, valor)
    return _copiar(valor)


def _copiar(valor):
    # copias para que quien use el resultado no modifique lo guardado
    if isinstance(valor, list):
        return [dict(v) for v in valor]
    if isinstance(valor, dict):
        return dict(valor)
    return valor


def limpiar_cache():
    """Olvida lo guardado en memoria del negocio actual."""
    base = _base_actual()
    with _cache_lock:
        for clave in [k for k in _cache if k[0] == base]:
            del _cache[clave]


# ---------- Negocio ----------

def get_negocio():
    def leer():
        with get_conn() as conn:
            return dict(conn.execute("SELECT * FROM negocio WHERE id = 1").fetchone())
    return _cacheado("negocio", leer)


def set_negocio(nombre, tipo, hora_apertura, hora_cierre, dias_laborales, intervalo_min,
                 descanso_inicio="", descanso_fin=""):
    with get_conn() as conn:
        conn.execute(
            """UPDATE negocio SET nombre=?, tipo=?, hora_apertura=?, hora_cierre=?,
               dias_laborales=?, intervalo_min=?, descanso_inicio=?, descanso_fin=? WHERE id=1""",
            (nombre, tipo, hora_apertura, hora_cierre, ",".join(dias_laborales), intervalo_min,
             descanso_inicio or None, descanso_fin or None),
        )
    limpiar_cache()


def set_logo(logo_base64):
    with get_conn() as conn:
        conn.execute("UPDATE negocio SET logo_base64=? WHERE id=1", (logo_base64,))
    limpiar_cache()


def set_suscripcion(plan=None, vence_el=None, precio_mensual=None, notas_admin=None, alta_el=None):
    """Cambia solo los campos que se pasan (los None se dejan como estan)."""
    campos = {"plan": plan, "vence_el": vence_el, "precio_mensual": precio_mensual,
              "notas_admin": notas_admin, "alta_el": alta_el}
    campos = {k: v for k, v in campos.items() if v is not None}
    if not campos:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE negocio SET " + ", ".join(f"{k}=?" for k in campos) + " WHERE id=1",
            list(campos.values()),
        )
    limpiar_cache()


def resumen_admin(desde_iso, hasta_iso):
    """Numeros de un negocio para el panel de administrador de Aika."""
    with get_conn() as conn:
        pacientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        citas_mes = conn.execute(
            "SELECT COUNT(*) FROM citas WHERE fecha BETWEEN ? AND ? AND estado != 'Cancelada'",
            (desde_iso, hasta_iso)).fetchone()[0]
        citas_total = conn.execute("SELECT COUNT(*) FROM citas").fetchone()[0]
        ultima = conn.execute("SELECT MAX(creada_el) FROM citas").fetchone()[0]
    return {"pacientes": pacientes, "citas_mes": citas_mes, "citas_total": citas_total,
            "ultima_cita_creada": ultima}


def set_color(color_hex):
    with get_conn() as conn:
        conn.execute("UPDATE negocio SET color_marca=? WHERE id=1", (color_hex or None,))
    limpiar_cache()


# ---------- Servicios ----------

def list_servicios(solo_activos=False):
    def leer():
        with get_conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM servicios ORDER BY nombre")]
    todos = _cacheado("servicios", leer)
    return [s for s in todos if s["activo"]] if solo_activos else todos


def add_servicio(nombre, duracion_min, precio):
    with get_conn() as conn:
        conn.execute("INSERT INTO servicios (nombre, duracion_min, precio) VALUES (?, ?, ?)",
                     (nombre, duracion_min, precio))
    limpiar_cache()


def update_servicio(servicio_id, nombre, duracion_min, precio, activo):
    with get_conn() as conn:
        conn.execute(
            "UPDATE servicios SET nombre=?, duracion_min=?, precio=?, activo=? WHERE id=?",
            (nombre, duracion_min, precio, int(activo), servicio_id),
        )
    limpiar_cache()


# ---------- Proveedores (personal) ----------

def list_proveedores(solo_activos=False):
    def leer():
        with get_conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM proveedores ORDER BY nombre")]
    todos = _cacheado("proveedores", leer)
    return [p for p in todos if p["activo"]] if solo_activos else todos


def add_proveedor(nombre, especialidad):
    with get_conn() as conn:
        conn.execute("INSERT INTO proveedores (nombre, especialidad) VALUES (?, ?)", (nombre, especialidad))
    limpiar_cache()


def update_proveedor(proveedor_id, nombre, especialidad, activo):
    with get_conn() as conn:
        conn.execute("UPDATE proveedores SET nombre=?, especialidad=?, activo=? WHERE id=?",
                     (nombre, especialidad, int(activo), proveedor_id))
    limpiar_cache()


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


def buscar_cliente_exacto(termino):
    """Para que un paciente/cliente que regresa se encuentre en la pagina
    publica: solo coincidencia exacta de telefono o de correo (sin importar
    mayusculas). A proposito NO busca por nombre ni por pedazos, para que
    nadie pueda sacar la lista de clientes escribiendo una letra."""
    termino = (termino or "").strip()
    if not termino:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM clientes
               WHERE telefono = ? OR (email != '' AND LOWER(email) = LOWER(?))
               ORDER BY nombre""",
            (termino, termino),
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


def _ocupados(proveedor_id, fecha, excluir_cita_id=None):
    """Bloques (inicio, fin) en minutos de las citas no canceladas del
    proveedor ese dia - UNA sola consulta, para luego revisar muchos
    horarios en memoria."""
    with get_conn() as conn:
        q = """SELECT hora_inicio, hora_fin FROM citas
               WHERE proveedor_id=? AND fecha=? AND estado != 'Cancelada'"""
        params = [proveedor_id, fecha]
        if excluir_cita_id:
            q += " AND id != ?"
            params.append(excluir_cita_id)
        existentes = conn.execute(q, params).fetchall()
    return [(_hora_a_minutos(e["hora_inicio"]), _hora_a_minutos(e["hora_fin"])) for e in existentes]


def _choca(ocupados, hora_inicio, hora_fin):
    ini, fin = _hora_a_minutos(hora_inicio), _hora_a_minutos(hora_fin)
    return any(ini < e_fin and fin > e_ini for e_ini, e_fin in ocupados)


def hay_conflicto(proveedor_id, fecha, hora_inicio, hora_fin, excluir_cita_id=None):
    """True si el proveedor ya tiene una cita (no cancelada) ese dia que se
    encima con el horario [hora_inicio, hora_fin) que se quiere agendar."""
    return _choca(_ocupados(proveedor_id, fecha, excluir_cita_id), hora_inicio, hora_fin)


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
    ocupados = _ocupados(proveedor_id, fecha)
    return [h for h in horarios
            if not _choca(ocupados, h, _minutos_a_hora(_hora_a_minutos(h) + duracion_min))]


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
