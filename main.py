import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import google.generativeai as genai
from PIL import Image
import io

# --- CONFIGURAZIONE LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURAZIONE VARIABILI D'AMBIENTE ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ID dei Gruppi (assicurati che siano interi, es: -100123456789)
try:
    SOURCE_GROUP_ID = int(os.getenv("SOURCE_GROUP_ID"))
    DEST_GROUP_ID = int(os.getenv("DEST_GROUP_ID"))
except (TypeError, ValueError):
    logger.error("ERRORE: SOURCE_GROUP_ID o DEST_GROUP_ID non impostati o non validi.")
    exit(1)

# --- CONFIGURAZIONE GEMINI AI ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# --- KEYWORDS PER LIVE DETECTION ---
LIVE_KEYWORDS = ["LIVE", "iPhone", "diretta", "streaming", "in onda"]

# --- FUNZIONI UTILI ---
def is_live_content(text: str) -> bool:
    """Controlla se il testo contiene parole chiave LIVE."""
    if not text:
        return False
    return any(keyword.lower() in text.lower() for keyword in LIVE_KEYWORDS)

async def generate_summary(content_parts):
    """Chiama Gemini per generare il riassunto."""
    try:
        prompt_base = (
            "Sei un assistente per una radio. Analizza il contenuto fornito (testo ed eventuale immagine). "
            "Se c'e' un'immagine con testo, trascrivilo mentalmente e usalo per il contesto (OCR). "
            "Genera un riassunto IMPERSONALE (senza citare nomi utenti), BREVE e CONCISO (tra 30 e 50 parole). "
            "Vai dritto al punto. NON INCLUDERE LINK."
        )
        input_data = [prompt_base] + content_parts
        response = await asyncio.to_thread(
            model.generate_content, input_data, safety_settings=safety_settings
        )
        return response.text
    except Exception as e:
        logger.error(f"Errore Gemini: {e}")
        return None

# --- HANDLERS TELEGRAM ---
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce sia messaggi di testo che foto."""
    # 1. Filtro Gruppo: Ignora messaggi che non vengono dal SOURCE_GROUP
    if update.effective_chat.id != SOURCE_GROUP_ID:
        return
    
    message = update.message
    if not message:
        return
    
    text_content = message.text or message.caption or ""
    image_data = None
    
    # 2. LIVE DETECTION (Priorita' assoluta)
    if is_live_content(text_content):
        alert_msg = "🔴 LIVE IN CORSO! Stai perdendo la diretta. Contatta @The_Edge_Lab_Italia in privato per aggiornamenti."
        await context.bot.send_message(chat_id=DEST_GROUP_ID, text=alert_msg)
        logger.info("Messaggio LIVE rilevato e notificato.")
        return  # Stop qui, non riassumere le live
    
    # 3. Gestione Foto (Download e preparazione per Gemini)
    if message.photo:
        try:
            # Prende la foto a piu' alta risoluzione
            photo_file = await message.photo[-1].get_file()
            img_bytes = await photo_file.download_as_bytearray()
            image_data = Image.open(io.BytesIO(img_bytes))
        except Exception as e:
            logger.error(f"Errore download foto: {e}")
    
    # Se fallisce la foto, proviamo a processare solo il testo se esiste
    if not text_content:
        return
    
    # 4. Preparazione Payload per Gemini
    gemini_input = []
    if text_content:
        gemini_input.append(f"Testo messaggio: {text_content}")
    if image_data:
        gemini_input.append(image_data)
    
    if not gemini_input:
        return
    
    # 5. Generazione Riassunto
    summary = await generate_summary(gemini_input)
    
    # 6. Invio al Gruppo Destinazione
    if summary:
        try:
            await context.bot.send_message(chat_id=DEST_GROUP_ID, text=summary)
            logger.info("Riassunto inviato con successo.")
        except Exception as e:
            logger.error(f"Errore invio Telegram: {e}")

# --- MAIN LOOP ---
if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        logger.error("Token Telegram mancante!")
        exit(1)
    
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Gestisce testo e foto nel gruppo
    handler = MessageHandler(filters.CHAT & (filters.TEXT | filters.PHOTO), process_message)
    application.add_handler(handler)
    
    logger.info("Bot avviato e in ascolto sul GRUPPO PRINCIPALE...")
    
    # Esecuzione
    application.run_polling()
