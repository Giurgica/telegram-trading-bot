#!/usr/bin/env python3
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request
import json
import asyncio

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram bot token from environment
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not TELEGRAM_BOT_TOKEN:
    logger.error('TELEGRAM_BOT_TOKEN not set')
    exit(1)

# Initialize Flask app
app = Flask(__name__)
application = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when /start is issued."""
    await update.message.reply_text('Trading Bot started!')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message."""
    help_text = '/start - Start bot\n/help - Help'
    await update.message.reply_text(help_text)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint for TradingView alerts."""
    try:
        data = request.json
        message = data.get('message', 'Alert')
        logger.info(f'Webhook received: {message}')
        return {'status': 'ok'}, 200
    except Exception as e:
        logger.error(f'Error: {e}')
        return {'error': str(e)}, 400

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'ok'}, 200

def main():
    global application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_cmd))
    logger.info('Bot polling started')
    application.run_polling()

if __name__ == '__main__':
    main()
