
from tg.handlers import menu_private, cold_inbox, warm_threads, assistant_topic

def register_all(bot):
    menu_private.register(bot)
    cold_inbox.register(bot)
    warm_threads.register(bot)
    assistant_topic.register(bot)
