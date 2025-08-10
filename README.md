
# SDS Assistant Bot

## Quick deploy

1. Set env vars:
```
BOT_TOKEN=...
OPENAI_API_KEY=...
GROUP_CHAT_ID=-100XXXXXXXXXX
COLD_INBOX_TOPIC=<thread_id>
ASSISTANT_TOPIC=<thread_id>
OWNER_ID=<your_id>
DESIGNERS={"Yaryna":"<tg_id>","Yulia":"<tg_id>","Kateryna":"<tg_id>"}
```
2. `pip install -r requirements.txt`
3. `python app.py`

## Structure
See folders `core/`, `ai/`, `services/`, `tg/`.
