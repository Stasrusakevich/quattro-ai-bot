from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def split_text(text, limit=3500):
    """Telegram limits text by UTF-16 code units, including astral emoji."""
    parts = []
    current = []
    units = 0
    for character in text:
        length = 2 if ord(character) > 0xFFFF else 1
        if units + length > limit:
            parts.append("".join(current))
            current = []
            units = 0
        current.append(character)
        units += length
    if current:
        parts.append("".join(current))
    return parts


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS assistant_inbox (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    author TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('note', 'task', 'gpt')),
                    text TEXT NOT NULL,
                    attachment_json TEXT,
                    created_at TEXT NOT NULL,
                    ai_state TEXT NOT NULL DEFAULT 'pending',
                    ai_response TEXT,
                    UNIQUE (chat_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS assistant_outbox (
                    id INTEGER PRIMARY KEY,
                    inbox_id INTEGER NOT NULL REFERENCES assistant_inbox(id),
                    part INTEGER NOT NULL,
                    method TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    telegram_message_id INTEGER,
                    error_type TEXT,
                    UNIQUE (inbox_id, part)
                );
                CREATE INDEX IF NOT EXISTS assistant_outbox_pending
                    ON assistant_outbox(state, next_attempt);
                CREATE TABLE IF NOT EXISTS assistant_audit (
                    id INTEGER PRIMARY KEY,
                    inbox_id INTEGER NOT NULL REFERENCES assistant_inbox(id),
                    action TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                PRAGMA user_version=1;
            """)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def recover_interrupted(self):
        with closing(self.connect()) as connection, connection:
            # The process may have stopped after Telegram accepted a request.
            connection.execute("""
                UPDATE assistant_outbox SET state='uncertain', error_type='Interrupted'
                WHERE state='sending'
            """)
            connection.execute("UPDATE assistant_inbox SET ai_state='failed' WHERE ai_state='running'")

    def accept(self, message, kind, owner_id):
        user = message.from_user
        author = user.full_name
        if user.username:
            author += f" (@{user.username})"
        text = message.text or message.caption or ""
        attachment = None
        for media_type in ("photo", "document", "voice", "audio", "video", "video_note", "animation", "sticker"):
            media = getattr(message, media_type, None)
            if media:
                if media_type == "photo":
                    media = media[-1]
                attachment = {"type": media_type, "file_id": media.file_id}
                break
        with closing(self.connect()) as connection, connection:
            cursor = connection.execute("""
                INSERT OR IGNORE INTO assistant_inbox
                    (chat_id, message_id, user_id, author, kind, text, attachment_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (message.chat_id, message.message_id, user.id, author, kind, text,
                  json.dumps(attachment) if attachment else None, utc_now()))
            row = connection.execute("""
                SELECT * FROM assistant_inbox WHERE chat_id=? AND message_id=?
            """, (message.chat_id, message.message_id)).fetchone()
            if not cursor.rowcount:
                return dict(row), False
            if kind != "gpt":
                title = "Задача" if kind == "task" else "Заметка"
                body = f"{title} #{row['id']}\nОт {author}\n\n{text}"
                parts = [("send_message", {"chat_id": owner_id, "text": part})
                         for part in split_text(body)]
                if attachment:
                    media_type = attachment["type"]
                    parts.append((f"send_{media_type}", {
                        "chat_id": owner_id, media_type: attachment["file_id"],
                    }))
                for part, (method, payload) in enumerate(parts):
                    connection.execute("""
                        INSERT INTO assistant_outbox (inbox_id, part, method, payload_json)
                        VALUES (?, ?, ?, ?)
                    """, (row["id"], part, method, json.dumps(payload)))
            self._audit(connection, row["id"], "accepted", kind)
            return dict(row), True

    def _audit(self, connection, item_id, action, details):
        connection.execute("""
            INSERT INTO assistant_audit (inbox_id, action, details, created_at)
            VALUES (?, ?, ?, ?)
        """, (item_id, action, details, utc_now()))

    def claim_notification(self, item_id=None):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("""
                SELECT * FROM assistant_outbox AS candidate
                WHERE state='pending' AND next_attempt<=?
                    AND (? IS NULL OR inbox_id=?)
                    AND NOT EXISTS (
                        SELECT 1 FROM assistant_outbox AS previous
                        WHERE previous.inbox_id=candidate.inbox_id
                          AND previous.part<candidate.part AND previous.state!='sent'
                    )
                ORDER BY id LIMIT 1
            """, (time.time(), item_id, item_id)).fetchone()
            if row is None:
                return None
            connection.execute("""
                UPDATE assistant_outbox SET state='sending', attempts=attempts+1 WHERE id=?
            """, (row["id"],))
            return dict(row)

    def notification_result(self, notification, state, *, message_id=None, error=None, delay=0):
        with closing(self.connect()) as connection, connection:
            connection.execute("""
                UPDATE assistant_outbox SET state=?, telegram_message_id=?, error_type=?, next_attempt=?
                WHERE id=? AND state='sending'
            """, (state, message_id, error, time.time() + delay, notification["id"]))
            self._audit(connection, notification["inbox_id"], "delivery", state)

    def notification_states(self, item_id):
        with closing(self.connect()) as connection:
            return [row[0] for row in connection.execute(
                "SELECT state FROM assistant_outbox WHERE inbox_id=?", (item_id,)
            )]

    def inbox(self, kind=None, limit=10):
        with closing(self.connect()) as connection:
            rows = connection.execute("""
                SELECT * FROM assistant_inbox
                WHERE kind IN ('note', 'task') AND (? IS NULL OR kind=?)
                ORDER BY id DESC LIMIT ?
            """, (kind, kind, limit)).fetchall()
            return [dict(row) for row in rows]

    def delivery_counts(self):
        with closing(self.connect()) as connection:
            return dict(connection.execute(
                "SELECT state, COUNT(*) FROM assistant_outbox GROUP BY state"
            ).fetchall())

    def retry_failed(self):
        with closing(self.connect()) as connection, connection:
            return connection.execute("""
                UPDATE assistant_outbox SET state='pending', next_attempt=0
                WHERE state='failed'
            """).rowcount

    def claim_ai(self, item_id):
        with closing(self.connect()) as connection, connection:
            return connection.execute("""
                UPDATE assistant_inbox SET ai_state='running'
                WHERE id=? AND ai_state='pending'
            """, (item_id,)).rowcount == 1

    def finish_ai(self, item_id, response=None):
        with closing(self.connect()) as connection, connection:
            connection.execute("""
                UPDATE assistant_inbox SET ai_state=?, ai_response=? WHERE id=?
            """, ("done" if response else "failed", response, item_id))

    def ai_history(self, user_id, before_id, *, chat_id, limit=5):
        with closing(self.connect()) as connection:
            rows = connection.execute("""
                SELECT text, ai_response FROM assistant_inbox
                WHERE user_id=? AND chat_id=? AND kind='gpt' AND ai_state='done' AND id<?
                ORDER BY id DESC LIMIT ?
            """, (user_id, chat_id, before_id, limit)).fetchall()
        history = []
        for row in reversed(rows):
            history.extend([{"role": "user", "content": row["text"]},
                            {"role": "assistant", "content": row["ai_response"]}])
        return history
