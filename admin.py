"""
Panel de administrador de Aika Solutions (?panel=admin en la URL raiz).

Solo para el dueno de la plataforma: ve TODAS las clinicas dadas de alta en
Secrets ([negocios.X]), su plan (prueba / activa / suspendida), cuando vencen,
cuantos pacientes y citas tienen, y puede extender, activar o suspender cada
una. Se protege con su propia clave: admin_password en Secrets.
"""

import calendar
import hmac
from datetime import date, timedelta

import streamlit as st

import db
import registro
import suscripcion
import ui


def _sumar_meses(f, meses):
    mes = f.month - 1 + meses
    anio = f.year + mes // 12
    mes = mes % 12 + 1
    return date(anio, mes, min(f.day, calendar.monthrange(anio, mes)[1]))


def _base_para_extender(estado, hoy):
    """Si aun no vence, se extiende desde su fecha; si ya vencio, desde hoy."""
    vence = estado["vence"]
    return vence if vence and vence >= hoy else hoy


def _negocios_en_secrets():
    try:
        return {slug: dict(datos) for slug, datos in st.secrets.get("negocios", {}).items()}
    except Exception:
        return {}


def _todas_las_clinicas():
    """Clinicas del registro central + las de Secrets ([negocios.X]).
    Regresa (dict slug -> datos, error_del_registro_o_None)."""
    clinicas = {slug: {**d, "origen": "secrets"} for slug, d in _negocios_en_secrets().items()}
    error = None
    if registro.configurado():
        try:
            for c in registro.listar():
                clinicas[c["slug"]] = {**c, "origen": "registro"}
        except Exception as e:
            error = str(e)[:200]
    return clinicas, error


def _seccion_registro():
    if not registro.configurado():
        with st.expander("🗂️ Lista central de clínicas: sin configurar"):
            st.markdown(
                "Con la lista central, las clínicas nuevas aparecen aquí **solas** (sin pegar nada en "
                "Secrets) y puedes registrarlas o quitarlas desde este panel.\n\n"
                "Para activarla, en tu PC haz doble clic en **`configurar_registro.bat`** y sigue los pasos.")
        return
    with st.expander("🗂️ Registrar una clínica que ya existe"):
        st.caption("Para clínicas creadas a mano o antes de la lista central. No cambia nada en su app.")
        with st.form("form_registrar_clinica"):
            r1, r2 = st.columns(2)
            slug = r1.text_input("Identificador corto (sin espacios)")
            nombre = r2.text_input("Nombre")
            url_app = st.text_input("Dirección de su app", placeholder="https://nombre.streamlit.app/")
            t1, t2 = st.columns(2)
            turso_url = t1.text_input("URL de su base (libsql://...)")
            turso_token = t2.text_input("Token de su base", type="password")
            if st.form_submit_button("Registrar", type="primary", use_container_width=True):
                if not (slug.strip() and nombre.strip() and turso_url.strip() and turso_token.strip()):
                    st.error("Faltan datos: identificador, nombre, URL y token son obligatorios.")
                else:
                    registro.guardar(slug.strip().lower(), nombre.strip(), "", url_app.strip(),
                                     turso_url.strip(), turso_token.strip())
                    st.success("Registrada.")
                    st.rerun()


def _leer_negocio(datos, desde, hasta):
    db.usar_turso(datos.get("turso_database_url"), datos.get("turso_auth_token"))
    db.init_db()
    negocio = db.get_negocio()
    resumen = db.resumen_admin(desde, hasta)
    return negocio, resumen


def _login():
    ui.barra_plataforma(True, admin=True)
    _izq, centro, _der = st.columns([1, 2, 1])
    with centro, st.container(key="card_principal"):
        ui.titulo_seccion("AIKA SOLUTIONS", "🔐 Panel de administración",
                          "Acceso exclusivo para el administrador de la plataforma.")
        clave_admin = None
        try:
            clave_admin = st.secrets.get("admin_password")
        except Exception:
            pass
        if not clave_admin:
            st.warning("Falta configurar la clave: agrega una línea `admin_password = \"...\"` "
                       "al inicio de Secrets (fuera de cualquier [negocios.X]).")
            st.stop()
        clave = st.text_input("Clave de administrador", type="password")
        if st.button("Entrar", type="primary", use_container_width=True):
            if hmac.compare_digest(clave.encode(), str(clave_admin).encode()):
                st.session_state.admin_ok = True
                st.rerun()
            st.error("Clave incorrecta.")
    st.stop()


