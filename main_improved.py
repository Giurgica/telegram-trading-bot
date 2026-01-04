import os
import logging
import asyncio
import re
from typing import Optional
from dataclasses import dataclass

# Librerie esterne
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from openai import AsyncOpenAI, APITimeoutError, APIConnectionError

# --- CONFIGURAZIONE LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot_activity.log"), # Salva log su file
        logging.StreamHandler()                  # Stampa log a video
    ]
)
logger = logging.getLogger("EdgeLabBot")

# --- CONFIGURAZIONE ENVIRONMENT ---
@dataclass
class BotConfig:
    """Classe per gestire e validare la configurazione."""
    telegram_token: str
    openai_api_key: str
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
                raise ValueError("Token Telegram o OpenAI API Key mancanti.")
            if config.target_group_id == 0 or config.source_group_id == 0:
                raise ValueError("ID dei gruppi non validi o mancanti.")
            return config
        except ValueError as e:
            logger.critical(f"Errore Configurazione: {e}")
            exit(1)

# --- SERVIZIO AI (OpenAI) ---
class AIService:
    """Gestisce tutte le interazioni con l'AI."""
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-3.5-turbo" # O gpt-4o-mini per maggiore velocità/costi ridotti

    async def summarize(self, text: str, retries: int = 2) -> Optional[str]:
        """
        Genera un riassunto con logica di retry in caso di errore di rete.
        """
        system_prompt = (
            "Sei un analista finanziario esperto. "
            "Riassumi il testo seguente in italiano, in massimo 50 parole. "
            "Sii diretto, usa elenchi puntati se necessario. "
            "Il tono deve essere professionale e urgente."
        )

        for attempt in range(retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Testo da riassumere:\n{text}"}
                    ],
                    max_tokens=150,
                    temperature=0.3
                )
                return response.choices[0].message.content.strip()
            
            except (APITimeoutError, APIConnectionError) as e:
                logger.warning(f"Tentativo {attempt+1}/{retries+1} fallito (Rete): {e}")
                await asyncio.sleep(1) # Attesa breve prima del retry
            except Exception as e:
                logger.error(f"Errore irreversibile OpenAI: {e}")
                return None
        
        logger.error("Tutti i tentativi AI falliti.")
        return None

# --- GESTORE DEL BOT ---
class TelegramForwarderBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.ai = AIService(config.openai_api_key)
        self.keywords_live = ["LIVE ON AIR", "IN DIRETTA", "🔴"]
        self.keywords_link = ["HTTP", "ZOOM", "YOUTUBE", "MEET"]

    def _sanitize_html(self, text: str) -> str:
        """Pulisce il testo per renderlo sicuro in HTML mode."""
        return text.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")

    async def _handle_live_event(self, context: ContextTypes.DEFAULT_TYPE):
        """Invia il messaggio promozionale per la live."""
        messaggio_live = (
            f"<b>ATTENZIONE: DIRETTA SPECIALE APPENA INIZIATA 🚨</b>\n\n"
            f"Sta partendo ORA una sessione cruciale per chi vuole portare il proprio trading a un livello superiore.\n"
            f"Registrati subito per entrare nel canale esclusivo e seguire la diretta in tempo reale.\n\n"
            f"🔗 <b>Unisciti ora:</b> {self.config.cta_link}"
        )
        await context.bot.send_message(
            chat_id=self.config.target_group_id, 
            text=messaggio_live,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        logger.info("⚡ Messaggio LIVE inviato.")

    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # 1. Validazione Sorgente
        if update.effective_chat.id != self.config.source_group_id:
            return # Ignora messaggi da altri gruppi
        
        if not update.message or not update.message.text:
            return # Ignora media senza caption o messaggi di servizio

        original_text = update.message.text
        user_name = self._sanitize_html(update.message.from_user.first_name or "Trader")
        text_upper = original_text.upper()

        # 2. Controllo LIVE (Priorità Massima)
        is_live = any(k in text_upper for k in self.keywords_live)
        has_link = any(k in text_upper for k in self.keywords_link)

        if is_live and has_link:
            await self._handle_live_event(context)
            return

        # 3. Logica Riassunto vs Diretto
        messaggio_finale = ""
        
        # Caso A: Messaggio Lungo -> AI
        if len(original_text) > 100:
            logger.info(f"Elaborazione AI per messaggio di {len(original_text)} caratteri...")
            # Placeholder "Sto scrivendo..." per feedback visivo
            await context.bot.send_chat_action(chat_id=self.config.target_group_id, action="typing")
            
            riassunto = await self.ai.summarize(original_text)
            
            if riassunto:
                clean_riassunto = self._sanitize_html(riassunto)
                messaggio_finale = (
                    f"📝 <b>Flash Update ({user_name}):</b>\n\n"
                    f"{clean_riassunto}\n\n"
                    f"🔎 <i>Analisi completa:</i> {self.config.cta_link}"
                )
            else:
                # Fallback se AI fallisce: invia originale troncato o intero
                messaggio_finale = (
                    f"👤 <b>{user_name}:</b>\n{self._sanitize_html(original_text)}\n\n"
                    f"👉 {self.config.cta_link}"
                )
        
        # Caso B: Messaggio Breve -> Diretto
        else:
            messaggio_finale = (
                f"👤 <b>{user_name}:</b> {self._sanitize_html(original_text)}\n\n"
                f"👉 {self.config.cta_link}"
            )

        # 4. Invio Messaggio Finale
        try:
            await context.bot.send_message(
                chat_id=self.config.target_group_id,
                text=messaggio_finale,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            logger.info(f"Messaggio inoltrato (AI: {'Sì' if len(original_text)>100 else 'No'}).")
        except Exception as e:
            logger.error(f"Errore critico invio Telegram: {e}")

    async def status_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando admin per verificare che il bot risponda."""
        await update.message.reply_text("✅ Bot Operativo e in ascolto.")

# --- MAIN ---
def main():
    # Caricamento Configurazione
    config = BotConfig.load()
    
    # Inizializzazione Bot Logic
    bot_logic = TelegramForwarderBot(config)
    
    # Setup Application
    application = ApplicationBuilder().token(config.telegram_token).build()

    # Handlers
    # Gestisce solo messaggi di testo nel gruppo sorgente
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), bot_logic.process_message)
    # Comando di debug (opzionale)
    status_handler = CommandHandler("status", bot_logic.status_check)

    application.add_handler(msg_handler)
    application.add_handler(status_handler)

    logger.info(f"🚀 Bot avviato. Monitoraggio gruppo: {config.source_group_id} -> Target: {config.target_group_id}")
    
    # Avvio Loop (Bloccante)
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot arrestato manualmente.")
