
from telebot import TeleBot
import os

from handlers import setup_handlers

TOKEN = os.getenv("BOT_TOKEN")
bot = TeleBot(TOKEN)

setup_handlers(bot)

bot.infinity_polling()
