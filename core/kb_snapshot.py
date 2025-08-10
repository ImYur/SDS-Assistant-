
from core.db import CONN

def build_snapshot():
    clients = CONN.execute("SELECT id,name,profile,designer,status,topic_id,project_title,project_type,budget FROM clients ORDER BY updated_at DESC LIMIT 200").fetchall()
    msgs = CONN.execute("SELECT c.name, m.role, substr(m.content,1,200) AS c FROM messages m JOIN clients c ON c.id=m.client_id ORDER BY m.id DESC LIMIT 400").fetchall()
    lines = []
    for r in clients:
        lines.append(f"[CLIENT] name={r['name']} profile={r['profile'] or '-'} designer={r['designer'] or '-'} status={r['status']} topic={r['topic_id']} title={r['project_title'] or '-'} type={r['project_type'] or '-'} budget={r['budget'] or '-'}")
    if msgs:
        lines.append("\n[MESSAGES LATEST]")
        for r in msgs:
            lines.append(f"{r['name']} | {r['role']}: {r['c']}")
    return "\n".join(lines)
