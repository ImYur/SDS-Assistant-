
from telebot import types

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🆕 New client", "📂 History")
    kb.row("🧵 Open topic", "🧑‍🎨 Send to designer")
    kb.row("📋 Active", "✅ Close project")
    kb.row("🔍 Price grid", "ℹ️ Info")
    return kb

def choose_profile_kb(msg_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("Yurii", callback_data=f"cold_prof|{msg_id}|Yurii"),
        types.InlineKeyboardButton("Olena", callback_data=f"cold_prof|{msg_id}|Olena"),
    )
    return kb

def cold_actions_kb(msg_id, prof):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📝 Generate pitch", callback_data=f"cold_pitch|{msg_id}|{prof}"))
    kb.add(types.InlineKeyboardButton("📤 Send pitch", callback_data=f"cold_sendpitch|{msg_id}"))
    kb.add(types.InlineKeyboardButton("🧵 Convert to Warm", callback_data=f"cold_convert|{msg_id}|{prof}"))
    return kb

def warm_action_kb(client_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📤 Send to client", callback_data=f"send_client|{client_id}"),
        types.InlineKeyboardButton("🧑‍🎨 To designer", callback_data=f"ask_designer|{client_id}")
    )
    kb.add(
        types.InlineKeyboardButton("ℹ️ Info", callback_data=f"info|{client_id}"),
        types.InlineKeyboardButton("✏️ Edit info", callback_data=f"edit|{client_id}")
    )
    kb.add(
        types.InlineKeyboardButton("✅ Close", callback_data=f"close|{client_id}")
    )
    return kb

def choose_profile_for_client(cid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("Yurii", callback_data=f"set_profile|{cid}|Yurii"),
        types.InlineKeyboardButton("Olena", callback_data=f"set_profile|{cid}|Olena"),
    )
    return kb

def choose_designer_kb(client_id, designers: dict):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for name in designers.keys():
        kb.add(types.InlineKeyboardButton(name, callback_data=f"set_designer|{client_id}|{name}"))
    return kb
