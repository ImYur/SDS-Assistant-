import os, re, json
from datetime import datetime, timedelta
import telebot
from telebot import types

import db
import ai
import prompts

TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
COLD_INBOX_TOPIC = int(os.getenv("COLD_INBOX_TOPIC", "0") or "0")
ASSISTANT_TOPIC = int(os.getenv("ASSISTANT_TOPIC", "0") or "0")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")
DESIGNERS = json.loads(os.getenv("DESIGNERS", "{}") or "{}")

if not TOKEN or not GROUP_CHAT_ID:
    raise RuntimeError("Missing BOT_TOKEN or GROUP_CHAT_ID")

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

SYSTEM_MAP = {"Yurii": prompts.YURII_SYSTEM, "Olena": prompts.OLENA_SYSTEM}
PROFILES = ["Yurii", "Olena"]

def md2_escape(s: str) -> str:
    if not s: return ""
    s = s.replace("\\","\\\\")
    for ch in ['_','*','[',']','(',')','~','`','>','#','+','-','=','|','{','}','.','!']:
        s = s.replace(ch, '\\'+ch)
    return s

def topic_link(topic_id):
    abs_id = str(GROUP_CHAT_ID).replace("-100","")
    return f"https://t.me/c/{abs_id}/{topic_id}"

# ===== Меню у приваті =====
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, input_field_placeholder="Choose…")
    kb.row("🆕 New client", "📂 History")
    kb.row("🧵 Open topic", "🧑‍🎨 Send to designer")
    kb.row("📋 Active", "✅ Close project")
    kb.row("🔍 Price grid")
    return kb

def ensure_menu_private(m):
    if m.chat.type == "private":
        try:
            bot.send_message(m.chat.id, "Menu:", reply_markup=main_menu())
        except: pass

# ===== Хелпери warm =====
def choose_designer_kb(client_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for name in DESIGNERS.keys():
        kb.add(types.InlineKeyboardButton(name, callback_data=f"set_designer|{client_id}|{name}"))
    return kb

def warm_action_kb(client_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📤 Send to client", callback_data=f"send_client|{client_id}"),
        types.InlineKeyboardButton("🧑‍🎨 To designer", callback_data=f"ask_designer|{client_id}")
    )
    kb.add(
        types.InlineKeyboardButton("✅ Close", callback_data=f"close|{client_id}"),
        types.InlineKeyboardButton("📎 History", callback_data=f"history|{client_id}")
    )
    return kb

# ===== Команди =====
@bot.message_handler(commands=['start','health'])
def start_cmd(m):
    bot.send_message(m.chat.id, "✅ SDS Assistant ready. Use the menu or send text.", reply_markup=main_menu())

@bot.message_handler(commands=['whoami'])
def whoami(m): bot.reply_to(m, f"ID: {m.from_user.id}", reply_markup=main_menu())

@bot.message_handler(commands=['debug_here'])
def debug_here(m):
    bot.send_message(m.chat.id, f"chat.id={m.chat.id}\nthread_id={getattr(m,'message_thread_id',None)}", parse_mode=None)

# ======== COLD INBOX (в тій же групі) ========
def in_cold(m): return m.chat.id==GROUP_CHAT_ID and getattr(m,'message_thread_id',None)==COLD_INBOX_TOPIC
def in_assistant(m): return m.chat.id==GROUP_CHAT_ID and getattr(m,'message_thread_id',None)==ASSISTANT_TOPIC

@bot.message_handler(func=lambda m: in_cold(m), content_types=['text'])
def cold_handler(m):
    text = m.text or ""
    db.add_cold(m.message_id, text)
    # вибір профілю
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("Yurii", callback_data=f"cold_prof|{m.message_id}|Yurii"),
        types.InlineKeyboardButton("Olena", callback_data=f"cold_prof|{m.message_id}|Olena"),
    )
    bot.reply_to(m, "Cold lead captured. Choose a profile:", reply_markup=kb)

@bot.callback_query_handler(func=lambda q: q.data.startswith("cold_prof|"))
def cold_choose_profile(q):
    _, msg_id, prof = q.data.split("|")
    msg_id = int(msg_id)
    db.set_cold_profile(msg_id, prof)
    # тягнемо текст cold
    kb_text = db.cold_kb_snapshot()
    # знайдемо оригінальний текст через snapshot не треба; простіше попросимо користувача натиснути «Generate pitch»
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📝 Generate pitch", callback_data=f"cold_pitch|{msg_id}|{prof}"))
    kb.add(types.InlineKeyboardButton("🧵 Convert to Warm", callback_data=f"cold_convert|{msg_id}|{prof}"))
    bot.edit_message_text(f"Profile set: {prof}. Next: generate pitch or convert to warm.", q.message.chat.id, q.message.id)
    bot.send_message(q.message.chat.id, "Actions:", reply_markup=kb)
    bot.answer_callback_query(q.id)

