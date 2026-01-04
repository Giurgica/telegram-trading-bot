import os
import logging
import asyncio
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from huggingface_hub import InferenceClient

# --- CONFIGURAZIONE LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- RECUPERO VARIABILI DA ENVIRONMENT ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
TARGET_GROUP_ID = os.getenv("TARGET_GROUP_ID")
SOURCE_GROUP_ID = os.getenv("SOURCE_GROUP_ID")

if not TELEGRAM_TOKEN or not TARGET_GROUP_ID or not SOURCE_GROUP_ID:
    logger.error("ERRORE: Mancano le Environment Variables")
    exit(1)

if not HF_TOKEN:
    logger.warning("ATTENZIONE: HF_TOKEN non configurato. AI disabilitata.")

try:
    TARGET_GROUP_ID = int(TARGET_GROUP_ID)
    SOURCE_GROUP_ID = int(SOURCE_GROUP_ID)
except ValueError:
    logger.error("ERRORE: Gli ID devono essere numeri interi.")
    exit(1)

# --- INIZIALIZZA CLIENT HUGGING FACE ---
if HF_TOKEN:
    try:
        hf_client = InferenceClient(model="facebook/bart-large-cnn", token=HF_TOKEN)
    except Exception as e:
        logger.error(f"Errore inizializzazione HF: {e}")
        hf_client = None
else:
    hf_client = None

# --- FUNZIONE 1: RIASSUNTO AI ---
def genera_riassunto_ai(testo):
    """Chiama l'API gratuita di Hugging Face per riassumere."""
    if not hf_client:
        return None
    try:
        summary = hf_client.summarization(
            testo,
            parameters={"min_length": 20, "max_length": 60, "do_sample": False}
        )
        return summary.summary_text if hasattr(summary, 'summary_text') else str(summary)
    except Exception as e:
        logger.error(f"Errore AI Hugging Face: {e}")
        return None

# --- FUNZIONE 2: RILEVAMENTO LIVE ON AIR ---
def rilevamento_live_on_air(testo):
    """Controlla se il messaggio contiene LIVE ON AIR e un link."""
    text_upper = testo.upper()
    keywords_live = ["LIVE ON AIR", "IN DIRETTA", "🔴"]
    keywords_link = ["HTTP", "ZOOM", "YOUTUBE", "MEET"]
    
    is_live = any(k in text_upper for k in keywords_live)
    has_link = any(k in text_upper for k in keywords_link)
    
    return is_live and has_link

def estrai_link(testo):
    """Estrae il primo link trovato nel testo."""
    words = testo.split()
    for word in words:
        if word.startswith("http://") or word.startswith("https://"):
            return word
    return "il link inviato"

# --- HANDLER PRINCIPALE ---
async def gestisci_messaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i messaggi con riassunto AI e rilevamento LIVE."""
    
    # Ignora messaggi non dal gruppo sorgente
    if update.effective_chat.id != SOURCE_GROUP_ID:
        return
    
    # Ignora messaggi senza testo
    if not update.message or not update.message.text:
        return
    
    original_text = update.message.text
    user = update.message.from_user.first_name or "Utente"
    
    # --- FUNZIONE 2: TRIGGER LIVE ON AIR ---
    if rilevamento_live_on_air(original_text):
        link_trovato = estrai_link(original_text)
        messaggio_hype = (
            f"🚨 **ATTENZIONE: DIRETTA SPECIALE!**\n\n"
            f"È appena iniziata una sessione fondamentale.\n"
            f"🔔 **REGISTRATI ORA** per accedere al canale esclusivo e non perdere i contenuti!\n\n"
            f"👉 **CLICCA QUI PER ENTRARE:** {link_trovato}\n\n"
            f"_(Accesso limitato a chi aderisce ora!)_"
        )
        
        try:
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=messaggio_hype,
                parse_mode='Markdown'
            )
            logger.info("Rilevata LIVE: Inviato messaggio Hype.")
        except Exception as e:
            logger.error(f"Errore invio messaggio LIVE: {e}")
        
        return  # Non inviamo altro per i messaggi LIVE
    
    # --- FUNZIONE 1: RIASSUNTO AI ---
    if len(original_text) > 100:
        logger.info(f"Messaggio lungo ({len(original_text)} chars). Tentativo riassunto AI...")
        
        # Esegui la chiamata AI in thread separato
        loop = asyncio.get_running_loop()
        riassunto = await loop.run_in_executor(None, genera_riassunto_ai, original_text)
        
        if riassunto:
            messaggio_finale = (
                f"📝 **Sintesi da {user}:**\n"
                f"{riassunto}\n\n"
                f"🔍 _(Messaggio originale ridotto da AI)_"
            )
        else:
            # Fallback: Se AI fallisce, manda l'originale
            messaggio_finale = f"👤 **{user}:**\n{original_text}"
    else:
        # Messaggio breve: Invia diretto
        messaggio_finale = f"👤 **{user}:** {original_text}"
    
    # --- INVIO AL GRUPPO TARGET ---
    try:
        await context.bot.send_message(
            chat_id=TARGET_GROUP_ID,
            text=messaggio_finale
        )
        logger.info(f"Messaggio inoltrato da {user}")
    except Exception as e:
        logger.error(f"Errore nell'invio: {e}")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        logger.error("Errore: Manca TELEGRAM_TOKEN")
        exit(1)
    
    # Crea l'applicazione Telegram
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Handler per i messaggi
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), gestisci_messaggio)
    application.add_handler(msg_handler)
    
    logger.info("Bot avviato con AI Hugging Face. In ascolto...")
    application.run_polling()
