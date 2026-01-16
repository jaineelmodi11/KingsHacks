import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(os.getenv("DB_PATH", "/tmp/sessions.db"))
_DB_INITIALIZED = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
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

    # Demo-safe linked cards: display info only (NO PAN/CVV)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            nickname TEXT,
            network TEXT NOT NULL,
            last4 TEXT NOT NULL,
            exp_month INTEGER,
            exp_year INTEGER,
            billing_country TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            card_id INTEGER,
            merchant TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            country TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'CNP',
            item_description TEXT,
            dcc_offered INTEGER NOT NULL DEFAULT 0,
            decision TEXT,
            challenge_method TEXT,
            risk_score INTEGER,
            status TEXT NOT NULL,
            challenge_id TEXT,
            created_at TEXT NOT NULL,
            raw_json TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id),
            FOREIGN KEY(card_id) REFERENCES cards(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS challenges (
            challenge_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            method TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
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


def upsert_session(conn: sqlite3.Connection, session_id: str, assistant_id: str, thread_id: str, created_at: str) -> None:
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


def insert_audit(conn: sqlite3.Connection, session_id: str, timestamp: str, user_prompt: str, assistant_text: str, raw_json: str) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (session_id, timestamp, user_prompt, assistant_text, raw_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, timestamp, user_prompt, assistant_text, raw_json),
    )
    conn.commit()


def add_audit_log(*, conn: sqlite3.Connection, session_id: str, user_prompt: str, assistant_text: Optional[str], raw_response_json: str) -> None:
    insert_audit(
        conn=conn,
        session_id=session_id,
        timestamp=_now_iso(),
        user_prompt=user_prompt,
        assistant_text=assistant_text or "",
        raw_json=raw_response_json,
    )


def create_session(*args) -> None:
    if len(args) >= 1 and isinstance(args[0], sqlite3.Connection):
        conn = args[0]
        rest = args[1:]
        if len(rest) == 3:
            session_id, assistant_id, thread_id = rest
            created_at = _now_iso()
        elif len(rest) == 4:
            session_id, assistant_id, thread_id, created_at = rest
        else:
            raise TypeError("create_session(conn, ...) expects (conn, session_id, assistant_id, thread_id[, created_at])")
        upsert_session(conn, session_id, assistant_id, thread_id, created_at)
        return

    if len(args) == 3:
        session_id, assistant_id, thread_id = args
        created_at = _now_iso()
    elif len(args) == 4:
        session_id, assistant_id, thread_id, created_at = args
    else:
        raise TypeError("create_session expects (session_id, assistant_id, thread_id[, created_at])")

    conn = get_connection()
    try:
        upsert_session(conn, session_id, assistant_id, thread_id, created_at)
    finally:
        conn.close()


def add_card(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    nickname: Optional[str],
    network: str,
    last4: str,
    exp_month: Optional[int],
    exp_year: Optional[int],
    billing_country: Optional[str],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO cards (session_id, nickname, network, last4, exp_month, exp_year, billing_country, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, nickname, network, last4, exp_month, exp_year, billing_country, _now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_cards(conn: sqlite3.Connection, *, session_id: str) -> List[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT id, nickname, network, last4, exp_month, exp_year, billing_country, created_at
        FROM cards WHERE session_id = ? ORDER BY id DESC
        """,
        (session_id,),
    )
    rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "nickname": r[1],
            "network": r[2],
            "last4": r[3],
            "exp_month": r[4],
            "exp_year": r[5],
            "billing_country": r[6],
            "created_at": r[7],
        }
        for r in rows
    ]


def get_card(conn: sqlite3.Connection, *, session_id: str, card_id: int) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT id, nickname, network, last4, exp_month, exp_year, billing_country, created_at
        FROM cards WHERE session_id = ? AND id = ?
        """,
        (session_id, card_id),
    )
    r = cur.fetchone()
    if not r:
        return None
    return {
        "id": r[0],
        "nickname": r[1],
        "network": r[2],
        "last4": r[3],
        "exp_month": r[4],
        "exp_year": r[5],
        "billing_country": r[6],
        "created_at": r[7],
    }


def insert_payment_attempt(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    card_id: Optional[int],
    merchant: str,
    amount: float,
    currency: str,
    country: str,
    channel: str,
    item_description: Optional[str],
    dcc_offered: bool,
    decision: Optional[str],
    challenge_method: Optional[str],
    risk_score: Optional[int],
    status: str,
    challenge_id: Optional[str],
    raw_json: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO payment_attempts
        (session_id, card_id, merchant, amount, currency, country, channel, item_description, dcc_offered,
         decision, challenge_method, risk_score, status, challenge_id, created_at, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            card_id,
            merchant,
            float(amount),
            currency,
            country,
            (channel or "CNP").upper(),
            item_description,
            1 if dcc_offered else 0,
            decision,
            challenge_method,
            risk_score,
            status,
            challenge_id,
            _now_iso(),
            raw_json,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def create_challenge(conn: sqlite3.Connection, *, challenge_id: str, session_id: str, method: str, status: str) -> None:
    conn.execute(
        """
        INSERT INTO challenges (challenge_id, session_id, method, status, created_at, resolved_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (challenge_id, session_id, method, status, _now_iso()),
    )
    conn.commit()


def resolve_challenge(conn: sqlite3.Connection, *, challenge_id: str, session_id: str, status: str) -> None:
    conn.execute(
        """
        UPDATE challenges
        SET status = ?, resolved_at = ?
        WHERE challenge_id = ? AND session_id = ?
        """,
        (status, _now_iso(), challenge_id, session_id),
    )
    conn.commit()


def get_challenge(conn: sqlite3.Connection, *, session_id: str, challenge_id: str) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT challenge_id, method, status, created_at, resolved_at
        FROM challenges WHERE session_id = ? AND challenge_id = ?
        """,
        (session_id, challenge_id),
    )
    r = cur.fetchone()
    if not r:
        return None
    return {
        "challenge_id": r[0],
        "method": r[1],
        "status": r[2],
        "created_at": r[3],
        "resolved_at": r[4],
    }
