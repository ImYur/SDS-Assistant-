import os, json, re
from datetime import datetime, timedelta
from telebot import types

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DESIGNERS = json.loads(os.getenv("DESIGNERS", "{}"))
MANAGERS = {OWNER_ID}  # можна додати ще ID менеджерів
PROFILES = ["Yurii", "Olena"]

# Пам'ять (in‑memory)
THREADS = {}  # key: client_name -> {"project": str|None, "history": [...], "profile":..., "designer":..., "last_file_sent": dt}
PROJECTS_BY_DESIGNER = {}

# ---------- утиліти ----------

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

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())

def guess_client(text: str):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    blob = "\n".join(lines)

    for pat in CLIENT_PATTERNS:
        m = re.search(pat, blob, re.IGNORECASE | re.MULTILINE)
        if m:
            return _norm(m.group("name"))
    # просте евристичне: якщо є підпис у кінці “Name, Title”
    if lines:
        last = lines[-1]
        m = re.match(r"(?P<name>[A-Za-z][A-Za-z \.\-]{1,40})\s*(?:,|CEO|Founder|Manager|Owner)\b", last)
        if m:
            return _norm(m.group("name"))
    return None

def guess_project(text: str):
    blob = text
    for pat in PROJECT_PATTERNS:
        m = re.search(pat, blob, re.IGNORECASE | re.MULTILINE)
        if m:
            return _norm(m.group("title"))
    # якщо в першому рядку є «:» — беремо як заголовок
    first = text.splitlines()[0].strip() if text.strip() else ""
    if ":" in first and len(first) <= 120:
        return _norm(first)
    return None

def thread_buttons(client_name):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🎯 Вибрати акаунт", callback_data=f"profile|{client_name}"),
        types.InlineKeyboardButton("🧑‍🎨 Відправити дизайнеру", callback_data=f"to_designer|{client_name}"),
        types.InlineKeyboardButton("📎 Показати історію", callback_data=f"history|{client_name}"),
        types.InlineKeyboardButton("🔔 Фоллоу-ап (24h)", callback_data=f"followup|{client_name}")
    )
    return kb

def choose_client_buttons(candidates):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for name in candidates:
        kb.add(types.InlineKeyboardButton(f"📌 {name}", callback_data=f"choose_client|{name}"))
    kb.add(types.InlineKeyboardButton("✍️ Ввести вручну", callback_data="enter_client"))
    return kb

# ---------- основні хендлери ----------

