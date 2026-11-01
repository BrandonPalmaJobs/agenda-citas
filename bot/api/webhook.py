"""Webhook de WhatsApp (Vercel): GET verifica con Meta, POST recibe mensajes."""

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

import _logica as logica

GRAPH = "https://graph.facebook.com/v21.0"


def mandar(tel, resp):
    """Convierte una respuesta del bot en mensaje de WhatsApp y lo envia."""
    if "botones" in resp:
        cuerpo = {"type": "interactive", "interactive": {
            "type": "button", "body": {"text": resp["texto"]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": t[:20]}}
                                   for i, t in resp["botones"][:3]]}}}
    elif "lista" in resp:
        cuerpo = {"type": "interactive", "interactive": {
            "type": "list", "body": {"text": resp["texto"]},
            "action": {"button": resp.get("boton_lista", "Ver opciones")[:20],
                       "sections": [{"title": "Opciones", "rows": [
                           {"id": i, "title": t[:24], **({"description": d[:72]} if d else {})}
                           for i, t, d in resp["lista"][:10]]}]}}}
    else:
        cuerpo = {"type": "text", "text": {"body": resp["texto"]}}
    r = requests.post(f"{GRAPH}/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages",
                      headers={"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"},
                      json={"messaging_product": "whatsapp", "to": tel, **cuerpo}, timeout=20)
    if r.status_code != 200:
        print("WhatsApp error:", r.status_code, r.text[:300])


def procesar(evento):
    for entrada in evento.get("entry", []):
        for cambio in entrada.get("changes", []):
            for m in cambio.get("value", {}).get("messages", []):
                tel, texto, boton = m.get("from"), "", None
                if m["type"] == "text":
                    texto = m["text"]["body"]
                elif m["type"] == "button":  # boton de plantilla (recordatorio)
                    boton = m["button"].get("payload")
                elif m["type"] == "interactive":
                    it = m["interactive"]
                    boton = (it.get("button_reply") or it.get("list_reply") or {}).get("id")
                else:
                    texto = "hola"
                r = logica.reg()
                for resp in logica.responder(r, tel, texto, boton, m.get("id")):
                    mandar(tel, resp)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        if q.get("hub.verify_token", [""])[0] == os.environ.get("WHATSAPP_VERIFY_TOKEN") and q.get("hub.challenge"):
            self._responder(200, q["hub.challenge"][0])
        else:
            self._responder(200 if not q else 403, "Bot de Aika Citas funcionando" if not q else "token incorrecto")

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", 0))
        try:
            procesar(json.loads(self.rfile.read(largo) or b"{}"))
        except Exception:
            traceback.print_exc()
        self._responder(200, "ok")  # siempre 200 para que Meta no reintente sin fin

    def _responder(self, codigo, texto):
        self.send_response(codigo)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(texto.encode())
