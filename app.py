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
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

import db
import google_calendar

# Paleta de las graficas de Estadisticas: azul fuerte / gris claro / blanco.
# Cancelada y No asistio quedan en tonos muy claros a proposito (pedido del
# negocio) - por eso todas las marcas llevan un contorno gris (CONTORNO) para
# que sigan siendo visibles sobre el fondo blanco.
AZUL_FUERTE = "#1c5cab"
GRIS_CLARO = "#d8d7d1"
BLANCO = "#ffffff"
CONTORNO = "#a9a89f"
COLOR_ESTADO = {"Completada": AZUL_FUERTE, "Cancelada": GRIS_CLARO, "No asistio": BLANCO}

DIAS_NOMBRE = {
    "Lun": "lunes", "Mar": "martes", "Mie": "miercoles", "Jue": "jueves",
    "Vie": "viernes", "Sab": "sabado", "Dom": "domingo",
}

st.set_page_config(page_title="Agenda de citas", page_icon="📅", layout="wide")

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
if turso_url and turso_token:
    db.usar_turso(turso_url, turso_token)
elif NEGOCIO_SLUG:
    st.error(f"No encontramos configuracion para el negocio '{NEGOCIO_SLUG}'. Revisa el link.")
    st.stop()

db.init_db()

negocio = db.get_negocio()


ZONA_HORARIA_NEGOCIO = ZoneInfo("America/Mexico_City")


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


def mostrar_logo(negocio, ancho=140):
    if negocio.get("logo_base64"):
        try:
            st.image(base64.b64decode(negocio["logo_base64"]), width=ancho)
        except Exception:
            pass


def selector_horarios(horarios, key_prefix):
    """Cuadritos de horas para elegir, en vez de un dropdown - solo muestra
    las horas que de verdad estan disponibles. Regresa la hora elegida."""
    key_sel = f"{key_prefix}_hora_sel"
    if st.session_state.get(key_sel) not in horarios:
        st.session_state[key_sel] = horarios[0] if horarios else None

    por_fila = 6
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


