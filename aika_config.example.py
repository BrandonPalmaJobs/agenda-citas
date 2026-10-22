"""
Configuracion privada de Aika Solutions (copia este archivo como
aika_config.py y llenalo; aika_config.py NO se sube a GitHub).

Sirve para que nuevo_cliente.py cree la base de datos de cada cliente nuevo
en Turso automaticamente. Si lo dejas vacio, el script te pide pegar la URL y
el token de una base creada a mano.

Como sacar estos datos (una sola vez):
1. Entra a https://app.turso.tech
2. Tu organizacion: es el nombre que sale arriba a la izquierda (tambien
   aparece en las URL de tus bases: libsql://<base>-<ORGANIZACION>.turso.io).
3. Token de API: Settings -> API Tokens -> Create API Token. Copialo.
"""

TURSO_API_TOKEN = ""
TURSO_ORGANIZACION = ""   # ej. "brandonpalmajobs"
TURSO_GRUPO = "default"
