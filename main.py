import os, re, json
from datetime import datetime, timedelta
import telebot
from telebot import types

# ========= ENV =========
TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))        # ОДНА супергрупа (і “cold”, і “теплі”)
DESIGNERS = json.loads(os.getenv("DESIGNERS", "{}"))        # {"Yaryna":"111", ...}
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")

# Тред “Cold — Inbox” у ТІЙ ЖЕ групі
COLD_INBOX_TOPIC = os.getenv("COLD_INBOX_TOPIC")            # наприклад: "5" (id треду)

if not TOKEN:
    raise RuntimeError("ENV BOT_TOKEN is missing")
if not GROUP_CHAT_ID:
    raise RuntimeError("ENV GROUP_CHAT_ID is missing")

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")  # загальний режим

# ========= STATE =========
THREADS = {}               # warm: client -> {...}
CURRENT_CLIENT = {}        # user_id -> client
PROJECTS_BY_DESIGNER = {}  # designer -> [...]
TOPIC_TITLE_CACHE = {}     # title -> topic_id
PROFILES = ["Yurii", "Olena"]

# cold inbox (в одній групі)
LEADS = {}                 # lead_id(=message_id) -> {"client","text","profile","status","created_ts"}

# ========= HELPERS =========
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🆕 Новий клієнт", "📂 Історія переписки")
    kb.row("🧵 Відкрити тему", "🧑‍🎨 Відправити дизайнеру")
    kb.row("📋 Активні клієнти", "✅ Завершити проєкт")
    kb.row("🔍 Перевірити ціну")
    return kb

def topic_link(group_id, topic_id):
    gid = str(group_id)
    abs_id = gid.replace("-100", "") if gid.startswith("-100") else str(abs(group_id))
    return f"https://t.me/c/{abs_id}/{topic_id}"

def md2_escape(s: str) -> str:
    if s is None: return ""
    s = s.replace("\\", "\\\\")
    for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        s = s.replace(ch, '\\' + ch)
    return s

def ensure_client(client):
    return THREADS.setdefault(client, {
        "project": None,
        "history": [],
        "profile": None,
        "designer": None,
        "topic_id": None,
        "status": "active",
        "last_file_sent": None
    })

def ensure_topic_for_client(client, project_title=None):
    info = ensure_client(client)
    if info.get("topic_id"):
        return info["topic_id"]

    title = client if not project_title else f"{client} · {project_title}"
    if title in TOPIC_TITLE_CACHE:
        info["topic_id"] = TOPIC_TITLE_CACHE[title]
        return info["topic_id"]

    topic = bot.create_forum_topic(chat_id=GROUP_CHAT_ID, name=title)
    tid = topic.message_thread_id
    info["topic_id"] = tid
    TOPIC_TITLE_CACHE[title] = tid
    bot.send_message(GROUP_CHAT_ID, f"🧵 Створено тему для *{md2_escape(client)}*.", message_thread_id=tid, parse_mode="MarkdownV2")
    return tid

def push_to_topic(client, text):
    info = ensure_client(client)
    if not info.get("topic_id"):
        ensure_topic_for_client(client, info.get("project"))
    safe = md2_escape(text)
    bot.send_message(GROUP_CHAT_ID, f"✉️ Менеджер:\n\n{safe}", message_thread_id=info["topic_id"], parse_mode="MarkdownV2")

def thread_buttons(client):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🎯 Вибрати акаунт", callback_data=f"profile|{client}"),
        types.InlineKeyboardButton("🧑‍🎨 Відправити дизайнеру", callback_data=f"to_designer|{client}"),
        types.InlineKeyboardButton("📎 Показати історію", callback_data=f"history|{client}"),
        types.InlineKeyboardButton("🔔 Фоллоу-ап (24h)", callback_data=f"followup|{client}")
    )
    if THREADS.get(client, {}).get("topic_id"):
        kb.add(types.InlineKeyboardButton("🧵 Відкрити тему", url=topic_link(GROUP_CHAT_ID, THREADS[client]["topic_id"])))
    return kb

def choose_client_inline(cands):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for name in cands:
        kb.add(types.InlineKeyboardButton(f"📌 {name}", callback_data=f"choose_client|{name}"))
    kb.add(types.InlineKeyboardButton("✍️ Ввести вручну", callback_data="enter_client"))
    return kb

