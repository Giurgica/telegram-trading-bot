import os
import logging
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# --- CONFIGURAZIONE LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- RECUPERO VARIABILI DA ENVIRONMENT ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TARGET_GROUP_ID = os.getenv("TARGET_GROUP_ID")
SOURCE_GROUP_ID = os.getenv("SOURCE_GROUP_ID")

if not TELEGRAM_TOKEN or not TARGET_GROUP_ID or not SOURCE_GROUP_ID:
    logger.error("ERRORE: Mancano le Environment Variables")
    exit(1)

try:
    TARGET_GROUP_ID = int(TARGET_GROUP_ID)
    SOURCE_GROUP_ID = int(SOURCE_GROUP_ID)
except ValueError:
    logger.error("ERRORE: Gli ID devono essere numeri interi.")
    exit(1)

async def invia_messaggio_istantaneo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia SUBITO ogni messaggio del gruppo source al grupo target."""
    
    # Ignora messaggi non dal gruppo sorgente
    if update.effective_chat.id != SOURCE_GROUP_ID:
        return
    
    # Ignora messaggi senza testo (foto, video, ecc)
    if not update.message or not update.message.text:
        return
    
    user = update.message.from_user.first_name or "Utente"
    text = update.message.text
    
    # Timestamp italiano
    tz_ita = pytz.timezone('Europe/Rome')
    ora = datetime.now(tz_ita).strftime("%H:%M:%S")
    
    # Formatta il messaggio: [HH:MM:SS] User: messaggio
    messaggio_formattato = f"[{ora}] **{user}**: {text}"
    
    try:
        # Invia SUBITO al gruppo target
        await context.bot.send_message(
            chat_id=TARGET_GROUP_ID,
            text=messaggio_formattato,
            parse_mode='Markdown'
        )
        logger.info(f"Messaggio inviato da {user} alle {ora}")
    except Exception as e:
        logger.error(f"Errore nell'invio: {e}")

if __name__ == '__main__':
    # Crea l'applicazione Telegram
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Handler per i messaggi - INVIA SUBITO
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), invia_messaggio_istantaneo)
    application.add_handler(msg_handler)
    
    logger.info("Bot avviato. In ascolto ISTANTANEO...")
    application.run_polling()
