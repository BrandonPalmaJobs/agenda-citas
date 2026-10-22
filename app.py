"""
Agenda de citas - app local con interfaz web (Streamlit), pensada para
consultorio medico, dental o barberia. Todo lo especifico del negocio
(nombre, tipo, servicios que ofrece, horario, personal) se configura desde
la propia app - el codigo no asume un giro de negocio en particular.

Uso:
    streamlit run app.py
    (o doble clic en correr_app.bat, que instala lo necesario y abre esto)

Guarda todo en un archivo SQLite local (agenda_citas.db) en esta misma
carpeta - no depende de internet ni de ningun servicio externo.

Esta app tiene dos vistas:
  - Publica (URL normal, sin nada al final): pagina para que el cliente
    se autoagende, mostrando solo horarios realmente disponibles.
  - Panel del negocio (agregar "?panel=staff" al final de la URL): todo
    lo administrativo, protegido con una clave (ver .streamlit/secrets.toml).
"""

import base64
import io
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

import importlib
import os

import turso_adapter
import db
import google_calendar
import suscripcion
import ui
import admin


def _recargar_si_cambio(*modulos):
    """Streamlit Cloud vuelve a correr app.py cuando se actualiza el codigo,
    pero a veces sigue usando la version VIEJA de los otros archivos (db.py,
    ui.py...) que ya tenia cargados - y la app truena porque app.py pide algo
    que el archivo viejo no tiene. Aqui se recarga cada archivo propio si
    cambio desde la ultima vez."""
    for modulo in modulos:
        try:
            fecha = os.path.getmtime(modulo.__file__)
        except OSError:
            continue
        if getattr(modulo, "_fecha_cargado", None) != fecha:
            if hasattr(modulo, "_fecha_cargado"):
                importlib.reload(modulo)
            modulo._fecha_cargado = fecha


# turso_adapter primero: db y los demas dependen de el
for _m in (turso_adapter, db, google_calendar, suscripcion, ui, admin):
    if not hasattr(_m, "_fecha_cargado"):
        # primera vez en este proceso tras una actualizacion: recargar por si
        # el proceso traia una version vieja en memoria
        importlib.reload(_m)
        _m._fecha_cargado = os.path.getmtime(_m.__file__)
_recargar_si_cambio(turso_adapter, db, google_calendar, suscripcion, ui, admin)

# Paleta de las graficas de Estadisticas: azul fuerte / gris claro / blanco.
# Cancelada y No asistio quedan en tonos muy claros a proposito (pedido del
# negocio) - por eso todas las marcas llevan un contorno gris (CONTORNO) para
# que sigan siendo visibles sobre el fondo blanco.
AZUL_FUERTE = ui.TEAL
GRIS_CLARO = "#CBD5E1"
BLANCO = "#ffffff"
CONTORNO = "#ffffff"
COLOR_ESTADO = ui.COLOR_ESTADO

DIAS_NOMBRE = {
    "Lun": "lunes", "Mar": "martes", "Mie": "miércoles", "Jue": "jueves",
    "Vie": "viernes", "Sab": "sábado", "Dom": "domingo",
}

# Una cuenta gratuita de Streamlit Cloud solo permite una app - para atender
# varios negocios con esa misma app, cada uno se identifica con "?negocio=X"
# en la URL, y sus credenciales viven en su propia tabla [negocios.X] dentro
# de Secrets. Sin ese parametro, se usan los Secrets de nivel superior (caso
# de una sola app para un solo negocio).
NEGOCIO_SLUG = st.query_params.get("negocio", "")


def _secreto(nombre):
    try:
        if NEGOCIO_SLUG:
            return st.secrets.get("negocios", {}).get(NEGOCIO_SLUG, {}).get(nombre)
        return st.secrets.get(nombre)
    except Exception:
        return None


# En Streamlit Cloud las credenciales de Turso viven en Secrets (nunca se
# suben a git); localmente vienen de turso_config.py. Se fijan por hilo (no
# con os.environ, que es global al proceso) porque una sola app puede estar
# atendiendo peticiones de varios negocios distintos a la vez.
turso_url = _secreto("turso_database_url")
turso_token = _secreto("turso_auth_token")

# Siempre se fija (incluso a None, None) aunque no haya credenciales para
# esta peticion: Streamlit puede reusar el mismo hilo del servidor para
# atender a otro negocio despues, y si no se limpia aqui, ese hilo se
# quedaria con las credenciales del negocio anterior "pegadas" - exactamente
# el mismo problema de fuga entre negocios que threading.local() buscaba
# evitar en primer lugar.
db.usar_turso(turso_url, turso_token)

_negocio_no_configurado = bool(NEGOCIO_SLUG and not (turso_url and turso_token))

# Cuando la app se vende a varios negocios (hay [negocios.X] en Secrets), la
# URL raiz sin "?negocio=" no pertenece a nadie: en vez de mostrar un negocio
# vacio ("Mi negocio") con una base temporal, se muestra una portada de la
# plataforma. Localmente (con turso_config.py o sin [negocios]) sigue igual.
def _hay_varios_negocios():
    try:
        return bool(st.secrets.get("negocios"))
    except Exception:
        return False


_es_raiz_de_plataforma = bool(
    not NEGOCIO_SLUG and _hay_varios_negocios() and not all(db.turso_adapter.credenciales_turso())
)

# Panel de administrador de Aika: URL raiz + ?panel=admin
# (solo en la app de la plataforma - la que tiene [negocios.X] en Secrets; en la
# app propia de una clinica, ?panel=admin no existe)
ES_ADMIN = not NEGOCIO_SLUG and st.query_params.get("panel") == "admin" and _hay_varios_negocios()

if _negocio_no_configurado or _es_raiz_de_plataforma or ES_ADMIN:
    negocio = None
else:
    db.init_db()
    negocio = db.get_negocio()

# Palabras e iconos segun el giro: un consultorio atiende "pacientes", una
# barberia "clientes" - asi la misma app se siente hecha para cada negocio
# al venderla a varios (todo lo demas sigue igual para todos).
VOCABULARIO = {
    "Consultorio dental": {
        "cliente": "paciente", "clientes": "pacientes", "Cliente": "Paciente", "Clientes": "Pacientes",
        "icono": "🦷", "icono_personal": "🧑‍⚕️", "con_quien": "¿Con qué doctor(a)?",
        "personal_desc": "Dentistas, higienistas y asistentes - quién atiende las citas.",
        "ejemplos_servicios": "Ej. 'Valoración' (30 min), 'Limpieza dental' (45 min), 'Resina' (60 min).",
        "subtitulo": "Odontología integral · Agenda en línea", "titulo_reserva": "Agenda tu cita dental",
        "paso_servicio": "Selecciona el tratamiento", "paso_especialista": "Elige a tu odontólogo(a)",
        "especialistas": "Odontólogos activos",
    },
    "Consultorio medico": {
        "cliente": "paciente", "clientes": "pacientes", "Cliente": "Paciente", "Clientes": "Pacientes",
        "icono": "🩺", "icono_personal": "🧑‍⚕️", "con_quien": "¿Con qué doctor(a)?",
        "personal_desc": "Doctores, enfermeras y asistentes - quién atiende las citas.",
        "ejemplos_servicios": "Ej. 'Consulta general' (30 min), 'Revisión de estudios' (20 min).",
        "subtitulo": "Consultorio médico · Agenda en línea", "titulo_reserva": "Agenda tu consulta",
        "paso_servicio": "Selecciona el tipo de consulta", "paso_especialista": "Elige a tu doctor(a)",
        "especialistas": "Doctores activos",
    },
    "Barberia": {
        "cliente": "cliente", "clientes": "clientes", "Cliente": "Cliente", "Clientes": "Clientes",
        "icono": "💈", "icono_personal": "💈", "con_quien": "¿Con quién?",
        "personal_desc": "Barberos y estilistas - quién atiende las citas.",
        "ejemplos_servicios": "Ej. 'Corte de cabello' (30 min), 'Corte y barba' (60 min).",
        "subtitulo": "Barbería · Agenda en línea", "titulo_reserva": "Agenda tu cita",
        "paso_servicio": "Selecciona el servicio", "paso_especialista": "Elige a tu barbero",
        "especialistas": "Barberos activos",
    },
}
VOCABULARIO_GENERICO = {
    "cliente": "cliente", "clientes": "clientes", "Cliente": "Cliente", "Clientes": "Clientes",
    "icono": "📅", "icono_personal": "👤", "con_quien": "¿Con quién?",
    "personal_desc": "Las personas que atienden las citas.",
    "ejemplos_servicios": "Ej. 'Consulta' (30 min), 'Sesión' (60 min).",
    "subtitulo": "Agenda en línea", "titulo_reserva": "Agenda tu cita",
    "paso_servicio": "Selecciona el servicio", "paso_especialista": "¿Con quién?",
    "especialistas": "Personal activo",
}
V = VOCABULARIO.get((negocio or {}).get("tipo"), VOCABULARIO_GENERICO)