# ========= Heuristics =========
CLIENT_PATTERNS = [
    r"#client\s*:\s*(?P<name>[A-Za-z][\w\s\-\.&]+)",
    r"client\s*:\s*(?P<name>[A-Za-z][\w\s\-\.&]+)",
    r"from\s*:\s*(?P<name>[A-Za-z][\w\s\-\.&]+)",
    r"(?:best|regards|cheers|thanks|sincerely)\s*,?\s*(?P<name>[A-Za-z][\w\.\-\s]+)$",
    r"^—\s*(?P<name>[A-Za-z][\w\.\-\s]+)$",
    r"^-{2,}\s*(?P<name>[A-Za-z][\w\.\-\s]+)$",
]
PROJECT_PATTERNS = [
    r"#project\s*:\s*(?P<title>.+)",
    r"project\s*:\s*(?P<title>.+)",
    r"^subject\s*:\s*(?P<title>.+)$"
]

def _norm(s): return re.sub(r"\s+", " ", s.strip())

def guess_client(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    blob = "\n".join(lines)
    for pat in CLIENT_PATTERNS:
        m = re.search(pat, blob, re.IGNORECASE | re.MULTILINE)
        if m: return _norm(m.group("name"))
    if lines:
        last = lines[-1]
        m = re.match(r"(?P<name>[A-Za-z][A-Za-z \.\-]{1,40})\s*(?:,|CEO|Founder|Manager|Owner)\b", last)
        if m: return _norm(m.group("name"))
    return None

def guess_project(text):
    for pat in PROJECT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m: return _norm(m.group("title"))
    first = text.splitlines()[0].strip() if text.strip() else ""
    if ":" in first and len(first) <= 120:
        return _norm(first)
    return None

def in_cold_inbox(msg):
    return (str(msg.chat.id) == str(GROUP_CHAT_ID)) and (str(msg.message_thread_id or "") == str(COLD_INBOX_TOPIC))

# ========= Commands =========
@bot.message_handler(commands=['start'])
def start_cmd(m):
    bot.send_message(m.chat.id, "👋 Бот запущений. Кидай текст клієнта — створю тему і збережу історію.", reply_markup=main_menu())

@bot.message_handler(commands=['health'])
def health(m): bot.reply_to(m, "✅ alive", reply_markup=main_menu())

@bot.message_handler(commands=['whoami'])
def whoami(m): bot.reply_to(m, f"Your ID: {m.from_user.id}", reply_markup=main_menu())

@bot.message_handler(commands=['getchatid'])
def get_chat_id(m): bot.reply_to(m, f"chat.id = {m.chat.id}", reply_markup=main_menu())

# без Markdown, щоб не ламався _
@bot.message_handler(commands=['debug_here'])
def debug_here(m):
    txt = f"chat.id={m.chat.id}\nthread_id={getattr(m,'message_thread_id',None)}\nfrom_user={m.from_user.id}"
    bot.send_message(m.chat.id, txt, parse_mode=None)

@bot.message_handler(commands=['projects_by'])
def projects_by(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) == 1:
        bot.reply_to(m, "Вкажи ім’я дизайнера. Приклад: `/projects_by Yaryna`", parse_mode="Markdown", reply_markup=main_menu()); return
    name = parts[1].strip()
    items = PROJECTS_BY_DESIGNER.get(name, [])
    if items:
        bot.reply_to(m, "📋 Завдання для *{}*:\n\n{}".format(name, "\n\n".join(items[-10:])), parse_mode="Markdown", reply_markup=main_menu())
    else:
        bot.reply_to(m, f"📭 Немає активних завдань для {name}.", reply_markup=main_menu())

# ========= COLD (в одній групі, тема “Cold — Inbox”) =========
@bot.message_handler(func=lambda m: in_cold_inbox(m), content_types=['text'])
def cold_inbox(m):
    text = m.text or ""
    # дозволимо тригер по хештегу #cold або будь-який текст у цій темі
    if "#cold" in text.lower() or True:
        lead_id = m.message_id
        client = guess_client(text) or "(без імені)"
        LEADS[lead_id] = {
            "client": client,
            "text": text,
            "profile": None,
            "status": "new",
            "created_ts": datetime.utcnow().isoformat(),
        }
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("Yurii", callback_data=f"cold_setprof|{lead_id}|Yurii"),
            types.InlineKeyboardButton("Olena", callback_data=f"cold_setprof|{lead_id}|Olena"),
        )
        kb.add(types.InlineKeyboardButton("🧵 Створити проєкт‑тред", callback_data=f"cold_convert|{lead_id}"))
        bot.reply_to(m, f"📌 Лід збережено (id={lead_id}). Клієнт: *{md2_escape(client)}*.\nВибери профіль та/або створи тред.", reply_markup=kb, parse_mode="MarkdownV2")