@bot.callback_query_handler(func=lambda q: q.data.startswith("cold_pitch|"))
def cold_make_pitch(q):
    _, msg_id, prof = q.data.split("|")
    msg_id = int(msg_id)
    # витягнемо сам текст з БД
    cur = db.CONN.cursor()
    cur.execute("SELECT text FROM cold_leads WHERE message_id=?", (msg_id,))
    row = cur.fetchone()
    job_text = row[0] if row else ""
    pitch = ai.gen_pitch(prof, job_text, SYSTEM_MAP)
    db.set_cold_status(msg_id, "archived")
    bot.edit_message_text("Pitch generated below 👇", q.message.chat.id, q.message.id)
    bot.send_message(q.message.chat.id, md2_escape(pitch), parse_mode="MarkdownV2")
    bot.answer_callback_query(q.id)

@bot.callback_query_handler(func=lambda q: q.data.startswith("cold_convert|"))
def cold_convert(q):
    _, msg_id, prof = q.data.split("|")
    msg_id = int(msg_id)
    # Спробуємо вгадати ім'я клієнта з перших рядків
    cur = db.CONN.cursor()
    cur.execute("SELECT text FROM cold_leads WHERE message_id=?", (msg_id,))
    row = cur.fetchone()
    text = row[0] if row else ""
    name_guess = None
    for line in text.splitlines():
        if 2<=len(line)<=50:
            name_guess = line.strip()
            break
    if not name_guess: name_guess = f"Lead {msg_id}"
    # створюємо warm‑клієнта без топіка — тема створиться нижче
    client_id = db.create_client(name_guess, profile=prof, status="active")
    # створюємо форум‑тему
    topic = bot.create_forum_topic(chat_id=GROUP_CHAT_ID, name=name_guess)
    tid = topic.message_thread_id
    db.set_client_topic(client_id, tid)
    db.set_cold_status(msg_id, "converted")
    link = topic_link(tid)
    bot.edit_message_text(f"✅ Converted to warm: {name_guess}\n{link}", q.message.chat.id, q.message.id, disable_web_page_preview=True)
    bot.answer_callback_query(q.id)

# ======== CHATGPT ASSISTANT ТЕМА ========
@bot.message_handler(func=lambda m: in_assistant(m), content_types=['text'])
def assistant_handler(m):
    # невеличкий KB snapshot
    kb_text = db.kb_snapshot()
    question = m.text or ""
    answer = ai.assistant_answer(kb_text, question)
    bot.reply_to(m, md2_escape(answer), parse_mode="MarkdownV2")

# ======== WARM: повідомлення в тредах клієнтів ========
@bot.message_handler(func=lambda m: m.chat.id==GROUP_CHAT_ID and getattr(m,'message_thread_id',None) not in (0, COLD_INBOX_TOPIC, ASSISTANT_TOPIC), content_types=['text'])
def warm_thread_msg(m):
    tid = m.message_thread_id
    row = db.get_client_by_topic(tid)
    if not row:
        # якщо клієнт не зареєстрований — створимо
        name = m.chat.title if not m.text else (m.text.splitlines()[0][:32] or "Client")
        cid = db.create_client(name, topic_id=tid, status="active")
        row = db.get_client_by_topic(tid)

    client_id,name,company,profile,designer,status,topic_id = row
    text = m.text or ""
    # додаємо до історії як "user" (від клієнта/менеджера)
    db.add_msg(client_id, "user", text)

    # якщо профіль ще не обраний — попросимо
    if not profile:
        kb = types.InlineKeyboardMarkup(row_width=2)
        for p in PROFILES:
            kb.add(types.InlineKeyboardButton(p, callback_data=f"set_profile|{client_id}|{p}"))
        bot.reply_to(m, "Choose an account profile for AI replies:", reply_markup=kb)
        return

    # зібрати коротку історію для AI
    hist = db.get_history_messages(client_id, last_n=20)
    reply = ai.gen_reply(profile, hist, SYSTEM_MAP)
    db.add_msg(client_id, "assistant", reply)

    # показати дії
    bot.send_message(GROUP_CHAT_ID, f"🤖 Suggested reply:\n\n{md2_escape(reply)}", message_thread_id=tid, parse_mode="MarkdownV2", reply_markup=warm_action_kb(client_id))

@bot.callback_query_handler(func=lambda q: q.data.startswith("set_profile|"))
def set_profile(q):
    _, cid, prof = q.data.split("|")
    db.set_client_profile(int(cid), prof)
    bot.edit_message_text(f"Profile set to {prof}. New messages will use this style.", q.message.chat.id, q.message.id)
    bot.answer_callback_query(q.id)

