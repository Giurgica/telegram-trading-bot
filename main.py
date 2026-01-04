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
    logger.error("ERRORE: Mancano le Environment Variables (TELEGRAM_TOKEN, TARGET_GROUP_ID, SOURCE_GROUP_ID)")
    exit(1)

try:
    TARGET_GROUP_ID = int(TARGET_GROUP_ID)
    SOURCE_GROUP_ID = int(SOURCE_GROUP_ID)
except ValueError:
    logger.error("ERRORE: Gli ID dei gruppi devono essere numeri interi.")
    exit(1)

# Lista per accumulare i messaggi
messaggi_accumulati = []

async def raccogli_messaggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Raccoglie i messaggi dal gruppo sorgente."""
    global messaggi_accumulati
    
    if update.effective_chat.id != SOURCE_GROUP_ID:
        return
    
    if update.message and update.message.text:
        user = update.message.from_user.first_name or "Utente"
        text = update.message.text
        
        # Formatta: [10:30] Mario: Testo del messaggio
        ora = datetime.now(pytz.timezone('Europe/Rome')).strftime("%H:%M")
        entry = f"[{ora}] **{user}**: {text}"
        messaggi_accumulati.append(entry)
        logger.info(f"Messaggio salvato da {user}")

async def invia_log_periodico(context: ContextTypes.DEFAULT_TYPE):
    """Invia i messaggi accumulati al gruppo target."""
    global messaggi_accumulati
    
    if not messaggi_accumulati:
        return
    
    logger.info(f"Invio di {len(messaggi_accumulati)} messaggi al gruppo target...")
    
    # Crea header con timestamp
    tz_ita = pytz.timezone('Europe/Rome')
    ora_corrente = datetime.now(tz_ita).strftime("%d/%m/%Y %H:%M")
    header = f"📋 **LOG ORARIO - {ora_corrente}**\n\n"
    
    # Unisci tutti i messaggi
    full_text = header + "\n".join(messaggi_accumulati)
    
    # Svuota la lista
    messaggi_accumulati = []
    
    # --- LOGICA ANTI-CRASH: SPLITTING ---
    # Telegram ha un limite di 4096 caratteri per messaggio
    MAX_LENGTH = 4000
    chunks = [full_text[i:i+MAX_LENGTH] for i in range(0, len(full_text), MAX_LENGTH)]
    
    # Invia ogni chunk
    for i, chunk in enumerate(chunks):
        try:
            if len(chunks) > 1:
                footer = f"\n\n_{i+1}/{len(chunks)}_"
                msg_to_send = chunk + footer
            else:
                msg_to_send = chunk
            
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=msg_to_send,
                parse_mode='Markdown'
            )
            logger.info(f"Messaggio inviato (parte {i+1}/{len(chunks)})")
        except Exception as e:
            logger.error(f"Errore nell'invio: {e}")

if __name__ == '__main__':
    # Crea l'applicazione
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Aggiungi handler per i messaggi
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), raccogli_messaggi)
    application.add_handler(msg_handler)
    
    # Imposta il timer per l'invio periodico
    job_queue = application.job_queue
    job_queue.run_repeating(invia_log_periodico, interval=3600, first=3600)
    
    logger.info("Bot avviato. In ascolto dei messaggi...")
    application.run_polling()
