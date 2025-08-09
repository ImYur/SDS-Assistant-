import os, json, re
from datetime import datetime, timedelta
from telebot import types

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DESIGNERS = json.loads(os.getenv("DESIGNERS", "{}"))
PROFILES = ["Yurii", "Olena"]

# Пам'ять в процесі
THREADS = {}                # client_name -> dict(...)
PROJECTS_BY_DESIGNER = {}   # designer -> [items]

# --------- евристики визначення клієнта/проєкту ---------
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
    import re as _re
    return _re.sub(r"\s+", " ", s.strip())

def guess_client(text: str):
    import re as _re
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    blob = "\n".join(lines)
    for pat in CLIENT_PATTERNS:
        m = _re.search(pat, blob, _re.IGNORECASE | _re.MULTILINE)
        if m: return _norm(m.group("name"))
    if lines:
        last = lines[-1]
        m = _re.match(r"(?P<name>[A-Za-z][A-Za-z \.\-]{1,40})\s*(?:,|CEO|Founder|Manager|Owner)\b", last)
        if m: return _norm(m.group("name"))
    return None

def guess_project(text: str):
    import re as _re
    for pat in PROJECT_PATTERNS:
        m = _re.search(pat, text, _re.IGNORECASE | _re.MULTILINE)
        if m: return _norm(m.group("title"))
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

