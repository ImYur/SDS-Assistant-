
from core.db import CONN
from core.utils import now

def create_client(name, company=None, profile=None, topic_id=None, status="active", manager_id=None, project_title=None, project_type=None, budget=None):
    cur = CONN.cursor()
    cur.execute("""INSERT INTO clients (name,company,project_title,project_type,budget,profile,designer,manager_id,status,topic_id,last_brief_ts,created_at,updated_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?,?)""" ,
                (name, company, project_title, project_type, budget, profile, None, manager_id, status, topic_id, now(), now()))
    CONN.commit()
    return cur.lastrowid

def get_by_topic(topic_id):
    return CONN.execute("SELECT * FROM clients WHERE topic_id=?", (topic_id,)).fetchone()

def get_by_id(cid):
    return CONN.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()

def set_topic(cid, tid):
    CONN.execute("UPDATE clients SET topic_id=?, updated_at=? WHERE id=?", (tid, now(), cid)); CONN.commit()

def set_profile(cid, profile):
    CONN.execute("UPDATE clients SET profile=?, updated_at=? WHERE id=?", (profile, now(), cid)); CONN.commit()

def set_designer(cid, designer):
    CONN.execute("UPDATE clients SET designer=?, updated_at=? WHERE id=?", (designer, now(), cid)); CONN.commit()

def set_status(cid, status):
    CONN.execute("UPDATE clients SET status=?, updated_at=? WHERE id=?", (status, now(), cid)); CONN.commit()

def set_last_brief_ts(cid, ts):
    CONN.execute("UPDATE clients SET last_brief_ts=?, updated_at=? WHERE id=?", (ts, now(), cid)); CONN.commit()

def update_info(cid, **fields):
    if not fields: return
    cols = ", ".join([f"{k}=?" for k in fields.keys()])
    vals = list(fields.values()) + [now(), cid]
    CONN.execute(f"UPDATE clients SET {cols}, updated_at=? WHERE id=?", vals)
    CONN.commit()

def list_active():
    return CONN.execute("SELECT id,name,topic_id FROM clients WHERE status='active' ORDER BY updated_at DESC").fetchall()
