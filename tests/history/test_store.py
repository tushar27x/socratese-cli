# tests/history/test_store.py
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from anthropic.types import MessageParam

from socratese.history.models import SessionRecord
from socratese.history.store import (
    MAX_SESSIONS,
    connect,
    end_session,
    get_db_path,
    load_session,
    recent_sessions,
    record_answer,
    record_question,
    save_messages,
    start_session,
)
from socratese.retrieval.models import RetrievedChunk


@pytest.fixture
def conn(tmp_path: Path):
    """A real SQLite database in tmp_path — deliberately not a fake.

    The schema's FOREIGN KEY ... ON DELETE CASCADE and UNIQUE constraints are
    the things most likely to be wrong, and only a real engine enforces them.
    """
    connection = connect(tmp_path / "sessions.db")
    yield connection
    connection.close()


def make_chunk(title: str = "Redis Persistence", distance: float = 0.7) -> RetrievedChunk:
    return RetrievedChunk(
        note_path=Path(f"/vault/{title}.md"),
        note_title=title,
        heading="RDB",
        content=f"body of {title}",
        distance=distance,
    )


# --- schema and location ------------------------------------------------------


def test_db_lives_beside_the_index_not_in_the_config_dir():
    """History is user data, not configuration — you would never hand-edit it."""
    path = get_db_path()

    assert path.name == "sessions.db"
    assert "socratese" in str(path)


def test_connect_creates_the_file_and_schema(tmp_path: Path):
    path = tmp_path / "nested" / "sessions.db"

    connection = connect(path)

    tables = {
        r["name"]
        for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"sessions", "turns", "session_notes"} <= tables
    assert path.exists()


def test_connect_is_idempotent(tmp_path: Path):
    path = tmp_path / "sessions.db"
    first = connect(path)
    start_session(first, "topic", "model", [make_chunk()])
    first.close()

    second = connect(path)

    assert len(recent_sessions(second)) == 1  # schema re-run did not wipe anything


def test_foreign_keys_are_enforced(conn: sqlite3.Connection):
    """sqlite3 disables them by default, which would make the CASCADE deletes
    in the schema silently inert."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO turns (session_id, ordinal, question) VALUES (?, ?, ?)",
            (999, 1, "orphan"),
        )


# --- writing a session --------------------------------------------------------


def test_start_session_returns_an_id_and_stores_the_topic(conn: sqlite3.Connection):
    session_id = start_session(conn, "how does redis persist?", "claude-haiku-4-5", [make_chunk()])

    record = load_session(conn, session_id)

    assert record is not None
    assert record.topic == "how does redis persist?"
    assert record.model == "claude-haiku-4-5"


def test_grounding_chunks_round_trip_including_content(conn: sqlite3.Connection):
    """Resume rebuilds the original prompt from these, so content must survive —
    not just the identifiers needed to display a source list."""
    chunk = make_chunk()
    session_id = start_session(conn, "topic", "model", [chunk])

    record = load_session(conn, session_id)

    assert record is not None
    assert record.chunks == [chunk]
    assert isinstance(record.chunks[0].note_path, Path)


def test_chunks_come_back_by_position_not_insertion_order(conn: sqlite3.Connection):
    """Rows are inserted deliberately scrambled so the assertion is about
    `position`, not insertion order. Same caveat as the turns test below: the
    UNIQUE(session_id, position) autoindex already sorts these, so the ORDER BY
    is defensive rather than load-bearing."""
    session_id = start_session(conn, "topic", "model", [])
    for position in (2, 0, 1):
        conn.execute(
            "INSERT INTO session_notes"
            " (session_id, position, note_path, note_title, heading, content, distance)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, position, f"/v/Note{position}.md", f"Note{position}", "", "body", 0.5),
        )
    conn.commit()

    record = load_session(conn, session_id)

    assert record is not None
    assert [c.note_title for c in record.chunks] == ["Note0", "Note1", "Note2"]


def test_a_question_is_stored_before_its_answer_exists(conn: sqlite3.Connection):
    """Written incrementally so a Ctrl-C'd session still leaves a transcript."""
    session_id = start_session(conn, "topic", "model", [make_chunk()])

    record_question(conn, session_id, 1, "what happens to concurrent writes?")

    record = load_session(conn, session_id)
    assert record is not None
    assert record.turns[0].question == "what happens to concurrent writes?"
    assert record.turns[0].answer is None