@bot.callback_query_handler(func=lambda q: q.data.startswith("send_client|"))
def send_client(q):
    _, cid = q.data.split("|")
    cid = int(cid)
    row = db.CONN.execute("SELECT topic_id FROM clients WHERE id=?", (cid,)).fetchone()
    if not row: 
        bot.answer_callback_query(q.id, "No topic"); return
    tid = row[0]
    # знайдемо останнє ai‑повідомлення
    last_ai = db.CONN.execute("SELECT content FROM messages WHERE client_id=? AND role='assistant' ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
    if not last_ai:
        bot.answer_callback_query(q.id, "No AI draft"); return
    bot.send_message(GROUP_CHAT_ID, md2_escape(last_ai[0]), message_thread_id=tid, parse_mode="MarkdownV2")
    bot.answer_callback_query(q.id, "Sent to client")

@bot.callback_query_handler(func=lambda q: q.data.startswith("ask_designer|"))
def ask_designer(q):
    _, cid = q.data.split("|")
    cid = int(cid)
    row = db.CONN.execute("SELECT designer FROM clients WHERE id=?", (cid,)).fetchone()
    if row and row[0]:
        # вже є дизайнер → відправимо останні нові дані
        send_brief_to_designer(cid, row[0], q)
    else:
        bot.edit_message_text("Choose designer:", q.message.chat.id, q.message.id, reply_markup=choose_designer_kb(cid))
        bot.answer_callback_query(q.id)

@bot.callback_query_handler(func=lambda q: q.data.startswith("set_designer|"))
def set_designer(q):
    _, cid, name = q.data.split("|")
    cid = int(cid)
    db.set_client_designer(cid, name)
    send_brief_to_designer(cid, name, q)

def send_brief_to_designer(cid, designer_name, q):
    chat_id = DESIGNERS.get(designer_name)
    row = db.CONN.execute("SELECT name,profile,topic_id FROM clients WHERE id=?", (cid,)).fetchone()
    msgs = db.CONN.execute("SELECT role,content FROM messages WHERE client_id=? ORDER BY id DESC LIMIT 8", (cid,)).fetchall()
    if not chat_id:
        bot.answer_callback_query(q.id, f"No Telegram ID for {designer_name}"); return
    # коротке ТЗ українською
    title = row[0]; prof=row[1]; tid=row[2]
    body = "\n".join([f"{r}: {c}" for r,c in msgs[::-1]])
    brief = f"Клієнт: {title}\nПрофіль: {prof}\nТред: {topic_link(tid)}\n\nОстанні оновлення:\n{body}"
    bot.send_message(int(chat_id), md2_escape(brief), parse_mode="MarkdownV2")
    bot.edit_message_text(f"✅ Sent brief to {designer_name}", q.message.chat.id, q.message.id)
    bot.answer_callback_query(q.id)

# ======== Завершення проєкту ========
@bot.callback_query_handler(func=lambda q: q.data.startswith("close|"))
def close_flow(q):
    _, cid = q.data.split("|"); cid=int(cid)
    row = db.CONN.execute("SELECT name,profile,topic_id FROM clients WHERE id=?", (cid,)).fetchone()
    name, prof, tid = row
    # контекст для подяки
    summary = f"Client: {name}\nRecent: {db.CONN.execute('SELECT content FROM messages WHERE client_id=? ORDER BY id DESC LIMIT 1',(cid,)).fetchone()[0]}"
    thanks = ai.gen_thanks(prof or "Yurii", summary, SYSTEM_MAP)
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("📤 Send thanks", callback_data=f"close_send|{cid}"),
        types.InlineKeyboardButton("🗄 Archive & delete thread", callback_data=f"close_archive|{cid}")
    )
    db.add_msg(cid, "assistant", thanks)
    bot.send_message(GROUP_CHAT_ID, f"🤖 Thanks draft:\n\n{md2_escape(thanks)}", message_thread_id=tid, parse_mode="MarkdownV2", reply_markup=kb)
    bot.answer_callback_query(q.id)

@bot.callback_query_handler(func=lambda q: q.data.startswith("close_send|"))
def close_send(q):
    _, cid = q.data.split("|"); cid=int(cid)
    tid = db.CONN.execute("SELECT topic_id FROM clients WHERE id=?", (cid,)).fetchone()[0]
    last_ai = db.CONN.execute("SELECT content FROM messages WHERE client_id=? AND role='assistant' ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
    if last_ai:
        bot.send_message(GROUP_CHAT_ID, md2_escape(last_ai[0]), message_thread_id=tid, parse_mode="MarkdownV2")
    bot.answer_callback_query(q.id, "Sent to client")

@bot.callback_query_handler(func=lambda q: q.data.startswith("close_archive|"))
def close_archive(q):
    _, cid = q.data.split("|"); cid=int(cid)
    row = db.CONN.execute("SELECT topic_id FROM clients WHERE id=?", (cid,)).fetchone()
    if row:
        tid = row[0]
        try:
            bot.delete_forum_topic(GROUP_CHAT_ID, tid)
        except Exception:
            pass
    db.set_client_status(cid, "closed")
    bot.edit_message_text("✅ Archived. Thread removed.", q.message.chat.id, q.message.id)
    bot.answer_callback_query(q.id)

# ======== Приват: меню‑кнопки ========
@bot.message_handler(func=lambda m: m.chat.type=="private" and m.text=="🔍 Price grid")
def price_grid(m):
    bot.reply_to(m,
        "• Logo “Clean Start” — $100\n"
        "• Brand Essentials — $220\n"
        "• Ready to Launch — $360\n"
        "• Complete Look — $520\n"
        "• Identity in Action — $1000\n"
        "• Signature System — $1500+",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: m.chat.type=="private", content_types=['text'])
def private_any(m):
    # постійно показуємо меню
    ensure_menu_private(m)

print("Bot is starting…")
bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