# El icono de la pestaña del navegador usa el logo del negocio (si ya subio
# uno) en vez del emoji generico - por eso set_page_config, que debe ser el
# primer comando de Streamlit, se llama hasta aqui, una vez que ya sabemos
# si hay negocio y logo.
_icono_pagina = V["icono"]
if negocio and negocio.get("logo_base64"):
    try:
        _icono_pagina = io.BytesIO(base64.b64decode(negocio["logo_base64"]))
    except Exception:
        _icono_pagina = V["icono"]

st.set_page_config(page_title=negocio["nombre"] if negocio else "Aika Solutions",
                   page_icon=_icono_pagina, layout="wide")
# Color de marca de la clinica (o el de Aika si no ha elegido uno)
COLOR_MARCA = ui.paleta((negocio or {}).get("color_marca"))["p"]
ui.inyectar_estilos(COLOR_MARCA)
AZUL_FUERTE = COLOR_MARCA
COLOR_ESTADO = {**ui.COLOR_ESTADO, "Completada": COLOR_MARCA}

# La barra oscura de "DEMO · Powered by Aika Solutions" solo sale en la demo
# que se ensena a clientes potenciales; los negocios que pagan no la ven.
ES_DEMO = NEGOCIO_SLUG == "demo"

if _negocio_no_configurado:
    st.error(f"No encontramos configuración para el negocio '{NEGOCIO_SLUG}'. Revisa el link.")
    st.stop()

if ES_ADMIN:
    try:
        _host = st.context.headers.get("host") or "localhost:8501"
    except Exception:
        _host = "localhost:8501"
    _esquema = "http" if _host.startswith(("localhost", "127.0.0.1")) else "https"
    admin.pagina(datetime.now(ZoneInfo("America/Mexico_City")).date(), f"{_esquema}://{_host}/")
    st.stop()

if _es_raiz_de_plataforma:
    ui.portada_plataforma()
    st.stop()


ZONA_HORARIA_NEGOCIO = ZoneInfo("America/Mexico_City")

# Suscripcion del negocio: si la prueba o el pago vencio (o esta suspendido),
# se bloquea la agenda - ver suscripcion.py
SUSCRIPCION = suscripcion.estado(negocio, datetime.now(ZONA_HORARIA_NEGOCIO).date())


def _contacto_aika():
    try:
        return st.secrets.get("contacto_aika") or ""
    except Exception:
        return ""


def ahora_negocio():
    """Hora actual en la zona horaria del negocio (Mexico), no la del
    servidor donde corra la app - Streamlit Cloud corre en otro huso
    horario y usar datetime.now() a secas filtraba horarios mal."""
    return datetime.now(ZONA_HORARIA_NEGOCIO)


def hoy_negocio():
    return ahora_negocio().date()


def generar_horarios(apertura, cierre, intervalo_min):
    slots = []
    actual = datetime.strptime(apertura, "%H:%M")
    fin = datetime.strptime(cierre, "%H:%M")
    while actual < fin:
        slots.append(actual.strftime("%H:%M"))
        actual += timedelta(minutes=intervalo_min)
    return slots


def quitar_horas_pasadas(horarios, fecha_sel):
    """Si la fecha elegida es hoy, quita los horarios que ya pasaron."""
    if fecha_sel != hoy_negocio():
        return horarios
    ahora = ahora_negocio().strftime("%H:%M")
    return [h for h in horarios if h > ahora]


def quitar_horas_descanso(horarios, duracion_min, descanso_inicio, descanso_fin):
    """Quita los horarios cuya cita se encimaria con el bloque de descanso
    (hora de comida, etc.) del negocio - si no hay descanso configurado no
    quita nada."""
    if not descanso_inicio or not descanso_fin:
        return horarios
    d_ini = datetime.strptime(descanso_inicio, "%H:%M")
    d_fin = datetime.strptime(descanso_fin, "%H:%M")
    resultado = []
    for h in horarios:
        h_ini = datetime.strptime(h, "%H:%M")
        h_fin = h_ini + timedelta(minutes=duracion_min)
        if h_ini < d_fin and h_fin > d_ini:
            continue
        resultado.append(h)
    return resultado


def hora_valida(s):
    if not re.match(r"^\d{2}:\d{2}$", s or ""):
        return False
    h, m = s.split(":")
    return 0 <= int(h) <= 23 and 0 <= int(m) <= 59


def telefono_valido(s):
    """Numero de celular mexicano: exactamente 10 digitos, sin espacios ni guiones."""
    return bool(re.fullmatch(r"\d{10}", (s or "").strip()))


def enmascarar_nombre(nombre):
    """'Brandon Palma' -> 'B*****n P***a': solo la inicial y la ultima letra de
    cada palabra (nombre y apellido) quedan visibles, para no exponer el
    nombre completo de un cliente ya registrado a quien apenas lo busca.
    Los asteriscos van escapados con "\\*" porque esto se muestra con
    st.success/st.markdown, que interpreta Markdown - sin escapar, varios
    asteriscos seguidos se leen como enfasis (negritas/cursivas) y desaparecen
    en vez de mostrarse tal cual."""
    palabras = []
    for palabra in (nombre or "").strip().split():
        if len(palabra) <= 2:
            palabras.append(palabra)
        else:
            palabras.append(palabra[0] + "\\*" * (len(palabra) - 2) + palabra[-1])
    return " ".join(palabras)


def mostrar_logo(negocio, ancho=140):
    if negocio.get("logo_base64"):
        try:
            st.image(base64.b64decode(negocio["logo_base64"]), width=ancho)
        except Exception:
            pass


def selector_horarios(horarios, key_prefix, por_fila=6):
    """Cuadritos de horas para elegir, en vez de un dropdown - solo muestra
    las horas que de verdad estan disponibles. Regresa la hora elegida."""
    key_sel = f"{key_prefix}_hora_sel"
    if st.session_state.get(key_sel) not in horarios:
        st.session_state[key_sel] = horarios[0] if horarios else None

    for i in range(0, len(horarios), por_fila):
        fila = horarios[i:i + por_fila]
        cols = st.columns(por_fila)
        for j, h in enumerate(fila):
            es_actual = st.session_state[key_sel] == h
            if cols[j].button(
                h, key=f"{key_prefix}_btn_{h}",
                type="primary" if es_actual else "secondary",
                use_container_width=True,
            ):
                st.session_state[key_sel] = h
                st.rerun()
    return st.session_state[key_sel]


def etiqueta_estado(estado):
    return {"Agendada": "🟦", "Completada": "✅", "Cancelada": "❌", "No asistio": "⚠️"}.get(estado, "")


def _resolver_proveedor_final(proveedor_sel, proveedores, fecha_sel, duracion, hora_sel):
    """Si el cliente eligio 'Cualquiera disponible' (proveedor_sel == 0),
    regresa el primer proveedor que de verdad sigue libre a esa hora.
    Regresa None si ya no hay nadie disponible (alguien mas se adelanto)."""
    if proveedor_sel != 0:
        return proveedor_sel
    disponible_ahora = [
        p["id"] for p in proveedores
        if db.horarios_disponibles(p["id"], fecha_sel.isoformat(), duracion, [hora_sel])
    ]
    return disponible_ahora[0] if disponible_ahora else None


