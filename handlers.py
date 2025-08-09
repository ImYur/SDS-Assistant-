import os, json, re
from datetime import datetime, timedelta
from telebot import types

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
# приклад ENV: {"Yaryna Panchyshyn":"111","Yulia Sytnyk":"222","Kateryna Kucher":"333"}
DESIGNERS = json.loads(os.getenv("DESIGNERS", "{}"))

PROFILES = ["Yurii", "Olena"]

# ---- Пам'ять у процесі ----
THREADS = {}                # client_name -> {"project", "history", "profile", "designer", "last_file_sent", "status"}
PROJECTS_BY_DESIGNER = {}   # designer_name -> [items]

# ---- Постійне меню (reply keyboard) ----
MENU_BTNS = [
    ["🆕 Новий клієнт", "📂 Історія переписки"],
    ["🧑‍🎨 Відправити дизайнеру", "✅ Завершити проєкт"],
    ["🔍 Перевірити ціну", "📋 Активні роботи"],
]
REPLY_KB = types.ReplyKeyboardMarkup(resize_keyboard=True)
for row in MENU_BTNS:
    REPLY_KB.row(*row)

# ---- Евристики витягування клієнта/проєкту з тексту ----
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
    if lines:
        last = lines[-1]
        m = re.match(r"(?P<name>[A-Za-z][A-Za-z \.\-]{1,40})\s*(?:,|CEO|Founder|Manager|Owner)\b", last)
        if m:
            return _norm(m.group("name"))
    return None

def guess_project(text: str):
    for pat in PROJECT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return _norm(m.group("title"))
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