# ========= WARM (приватні чати із менеджером) =========
@bot.message_handler(func=lambda m: True, content_types=['text'])
def any_text(m):
    # у групі обробляємо лише Cold — Inbox; інші групові ігноруємо
    if m.chat.type in ("group", "supergroup"):
        return

    text = m.text or ""
    current = CURRENT_CLIENT.get(m.from_user.id)
    if current:
        info = ensure_client(current)
        info["history"].append((datetime.utcnow().isoformat(), text))
        if len(text.strip()) < 3:
            bot.reply_to(m, f"✅ Тред *{current}* вибрано. Кинь повідомлення клієнта.", reply_markup=thread_buttons(current))
            return
        try:
            ensure_topic_for_client(current, info.get("project"))
            push_to_topic(current, text)
        except Exception:
            pass
        bot.reply_to(m, f"✅ Додано в тред *{current}*.", reply_markup=thread_buttons(current))
        return

    client = guess_client(text)
    project = guess_project(text)
    if client:
        info = ensure_client(client)
        if project: info["project"] = project
        info["history"].append((datetime.utcnow().isoformat(), text))
        CURRENT_CLIENT[m.from_user.id] = client
        try:
            tid = ensure_topic_for_client(client, info.get("project"))
            link = topic_link(GROUP_CHAT_ID, tid)
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🧵 Відкрити тему", url=link))
            bot.reply_to(m, f"✅ Створив/оновив тред *{client}*.", reply_markup=main_menu())
            bot.send_message(m.chat.id, "Швидкий перехід:", reply_markup=kb)
        except Exception:
            bot.reply_to(m, f"✅ Збережено в тред *{client}*.", reply_markup=thread_buttons(client))
        return

    existing = sorted(THREADS.keys())
    if existing:
        bot.reply_to(m, "Не розпізнав клієнта. Обери зі списку або введи вручну:", reply_markup=choose_client_inline(existing))
    else:
        msg = bot.reply_to(m, "Як називається клієнт? (буде створено новий тред)", reply_markup=types.ForceReply())
        bot.register_for_reply(msg, _set_client_name_step)

def _set_client_name_step(reply_msg):
    name = (reply_msg.text or "").strip()
    if not name:
        bot.reply_to(reply_msg, "Порожнє ім’я. Спробуй ще раз.", reply_markup=main_menu()); return
    ensure_client(name)
    CURRENT_CLIENT[reply_msg.from_user.id] = name
    try:
        tid = ensure_topic_for_client(name, THREADS[name].get("project"))
        link = topic_link(GROUP_CHAT_ID, tid)
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🧵 Відкрити тему", url=link))
        bot.reply_to(reply_msg, f"🆕 Створив клієнта *{name}*. Кинь перше повідомлення.", reply_markup=main_menu())
        bot.send_message(reply_msg.chat.id, "Швидкий перехід:", reply_markup=kb)
    except Exception as e:
        bot.reply_to(reply_msg, f"⚠️ Не вдалось створити тему: {e}", reply_markup=main_menu())

