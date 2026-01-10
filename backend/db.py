# backend/db.py
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# App Runner/container-safe default: writable filesystem
DB_PATH = Path(os.getenv("DB_PATH", "/tmp/sessions.db"))

_DB_INITIALIZED = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create the SQLite database and required tables if they do not exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            assistant_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            user_prompt TEXT NOT NULL,
            assistant_text TEXT,
            raw_json TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )
        """
    )
    conn.commit()
    conn.close()


def _ensure_db() -> None:
    global _DB_INITIALIZED
    if not _DB_INITIALIZED:
        init_db()
        _DB_INITIALIZED = True


def get_connection() -> sqlite3.Connection:
    _ensure_db()
    # timeout helps with brief lock contention; check_same_thread avoids issues under threads
    return sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)


def get_session(conn: sqlite3.Connection, session_id: str) -> Optional[Dict[str, str]]:
    cur = conn.execute(
        "SELECT session_id, assistant_id, thread_id FROM sessions WHERE session_id = ?",
        (session_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"session_id": row[0], "assistant_id": row[1], "thread_id": row[2]}


def upsert_session(
    conn: sqlite3.Connection,
    session_id: str,
    assistant_id: str,
    thread_id: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sessions (session_id, assistant_id, thread_id, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            assistant_id=excluded.assistant_id,
            thread_id=excluded.thread_id,
            created_at=excluded.created_at
        """,
        (session_id, assistant_id, thread_id, created_at),
    )
    conn.commit()


def insert_audit(
    conn: sqlite3.Connection,
    session_id: str,
    timestamp: str,
    user_prompt: str,
    assistant_text: str,
    raw_json: str,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (session_id, timestamp, user_prompt, assistant_text, raw_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, timestamp, user_prompt, assistant_text, raw_json),
    )
    conn.commit()


def create_session(*args) -> None:
    """
    Back-compat helper. Supports ALL patterns:

      1) create_session(session_id, assistant_id, thread_id)
      2) create_session(session_id, assistant_id, thread_id, created_at)
      3) create_session(conn, session_id, assistant_id, thread_id)
      4) create_session(conn, session_id, assistant_id, thread_id, created_at)
    """

    # If first arg is a sqlite connection, peel it off
    if len(args) >= 1 and isinstance(args[0], sqlite3.Connection):
        conn = args[0]
        rest = args[1:]

        if len(rest) == 3:
            session_id, assistant_id, thread_id = rest
            created_at = _now_iso()
        elif len(rest) == 4:
            session_id, assistant_id, thread_id, created_at = rest
        else:
            raise TypeError(
                "create_session(conn, ...) expects 4 or 5 total args: "
                "(conn, session_id, assistant_id, thread_id[, created_at])"
            )

        upsert_session(conn, session_id, assistant_id, thread_id, created_at)
        return

    # No connection passed in
    if len(args) == 3:
        session_id, assistant_id, thread_id = args
        created_at = _now_iso()
        conn = get_connection()
        try:
            upsert_session(conn, session_id, assistant_id, thread_id, created_at)
        finally:
            conn.close()
        return

    if len(args) == 4:
        session_id, assistant_id, thread_id, created_at = args
        conn = get_connection()
        try:
            upsert_session(conn, session_id, assistant_id, thread_id, created_at)
        finally:
            conn.close()
        return

    raise TypeError(
        "create_session expects one of:\n"
        "  (session_id, assistant_id, thread_id)\n"
        "  (session_id, assistant_id, thread_id, created_at)\n"
        "  (conn, session_id, assistant_id, thread_id)\n"
        "  (conn, session_id, assistant_id, thread_id, created_at)\n"
    )
