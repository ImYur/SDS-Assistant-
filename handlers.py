# handlers.py — мінімальний, не перехоплює тексти, щоб не заважати main.py
def register_handlers(bot):
    @bot.message_handler(commands=['debug_here'])
    def debug_here(m):
        bot.reply_to(m, f"chat.id={m.chat.id}\nthread_id={getattr(m,'message_thread_id',None)}", parse_mode=None)
    return