def _avisar_calendar(cita_id, cliente, servicio_nombre, proveedor_nombre, fecha_iso, hora_inicio, duracion, notas):
    """Intenta crear el evento en Google Calendar - nunca falla la cita si
    esto no funciona, solo regresa el mensaje de error (o None) para
    mostrarlo como aviso secundario."""
    hora_fin = (datetime.strptime(hora_inicio, "%H:%M") + timedelta(minutes=duracion)).strftime("%H:%M")
    event_id, error = google_calendar.crear_evento_cita(
        negocio_nombre=negocio["nombre"], servicio_nombre=servicio_nombre,
        proveedor_nombre=proveedor_nombre, cliente_nombre=cliente["nombre"],
        cliente_email=cliente["email"], fecha=fecha_iso, hora_inicio=hora_inicio,
        hora_fin=hora_fin, notas=notas,
    )
    if event_id:
        db.guardar_evento_calendar(cita_id, event_id)
    return error


def link_publico():
    """URL directa con la que agendan los pacientes de ESTE negocio (sin la
    parte del panel). Se arma con el dominio con el que se abrio la app."""
    try:
        host = st.context.headers.get("host") or ""
    except Exception:
        host = ""
    if not host:
        host = "TU-APP.streamlit.app"
    esquema = "http" if host.startswith(("localhost", "127.0.0.1")) else "https"
    return f"{esquema}://{host}/" + (f"?negocio={NEGOCIO_SLUG}" if NEGOCIO_SLUG else "")


MESES_NOMBRE = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_legible(f):
    return f"{DIAS_NOMBRE[db.DIAS_SEMANA[f.weekday()]]} {f.day} de {MESES_NOMBRE[f.month]}"


def icono_servicio(nombre):
    """Un icono que acompane a cada servicio en su tarjeta, segun palabras
    clave del nombre (si no reconoce nada, usa el icono del giro)."""
    n = (nombre or "").lower()
    reglas = [
        (("limpieza", "profilaxis"), "🪥"), (("blanque",), "✨"), (("brackets", "ortodon"), "😁"),
        (("endodon", "conducto"), "🦷"), (("extrac", "cirug", "muela"), "🦷"), (("resina", "curaci"), "🦷"),
        (("carilla", "sonrisa", "estetic", "estétic"), "💎"), (("implante",), "🔩"),
        (("valoraci", "diagn", "consulta", "revisi"), "🩺"), (("barba",), "🧔"), (("corte",), "✂️"),
        (("ceja",), "👁️"), (("niño", "nino", "infantil"), "🧒"),
    ]
    for claves, icono in reglas:
        if any(c in n for c in claves):
            return icono
    return V["icono"]


def avatar_persona(nombre):
    n = (nombre or "").lower()
    if n.startswith("dra"):
        return "👩‍⚕️"
    if n.startswith("dr"):
        return "👨‍⚕️"
    return V["icono_personal"]


def precio_texto(precio):
    return f"${precio:,.0f}" if precio else ""


# ---------------------------------------------------------------- Vista publica: cliente se autoagenda
def pagina_reservar_publica():
    # Sin barra "DEMO" aqui: los pacientes nunca la ven (solo personal y dueno)
    ui.encabezado_negocio(negocio, V["subtitulo"], V["icono"])

    if SUSCRIPCION["bloqueado"]:
        st.info("La agenda en línea no está disponible por el momento. "
                f"Por favor comunícate directamente con {negocio['nombre']} para agendar tu cita.")
        ui.pie()
        return

    servicios = db.list_servicios(solo_activos=True)
    proveedores = db.list_proveedores(solo_activos=True)

    if not servicios or not proveedores:
        st.info("Este negocio todavía no tiene la agenda configurada. Intenta más tarde.")
        ui.pie()
        return

    with st.container(key="card_principal"):
        ui.titulo_seccion("RESERVA EN LÍNEA", V["titulo_reserva"],
                          "Elige el servicio, con quién y el horario que más te convenga. Solo verás horarios realmente libres.")

        # ---- 1. Servicio (tarjetas)
        ui.paso(1, V["paso_servicio"])
        serv_por_id = {s["id"]: s for s in servicios}
        with st.container(key="tarjetas_servicio"):
            servicio_id = st.radio(
                "Servicio", options=list(serv_por_id.keys()), key="pub_servicio", label_visibility="collapsed",
                format_func=lambda sid: f"{icono_servicio(serv_por_id[sid]['nombre'])}  **{serv_por_id[sid]['nombre']}**",
                captions=[
                    " · ".join(x for x in [f"{s['duracion_min']} min", precio_texto(s["precio"])] if x)
                    for s in servicios
                ],
            )
        duracion = serv_por_id[servicio_id]["duracion_min"]

        # ---- 2. Especialista (tarjetas)
        ui.paso(2, V["paso_especialista"])
        prov_por_id = {p["id"]: p for p in proveedores}
        with st.container(key="tarjetas_especialista"):
            proveedor_sel = st.radio(
                "Especialista", options=[0] + list(prov_por_id.keys()), key="pub_proveedor",
                label_visibility="collapsed",
                format_func=lambda pid: "⚡  **Cualquiera disponible**" if pid == 0
                else f"{avatar_persona(prov_por_id[pid]['nombre'])}  **{prov_por_id[pid]['nombre']}**",
                captions=["El primer horario libre"] + [p["especialidad"] or " " for p in proveedores],
            )

        # ---- 3 y 4. Fecha + horarios
        dias_laborales = negocio["dias_laborales"].split(",")
        col_fecha, col_hora = st.columns([1, 2], gap="large")
        with col_fecha:
            ui.paso(3, "Fecha de la cita")
            # Si hoy ya cerro (o no se abre), arrancar en el siguiente dia habil
            fecha_inicial = hoy_negocio()
            if ahora_negocio().strftime("%H:%M") >= negocio["hora_cierre"]:
                fecha_inicial += timedelta(days=1)
            for _ in range(7):
                if db.DIAS_SEMANA[fecha_inicial.weekday()] in dias_laborales:
                    break
                fecha_inicial += timedelta(days=1)
            fecha_sel = st.date_input(
                "Fecha", value=fecha_inicial, min_value=hoy_negocio(), key="fecha_reserva_publica",
                label_visibility="collapsed", format="DD/MM/YYYY")
            st.caption(fecha_legible(fecha_sel).capitalize())

        hora_sel = None
        with col_hora:
            ui.paso(4, "Horarios disponibles")
            if db.DIAS_SEMANA[fecha_sel.weekday()] not in dias_laborales:
                dias_abiertos = ", ".join(DIAS_NOMBRE.get(d, d) for d in dias_laborales)
                siguiente = fecha_sel
                for _ in range(14):
                    siguiente += timedelta(days=1)
                    if db.DIAS_SEMANA[siguiente.weekday()] in dias_laborales:
                        break
                st.warning(f"Ese día no abrimos. Atendemos: {dias_abiertos}.")
                st.button(
                    f"Ir al {fecha_legible(siguiente)}",
                    on_click=lambda: st.session_state.update(fecha_reserva_publica=siguiente),
                )
            else:
                horarios_base = generar_horarios(
                    negocio["hora_apertura"], negocio["hora_cierre"], negocio["intervalo_min"])
                horarios_base = quitar_horas_pasadas(horarios_base, fecha_sel)
                horarios_base = quitar_horas_descanso(
                    horarios_base, duracion, negocio.get("descanso_inicio"), negocio.get("descanso_fin"))
                if proveedor_sel == 0:
                    disponibles = sorted(set().union(*[
                        db.horarios_disponibles(p["id"], fecha_sel.isoformat(), duracion, horarios_base)
                        for p in proveedores
                    ]))
                else:
                    disponibles = db.horarios_disponibles(
                        proveedor_sel, fecha_sel.isoformat(), duracion, horarios_base)
                if not disponibles:
                    st.info("Ya no quedan horarios libres ese día con esta opción. Prueba otra fecha o especialista.")
                else:
                    with st.container(key="horarios"):
                        hora_sel = selector_horarios(disponibles, key_prefix="pub", por_fila=4)

        if hora_sel is None:
            ui.pie()
            return

        servicio_nombre = serv_por_id[servicio_id]["nombre"]
        con_quien = "el primer especialista disponible" if proveedor_sel == 0 else prov_por_id[proveedor_sel]["nombre"]
        st.success(
            f"**{servicio_nombre}** con {con_quien} — {fecha_legible(fecha_sel)} a las **{hora_sel}**"
        )

        def _confirmar(cliente, notas):
            proveedor_final = _resolver_proveedor_final(proveedor_sel, proveedores, fecha_sel, duracion, hora_sel)
            if proveedor_final is None:
                st.error("Ese horario se acaba de ocupar, por favor elige otro.")
                return
            proveedor_nombre = next(p["nombre"] for p in proveedores if p["id"] == proveedor_final)
            try:
                cita_id = db.agendar_cita(cliente["id"], proveedor_final, servicio_id, fecha_sel.isoformat(),
                                           hora_sel, duracion, notas.strip())
            except ValueError:
                st.error("Ese horario se acaba de ocupar, por favor elige otro.")
                return
            st.success(
                f"✅ Listo, {cliente['nombre']}. Tu cita quedó agendada para el "
                f"{fecha_legible(fecha_sel)} a las {hora_sel} con {proveedor_nombre}."
            )
            error_calendar = _avisar_calendar(
                cita_id, cliente, servicio_nombre, proveedor_nombre,
                fecha_sel.isoformat(), hora_sel, duracion, notas)
            if error_calendar:
                st.caption(f"(La cita quedó guardada. No se pudo mandar la invitación de Google Calendar: {error_calendar})")


        # ---- 5. Datos del paciente
        ui.paso(5, "Tus datos")
        with st.container(key="card_datos"):
            modo = st.radio("¿Ya has agendado con nosotros antes?", [f"No, soy {V['cliente']} nuevo", f"Sí, ya soy {V['cliente']}"],
                             horizontal=True)

            if modo == f"Sí, ya soy {V['cliente']}":
                # Solo coincidencia EXACTA de telefono o correo (nunca por nombre ni por
                # pedazos): asi nadie puede escribir "a" y ver la lista de pacientes.
                # Y lo unico que se muestra de quien se encontro es su nombre
                # enmascarado - nunca telefonos ni correos.
                busqueda = st.text_input("Escribe tu teléfono (10 dígitos) o el correo con el que te registraste")
                cliente_sel = None
                termino = busqueda.strip()
                if termino:
                    if "@" not in termino and not telefono_valido(termino):
                        st.warning("Escribe tu teléfono completo (10 dígitos, solo números) o tu correo.")
                        encontrados = None
                    else:
                        encontrados = db.buscar_cliente_exacto(termino)
                    if encontrados is None:
                        pass
                    elif not encontrados:
                        st.warning("No encontramos a nadie con ese dato. Revisa que esté bien escrito, "
                                   f"o elige '{V['Cliente']} nuevo' para registrarte.")
                    elif len(encontrados) == 1:
                        cliente_sel = encontrados[0]
                        st.success(f"Hola de nuevo, {enmascarar_nombre(cliente_sel['nombre'])}.")
                    else:
                        opciones = {c["id"]: enmascarar_nombre(c["nombre"]) for c in encontrados}
                        cid = st.selectbox("Hay varios registros con ese dato - ¿cuál eres?", options=list(opciones.keys()),
                                            format_func=lambda cid: opciones[cid])
                        cliente_sel = next(c for c in encontrados if c["id"] == cid)

                notas = st.text_input("Notas o síntomas (opcional)", key="notas_reservar_existente")
                if cliente_sel and st.button("Confirmar cita", type="primary", use_container_width=True):
                    _confirmar(cliente_sel, notas)
            else:
                with st.form("form_reservar_publico"):
                    c1, c2 = st.columns(2)
                    nombre = c1.text_input("Nombre completo *", placeholder="Ej. Ana María Gómez")
                    telefono = c2.text_input("Teléfono (WhatsApp) *", placeholder="10 dígitos, ej. 5512345678")
                    c3, c4 = st.columns(2)
                    email = c3.text_input("Correo electrónico (opcional)", placeholder="tucorreo@ejemplo.com",
                                          help="Si lo dejas, te mandamos la invitación y un recordatorio.")
                    notas = c4.text_input("Notas o síntomas (opcional)", placeholder="Ej. dolor de muela, revisión")

                    if st.form_submit_button("Confirmar cita", type="primary", use_container_width=True):
                        if not nombre.strip() or not telefono.strip():
                            st.error("Nombre y teléfono son obligatorios.")
                        elif not telefono_valido(telefono):
                            st.error("El teléfono debe tener 10 dígitos (solo números, sin espacios ni guiones).")
                        else:
                            # Si el telefono ya esta registrado no se agenda a nombre de
                            # otra persona en silencio: se le pide que entre como
                            # registrado (asi tampoco se revela de quien es ese numero).
                            if db.find_cliente_por_telefono(telefono.strip()):
                                st.warning(
                                    "Ese teléfono ya está registrado. Elige "
                                    f"'Sí, ya soy {V['cliente']}' arriba y búscate con tu teléfono.")
                            else:
                                cliente_id = db.add_cliente(nombre.strip(), telefono.strip(), email.strip(), "")
                                cliente = {"id": cliente_id, "nombre": nombre.strip(), "email": email.strip()}
                                _confirmar(cliente, notas)

    ui.pie()


