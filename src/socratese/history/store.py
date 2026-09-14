"""SQLite-backed session history.

Deliberately *not* Chroma. The questions asked of history are relational
("my last ten sessions", "which notes do I keep failing on"), not
nearest-neighbour. More importantly the Chroma collection is disposable —
`socratese index` rebuilds it — while transcripts are not, so they must not
share a store that a re-index could wipe.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import platformdirs

from anthropic.types import MessageParam

from socratese.history.models import SessionRecord, Turn
from socratese.retrieval.models import RetrievedChunk

APP_NAME = "socratese"

#: Sessions are a recent-history feature, not an archive. The oldest is
#: dropped once a new one would exceed this.
MAX_SESSIONS = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY,
    topic      TEXT NOT NULL,
    model      TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    messages   TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    id         INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ordinal    INTEGER NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT,
    UNIQUE (session_id, ordinal)
);

CREATE TABLE IF NOT EXISTS session_notes (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    note_path  TEXT NOT NULL,
    note_title TEXT NOT NULL,
    heading    TEXT NOT NULL,
    content    TEXT NOT NULL,
    distance   REAL NOT NULL,
    UNIQUE (session_id, position)
);
"""


def get_db_path() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME)) / "sessions.db"


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to the current schema.

    CREATE TABLE IF NOT EXISTS is a no-op on a table that already exists, so
    columns added after a database was first created need adding explicitly.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
    if "messages" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN messages TEXT")
        conn.commit()


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the history database, creating it and its schema if needed."""
    path = path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # off by default in sqlite3; without it the CASCADE deletes above are inert
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _prune(conn: sqlite3.Connection, keep: int) -> int:
    """Drop all but the `keep` most recent sessions. Returns how many went."""
    cursor = conn.execute(
        "DELETE FROM sessions WHERE id NOT IN ("
        "  SELECT id FROM sessions ORDER BY id DESC LIMIT ?"
        ")",
        (keep,),
    )
    return cursor.rowcount


def start_session(
    conn: sqlite3.Connection,
    topic: str,
    model: str,
    chunks: list[RetrievedChunk],
) -> int:
    """Open a session row and store the chunks grounding it. Returns its id.

    Pruning happens here rather than on exit so an abandoned session still
    counts against the limit, and so the newest session is never the one
    dropped.
    """
    _prune(conn, MAX_SESSIONS - 1)

    cursor = conn.execute(
        "INSERT INTO sessions (topic, model, started_at) VALUES (?, ?, ?)",
        (topic, model, datetime.now(timezone.utc).isoformat()),
    )
    session_id = cursor.lastrowid
    assert session_id is not None  # sqlite always assigns an INTEGER PRIMARY KEY

    conn.executemany(
        "INSERT INTO session_notes"
        " (session_id, position, note_path, note_title, heading, content, distance)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (session_id, i, str(c.note_path), c.note_title, c.heading, c.content, c.distance)
            for i, c in enumerate(chunks)
        ],
    )
    conn.commit()
    return session_id


def record_question(conn: sqlite3.Connection, session_id: int, ordinal: int, question: str) -> None:
    """Store a question as soon as it is asked, before the answer exists.

    Written incrementally so a crashed or Ctrl-C'd session still leaves its
    transcript behind.
    """
    conn.execute(
        "INSERT INTO turns (session_id, ordinal, question) VALUES (?, ?, ?)",
        (session_id, ordinal, question),
    )
    conn.commit()


def record_answer(conn: sqlite3.Connection, session_id: int, ordinal: int, answer: str) -> None:
    conn.execute(
        "UPDATE turns SET answer = ? WHERE session_id = ? AND ordinal = ?",
        (answer, session_id, ordinal),
    )
    conn.commit()


def save_messages(
    conn: sqlite3.Connection, session_id: int, messages: list[MessageParam]
) -> None:
    """Snapshot the raw conversation as sent to the API.

    Stored verbatim so a resumed session continues from exactly what the model
    saw, rather than a transcript re-rendered with today's prompt formatting.
    The `turns` table stays the queryable view; this is the replayable one.
    """
    conn.execute(
        "UPDATE sessions SET messages = ? WHERE id = ?",
        (json.dumps(messages), session_id),
    )
    conn.commit()


def end_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), session_id),
    )
    conn.commit()


def _row_to_record(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        topic=row["topic"],
        model=row["model"],
        started_at=datetime.fromisoformat(row["started_at"]),
        ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
        messages=json.loads(row["messages"]) if row["messages"] else [],
    )


def recent_sessions(conn: sqlite3.Connection, limit: int = MAX_SESSIONS) -> list[SessionRecord]:
    """Most recent first. Turns and chunks are not loaded — use `load_session`."""
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_record(row) for row in rows]


def load_session(conn: sqlite3.Connection, session_id: int) -> SessionRecord | None:
    """Fully hydrate one session, including its turns and grounding chunks."""
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        return None

    record = _row_to_record(row)
    record.turns = [
        Turn(ordinal=t["ordinal"], question=t["question"], answer=t["answer"])
        for t in conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY ordinal", (session_id,)
        )
    ]
    record.chunks = [
        RetrievedChunk(
            note_path=Path(n["note_path"]),
            note_title=n["note_title"],
            heading=n["heading"],
            content=n["content"],
            distance=n["distance"],
        )
        for n in conn.execute(
            "SELECT * FROM session_notes WHERE session_id = ? ORDER BY position", (session_id,)
        )
    ]
    return record