# ========= CALLBACKS =========
@bot.callback_query_handler(func=lambda c: True)
def cb(q):
    data = (q.data or "").split("|")
    action = data[0]

    # ----- warm -----
    if action == "choose_client":
        client = data[1]
        ensure_client(client)
        CURRENT_CLIENT[q.from_user.id] = client
        bot.edit_message_text(f"✅ Обрано клієнта: *{md2_escape(client)}*. Надішли повідомлення — додам в історію.",
                              q.message.chat.id, q.message.id, parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id); return

    if action == "enter_client":
        msg = bot.send_message(q.message.chat.id, "Введи ім’я клієнта:", reply_markup=types.ForceReply())
        bot.register_for_reply(msg, _set_client_name_step)
        bot.answer_callback_query(q.id); return

    if action == "history":
        client = data[1]
        hist = THREADS.get(client, {}).get("history", [])
        if not hist:
            bot.answer_callback_query(q.id, "Історія порожня."); return
        body = "\n\n".join([f"{t}:\n{m}" for t,m in hist])[-3800:]
        bot.send_message(q.message.chat.id, f"🕓 Історія для *{md2_escape(client)}*:\n\n{md2_escape(body)}", parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id); return

    if action == "profile":
        client = data[1]
        kb = types.InlineKeyboardMarkup(row_width=2)
        for p in PROFILES:
            kb.add(types.InlineKeyboardButton(p, callback_data=f"setprofile|{client}|{p}"))
        bot.send_message(q.message.chat.id, f"Для *{md2_escape(client)}*: вибери профіль:", reply_markup=kb, parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id); return

    if action == "setprofile":
        _, client, prof = data
        ensure_client(client); THREADS[client]["profile"] = prof
        bot.send_message(q.message.chat.id, f"✅ Профіль *{md2_escape(prof)}* встановлено для *{md2_escape(client)}*", parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id); return

    if action == "to_designer":
        client = data[1]
        if not DESIGNERS:
            bot.send_message(q.message.chat.id, "DESIGNERS порожній. Додай JSON з іменами та Telegram ID.")
            bot.answer_callback_query(q.id); return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for name in DESIGNERS.keys():
            kb.add(types.InlineKeyboardButton(name, callback_data=f"send_to|{client}|{name}"))
        bot.send_message(q.message.chat.id, f"Кому надіслати тред *{md2_escape(client)}*?", reply_markup=kb, parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id); return

    if action == "send_to":
        _, client, designer = data
        hist = THREADS.get(client, {}).get("history", [])
        last_msg = hist[-1][1] if hist else "Без повідомлень"
        chat_id = DESIGNERS.get(designer)
        if chat_id:
            PROJECTS_BY_DESIGNER.setdefault(designer, []).append(f"{client}: {last_msg}")
            bot.send_message(chat_id, f"🧾 {md2_escape(client)}\n\n{md2_escape(last_msg)}", parse_mode="MarkdownV2")
            bot.send_message(q.message.chat.id, f"✅ Надіслано *{md2_escape(designer)}*", parse_mode="MarkdownV2")
        else:
            bot.send_message(q.message.chat.id, f"⚠️ Для '{designer}' немає Telegram ID у ENV DESIGNERS.")
        bot.answer_callback_query(q.id); return

    if action == "followup":
        client = data[1]
        info = THREADS.get(client, {})
        last_file = info.get("last_file_sent")
        if last_file and datetime.utcnow() - last_file > timedelta(hours=24):
            bot.send_message(q.message.chat.id, f"🔔 24 години минули: нагадай клієнту *{md2_escape(client)}*.", parse_mode="MarkdownV2")
        else:
            bot.send_message(q.message.chat.id, "🕓 Ще не минуло 24 год або файл не відправлявся.")
        bot.answer_callback_query(q.id); return

    if action == "close":
        client = data[1]
        if client in THREADS:
            THREADS[client]["status"] = "closed"
            bot.send_message(q.message.chat.id, f"✅ Тред *{md2_escape(client)}* закрито.", parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id); return

    # ----- COLD -----
    if action == "cold_setprof":
        _, lead_id, prof = data
        lead_id = int(lead_id)
        lead = LEADS.get(lead_id)
        if not lead:
            bot.answer_callback_query(q.id, "Лід не знайдено."); return
        lead["profile"] = prof
        bot.edit_message_text(f"Лід id={lead_id}. Профіль: *{md2_escape(prof)}*.\nГотово до створення проєкту.",
                              q.message.chat.id, q.message.id, parse_mode="MarkdownV2")
        bot.answer_callback_query(q.id); return

    if action == "cold_convert":
        _, lead_id = data
        lead_id = int(lead_id)
        lead = LEADS.get(lead_id)
        if not lead:
            bot.answer_callback_query(q.id, "Лід не знайдено."); return

        client = lead["client"] if lead["client"] != "(без імені)" else f"Lead {lead_id}"
        tid = ensure_topic_for_client(client)
        summary = (
            f"*Lead → Project*\n"
            f"• ID: `{lead_id}`\n"
            f"• Client: *{md2_escape(client)}*\n"
            f"• Profile: *{md2_escape(lead.get('profile') or '—')}*\n"
            f"• Created: `{lead['created_ts']}`\n\n"
            f"{md2_escape(lead['text'])}"
        )
        bot.send_message(GROUP_CHAT_ID, summary, message_thread_id=tid, parse_mode="MarkdownV2")

        lead["status"] = "archived"
        link = topic_link(GROUP_CHAT_ID, tid)
        bot.edit_message_text(f"✅ Проєкт‑тред створено: {link}", q.message.chat.id, q.message.id, disable_web_page_preview=True)
        bot.answer_callback_query(q.id); return

# ========= RUN =========
print(f"Bot is starting… GROUP_CHAT_ID={GROUP_CHAT_ID} COLD_INBOX_TOPIC={COLD_INBOX_TOPIC}")
bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