# ---------------------------------------------------------------- Vista publica: cliente se autoagenda
def pagina_reservar_publica():
    mostrar_logo(negocio)
    st.title(f"📅 Reservar cita - {negocio['nombre']}")
    st.caption(negocio["tipo"])

    servicios = db.list_servicios(solo_activos=True)
    proveedores = db.list_proveedores(solo_activos=True)

    if not servicios or not proveedores:
        st.info("Este negocio todavia no tiene la agenda configurada. Intenta mas tarde.")
        return

    servicio_id = st.selectbox(
        "Servicio", options=[s["id"] for s in servicios],
        format_func=lambda sid: next(f"{s['nombre']} ({s['duracion_min']} min)" for s in servicios if s["id"] == sid))
    duracion = next(s["duracion_min"] for s in servicios if s["id"] == servicio_id)

    opciones_prov = {0: "Cualquiera disponible"} | {p["id"]: p["nombre"] for p in proveedores}
    proveedor_sel = st.selectbox("Con quien", options=list(opciones_prov.keys()),
                                  format_func=lambda pid: opciones_prov[pid])

    dias_laborales = negocio["dias_laborales"].split(",")
    fecha_sel = st.date_input(
        "Fecha", value=hoy_negocio(), min_value=hoy_negocio(), key="fecha_reserva_publica")

    if db.DIAS_SEMANA[fecha_sel.weekday()] not in dias_laborales:
        dias_abiertos = ", ".join(DIAS_NOMBRE.get(d, d) for d in dias_laborales)
        siguiente = fecha_sel
        for _ in range(14):
            siguiente += timedelta(days=1)
            if db.DIAS_SEMANA[siguiente.weekday()] in dias_laborales:
                break
        st.warning(
            f"El {fecha_sel.strftime('%d/%m/%Y')} "
            f"({DIAS_NOMBRE.get(db.DIAS_SEMANA[fecha_sel.weekday()], '')}) el negocio esta cerrado. "
            f"Atendemos: {dias_abiertos}."
        )
        st.button(
            f"Usar el proximo dia disponible ({siguiente.strftime('%d/%m/%Y')})",
            on_click=lambda: st.session_state.update(fecha_reserva_publica=siguiente),
        )
        return

    horarios_base = generar_horarios(negocio["hora_apertura"], negocio["hora_cierre"], negocio["intervalo_min"])
    horarios_base = quitar_horas_pasadas(horarios_base, fecha_sel)
    horarios_base = quitar_horas_descanso(
        horarios_base, duracion, negocio.get("descanso_inicio"), negocio.get("descanso_fin"))

    if proveedor_sel == 0:
        disponibles = sorted(set().union(*[
            db.horarios_disponibles(p["id"], fecha_sel.isoformat(), duracion, horarios_base) for p in proveedores
        ]))
    else:
        disponibles = db.horarios_disponibles(proveedor_sel, fecha_sel.isoformat(), duracion, horarios_base)

    if not disponibles:
        st.warning("No hay horarios disponibles ese dia para esa opcion. Prueba otra fecha, servicio o proveedor.")
        return

    st.write("Hora disponible")
    hora_sel = selector_horarios(disponibles, key_prefix="pub")

    servicio_nombre = next(s["nombre"] for s in servicios if s["id"] == servicio_id)

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
            f"Listo, {cliente['nombre']}. Tu cita quedo agendada para el "
            f"{fecha_sel.strftime('%d/%m/%Y')} a las {hora_sel}."
        )
        error_calendar = _avisar_calendar(
            cita_id, cliente, servicio_nombre, proveedor_nombre,
            fecha_sel.isoformat(), hora_sel, duracion, notas)
        if error_calendar:
            st.caption(f"(La cita quedo guardada. No se pudo mandar la invitacion de Google Calendar: {error_calendar})")

    st.divider()
    st.subheader("Tus datos")
    modo = st.radio("¿Ya has agendado con nosotros antes?", ["No, soy cliente nuevo", "Si, ya soy cliente"],
                     horizontal=True)

    if modo == "Si, ya soy cliente":
        busqueda = st.text_input("Escribe tu nombre, telefono o correo para encontrarte")
        cliente_sel = None
        if busqueda.strip():
            encontrados = db.buscar_clientes(busqueda.strip())
            if not encontrados:
                st.warning("No encontramos a nadie con ese dato. Revisa que este bien escrito, "
                           "o usa 'Cliente nuevo' para registrarte.")
            elif len(encontrados) == 1:
                cliente_sel = encontrados[0]
                st.success(f"Hola de nuevo, {cliente_sel['nombre']}.")
            else:
                opciones = {c["id"]: f"{c['nombre']} - {c['telefono'] or c['email'] or 'sin datos'}"
                            for c in encontrados}
                cid = st.selectbox("Encontramos varios - ¿cual eres?", options=list(opciones.keys()),
                                    format_func=lambda cid: opciones[cid])
                cliente_sel = next(c for c in encontrados if c["id"] == cid)

        notas = st.text_area("Algo que debamos saber (opcional)", key="notas_reservar_existente")
        if cliente_sel and st.button("Confirmar cita"):
            _confirmar(cliente_sel, notas)
    else:
        with st.form("form_reservar_publico"):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre completo")
            telefono = c2.text_input("Telefono")
            email = st.text_input("Email (opcional - si lo dejas, te mandamos invitacion y recordatorio)")
            notas = st.text_area("Algo que debamos saber (opcional)")

            if st.form_submit_button("Confirmar cita"):
                if not nombre.strip() or not telefono.strip():
                    st.error("Nombre y telefono son obligatorios.")
                else:
                    cliente_existente = db.find_cliente_por_telefono(telefono.strip())
                    if cliente_existente:
                        cliente = cliente_existente
                    else:
                        cliente_id = db.add_cliente(nombre.strip(), telefono.strip(), email.strip(), "")
                        cliente = {"id": cliente_id, "nombre": nombre.strip(), "email": email.strip()}
                    _confirmar(cliente, notas)


# ---------------------------------------------------------------- Ruteo: publico vs panel del negocio
if st.query_params.get("panel") != "staff":
    pagina_reservar_publica()
    st.stop()

if "staff_autenticado" not in st.session_state:
    st.session_state.staff_autenticado = False
if "rol" not in st.session_state:
    st.session_state.rol = None

if not st.session_state.staff_autenticado:
    st.title("🔒 Panel del negocio")
    clave = st.text_input("Clave de acceso", type="password")
    if st.button("Entrar"):
        clave_dueno = _secreto("dueno_password")
        clave_staff = _secreto("staff_password")
        if clave_dueno and clave == clave_dueno:
            st.session_state.staff_autenticado = True
            st.session_state.rol = "dueno"
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
        mostrar_logo(negocio, ancho=100)
