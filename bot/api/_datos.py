"""Acceso a datos del bot: Turso por HTTP (o SQLite local para pruebas,
con una URL que empiece con 'file:')."""

import os
import sqlite3

import requests


class Base:
    def __init__(self, url, token):
        self.url, self.token = url, token
        if url.startswith("file:"):
            self._sql = sqlite3.connect(url[5:])
            self._sql.row_factory = sqlite3.Row
        else:
            self._sql = None
            self._http = requests.Session()
            self._http.headers["Authorization"] = f"Bearer {token}"
            self._base = url.replace("libsql://", "https://", 1).rstrip("/") + "/v1/execute"

    def q(self, sql, params=()):
        """Ejecuta y regresa (filas como dicts, lastrowid)."""
        if self._sql:
            cur = self._sql.execute(sql, params)
            self._sql.commit()
            return [dict(r) for r in cur.fetchall()], cur.lastrowid
        args = []
        for v in params:
            if v is None:
                args.append({"type": "null"})
            elif isinstance(v, int):
                args.append({"type": "integer", "value": str(v)})
            elif isinstance(v, float):
                args.append({"type": "float", "value": v})
            else:
                args.append({"type": "text", "value": str(v)})
        r = self._http.post(self._base, json={"stmt": {"sql": sql, "args": args, "want_rows": True}},
                            timeout=20).json()
        if "result" not in r:
            raise RuntimeError(f"Turso: {r}")
        res = r["result"]
        cols = [c["name"] for c in res.get("cols", [])]
        filas = []
        for fila in res.get("rows", []):
            d = {}
            for c, celda in zip(cols, fila):
                t, v = celda.get("type"), celda.get("value")
                d[c] = None if t == "null" else int(v) if t == "integer" else float(v) if t == "float" else v
            filas.append(d)
        lid = res.get("last_insert_rowid")
        return filas, int(lid) if lid is not None else None

    def uno(self, sql, params=()):
        filas, _ = self.q(sql, params)
        return filas[0] if filas else None


def registro():
    return Base(os.environ["REGISTRO_TURSO_URL"], os.environ.get("REGISTRO_TURSO_TOKEN", ""))
