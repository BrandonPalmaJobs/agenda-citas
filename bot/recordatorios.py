"""Recordatorios de WhatsApp desde Vercel (lo llama cron-job.org cada 15 min:
GET /recordatorios?clave=<WHATSAPP_VERIFY_TOKEN>).

Recorre la lista central de clinicas; en cada una manda la plantilla
recordatorio_cita (botones Confirmo / Necesito cancelar) a las citas 'Agendada'
que empiezan en las proximas HORAS horas y aun no tienen recordatorio.
Se salta clinicas suspendidas o con la prueba/suscripcion vencida."""

import os
from datetime import date, timedelta

import requests

import logica

HORAS = int(os.environ.get("RECORDATORIO_HORAS_ANTES", "4"))
GRAPH = "https://graph.facebook.com/v21.0"


def _bloqueada(negocio, hoy):
    plan = (negocio or {}).get("plan") or ""
    if plan == "suspendida":
        return True
    if plan in ("", "demo") or not negocio.get("vence_el"):
        return False
    try:
        return date.fromisoformat(negocio["vence_el"]) < hoy
    except ValueError:
        return False


def _enviar(tel10, valores, ref):
    numero = "52" + tel10 if len(tel10) == 10 else tel10
    comp = [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in valores]}]
    for i, accion in enumerate(("confirmar", "cancelar")):
        comp.append({"type": "button", "sub_type": "quick_reply", "index": str(i),
                     "parameters": [{"type": "payload", "payload": f"{accion}:{ref}"}]})
    r = requests.post(f"{GRAPH}/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages",
                      headers={"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"},
                      json={"messaging_product": "whatsapp", "to": numero, "type": "template",
                            "template": {"name": "recordatorio_cita", "language": {"code": "es_MX"},
                                         "components": comp}}, timeout=20)
    return r.status_code == 200, r.text[:200]


AVISOS = {
    "cancelada": ("cita_cancelada",
                  "Hola {0}, te avisamos que tu cita en {1} del {2} a las {3} fue cancelada. "
                  "Si quieres agendar otra fecha, responde a este mensaje o escribe hola."),
    "reprogramada": ("cita_reprogramada",
                     "Hola {0}, tu cita en {1} cambió de fecha. Nueva cita: {2} a las {3} con {4}. "
                     "Si no te acomoda, responde a este mensaje o escribe hola."),
}


def _post(numero, cuerpo):
    r = requests.post(f"{GRAPH}/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages",
                      headers={"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"},
                      json={"messaging_product": "whatsapp", "to": numero, **cuerpo}, timeout=20)
    return r.status_code == 200, r.text[:200]


def _avisos(b, slug, ahora, log):
    """Manda los avisos que dejo anotados el panel (cita cancelada / cambiada)."""
    import json
    b.q("""CREATE TABLE IF NOT EXISTS avisos_whatsapp (id INTEGER PRIMARY KEY AUTOINCREMENT, cita_id INTEGER,
           tipo TEXT NOT NULL, telefono TEXT NOT NULL, valores TEXT NOT NULL, creado_el TEXT NOT NULL,
           estado TEXT NOT NULL DEFAULT 'pendiente', intentos INTEGER NOT NULL DEFAULT 0, error TEXT)""")
    pendientes, _ = b.q("SELECT * FROM avisos_whatsapp WHERE estado = 'pendiente' ORDER BY id LIMIT 30")
    n = 0
    for a in pendientes:
        b.q("UPDATE avisos_whatsapp SET estado = 'enviando', intentos = intentos + 1 WHERE id = ?", (a["id"],))
        plantilla, texto = AVISOS.get(a["tipo"], (None, None))
        valores = json.loads(a["valores"])
        tel = "".join(d for d in a["telefono"] if d.isdigit())
        numero = "52" + tel if len(tel) == 10 else tel
        ok, det = _post(numero, {"type": "template", "template": {
            "name": plantilla, "language": {"code": "es_MX"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in valores]}]}})
        if not ok:  # plantilla aun no aprobada: texto normal (llega si escribio en las ultimas 24 h)
            ok, _ = _post(numero, {"type": "text", "text": {"body": texto.format(*valores)}})
        if ok:
            b.q("UPDATE avisos_whatsapp SET estado = 'enviado', error = NULL WHERE id = ?", (a["id"],))
            n += 1
        else:
            # se reintenta en cada vuelta durante 24 h (p. ej. mientras Meta aprueba la plantilla)
            viejo = a["creado_el"][:16] < (ahora - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
            b.q("UPDATE avisos_whatsapp SET estado = ?, error = ? WHERE id = ?",
                ("fallido" if viejo else "pendiente", det, a["id"]))
            log.append(f"[{slug}] aviso {a['id']}: NO - {det}")
    if n:
        log.append(f"[{slug}] avisos enviados: {n}")


def correr(horas=HORAS):
    ahora = logica.ahora()
    desde, hasta = ahora.strftime("%Y-%m-%dT%H:%M"), (ahora + timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M")
    r = logica.reg()
    log, enviados = [], 0
    for c in logica.clinicas(r):
        try:
            b = logica.base_clinica(r, c["slug"])
            negocio = b.uno("SELECT * FROM negocio WHERE id = 1")
            if _bloqueada(negocio, ahora.date()):
                log.append(f"[{c['slug']}] bloqueada")
                continue
            _avisos(b, c["slug"], ahora, log)
            citas, _ = b.q("""SELECT citas.id, citas.fecha, citas.hora_inicio, clientes.nombre AS paciente,
                                     clientes.telefono, proveedores.nombre AS doctor
                              FROM citas JOIN clientes ON clientes.id = citas.cliente_id
                              JOIN proveedores ON proveedores.id = citas.proveedor_id
                              WHERE citas.estado = 'Agendada' AND citas.recordatorio_enviado = 0
                                AND (citas.fecha || 'T' || citas.hora_inicio) BETWEEN ? AND ?""", (desde, hasta))
            for x in citas:
                tel = "".join(d for d in (x["telefono"] or "") if d.isdigit())
                if not tel:
                    continue
                # se marca ANTES de mandar: si dos llamadas coinciden, no sale doble
                b.q("UPDATE citas SET recordatorio_enviado = 1 WHERE id = ?", (x["id"],))
                f = date.fromisoformat(x["fecha"])
                cuando = f"{logica.DIAS_TXT[f.weekday()]} {f.day} de {logica.MESES_TXT[f.month]}"
                ok, detalle = _enviar(tel, [(x["paciente"] or "").split(" ")[0] or "paciente", negocio["nombre"],
                                            cuando, x["hora_inicio"], x["doctor"]], f"{c['slug']}:{x['id']}")
                if ok:
                    enviados += 1
                    log.append(f"[{c['slug']}] cita {x['id']}: enviado")
                else:
                    b.q("UPDATE citas SET recordatorio_enviado = 0 WHERE id = ?", (x["id"],))
                    log.append(f"[{c['slug']}] cita {x['id']}: NO - {detalle}")
        except Exception as e:
            log.append(f"[{c['slug']}] error: {e}")
    log.append(f"Recordatorios enviados: {enviados}")
    return "\n".join(log)
