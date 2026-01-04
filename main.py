import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import openai

# --- CONFIGURAZIONE LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- RECUPERO VARIABILI DA RENDER ---
# Il codice leggera questi valori dalle impostazioni che metterai su Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TARGET_GROUP_ID = os.getenv("TARGET_GROUP_ID") 
SOURCE_GROUP_ID = os.getenv("SOURCE_GROUP_ID")

# Verifica che le variabili siano state inserite
if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not TARGET_GROUP_ID or not SOURCE_GROUP_ID:
    print("ERRORE FATALE: Mancano le Environment Variables su Render.")
    exit(1)

# Conversione ID in numeri interi
try:
    TARGET_GROUP_ID = int(TARGET_GROUP_ID)
    SOURCE_GROUP_ID = int(SOURCE_GROUP_ID)
except ValueError:
    print("ERRORE: Gli ID dei gruppi devono essere numeri interi (es. -100123456).")
    exit(1)

# Configurazione OpenAI
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Lista temporanea per accumulare i messaggi
messaggi_accumulati = []

async def raccogli_messaggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ascolta i messaggi. Se provengono dal gruppo di partenza (SOURCE),
    li salva nella memoria temporanea.
    """
    # Se il messaggio non viene dal gruppo di partenza, ignoralo
    if update.effective_chat.id != SOURCE_GROUP_ID:
        return

    if update.message and update.message.text:
        user = update.message.from_user.first_name
        text = update.message.text
        # Aggiunge alla lista
        messaggi_accumulati.append(f"{user}: {text}")
        print(f"Messaggio salvato da {user}")

async def genera_e_invia_riassunto(context: ContextTypes.DEFAULT_TYPE):
    """
    Funzione periodica: prende i messaggi accumulati, chiede il riassunto all'AI
    e lo invia al gruppo di destinazione.
    """
    global messaggi_accumulati
    
    # Se non c'e nulla da dire, non fare nulla
    if not messaggi_accumulati:
        return

    print(f"Elaborazione di {len(messaggi_accumulati)} messaggi...")
    
    # Crea una copia del testo da mandare all'AI
    testo_chat = "\n".join(messaggi_accumulati)
    
    # Svuota SUBITO la lista principale per non perdere i nuovi messaggi in arrivo
    messaggi_accumulati = [] 

    try:
        # Costruiamo la richiesta per l'Intelligenza Artificiale
        prompt = (
            f"Sei un assistente che gestisce la comunicazione tra gruppi Telegram. "
            f"Ecco la conversazione avvenuta nell'ultima ora nel gruppo principale.\n"
            f"Genera un riassunto in italiano chiaro, schematico e strutturato per punti.\n"
            f"Evidenzia decisioni importanti, link o appuntamenti:\n\n"
            f"{testo_chat}"
        )
        
        # Chiamata a OpenAI (GPT)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # Usa "gpt-4o" se preferisci (costa leggermente di piu)
            messages=[
                {"role": "system", "content": "Sei un segretario efficiente."},
                {"role": "user", "content": prompt}
            ]
        )
        riassunto = response.choices[0].message.content

        # Invio del riassunto nel gruppo di DESTINAZIONE
        await context.bot.send_message(
            chat_id=TARGET_GROUP_ID, 
            text=f"📝 **RIASSUNTO PERIODICO**\n\n{riassunto}", 
            parse_mode='Markdown'
        )
        print("Riassunto inviato con successo.")

    except Exception as e:
        print(f"Errore durante il processo di riassunto: {e}")

if __name__ == '__main__':
    # Avvio del Bot
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Gestore dei messaggi (Ignora i comandi tipo /start, legge solo testo)
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), raccogli_messaggi)
    application.add_handler(msg_handler)

    # Impostazione del Timer
    job_queue = application.job_queue
    
    # IMPORTANTE: Qui decidi ogni quanto fare il riassunto.
    # interval=3600 significa 3600 secondi (1 ORA).
    # first=3600 significa che il primo riassunto parte dopo 1 ora dall'avvio.
    job_queue.run_repeating(genera_e_invia_riassunto, interval=3600, first=3600)

    print("Bot avviato correttamente. In ascolto...")
    application.run_polling()
