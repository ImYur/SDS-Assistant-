# Мінімальний, щоб не перехоплювати логіку з main.py
def register_handlers(bot):
    @bot.message_handler(commands=['debug_here'])
    def debug_here(m):
        bot.reply_to(m, f"chat.id={m.chat.id}\nthreadid={getattr(m,'message_thread_id',None)}", parse_mode=None)
    return
