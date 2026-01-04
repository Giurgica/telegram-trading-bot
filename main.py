import os
import logging
import asyncio
from typing import Optional
from dataclasses import dataclass

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# --- CONFIGURAZIONE LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("EdgeLabBot")

# --- CONFIGURAZIONE ENVIRONMENT ---
@dataclass
class BotConfig:
    telegram_token: str
    openai_api_key: str  # Qui ci va la chiave di Google (AIza...)
    target_group_id: int
    source_group_id: int
    cta_link: str = "@The_Edge_Lab_Italia"

    @classmethod
    def load(cls):
        try:
            config = cls(
                telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
                openai_api_key=os.getenv("OPENAI_API_KEY", ""),
                target_group_id=int(os.getenv("TARGET_GROUP_ID", "0")),
                source_group_id=int(os.getenv("SOURCE_GROUP_ID", "0"))
            )
            if not config.telegram_token or not config.openai_api_key:
                raise ValueError("Token Telegram o API Key mancanti.")
            return config
        except ValueError as e:
            logger.critical(f"Errore Config: {e}")
            exit(1)

# --- SERVIZIO AI (Google Gemini Nativo) ---
class AIService:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model_name = 'gemini-1.5-flash'
        
        # --- DEBUG AVVIO: Stampa i modelli disponibili ---
        try:
            logger.info("🔍 Cerco modelli disponibili...")
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            logger.info(f"Modelli Trovati: {available_models}")
            
            # Verifica se il modello scelto è nella lista
            full_model_name = f"models/{self.model_name}"
            if full_model_name not in available_models and self.model_name not in available_models:
                logger.warning(f"⚠️ {self.model_name} non trovato esattamente nella lista. Userò il primo disponibile o fallback.")
        except Exception as e:
            logger.error(f"Errore nel listare i modelli: {e}")
        
        # Configurazione Modello
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction="Sei un analista finanziario. Riassumi messaggi di trading in italiano (max 50 parole). Diretto e operativo."
        )

    async def summarize(self, text: str) -> Optional[str]:
        try:
            response = await self.model.generate_content_async(
                f"Riassumi questo:\n{text}",
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=150
                )
            )
            return response.text.strip() if response.text else None
        except Exception as e:
            logger.error(f"Errore AI ({self.model_name}): {e}")
            return None

# --- BOT LOGIC ---
class TelegramForwarderBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.ai = AIService(config.openai_api_key)

    def _sanitize_html(self, text: str) -> str:
        return text.replace("<", "<").replace(">", ">").replace("&", "&")

    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != self.config.source_group_id:
            return
        if not update.message or not update.message.text:
            return
        
        original_text = update.message.text
        user = self._sanitize_html(update.message.from_user.first_name or "Trader")
        
        # Logica LIVE
        if "LIVE" in original_text.upper() and "HTTP" in original_text.upper():
            await context.bot.send_message(
                chat_id=self.config.target_group_id,
                text=f"🚨 **LIVE IN CORSO!**\nUnisciti ora: {self.config.cta_link}",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Logica Riassunto
        messaggio_finale = ""
        if len(original_text) > 100:
            logger.info(f"Generazione riassunto per messaggio di {len(original_text)} char...")
            await context.bot.send_chat_action(chat_id=self.config.target_group_id, action="typing")
            riassunto = await self.ai.summarize(original_text)
            if riassunto:
                messaggio_finale = f"📝 **Flash ({user}):**\n{self._sanitize_html(riassunto)}\n👉 {self.config.cta_link}"
            else:
                messaggio_finale = f"👤**{user}:**\n{self._sanitize_html(original_text)}"
        else:
            messaggio_finale = f"👤**{user}:** {self._sanitize_html(original_text)}"
        
        try:
            await context.bot.send_message(
                chat_id=self.config.target_group_id,
                text=messaggio_finale,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Errore invio: {e}")

# --- MAIN ---
if __name__ == '__main__':
    conf = BotConfig.load()
    bot = TelegramForwarderBot(conf)
    app = ApplicationBuilder().token(conf.telegram_token).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), bot.process_message))
    logger.info("✅ Bot Avviato con Google Gemini Nativo")
    app.run_polling()
