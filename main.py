import os
from telebot import TeleBot
from handlers import setup_handlers

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("ENV BOT_TOKEN is missing")

bot = TeleBot(TOKEN, parse_mode="Markdown")

setup_handlers(bot)

# стабільний запуск
bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