def pagina(hoy, url_base):
    """hoy: fecha actual de Mexico. url_base: 'https://...streamlit.app/'."""
    if not st.session_state.get("admin_ok"):
        _login()

    ui.barra_plataforma(True, admin=True)
    c1, c2 = st.columns([4, 1])
    with c1:
        st.title("🛠️ Clínicas de la plataforma")
    with c2:
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.admin_ok = False
            st.rerun()

    negocios, error_registro = _todas_las_clinicas()
    if error_registro:
        st.error(f"No se pudo leer la lista central de clínicas: {error_registro}")
    if not negocios:
        st.info("Todavía no hay clínicas registradas.")
        _seccion_registro()
        return

    desde = hoy.replace(day=1).isoformat()
    hasta = _sumar_meses(hoy.replace(day=1), 1).isoformat()
    filas = []
    for slug, datos in negocios.items():
        try:
            negocio, resumen = _leer_negocio(datos, desde, hasta)
            filas.append((slug, datos, negocio, resumen, suscripcion.estado(negocio, hoy), None))
        except Exception as e:  # una clinica con problemas no tumba el panel
            filas.append((slug, datos, None, None, None, str(e)[:200]))
    db.usar_turso(None, None)

    # ---- Indicadores generales
    ok = [f for f in filas if f[2]]
    en_prueba = [f for f in ok if f[4]["plan"] == "prueba" and not f[4]["bloqueado"]]
    activas = [f for f in ok if f[4]["plan"] == "activa" and not f[4]["bloqueado"]]
    bloqueadas = [f for f in ok if f[4]["bloqueado"]]
    ingreso = sum((f[2].get("precio_mensual")
                   or suscripcion.NIVELES.get(f[2].get("nivel") or "basico", (0, 0))[1]) for f in activas)
    ui.kpis([
        ("🏥", "Clínicas", len(filas), ui.TEAL_CLARO, ui.TEAL),
        ("🧪", "En prueba", len(en_prueba), "#EEF2FF", "#4338CA"),
        ("✅", "Pagando", len(activas), "#ECFDF5", "#047857"),
        ("💵", "Ingreso mensual", f"${ingreso:,.0f}", "#FFFBEB", "#B45309"),
    ])
    if bloqueadas:
        st.warning(f"{len(bloqueadas)} clínica(s) bloqueada(s) por vencimiento o suspensión: "
                   + ", ".join(f[2]["nombre"] for f in bloqueadas))

    with st.expander("➕ Dar de alta una clínica nueva"):
        pasos_extra = ("3. Listo: aparece aquí sola (lista central) y el despertador la visita sola."
                       if registro.configurado() else
                       "3. Pega su bloque `[negocios.…]` al final de los Secrets de **esta** app para verla aquí.\n"
                       "4. Agrega su dirección a `despertar_urls.txt` en GitHub para que nunca se duerma.")
        st.markdown(
            "1. En tu PC, en la carpeta `agenda_citas`, haz doble clic en **`nuevo_cliente.bat`** y "
            "contesta lo que te pregunta (nombre, giro, color, logo, dirección de su app).\n"
            "2. El script te guía para crear **su propia app** en Streamlit (mismo código) y pegar sus Secrets.\n"
            + pasos_extra +
            "\n\nQueda con **14 días de prueba**; el script te da sus links y contraseñas."
        )
    _seccion_registro()

    orden = {"suspendida": 0, "prueba": 1, "activa": 2, "demo": 3, "": 4}
    filas.sort(key=lambda f: (f[2] is not None, orden.get((f[4] or {}).get("plan", ""), 5),
                              (f[4] or {}).get("dias_restantes") if (f[4] or {}).get("dias_restantes") is not None else 9999))

    for slug, datos, negocio, resumen, est, error in filas:
        with st.container(border=True):
            if error:
                st.markdown(f"**{slug}** · ⚠️ No se pudo leer su base de datos")
                st.caption(error)
                _boton_quitar(slug, datos)
                continue
            _tarjeta_clinica(slug, datos, negocio, resumen, est, hoy, url_base)


def _boton_quitar(slug, datos):
    if datos.get("origen") == "registro":
        if st.button("Quitar de la lista", key=f"quitar_{slug}",
                     help="Solo la quita de esta lista. No borra sus datos ni apaga su app."):
            registro.quitar(slug)
            st.rerun()


