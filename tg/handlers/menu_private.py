
from telebot import types
from tg.bot import bot
from tg.keyboards import main_menu
from core import repo_clients
from core.utils import md2_escape
import config

def register(bot):

    @bot.message_handler(commands=['start','health'])
    def start_cmd(m):
        bot.send_message(m.chat.id, "✅ SDS Assistant ready. Use the menu or send text.", reply_markup=main_menu())

    @bot.message_handler(commands=['menu'])
    def menu_cmd(m):
        bot.send_message(m.chat.id, "Menu:", reply_markup=main_menu())

    @bot.message_handler(commands=['whoami'])
    def whoami(m):
        bot.reply_to(m, f"ID: {m.from_user.id}")
        bot.send_message(m.chat.id, "Menu:", reply_markup=main_menu())

    @bot.message_handler(func=lambda m: m.chat.type=='private' and m.text=='🔍 Price grid')
    def price(m):
        bot.reply_to(m,
            "• Logo “Clean Start” — $100\n"
            "• Brand Essentials — $220\n"
            "• Ready to Launch — $360\n"
            "• Complete Look — $520\n"
            "• Identity in Action — $1000\n"
            "• Signature System — $1500+",
            reply_markup=main_menu()
        )

    @bot.message_handler(func=lambda m: m.chat.type=='private' and m.text=='📋 Active')
    def active(m):
        rows = repo_clients.list_active()
        if not rows:
            bot.reply_to(m, "No active projects.", reply_markup=main_menu()); return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for r in rows:
            gid = str(config.GROUP_CHAT_ID).replace("-100","")
            link = f"https://t.me/c/{gid}/{r['topic_id']}"
            kb.add(types.InlineKeyboardButton(f"🧵 {r['name']}", url=link))
        bot.reply_to(m, "Active projects:", reply_markup=kb)

    @bot.message_handler(func=lambda m: m.chat.type=='private' and m.text=='🆕 New client')
    def new_client(m):
        force = types.ForceReply(input_field_placeholder="Client name or paste client text…")
        msg = bot.reply_to(m, "Enter client name (or paste their message).", reply_markup=force)
        bot.register_for_reply(msg, _new_client_step)

    def _new_client_step(reply_msg):
        text = (reply_msg.text or "").strip()
        # naive parse: if multi-line, take first line as name, second as project title
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        name = lines[0][:48] if lines else ("Client " + str(reply_msg.from_user.id))
        project = lines[1][:80] if len(lines)>1 else None

        # create forum topic
        topic = bot.create_forum_topic(chat_id=config.GROUP_CHAT_ID, name=name)
        tid = topic.message_thread_id

        # save client
        from core import repo_clients, repo_messages
        cid = repo_clients.create_client(name, project_title=project, topic_id=tid, status="active", manager_id=reply_msg.from_user.id)
        # seed messages with provided text (so AI has context)
        from core.utils import now
        if text:
            repo_messages.add(cid, "user", text)

        # ask profile
        from tg.keyboards import choose_profile_for_client
        bot.send_message(config.GROUP_CHAT_ID, f"🆕 New warm thread created for *{md2_escape(name)}*.", message_thread_id=tid, parse_mode="MarkdownV2")
        bot.send_message(config.GROUP_CHAT_ID, "Choose profile for AI:", message_thread_id=tid, reply_markup=choose_profile_for_client(cid))

    @bot.message_handler(func=lambda m: m.chat.type=='private', content_types=['text'])
    def private_any(m):
        if m.text and m.text.strip().startswith("/"):
            return
        bot.send_message(m.chat.id, "Menu:", reply_markup=main_menu())
