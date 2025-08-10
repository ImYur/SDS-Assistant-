
from core.db import CONN
from core.utils import now

def add(message_id, text, profile=None, status="new"):
    CONN.execute("INSERT INTO cold_leads (message_id,text,pitch_text,profile,status,created_at) VALUES (?,?,?,?,?,?)",
                 (message_id, text, None, profile, status, now()))
    CONN.commit()

def set_profile(message_id, profile):
    CONN.execute("UPDATE cold_leads SET profile=?, status='new' WHERE message_id=?", (profile, message_id)); CONN.commit()

def set_status(message_id, status):
    CONN.execute("UPDATE cold_leads SET status=? WHERE message_id=?", (status, message_id)); CONN.commit()

def set_pitch(message_id, pitch_text):
    CONN.execute("UPDATE cold_leads SET pitch_text=?, status='archived' WHERE message_id=?", (pitch_text, message_id)); CONN.commit()

def get_text(message_id):
    r = CONN.execute("SELECT text FROM cold_leads WHERE message_id=?", (message_id,)).fetchone()
    return r["text"] if r else ""

def get_pitch(message_id):
    r = CONN.execute("SELECT pitch_text FROM cold_leads WHERE message_id=?", (message_id,)).fetchone()
    return r["pitch_text"] if r else None

def snapshot(limit=200):
    rows = CONN.execute("SELECT message_id, profile, status, substr(text,1,500) AS t FROM cold_leads ORDER BY message_id DESC LIMIT ?", (limit,)).fetchall()
    return "\n".join([f"[COLD #{r['message_id']}] profile={r['profile'] or '-'} status={r['status']}\n{r['t']}" for r in rows])
