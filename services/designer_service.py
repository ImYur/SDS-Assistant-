
from core import repo_clients, repo_messages
from core.utils import md2_escape, now

def brief_text(cid):
    row = repo_clients.get_by_id(cid)
    msgs = repo_messages.latest_since(cid, row["last_brief_ts"])
    body = "\n".join([f"{m['role']}: {m['content']}" for m in msgs]) if msgs else "Без оновлень з часу останнього брифу."
    link = f"https://t.me/c/{str(row['topic_id'])[4:] if str(row['topic_id']).startswith('-100') else ''}/{row['topic_id']}"
    title = row["project_title"] or row["name"]
    prof = row["profile"] or "-"
    brief = f"Клієнт: {title}\nПрофіль: {prof}\nТред: {link}\n\nОстанні оновлення:\n{body}"
    return brief

def after_send_update(cid):
    repo_clients.set_last_brief_ts(cid, now())
