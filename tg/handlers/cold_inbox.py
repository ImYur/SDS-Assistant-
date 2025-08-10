
from tg.bot import bot
from tg.keyboards import choose_profile_kb, cold_actions_kb
from core.utils import md2_escape
from services import cold_service
import config

def register(bot):

    def in_cold(m): 
        return m.chat.id==config.GROUP_CHAT_ID and getattr(m,'message_thread_id',None)==config.COLD_INBOX_TOPIC

    @bot.message_handler(func=lambda m: in_cold(m), content_types=['text'])
    def cold_capture(m):
        txt = m.text or ""
        cold_service.capture_lead(m.message_id, txt)
        bot.send_message(m.chat.id, "Cold lead captured. Choose a profile:", reply_markup=choose_profile_kb(m.message_id), message_thread_id=m.message_thread_id)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("cold_prof|"))
    def choose_prof(q):
        _, msg_id, prof = q.data.split("|")
        cold_service.set_profile(int(msg_id), prof)
        bot.edit_message_text(chat_id=q.message.chat.id, message_id=q.message.id, text=f"Profile set: {prof}.")
        bot.send_message(q.message.chat.id, "Actions:", reply_markup=cold_actions_kb(int(msg_id), prof), message_thread_id=getattr(q.message,'message_thread_id',None))
        bot.answer_callback_query(q.id)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("cold_pitch|"))
    def gen_pitch(q):
        _, msg_id, prof = q.data.split("|")
        msg_id = int(msg_id)
        job_text = cold_service.get_text(msg_id)
        pitch = cold_service.gen_pitch(prof, job_text)
        cold_service.save_pitch(msg_id, pitch)
        bot.edit_message_text(chat_id=q.message.chat.id, message_id=q.message.id, text="Pitch generated below 👇")
        bot.send_message(q.message.chat.id, md2_escape(pitch), parse_mode="MarkdownV2", message_thread_id=getattr(q.message,'message_thread_id',None))
        bot.answer_callback_query(q.id)

    @bot.callback_query_handler(func=lambda q: q.data.startswith("cold_sendpitch|"))
    def send_pitch(q):
        _, msg_id = q.data.split("|")
        msg_id = int(msg_id)
        pitch = cold_service.get_pitch(msg_id)
        if not pitch:
            bot.answer_callback_query(q.id, "No pitch yet"); return
        bot.send_message(q.message.chat.id, md2_escape(pitch), parse_mode="MarkdownV2", message_thread_id=getattr(q.message,'message_thread_id',None))
        bot.answer_callback_query(q.id, "Sent")

    @bot.callback_query_handler(func=lambda q: q.data.startswith("cold_convert|"))
    def convert(q):
        _, msg_id, prof = q.data.split("|")
        msg_id = int(msg_id)
        job_text = cold_service.get_text(msg_id)
        pitch = cold_service.get_pitch(msg_id) or "—"
        # guess name
        name = None
        for line in (job_text or "").splitlines():
            if 2 <= len(line.strip()) <= 50:
                name = line.strip(); break
        if not name: name = f"Lead {msg_id}"
        # create warm
        topic = bot.create_forum_topic(chat_id=config.GROUP_CHAT_ID, name=name)
        tid = topic.message_thread_id
        from core import repo_clients, repo_messages
        cid = repo_clients.create_client(name, profile=prof, topic_id=tid, status="active")
        repo_messages.add(cid, "user", f"Client brief (from cold):\n{job_text}")
        repo_messages.add(cid, "assistant", f"Our initial reply (pitch):\n{pitch}")
        # link
        abs_id = str(config.GROUP_CHAT_ID).replace("-100","")
        link = f"https://t.me/c/{abs_id}/{tid}"
        bot.edit_message_text(chat_id=q.message.chat.id, message_id=q.message.id, text=f"✅ Converted to warm: {name}\n{link}", disable_web_page_preview=True)
        bot.answer_callback_query(q.id)
