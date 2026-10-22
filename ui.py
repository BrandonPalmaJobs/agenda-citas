"""
Capa visual de la app (Aika Solutions): estilos (CSS) y piezas de HTML
reutilizables - barra de la plataforma, encabezado del negocio, pasos
numerados, tarjetas de indicadores, etiquetas de estado y pie de pagina.

Streamlit no deja estilizar todo con parametros, asi que aqui se inyecta un
solo bloque de CSS. Las secciones con tarjetas (servicios, especialistas,
horarios) se envuelven en st.container(key="...") y el CSS las ubica por la
clase "st-key-<key>" que Streamlit les pone - asi los estilos no se
"contagian" a otras partes de la app.
"""

import html

import streamlit as st

# Paleta de la marca (Aika). El color principal de cada clinica puede ser
# otro: se guarda en la base (negocio.color_marca) y paleta() calcula sus tonos.
COLOR_PREDETERMINADO = "#0F766E"
TEAL = "#0F766E"
TEAL_MEDIO = "#14B8A6"
TEAL_CLARO = "#F0FDFA"
TEAL_BORDE = "#99F6E4"
NAVY = "#0B1324"
NAVY_2 = "#111C33"
TEXTO = "#0F172A"
TEXTO_SUAVE = "#64748B"
BORDE = "#E2E8F0"
FONDO = "#F6F8FB"
AMBAR = "#F59E0B"
ROJO = "#E11D48"

# Colores de los estados de una cita (tambien los usan las graficas)
COLOR_ESTADO = {
    "Completada": TEAL,
    "Cancelada": "#CBD5E1",
    "No asistio": "#FBBF24",
}
_CHIP_ESTADO = {
    "Agendada": ("#EEF2FF", "#4338CA", "Agendada"),
    "Completada": ("var(--ak-p-claro)", "var(--ak-p-oscuro)", "Completada"),
    "Cancelada": ("#F1F5F9", "#475569", "Cancelada"),
    "No asistio": ("#FFFBEB", "#B45309", "No asistió"),
}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [data-testid="stApp"], [data-testid="stApp"] * {{
    font-family: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
}}
/* Los iconos de Streamlit usan su propia fuente de simbolos: no tocarla */
[data-testid="stApp"] [data-testid="stIconMaterial"],
[data-testid="stApp"] span.material-symbols-rounded {{
    font-family: 'Material Symbols Rounded' !important;
}}
[data-testid="stApp"] {{ background: {FONDO}; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1080px; }}

/* Quitar la "marca" de Streamlit: encabezado, botones Fork/GitHub, anclas */
[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stToolbarActions"], [data-testid="stMainMenu"] {{ display: none !important; }}
[data-testid="stHeaderActionElements"] {{ display: none !important; }}
footer {{ visibility: hidden; }}

h1, h2, h3 {{ color: {TEXTO}; letter-spacing: -0.02em; }}
h1 {{ font-weight: 800 !important; }}

/* Botones */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
    background: var(--ak-p) !important; border: 1px solid var(--ak-p) !important; color: var(--ak-p-texto) !important;
    border-radius: 12px !important; font-weight: 700 !important;
    box-shadow: 0 6px 16px -8px var(--ak-p-sombra);
}}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    background: var(--ak-p-oscuro) !important; border-color: var(--ak-p-oscuro) !important;
}}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {{
    border-radius: 12px !important; border: 1px solid {BORDE} !important; background: #fff !important;
    color: {TEXTO} !important; font-weight: 600 !important;
}}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover {{
    border-color: var(--ak-p) !important; color: var(--ak-p) !important;
}}

/* Campos */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input, [data-testid="stDateInput"] input {{ border-radius: 10px; }}
[data-testid="stSelectbox"] > div > div, [data-baseweb="select"] > div {{ border-radius: 10px !important; }}
[data-testid="stWidgetLabel"] p {{ font-weight: 600; color: {TEXTO}; font-size: .88rem; }}