def setup_handlers(bot):
    # ===== Команди =====
    @bot.message_handler(commands=['start'])
    def start(m):
        bot.send_message(
            m.chat.id,
            "👋 Привіт! Я Stylus Assistant. Кидай текст із Upwork (можна з підписом / тегами типу `#client: John | #project: Logo`).",
            reply_markup=REPLY_KB
        )

    @bot.message_handler(commands=['health'])
    def health(m):
        bot.reply_to(m, "✅ alive", reply_markup=REPLY_KB)

    @bot.message_handler(commands=['whoami'])
    def whoami(m):
        bot.reply_to(m, f"Your ID: {m.from_user.id}", reply_markup=REPLY_KB)

    @bot.message_handler(commands=['projects_by'])
    def projects_by(m):
        parts = m.text.split(maxsplit=1)
        if len(parts) == 1:
            bot.reply_to(m, "Вкажи ім’я дизайнера. Приклад: `/projects_by Yaryna`", parse_mode="Markdown", reply_markup=REPLY_KB)
            return
        name = parts[1].strip()
        items = PROJECTS_BY_DESIGNER.get(name, [])
        if items:
            bot.reply_to(m, "📋 Завдання для *{}*:\n\n{}".format(name, "\n\n".join(items[-10:])),
                         parse_mode="Markdown", reply_markup=REPLY_KB)
        else:
            bot.reply_to(m, f"📭 Немає активних завдань для {name}.", reply_markup=REPLY_KB)

    # ===== Меню (reply keyboard) =====
    @bot.message_handler(func=lambda m: m.text == "🆕 Новий клієнт")
    def menu_new_client(m):
        force = types.ForceReply(input_field_placeholder="Введи ім’я клієнта (наприклад: Acme Inc.)")
        msg = bot.reply_to(m, "Як називається клієнт? (буде створено новий тред)", reply_markup=force)
        bot.register_for_reply(msg, _set_client_name_step)

    @bot.message_handler(func=lambda m: m.text == "📂 Історія переписки")
    def menu_history(m):
        if not THREADS:
            bot.reply_to(m, "Поки що немає жодного треду.", reply_markup=REPLY_KB)
            return
        names = sorted(THREADS.keys())
        bot.reply_to(m, "Вибери клієнта:", reply_markup=choose_client_buttons(names))

    @bot.message_handler(func=lambda m: m.text == "🧑‍🎨 Відправити дизайнеру")
    def menu_send_designer(m):
        if not THREADS:
            bot.reply_to(m, "Немає тредів. Спочатку створіть клієнта або киньте повідомлення.", reply_markup=REPLY_KB)
            return
        names = sorted(THREADS.keys())
        kb = types.InlineKeyboardMarkup(row_width=1)
        for n in names:
            kb.add(types.InlineKeyboardButton(f"{n}", callback_data=f"to_designer|{n}"))
        bot.reply_to(m, "Оберіть клієнта для відправки дизайнеру:", reply_markup=kb)

    @bot.message_handler(func=lambda m: m.text == "✅ Завершити проєкт")
    def menu_close(m):
        if not THREADS:
            bot.reply_to(m, "Немає активних тредів.", reply_markup=REPLY_KB)
            return
        names = sorted(THREADS.keys())
        kb = types.InlineKeyboardMarkup(row_width=1)
        for n in names:
            kb.add(types.InlineKeyboardButton(f"✅ Закрити: {n}", callback_data=f"close|{n}"))
        bot.reply_to(m, "Оберіть тред для закриття:", reply_markup=kb)

    @bot.message_handler(func=lambda m: m.text == "🔍 Перевірити ціну")
    def menu_price(m):
        bot.reply_to(
            m,
            "Швидка сітка:\n• Logo “Clean Start” — $100\n• Brand Essentials — $220\n• Ready to Launch — $360\n• Complete Look — $520\n• Identity in Action — $1000\n• Signature System — $1500+",
            reply_markup=REPLY_KB
        )

    @bot.message_handler(func=lambda m: m.text == "📋 Активні роботи")
    def menu_active(m):
        active = [n for n, t in THREADS.items() if t.get("status") != "closed"]
        if not active:
            bot.reply_to(m, "Активних немає.", reply_markup=REPLY_KB)
            return
        lines = []
        for n in active:
            t = THREADS[n]
            prof = t.get("profile") or "—"
            des = t.get("designer") or "—"
            lines.append(f"• {n}  | профіль: {prof} | дизайнер: {des}")
        bot.reply_to(m, "Активні:\n" + "\n".join(lines), reply_markup=REPLY_KB)

    # ===== Загальний текст (будь-де) — формуємо/продовжуємо треди по клієнту =====
    @bot.message_handler(func=lambda m: True, content_types=['text'])
    def handle_text(m):
        text = m.text or ""
        client = guess_client(text)
        project = guess_project(text)

        if client:
            thread = THREADS.setdefault(client, {
                "project": None, "history": [], "profile": None,
                "designer": None, "last_file_sent": None, "status": "active"
            })
            if project:
                thread["project"] = project
            thread["history"].append((datetime.utcnow().isoformat(), text))
            tags = f"#client_{client.replace(' ', '_')}"
            if thread.get("project"):
                tags += f"  #project_{thread['project'].replace(' ', '_')}"
            bot.reply_to(
                m,
                f"✅ Збережено в тред *{client}*.\n{tags}",
                reply_markup=thread_buttons(client)
            )
            return

        # якщо не розпізнали — запропонувати вибір/ввід
        existing = sorted(THREADS.keys())
        if existing:
            bot.reply_to(m, "Не розпізнав клієнта. Обери зі списку або введи вручну:",
                         reply_markup=choose_client_buttons(existing))
        else:
            force = types.ForceReply(input_field_placeholder="Введи ім’я клієнта (наприклад: Acme Inc.)")
            msg = bot.reply_to(m, "Як називається клієнт? (буде створено новий тред)", reply_markup=force)
            bot.register_for_reply(msg, _set_client_name_step)

    # ===== ForceReply крок для ручного створення клієнта =====
    def _set_client_name_step(reply_msg):
        name = (reply_msg.text or "").strip()
        if not name:
            bot.reply_to(reply_msg, "Порожнє ім’я. Спробуй ще раз.", reply_markup=REPLY_KB)
            return
        THREADS.setdefault(name, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None, "status": "active"})
        bot.reply_to(reply_msg, f"🆕 Створив тред для *{name}*. Тепер надішли повідомлення клієнта ще раз.", reply_markup=REPLY_KB)

    # ===== CALLBACKS =====
    @bot.callback_query_handler(func=lambda c: True)
    def cb(q):
        data = q.data or ""
        parts = data.split("|")
        action = parts[0]

        if action == "choose_client":
            client = parts[1]
            THREADS.setdefault(client, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None, "status": "active"})
            bot.edit_message_text(
                f"✅ Обрано клієнта: *{client}*. Надішли повідомлення — додам в історію.",
                q.message.chat.id, q.message.id
            )
            bot.answer_callback_query(q.id); return

        if action == "enter_client":
            force = types.ForceReply(input_field_placeholder="Введи ім’я клієнта")
            msg = bot.send_message(q.message.chat.id, "Введи ім’я клієнта:", reply_markup=force)
            bot.register_for_reply(msg, _set_client_name_step)
            bot.answer_callback_query(q.id); return

        if action == "history":
            client = parts[1]
            hist = THREADS.get(client, {}).get("history", [])
            if not hist:
                bot.answer_callback_query(q.id, "Історія порожня."); return
            text = "\n\n".join([f"{t}:\n{m}" for t, m in hist])[-4000:]
            bot.send_message(q.message.chat.id, f"🕓 Історія для *{client}*:\n\n{text}")
            bot.answer_callback_query(q.id); return

        if action == "profile":
            client = parts[1]
            kb = types.InlineKeyboardMarkup(row_width=2)
            for p in PROFILES:
                kb.add(types.InlineKeyboardButton(p, callback_data=f"setprofile|{client}|{p}"))
            bot.send_message(q.message.chat.id, f"Для *{client}*: вибери профіль:", reply_markup=kb)
            bot.answer_callback_query(q.id); return

        if action == "setprofile":
            _, client, prof = parts
            THREADS.setdefault(client, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None, "status": "active"})
            THREADS[client]["profile"] = prof
            bot.send_message(q.message.chat.id, f"✅ Профіль *{prof}* встановлено для *{client}*  #профіль_{prof}")
            bot.answer_callback_query(q.id); return

        if action == "to_designer":
            client = parts[1]
            if not DESIGNERS:
                bot.send_message(q.message.chat.id, "DESIGNERS порожній. Додай JSON з іменами та Telegram ID.")
                bot.answer_callback_query(q.id); return
            kb = types.InlineKeyboardMarkup(row_width=1)
            for name in DESIGNERS.keys():
                kb.add(types.InlineKeyboardButton(name, callback_data=f"send_to|{client}|{name}"))
            bot.send_message(q.message.chat.id, f"Кому надіслати тред *{client}*?", reply_markup=kb)
            bot.answer_callback_query(q.id); return

        if action == "send_to":
            _, client, designer = parts
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
            client = parts[1]
            info = THREADS.get(client, {})
            last_file = info.get("last_file_sent")
            if last_file and datetime.utcnow() - last_file > timedelta(hours=24):
                bot.send_message(q.message.chat.id, f"🔔 24 години минули: нагадай клієнту *{client}*.")
            else:
                bot.send_message(q.message.chat.id, "🕓 Ще не минуло 24 год або файл не відправлявся.")
            bot.answer_callback_query(q.id); return

        if action == "close":
            client = parts[1]
            if client in THREADS:
                THREADS[client]["status"] = "closed"
                bot.send_message(q.message.chat.id, f"✅ Тред *{client}* закрито.")
            bot.answer_callback_query(q.id); return
