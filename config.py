
import os, json

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
COLD_INBOX_TOPIC = int(os.getenv("COLD_INBOX_TOPIC", "0") or "0")
ASSISTANT_TOPIC = int(os.getenv("ASSISTANT_TOPIC", "0") or "0")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")
DESIGNERS = json.loads(os.getenv("DESIGNERS", "{}") or "{}")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

if not BOT_TOKEN or not GROUP_CHAT_ID:
    raise RuntimeError("Missing BOT_TOKEN or GROUP_CHAT_ID")
