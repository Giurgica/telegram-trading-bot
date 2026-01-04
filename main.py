import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

async def gestisci_messaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia SUBITO ogni messaggio dal gruppo sorgente al target."""
    
    if update.effective_chat.id != SOURCE_GROUP_ID:
        return
    
    if not update.message or not update.message.text:
        return
    
    original_text = update.message.text
    user = update.message.from_user.first_name or "Utente"
    
    # RILEVAMENTO LIVE ON AIR CON LINK
    text_upper = original_text.upper()
    keywords_live = ["LIVE ON AIR", "IN DIRETTA", "🔴"]
    keywords_link = ["HTTP", "ZOOM", "YOUTUBE", "MEET"]
    
    is_live = any(k in text_upper for k in keywords_live)
    has_link = any(k in text_upper for k in keywords_link)
    
    if is_live and has_link:
        # Messaggio personalizzato di incentivo per LIVE
        messaggio_live = (
            f"ATTENZIONE: DIRETTA SPECIALE APPENA INIZIATA 🚨\n\n"
            f"Sta partendo ORA una sessione cruciale per chi vuole portare il proprio trading a un livello superiore.\n"
            f"Registrati subito per entrare nel canale esclusivo e seguire la diretta in tempo reale, senza perdere nemmeno un contenuto operativo.\n\n"
            f"🔗 Unisciti ora: @The_Edge_Lab_Italia"
        )
        try:
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=messaggio_live
            )
            logger.info("LIVE rilevata: messaggio incentivo inviato ISTANTANEAMENTE")
        except Exception as e:
            logger.error(f"Errore invio LIVE: {e}")
        return
    
    # INOLTRO ISTANTANEO per messaggi normali
    messaggio_formattato = f"👤 **{user}**: {original_text}"
    
    try:
        await context.bot.send_message(
            chat_id=TARGET_GROUP_ID,
            text=messaggio_formattato
        )
        logger.info(f"Messaggio inoltrato ISTANTANEAMENTE da {user}")
    except Exception as e:
        logger.error(f"Errore nell'invio: {e}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), gestisci_messaggio)
    application.add_handler(msg_handler)
    logger.info("Bot ISTANTANEO avviato. In ascolto...")
    application.run_polling()
