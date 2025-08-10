
from tg.bot import bot
from tg.routing import register_all

if __name__ == "__main__":
    register_all(bot)
    print("SDS bot starting…")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
