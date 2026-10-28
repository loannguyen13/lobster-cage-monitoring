import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Outbox:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY, body BLOB NOT NULL,
                    sent INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS budget (
                    utc_day TEXT PRIMARY KEY, units INTEGER NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, message_id, body):
        with self.connect() as db:
            existing = db.execute("SELECT body FROM messages WHERE message_id=?", (message_id,)).fetchone()
            if existing and bytes(existing[0]) != body:
                raise ValueError("Conflicting contents for existing message_id")
            db.execute("INSERT OR IGNORE INTO messages(message_id,body) VALUES (?,?)", (message_id, body))

    def next(self):
        with self.connect() as db:
            return db.execute("SELECT message_id,body FROM messages WHERE sent=0 ORDER BY rowid LIMIT 1").fetchone()

    def mark_sent(self, message_id):
        with self.connect() as db:
            db.execute("UPDATE messages SET sent=1 WHERE message_id=?", (message_id,))

    def reserve(self, body, daily_limit, utc_day=None):
        # 512-byte safety allowance for metadata. Reserve BEFORE each attempt,
        # even if the SDK reports failure (the Hub may have received it).
        units = math.ceil((len(body) + 512) / 512)
        day = utc_day or datetime.now(timezone.utc).date().isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO budget VALUES (?,0)", (day,))
            used = db.execute("SELECT units FROM budget WHERE utc_day=?", (day,)).fetchone()[0]
            if used + units > daily_limit:
                return False
            db.execute("UPDATE budget SET units=units+? WHERE utc_day=?", (units, day))
        return True