/* Tarjetas (contenedores con borde) */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
    background: #fff;
}}
.st-key-card_principal, .st-key-card_datos {{
    background: #fff; border: 1px solid {BORDE}; border-radius: 22px;
    padding: 1.6rem 1.8rem; box-shadow: 0 10px 30px -18px rgba(15,23,42,.25);
}}
.st-key-card_datos {{ padding: 1.3rem 1.5rem; border-radius: 18px; box-shadow: none; background: #FBFCFE; }}
@media (max-width: 640px) {{
  .st-key-card_principal {{ padding: 1.1rem 1rem; border-radius: 18px; }}
}}

/* Tarjetas seleccionables (radio convertido en tarjetas).
   Estructura de Streamlit: [role=radiogroup] > div(opcion, data-selected) >
   label[stRadioOption] (circulo + texto) + div[stRadioCaption] (subtexto) */
.st-key-tarjetas_servicio [data-testid="stElementContainer"],
.st-key-tarjetas_especialista [data-testid="stElementContainer"] {{ width: 100% !important; }}
.st-key-tarjetas_servicio [data-testid="stRadio"],
.st-key-tarjetas_especialista [data-testid="stRadio"] {{ width: 100%; }}
.st-key-tarjetas_servicio [role="radiogroup"], .st-key-tarjetas_especialista [role="radiogroup"] {{
    display: grid !important; gap: 12px; width: 100%;
}}
.st-key-tarjetas_servicio [role="radiogroup"] {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
.st-key-tarjetas_especialista [role="radiogroup"] {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
@media (max-width: 640px) {{
  .st-key-tarjetas_servicio [role="radiogroup"], .st-key-tarjetas_especialista [role="radiogroup"] {{
      grid-template-columns: 1fr;
  }}
}}
.st-key-tarjetas_servicio [role="radiogroup"] > div, .st-key-tarjetas_especialista [role="radiogroup"] > div {{
    position: relative; background: #fff; border: 1.5px solid {BORDE}; border-radius: 16px;
    padding: 14px 16px; margin: 0 !important; min-height: 70px; cursor: pointer;
    display: flex; flex-direction: column; justify-content: center;
    transition: border-color .15s, box-shadow .15s, background .15s, transform .15s;
}}
.st-key-tarjetas_servicio [role="radiogroup"] > div:hover,
.st-key-tarjetas_especialista [role="radiogroup"] > div:hover {{ border-color: var(--ak-p-borde); transform: translateY(-1px); }}
.st-key-tarjetas_servicio [role="radiogroup"] > div[data-selected="true"],
.st-key-tarjetas_especialista [role="radiogroup"] > div[data-selected="true"],
.st-key-tarjetas_servicio [role="radiogroup"] > div:has(input:checked),
.st-key-tarjetas_especialista [role="radiogroup"] > div:has(input:checked) {{
    border-color: var(--ak-p); background: var(--ak-p-claro); box-shadow: 0 0 0 3px var(--ak-p-anillo);
}}
/* toda la tarjeta es clickeable: el label se "estira" sobre la tarjeta */
.st-key-tarjetas_servicio [data-testid="stRadioOption"],
.st-key-tarjetas_especialista [data-testid="stRadioOption"] {{ position: static; width: 100%; margin: 0; padding: 0; }}
.st-key-tarjetas_servicio [data-testid="stRadioOption"]::after,
.st-key-tarjetas_especialista [data-testid="stRadioOption"]::after {{
    content: ""; position: absolute; inset: 0; border-radius: 16px; cursor: pointer;
}}
/* esconder el circulito del radio */
.st-key-tarjetas_servicio [data-testid="stRadioOption"] > div > div:first-child,
.st-key-tarjetas_especialista [data-testid="stRadioOption"] > div > div:first-child {{ display: none !important; }}
.st-key-tarjetas_servicio [data-testid="stRadioOption"] p,
.st-key-tarjetas_especialista [data-testid="stRadioOption"] p {{ margin: 0; color: {TEXTO}; font-size: .95rem; }}
.st-key-tarjetas_servicio [data-testid="stRadioCaption"],
.st-key-tarjetas_especialista [data-testid="stRadioCaption"] {{ padding-left: 0 !important; margin: 4px 0 0 0 !important; }}
.st-key-tarjetas_servicio [data-testid="stRadioCaption"] p {{ color: {TEXTO_SUAVE}; font-weight: 600; font-size: .85rem; }}
.st-key-tarjetas_especialista [role="radiogroup"] > div {{ align-items: center; text-align: center; }}
.st-key-tarjetas_especialista [data-testid="stRadioOption"] p {{ font-size: .92rem; }}
.st-key-tarjetas_especialista [data-testid="stRadioCaption"] p {{ color: {TEXTO_SUAVE}; font-size: .8rem; }}

/* Horarios en "pastillas" */
.st-key-horarios [data-testid="stVerticalBlock"] {{ gap: 10px; }}
.st-key-horarios [data-testid="stHorizontalBlock"] {{ gap: 10px; }}
@media (max-width: 640px) {{
  .st-key-horarios [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
  .st-key-horarios [data-testid="stColumn"] {{
      flex: 1 1 calc(33.33% - 10px) !important; min-width: calc(33.33% - 10px) !important;
  }}
}}
.st-key-horarios button {{ border-radius: 999px !important; padding: .35rem .5rem !important; font-weight: 700 !important; }}

/* Indicadores (st.metric) como tarjetas */
[data-testid="stMetric"] {{
    background: #fff; border: 1px solid {BORDE}; border-radius: 18px; padding: 16px 18px;
    box-shadow: 0 6px 18px -14px rgba(15,23,42,.3);
}}
[data-testid="stMetricLabel"] p {{ color: {TEXTO_SUAVE}; font-weight: 600; }}
[data-testid="stMetricValue"] {{ color: {TEXTO}; font-weight: 800; }}

/* Barra lateral del panel */
[data-testid="stSidebar"] {{ background: linear-gradient(180deg, {NAVY} 0%, {NAVY_2} 100%); }}
[data-testid="stSidebar"] * {{ color: #E2E8F0; }}
[data-testid="stSidebar"] h1 {{ color: #fff; font-size: 1.15rem !important; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ color: #94A3B8 !important; }}
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 4px; }}
[data-testid="stSidebar"] [data-testid="stElementContainer"] {{ width: 100% !important; }}
[data-testid="stSidebar"] [role="radiogroup"] > div {{
    position: relative; padding: 9px 12px; border-radius: 10px; margin: 0 !important; width: 100%;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"] {{ position: static; width: 100%; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"]::after {{ content: ""; position: absolute; inset: 0; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {{ display: none !important; }}
[data-testid="stSidebar"] [role="radiogroup"] > div:hover {{ background: rgba(255,255,255,.06); }}
[data-testid="stSidebar"] [role="radiogroup"] > div[data-selected="true"] {{ background: var(--ak-p-anillo); }}
[data-testid="stSidebar"] [role="radiogroup"] > div[data-selected="true"] p {{ color: var(--ak-p-brillante) !important; font-weight: 700; }}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
    background: rgba(255,255,255,.06) !important; border-color: rgba(255,255,255,.12) !important; color: #E2E8F0 !important;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{
    background: rgba(255,255,255,.05) !important; border: 1px solid rgba(255,255,255,.16) !important; border-radius: 12px;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary * {{ color: #FFFFFF !important; font-weight: 700; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {{ background: rgba(255,255,255,.06); }}
/* Cuadro del link para pacientes: fondo oscuro, texto verde brillante */
[data-testid="stSidebar"] [data-testid="stCode"],
[data-testid="stSidebar"] [data-testid="stCode"] > div,
[data-testid="stSidebar"] [data-testid="stCode"] pre {{
    background: #020617 !important; border-radius: 10px !important;
}}
[data-testid="stSidebar"] [data-testid="stCode"] pre {{
    border: 1.5px solid var(--ak-p-medio) !important; padding: 12px 44px 12px 12px !important;
}}
[data-testid="stSidebar"] [data-testid="stCode"] code,
[data-testid="stSidebar"] [data-testid="stCode"] code * {{
    color: var(--ak-p-brillante) !important; background: transparent !important; font-weight: 600;
    white-space: pre-wrap !important; word-break: break-all !important; font-size: .82rem !important;
}}
[data-testid="stSidebar"] [data-testid="stCode"] button {{
    opacity: 1 !important; visibility: visible !important; background: var(--ak-p-medio) !important;
    border: none !important; border-radius: 8px !important; color: #04201D !important;
}}
[data-testid="stSidebar"] [data-testid="stCode"] button * {{ color: #04201D !important; fill: #04201D !important; }}
[data-testid="stSidebar"] .ak-link-ayuda {{ color: #CBD5E1 !important; font-size: .82rem; margin: 2px 0 8px; }}

/* Componentes propios (HTML) */
.ak-barra {{
    background: {NAVY}; color: #CBD5E1; border-radius: 16px; padding: 10px 16px; margin-bottom: 14px;
    display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; justify-content: space-between; font-size: .85rem;
}}
.ak-barra b {{ color: #fff; }}
.ak-pill {{
    display: inline-block; background: rgba(20,184,166,.18); color: #5EEAD4; border: 1px solid rgba(94,234,212,.35);
    border-radius: 999px; padding: 2px 10px; font-weight: 800; font-size: .72rem; letter-spacing: .06em; margin-right: 8px;
}}
.ak-plan {{ color: #94A3B8; }} .ak-plan b {{ color: #5EEAD4; }}
.ak-header {{
    display: flex; align-items: center; gap: 16px; background: #fff; border: 1px solid {BORDE};
    border-radius: 20px; padding: 14px 18px; margin-bottom: 18px;
}}
.ak-logo {{ width: 60px; height: 60px; border-radius: 16px; object-fit: contain; background: #fff; border: 1px solid {BORDE}; }}
.ak-logo-ph {{
    width: 60px; height: 60px; border-radius: 16px; display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, var(--ak-p) 0%, var(--ak-p-medio) 100%); font-size: 30px;
}}
.ak-nombre {{ font-size: 1.35rem; font-weight: 800; color: {TEXTO}; line-height: 1.15; letter-spacing: -0.02em; }}
.ak-sub {{ color: {TEXTO_SUAVE}; font-size: .88rem; margin-top: 2px; }}
.ak-kicker {{
    display: inline-block; background: var(--ak-p-claro); color: var(--ak-p); border: 1px solid var(--ak-p-borde);
    border-radius: 999px; padding: 3px 12px; font-size: .72rem; font-weight: 800; letter-spacing: .08em;
}}
.ak-titulo {{ font-size: 1.75rem; font-weight: 800; color: {TEXTO}; margin: 10px 0 2px; letter-spacing: -0.02em; }}
.ak-desc {{ color: {TEXTO_SUAVE}; margin-bottom: 6px; }}
.ak-sep {{ height: 1px; background: {BORDE}; margin: 14px 0 6px; }}
.ak-paso {{ display: flex; align-items: center; gap: 10px; font-weight: 700; color: {TEXTO}; margin: 18px 0 8px; }}
.ak-num {{
    width: 26px; height: 26px; border-radius: 999px; background: var(--ak-p); color: var(--ak-p-texto); display: inline-flex;
    align-items: center; justify-content: center; font-size: .8rem; font-weight: 800; flex: none;
}}
.ak-kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 14px; margin: 4px 0 18px; }}
@media (max-width: 820px) {{ .ak-kpis {{ grid-template-columns: repeat(2, minmax(0,1fr)); }} }}
.ak-kpi {{
    background: #fff; border: 1px solid {BORDE}; border-radius: 18px; padding: 14px 16px;
    display: flex; gap: 12px; align-items: center; box-shadow: 0 6px 18px -14px rgba(15,23,42,.3);
}}
.ak-kpi-ico {{ width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; flex: none; }}
.ak-kpi-lbl {{ color: {TEXTO_SUAVE}; font-size: .8rem; font-weight: 600; line-height: 1.2; }}
.ak-kpi-val {{ color: {TEXTO}; font-size: 1.4rem; font-weight: 800; line-height: 1.2; }}
.ak-chip {{ display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: .75rem; font-weight: 700; }}
.ak-cita-hora {{ font-size: 1.05rem; font-weight: 800; color: {TEXTO}; }}
.ak-cita-linea {{ color: {TEXTO_SUAVE}; font-size: .9rem; margin-top: 2px; }}
.ak-cita-linea b {{ color: {TEXTO}; font-weight: 600; }}
.ak-pie {{ text-align: center; color: #94A3B8; font-size: .8rem; margin-top: 28px; }}
.ak-pie b {{ color: var(--ak-p); }}
.ak-landing {{
    background: linear-gradient(135deg, {NAVY} 0%, #0F2A3D 60%, var(--ak-p) 140%); color: #E2E8F0;
    border-radius: 24px; padding: 48px 36px; margin-top: 10px;
}}
.ak-landing h1 {{ color: #fff !important; font-size: 2.4rem; margin: 10px 0 6px; }}
.ak-landing p {{ color: #CBD5E1; font-size: 1.05rem; max-width: 640px; }}
.ak-feats {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 14px; margin-top: 18px; }}
@media (max-width: 820px) {{ .ak-feats {{ grid-template-columns: 1fr; }} }}
.ak-feat {{ background: #fff; border: 1px solid {BORDE}; border-radius: 18px; padding: 18px; }}
.ak-feat b {{ color: {TEXTO}; display: block; margin: 6px 0 4px; }}
.ak-feat span {{ color: {TEXTO_SUAVE}; font-size: .9rem; }}
</style>
"""


def _h(texto):
    return html.escape(str(texto or ""))


def _html(contenido):
    st.markdown(contenido, unsafe_allow_html=True)


def _hex_a_rgb(h):
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_a_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def _mezclar(rgb, con, t):
    """Mezcla el color con otro (t=0 -> igual, t=1 -> el otro)."""
    return tuple(a + (b - a) * t for a, b in zip(rgb, con))


def _luminancia(rgb):
    def canal(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def color_valido(h):
    try:
        _hex_a_rgb(h)
        return len((h or "").lstrip("#")) in (3, 6)
    except ValueError:
        return False


def _brillante(rgb):
    """Version clara del color que se lea bien sobre el menu lateral oscuro."""
    t = 0.35
    while _luminancia(_mezclar(rgb, (255, 255, 255), t)) < 0.5 and t < 0.9:
        t += 0.05
    return _mezclar(rgb, (255, 255, 255), t)


def paleta(color):
    """A partir del color de marca de la clinica calcula todos los tonos que
    usa el diseno (claro, borde, oscuro, brillante para el menu oscuro...) y
    el color de texto que mejor se lee encima (blanco o casi negro)."""
    if not color_valido(color):
        color = COLOR_PREDETERMINADO
    rgb = _hex_a_rgb(color)
    blanco, negro = (255, 255, 255), (0, 0, 0)
    texto = "#FFFFFF" if _luminancia(rgb) < 0.45 else "#0F172A"
    r, g, b = rgb
    return {
        "p": _rgb_a_hex(rgb),
        "oscuro": _rgb_a_hex(_mezclar(rgb, negro, 0.22)),
        "medio": _rgb_a_hex(_mezclar(rgb, blanco, 0.25)),
        "claro": _rgb_a_hex(_mezclar(rgb, blanco, 0.93)),
        "borde": _rgb_a_hex(_mezclar(rgb, blanco, 0.6)),
        "brillante": _rgb_a_hex(_brillante(rgb)),
        "anillo": f"rgba({r},{g},{b},.18)",
        "sombra": f"rgba({r},{g},{b},.45)",
        "texto": texto,
    }


def inyectar_estilos(color=None):
    t = paleta(color)
    variables = "".join(f"--ak-{'p' if k == 'p' else 'p-' + k}: {v};" for k, v in t.items())
    _html(f"<style>:root {{ {variables} }}</style>" + _CSS)


def barra_plataforma(es_demo):
    if es_demo:
        _html(
            '<div class="ak-barra"><div><span class="ak-pill">DEMO</span>'
            'Plataforma de agenda para clínicas y consultorios · Powered by <b>Aika Solutions</b></div>'
            '<div class="ak-plan">Plan activo: <b>Demo Enterprise</b></div></div>'
        )


def encabezado_negocio(negocio, subtitulo, icono):
    if negocio.get("logo_base64"):
        logo = f'<img class="ak-logo" src="data:image/png;base64,{negocio["logo_base64"]}" alt="logo">'
    else:
        logo = f'<div class="ak-logo-ph">{icono}</div>'
    _html(
        f'<div class="ak-header">{logo}<div><div class="ak-nombre">{_h(negocio["nombre"])}</div>'
        f'<div class="ak-sub">{_h(subtitulo)}</div></div></div>'
    )


def titulo_seccion(kicker, titulo, descripcion=""):
    desc = f'<div class="ak-desc">{_h(descripcion)}</div>' if descripcion else ""
    _html(f'<span class="ak-kicker">{_h(kicker)}</span><div class="ak-titulo">{_h(titulo)}</div>{desc}'
          '<div class="ak-sep"></div>')


def paso(numero, texto):
    _html(f'<div class="ak-paso"><span class="ak-num">{numero}</span>{_h(texto)}</div>')


def kpis(items):
    """items: lista de (icono, etiqueta, valor, color_fondo, color_icono)."""
    tarjetas = "".join(
        f'<div class="ak-kpi"><div class="ak-kpi-ico" style="background:{fondo};color:{color}">{icono}</div>'
        f'<div><div class="ak-kpi-lbl">{_h(etq)}</div><div class="ak-kpi-val">{_h(val)}</div></div></div>'
        for icono, etq, val, fondo, color in items
    )
    _html(f'<div class="ak-kpis">{tarjetas}</div>')


def chip_estado(estado):
    fondo, color, texto = _CHIP_ESTADO.get(estado, ("#F1F5F9", "#475569", estado))
    return f'<span class="ak-chip" style="background:{fondo};color:{color}">{_h(texto)}</span>'


def tarjeta_cita_html(c, etiqueta_cliente):
    tel = c.get("cliente_telefono") or "sin teléfono"
    return (
        f'<div class="ak-cita-hora">{_h(c["hora_inicio"])} – {_h(c["hora_fin"])} &nbsp;{chip_estado(c["estado"])}</div>'
        f'<div class="ak-cita-linea">{_h(etiqueta_cliente)}: <b>{_h(c["cliente_nombre"])}</b> · {_h(tel)}</div>'
        f'<div class="ak-cita-linea">{_h(c["servicio_nombre"])} · con <b>{_h(c["proveedor_nombre"])}</b></div>'
    )


def pie():
    _html('<div class="ak-pie">Agenda en línea · Powered by <b>Aika Solutions</b></div>')


def portada_plataforma():
    _html(
        '<div class="ak-landing"><span class="ak-pill">AIKA SOLUTIONS</span>'
        '<h1>Agenda de citas en línea para tu clínica</h1>'
        '<p>Tus pacientes reservan solos, 24/7, viendo solo horarios realmente disponibles. '
        'Tú controlas agenda, especialistas, servicios y ganancias desde un panel privado.</p></div>'
        '<div class="ak-feats">'
        '<div class="ak-feat">📅<b>Reservas en línea</b><span>Link propio para que tus pacientes agenden sin llamar.</span></div>'
        '<div class="ak-feat">🧑‍⚕️<b>Agenda por especialista</b><span>Sin empalmes, con horario de comida y días laborales.</span></div>'
        '<div class="ak-feat">📊<b>Estadísticas</b><span>Ingresos, cancelaciones e inasistencias por periodo.</span></div>'
        '</div>'
    )
    _html('<div class="ak-pie">¿Te compartieron el link de tu clínica? Revisa que esté completo: '
          'termina en algo como <code>?negocio=nombre</code>.</div>')