# ---------------------------------------------------------------- Ruteo: publico vs panel del negocio
if st.query_params.get("panel") != "staff":
    pagina_reservar_publica()
    st.stop()

if "staff_autenticado" not in st.session_state:
    st.session_state.staff_autenticado = False
if "rol" not in st.session_state:
    st.session_state.rol = None

if SUSCRIPCION["bloqueado"]:
    ui.encabezado_negocio(negocio, "Panel privado del negocio", V["icono"])
    if SUSCRIPCION["motivo"] == "suspendida":
        titulo = "Tu cuenta está suspendida"
        mensaje = "El acceso al panel y a la agenda en línea está pausado."
    elif SUSCRIPCION["plan"] == "prueba":
        titulo = "Tu prueba gratis terminó"
        mensaje = ("Gracias por probar la agenda en línea. Tus datos están guardados: "
                   "en cuanto actives tu suscripción, todo vuelve a funcionar tal como lo dejaste.")
    else:
        titulo = "Tu suscripción venció"
        mensaje = ("Tus datos están guardados: en cuanto renueves, todo vuelve a funcionar "
                   "tal como lo dejaste.")
    contacto = _contacto_aika()
    ui.aviso_bloqueo(titulo, mensaje + (f" Contacta a Aika Solutions: {contacto}" if contacto
                                        else " Contacta a Aika Solutions para continuar."))
    st.stop()

if not st.session_state.staff_autenticado:
    ui.barra_plataforma(ES_DEMO)
    ui.encabezado_negocio(negocio, "Panel privado del negocio", V["icono"])
    _izq, centro, _der = st.columns([1, 2, 1])
    with centro, st.container(key="card_principal"):
        ui.titulo_seccion("ACCESO", "🔒 Entrar al panel", "Usa la clave del personal o la del dueño.")
        clave = st.text_input("Clave de acceso", type="password")
        entrar = st.button("Entrar", type="primary", use_container_width=True)
    if entrar:
        clave_dueno = _secreto("dueno_password")
        clave_staff = _secreto("staff_password")
        if clave_dueno and clave == clave_dueno:
            st.session_state.staff_autenticado = True
            st.session_state.rol = "dueño"
            st.rerun()
        elif clave_staff and clave == clave_staff:
            st.session_state.staff_autenticado = True
            st.session_state.rol = "staff"
            st.rerun()
        else:
            st.error("Clave incorrecta (revisa .streamlit/secrets.toml).")
    st.stop()

if negocio.get("logo_base64"):
    with st.sidebar:
        mostrar_logo(negocio, ancho=88)
st.sidebar.title(negocio["nombre"])
st.sidebar.caption(f"{V['subtitulo']} · {'Dueño' if st.session_state.rol == 'dueño' else 'Personal'}")

ICONOS_MENU = {"Agenda del día": "📅", "Nueva cita": "➕", V["Clientes"]: "👥", "Servicios": "🧾",
               "Personal": V["icono_personal"], "Configuración": "⚙️", "Estadísticas": "📊"}
paginas = ["Agenda del día", "Nueva cita", V["Clientes"], "Servicios", "Personal", "Configuración"]
if st.session_state.rol == "dueño":
    paginas.append("Estadísticas")
