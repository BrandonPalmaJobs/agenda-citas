# Bot de WhatsApp de Aika Citas

Servidor pequeño (Vercel, gratis) que recibe los mensajes de WhatsApp:
- Botones del recordatorio: **Confirmo** / **Necesito cancelar**.
- Menú para **agendar**, ver **mis citas** y **cancelar**.

Se publica en Vercel con *Root Directory* = `bot`. Variables de entorno:
`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`,
`REGISTRO_TURSO_URL`, `REGISTRO_TURSO_TOKEN`, `BOT_CLINICA` (ej. `demo`).
Webhook para Meta: `https://<tu-proyecto>.vercel.app/webhook`.
