
import sqlite3, os, pathlib

DB_PATH = os.getenv("DB_PATH", "sds.sqlite3")
SCHEMA_PATH = pathlib.Path(__file__).with_name("schema.sql")

def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

CONN = connect()

with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    CONN.executescript(f.read())
    CONN.commit()
