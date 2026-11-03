"""
Manda los recordatorios de WhatsApp de TODAS las clinicas.

Recorre la lista central de clinicas (registro) y, en cada una, las citas
'Agendada' que empiezan en las proximas HORAS_ANTES horas y aun no tienen
recordatorio; les manda la plantilla con botones Confirmo / Necesito cancelar.
Las clinicas bloqueadas (prueba vencida o suspendidas) se saltan.

Corre solo en GitHub Actions cada 15 min (.github/workflows/recordatorios.yml).
A mano:  python enviar_recordatorios.py            (todas)
         python enviar_recordatorios.py --prueba   (no manda nada, solo muestra)
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import db
import registro
import suscripcion
import whatsapp

HORAS_ANTES = int(os.environ.get("RECORDATORIO_HORAS_ANTES", "4"))
SIMULADO = os.environ.get("RECORDATORIO_SIMULADO") == "1"  # prueba sin plantilla, no marca como enviado
ZONA = ZoneInfo("America/Mexico_City")
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def fecha_legible(fecha_iso, hoy):
    f = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month]}"  # la plantilla ya dice "el {{3}}"


def procesar_clinica(slug, url, token, ahora, prueba):
    db.usar_turso(url, token)
    db.init_db()
    negocio = db.get_negocio()
    if suscripcion.estado(negocio, ahora.date())["bloqueado"]:
        print(f"[{slug}] bloqueada, se salta")
        return 0
    limite = ahora + timedelta(hours=HORAS_ANTES)
    citas = db.citas_para_recordar(ahora.strftime("%Y-%m-%dT%H:%M"), limite.strftime("%Y-%m-%dT%H:%M"))
    enviados = 0
    for c in citas:
        if not c["cliente_telefono"]:
            continue
        cuando = fecha_legible(c["fecha"], ahora.date())
        if prueba:
            print(f"[{slug}] (prueba) {c['cliente_nombre']} {c['cliente_telefono']} {cuando} {c['hora_inicio']}")
            continue
        enviar = whatsapp.enviar_recordatorio_simulado if SIMULADO else whatsapp.enviar_recordatorio
        ok, error = enviar(
            c["cliente_telefono"], c["cliente_nombre"].split()[0], negocio["nombre"], cuando,
            c["hora_inicio"], c["proveedor_nombre"], ref=f"{slug}:{c['id']}")
        if ok and SIMULADO:
            print(f"[{slug}] cita {c['id']}: SIMULACION enviada a {c['cliente_nombre']}")
        elif ok:
            db.marcar_recordatorio_enviado(c["id"])
            enviados += 1
            print(f"[{slug}] cita {c['id']}: enviado a {c['cliente_nombre']}")
        else:
            print(f"[{slug}] cita {c['id']}: NO se pudo - {error}")
    return enviados


def main():
    prueba = "--prueba" in sys.argv
    if not prueba and not whatsapp.credenciales_configuradas():
        print("Sin credenciales de WhatsApp: nada que hacer.")
        return
    if not registro.configurado():
        print("La lista central de clinicas no esta configurada.")
        return
    ahora = datetime.now(ZONA).replace(tzinfo=None)
    total = 0
    for c in registro.listar():
        try:
            total += procesar_clinica(c["slug"], c["turso_database_url"], c["turso_auth_token"], ahora, prueba)
        except Exception as e:
            print(f"[{c['slug']}] error: {e}")
    print(f"Recordatorios enviados: {total}")


if __name__ == "__main__":
    main()
