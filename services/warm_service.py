
from core import repo_clients, repo_messages
from core.utils import now
from ai import openai_http, prompts

SYSTEM_MAP = {"Yurii": prompts.YURII_SYSTEM, "Olena": prompts.OLENA_SYSTEM}

def ensure_client_by_topic(bot, group_id, topic_id, name_guess="Client"):
    row = repo_clients.get_by_topic(topic_id)
    if row:
        return row
    # create client
    cid = repo_clients.create_client(name_guess, topic_id=topic_id, status="active")
    return repo_clients.get_by_topic(topic_id)

def ai_reply(profile, client_id):
    hist = repo_messages.history_for_ai(client_id, last_n=20)
    system = SYSTEM_MAP.get(profile, prompts.YURII_SYSTEM)
    messages = [{"role":"system","content":system}] + hist + [{"role":"user","content":"Draft a concise, helpful reply to the last client message in English."}]
    out = openai_http.chat(messages, temperature=0.7, max_tokens=350)
    repo_messages.add(client_id, "assistant", out)
    return out

def thanks_note(profile, brief_context):
    system = SYSTEM_MAP.get(profile, prompts.YURII_SYSTEM)
    messages = [
        {"role":"system","content":system},
        {"role":"user","content": f"Context:\n{brief_context}\n\nWrite a short thank-you & wrap-up note in English (3–5 sentences)."}
    ]
    return openai_http.chat(messages, temperature=0.6, max_tokens=220)

def build_info_text(row):
    link = f"https://t.me/c/{str(row['topic_id'])[4:] if str(row['topic_id']).startswith('-100') else ''}/{row['topic_id']}"
    def val(k): return row[k] if row[k] else "-"
    return (
        f"*Client:* {val('name')}\n"
        f"*Project:* {val('project_title')}\n"
        f"*Type:* {val('project_type')}\n"
        f"*Budget:* {val('budget')}\n"
        f"*Profile:* {val('profile')}\n"
        f"*Designer:* {val('designer')}\n"
        f"*Manager ID:* {val('manager_id')}\n"
        f"*Status:* {val('status')}\n"
        f"*Topic:* {row['topic_id']}"
    )