def _tarjeta_clinica(slug, datos, negocio, resumen, est, hoy, url_base):
    if est["bloqueado"]:
        chip = ui.chip_html("Bloqueada" if est["motivo"] == "vencida" else "Suspendida", "#FFF1F2", "#BE123C")
    elif est["plan"] == "prueba":
        chip = ui.chip_html("Prueba gratis", "#EEF2FF", "#4338CA")
    elif est["plan"] == "activa":
        chip = ui.chip_html("Pagando", "#ECFDF5", "#047857")
    else:
        chip = ui.chip_html(suscripcion.etiqueta_plan(est["plan"]), "#F1F5F9", "#475569")
    if est["vence"]:
        d = est["dias_restantes"]
        cuando = (f"venció hace {-d} día(s)" if d < 0 else "vence hoy" if d == 0 else f"vence en {d} día(s)")
        vence_txt = f"{est['vence'].strftime('%d/%m/%Y')} · {cuando}"
    else:
        vence_txt = "sin vencimiento"
    nivel = negocio.get("nivel") or suscripcion.NIVEL_PREDETERMINADO
    nombre_nivel, precio_nivel, maximo = suscripcion.NIVELES.get(nivel, suscripcion.NIVELES["basico"])
    precio = negocio.get("precio_mensual") or precio_nivel
    pac_mes = resumen.get("pacientes_mes", 0)
    nivel_ok = suscripcion.nivel_para(pac_mes)
    if datos.get("url_app"):  # clinica con su propia app (opcion B)
        link_pacientes = datos["url_app"].rstrip("/") + "/"
        link_panel = link_pacientes + "?panel=staff"
    else:                     # clinica dentro de esta app (?negocio=)
        link_pacientes = f"{url_base}?negocio={slug}"
        link_panel = link_pacientes + "&panel=staff"
    st.markdown(
        f'<div class="ak-cita-hora">{ui.escapar(negocio["nombre"])} &nbsp;{chip}</div>'
        f'<div class="ak-cita-linea">{ui.escapar(negocio["tipo"])} · <code>{ui.escapar(slug)}</code> · '
        f'Vencimiento: <b>{vence_txt}</b></div>'
        f'<div class="ak-cita-linea">Plan <b>{nombre_nivel}</b> · <b>${precio:,.0f}/mes</b> · '
        f'Pacientes este mes: <b>{pac_mes} de {maximo}</b> · Citas este mes: <b>{resumen["citas_mes"]}</b> · '
        f'Pacientes registrados: <b>{resumen["pacientes"]}</b></div>',
        unsafe_allow_html=True)
    if est["plan"] != "demo" and pac_mes > maximo:
        if nivel_ok:
            n2, p2, m2 = suscripcion.NIVELES[nivel_ok]
            st.warning(f"⬆️ Rebasó su plan: {pac_mes} pacientes este mes (su plan {nombre_nivel} cubre {maximo}). "
                       f"Le corresponde **{n2}** (${p2}/mes).")
        else:
            st.warning(f"⬆️ {pac_mes} pacientes este mes: pasa de 200, le corresponde **cotización especial**.")

    with st.expander("Administrar"):
        st.markdown(f"Link de pacientes: {link_pacientes}  \nPanel: {link_panel}")
        db.usar_turso(datos.get("turso_database_url"), datos.get("turso_auth_token"))
        try:
            base = _base_para_extender(est, hoy)
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("+14 días de prueba", key=f"p14_{slug}", use_container_width=True):
                db.set_suscripcion(plan="prueba", vence_el=(base + timedelta(days=14)).isoformat())
                st.rerun()
            if b2.button("💵 Pagó 1 mes", key=f"m1_{slug}", type="primary", use_container_width=True):
                db.set_suscripcion(plan="activa", vence_el=_sumar_meses(base, 1).isoformat())
                st.rerun()
            if b3.button("💵 Pagó 1 año", key=f"a1_{slug}", use_container_width=True):
                db.set_suscripcion(plan="activa", vence_el=_sumar_meses(base, 12).isoformat())
                st.rerun()
            if est["plan"] == "suspendida":
                if b4.button("Reactivar", key=f"re_{slug}", use_container_width=True):
                    db.set_suscripcion(plan="activa" if est["vence"] and not est["dias_restantes"] < 0 else "prueba")
                    st.rerun()
            elif b4.button("⛔ Suspender", key=f"su_{slug}", use_container_width=True):
                db.set_suscripcion(plan="suspendida")
                st.rerun()

            with st.form(f"form_admin_{slug}"):
                niveles = list(suscripcion.NIVELES.keys())
                nivel_e = st.selectbox("Nivel del plan", niveles, format_func=suscripcion.etiqueta_nivel,
                                       index=niveles.index(nivel) if nivel in niveles else 0,
                                       help="Al guardar, el precio se pone solo según el nivel "
                                            "(si quieres otro precio, escríbelo abajo y marca la casilla).")
                f1, f2, f3 = st.columns(3)
                planes = ["prueba", "activa", "suspendida", "demo"]
                plan_e = f1.selectbox("Plan", planes, format_func=suscripcion.etiqueta_plan,
                                      index=planes.index(est["plan"]) if est["plan"] in planes else 0)
                vence_e = f2.date_input("Vence el", value=est["vence"] or hoy + timedelta(days=14),
                                        format="DD/MM/YYYY")
                precio_e = f3.number_input("Precio especial (MXN)", min_value=0.0, step=50.0,
                                           value=float(precio or precio_nivel))
                especial = st.checkbox("Usar el precio especial (descuento o cotización)",
                                       value=bool(negocio.get("precio_mensual"))
                                       and negocio.get("precio_mensual") != precio_nivel)
                notas_e = st.text_input("Notas internas (solo tú las ves)", value=negocio.get("notas_admin") or "")
                if st.form_submit_button("Guardar cambios", use_container_width=True):
                    precio_final = precio_e if especial else suscripcion.NIVELES[nivel_e][1]
                    db.set_suscripcion(plan=plan_e, vence_el=vence_e.isoformat(), nivel=nivel_e,
                                       precio_mensual=precio_final, notas_admin=notas_e)
                    st.success("Guardado.")
                    st.rerun()
        finally:
            db.usar_turso(None, None)
        _boton_quitar(slug, datos)