pagina = st.sidebar.radio("Menú", paginas, format_func=lambda p: f"{ICONOS_MENU.get(p, '')}  {p}",
                          label_visibility="collapsed")
# En celular/tableta el menu tapa la pantalla: al elegir una opcion se cierra solo
if st.session_state.get("_pagina_anterior") not in (None, pagina):
    ui.cerrar_menu_en_celular()
st.session_state["_pagina_anterior"] = pagina
st.sidebar.divider()
with st.sidebar.expander(f"🔗 Link para que agenden los {V['clientes']}", expanded=True):
    st.markdown('<div class="ak-link-ayuda">Compártelo por WhatsApp o redes. '
                'Cópialo con el botón verde de la derecha.</div>', unsafe_allow_html=True)
    st.code(link_publico(), language=None)
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    st.session_state.staff_autenticado = False
    st.session_state.rol = None
    st.rerun()
st.sidebar.caption("Powered by Aika Solutions")

ui.barra_plataforma(ES_DEMO)
if SUSCRIPCION["aviso"]:
    contacto = _contacto_aika()
    st.warning(SUSCRIPCION["aviso"] + (f" ({contacto})" if contacto else ""))


# ---------------------------------------------------------------- Agenda del dia
if pagina == "Agenda del día":
    st.title(f"{V['icono']} Agenda del día")

    col1, col2 = st.columns([1, 2])
    with col1:
        fecha_sel = st.date_input("Fecha", value=hoy_negocio(), format="DD/MM/YYYY")
    proveedores = db.list_proveedores(solo_activos=True)
    with col2:
        opciones_prov = {0: "Todos"} | {p["id"]: p["nombre"] for p in proveedores}
        prov_sel = st.selectbox("Especialista", options=list(opciones_prov.keys()), format_func=lambda pid: opciones_prov[pid])

    citas = db.list_citas(fecha=fecha_sel.isoformat(), proveedor_id=prov_sel or None)

    # ---- Indicadores de arriba
    activas = [c for c in citas if c["estado"] != "Cancelada"]
    pendientes = [c for c in citas if c["estado"] == "Agendada"]
    n_clientes = len(db.list_clientes())
    if st.session_state.rol == "dueño":
        hoy_ = hoy_negocio()
        fin_mes = db.citas_finalizadas(hoy_.replace(day=1).isoformat(), hoy_.isoformat())
        ingresos_mes = sum(r["precio"] for r in fin_mes if r["estado"] == "Completada")
        cuarto = ("💵", "Ingresos del mes", f"${ingresos_mes:,.0f}", "#ECFDF5", "#047857")
    else:
        cuarto = (V["icono_personal"], V["especialistas"], len(proveedores), "#F5F3FF", "#6D28D9")
    ui.kpis([
        ("📅", f"Citas del {fecha_sel.strftime('%d/%m')}", len(activas), ui.TEAL_CLARO, ui.TEAL),
        ("⏳", "Pendientes por atender", len(pendientes), "#EEF2FF", "#4338CA"),
        ("👥", f"{V['Clientes']} registrados", n_clientes, "#EFF6FF", "#1D4ED8"),
        cuarto,
    ])

    # Listas completas (no solo activos) para que una cita ya creada con un
    # servicio/proveedor que despues se desactivo se pueda seguir editando.
    todos_servicios = db.list_servicios()
    todos_proveedores = db.list_proveedores()
    clientes = db.list_clientes()
    horarios = generar_horarios(negocio["hora_apertura"], negocio["hora_cierre"], negocio["intervalo_min"])

    if "editando_cita" not in st.session_state:
        st.session_state.editando_cita = None

    if not citas:
        st.info("No hay citas agendadas para este día (con este filtro).")
    for c in citas:
        with st.container(border=True):
            st.markdown(ui.tarjeta_cita_html(c, V["Cliente"]), unsafe_allow_html=True)
            if c["estado"] == "Agendada":
                b1, b2, b3, b4 = st.columns(4)
                if b1.button("✓ Completar", key=f"comp_{c['id']}", type="primary", use_container_width=True):
                    db.cambiar_estado_cita(c["id"], "Completada")
                    st.rerun()
                if b2.button("✎ Editar", key=f"edit_{c['id']}", use_container_width=True):
                    st.session_state.editando_cita = c["id"]
                    st.rerun()
                if b3.button("No asistió", key=f"noasi_{c['id']}", use_container_width=True):
                    db.cambiar_estado_cita(c["id"], "No asistio")
                    st.rerun()
                if b4.button("Cancelar", key=f"canc_{c['id']}", use_container_width=True):
                    db.cambiar_estado_cita(c["id"], "Cancelada")
                    google_calendar.borrar_evento(c["evento_calendar_id"])
                    st.rerun()

            if st.session_state.editando_cita == c["id"]:
                st.divider()
                ids_clientes = [cl["id"] for cl in clientes]
                ids_servicios = [s["id"] for s in todos_servicios]
                ids_proveedores = [p["id"] for p in todos_proveedores]
                with st.form(f"form_editar_cita_{c['id']}"):
                    e1, e2, e3 = st.columns(3)
                    cliente_id_e = e1.selectbox(
                        V["Cliente"], options=ids_clientes,
                        index=ids_clientes.index(c["cliente_id"]),
                        format_func=lambda cid: next(cl["nombre"] for cl in clientes if cl["id"] == cid))
                    servicio_id_e = e2.selectbox(
                        "Servicio", options=ids_servicios,
                        index=ids_servicios.index(c["servicio_id"]),
                        format_func=lambda sid: next(
                            f"{s['nombre']} ({s['duracion_min']} min)" for s in todos_servicios if s["id"] == sid))
                    proveedor_id_e = e3.selectbox(
                        V["con_quien"], options=ids_proveedores,
                        index=ids_proveedores.index(c["proveedor_id"]),
                        format_func=lambda pid: next(p["nombre"] for p in todos_proveedores if p["id"] == pid))

                    f1, f2 = st.columns(2)
                    fecha_e = f1.date_input("Fecha", value=date.fromisoformat(c["fecha"]))
                    hora_e = f2.selectbox(
                        "Hora", options=horarios,
                        index=horarios.index(c["hora_inicio"]) if c["hora_inicio"] in horarios else 0)
                    notas_e = st.text_area("Notas", value=c["notas"] or "")

                    g1, g2 = st.columns(2)
                    guardar = g1.form_submit_button("Guardar cambios")
                    cancelar_edicion = g2.form_submit_button("Cancelar edición")

                    if guardar:
                        duracion = next(s["duracion_min"] for s in todos_servicios if s["id"] == servicio_id_e)
                        try:
                            db.editar_cita(c["id"], cliente_id_e, proveedor_id_e, servicio_id_e,
                                            fecha_e.isoformat(), hora_e, duracion, notas_e)
                            st.session_state.editando_cita = None
                            st.success("Cita actualizada.")
                            st.rerun()
                        except ValueError as e_err:
                            st.error(str(e_err))
                    if cancelar_edicion:
                        st.session_state.editando_cita = None
                        st.rerun()

