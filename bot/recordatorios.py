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
