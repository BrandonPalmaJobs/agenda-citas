"""Webhook de WhatsApp de Aika Citas (Vercel, WSGI).
GET  /webhook  -> verificacion con Meta (hub.challenge)
POST /webhook  -> mensajes entrantes
GET  /         -> "funcionando" (para revisar que esta vivo)
"""

import json
import os
import traceback
from urllib.parse import parse_qs

import requests

import logica

GRAPH = "https://graph.facebook.com/v21.0"


def mandar(tel, resp):
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
                elif m["type"] == "button":
                    boton = m["button"].get("payload")
                elif m["type"] == "interactive":
                    it = m["interactive"]
                    boton = (it.get("button_reply") or it.get("list_reply") or {}).get("id")
                else:
                    texto = "hola"
                r = logica.reg()
                for resp in logica.responder(r, tel, texto, boton, m.get("id")):
                    mandar(tel, resp)


def app(environ, start_response):
    metodo = environ.get("REQUEST_METHOD", "GET")
    q = parse_qs(environ.get("QUERY_STRING", ""))
    codigo, texto = "200 OK", "Bot de Aika Citas funcionando"
    if metodo == "GET" and "hub.mode" in q:
        if q.get("hub.verify_token", [""])[0] == os.environ.get("WHATSAPP_VERIFY_TOKEN"):
            texto = q.get("hub.challenge", [""])[0]
        else:
            codigo, texto = "403 Forbidden", "token incorrecto"
    elif metodo == "POST":
        try:
            largo = int(environ.get("CONTENT_LENGTH") or 0)
            procesar(json.loads(environ["wsgi.input"].read(largo) or b"{}"))
        except Exception:
            traceback.print_exc()
        texto = "ok"  # siempre 200 para que Meta no reintente sin fin
    start_response(codigo, [("Content-Type", "text/plain; charset=utf-8")])
    return [texto.encode()]
