"""
SQLite persistence for the brain: session history, notes, reminders.
Long-term personal facts are handled by Mem0, not here.
"""
import os
import sqlite3
from datetime import datetime, timezone

_DATA_DIR = os.environ.get("DATA_DIR", "/home/ubuntu/VoiceProject/data")
DB_PATH   = os.path.join(_DATA_DIR, "assistant.db")


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role      TEXT NOT NULL,
                content   TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL DEFAULT 'default',
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL DEFAULT 'default',
                message    TEXT NOT NULL,
                fire_at    TEXT NOT NULL,
                channel    TEXT NOT NULL DEFAULT 'phone',
                delivered  INTEGER NOT NULL DEFAULT 0
            );
        """)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Session history ────────────────────────────────────────────────

def get_recent_messages(session_id: str, limit: int = 12) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """
            SELECT role, content FROM messages
            WHERE session_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def add_message(session_id: str, role: str, content: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, _now()),
        )


# ── Notes ──────────────────────────────────────────────────────────

def create_note(title: str, content: str, user_id: str = "default"):
    with _conn() as con:
        con.execute(
            "INSERT INTO notes (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, title, content, _now()),
        )


def search_notes(query: str, user_id: str = "default") -> list[dict]:
    pattern = f"%{query}%"
    with _conn() as con:
        rows = con.execute(
            """
            SELECT title, content, created_at FROM notes
            WHERE user_id = ? AND (title LIKE ? OR content LIKE ?)
            ORDER BY id DESC LIMIT 10
            """,
            (user_id, pattern, pattern),
        ).fetchall()
    return [{"title": r["title"], "content": r["content"], "created_at": r["created_at"]} for r in rows]