st.sidebar.title(negocio["nombre"])
st.sidebar.caption(negocio["tipo"])
if st.sidebar.button("Salir del panel"):
    st.session_state.staff_autenticado = False
    st.session_state.rol = None
    st.rerun()
with st.sidebar.expander("Link para que agenden los clientes"):
    if NEGOCIO_SLUG:
        st.caption(
            "Esta app atiende varios negocios - comparte la URL con "
            f"'?negocio={NEGOCIO_SLUG}' pero SIN el '&panel=staff' "
            "(esa parte es solo para que tu entres aqui). Ejemplo: si el "
            f"panel vive en .../?negocio={NEGOCIO_SLUG}&panel=staff, el link "
            f"para clientes es .../?negocio={NEGOCIO_SLUG}"
        )
    else:
        st.caption(
            "Comparte la URL de esta app SIN el '?panel=staff' al final "
            "(esa parte es solo para que tu entres aqui). Por ejemplo, si "
            "esto vive en https://mi-negocio.streamlit.app/?panel=staff, "
            "el link para clientes es https://mi-negocio.streamlit.app/"
        )

paginas = ["Agenda del dia", "Nueva cita", "Clientes", "Servicios", "Personal", "Configuracion"]
if st.session_state.rol == "dueno":
    paginas.append("Estadisticas")
pagina = st.sidebar.radio("Ir a:", paginas)


