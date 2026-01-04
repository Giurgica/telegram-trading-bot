import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import AsyncOpenAI

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
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

# Inizializza OpenAI client
if OPENAI_API_KEY:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None
    logger.warning("Avviso: OPENAI_API_KEY non impostato. AI disabilitato.")

def genera_riassunto_ai(testo):
    """Genera un vero riassunto usando OpenAI GPT."""
    if not openai_client:
        return None
    try:
        # Prompt intelligente per riassunti brevi e profondi
        prompt = f"""Riassumi il seguente testo in modo BREVE ma PROFONDO. Usa max 50 parole. 
Va bene usare abbreviazioni e punti chiave. Salta dettagli superflui.
Testo: {testo}

Riassunto:"""
        # Questo sarà fatto con await in una funzione async
        return prompt
    except Exception as e:
        logger.error(f"Errore generazione prompt: {e}")
        return None

async def genera_riassunto_ai_async(testo):
    """Genera un vero riassunto usando OpenAI GPT (versione async)."""
    if not openai_client:
        return None
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Sei un esperto di sintesi. Riassumi sempre in modo BREVE e PROFONDO, massimo 50 parole. Usa punti chiave e abbreviazioni."},
                {"role": "user", "content": f"Riassumi questo:\n{testo}"}
            ],
            max_tokens=100,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Errore OpenAI AI: {e}")
        return None

async def gestisci_messaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia SUBITO ogni messaggio con riassunti REALI via OpenAI."""
    
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
    
    # MESSAGGI LUNGHI: USA OPENAI PER VERI RIASSUNTI
    if len(original_text) > 100:
        logger.info(f"Messaggio lungo ({len(original_text)} chars). Generando riassunto AI...")
        riassunto = await genera_riassunto_ai_async(original_text)
        
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
    logger.info("Bot ISTANTANEO con AI VERI riassunti (OpenAI) avviato. In ascolto...")
    application.run_polling()
