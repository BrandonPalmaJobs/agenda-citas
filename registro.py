"""
Lista central de clinicas de Aika Solutions ("registro").

Una base de datos pequena y aparte (en Turso) con UNA fila por clinica:
como se llama, su direccion (app propia), y las credenciales de SU base de
datos. La usan:
  - el panel de administrador (?panel=admin) para listar todas las clinicas
  - nuevo_cliente.py, que anota cada clinica nueva aqui automaticamente
  - el despertador (GitHub Actions), para saber que apps visitar
  - el bot de WhatsApp (a futuro), para saber de que clinica es cada mensaje

Las fechas de prueba/pago NO viven aqui: siguen en la base de cada clinica
(su app las necesita para bloquearse sola).

Donde estan las credenciales del registro (la primera que exista):
  1. Secrets de Streamlit:   [registro] turso_database_url / turso_auth_token
  2. Variables de entorno:   REGISTRO_TURSO_URL / REGISTRO_TURSO_TOKEN
  3. .streamlit/secrets.toml de esta carpeta (seccion [registro])
Si no hay ninguna, el registro "no esta configurado" y todo funciona como
antes (con los [negocios.X] de Secrets).

Para pruebas locales, turso_database_url = "local" usa un archivo SQLite
(registro_local.db) en vez de Turso.
"""

import os
import sqlite3
from datetime import date

import turso_adapter

ARCHIVO_LOCAL = "registro_local.db"
_ESQUEMA = """
CREATE TABLE IF NOT EXISTS clinicas (
    slug TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    tipo TEXT,
    url_app TEXT,
    turso_database_url TEXT NOT NULL,
    turso_auth_token TEXT NOT NULL,
    alta_el TEXT,
    activa INTEGER NOT NULL DEFAULT 1,
    notas TEXT
)
"""


def _leer_secrets_local():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
    if not os.path.exists(ruta):
        return {}
    texto = open(ruta, encoding="utf-8").read()
    try:
        import tomllib
        return tomllib.loads(texto)
    except ImportError:
        from cargar_demo import _leer_toml_simple
        return _leer_toml_simple(texto)


def credenciales():
    """(url, token) del registro, o (None, None) si no esta configurado."""
    try:
        import streamlit as st
        r = st.secrets.get("registro")
        if r and r.get("turso_database_url") and r.get("turso_auth_token"):
            return r["turso_database_url"], r["turso_auth_token"]
    except Exception:
        pass
    url, token = os.environ.get("REGISTRO_TURSO_URL"), os.environ.get("REGISTRO_TURSO_TOKEN")
    if url and token:
        return url, token
    r = _leer_secrets_local().get("registro") or {}
    if r.get("turso_database_url") and r.get("turso_auth_token"):
        return r["turso_database_url"], r["turso_auth_token"]
    return None, None


def configurado():
    return all(credenciales())


class _ConexionLocal:
    def __init__(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ARCHIVO_LOCAL)
        self._c = sqlite3.connect(ruta)
        self._c.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        cur = self._c.execute(sql, params)
        self._c.commit()
        return cur

    def close(self):
        self._c.close()


def _conectar(url=None, token=None):
    if url is None:
        url, token = credenciales()
    if not url:
        raise RuntimeError("El registro de clinicas no esta configurado.")
    if url == "local":
        conn = _ConexionLocal()
    else:
        conn = turso_adapter.TursoConn(url, token)
    conn.execute(_ESQUEMA)
    return conn


def listar(incluir_inactivas=False, url=None, token=None):
    conn = _conectar(url, token)
    try:
        q = "SELECT * FROM clinicas" + ("" if incluir_inactivas else " WHERE activa = 1") + " ORDER BY nombre"
        return [dict(r) for r in conn.execute(q).fetchall()]
    finally:
        conn.close()


def obtener(slug, url=None, token=None):
    conn = _conectar(url, token)
    try:
        fila = conn.execute("SELECT * FROM clinicas WHERE slug = ?", (slug,)).fetchone()
        return dict(fila) if fila else None
    finally:
        conn.close()


def guardar(slug, nombre, tipo, url_app, turso_database_url, turso_auth_token, notas="",
            url=None, token=None):
    """Agrega la clinica, o la actualiza si ese slug ya existe (y la reactiva)."""
    conn = _conectar(url, token)
    try:
        conn.execute(
            """INSERT INTO clinicas (slug, nombre, tipo, url_app, turso_database_url, turso_auth_token,
                                     alta_el, activa, notas)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
               ON CONFLICT(slug) DO UPDATE SET nombre=excluded.nombre, tipo=excluded.tipo,
                   url_app=excluded.url_app, turso_database_url=excluded.turso_database_url,
                   turso_auth_token=excluded.turso_auth_token, activa=1, notas=excluded.notas""",
            (slug, nombre, tipo, url_app or "", turso_database_url, turso_auth_token,
             date.today().isoformat(), notas or ""),
        )
    finally:
        conn.close()


def quitar(slug, url=None, token=None):
    """La quita de la lista (no borra NADA de su base de datos ni su app)."""
    conn = _conectar(url, token)
    try:
        conn.execute("UPDATE clinicas SET activa = 0 WHERE slug = ?", (slug,))
    finally:
        conn.close()
