
from core.db import CONN
from core.utils import now

def add(client_id, role, content):
    CONN.execute("INSERT INTO messages (client_id,role,content,ts) VALUES (?,?,?,?)",
                 (client_id, role, content, now()))
    CONN.commit()

def history_for_ai(client_id, last_n=20):
    rows = CONN.execute("SELECT role,content FROM messages WHERE client_id=? ORDER BY id ASC", (client_id,)).fetchall()
    out = []
    for r in rows[-last_n:]:
        role = "assistant" if r["role"]=="assistant" else "user"
        out.append({"role": role, "content": r["content"]})
    return out

def latest_since(client_id, since_ts):
    if since_ts:
        return CONN.execute("SELECT role,content,ts FROM messages WHERE client_id=? AND ts>? ORDER BY id ASC", (client_id, since_ts)).fetchall()
    else:
        return CONN.execute("SELECT role,content,ts FROM messages WHERE client_id=? ORDER BY id ASC", (client_id,)).fetchall()

def last_ai_message(client_id):
    r = CONN.execute("SELECT content FROM messages WHERE client_id=? AND role='assistant' ORDER BY id DESC LIMIT 1", (client_id,)).fetchone()
    return r["content"] if r else None