# =============== HANDLERS ===============
def setup_handlers(bot):

    @bot.message_handler(commands=['health'])
    def health(m):
        bot.reply_to(m, "✅ alive")

    @bot.message_handler(commands=['whoami'])
    def whoami(m):
        bot.reply_to(m, f"Your ID: {m.from_user.id}")

    @bot.message_handler(commands=['start'])
    def start(m):
        bot.reply_to(
            m,
            "👋 Привіт! Надсилай текст діалогу з клієнтом/інвайт. "
            "Я створю/продовжу тред за *іменем клієнта*, а не за твоїм акаунтом.",
            parse_mode="Markdown"
        )

    # Важливо: тимчасово дозволяємо ВСІ приватні повідомлення (щоб точно реагував)
    def _allow(m):
        return m.chat.type == 'private'

    @bot.message_handler(func=_allow, content_types=['text'])
    def handle_text(m):
        text = m.text or ""

        # 1) Витягаємо клієнта/проєкт з тексту
        client = guess_client(text)
        project = guess_project(text)

        if client:
            thread = THREADS.setdefault(client, {
                "project": None, "history": [], "profile": None,
                "designer": None, "last_file_sent": None
            })
            if project: thread["project"] = project
            thread["history"].append((datetime.utcnow().isoformat(), text))

            tags = f"#client_{client.replace(' ', '_')}"
            if thread.get("project"):
                tags += f"  #project_{thread['project'].replace(' ', '_')}"
            bot.reply_to(
                m,
                f"✅ Збережено в тред *{client}*.\n{tags}",
                parse_mode="Markdown",
                reply_markup=thread_buttons(client)
            )
            return

        # 2) Якщо не розпізнали — запропонувати вибір існуючих або ручний ввід
        existing = sorted(THREADS.keys())
        if existing:
            bot.reply_to(m, "Не розпізнав клієнта. Обери зі списку або введи вручну:",
                         reply_markup=choose_client_buttons(existing))
        else:
            force = types.ForceReply(input_field_placeholder="Введи ім’я клієнта (наприклад: Acme Inc.)")
            msg = bot.reply_to(m, "Як називається клієнт? (створю новий тред)", reply_markup=force)
            bot.register_for_reply(msg, _set_client_name_step)

    def _set_client_name_step(reply_msg):
        name = (reply_msg.text or "").strip()
        if not name:
            bot.reply_to(reply_msg, "Порожнє ім’я. Спробуй ще раз.")
            return
        THREADS.setdefault(name, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None})
        bot.reply_to(reply_msg, f"🆕 Створив тред для *{name}*. Надішли повідомлення клієнта ще раз.", parse_mode="Markdown")

    # ---------- CALLBACKS (безпечний парсер) ----------
    @bot.callback_query_handler(func=lambda c: True)
    def cb(q):
        data = q.data or ""
        try:
            action, tail = data.split("|", 1)
        except ValueError:
            bot.answer_callback_query(q.id); return

        if action == "choose_client":
            client = tail
            THREADS.setdefault(client, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None})
            bot.edit_message_text(
                f"✅ Обрано клієнта: *{client}*. Надішли повідомлення — додам в історію.",
                q.message.chat.id, q.message.id, parse_mode="Markdown"
            )
            bot.answer_callback_query(q.id); return

        if action == "enter_client":
            force = types.ForceReply(input_field_placeholder="Введи ім’я клієнта")
            msg = bot.send_message(q.message.chat.id, "Введи ім’я клієнта:", reply_markup=force)
            bot.register_for_reply(msg, _set_client_name_step)
            bot.answer_callback_query(q.id); return

        if action == "history":
            client = tail
            hist = THREADS.get(client, {}).get("history", [])
            if not hist:
                bot.answer_callback_query(q.id, "Історія порожня.")
                return
            text = "\n\n".join([f"{t}:\n{m}" for t, m in hist])[-4000:]
            bot.send_message(q.message.chat.id, f"🕓 Історія для *{client}*:\n\n{text}", parse_mode="Markdown")
            bot.answer_callback_query(q.id); return

        if action == "profile":
            client = tail
            kb = types.InlineKeyboardMarkup(row_width=2)
            for p in PROFILES:
                kb.add(types.InlineKeyboardButton(p, callback_data=f"setprofile|{client}|{p}"))
            bot.send_message(q.message.chat.id, f"Для *{client}*: вибери профіль:", parse_mode="Markdown", reply_markup=kb)
            bot.answer_callback_query(q.id); return

        if action == "setprofile":
            try:
                client, prof = tail.split("|", 1)
            except ValueError:
                bot.answer_callback_query(q.id); return
            THREADS.setdefault(client, {"project": None, "history": [], "profile": None, "designer": None, "last_file_sent": None})
            THREADS[client]["profile"] = prof
            bot.send_message(q.message.chat.id, f"✅ Профіль *{prof}* встановлено для *{client}*  #профіль_{prof}", parse_mode="Markdown")
            bot.answer_callback_query(q.id); return

        if action == "to_designer":
            client = tail
            if not DESIGNERS:
                bot.send_message(q.message.chat.id, "DESIGNERS порожній. Додай JSON з іменами та Telegram ID.")
                bot.answer_callback_query(q.id); return
            kb = types.InlineKeyboardMarkup(row_width=1)
            for name in DESIGNERS.keys():
                kb.add(types.InlineKeyboardButton(name, callback_data=f"send_to|{client}|{name}"))
            bot.send_message(q.message.chat.id, f"Кому надіслати тред *{client}*?", parse_mode="Markdown", reply_markup=kb)
            bot.answer_callback_query(q.id); return

        if action == "send_to":
            try:
                client, designer = tail.split("|", 1)
            except ValueError:
                bot.answer_callback_query(q.id); return
            hist = THREADS.get(client, {}).get("history", [])
            last_msg = hist[-1][1] if hist else "Без повідомлень"
            chat_id = DESIGNERS.get(designer)
            if chat_id:
                PROJECTS_BY_DESIGNER.setdefault(designer, []).append(f"{client}: {last_msg}")
                bot.send_message(chat_id, f"🧾 {client}\n\n{last_msg}")
                bot.send_message(q.message.chat.id, f"✅ Надіслано *{designer}*  #дизайнер_{designer}", parse_mode="Markdown")
            else:
                bot.send_message(q.message.chat.id, f"⚠️ Для '{designer}' не знайдено Telegram ID у DESIGNERS.")
            bot.answer_callback_query(q.id); return

        if action == "followup":
            client = tail
            info = THREADS.get(client, {})
            last_file = info.get("last_file_sent")
            if last_file and datetime.utcnow() - last_file > timedelta(hours=24):
                bot.send_message(q.message.chat.id, f"🔔 24 години минули: нагадай клієнту *{client}*.")
            else:
                bot.send_message(q.message.chat.id, "🕓 Ще не минуло 24 год або файл не надсилався.")
            bot.answer_callback_query(q.id); return