def setup_handlers(bot):

    @bot.message_handler(commands=['start'])
    def handle_start(message):
        bot.reply_to(message, "👋 Привіт! Надсилай текст діалогу з клієнтом/інвайт — я створю або продовжу тред по *клієнту*, а не по твоєму акаунту.", parse_mode="Markdown")

    @bot.message_handler(commands=['projects_by'])
    def projects_by(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) == 1:
            bot.reply_to(message, "Вкажи ім’я дизайнера. Приклад: `/projects_by Yaryna`", parse_mode="Markdown")
            return
        name = parts[1].strip()
        items = PROJECTS_BY_DESIGNER.get(name, [])
        if items:
            bot.reply_to(message, "📋 Завдання для *{}*:\n\n{}".format(name, "\n\n".join(items[-10:])), parse_mode="Markdown")
        else:
            bot.reply_to(message, f"📭 Немає активних завдань для {name}.")

    # головний хендлер тексту від менеджера
    @bot.message_handler(func=lambda m: m.from_user.id in MANAGERS, content_types=['text'])
    def handle_manager_text(message):
        text = message.text or ""
        # 1) спробуємо знайти клієнта/проєкт із тексту
        client = guess_client(text)
        project = guess_project(text)

        if client:
            client_key = client
            thread = THREADS.setdefault(client_key, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None})
            if project:
                thread["project"] = project
            thread["history"].append((datetime.utcnow().isoformat(), text))

            tags = f"#client_{client.replace(' ', '_')}"
            if thread.get("project"):
                tags += f"  #project_{thread['project'].replace(' ', '_')}"
            bot.reply_to(
                message,
                f"✅ Збережено в тред *{client}*.\n{tags}",
                parse_mode="Markdown",
                reply_markup=thread_buttons(client_key)
            )
            return

        # 2) якщо не вдалось — показати вибір з існуючих + “ввести вручну”
        existing = sorted(THREADS.keys())
        if existing:
            bot.reply_to(message, "Не розпізнав клієнта. Обери зі списку або введи вручну:", reply_markup=choose_client_buttons(existing))
        else:
            # немає тредів — просимо ввести ім'я
            force = types.ForceReply(selective=False, input_field_placeholder="Введи ім’я клієнта (наприклад: Acme Inc.)")
            m = bot.reply_to(message, "Як називається клієнт? (буде створено новий тред)", reply_markup=force)
            bot.register_for_reply(m, _set_client_name_step)

    # введення імені вручну (ForceReply)
    def _set_client_name_step(reply_msg):
        name = reply_msg.text.strip()
        if not name:
            bot.reply_to(reply_msg, "Порожнє ім’я. Спробуй ще раз.")
            return
        THREADS.setdefault(name, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None})
        bot.reply_to(reply_msg, f"🆕 Створив тред для клієнта *{name}*.\nТепер надішли повідомлення клієнта ще раз — я додам у цей тред.", parse_mode="Markdown")

    # ---------- callbacks ----------

    @bot.callback_query_handler(func=lambda c: c.data.startswith("choose_client|"))
    def cb_choose_client(query):
        _, client_name = query.data.split("|", 1)
        THREADS.setdefault(client_name, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None})
        bot.edit_message_text(
            f"✅ Обрано клієнта: *{client_name}*.\nНадішли повідомлення клієнта — я додам його в історію.",
            chat_id=query.message.chat.id, message_id=query.message.id, parse_mode="Markdown"
        )
        bot.answer_callback_query(query.id)

    @bot.callback_query_handler(func=lambda c: c.data == "enter_client")
    def cb_enter_client(query):
        force = types.ForceReply(selective=False, input_field_placeholder="Введи ім’я клієнта")
        m = bot.send_message(query.message.chat.id, "Введи ім’я клієнта:", reply_markup=force)
        bot.register_for_reply(m, _set_client_name_step)
        bot.answer_callback_query(query.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("history|"))
    def cb_history(query):
        client_name = query.data.split("|", 1)[1]
        hist = THREADS.get(client_name, {}).get("history", [])
        if not hist:
            bot.answer_callback_query(query.id, "Історія порожня.")
            return
        text = "\n\n".join([f"{t}:\n{m}" for t, m in hist])[-4000:]
        bot.send_message(query.message.chat.id, f"🕓 Історія для *{client_name}*:\n\n{text}", parse_mode="Markdown")
        bot.answer_callback_query(query.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("profile|"))
    def cb_profile(query):
        client_name = query.data.split("|", 1)[1]
        kb = types.InlineKeyboardMarkup(row_width=2)
        for p in PROFILES:
            kb.add(types.InlineKeyboardButton(p, callback_data=f"setprofile|{client_name}|{p}"))
        bot.send_message(query.message.chat.id, f"Для *{client_name}*: вибери профіль:", parse_mode="Markdown", reply_markup=kb)
        bot.answer_callback_query(query.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("setprofile|"))
    def cb_setprofile(query):
        _, client_name, prof = query.data.split("|", 2)
        THREADS.setdefault(client_name, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None})
        THREADS[client_name]["profile"] = prof
        bot.send_message(query.message.chat.id, f"✅ Профіль *{prof}* встановлено для *{client_name}*  #профіль_{prof}", parse_mode="Markdown")
        bot.answer_callback_query(query.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("to_designer|"))
    def cb_to_designer(query):
        client_name = query.data.split("|", 1)[1]
        if not DESIGNERS:
            bot.send_message(query.message.chat.id, "Список дизайнерів порожній (ENV `DESIGNERS`).")
            bot.answer_callback_query(query.id); return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for name in DESIGNERS.keys():
            kb.add(types.InlineKeyboardButton(name, callback_data=f"send_to|{client_name}|{name}"))
        bot.send_message(query.message.chat.id, f"Кому надіслати тред *{client_name}*?", parse_mode="Markdown", reply_markup=kb)
        bot.answer_callback_query(query.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("send_to|"))
    def cb_send_to(query):
        _, client_name, designer = query.data.split("|", 2)
        hist = THREADS.get(client_name, {}).get("history", [])
        last_msg = hist[-1][1] if hist else "Без повідомлень"
        chat_id = DESIGNERS.get(designer)
        if chat_id:
            PROJECTS_BY_DESIGNER.setdefault(designer, []).append(f"{client_name}: {last_msg}")
            bot.send_message(chat_id, f"🧾 {client_name}\n\n{last_msg}")
            bot.send_message(query.message.chat.id, f"✅ Надіслано *{designer}*  #дизайнер_{designer}", parse_mode="Markdown")
        else:
            bot.send_message(query.message.chat.id, f"⚠️ Для '{designer}' не знайдено Telegram ID у `DESIGNERS`.")
        bot.answer_callback_query(query.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("followup|"))
    def cb_followup(query):
        client_name = query.data.split("|", 1)[1]
        info = THREADS.get(client_name, {})
        last_file = info.get("last_file_sent")
        if last_file and datetime.utcnow() - last_file > timedelta(hours=24):
            bot.send_message(query.message.chat.id, f"🔔 24 години минули: нагадай клієнту *{client_name}*.")
        else:
            bot.send_message(query.message.chat.id, "🕓 Ще не минуло 24 год або файл не надсилався.")
        bot.answer_callback_query(query.id)