def test_recording_an_answer_attaches_it_to_the_question(conn: sqlite3.Connection):
    session_id = start_session(conn, "topic", "model", [make_chunk()])
    record_question(conn, session_id, 1, "Q1?")

    record_answer(conn, session_id, 1, "my answer")

    record = load_session(conn, session_id)
    assert record is not None
    assert record.turns[0].answer == "my answer"


def test_turns_come_back_by_ordinal_not_insertion_order(conn: sqlite3.Connection):
    """Recorded out of sequence on purpose — nothing stops a caller doing that.

    Note this test cannot be mutation-verified against the query's ORDER BY:
    SQLite serves the lookup from the UNIQUE(session_id, ordinal) autoindex, so
    rows come back sorted with or without it. The ORDER BY stays because the
    contract should not depend on which index the planner happens to pick; the
    test pins the observable ordering, not the clause producing it."""
    session_id = start_session(conn, "topic", "model", [make_chunk()])
    for ordinal in (3, 1, 2):
        record_question(conn, session_id, ordinal, f"Q{ordinal}?")
        record_answer(conn, session_id, ordinal, f"A{ordinal}")

    record = load_session(conn, session_id)

    assert record is not None
    assert [t.question for t in record.turns] == ["Q1?", "Q2?", "Q3?"]
    assert [t.answer for t in record.turns] == ["A1", "A2", "A3"]


def test_a_turn_ordinal_cannot_be_reused(conn: sqlite3.Connection):
    session_id = start_session(conn, "topic", "model", [make_chunk()])
    record_question(conn, session_id, 1, "Q1?")

    with pytest.raises(sqlite3.IntegrityError):
        record_question(conn, session_id, 1, "Q1 again?")


def test_end_session_marks_it_complete(conn: sqlite3.Connection):
    session_id = start_session(conn, "topic", "model", [make_chunk()])
    before = load_session(conn, session_id)
    assert before is not None and not before.is_complete

    end_session(conn, session_id)

    after = load_session(conn, session_id)
    assert after is not None and after.is_complete
    assert isinstance(after.ended_at, datetime)


# --- the ten-session limit ----------------------------------------------------


def test_only_the_ten_most_recent_sessions_are_kept(conn: sqlite3.Connection):
    for i in range(MAX_SESSIONS + 5):
        start_session(conn, f"topic {i}", "model", [make_chunk()])

    assert len(recent_sessions(conn, limit=100)) == MAX_SESSIONS


def test_pruning_drops_the_oldest_and_never_the_newest(conn: sqlite3.Connection):
    for i in range(MAX_SESSIONS + 3):
        start_session(conn, f"topic {i}", "model", [make_chunk()])

    topics = [s.topic for s in recent_sessions(conn, limit=100)]

    assert topics[0] == f"topic {MAX_SESSIONS + 2}"  # newest survived
    assert "topic 0" not in topics  # oldest went
    assert "topic 1" not in topics


def test_pruning_takes_the_turns_and_notes_with_it(conn: sqlite3.Connection):
    """Relies on ON DELETE CASCADE actually firing — the reason foreign_keys
    is switched on in connect()."""
    first = start_session(conn, "doomed", "model", [make_chunk()])
    record_question(conn, first, 1, "Q1?")

    for i in range(MAX_SESSIONS):
        start_session(conn, f"topic {i}", "model", [make_chunk()])

    assert load_session(conn, first) is None
    orphan_turns = conn.execute(
        "SELECT COUNT(*) AS n FROM turns WHERE session_id = ?", (first,)
    ).fetchone()["n"]
    orphan_notes = conn.execute(
        "SELECT COUNT(*) AS n FROM session_notes WHERE session_id = ?", (first,)
    ).fetchone()["n"]
    assert orphan_turns == 0
    assert orphan_notes == 0


