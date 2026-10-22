"""
Reglas de la suscripcion de cada negocio (prueba gratis / pagada / suspendida).

Los datos viven en la tabla negocio de CADA clinica (plan, vence_el,
precio_mensual) y los administra Aika Solutions desde su panel
(?panel=admin). Aqui solo se decide, con esos datos, si la agenda esta
abierta o bloqueada y que aviso mostrar.

  plan vacio / 'demo'  -> nunca se bloquea (la demo y negocios antiguos)
  'prueba' / 'activa'  -> abierta hasta vence_el (inclusive); despues, bloqueada
  'suspendida'         -> bloqueada sin importar la fecha
"""

from datetime import date

PLANES = {
    "demo": "Demo",
    "prueba": "Prueba gratis",
    "activa": "Suscripción activa",
    "suspendida": "Suspendida",
}
DIAS_PRUEBA = 14
DIAS_AVISO = 5  # desde cuantos dias antes se le avisa al negocio en su panel


def _fecha(texto):
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def estado(negocio, hoy):
    """Regresa un dict con:
        bloqueado (bool), plan, vence (date|None), dias_restantes (int|None),
        aviso (texto para el panel del negocio, o None),
        motivo ('vencida' | 'suspendida' | None)
    """
    plan = (negocio or {}).get("plan") or ""
    vence = _fecha((negocio or {}).get("vence_el"))
    dias = (vence - hoy).days if vence else None
    resultado = {"bloqueado": False, "plan": plan, "vence": vence, "dias_restantes": dias,
                 "aviso": None, "motivo": None}

    if plan == "suspendida":
        resultado.update(bloqueado=True, motivo="suspendida")
        return resultado
    if plan in ("", "demo") or vence is None:
        return resultado
    if dias < 0:
        resultado.update(bloqueado=True, motivo="vencida")
        return resultado
    if dias <= DIAS_AVISO:
        que = "Tu prueba gratis" if plan == "prueba" else "Tu suscripción"
        cuando = "hoy" if dias == 0 else ("mañana" if dias == 1 else f"en {dias} días")
        resultado["aviso"] = (f"{que} termina {cuando} ({vence.strftime('%d/%m/%Y')}). "
                              "Contacta a Aika Solutions para continuar sin interrupciones.")
    return resultado


def etiqueta_plan(plan):
    return PLANES.get(plan or "", "Sin plan (no vence)")
