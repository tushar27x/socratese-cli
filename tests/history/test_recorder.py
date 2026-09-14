# tests/history/test_recorder.py
import sqlite3
from pathlib import Path

import pytest

from socratese.history.recorder import SessionRecorder, recording
from socratese.history.store import connect, load_session, recent_sessions
from socratese.retrieval.models import RetrievedChunk


@pytest.fixture
def conn(tmp_path: Path):
    connection = connect(tmp_path / "sessions.db")
    yield connection
    connection.close()


def make_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        note_path=Path("/vault/Redis.md"),
        note_title="Redis",
        heading="RDB",
        content="body",
        distance=0.7,
    )


def test_a_conversation_round_trips_through_the_recorder(conn: sqlite3.Connection):
    with recording("topic", "model", [make_chunk()], conn=conn) as rec:
        rec.question("Q1?")
        rec.answer("A1")
        rec.question("Q2?")
        rec.answer("A2")
        session_id = rec.session_id

    assert session_id is not None
    record = load_session(conn, session_id)
    assert record is not None
    assert [(t.question, t.answer) for t in record.turns] == [("Q1?", "A1"), ("Q2?", "A2")]


def test_the_recorder_keeps_its_own_ordinal(conn: sqlite3.Connection):
    """Callers should never have to count turns — getting that wrong would
    silently overwrite an earlier answer."""
    with recording("topic", "model", [make_chunk()], conn=conn) as rec:
        for i in range(1, 4):
            rec.question(f"Q{i}?")
            rec.answer(f"A{i}")
        session_id = rec.session_id

    assert session_id is not None
    record = load_session(conn, session_id)
    assert record is not None
    assert [t.ordinal for t in record.turns] == [1, 2, 3]


def test_an_unanswered_final_question_is_still_recorded(conn: sqlite3.Connection):
    """The user was asked something and walked away. That is the signal."""
    with recording("topic", "model", [make_chunk()], conn=conn) as rec:
        rec.question("Q1?")
        rec.answer("A1")
        rec.question("Q2?")
        session_id = rec.session_id

    assert session_id is not None
    record = load_session(conn, session_id)
    assert record is not None
    assert record.turns[-1].answer is None
    assert record.answered_turns == 1


def test_the_session_is_closed_out_even_when_the_block_raises(conn: sqlite3.Connection):
    with pytest.raises(KeyboardInterrupt):
        with recording("topic", "model", [make_chunk()], conn=conn) as rec:
            rec.question("Q1?")
            raise KeyboardInterrupt

    record = recent_sessions(conn)[0]
    assert record.is_complete  # not left looking in-progress forever


def test_the_grounding_chunks_are_stored_at_the_start(conn: sqlite3.Connection):
    with recording("topic", "model", [make_chunk()], conn=conn) as rec:
        session_id = rec.session_id

    assert session_id is not None
    record = load_session(conn, session_id)
    assert record is not None
    assert record.chunks == [make_chunk()]


# --- degradation --------------------------------------------------------------


def test_a_broken_database_yields_a_disabled_recorder(monkeypatch: pytest.MonkeyPatch):
    """History must never cost the user a tutoring session."""
    def boom(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr("socratese.history.recorder.connect", boom)

    with recording("topic", "model", [make_chunk()]) as rec:
        rec.question("Q1?")  # must not raise
        rec.answer("A1")
        assert rec.enabled is False


def test_a_write_failure_mid_session_disables_recording_silently(conn: sqlite3.Connection):
    with recording("topic", "model", [make_chunk()], conn=conn) as rec:
        rec.question("Q1?")
        rec.answer("A1")
        conn.close()  # simulate the database going away mid-conversation

        rec.question("Q2?")  # must not raise
        rec.answer("A2")

        assert rec.enabled is False


def test_a_disabled_recorder_reports_itself_as_such():
    recorder = SessionRecorder(None, None)

    recorder.question("Q1?")
    recorder.answer("A1")

    assert recorder.enabled is False
