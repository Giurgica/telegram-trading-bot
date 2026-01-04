import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from huggingface_hub import InferenceClient

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
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

# Inizializza Hugging Face client
if HF_TOKEN:
    hf_client = InferenceClient(model="facebook/bart-large-cnn", token=HF_TOKEN)
else:
    hf_client = None
    logger.warning("Avviso: HF_TOKEN non impostato. AI disabilitato.")

def genera_riassunto_ai(testo):
    """Genera un vero riassunto usando Hugging Face AI."""
    if not hf_client:
        return None
    try:
        summary = hf_client.summarization(
            testo,
            parameters={"min_length": 30, "max_length": 80, "do_sample": False}
        )
        return summary.summary_text if hasattr(summary, 'summary_text') else str(summary)
    except Exception as e:
        logger.error(f"Errore HF AI: {e}")
        return None

async def gestisci_messaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia SUBITO ogni messaggio con riassunti REALI via AI."""
    
    if update.effective_chat.id != SOURCE_GROUP_ID:
        return
    
    if not update.message or not update.message.text:
        return
    
    original_text = update.message.text
    user = update.message.from_user.first_name or "Utente"
    
    # RILEVAMENTO LIVE ON AIR
    text_upper = original_text.upper()
    keywords_live = ["LIVE ON AIR", "IN DIRETTA", "🔴"]
    keywords_link = ["HTTP", "ZOOM", "YOUTUBE", "MEET"]
    
    is_live = any(k in text_upper for k in keywords_live)
    has_link = any(k in text_upper for k in keywords_link)
    
    if is_live and has_link:
        messaggio_live = (
            f"ATTENZIONE: DIRETTA SPECIALE APPENA INIZIATA 🚨\n\n"
            f"Sta partendo ORA una sessione cruciale per chi vuole portare il proprio trading a un livello superiore.\n"
            f"Registrati subito per entrare nel canale esclusivo e seguire la diretta in tempo reale, senza perdere nemmeno un contenuto operativo.\n\n"
            f"🔗 Unisciti ora: @The_Edge_Lab_Italia"
        )
        try:
            await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=messaggio_live)
            logger.info("LIVE rilevata: messaggio incentivo inviato")
        except Exception as e:
            logger.error(f"Errore invio LIVE: {e}")
        return
    
    # MESSAGGI LUNGHI: USA HUGGING FACE PER VERI RIASSUNTI
    if len(original_text) > 100:
        logger.info(f"Messaggio lungo ({len(original_text)} chars). Generando riassunto AI...")
        loop = asyncio.get_running_loop()
        riassunto = await loop.run_in_executor(None, genera_riassunto_ai, original_text)
        
        if riassunto:
            messaggio_finale = (
                f"📝 **Riassunto da {user}:**\n"
                f"{riassunto}\n\n"
                f"🔍 Per l'analisi completa e i livelli chiave → @The_Edge_Lab_Italia"
            )
        else:
            # Fallback se AI fallisce
            messaggio_finale = f"👤 **{user}:** {original_text}"
    else:
        # Messaggi brevi: invia diretto
        messaggio_finale = f"👤 **{user}:** {original_text}"
    
    # INVIA AL GRUPPO TARGET
    try:
        await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=messaggio_finale)
        logger.info(f"Messaggio inoltrato da {user}")
    except Exception as e:
        logger.error(f"Errore nell'invio: {e}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), gestisci_messaggio)
    application.add_handler(msg_handler)
    logger.info("Bot ISTANTANEO con AI VERI riassunti avviato. In ascolto...")
    application.run_polling()
