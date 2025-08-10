
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  company TEXT,
  project_title TEXT,
  project_type TEXT,
  budget TEXT,
  profile TEXT,
  designer TEXT,
  manager_id INTEGER,
  status TEXT DEFAULT 'active',
  topic_id INTEGER,
  last_brief_ts TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_topic ON clients(topic_id);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id INTEGER,
  role TEXT,         -- 'user'|'assistant'|'manager'|'client'
  content TEXT,
  ts TEXT,
  FOREIGN KEY(client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS cold_leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER,
  text TEXT,
  pitch_text TEXT,
  profile TEXT,
  status TEXT DEFAULT 'new', -- 'new'|'archived'|'converted'
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
