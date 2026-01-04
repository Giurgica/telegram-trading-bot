import os
import logging
import asyncio
from dataclasses import dataclass
from typing import Optional

# Librerie Esterne
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# --- 1. CONFIGURAZIONE LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("EdgeLabBot")

# --- 2. GESTIONE CONFIGURAZIONE ---
@dataclass
class BotConfig:
    telegram_token: str
    google_api_key: str  # In Railway useremo la variabile OPENAI_API_KEY per comodità
    target_group_id: int
    source_group_id: int
    cta_link: str = "@The_Edge_Lab_Italia"

    @classmethod
    def load(cls):
        """Carica e valida le variabili d'ambiente."""
        try:
            # Nota: Leggiamo OPENAI_API_KEY perché è quella che hai già settato su Railway,
            # ma la usiamo come chiave per Google Gemini.
            token = os.getenv("TELEGRAM_TOKEN", "")
            api_key = os.getenv("OPENAI_API_KEY", "") 
            
            target = int(os.getenv("TARGET_GROUP_ID", "0"))
            source = int(os.getenv("SOURCE_GROUP_ID", "0"))

            if not token or not api_key:
                raise ValueError("Mancano TELEGRAM_TOKEN o OPENAI_API_KEY.")
            if target == 0 or source == 0:
                raise ValueError("TARGET_GROUP_ID o SOURCE_GROUP_ID non validi.")

            return cls(token, api_key, target, source)
        except ValueError as e:
            logger.critical(f"❌ Errore Configurazione: {e}")
            exit(1)

# --- 3. SERVIZIO AI (Google Gemini) ---
class AIService:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model_name = 'gemini-1.5-flash'
        
        # PROMPT AGGIORNATO: Analitico, 30-50 parole, NO Nomi
        system_prompt = (
            "Sei un analista finanziario istituzionale senior. "
            "Il tuo compito è sintetizzare i messaggi di trading in un report operativo.\n\n"
            "REGOLE OBBLIGATORIE:\n"
            "1. NO NOMI: Non menzionare MAI l'autore del messaggio (es. evita 'L'utente dice', 'Marco scrive').\n"
            "2. LUNGHEZZA: Il testo DEVE essere corposo, tra le 30 e le 50 parole.\n"
            "3. STILE: Discorsivo, professionale, urgente. Spiega il 'cosa' e il 'perché'.\n"
            "4. CONTENUTO: Estrai livelli tecnici, direzione (Long/Short) e sentiment.\n"
            "5. LINGUA: Italiano perfetto."
        )

        try:
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt
            )
            logger.info(f"✅ Modello AI caricato: {self.model_name}")
        except Exception as e:
            logger.error(f"❌ Errore init AI: {e}")

    async def summarize(self, text: str) -> Optional[str]:
        """Genera il riassunto con parametri ottimizzati per analisi più lunghe."""
        try:
            response = await self.model.generate_content_async(
                f"Analizza questo input:\n{text}",
                generation_config=genai.GenerationConfig(
                    temperature=0.4,       # Un po' più di creatività per raggiungere le 50 parole
                    max_output_tokens=300  # Abbastanza spazio per non tagliare
                )
            )
            return response.text.strip() if response.text else None
        except Exception as e:
            logger.error(f"⚠️ Errore Generazione AI: {e}")
            return None

# --- 4. LOGICA DEL BOT ---
class TelegramForwarderBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.ai = AIService(config.google_api_key)

    def _sanitize(self, text: str) -> str:
        """Pulisce il testo per evitare crash in HTML mode."""
        if not text: return ""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Filtri di base
        if update.effective_chat.id != self.config.source_group_id:
            return
        if not update.message or not update.message.text:
            return

        original_text = update.message.text
        # Prendiamo il nome solo per l'intestazione, NON lo passiamo all'AI
        user_name = self._sanitize(update.message.from_user.first_name or "Trader")
        
        # --- A. GESTIONE LIVE (Priorità Alta) ---
        if "LIVE" in original_text.upper() and "HTTP" in original_text.upper():
            await context.bot.send_message(
                chat_id=self.config.target_group_id,
                text=(
                    f"🚨 <b>DIRETTA OPERATIVA IN CORSO!</b>\n\n"
                    f"Sessione live appena iniziata. Non perdere i livelli in tempo reale.\n"
                    f"👇 <b>Clicca per entrare:</b>\n{self.config.cta_link}"
                ),
                parse_mode=ParseMode.HTML
            )
            logger.info("📢 Annuncio LIVE inviato.")
            return

        # --- B. GESTIONE RIASSUNTO (Messaggi > 100 char) ---
        messaggio_finale = ""
        
        if len(original_text) > 100:
            logger.info(f"🧠 Elaborazione AI ({len(original_text)} chars)...")
            await context.bot.send_chat_action(chat_id=self.config.target_group_id, action="typing")
            
            # Passiamo all'AI solo il testo, niente nomi
            riassunto = await self.ai.summarize(original_text)
            
            if riassunto:
                messaggio_finale = (
                    f"📊 <b>Market Insight ({user_name}):</b>\n\n"
                    f"<i>{self._sanitize(riassunto)}</i>\n\n"
                    f"👉 <b>Approfondisci qui:</b> {self.config.cta_link}"
                )
            else:
                # Fallback se l'AI fallisce
                messaggio_finale = (
                    f"👤 <b>{user_name}:</b>\n{self._sanitize(original_text)}\n\n"
                    f"👉 {self.config.cta_link}"
                )
        
        # --- C. MESSAGGI BREVI (Diretti) ---
        else:
            messaggio_finale = (
                f"👤 <b>{user_name}:</b> {self._sanitize(original_text)}\n\n"
                f"👉 {self.config.cta_link}"
            )

        # Invio
        try:
            await context.bot.send_message(
                chat_id=self.config.target_group_id,
                text=messaggio_finale,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"❌ Errore Invio Telegram: {e}")

    async def status_check(self, update:
