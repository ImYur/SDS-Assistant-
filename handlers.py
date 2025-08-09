import os, json
from datetime import datetime, timedelta
from telebot import types

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
# DESIGNERS — це JSON у змінних середовища, напр.:
# {"Yaryna Panchyshyn":"123456789","Yulia Sytnyk":"222222222","Kateryna Kucher":"333333333"}
DESIGNERS = json.loads(os.getenv("DESIGNERS", "{}"))

# Пам'ять у процесі
CLIENTS = {}  # key: f"{user_id}_{chat_id}" -> dict(... нижче)
PROJECTS_BY_DESIGNER = {}  # name -> [items]

PROFILES = ["Yurii", "Olena"]


def _client_key(message):
    return f"{message.from_user.id}_{message.chat.id}"


def _client_buttons(client_key):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("✍️ Відповісти", callback_data=f"reply|{client_key}"),
        types.InlineKeyboardButton("🎯 Вибрати акаунт", callback_data=f"profile|{client_key}"),
        types.InlineKeyboardButton("🧑‍🎨 Відправити дизайнеру", callback_data=f"to_designer|{client_key}"),
        types.InlineKeyboardButton("📎 Показати історію", callback_data=f"history|{client_key}"),
        types.InlineKeyboardButton("🔔 Фоллоу-ап (24h)", callback_data=f"followup|{client_key}"),
    )
    return kb