# ---------------------------------------------------------------- Nueva cita
elif pagina == "Nueva cita":
    st.title("➕ Agendar nueva cita")

    servicios = db.list_servicios(solo_activos=True)
    proveedores = db.list_proveedores(solo_activos=True)
    clientes = db.list_clientes()

    if not servicios:
        st.warning("Primero agrega al menos un servicio en la pagina 'Servicios'.")
    elif not proveedores:
        st.warning("Primero agrega al menos una persona en la pagina 'Personal'.")
    else:
        with st.expander(f"¿{V['Cliente']} nuevo? Agrégalo aquí primero"):
            with st.form("form_cliente_rapido"):
                nc1, nc2 = st.columns(2)
                nombre_nuevo = nc1.text_input(f"Nombre del {V['cliente']}")
                telefono_nuevo = nc2.text_input("Teléfono")
                email_nuevo = st.text_input("Correo (opcional - si lo pones, se le manda invitación de Calendar)")
                if st.form_submit_button(f"Guardar {V['cliente']}"):
                    if not nombre_nuevo.strip():
                        st.error(f"Ponle un nombre al {V['cliente']}.")
                    elif telefono_nuevo.strip() and not telefono_valido(telefono_nuevo):
                        st.error("El teléfono debe tener 10 dígitos (solo números, sin espacios ni guiones).")
                    else:
                        db.add_cliente(nombre_nuevo.strip(), telefono_nuevo.strip(), email_nuevo.strip(), "")
                        st.success(f"{V['Cliente']} '{nombre_nuevo}' agregado. Ya debería aparecer en la lista de abajo.")
                        st.rerun()

        clientes = db.list_clientes()
        if not clientes:
            st.info(f"Todavía no hay {V['clientes']} registrados. Agrega uno arriba.")
        else:
            servicio_id = st.selectbox("Servicio", options=[s["id"] for s in servicios],
                                        format_func=lambda sid: next(
                                            f"{s['nombre']} ({s['duracion_min']} min)" for s in servicios if s["id"] == sid))
            proveedor_id = st.selectbox(V["con_quien"], options=[p["id"] for p in proveedores],
                                         format_func=lambda pid: next(p["nombre"] for p in proveedores if p["id"] == pid))
            duracion = next(s["duracion_min"] for s in servicios if s["id"] == servicio_id)

            fecha_cita = st.date_input("Fecha", value=hoy_negocio())
            horarios_base = generar_horarios(negocio["hora_apertura"], negocio["hora_cierre"], negocio["intervalo_min"])
            horarios_base = quitar_horas_pasadas(horarios_base, fecha_cita)
            horarios_base = quitar_horas_descanso(
                horarios_base, duracion, negocio.get("descanso_inicio"), negocio.get("descanso_fin"))
            horarios = db.horarios_disponibles(proveedor_id, fecha_cita.isoformat(), duracion, horarios_base)

            if not horarios:
                st.warning("No hay horarios disponibles para ese proveedor en esa fecha.")
            else:
                st.write("Hora disponible")
                with st.container(key="horarios"):
                    hora_cita = selector_horarios(horarios, key_prefix="staff_nueva")

                with st.form("form_nueva_cita"):
                    cliente_id = st.selectbox(V["Cliente"], options=[c["id"] for c in clientes],
                                               format_func=lambda cid: next(c["nombre"] for c in clientes if c["id"] == cid))
                    notas = st.text_area("Notas (opcional)")

                    if st.form_submit_button("Agendar cita", type="primary", use_container_width=True):
                        try:
                            cita_id = db.agendar_cita(cliente_id, proveedor_id, servicio_id, fecha_cita.isoformat(),
                                                       hora_cita, duracion, notas)
                            st.success("Cita agendada correctamente.")
                            cliente_sel = next(c for c in clientes if c["id"] == cliente_id)
                            servicio_nombre = next(s["nombre"] for s in servicios if s["id"] == servicio_id)
                            proveedor_nombre = next(p["nombre"] for p in proveedores if p["id"] == proveedor_id)
                            error_calendar = _avisar_calendar(
                                cita_id, cliente_sel, servicio_nombre, proveedor_nombre,
                                fecha_cita.isoformat(), hora_cita, duracion, notas)
                            if error_calendar:
                                st.caption(f"(No se pudo mandar la invitación de Google Calendar: {error_calendar})")
                        except ValueError as e:
                            st.error(str(e))

# ---------------------------------------------------------------- Clientes
elif pagina == V["Clientes"]:
    st.title(f"👥 {V['Clientes']}")

    with st.expander(f"Agregar {V['cliente']} nuevo"):
        with st.form("form_nuevo_cliente"):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre")
            telefono = c2.text_input("Teléfono")
            email = st.text_input("Correo (opcional - si lo pones, se le manda invitación de Calendar)")
            notas = st.text_area("Notas (opcional)")
            if st.form_submit_button("Guardar"):
                if not nombre.strip():
                    st.error(f"Ponle un nombre al {V['cliente']}.")
                elif telefono.strip() and not telefono_valido(telefono):
                    st.error("El teléfono debe tener 10 dígitos (solo números, sin espacios ni guiones).")
                else:
                    db.add_cliente(nombre.strip(), telefono.strip(), email.strip(), notas.strip())
                    st.success(f"{V['Cliente']} agregado.")
                    st.rerun()

    busqueda = st.text_input("Buscar por nombre o teléfono")
    clientes = db.list_clientes(busqueda or None)
    st.caption(f"{len(clientes)} {V['cliente']}(s)")
    for cl in clientes:
        with st.expander(f"{cl['nombre']} - {cl['telefono'] or 'sin teléfono'}"):
            with st.form(f"form_editar_cliente_{cl['id']}"):
                c1, c2 = st.columns(2)
                nombre_e = c1.text_input("Nombre", value=cl["nombre"], key=f"nom_{cl['id']}")
                telefono_e = c2.text_input("Teléfono", value=cl["telefono"] or "", key=f"tel_{cl['id']}")
                email_e = st.text_input("Email", value=cl["email"] or "", key=f"mail_{cl['id']}")
                notas_e = st.text_area("Notas", value=cl["notas"] or "", key=f"notas_{cl['id']}")
                if st.form_submit_button("Guardar cambios"):
                    if telefono_e.strip() and not telefono_valido(telefono_e):
                        st.error("El teléfono debe tener 10 dígitos (solo números, sin espacios ni guiones).")
                    else:
                        db.update_cliente(cl["id"], nombre_e.strip(), telefono_e.strip(), email_e.strip(), notas_e.strip())
                        st.success("Actualizado.")
                        st.rerun()

# ---------------------------------------------------------------- Servicios
elif pagina == "Servicios":
    st.title("🛠️ Servicios")
    st.caption(V["ejemplos_servicios"])

    with st.expander("Agregar servicio nuevo"):
        with st.form("form_nuevo_servicio"):
            c1, c2, c3 = st.columns(3)
            nombre = c1.text_input("Nombre del servicio")
            duracion = c2.number_input("Duración (minutos)", min_value=5, step=5, value=30)
            precio = c3.number_input("Precio (opcional)", min_value=0.0, step=0.5, value=0.0)
            if st.form_submit_button("Guardar"):
                if nombre.strip():
                    db.add_servicio(nombre.strip(), int(duracion), precio or None)
                    st.success("Servicio agregado.")
                    st.rerun()
                else:
                    st.error("Ponle un nombre al servicio.")

    for s in db.list_servicios():
        with st.expander(f"{'✅' if s['activo'] else '🚫'} {s['nombre']} - {s['duracion_min']} min"):
            with st.form(f"form_editar_servicio_{s['id']}"):
                c1, c2, c3 = st.columns(3)
                nombre_e = c1.text_input("Nombre", value=s["nombre"], key=f"snom_{s['id']}")
                duracion_e = c2.number_input("Duración (min)", min_value=5, step=5, value=s["duracion_min"], key=f"sdur_{s['id']}")
                precio_e = c3.number_input("Precio", min_value=0.0, step=0.5, value=s["precio"] or 0.0, key=f"sprecio_{s['id']}")
                activo_e = st.checkbox("Activo (aparece al agendar)", value=bool(s["activo"]), key=f"sact_{s['id']}")
                if st.form_submit_button("Guardar cambios"):
                    db.update_servicio(s["id"], nombre_e.strip(), int(duracion_e), precio_e or None, activo_e)
                    st.success("Actualizado.")
                    st.rerun()

# ---------------------------------------------------------------- Personal
elif pagina == "Personal":
    st.title(f"{V['icono_personal']} Personal")
    st.caption(V["personal_desc"])

    with st.expander("Agregar persona nueva"):
        with st.form("form_nuevo_proveedor"):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre")
            especialidad = c2.text_input("Rol / especialidad (opcional)")
            if st.form_submit_button("Guardar"):
                if nombre.strip():
                    db.add_proveedor(nombre.strip(), especialidad.strip())
                    st.success("Agregado.")
                    st.rerun()
                else:
                    st.error("Ponle un nombre.")

    for p in db.list_proveedores():
        with st.expander(f"{'✅' if p['activo'] else '🚫'} {p['nombre']} - {p['especialidad'] or 'sin rol'}"):
            with st.form(f"form_editar_proveedor_{p['id']}"):
                c1, c2 = st.columns(2)
                nombre_e = c1.text_input("Nombre", value=p["nombre"], key=f"pnom_{p['id']}")
                especialidad_e = c2.text_input("Rol / especialidad", value=p["especialidad"] or "", key=f"pesp_{p['id']}")
                activo_e = st.checkbox("Activo (aparece al agendar)", value=bool(p["activo"]), key=f"pact_{p['id']}")
                if st.form_submit_button("Guardar cambios"):
                    db.update_proveedor(p["id"], nombre_e.strip(), especialidad_e.strip(), activo_e)
                    st.success("Actualizado.")
                    st.rerun()

