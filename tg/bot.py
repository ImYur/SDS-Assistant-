
from telebot import TeleBot
import config

bot = TeleBot(config.BOT_TOKEN, parse_mode="Markdown")