def setup_handlers(bot):
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        bot.reply_to(message, "👋 Привіт! Я Stylus Assistant. Надішли повідомлення клієнта або форвард від Upwork — я все структурую.")

    @bot.message_handler(commands=['projects_by'])
    def projects_by(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) == 1:
            bot.reply_to(message, "Вкажи ім’я дизайнера. Напр.: `/projects_by Yaryna`", parse_mode="Markdown")
            return
        name = parts[1].strip()
        items = PROJECTS_BY_DESIGNER.get(name, [])
        if items:
            text = "📋 Завдання для *{}*:\n\n".format(name) + "\n\n".join(items[-10:])
            bot.reply_to(message, text, parse_mode="Markdown")
        else:
            bot.reply_to(message, f"📭 Немає активних завдань для {name}.")

    @bot.message_handler(func=lambda m: True, content_types=['text'])
    def handle_message(message):
        # Фіксуємо/оновлюємо клієнта + історію
        key = _client_key(message)
        now = datetime.utcnow()
        is_new = key not in CLIENTS

        if is_new:
            CLIENTS[key] = {
                "name": message.from_user.full_name,
                "chat_id": message.chat.id,
                "history": [],
                "status": "new",
                "profile": None,
                "designer": None,
                "last_file_sent": None,   # якщо відправлятимеш файли — позначимо момент
            }

        CLIENTS[key]["history"].append((now.isoformat(), message.text))
        CLIENTS[key]["status"] = "active"

        if is_new:
            tags = f"#клієнт_{message.from_user.full_name.replace(' ', '_')} #статус_new"
            bot.reply_to(
                message,
                f"🆕 Новий клієнт: *{message.from_user.full_name}*\n{tags}",
                parse_mode="Markdown",
                reply_markup=_client_buttons(key)
            )
        else:
            bot.reply_to(
                message,
                "📨 Повідомлення збережено. Обери дію нижче:",
                reply_markup=_client_buttons(key)
            )

    # ==== CALLBACKS ====

    @bot.callback_query_handler(func=lambda c: True)
    def on_cb(query):
        try:
            action, client_key = query.data.split("|", 1)
        except Exception:
            bot.answer_callback_query(query.id)
            return

        # Історія
        if action == "history":
            hist = CLIENTS.get(client_key, {}).get("history", [])
            if not hist:
                bot.answer_callback_query(query.id, "Історія порожня.")
                return
            text = "\n\n".join([f"{t}:\n{m}" for t, m in hist])[-4000:]
            bot.send_message(query.message.chat.id, f"🕓 Історія:\n\n{text}")
            bot.answer_callback_query(query.id)
            return

        # Вибір акаунта
        if action == "profile":
            kb = types.InlineKeyboardMarkup(row_width=2)
            for p in PROFILES:
                kb.add(types.InlineKeyboardButton(p, callback_data=f"setprofile|{client_key}|{p}"))
            bot.send_message(query.message.chat.id, "🧩 Вибери профіль:", reply_markup=kb)
            bot.answer_callback_query(query.id)
            return

        if action == "setprofile":
            # очікуємо формат setprofile|client_key|Profile
            parts = query.data.split("|")
            if len(parts) == 3:
                _, ck, prof = parts
                CLIENTS[ck]["profile"] = prof
                bot.send_message(query.message.chat.id, f"✅ Встановлено профіль: *{prof}*  #профіль_{prof}", parse_mode="Markdown")
            bot.answer_callback_query(query.id)
            return

        # Відправити дизайнеру → вибір дизайнера
        if action == "to_designer":
            if not DESIGNERS:
                bot.send_message(query.message.chat.id, "Список дизайнерів порожній. Додай змінну середовища DESIGNERS з їхніми ID.")
                bot.answer_callback_query(query.id)
                return
            kb = types.InlineKeyboardMarkup(row_width=1)
            for name in DESIGNERS.keys():
                kb.add(types.InlineKeyboardButton(name, callback_data=f"send_to|{client_key}|{name}"))
            bot.send_message(query.message.chat.id, "👤 Кому надіслати?", reply_markup=kb)
            bot.answer_callback_query(query.id)
            return

        if action == "send_to":
            # очікуємо send_to|client_key|Designer Name
            parts = query.data.split("|")
            if len(parts) == 3:
                _, ck, designer = parts
                hist = CLIENTS.get(ck, {}).get("history", [])
                last_msg = hist[-1][1] if hist else "Без повідомлень"
                chat_id = DESIGNERS.get(designer)
                CLIENTS[ck]["designer"] = designer
                if chat_id:
                    bot.send_message(chat_id, f"🧾 Нове завдання:\n\n{last_msg}")
                    PROJECTS_BY_DESIGNER.setdefault(designer, []).append(last_msg)
                    bot.send_message(query.message.chat.id, f"✅ Надіслано дизайнеру *{designer}*  #дизайнер_{designer}", parse_mode="Markdown")
                else:
                    bot.send_message(query.message.chat.id, f"⚠️ Для дизайнера '{designer}' не знайдено Telegram ID у змінній DESIGNERS.")
            bot.answer_callback_query(query.id)
            return

        # Фоллоу-ап (24h) — проста перевірка
        if action == "followup":
            info = CLIENTS.get(client_key, {})
            last_file = info.get("last_file_sent")
            if last_file and datetime.utcnow() - last_file > timedelta(hours=24):
                bot.send_message(query.message.chat.id, "🔔 Нагадування: 24 години минули після відправки файлу, клієнт не відповів.")
            else:
                bot.send_message(query.message.chat.id, "🕓 Ще не минуло 24 год після останнього файлу або файл не відправлявся.")
            bot.answer_callback_query(query.id)
            return

        # Чернетка відповіді (поки без автогенерації тексту)
        if action == "reply":
            info = CLIENTS.get(client_key, {})
            prof = info.get("profile") or "— не вибрано —"
            bot.send_message(
                query.message.chat.id,
                f"✍️ Чернетка відповіді (профіль: *{prof}*):\n\n"
                f"Hi! Thanks for your message. We can help with logo/brand identity and packaging. "
                f"Could you share more details: scope, deadlines, examples, and budget?\n\n"
                f"(натисни *Вибрати акаунт*, щоб стилізувати під Yurii/Olena)",
                parse_mode="Markdown"
            )
            bot.answer_callback_query(query.id)
            return
