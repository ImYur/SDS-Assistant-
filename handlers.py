
def setup_handlers(bot):
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        bot.reply_to(message, "👋 Привіт! Я Stylus Assistant. Чекаю повідомлення від клієнта або команди.")

    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        # Тут буде логіка перевірки, хто пише, і що з цим робити
        bot.reply_to(message, "✅ Повідомлення прийнято. (Це лише базова відповідь.)")