# ---------------------------------------------------------------- Agenda del dia
if pagina == "Agenda del dia":
    st.title("📅 Agenda del dia")

    col1, col2 = st.columns([1, 2])
    with col1:
        fecha_sel = st.date_input("Fecha", value=hoy_negocio())
    proveedores = db.list_proveedores(solo_activos=True)
    with col2:
        opciones_prov = {0: "Todos"} | {p["id"]: p["nombre"] for p in proveedores}
        prov_sel = st.selectbox("Proveedor", options=list(opciones_prov.keys()),
                                 format_func=lambda pid: opciones_prov[pid])

    citas = db.list_citas(fecha=fecha_sel.isoformat(), proveedor_id=prov_sel or None)

    # Listas completas (no solo activos) para que una cita ya creada con un
    # servicio/proveedor que despues se desactivo se pueda seguir editando.
    todos_servicios = db.list_servicios()
    todos_proveedores = db.list_proveedores()
    clientes = db.list_clientes()
    horarios = generar_horarios(negocio["hora_apertura"], negocio["hora_cierre"], negocio["intervalo_min"])

    if "editando_cita" not in st.session_state:
        st.session_state.editando_cita = None

    if not citas:
        st.info("No hay citas agendadas para este dia (con este filtro).")
    for c in citas:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                st.markdown(f"**{c['hora_inicio']} - {c['hora_fin']}**  {etiqueta_estado(c['estado'])} {c['estado']}")
                st.write(f"Cliente: {c['cliente_nombre']} ({c['cliente_telefono'] or 'sin telefono'})")
            with c2:
                st.write(f"Servicio: {c['servicio_nombre']}")
                st.write(f"Con: {c['proveedor_nombre']}")
            with c3:
                if c["estado"] == "Agendada":
                    if st.button("Editar", key=f"edit_{c['id']}"):
                        st.session_state.editando_cita = c["id"]
                        st.rerun()
                    if st.button("Completar", key=f"comp_{c['id']}"):
                        db.cambiar_estado_cita(c["id"], "Completada")
                        st.rerun()
                    if st.button("Cancelar", key=f"canc_{c['id']}"):
                        db.cambiar_estado_cita(c["id"], "Cancelada")
                        google_calendar.borrar_evento(c["evento_calendar_id"])
                        st.rerun()
                    if st.button("No asistio", key=f"noasi_{c['id']}"):
                        db.cambiar_estado_cita(c["id"], "No asistio")
                        st.rerun()

            if st.session_state.editando_cita == c["id"]:
                st.divider()
                ids_clientes = [cl["id"] for cl in clientes]
                ids_servicios = [s["id"] for s in todos_servicios]
                ids_proveedores = [p["id"] for p in todos_proveedores]
                with st.form(f"form_editar_cita_{c['id']}"):
                    e1, e2, e3 = st.columns(3)
                    cliente_id_e = e1.selectbox(
                        "Cliente", options=ids_clientes,
                        index=ids_clientes.index(c["cliente_id"]),
                        format_func=lambda cid: next(cl["nombre"] for cl in clientes if cl["id"] == cid))
                    servicio_id_e = e2.selectbox(
                        "Servicio", options=ids_servicios,
                        index=ids_servicios.index(c["servicio_id"]),
                        format_func=lambda sid: next(
                            f"{s['nombre']} ({s['duracion_min']} min)" for s in todos_servicios if s["id"] == sid))
                    proveedor_id_e = e3.selectbox(
                        "Con quien", options=ids_proveedores,
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
                    cancelar_edicion = g2.form_submit_button("Cancelar edicion")

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
        with st.expander("¿Cliente nuevo? Agregalo aqui primero"):
            with st.form("form_cliente_rapido"):
                nc1, nc2 = st.columns(2)
                nombre_nuevo = nc1.text_input("Nombre del cliente")
                telefono_nuevo = nc2.text_input("Telefono")
                email_nuevo = st.text_input("Correo (opcional - si lo pones, se le manda invitacion de Calendar)")
                if st.form_submit_button("Guardar cliente"):
                    if not nombre_nuevo.strip():
                        st.error("Ponle un nombre al cliente.")
                    else:
                        db.add_cliente(nombre_nuevo.strip(), telefono_nuevo.strip(), email_nuevo.strip(), "")
                        st.success(f"Cliente '{nombre_nuevo}' agregado. Ya deberia aparecer en la lista de abajo.")
                        st.rerun()

        clientes = db.list_clientes()
        if not clientes:
            st.info("Todavia no hay clientes registrados. Agrega uno arriba.")
        else:
            servicio_id = st.selectbox("Servicio", options=[s["id"] for s in servicios],
                                        format_func=lambda sid: next(
                                            f"{s['nombre']} ({s['duracion_min']} min)" for s in servicios if s["id"] == sid))
            proveedor_id = st.selectbox("Con quien", options=[p["id"] for p in proveedores],
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
                hora_cita = selector_horarios(horarios, key_prefix="staff_nueva")

                with st.form("form_nueva_cita"):
                    cliente_id = st.selectbox("Cliente", options=[c["id"] for c in clientes],
                                               format_func=lambda cid: next(c["nombre"] for c in clientes if c["id"] == cid))
                    notas = st.text_area("Notas (opcional)")

                    if st.form_submit_button("Agendar cita"):
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
                                st.caption(f"(No se pudo mandar la invitacion de Google Calendar: {error_calendar})")
                        except ValueError as e:
                            st.error(str(e))

# ---------------------------------------------------------------- Clientes
elif pagina == "Clientes":
    st.title("👥 Clientes")

    with st.expander("Agregar cliente nuevo"):
        with st.form("form_nuevo_cliente"):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre")
            telefono = c2.text_input("Telefono")
            email = st.text_input("Correo (opcional - si lo pones, se le manda invitacion de Calendar)")
            notas = st.text_area("Notas (opcional)")
            if st.form_submit_button("Guardar"):
                if not nombre.strip():
                    st.error("Ponle un nombre al cliente.")
                else:
                    db.add_cliente(nombre.strip(), telefono.strip(), email.strip(), notas.strip())
                    st.success("Cliente agregado.")
                    st.rerun()

    busqueda = st.text_input("Buscar por nombre o telefono")
    clientes = db.list_clientes(busqueda or None)
    st.caption(f"{len(clientes)} cliente(s)")
    for cl in clientes:
        with st.expander(f"{cl['nombre']} - {cl['telefono'] or 'sin telefono'}"):
            with st.form(f"form_editar_cliente_{cl['id']}"):
                c1, c2 = st.columns(2)
                nombre_e = c1.text_input("Nombre", value=cl["nombre"], key=f"nom_{cl['id']}")
                telefono_e = c2.text_input("Telefono", value=cl["telefono"] or "", key=f"tel_{cl['id']}")
                email_e = st.text_input("Email", value=cl["email"] or "", key=f"mail_{cl['id']}")
                notas_e = st.text_area("Notas", value=cl["notas"] or "", key=f"notas_{cl['id']}")
                if st.form_submit_button("Guardar cambios"):
                    db.update_cliente(cl["id"], nombre_e.strip(), telefono_e.strip(), email_e.strip(), notas_e.strip())
                    st.success("Actualizado.")
                    st.rerun()

# ---------------------------------------------------------------- Servicios
elif pagina == "Servicios":
    st.title("🛠️ Servicios")
    st.caption("Ej. 'Consulta general' (30 min), 'Limpieza dental' (45 min), 'Corte de cabello' (20 min).")

    with st.expander("Agregar servicio nuevo"):
        with st.form("form_nuevo_servicio"):
            c1, c2, c3 = st.columns(3)
            nombre = c1.text_input("Nombre del servicio")
            duracion = c2.number_input("Duracion (minutos)", min_value=5, step=5, value=30)
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
                duracion_e = c2.number_input("Duracion (min)", min_value=5, step=5, value=s["duracion_min"], key=f"sdur_{s['id']}")
                precio_e = c3.number_input("Precio", min_value=0.0, step=0.5, value=s["precio"] or 0.0, key=f"sprecio_{s['id']}")
                activo_e = st.checkbox("Activo (aparece al agendar)", value=bool(s["activo"]), key=f"sact_{s['id']}")
                if st.form_submit_button("Guardar cambios"):
                    db.update_servicio(s["id"], nombre_e.strip(), int(duracion_e), precio_e or None, activo_e)
                    st.success("Actualizado.")
                    st.rerun()

# ---------------------------------------------------------------- Personal
elif pagina == "Personal":
    st.title("🧑‍⚕️ Personal")
    st.caption("Doctores, dentistas, barberos - quien atiende las citas.")

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
elif pagina == "Configuracion":
    st.title("⚙️ Configuracion del negocio")

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
        dias = st.multiselect("Dias laborales", options=db.DIAS_SEMANA, default=dias_actuales)

        tiene_descanso = st.checkbox(
            "¿Cierran para comer o tienen un bloque no disponible a medio dia?",
            value=bool(negocio.get("descanso_inicio")))
        dc1, dc2 = st.columns(2)
        descanso_inicio = dc1.text_input(
            "Descanso desde (HH:MM)", value=negocio.get("descanso_inicio") or "14:00", disabled=not tiene_descanso)
        descanso_fin = dc2.text_input(
            "Descanso hasta (HH:MM)", value=negocio.get("descanso_fin") or "15:00", disabled=not tiene_descanso)

        if st.form_submit_button("Guardar configuracion"):
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
                st.error("Elige al menos un dia laboral.")
            else:
                db.set_negocio(nombre.strip(), tipo, hora_apertura, hora_cierre, dias, int(intervalo),
                                descanso_inicio, descanso_fin)
                st.success("Configuracion guardada.")
                st.rerun()

# ---------------------------------------------------------------- Estadisticas (solo dueno)
elif pagina == "Estadisticas":
    st.title("📊 Estadisticas del negocio")
    st.caption("Solo visible para el dueno. Cuenta cada cita una vez que ya tuvo un resultado final.")

    hoy = hoy_negocio()
    preset = st.selectbox(
        "Rango de fechas",
        ["Hoy", "Ultimos 7 dias", "Este mes", "Ultimos 30 dias", "Personalizado"],
        index=2,
    )
    if preset == "Hoy":
        fecha_inicio, fecha_fin = hoy, hoy
    elif preset == "Ultimos 7 dias":
        fecha_inicio, fecha_fin = hoy - timedelta(days=6), hoy
    elif preset == "Este mes":
        fecha_inicio, fecha_fin = hoy.replace(day=1), hoy
    elif preset == "Ultimos 30 dias":
        fecha_inicio, fecha_fin = hoy - timedelta(days=29), hoy
    else:
        c1, c2 = st.columns(2)
        fecha_inicio = c1.date_input("Desde", value=hoy.replace(day=1))
        fecha_fin = c2.date_input("Hasta", value=hoy)

    if fecha_inicio > fecha_fin:
        st.error("La fecha 'Desde' no puede ser despues de 'Hasta'.")
    else:
        agrupar_por = st.radio("Agrupar graficas por:", ["Dia", "Semana", "Quincena", "Mes"], horizontal=True)

        registros = db.citas_finalizadas(fecha_inicio.isoformat(), fecha_fin.isoformat())

        if not registros:
            st.info("No hay citas completadas, canceladas o no asistidas en este rango.")
        else:
            df = pd.DataFrame(registros)
            df["fecha"] = pd.to_datetime(df["fecha"])

            def periodo_de(f):
                if agrupar_por == "Dia":
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
                    f"'{nombres}' no tiene precio configurado (o esta en $0), por eso las citas "
                    f"completadas de ese servicio no suman a 'Ganado'. Ponle precio en la pagina 'Servicios' "
                    f"si deberia contar."
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
            st.subheader("Distribucion de citas por resultado (todo el rango)")
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
