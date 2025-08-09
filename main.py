import os, re, json
from datetime import datetime, timedelta
import telebot
from telebot import types

# ========= ENV =========
TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))       # SDS Projekts (теплі)
DESIGNERS = json.loads(os.getenv("DESIGNERS", "{}"))
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")

# ----- COLD (окрема група + одна тема Inbox) -----
COLD_GROUP_ID = int(os.getenv("COLD_GROUP_ID", "0"))       # SDS Cold Leads
COLD_INBOX_TOPIC = os.getenv("COLD_INBOX_TOPIC")           # message_thread_id теми "Cold — Inbox" (строка або число)

if not TOKEN:
    raise RuntimeError("ENV BOT_TOKEN is missing")

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# ========= STATE =========
THREADS = {}                 # client -> {...}
CURRENT_CLIENT = {}          # user_id -> client
PROJECTS_BY_DESIGNER = {}    # designer -> ["Client: last msg", ...]
TOPIC_TITLE_CACHE = {}       # title -> topic_id (антидублювання)
PROFILES = ["Yurii", "Olena"]

# ========= UI =========
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🆕 Новий клієнт", "📂 Історія переписки")
    kb.row("🧵 Відкрити тему", "🧑‍🎨 Відправити дизайнеру")
    kb.row("📋 Активні клієнти", "✅ Завершити проєкт")
    kb.row("🔍 Перевірити ціну")
    return kb

# ========= Utils (теплі) =========
def topic_link(group_id, topic_id):
    gid = str(group_id)
    abs_id = gid.replace("-100", "") if gid.startswith("-100") else str(abs(group_id))
    return f"https://t.me/c/{abs_id}/{topic_id}"

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
    if not GROUP_CHAT_ID:
        raise RuntimeError("ENV GROUP_CHAT_ID is missing")

    title = client if not project_title else f"{client} · {project_title}"
    if title in TOPIC_TITLE_CACHE:
        info["topic_id"] = TOPIC_TITLE_CACHE[title]
        return info["topic_id"]

    topic = bot.create_forum_topic(chat_id=GROUP_CHAT_ID, name=title)
    topic_id = topic.message_thread_id
    info["topic_id"] = topic_id
    TOPIC_TITLE_CACHE[title] = topic_id

    bot.send_message(GROUP_CHAT_ID, f"🧵 Створено тему для *{client}*.", message_thread_id=topic_id)
    return topic_id

def push_to_topic(client, text):
    info = ensure_client(client)
    if not info.get("topic_id"):
        ensure_topic_for_client(client, info.get("project"))
    bot.send_message(GROUP_CHAT_ID, f"✉️ Менеджер:\n\n{text}", message_thread_id=info["topic_id"])

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

# Діагностика в групі/темі
@bot.message_handler(commands=['debug_here'])
def debug_here(m):
    bot.reply_to(m, f"chat.id={m.chat.id}\nthread_id={m.message_thread_id}")

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

# ========= Меню (теплі) =========
@bot.message_handler(func=lambda m: m.text == "🆕 Новий клієнт")
def new_client_btn(m):
    force = types.ForceReply(input_field_placeholder="Введи ім’я клієнта (наприклад: Acme Inc.)")
    msg = bot.reply_to(m, "Як називається клієнт? (створю тему та тред)", reply_markup=force)
    bot.register_for_reply(msg, _set_client_name_step)

def _set_client_name_step(reply_msg):
    name = (reply_msg.text or "").strip()
    if not name:
        bot.reply_to(reply_msg, "Порожнє ім’я. Спробуй ще раз.", reply_markup=main_menu()); return
    ensure_client(name)
    CURRENT_CLIENT[reply_msg.from_user.id] = name
    try:
        topic_id = ensure_topic_for_client(name, THREADS[name].get("project"))
        link = topic_link(GROUP_CHAT_ID, topic_id)
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🧵 Відкрити тему", url=link))
        bot.reply_to(reply_msg, f"🆕 Створив клієнта *{name}*. Надішли повідомлення клієнта — додам у тред.", reply_markup=main_menu())
        bot.send_message(reply_msg.chat.id, "Швидкий перехід:", reply_markup=kb)
    except Exception as e:
        bot.reply_to(reply_msg, f"⚠️ Не вдалось створити тему (GROUP_CHAT_ID?): {e}", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📂 Історія переписки")
def history_btn(m):
    if not THREADS:
        bot.reply_to(m, "Поки що немає жодного клієнта.", reply_markup=main_menu()); return
    names = sorted(THREADS.keys())
    bot.reply_to(m, "Вибери клієнта:", reply_markup=choose_client_inline(names))

@bot.message_handler(func=lambda m: m.text == "🧵 Відкрити тему")
def open_topic_btn(m):
    client = CURRENT_CLIENT.get(m.from_user.id)
    if not client:
        bot.reply_to(m, "Спершу обери/створи клієнта (кнопка “🆕 Новий клієнт”).", reply_markup=main_menu()); return
    info = ensure_client(client)
    try:
        tid = ensure_topic_for_client(client, info.get("project"))
        link = topic_link(GROUP_CHAT_ID, tid)
        bot.send_message(m.chat.id, "Ось тема:", reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🧵 Перейти", url=link)
        ))
    except Exception as e:
        bot.reply_to(m, f"⚠️ Не вдалось відкрити тему: {e}", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "🧑‍🎨 Відправити дизайнеру")
