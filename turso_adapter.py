"""
Adaptador delgado para que la base de datos remota en Turso se use exactamente
igual que sqlite3 en el resto del codigo (mismo patron conn.execute(...),
dict(fila), cursor.lastrowid, etc.) - asi db.py no tuvo que reescribirse.

Habla el protocolo HTTP de Turso (Hrana sobre HTTP, endpoint v1/execute)
directo con requests - a proposito NO usa la libreria libsql_client: su
variante "sincrona" tiene un bug intermitente (mezcla mal hilos con su loop
async interno y a veces tira una respuesta a medias). Con requests puro,
sin nada de async, ese problema no existe.

Se activa solo si hay credenciales de Turso disponibles: primero las que se
hayan fijado para el hilo actual con establecer_credenciales() (una app que
atiende varios negocios llama a esto por cada peticion - ver db.usar_turso),
luego las variables de entorno TURSO_DATABASE_URL/TURSO_AUTH_TOKEN, y por
ultimo el archivo local turso_config.py. Si no hay nada de eso, quien use
esto debe seguir con sqlite3 normal - ver la funcion credenciales_turso().
"""

import os
import re
import threading

import requests

_local = threading.local()


def establecer_credenciales(url, token):
    """Fija las credenciales de Turso para el hilo actual. Importante: NO
    usar os.environ para esto en una app que atiende varios negocios en el
    mismo proceso - os.environ es global a todo el proceso, asi que el
    primer negocio que cargara se quedaria "pegado" para todas las
    peticiones siguientes de CUALQUIER negocio. Cada sesion de Streamlit
    corre en su propio hilo, asi que threading.local() si aisla bien."""
    _local.turso_url = url
    _local.turso_token = token


def credenciales_turso():
    """Regresa (url, auth_token) si hay credenciales de Turso disponibles,
    o (None, None) si no - para que el que llama decida usar sqlite3 local."""
    url = getattr(_local, "turso_url", None)
    token = getattr(_local, "turso_token", None)
    if url and token:
        return url, token
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if url and token:
        return url, token
    try:
        import turso_config as config
        return config.TURSO_DATABASE_URL, config.TURSO_AUTH_TOKEN
    except ImportError:
        return None, None


class TursoError(RuntimeError):
    pass


def _codificar_valor(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, bytes):
        import base64
        return {"type": "blob", "value": base64.b64encode(v).decode("ascii")}
    return {"type": "text", "value": str(v)}


def _decodificar_valor(celda):
    tipo = celda.get("type")
    valor = celda.get("value")
    if tipo == "null" or valor is None:
        return None
    if tipo == "integer":
        return int(valor)
    if tipo == "float":
        return float(valor)
    if tipo == "blob":
        import base64
        return base64.b64decode(valor)
    return valor  # "text" y cualquier otro caso: tal cual


class _Row:
    """Imita sqlite3.Row: acceso por indice (fila[0]) y por nombre
    (fila["col"]), y soporta dict(fila) porque expone .keys()."""

    def __init__(self, columns, values):
        self._columns = columns
        self._values = values

    def keys(self):
        return self._columns

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._columns.index(key)]
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


class _ResultProxy:
    def __init__(self, result):
        columns = tuple(c["name"] for c in result.get("cols", []))
        self._rows = [
            _Row(columns, tuple(_decodificar_valor(celda) for celda in fila))
            for fila in result.get("rows", [])
        ]
        lastrowid = result.get("last_insert_rowid")
        self.lastrowid = int(lastrowid) if lastrowid is not None else None

    def __iter__(self):
        return iter(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def _dividir_script(script):
    """Parte un CREATE TABLE ... ; CREATE TABLE ... ; en statements
    individuales - la API de Turso ejecuta un statement por llamada."""
    statements = []
    for parte in re.split(r";\s*(?:\n|$)", script):
        parte = parte.strip()
        if parte:
            statements.append(parte)
    return statements


class TursoConn:
    """Se usa igual que una conexion de sqlite3 dentro de get_conn():
    conn.execute(...), conn.executescript(...), conn.commit(), conn.close()."""

    def __init__(self, url, auth_token):
        self._base_url = url.replace("libsql://", "https://", 1).rstrip("/") + "/"
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {auth_token}"})

    def execute(self, sql, params=None):
        stmt = {
            "sql": sql,
            "args": [_codificar_valor(v) for v in (params or [])],
            "want_rows": True,
        }
        resp = self._session.post(self._base_url + "v1/execute", json={"stmt": stmt}, timeout=20)
        body = resp.json()
        if "result" not in body:
            mensaje = body.get("message") or body.get("error") or body
            raise TursoError(f"Error al ejecutar SQL en Turso: {mensaje}")
        return _ResultProxy(body["result"])

    def executescript(self, script):
        for statement in _dividir_script(script):
            self.execute(statement)

    def commit(self):
        pass  # cada execute() ya aplica de inmediato via HTTP, no hay transaccion pendiente

    def close(self):
        self._session.close()
