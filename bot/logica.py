"""Logica del bot: estados de la conversacion, agenda y respuestas."""

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from datos import Base, registro

ZONA = ZoneInfo("America/Mexico_City")
DIAS = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
DIAS_TXT = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_TXT = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]


def ahora():
    return datetime.now(ZONA).replace(tzinfo=None)


def fecha_txt(iso):
    f = datetime.strptime(iso, "%Y-%m-%d").date()
    hoy = ahora().date()
    base = f"{DIAS_TXT[f.weekday()]} {f.day} de {MESES_TXT[f.month]}"
    return "hoy " + base if f == hoy else "mañana " + base if f == hoy + timedelta(days=1) else "el " + base


def _sin_acentos(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def _min(h):
    a, b = h.split(":")
    return int(a) * 60 + int(b)


def _hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


# ------------------------------------------------------------------ registro / estado
REG_ESQUEMA = """CREATE TABLE IF NOT EXISTS conversaciones (
    telefono TEXT PRIMARY KEY, clinica TEXT, estado TEXT, datos TEXT, ultimo_msg TEXT, actualizado TEXT)"""


def reg():
    r = registro()
    r.q(REG_ESQUEMA)
    return r


def clinicas(r):
    filas, _ = r.q("SELECT slug, nombre, turso_database_url, turso_auth_token FROM clinicas WHERE activa = 1")
    return filas


def base_clinica(r, slug):
    c = r.uno("SELECT turso_database_url, turso_auth_token FROM clinicas WHERE slug = ? AND activa = 1", (slug,))
    if not c:
        return None
    b = Base(c["turso_database_url"], c["turso_auth_token"])
    cols, _ = b.q("PRAGMA table_info(citas)")
    if "confirmada" not in {x["name"] for x in cols}:
        b.q("ALTER TABLE citas ADD COLUMN confirmada INTEGER NOT NULL DEFAULT 0")
    return b


def leer_estado(r, tel):
    fila = r.uno("SELECT * FROM conversaciones WHERE telefono = ?", (tel,))
    if not fila:
        return {"clinica": None, "estado": "inicio", "datos": {}, "ultimo_msg": None}
    fila["datos"] = json.loads(fila.get("datos") or "{}")
    return fila


def guardar_estado(r, tel, clinica, estado, datos, ultimo_msg):
    r.q("""INSERT INTO conversaciones (telefono, clinica, estado, datos, ultimo_msg, actualizado)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(telefono) DO UPDATE SET clinica=excluded.clinica, estado=excluded.estado,
             datos=excluded.datos, ultimo_msg=excluded.ultimo_msg, actualizado=excluded.actualizado""",
        (tel, clinica, estado, json.dumps(datos, ensure_ascii=False), ultimo_msg, ahora().isoformat()))


# ------------------------------------------------------------------ agenda de una clinica
def telefono_local(wa_id):
    d = "".join(c for c in wa_id if c.isdigit())
    if d.startswith("521") and len(d) == 13:
        d = d[3:]
    elif d.startswith("52") and len(d) == 12:
        d = d[2:]
    return d[-10:]


def buscar_paciente(b, tel10):
    return b.uno("SELECT * FROM clientes WHERE telefono = ?", (tel10,))


def horarios_libres(b, negocio, servicio, fecha_iso, proveedores):
    """[(hora, proveedor_id)] con el primer especialista libre en cada horario."""
    f = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
    if DIAS[f.weekday()] not in (negocio["dias_laborales"] or "").split(","):
        return []
    ini, fin, paso = _min(negocio["hora_apertura"]), _min(negocio["hora_cierre"]), int(negocio["intervalo_min"])
    dur = int(servicio["duracion_min"])
    d_ini = _min(negocio["descanso_inicio"]) if negocio.get("descanso_inicio") else None
    d_fin = _min(negocio["descanso_fin"]) if negocio.get("descanso_fin") else None
    n = ahora()
    minimo = n.hour * 60 + n.minute + 30 if f == n.date() else -1
    ocupados = {}
    filas, _ = b.q("SELECT proveedor_id, hora_inicio, hora_fin FROM citas WHERE fecha = ? AND estado != 'Cancelada'",
                   (fecha_iso,))
    for x in filas:
        ocupados.setdefault(x["proveedor_id"], []).append((_min(x["hora_inicio"]), _min(x["hora_fin"])))
    libres = []
    m = ini
    while m + dur <= fin:
        if m > minimo and not (d_ini is not None and m < d_fin and m + dur > d_ini):
            for p in proveedores:
                if not any(m < e and m + dur > s for s, e in ocupados.get(p["id"], [])):
                    libres.append((_hhmm(m), p["id"]))
                    break
        m += paso
    return libres


def proximos_dias(b, negocio, servicio, proveedores, cuantos=7):
    dias, f = [], ahora().date()
    for _ in range(30):
        iso = f.isoformat()
        if horarios_libres(b, negocio, servicio, iso, proveedores):
            dias.append(iso)
            if len(dias) == cuantos:
                break
        f += timedelta(days=1)
    return dias


def mis_citas(b, tel10):
    hoy = ahora().date().isoformat()
    filas, _ = b.q("""SELECT citas.id, citas.fecha, citas.hora_inicio, citas.confirmada, servicios.nombre AS servicio,
                             proveedores.nombre AS doctor
                      FROM citas JOIN clientes ON clientes.id = citas.cliente_id
                      JOIN servicios ON servicios.id = citas.servicio_id
                      JOIN proveedores ON proveedores.id = citas.proveedor_id
                      WHERE clientes.telefono = ? AND citas.estado = 'Agendada' AND citas.fecha >= ?
                      ORDER BY citas.fecha, citas.hora_inicio LIMIT 9""", (tel10, hoy))
    return filas


# ------------------------------------------------------------------ respuestas
# Cada respuesta es un dict: {"texto": ...} o {"texto", "botones": [(id, titulo)]}
# o {"texto", "lista": [(id, titulo, descripcion)], "boton_lista": "Ver opciones"}
URL_DEMO = os.environ.get("BOT_URL_PLATAFORMA", "https://clinicadentalaikasolutions.streamlit.app/")


def link_web(r, slug):
    """Pagina donde los pacientes ven todos los horarios: la app propia de la clinica
    (url_app en la lista central) o la plataforma compartida con ?negocio=slug."""
    c = r.uno("SELECT url_app FROM clinicas WHERE slug = ?", (slug,)) or {}
    url = (c.get("url_app") or "").strip()
    return url if url else f"{URL_DEMO.rstrip('/')}/?negocio={slug}"


def menu(nombre_clinica, saludo=True, web=None):
    t = (f"¡Hola! 👋 Soy el asistente de *{nombre_clinica}*.\n¿Qué quieres hacer?" if saludo
         else "¿Te ayudo con algo más?")
    if saludo and web:
        t += f"\n\n🌐 Si prefieres ver todos los horarios y precios: {web}"
    if saludo:
        t += "\n_¿Es otro consultorio? Escribe *cambiar consultorio*._"
    return {"texto": t, "botones": [("m_agendar", "📅 Agendar cita"), ("m_mis", "🗓️ Mis citas"),
                                    ("m_cancelar", "❌ Cancelar cita")]}


def responder(r, tel, texto, boton_id, msg_id):
    """Procesa un mensaje y regresa la lista de respuestas a mandar."""
    est = leer_estado(r, tel)
    if msg_id and est.get("ultimo_msg") == msg_id:
        return []  # Meta reintento el mismo mensaje
    datos = est["datos"]
    tel10 = telefono_local(tel)
    entrada = (boton_id or texto or "").strip()
    norm = _sin_acentos(entrada)

    # Botones del recordatorio: confirmar:slug:id / cancelar:slug:id
    m = re.match(r"^(confirmar|cancelar):([\w-]+):(\d+)$", entrada)
    if m:
        accion, slug, cita_id = m.group(1), m.group(2), int(m.group(3))
        b = base_clinica(r, slug)
        resp = [_accion_recordatorio(b, accion, cita_id, tel10)] if b else [{"texto": "No encontramos esa cita."}]
        guardar_estado(r, tel, slug, "inicio", {}, msg_id)
        return resp

    # Elegir clinica
    todas = clinicas(r)
    slug = est.get("clinica")
    if norm in ("cambiar clinica", "otra clinica", "cambiar consultorio", "otro consultorio"):
        slug = None
    for c in todas:
        if (_sin_acentos(nombre_clinica(r, c)) in norm and len(nombre_clinica(r, c)) > 3) or f"({c['slug']})" in norm:
            slug = c["slug"]
    if not slug and est.get("estado") == "elegir_clinica" and est.get("clinica") is None:
        slug = _clinica_elegida(r, entrada, norm, est["datos"].get("opciones", []), todas)
        if slug:
            guardar_estado(r, tel, slug, "inicio", {}, msg_id)
            est = {"clinica": slug, "estado": "inicio", "datos": {}}
            norm = "hola"  # al elegirla, mostrar su menu
    if not slug and len(todas) == 1:
        slug = todas[0]["slug"]
    if not slug or not any(c["slug"] == slug for c in todas):
        return _preguntar_clinica(r, tel, tel10, norm, todas, msg_id)
    b = base_clinica(r, slug)
    negocio = b.uno("SELECT * FROM negocio WHERE id = 1")
    estado = est["estado"] if est.get("clinica") == slug else "inicio"

    if norm.startswith("hola") or norm in ("hola", "menu", "inicio", "buenas", "buenos dias", "buenas tardes", "buenas noches", "hi") \
            or estado == "inicio" and not boton_id:
        estado, datos = "menu", {}
        guardar_estado(r, tel, slug, estado, datos, msg_id)
        return [menu(negocio["nombre"], web=link_web(r, slug))]

    if norm in ("web", "link", "pagina", "horarios", "ver horarios"):
        guardar_estado(r, tel, slug, "menu", {}, msg_id)
        return [{"texto": f"🌐 Aquí ves todos los horarios, precios y especialistas:\n{link_web(r, slug)}"},
                menu(negocio["nombre"], False)]

    resp, estado, datos = _flujo(b, negocio, tel10, estado, datos, entrada, norm)
    guardar_estado(r, tel, slug, estado, datos, msg_id)
    return resp


def nombre_clinica(r, c):
    """Nombre para mostrar: el de la lista central, o el de su base si ahi solo esta el codigo."""
    n = (c.get("nombre") or "").strip()
    if n and n.lower() != c["slug"].lower():
        return n
    if "_nombre_real" not in c:
        try:
            neg = base_clinica(r, c["slug"]).uno("SELECT nombre FROM negocio WHERE id = 1") or {}
            c["_nombre_real"] = neg.get("nombre") or c["slug"]
        except Exception:
            c["_nombre_real"] = c["slug"]
    return c["_nombre_real"]


def _clinicas_del_paciente(r, tel10, todas):
    """Clinicas donde ese telefono ya es paciente (solo se revisa si son pocas)."""
    if len(todas) > 30:
        return []
    suyas = []
    for c in todas:
        try:
            if buscar_paciente(base_clinica(r, c["slug"]), tel10):
                suyas.append(c["slug"])
        except Exception:
            pass
    return suyas


def _preguntar_clinica(r, tel, tel10, norm, todas, msg_id):
    """El paciente no dijo de que clinica es: le preguntamos."""
    if not todas:
        return [{"texto": "Por ahora no hay consultorios disponibles. Intenta más tarde."}]
    suyas = _clinicas_del_paciente(r, tel10, todas)
    if len(todas) <= 10 or suyas:
        orden = sorted(todas, key=lambda c: (c["slug"] not in suyas, nombre_clinica(r, c)))[:10]
        filas = [(f"c_{c['slug']}", nombre_clinica(r, c)[:24], "Ya eres paciente" if c["slug"] in suyas else "")
                 for c in orden]
        guardar_estado(r, tel, None, "elegir_clinica", {"opciones": [c["slug"] for c in orden]}, msg_id)
        extra = "\nSi no aparece, escribe su nombre." if len(todas) > len(orden) else ""
        return [{"texto": "¡Hola! 👋 ¿Con qué consultorio quieres tu cita?" + extra,
                 "lista": filas, "boton_lista": "Ver consultorios"}]
    guardar_estado(r, tel, None, "elegir_clinica", {"opciones": []}, msg_id)
    return [{"texto": "¡Hola! 👋 ¿Con qué consultorio quieres tu cita? Escríbeme su nombre."}]


def _clinica_elegida(r, entrada, norm, opciones, todas):
    if entrada.startswith("c_") and any(c["slug"] == entrada[2:] for c in todas):
        return entrada[2:]
    if entrada.isdigit() and 1 <= int(entrada) <= len(opciones):
        return opciones[int(entrada) - 1]
    if len(norm) >= 3:
        hallados = [c["slug"] for c in todas if norm in _sin_acentos(nombre_clinica(r, c))]
        if len(hallados) == 1:
            return hallados[0]
    return None


def _accion_recordatorio(b, accion, cita_id, tel10):
    cita = b.uno("""SELECT citas.*, clientes.telefono FROM citas JOIN clientes ON clientes.id = citas.cliente_id
                    WHERE citas.id = ?""", (cita_id,))
    if not cita or cita["telefono"] != tel10:
        return {"texto": "No encontramos esa cita."}
    if cita["estado"] != "Agendada":
        return {"texto": f"Esa cita ya está como *{cita['estado']}*."}
    if accion == "confirmar":
        b.q("UPDATE citas SET confirmada = 1 WHERE id = ?", (cita_id,))
        return {"texto": f"✅ ¡Gracias! Tu cita de {fecha_txt(cita['fecha'])} a las {cita['hora_inicio']} "
                         "quedó *confirmada*. Te esperamos."}
    b.q("UPDATE citas SET estado = 'Cancelada' WHERE id = ?", (cita_id,))
    return {"texto": f"Listo, cancelamos tu cita de {fecha_txt(cita['fecha'])} a las {cita['hora_inicio']}. "
                     "Si quieres agendar otra, escribe *hola*."}


def _elegido(entrada, prefijo, opciones):
    """Acepta el id del boton/lista o el numero escrito por el paciente."""
    if entrada.startswith(prefijo):
        return entrada[len(prefijo):]
    if entrada.isdigit() and 1 <= int(entrada) <= len(opciones):
        return str(opciones[int(entrada) - 1])
    return None


def _filtrar(proveedores, pid):
    return [p for p in proveedores if p["id"] == pid] or proveedores if pid else proveedores


def _dias(b, negocio, s, provs, datos):
    dias = proximos_dias(b, negocio, s, provs)
    if not dias:
        return [{"texto": "No encontramos horarios libres pronto. Escribe *menu* para elegir otra opción."}], "menu", {}
    filas = []
    for iso in dias:
        f = datetime.strptime(iso, "%Y-%m-%d").date()
        filas.append((f"d_{iso}", f"{DIAS_TXT[f.weekday()].capitalize()} {f.day} {MESES[f.month]}", ""))
    return [{"texto": f"*{s['nombre']}* ({s['duracion_min']} min). ¿Qué día te acomoda?", "lista": filas,
             "boton_lista": "Ver días"}], "dia", {**datos, "dias": dias}


def _flujo(b, negocio, tel10, estado, datos, entrada, norm):
    servicios, _ = b.q("SELECT * FROM servicios WHERE activo = 1 ORDER BY nombre")
    proveedores, _ = b.q("SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre")

    if entrada == "m_agendar" or (estado == "menu" and norm in ("1", "agendar")):
        filas = [(f"s_{s['id']}", s["nombre"][:24],
                  f"{s['duracion_min']} min" + (f" · ${s['precio']:,.0f}" if s.get("precio") else ""))
                 for s in servicios[:10]]
        return [{"texto": "¿Qué tratamiento necesitas?", "lista": filas, "boton_lista": "Ver tratamientos"}], \
            "servicio", {"servicios": [s["id"] for s in servicios[:10]]}

    if entrada == "m_mis" or (estado == "menu" and norm in ("2", "mis citas")):
        citas = mis_citas(b, tel10)
        if not citas:
            return [{"texto": "No tienes citas próximas."}, menu(negocio["nombre"], False)], "menu", {}
        t = "Tus próximas citas:\n" + "\n".join(
            f"• {fecha_txt(c['fecha'])} {c['hora_inicio']} — {c['servicio']} con {c['doctor']}"
            + (" ✅" if c.get("confirmada") else "") for c in citas)
        return [{"texto": t}, menu(negocio["nombre"], False)], "menu", {}

    if entrada == "m_cancelar" or (estado == "menu" and norm in ("3", "cancelar")):
        citas = mis_citas(b, tel10)
        if not citas:
            return [{"texto": "No tienes citas próximas para cancelar."}, menu(negocio["nombre"], False)], "menu", {}
        filas = [(f"x_{c['id']}", f"{c['fecha'][8:]}/{c['fecha'][5:7]} {c['hora_inicio']}", c["servicio"][:72])
                 for c in citas]
        return [{"texto": "¿Qué cita quieres cancelar?", "lista": filas, "boton_lista": "Ver mis citas"}], \
            "cancelar", {"citas": [c["id"] for c in citas]}

    if estado == "cancelar":
        cid = _elegido(entrada, "x_", datos.get("citas", []))
        if cid:
            c = b.uno("SELECT fecha, hora_inicio FROM citas WHERE id = ?", (int(cid),))
            return [{"texto": f"¿Seguro que quieres cancelar tu cita de {fecha_txt(c['fecha'])} a las "
                              f"{c['hora_inicio']}?", "botones": [("cx_si", "Sí, cancelar"), ("cx_no", "No")]}], \
                "cancelar_ok", {"cita": int(cid)}
    if estado == "cancelar_ok":
        if entrada == "cx_si" or norm in ("si", "sí"):
            b.q("UPDATE citas SET estado = 'Cancelada' WHERE id = ?", (datos["cita"],))
            return [{"texto": "Listo, tu cita quedó cancelada."}, menu(negocio["nombre"], False)], "menu", {}
        return [menu(negocio["nombre"], False)], "menu", {}

    if estado == "servicio":
        sid = _elegido(entrada, "s_", datos.get("servicios", []))
        if sid:
            s = next(x for x in servicios if x["id"] == int(sid))
            if len(proveedores) > 1:
                filas = [("p_0", "Cualquiera", "El primero con horario libre")] + \
                        [(f"p_{p['id']}", p["nombre"][:24], "") for p in proveedores[:9]]
                return [{"texto": f"*{s['nombre']}*. ¿Con quién te gustaría tu cita?", "lista": filas,
                         "boton_lista": "Ver especialistas"}], "doctor", \
                    {"servicio": s["id"], "docs": [0] + [p["id"] for p in proveedores[:9]]}
            return _dias(b, negocio, s, proveedores, {"servicio": s["id"], "doc": 0})

    if estado == "doctor":
        pid = _elegido(entrada, "p_", datos.get("docs", []))
        if pid is not None:
            s = next(x for x in servicios if x["id"] == datos["servicio"])
            return _dias(b, negocio, s, _filtrar(proveedores, int(pid)), {**datos, "doc": int(pid)})

    if estado == "dia":
        iso = _elegido(entrada, "d_", datos.get("dias", []))
        if iso:
            s = next(x for x in servicios if x["id"] == datos["servicio"])
            libres = horarios_libres(b, negocio, s, iso, _filtrar(proveedores, datos.get("doc", 0)))
            # repartir los 10 horarios a lo largo del dia
            paso = max(1, len(libres) // 10 + (1 if len(libres) % 10 else 0))
            mostrar = libres[::paso][:10]
            filas = [(f"h_{h}|{p}", h, next(x["nombre"] for x in proveedores if x["id"] == p)) for h, p in mostrar]
            return [{"texto": f"Horarios libres {fecha_txt(iso)}:", "lista": filas, "boton_lista": "Ver horarios"}], \
                "hora", {**datos, "fecha": iso, "horas": [f"{h}|{p}" for h, p in mostrar]}

    if estado == "hora":
        hp = _elegido(entrada, "h_", datos.get("horas", []))
        if hp:
            hora, prov = hp.split("|")
            datos = {**datos, "hora": hora, "proveedor": int(prov)}
            if buscar_paciente(b, tel10):
                return _confirmar(b, negocio, servicios, proveedores, datos)
            return [{"texto": "Para terminar, ¿a nombre de quién agendo la cita? (nombre y apellido)"}], "nombre", datos

    if estado == "nombre" and len(entrada) >= 3 and not entrada.startswith(("m_", "s_", "p_", "d_", "h_", "yo_")):
        nombre = " ".join(entrada.split()).title()[:60]
        datos = {**datos, "nombre": nombre}
        # Puede que ya sea paciente registrado con otro telefono: preguntar antes de duplicarlo
        clave = _sin_acentos(nombre)
        filas, _ = b.q("SELECT id, nombre, telefono FROM clientes")
        iguales = [f for f in filas if _sin_acentos(" ".join((f["nombre"] or "").split())) == clave]
        if len(iguales) == 1:
            t = iguales[0]["telefono"] or ""
            fin = f" con teléfono terminado en *{t[-4:]}*" if len(t) >= 4 else ""
            return [{"texto": f"Ya tenemos registrado a *{iguales[0]['nombre']}*{fin}. ¿Eres tú?",
                     "botones": [("yo_si", "Sí, soy yo"), ("yo_no", "No, soy otra persona")]}], \
                "es_tu", {**datos, "posible": iguales[0]["id"]}
        return _confirmar(b, negocio, servicios, proveedores, datos)

    if estado == "es_tu":
        if entrada == "yo_si" or norm in ("si", "sí", "si soy yo"):
            return _confirmar(b, negocio, servicios, proveedores, {**datos, "cliente_id": datos["posible"]})
        if entrada == "yo_no" or norm.startswith("no"):
            return _confirmar(b, negocio, servicios, proveedores, datos)

    if estado == "confirmar":
        if entrada == "ok_si" or norm in ("si", "sí"):
            return _agendar(b, negocio, servicios, proveedores, tel10, datos)
        if entrada == "ok_no" or norm == "no":
            return [{"texto": "Sin problema, no se agendó nada."}, menu(negocio["nombre"], False)], "menu", {}

    # No se entendio: repetir lo que corresponde
    return [{"texto": "No te entendí 🙈. Elige una opción de la lista o escribe *menu* para empezar de nuevo."}], \
        estado, datos


def _confirmar(b, negocio, servicios, proveedores, datos):
    s = next(x for x in servicios if x["id"] == datos["servicio"])
    doc = next(x["nombre"] for x in proveedores if x["id"] == datos["proveedor"])
    t = (f"¿Confirmo tu cita?\n\n🦷 *{s['nombre']}*\n📅 {fecha_txt(datos['fecha']).capitalize()}\n"
         f"🕐 {datos['hora']}\n👩‍⚕️ {doc}\n📍 {negocio['nombre']}")
    return [{"texto": t, "botones": [("ok_si", "✅ Sí, agendar"), ("ok_no", "Cancelar")]}], "confirmar", datos


def _agendar(b, negocio, servicios, proveedores, tel10, datos):
    s = next(x for x in servicios if x["id"] == datos["servicio"])
    libres = dict((h, p) for h, p in horarios_libres(b, negocio, s, datos["fecha"],
                                                     [x for x in proveedores if x["id"] == datos["proveedor"]]))
    if datos["hora"] not in libres:
        return [{"texto": "Uy, ese horario se acaba de ocupar 😕. Escribe *hola* para elegir otro."}], "menu", {}
    paciente = buscar_paciente(b, tel10)
    if paciente:
        cid = paciente["id"]
    elif datos.get("cliente_id"):
        # Paciente que ya existia con otro numero: se queda su expediente y se actualiza su WhatsApp
        cid = datos["cliente_id"]
        viejo = b.uno("SELECT telefono, notas FROM clientes WHERE id = ?", (cid,)) or {}
        nota = ((viejo.get("notas") or "") + f"\nTeléfono anterior: {viejo.get('telefono') or '-'}").strip()
        b.q("UPDATE clientes SET telefono = ?, notas = ? WHERE id = ?", (tel10, nota, cid))
    else:
        _, cid = b.q("INSERT INTO clientes (nombre, telefono, email, notas) VALUES (?, ?, '', 'Registrado por WhatsApp')",
                     (datos.get("nombre") or "Paciente WhatsApp", tel10))
    fin = _hhmm(_min(datos["hora"]) + int(s["duracion_min"]))
    b.q("""INSERT INTO citas (cliente_id, proveedor_id, servicio_id, fecha, hora_inicio, hora_fin, estado, notas,
                              creada_el, recordatorio_enviado, confirmada)
           VALUES (?, ?, ?, ?, ?, ?, 'Agendada', 'Agendada por WhatsApp', ?, 0, 0)""",
        (cid, datos["proveedor"], s["id"], datos["fecha"], datos["hora"], fin, ahora().isoformat(timespec="seconds")))
    return [{"texto": f"🎉 ¡Listo! Tu cita quedó agendada {fecha_txt(datos['fecha'])} a las {datos['hora']}.\n"
                      "Te mandaremos un recordatorio antes. Si necesitas algo, escribe *hola*."}], "inicio", {}
