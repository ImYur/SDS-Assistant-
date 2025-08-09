import telebot
from telebot import types
import os

TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_ТУТ")

bot = telebot.TeleBot(TOKEN)

# ===== Меню кнопки =====
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🆕 Новий клієнт", "📂 Історія переписки")
    markup.row("📝 Відправити дизайнеру", "✅ Завершити проєкт")
    markup.row("🔍 Перевірити ціну", "📋 Активні роботи")
    return markup

# ===== /start =====
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(message.chat.id, "Бот запущений ✅", reply_markup=main_menu())

# ===== /getchatid =====
@bot.message_handler(commands=['getchatid'])
def get_chat_id(message):
    bot.reply_to(message, f"chat.id = {message.chat.id}")

# ===== Приклад реакції на кнопки =====
@bot.message_handler(func=lambda m: m.text == "🆕 Новий клієнт")
def new_client(message):
    bot.send_message(message.chat.id, "Введи ім'я нового клієнта:")

@bot.message_handler(func=lambda m: m.text == "📂 Історія переписки")
def history(message):
    bot.send_message(message.chat.id, "Тут буде історія переписки 📜")

# ===== Реакція на будь-який текст =====
@bot.message_handler(func=lambda m: True)
def all_text(message):
    bot.send_message(message.chat.id, f"Ти написав: {message.text}")

print("Бот запущений...")
bot.infinity_polling()
