import os
import logging
import asyncio
from typing import Optional
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("OPENAI_API_KEY")  # Usa la chiave Google (rinominata da OPENAI_API_KEY per compatibilità)
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

# --- SERVIZIO AI (Nativo Google Gemini) ---
class AIService:
    """Gestisce l'interazione diretta con Google Gemini (Gratis)."""
    def __init__(self, api_key: str):
        if not api_key:
            logger.error("API Key Google mancante!")
            self.model = None
            return
        
        # Configurazione globale della libreria
        genai.configure(api_key=api_key)
        
        # Configurazione del modello con System Instruction
        # Nota: gemini-1.5-flash è il modello corretto, veloce e gratuito.
        self.model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=(
                "Sei un analista finanziario esperto. "
                "Riassumi i messaggi di trading in italiano. "
                "Massimo 50 parole. Sii diretto, operativo e urgente. "
                "Evita frasi introduttive come 'Ecco il riassunto'."
            )
        )
    
    async def summarize(self, text: str, retries: int = 1) -> Optional[str]:
        """Genera riassunto usando Google Gemini Nativo."""
        if not self.model:
            return None
        
        # Configurazione parametri di generazione
        generation_config = genai.GenerationConfig(
            temperature=0.3,
            max_output_tokens=150,
        )
        
        for attempt in range(retries + 1):
            try:
                # Chiamata asincrona nativa
                response = await self.model.generate_content_async(
                    f"Analizza e riassumi questo messaggio:\n{text}",
                    generation_config=generation_config
                )
                
                # Verifica che la risposta sia valida
                if response.text:
                    return response.text.strip()
                    
            except google_exceptions.ResourceExhausted:
                logger.warning("Quota gratuita Gemini superata (ResourceExhausted).")
                return None  # inutile riprovare subito se la quota è finita
            except google_exceptions.NotFound:
                # Se flash fallisce, fallback su gemini-pro
                logger.warning(f"Modello Flash non trovato, provo fallback su Pro...")
                return await self._fallback_summarize(text)
            except Exception as e:
                logger.warning(f"Tentativo Gemini {attempt+1} fallito: {e}")
                await asyncio.sleep(1)
        
        return None
    
    async def _fallback_summarize(self, text: str) -> Optional[str]:
        """Metodo di emergenza se il modello Flash non risponde."""
        try:
            fallback_model = genai.GenerativeModel('gemini-pro')
            response = await fallback_model.generate_content_async(
                f"Riassumi in breve (max 50 parole) come analista finanziario:\n{text}"
            )
            return response.text.strip() if response.text else None
        except Exception as e:
            logger.error(f"Anche il fallback ha fallito: {e}")
            return None

# Inizializzazione AI
ai_service = AIService(GEMINI_API_KEY)

async def gestisci_messaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia SUBITO ogni messaggio con riassunti VERI via Gemini."""
    
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
    
    # MESSAGGI LUNGHI: USA GEMINI PER VERI RIASSUNTI
    if len(original_text) > 100:
        logger.info(f"Messaggio lungo ({len(original_text)} chars). Generando riassunto AI...")
        riassunto = await ai_service.summarize(original_text)
        
        if riassunto:
            messaggio_finale = (
                f"📝 **Riassunto da {user}:**\n"
                f"{riassunto}\n\n"
                f"🔍 Per l'analisi completa e i livelli chiave → @The_Edge_Lab_Italia"
            )
        else:
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
    logger.info("Bot ISTANTANEO con AI GEMINI GRATIS (Google) avviato. In ascolto...")
    application.run_polling()