# ---------------------------------------------------------------- Configuracion
elif pagina == "Configuración":
    st.title("⚙️ Configuración del negocio")

    st.subheader("Logo")
    mostrar_logo(negocio, ancho=160)
    logo_subido = st.file_uploader("Subir/cambiar logo (PNG o JPG)", type=["png", "jpg", "jpeg"])
    lc1, lc2 = st.columns(2)
    if logo_subido is not None and lc1.button("Guardar este logo"):
        db.set_logo(base64.b64encode(logo_subido.read()).decode("ascii"))
        st.success("Logo actualizado.")
        st.rerun()
    if negocio.get("logo_base64") and lc2.button("Quitar logo"):
        db.set_logo(None)
        st.success("Logo quitado.")
        st.rerun()

    st.divider()

    st.subheader("Color de la marca")
    st.caption("Es el color de botones, tarjetas seleccionadas, pasos y gráficas, para tu panel y la página "
               "de tus " + V["clientes"] + ". Elige uno que combine con tu logo.")
    COLORES_SUGERIDOS = {
        "Verde azulado": "#0F766E", "Azul": "#1D4ED8", "Azul marino": "#1E3A8A", "Morado": "#7C3AED",
        "Rosa": "#DB2777", "Rojo": "#DC2626", "Naranja": "#EA580C", "Dorado": "#B45309",
        "Verde": "#15803D", "Negro": "#111827",
    }
    if "color_elegido" not in st.session_state:
        st.session_state.color_elegido = COLOR_MARCA
    sugeridos = st.columns(5)
    for i, (nombre_color, hex_color) in enumerate(COLORES_SUGERIDOS.items()):
        sugeridos[i % 5].button(
            nombre_color, key=f"color_{hex_color}", use_container_width=True,
            on_click=lambda h=hex_color: st.session_state.update(color_elegido=h))
    cc1, cc2 = st.columns([1, 2])
    with cc1:
        color_elegido = st.color_picker("O elige cualquier color", key="color_elegido")
    with cc2:
        vista = ui.paleta(color_elegido)
        st.markdown(
            f'<div style="margin-top:28px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">'
            f'<span style="background:{vista["p"]};color:{vista["texto"]};padding:8px 16px;border-radius:12px;'
            f'font-weight:700">Confirmar cita</span>'
            f'<span style="background:{vista["claro"]};border:1.5px solid {vista["p"]};padding:8px 16px;'
            f'border-radius:12px;font-weight:600">Tarjeta seleccionada</span>'
            f'<span style="background:{vista["p"]};color:{vista["texto"]};width:26px;height:26px;'
            f'border-radius:999px;display:inline-flex;align-items:center;justify-content:center;font-weight:800">1</span>'
            f'</div>', unsafe_allow_html=True)
    gc1, gc2 = st.columns(2)
    if gc1.button("Guardar color", type="primary", use_container_width=True):
        db.set_color(color_elegido)
        st.success("Color guardado.")
        st.rerun()
    if negocio.get("color_marca") and gc2.button("Volver al color original", use_container_width=True):
        db.set_color(None)
        st.session_state.pop("color_elegido", None)
        st.rerun()

    st.divider()

    # Fuera del formulario a proposito: los widgets dentro de un st.form no
    # vuelven a correr el script hasta que se manda el formulario, asi que
    # el checkbox no podia des-bloquear los campos de abajo en vivo.
    tiene_descanso = st.checkbox(
        "¿Cierran para comer o tienen un bloque no disponible a medio día?",
        value=bool(negocio.get("descanso_inicio")), key="config_tiene_descanso")

    with st.form("form_config"):
        nombre = st.text_input("Nombre del negocio", value=negocio["nombre"])
        tipo = st.selectbox("Tipo de negocio", options=db.TIPOS_NEGOCIO,
                             index=db.TIPOS_NEGOCIO.index(negocio["tipo"]) if negocio["tipo"] in db.TIPOS_NEGOCIO else 0)
        c1, c2, c3 = st.columns(3)
        hora_apertura = c1.text_input("Hora de apertura (HH:MM)", value=negocio["hora_apertura"])
        hora_cierre = c2.text_input("Hora de cierre (HH:MM)", value=negocio["hora_cierre"])
        intervalo = c3.number_input("Intervalo entre horarios disponibles (min)", min_value=5, step=5,
                                     value=negocio["intervalo_min"])
        dias_actuales = negocio["dias_laborales"].split(",")
        dias = st.multiselect("Días laborales", options=db.DIAS_SEMANA, default=dias_actuales)

        dc1, dc2 = st.columns(2)
        descanso_inicio = dc1.text_input(
            "Descanso desde (HH:MM)", value=negocio.get("descanso_inicio") or "14:00", disabled=not tiene_descanso)
        descanso_fin = dc2.text_input(
            "Descanso hasta (HH:MM)", value=negocio.get("descanso_fin") or "15:00", disabled=not tiene_descanso)

        if st.form_submit_button("Guardar configuración"):
            hora_apertura, hora_cierre = hora_apertura.strip(), hora_cierre.strip()
            descanso_inicio, descanso_fin = (descanso_inicio.strip(), descanso_fin.strip()) if tiene_descanso else ("", "")

            if not hora_valida(hora_apertura) or not hora_valida(hora_cierre):
                st.error("La hora de apertura y de cierre deben tener el formato HH:MM (ej. 09:00).")
            elif hora_apertura >= hora_cierre:
                st.error("La hora de apertura debe ser antes que la hora de cierre.")
            elif tiene_descanso and (not hora_valida(descanso_inicio) or not hora_valida(descanso_fin)):
                st.error("El descanso debe tener horas con formato HH:MM (ej. 14:00).")
            elif tiene_descanso and not (hora_apertura <= descanso_inicio < descanso_fin <= hora_cierre):
                st.error("El descanso debe caer dentro del horario del negocio, con la hora 'desde' antes que 'hasta'.")
            elif not dias:
                st.error("Elige al menos un día laboral.")
            else:
                db.set_negocio(nombre.strip(), tipo, hora_apertura, hora_cierre, dias, int(intervalo),
                                descanso_inicio, descanso_fin)
                st.success("Configuración guardada.")
                st.rerun()

