
from tg.bot import bot
from tg.keyboards import warm_action_kb, choose_profile_for_client, choose_designer_kb
from core.utils import md2_escape, now
from core import repo_clients, repo_messages
from services import warm_service, designer_service
import config

def register(bot):

    def is_warm_thread(m):
        tid = getattr(m,'message_thread_id',None)
        return m.chat.id==config.GROUP_CHAT_ID and tid and tid not in (config.COLD_INBOX_TOPIC, config.ASSISTANT_TOPIC)

    @bot.message_handler(func=lambda m: is_warm_thread(m), content_types=['text'])
    def warm_msg(m):
        tid = m.message_thread_id
        row = repo_clients.get_by_topic(tid)
        if not row:
            cid = repo_clients.create_client(f"Client {tid}", topic_id=tid, status="active", manager_id=m.from_user.id)
            row = repo_clients.get_by_topic(tid)
        cid = row["id"]
        text = m.text or ""
        repo_messages.add(cid, "user", text)

        if not row["profile"]:
            bot.reply_to(m, "Choose an account profile for AI replies:", reply_markup=choose_profile_for_client(cid))
            return

        # AI draft
        draft = warm_service.ai_reply(row["profile"], cid)
        bot.send_message(config.GROUP_CHAT_ID, f"🤖 Suggested reply:\n\n{md2_escape(draft)}", message_thread_id=tid, parse_mode="MarkdownV2", reply_markup=warm_action_kb(cid))

    @bot.callback_query_handler(func=lambda q: q.data.startswith("set_profile|"))
    def set_profile(q):
        _, cid, prof = q.data.split("|")
        repo_clients.set_profile(int(cid), prof)
        bot.edit_message_text(f"Profile set to {prof}. New messages will use this style.", q.message.chat.id, q.message.id)
        bot.answer_callback_query(q.id)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("send_client|"))
    def send_client(q):
        _, cid = q.data.split("|")
        cid = int(cid)
        row = repo_clients.get_by_id(cid)
        tid = row["topic_id"]
        last_ai = repo_messages.last_ai_message(cid)
        if not last_ai:
            bot.answer_callback_query(q.id, "No AI draft"); return
        bot.send_message(config.GROUP_CHAT_ID, md2_escape(last_ai), message_thread_id=tid, parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id, "Sent")

    @bot.callback_query_handler(func=lambda q: q.data.startswith("ask_designer|"))
    def ask_designer(q):
        _, cid = q.data.split("|")
        cid = int(cid)
        row = repo_clients.get_by_id(cid)
        if row["designer"]:
            # send diff brief to assigned designer
            name = row["designer"]
            from config import DESIGNERS
            chat_id = DESIGNERS.get(name)
            if not chat_id:
                bot.answer_callback_query(q.id, f"No Telegram ID for {name}"); return
            brief = designer_service.brief_text(cid)
            bot.send_message(int(chat_id), md2_escape(brief), parse_mode="MarkdownV2")
            designer_service.after_send_update(cid)
            bot.edit_message_text(f"✅ Sent brief to {name}", q.message.chat.id, q.message.id)
            bot.answer_callback_query(q.id)
        else:
            from config import DESIGNERS
            bot.edit_message_text("Choose designer:", q.message.chat.id, q.message.id, reply_markup=choose_designer_kb(cid, DESIGNERS))
            bot.answer_callback_query(q.id)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("set_designer|"))
    def set_designer(q):
        _, cid, name = q.data.split("|")
        cid = int(cid)
        repo_clients.set_designer(cid, name)
        from config import DESIGNERS
        chat_id = DESIGNERS.get(name)
        if not chat_id:
            bot.answer_callback_query(q.id, f"No Telegram ID for {name}"); return
        brief = designer_service.brief_text(cid)
        bot.send_message(int(chat_id), md2_escape(brief), parse_mode="MarkdownV2")
        designer_service.after_send_update(cid)
        bot.edit_message_text(f"✅ Sent brief to {name}", q.message.chat.id, q.message.id)
        bot.answer_callback_query(q.id)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("info|"))
    def info(q):
        _, cid = q.data.split("|")
        row = repo_clients.get_by_id(int(cid))
        info_text = warm_service.build_info_text(row)
        bot.edit_message_text(info_text, q.message.chat.id, q.message.id, parse_mode="Markdown")
        bot.answer_callback_query(q.id)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("edit|"))
    def edit(q):
        _, cid = q.data.split("|")
        cid = int(cid)
        # спрощено: поки редагуємо тільки name/project/budget/type
        from telebot import types
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("Client name", callback_data=f"edit_field|{cid}|name"),
            types.InlineKeyboardButton("Project title", callback_data=f"edit_field|{cid}|project_title"),
        )
        kb.add(
            types.InlineKeyboardButton("Project type", callback_data=f"edit_field|{cid}|project_type"),
            types.InlineKeyboardButton("Budget", callback_data=f"edit_field|{cid}|budget")
        )
        bot.edit_message_text("Choose field to edit:", q.message.chat.id, q.message.id, reply_markup=kb)
        bot.answer_callback_query(q.id)

    edit_states = {}

    @bot.callback_query_handler(func=lambda q: q.data.startswith("edit_field|"))
    def edit_field(q):
        _, cid, field = q.data.split("|")
        cid = int(cid)
        edit_states[q.from_user.id] = (cid, field, q.message.chat.id, q.message.id)
        from telebot import types
        msg = bot.send_message(q.message.chat.id, f"Enter new value for *{field}*:", parse_mode="Markdown", reply_markup=types.ForceReply())
        bot.register_for_reply(msg, _edit_value_step)
        bot.answer_callback_query(q.id)

    def _edit_value_step(m):
        state = edit_states.get(m.from_user.id)
        if not state: return
        cid, field, chat_id, mid = state
        from core import repo_clients
        repo_clients.update_info(cid, **{field: m.text})
        bot.edit_message_text("Updated ✅", chat_id, mid)
        bot.send_message(m.chat.id, "Saved.")
        edit_states.pop(m.from_user.id, None)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("close|"))
    def close_flow(q):
        _, cid = q.data.split("|"); cid=int(cid)
        row = repo_clients.get_by_id(cid)
        last = repo_messages.last_ai_message(cid) or ""
        summary = f"Client: {row['name']}\nRecent: {last}"
        thanks = warm_service.thanks_note(row['profile'] or 'Yurii', summary)
        repo_messages.add(cid, "assistant", thanks)
        from telebot import types
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("📤 Send thanks", callback_data=f"close_send|{cid}"),
            types.InlineKeyboardButton("🗄 Archive & delete thread", callback_data=f"close_archive|{cid}")
        )
        bot.send_message(config.GROUP_CHAT_ID, f"🤖 Thanks draft:\n\n{md2_escape(thanks)}", message_thread_id=row['topic_id'], parse_mode="MarkdownV2", reply_markup=kb)
        bot.answer_callback_query(q.id)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("close_send|"))
    def close_send(q):
        _, cid = q.data.split("|"); cid=int(cid)
        row = repo_clients.get_by_id(cid)
        last_ai = repo_messages.last_ai_message(cid)
        if last_ai:
            bot.send_message(config.GROUP_CHAT_ID, md2_escape(last_ai), message_thread_id=row['topic_id'], parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id, "Sent")

    @bot.callback_query_handler(func=lambda q: q.data.startswith("close_archive|"))
    def close_archive(q):
        _, cid = q.data.split("|"); cid=int(cid)
        row = repo_clients.get_by_id(cid)
        try:
            bot.delete_forum_topic(config.GROUP_CHAT_ID, row['topic_id'])
        except Exception:
            pass
        repo_clients.set_status(cid, "closed")
        bot.edit_message_text("✅ Archived. Thread removed.", q.message.chat.id, q.message.id)
        bot.answer_callback_query(q.id)
