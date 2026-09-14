"""Turn-by-turn recording for a live session.

History is secondary to tutoring: if the database cannot be opened or written,
the session must still run. Every failure here degrades to not recording, never
to interrupting the conversation.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from socratese.history.store import (
    connect,
    end_session,
    record_answer,
    record_question,
    start_session,
)
from socratese.retrieval.models import RetrievedChunk


class SessionRecorder:
    """Writes questions and answers as they happen, keeping its own ordinal.

    A recorder with `session_id` of None is disabled — its methods are no-ops.
    That is what a failed database gets, so callers never branch on it.
    """

    def __init__(self, conn: sqlite3.Connection | None, session_id: int | None) -> None:
        self._conn = conn
        self.session_id = session_id
        self._ordinal = 0

    @property
    def enabled(self) -> bool:
        return self._conn is not None and self.session_id is not None

    def question(self, text: str) -> None:
        self._ordinal += 1
        if self._conn is None or self.session_id is None:
            return
        try:
            record_question(self._conn, self.session_id, self._ordinal, text)
        except sqlite3.Error:
            self._conn = None

    def answer(self, text: str) -> None:
        if self._conn is None or self.session_id is None:
            return
        try:
            record_answer(self._conn, self.session_id, self._ordinal, text)
        except sqlite3.Error:
            self._conn = None


@contextmanager
def recording(
    topic: str,
    model: str,
    chunks: list[RetrievedChunk],
    conn: sqlite3.Connection | None = None,
) -> Generator[SessionRecorder]:
    """Open a recorded session, closing it out however the block exits.

    `end_session` runs in a finally, so a Ctrl-C'd or errored conversation is
    still marked finished rather than left looking in-progress forever.
    """
    owned = conn is None
    try:
        conn = conn or connect()
        session_id = start_session(conn, topic, model, chunks)
    except sqlite3.Error:
        yield SessionRecorder(None, None)
        return

    recorder = SessionRecorder(conn, session_id)
    try:
        yield recorder
    finally:
        try:
            end_session(conn, session_id)
        except sqlite3.Error:
            pass
        if owned:
            conn.close()