# ---------------------------------------------------------------- Estadisticas (solo dueno)
elif pagina == "Estadísticas":
    st.title("📊 Estadísticas del negocio")
    st.caption("Solo visible para el dueño. Cuenta cada cita una vez que ya tuvo un resultado final.")

    hoy = hoy_negocio()
    preset = st.selectbox(
        "Rango de fechas",
        ["Hoy", "Últimos 7 días", "Este mes", "Últimos 30 días", "Personalizado"],
        index=2,
    )
    if preset == "Hoy":
        fecha_inicio, fecha_fin = hoy, hoy
    elif preset == "Últimos 7 días":
        fecha_inicio, fecha_fin = hoy - timedelta(days=6), hoy
    elif preset == "Este mes":
        fecha_inicio, fecha_fin = hoy.replace(day=1), hoy
    elif preset == "Últimos 30 días":
        fecha_inicio, fecha_fin = hoy - timedelta(days=29), hoy
    else:
        c1, c2 = st.columns(2)
        fecha_inicio = c1.date_input("Desde", value=hoy.replace(day=1))
        fecha_fin = c2.date_input("Hasta", value=hoy)

    if fecha_inicio > fecha_fin:
        st.error("La fecha 'Desde' no puede ser después de 'Hasta'.")
    else:
        agrupar_por = st.radio("Agrupar gráficas por:", ["Día", "Semana", "Quincena", "Mes"], horizontal=True)

        registros = db.citas_finalizadas(fecha_inicio.isoformat(), fecha_fin.isoformat())

        if not registros:
            st.info("No hay citas completadas, canceladas o no asistidas en este rango.")
        else:
            df = pd.DataFrame(registros)
            df["fecha"] = pd.to_datetime(df["fecha"])

            def periodo_de(f):
                if agrupar_por == "Día":
                    return f.strftime("%Y-%m-%d")
                if agrupar_por == "Semana":
                    return (f - pd.Timedelta(days=f.weekday())).strftime("Semana del %Y-%m-%d")
                if agrupar_por == "Quincena":
                    return f"{f.strftime('%Y-%m')} ({'1-15' if f.day <= 15 else '16-fin'})"
                return f.strftime("%Y-%m")

            df["periodo"] = df["fecha"].apply(periodo_de)

            # ---- KPIs del total del rango. Las canceladas / no-asistio NO se
            # restan de lo ganado - solo se muestran aparte, como referencia.
            ganado = float(df.loc[df["estado"] == "Completada", "precio"].sum())
            no_cobrado = float(df.loc[df["estado"] != "Completada", "precio"].sum())

            dias_rango = pd.date_range(fecha_inicio, fecha_fin, freq="D")
            n_dias = max(len(dias_rango), 1)
            n_semanas = max(len(dias_rango.to_period("W").unique()), 1)
            n_quincenas = max(len({(d.year, d.month, 1 if d.day <= 15 else 2) for d in dias_rango}), 1)
            n_meses = max(len(dias_rango.to_period("M").unique()), 1)

            k1, k2 = st.columns(2)
            k1.metric("Ganado (citas completadas)", f"${ganado:,.2f}")
            k2.metric("Valor no cobrado (canceladas + no asistio)", f"${no_cobrado:,.2f}")
            st.caption("El valor no cobrado es solo informativo - no se resta de lo ganado.")

            servicios_sin_precio = sorted(
                df.loc[(df["estado"] == "Completada") & (df["precio"] == 0), "servicio_nombre"].unique()
            )
            if servicios_sin_precio:
                nombres = ", ".join(servicios_sin_precio)
                st.warning(
                    f"'{nombres}' no tiene precio configurado (o está en $0), por eso las citas "
                    f"completadas de ese servicio no suman a 'Ganado'. Ponle precio en la pagina 'Servicios' "
                    f"si debería contar."
                )

            st.caption("Promedios de lo ganado sobre el rango de fechas seleccionado")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Promedio diario", f"${ganado / n_dias:,.2f}")
            p2.metric("Promedio semanal", f"${ganado / n_semanas:,.2f}")
            p3.metric("Promedio quincenal", f"${ganado / n_quincenas:,.2f}")
            p4.metric("Promedio mensual", f"${ganado / n_meses:,.2f}")

            st.divider()

            orden_periodos = sorted(df["periodo"].unique())
            escala_estado = alt.Scale(domain=list(COLOR_ESTADO.keys()), range=list(COLOR_ESTADO.values()))

            # ---- Grafica 1 (barras): citas por resultado, por periodo
            st.subheader("Citas por resultado, por periodo")
            conteo = df.groupby(["periodo", "estado"]).size().reset_index(name="cantidad")
            chart_estados = alt.Chart(conteo).mark_bar(
                size=18, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, stroke=CONTORNO, strokeWidth=1
            ).encode(
                x=alt.X("periodo:N", title=None, sort=orden_periodos),
                xOffset=alt.XOffset("estado:N", sort=["Completada", "Cancelada", "No asistio"]),
                y=alt.Y("cantidad:Q", title="Citas", stack=None, axis=alt.Axis(format="d", tickMinStep=1)),
                color=alt.Color("estado:N", scale=escala_estado, legend=alt.Legend(title="Resultado")),
                tooltip=[
                    alt.Tooltip("periodo:N", title="Periodo"),
                    alt.Tooltip("estado:N", title="Resultado"),
                    alt.Tooltip("cantidad:Q", title="Citas"),
                ],
            ).properties(height=320)
            st.altair_chart(chart_estados, use_container_width=True)

            # ---- Grafica 2 (pastel): distribucion de resultados en todo el rango
            st.subheader("Distribución de citas por resultado (todo el rango)")
            conteo_total = df.groupby("estado").size().reset_index(name="cantidad")
            conteo_total["porcentaje"] = conteo_total["cantidad"] / conteo_total["cantidad"].sum()
            base_pie1 = alt.Chart(conteo_total).encode(
                theta=alt.Theta("cantidad:Q", stack=True),
                color=alt.Color("estado:N", scale=escala_estado, legend=alt.Legend(title="Resultado")),
                tooltip=[
                    alt.Tooltip("estado:N", title="Resultado"),
                    alt.Tooltip("cantidad:Q", title="Citas"),
                    alt.Tooltip("porcentaje:Q", title="Porcentaje", format=".0%"),
                ],
            )
            pie1 = base_pie1.mark_arc(outerRadius=130, stroke=CONTORNO, strokeWidth=1.5)
            etiquetas1 = base_pie1.mark_text(radius=155, color="#52514e").encode(
                text=alt.Text("porcentaje:Q", format=".0%")
            )
            st.altair_chart((pie1 + etiquetas1).properties(height=360), use_container_width=True)

            # ---- Grafica 3 (barras): ganado por periodo
            st.subheader("Ganado por periodo")
            ganado_periodo = (
                df[df["estado"] == "Completada"]
                .groupby("periodo")["precio"].sum()
                .reset_index(name="ganado")
                .sort_values("periodo")
            )
            chart_ganado = alt.Chart(ganado_periodo).mark_bar(
                size=18, color=AZUL_FUERTE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4
            ).encode(
                x=alt.X("periodo:N", title=None, sort=orden_periodos),
                y=alt.Y("ganado:Q", title="Ganado ($)", axis=alt.Axis(format="$,.0f")),
                tooltip=[
                    alt.Tooltip("periodo:N", title="Periodo"),
                    alt.Tooltip("ganado:Q", title="Ganado", format="$,.2f"),
                ],
            ).properties(height=320)
            st.altair_chart(chart_ganado, use_container_width=True)

            # ---- Grafica 4 (pastel): valor cobrado vs no cobrado
            st.subheader("Valor cobrado vs no cobrado (todo el rango)")
            cobro = pd.DataFrame([
                {"tipo": "Cobrado (completadas)", "valor": ganado},
                {"tipo": "No cobrado (canceladas + no asistio)", "valor": no_cobrado},
            ])
            if cobro["valor"].sum() == 0:
                st.info("Los servicios en este rango no tienen precio configurado.")
            else:
                cobro["porcentaje"] = cobro["valor"] / cobro["valor"].sum()
                base_pie2 = alt.Chart(cobro).encode(
                    theta=alt.Theta("valor:Q", stack=True),
                    color=alt.Color(
                        "tipo:N",
                        scale=alt.Scale(
                            domain=["Cobrado (completadas)", "No cobrado (canceladas + no asistio)"],
                            range=[AZUL_FUERTE, GRIS_CLARO],
                        ),
                        legend=alt.Legend(title=None),
                    ),
                    tooltip=[
                        alt.Tooltip("tipo:N", title="Tipo"),
                        alt.Tooltip("valor:Q", title="Valor", format="$,.2f"),
                        alt.Tooltip("porcentaje:Q", title="Porcentaje", format=".0%"),
                    ],
                )
                pie2 = base_pie2.mark_arc(outerRadius=130, stroke=CONTORNO, strokeWidth=1.5)
                etiquetas2 = base_pie2.mark_text(radius=155, color="#52514e").encode(
                    text=alt.Text("porcentaje:Q", format=".0%")
                )
                st.altair_chart((pie2 + etiquetas2).properties(height=360), use_container_width=True)

            resumen_periodo = df.groupby("periodo").apply(
                lambda g: pd.Series({
                    "ganado": g.loc[g["estado"] == "Completada", "precio"].sum(),
                    "no_cobrado": g.loc[g["estado"] != "Completada", "precio"].sum(),
                })
            ).reset_index().sort_values("periodo")

            with st.expander("Ver tabla de datos"):
                st.dataframe(
                    resumen_periodo[["periodo", "ganado", "no_cobrado"]].rename(columns={
                        "periodo": "Periodo", "ganado": "Ganado", "no_cobrado": "No cobrado",
                    }),
                    use_container_width=True, hide_index=True,
                )
