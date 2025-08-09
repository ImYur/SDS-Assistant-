# handlers.py — мінімальний варіант під наш новий main.py

from telebot import types

def register_handlers(bot):

    # ✅ Дебаг-команда для перевірки де зараз бот
    @bot.message_handler(commands=['debug_here'])
    def debug_here(m):
        bot.reply_to(
            m,
            f"chat.id = {m.chat.id}\n"
            f"thread_id = {getattr(m, 'message_thread_id', None)}"
        )

    # ✅ Пінг
    @bot.message_handler(commands=['ping'])
    def ping(m):
        bot.reply_to(m, "pong 🏓")

    # ❗ Тут більше нічого не перехоплюємо, 
    # щоб всю логіку повідомлень обробляв main.py
    return