def send_designer_btn(m):
    if not THREADS:
        bot.reply_to(m, "Немає тредів. Спочатку створіть клієнта.", reply_markup=main_menu()); return
    client = CURRENT_CLIENT.get(m.from_user.id)
    if not client:
        names = sorted(THREADS.keys())
        bot.reply_to(m, "Обери клієнта:", reply_markup=choose_client_inline(names)); return
    if not DESIGNERS:
        bot.reply_to(m, "ENV DESIGNERS порожній. Додай JSON з іменами та Telegram ID.", reply_markup=main_menu()); return
    kb = types.InlineKeyboardMarkup(row_width=1)
    for d in DESIGNERS.keys():
        kb.add(types.InlineKeyboardButton(d, callback_data=f"send_to|{client}|{d}"))
    bot.reply_to(m, f"Кому надіслати тред *{client}*?", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📋 Активні клієнти")
def active_btn(m):
    act = [n for n,t in THREADS.items() if t.get("status")!="closed"]
    if not act:
        bot.reply_to(m, "Активних немає.", reply_markup=main_menu()); return
    kb = types.InlineKeyboardMarkup(row_width=1)
    for n in act:
        tid = THREADS[n].get("topic_id")
        if tid:
            kb.add(types.InlineKeyboardButton(f"🧵 {n}", url=topic_link(GROUP_CHAT_ID, tid)))
        else:
            kb.add(types.InlineKeyboardButton(f"🧵 {n} (створити тему)", callback_data=f"mk_topic|{n}"))
    bot.reply_to(m, "Активні клієнти:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "✅ Завершити проєкт")
def close_btn(m):
    if not THREADS:
        bot.reply_to(m, "Немає активних тредів.", reply_markup=main_menu()); return
    names = [n for n,t in THREADS.items() if t.get("status")!="closed"]
    if not names:
        bot.reply_to(m, "Усі вже закриті.", reply_markup=main_menu()); return
    kb = types.InlineKeyboardMarkup(row_width=1)
    for n in names:
        kb.add(types.InlineKeyboardButton(f"✅ Закрити: {n}", callback_data=f"close|{n}"))
    bot.reply_to(m, "Оберіть тред для закриття:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🔍 Перевірити ціну")
def price_btn(m):
    bot.reply_to(
        m,
        "Швидка сітка:\n"
        "• Logo “Clean Start” — $100\n"
        "• Brand Essentials — $220\n"
        "• Ready to Launch — $360\n"
        "• Complete Look — $520\n"
        "• Identity in Action — $1000\n"
        "• Signature System — $1500+",
        reply_markup=main_menu()
    )

# ========= Гард: ігноруємо ВСІ групові меседжі, крім Cold — Inbox =========
def in_cold_inbox(msg):
    if not (COLD_GROUP_ID and COLD_INBOX_TOPIC):
        return False
    if msg.chat.id != COLD_GROUP_ID:
        return False
    return str(msg.message_thread_id or "") == str(COLD_INBOX_TOPIC)

# ========= COLD: тільки “Cold — Inbox” =========
@bot.message_handler(func=lambda m: in_cold_inbox(m), content_types=['text'])
def cold_inbox_handler(m):
    kb_choose_prof = types.InlineKeyboardMarkup(row_width=2)
    kb_choose_prof.add(
        types.InlineKeyboardButton("Yurii", callback_data=f"cold_setprof|Yurii|{m.message_thread_id}"),
        types.InlineKeyboardButton("Olena", callback_data=f"cold_setprof|Olena|{m.message_thread_id}")
    )
    bot.reply_to(m, "Який профіль краще подати на цей лід?", reply_markup=kb_choose_prof)

# ========= ТЕПЛИЙ: текст лише з приватів (і з груп — НІ, окрім cold inbox) =========
@bot.message_handler(func=lambda m: True, content_types=['text'])
def any_text(m):
    # 1) Якщо Cold — Inbox, нічого тут не робимо (обробив попередній хендлер)
    if in_cold_inbox(m):
        return
    # 2) Якщо це будь-яка група/супергрупа — ігноруємо, щоб не лилося в останнього клієнта
    if m.chat.type in ("group", "supergroup"):
        return

    text = m.text or ""
    current = CURRENT_CLIENT.get(m.from_user.id)
    if current:
        info = ensure_client(current)
        info["history"].append((datetime.utcnow().isoformat(), text))
        # короткі/службові — не шлемо в тему
        if len(text.strip()) < 3:
            kb = thread_buttons(current)
            bot.reply_to(m, f"✅ Тред *{current}* вибрано. Надішли повідомлення клієнта для історії.", reply_markup=kb)
            return
        try:
            ensure_topic_for_client(current, info.get("project"))
            push_to_topic(current, text)
        except Exception:
            pass
        kb = thread_buttons(current)
        bot.reply_to(m, f"✅ Додано в тред *{current}*.", reply_markup=kb)
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
            kb_open = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🧵 Відкрити тему", url=link))
            bot.reply_to(m, f"✅ Створив/оновив тред *{client}*.", reply_markup=main_menu())
            bot.send_message(m.chat.id, "Швидкий перехід:", reply_markup=kb_open)
        except Exception:
            bot.reply_to(m, f"✅ Збережено в тред *{client}*.", reply_markup=thread_buttons(client))
        return

    existing = sorted(THREADS.keys())
    if existing:
        bot.reply_to(m, "Не розпізнав клієнта. Обери зі списку або введи вручну:", reply_markup=choose_client_inline(existing))
    else:
        force = types.ForceReply(input_field_placeholder="Введи ім’я клієнта (наприклад: Acme Inc.)")
        msg = bot.reply_to(m, "Як називається клієнт? (буде створено новий тред)", reply_markup=force)
        bot.register_for_reply(msg, _set_client_name_step)

# ========= CALLBACKS =========
@bot.callback_query_handler(func=lambda c: True)
def cb(q):
    data = (q.data or "").split("|")
    action = data[0]

    # ---- ТЕПЛИЙ ----
    if action == "choose_client":
        client = data[1]
        ensure_client(client)
        CURRENT_CLIENT[q.from_user.id] = client
        bot.edit_message_text(f"✅ Обрано клієнта: *{client}*. Надішли повідомлення — додам в історію.",
                              q.message.chat.id, q.message.id)
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
        text = "\n\n".join([f"{t}:\n{m}" for t,m in hist])[-4000:]
        bot.send_message(q.message.chat.id, f"🕓 Історія для *{client}*:\n\n{text}")
        bot.answer_callback_query(q.id); return

    if action == "profile":
        client = data[1]
        kb = types.InlineKeyboardMarkup(row_width=2)
        for p in PROFILES:
            kb.add(types.InlineKeyboardButton(p, callback_data=f"setprofile|{client}|{p}"))
        bot.send_message(q.message.chat.id, f"Для *{client}*: вибери профіль:", reply_markup=kb)
        bot.answer_callback_query(q.id); return

    if action == "setprofile":
        _, client, prof = data
        ensure_client(client); THREADS[client]["profile"] = prof
        bot.send_message(q.message.chat.id, f"✅ Профіль *{prof}* встановлено для *{client}*  #профіль_{prof}")
        bot.answer_callback_query(q.id); return

    if action == "to_designer":
        client = data[1]
        if not DESIGNERS:
            bot.send_message(q.message.chat.id, "DESIGNERS порожній. Додай JSON з іменами та Telegram ID.")
            bot.answer_callback_query(q.id); return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for name in DESIGNERS.keys():
            kb.add(types.InlineKeyboardButton(name, callback_data=f"send_to|{client}|{name}"))
        bot.send_message(q.message.chat.id, f"Кому надіслати тред *{client}*?", reply_markup=kb)
        bot.answer_callback_query(q.id); return

    if action == "send_to":
        _, client, designer = data
        hist = THREADS.get(client, {}).get("history", [])
        last_msg = hist[-1][1] if hist else "Без повідомлень"
        chat_id = DESIGNERS.get(designer)
        if chat_id:
            PROJECTS_BY_DESIGNER.setdefault(designer, []).append(f"{client}: {last_msg}")
            bot.send_message(chat_id, f"🧾 {client}\n\n{last_msg}")
            bot.send_message(q.message.chat.id, f"✅ Надіслано *{designer}*  #дизайнер_{designer}")
        else:
            bot.send_message(q.message.chat.id, f"⚠️ Для '{designer}' немає Telegram ID у ENV DESIGNERS.")
        bot.answer_callback_query(q.id); return

    if action == "followup":
        client = data[1]
        info = THREADS.get(client, {})
        last_file = info.get("last_file_sent")
        if last_file and datetime.utcnow() - last_file > timedelta(hours=24):
            bot.send_message(q.message.chat.id, f"🔔 24 години минули: нагадай клієнту *{client}*.")
        else:
            bot.send_message(q.message.chat.id, "🕓 Ще не минуло 24 год або файл не відправлявся.")
        bot.answer_callback_query(q.id); return

    if action == "close":
        client = data[1]
        if client in THREADS:
            THREADS[client]["status"] = "closed"
            bot.send_message(q.message.chat.id, f"✅ Тред *{client}* закрито.")
        bot.answer_callback_query(q.id); return

    # ---- COLD (крок 1) ----
    if action == "cold_setprof":
        _, prof, topic_id = data
        bot.edit_message_text(f"Профіль обрано: *{prof}*. Далі згенеруємо пітч і перевірку ціни у кроці 2.",
                              q.message.chat.id, q.message.id)
        bot.answer_callback_query(q.id); return

# ========= RUN =========
print(f"Bot is starting… GROUP_CHAT_ID={GROUP_CHAT_ID} COLD_GROUP_ID={COLD_GROUP_ID} COLD_INBOX_TOPIC={COLD_INBOX_TOPIC}")
bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