# --- reading ------------------------------------------------------------------


def test_recent_sessions_is_newest_first(conn: sqlite3.Connection):
    start_session(conn, "older", "model", [make_chunk()])
    start_session(conn, "newer", "model", [make_chunk()])

    assert [s.topic for s in recent_sessions(conn)] == ["newer", "older"]


def test_recent_sessions_does_not_hydrate_turns(conn: sqlite3.Connection):
    """Listing should stay cheap; load_session is the one that reads everything."""
    session_id = start_session(conn, "topic", "model", [make_chunk()])
    record_question(conn, session_id, 1, "Q1?")

    listed = recent_sessions(conn)[0]

    assert listed.turns == []
    assert listed.chunks == []


def test_recent_sessions_on_an_empty_database(conn: sqlite3.Connection):
    assert recent_sessions(conn) == []


def test_loading_a_session_that_does_not_exist(conn: sqlite3.Connection):
    assert load_session(conn, 999) is None


def test_answered_turns_ignores_unanswered_ones(conn: sqlite3.Connection):
    session_id = start_session(conn, "topic", "model", [make_chunk()])
    record_question(conn, session_id, 1, "Q1?")
    record_answer(conn, session_id, 1, "answered")
    record_question(conn, session_id, 2, "Q2?")  # user quit here

    record = load_session(conn, session_id)

    assert record is not None
    assert isinstance(record, SessionRecord)
    assert len(record.turns) == 2
    assert record.answered_turns == 1


# --- raw messages -------------------------------------------------------------


def test_raw_messages_round_trip(conn: sqlite3.Connection):
    session_id = start_session(conn, "topic", "model", [make_chunk()])
    messages: list[MessageParam] = [
        {"role": "user", "content": "excerpts and topic"},
        {"role": "assistant", "content": "Q1?"},
    ]

    save_messages(conn, session_id, messages)

    record = load_session(conn, session_id)
    assert record is not None
    assert record.messages == messages
    assert record.is_resumable


def test_saving_messages_overwrites_rather_than_appends(conn: sqlite3.Connection):
    """Each turn snapshots the whole conversation, so the column must hold the
    latest state, not an accumulation of every snapshot taken."""
    session_id = start_session(conn, "topic", "model", [make_chunk()])
    save_messages(conn, session_id, [{"role": "user", "content": "first"}])

    save_messages(conn, session_id, [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ])

    record = load_session(conn, session_id)
    assert record is not None
    assert len(record.messages) == 2


def test_a_session_without_raw_messages_is_not_resumable(conn: sqlite3.Connection):
    """Sessions recorded before raw messages were stored still list and review,
    they just cannot be replayed."""
    session_id = start_session(conn, "topic", "model", [make_chunk()])

    record = load_session(conn, session_id)

    assert record is not None
    assert record.messages == []
    assert not record.is_resumable


def test_an_existing_database_gains_the_messages_column(tmp_path: Path):
    """A database created before this column existed must not need deleting.
    CREATE TABLE IF NOT EXISTS is a no-op on an existing table, so the column
    is added by an explicit migration."""
    path = tmp_path / "sessions.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        "CREATE TABLE sessions (id INTEGER PRIMARY KEY, topic TEXT NOT NULL,"
        " model TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT);"
    )
    legacy.execute(
        "INSERT INTO sessions (topic, model, started_at) VALUES ('old', 'm', '2026-01-01T00:00:00+00:00')"
    )
    legacy.commit()
    legacy.close()

    conn = connect(path)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
    assert "messages" in columns
    survivor = recent_sessions(conn)[0]
    assert survivor.topic == "old"  # migration preserved the existing row
    assert not survivor.is_resumable
    conn.close()
