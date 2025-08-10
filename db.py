# db.py
import sqlite3, os, json, time
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "sds.sqlite3")

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  company TEXT,
  profile TEXT,              -- 'Yurii'|'Olena'|NULL
  designer TEXT,             -- designer name (key from DESIGNERS) or NULL
  status TEXT DEFAULT 'active', -- 'active'|'closed'|'cold'
  topic_id INTEGER,          -- forum thread id in group for warm
  created_at TEXT,
  updated_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_topic ON clients(topic_id);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER,
  role TEXT,                 -- 'user'|'assistant'|'manager'|'client'
  content TEXT,
  ts TEXT,
  FOREIGN KEY(client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS cold_leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER,        -- source telegram message id in Cold Inbox
  text TEXT,
  profile TEXT,
  status TEXT DEFAULT 'new', -- 'new'|'archived'|'converted'
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""

def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

CONN = connect()
CONN.executescript(SCHEMA)
CONN.commit()

def now():
    return datetime.utcnow().isoformat(timespec="seconds")

# ---- clients ----
def create_client(name, company=None, profile=None, topic_id=None, status="active"):
    cur = CONN.cursor()
    cur.execute("INSERT INTO clients (name,company,profile,topic_id,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (name, company, profile, topic_id, status, now(), now()))
    CONN.commit()
    return cur.lastrowid

def get_client_by_topic(topic_id):
    cur = CONN.cursor()
    cur.execute("SELECT id,name,company,profile,designer,status,topic_id FROM clients WHERE topic_id=?", (topic_id,))
    return cur.fetchone()

def get_client_by_name(name):
    cur = CONN.cursor()
    cur.execute("SELECT id,name,company,profile,designer,status,topic_id FROM clients WHERE name=?", (name,))
    return cur.fetchone()

def set_client_topic(client_id, topic_id):
    CONN.execute("UPDATE clients SET topic_id=?, updated_at=? WHERE id=?", (topic_id, now(), client_id))
    CONN.commit()

def set_client_profile(client_id, profile):
    CONN.execute("UPDATE clients SET profile=?, updated_at=? WHERE id=?", (profile, now(), client_id)); CONN.commit()

def set_client_designer(client_id, designer):
    CONN.execute("UPDATE clients SET designer=?, updated_at=? WHERE id=?", (designer, now(), client_id)); CONN.commit()

def set_client_status(client_id, status):
    CONN.execute("UPDATE clients SET status=?, updated_at=? WHERE id=?", (status, now(), client_id)); CONN.commit()

def list_active_clients():
    cur = CONN.cursor()
    cur.execute("SELECT id,name,topic_id FROM clients WHERE status='active' ORDER BY updated_at DESC")
    return cur.fetchall()

# ---- messages ----
def add_msg(client_id, role, content):
    CONN.execute("INSERT INTO messages (client_id,role,content,ts) VALUES (?,?,?,?)",
                 (client_id, role, content, now()))
    CONN.commit()

def get_history_messages(client_id, last_n=20):
    cur = CONN.cursor()
    cur.execute("SELECT role,content FROM messages WHERE client_id=? ORDER BY id ASC", (client_id,))
    rows = cur.fetchall()
    out = []
    for r,c in rows[-last_n:]:
        out.append({"role": "assistant" if r=="assistant" else "user", "content": c})
    return out

# ---- cold leads ----
def add_cold(message_id, text, profile=None, status="new"):
    CONN.execute("INSERT INTO cold_leads (message_id,text,profile,status,created_at) VALUES (?,?,?,?,?)",
                 (message_id, text, profile, status, now()))
    CONN.commit()

def set_cold_profile(message_id, profile):
    CONN.execute("UPDATE cold_leads SET profile=?, status='new' WHERE message_id=?", (profile, message_id)); CONN.commit()

def set_cold_status(message_id, status):
    CONN.execute("UPDATE cold_leads SET status=? WHERE message_id=?", (status, message_id)); CONN.commit()

def cold_kb_snapshot():
    cur = CONN.cursor()
    cur.execute("SELECT message_id, profile, status, substr(text,1,500) FROM cold_leads ORDER BY message_id DESC LIMIT 200")
    rows = cur.fetchall()
    return "\n".join([f"[COLD #{mid}] profile={p or '-'} status={s}\n{text}" for mid,p,s,text in rows])

# ---- kb for assistant ----
def kb_snapshot():
    # маленький зріз знань для AI Assistant
    cur = CONN.cursor()
    cur.execute("SELECT id,name,profile,designer,status,topic_id FROM clients ORDER BY updated_at DESC LIMIT 200")
    clients = cur.fetchall()
    cur = CONN.cursor()
    cur.execute("SELECT c.name, m.role, substr(m.content,1,200) FROM messages m JOIN clients c ON c.id=m.client_id ORDER BY m.id DESC LIMIT 400")
    msgs = cur.fetchall()
    lines = []
    for cid,name,profile,designer,status,tid in clients:
        lines.append(f"[CLIENT] name={name} profile={profile or '-'} designer={designer or '-'} status={status} topic={tid}")
    if msgs:
        lines.append("\n[MESSAGES LATEST]")
        for name,role,content in msgs:
            lines.append(f"{name} | {role}: {content}")
    return "\n".join(lines)
