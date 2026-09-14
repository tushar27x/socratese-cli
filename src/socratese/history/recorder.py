"""Turn-by-turn recording for a live session.

History is secondary to tutoring: if the database cannot be opened or written,
the session must still run. Every failure here degrades to not recording, never
to interrupting the conversation.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable, Generator
from contextlib import contextmanager

from anthropic.types import MessageParam

from socratese.history.store import (
    connect,
    end_session,
    last_ordinal,
    reopen_session,
    record_answer,
    record_question,
    save_messages,
    start_session,
)
from socratese.retrieval.models import RetrievedChunk


class SessionRecorder:
    """Writes questions and answers as they happen, keeping its own ordinal.

    A recorder with `session_id` of None is disabled — its methods are no-ops.
    That is what a failed database gets, so callers never branch on it.
    """

    def __init__(
        self,
        conn: sqlite3.Connection | None,
        session_id: int | None,
        start_at: int = 0,
    ) -> None:
        self._conn = conn
        self.session_id = session_id
        self._ordinal = start_at

    @property
    def enabled(self) -> bool:
        return self._conn is not None and self.session_id is not None

    def question(self, text: str, messages: list[MessageParam] | None = None) -> None:
        self._ordinal += 1
        self._write(lambda conn, sid: record_question(conn, sid, self._ordinal, text), messages)

    def answer(self, text: str, messages: list[MessageParam] | None = None) -> None:
        self._write(lambda conn, sid: record_answer(conn, sid, self._ordinal, text), messages)

    def _write(
        self,
        operation: Callable[[sqlite3.Connection, int], None],
        messages: list[MessageParam] | None,
    ) -> None:
        """Apply one write plus an optional message snapshot, or disable on error.

        `messages` is passed in rather than read off a Session so this module
        stays independent of the dialogue layer.
        """
        if self._conn is None or self.session_id is None:
            return
        try:
            operation(self._conn, self.session_id)
            if messages is not None:
                save_messages(self._conn, self.session_id, messages)
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


@contextmanager
def resuming(
    session_id: int, conn: sqlite3.Connection | None = None
) -> Generator[SessionRecorder]:
    """Continue recording into an existing session rather than opening a new one.

    A resumed conversation belongs in the row it started in; splitting it would
    fragment the transcript and burn two of the ten slots on one conversation.
    """
    owned = conn is None
    try:
        conn = conn or connect()
        reopen_session(conn, session_id)
        start_at = last_ordinal(conn, session_id)
    except sqlite3.Error:
        yield SessionRecorder(None, None)
        return

    recorder = SessionRecorder(conn, session_id, start_at=start_at)
    try:
        yield recorder
    finally:
        try:
            end_session(conn, session_id)
        except sqlite3.Error:
            pass
        if owned:
            conn.close()
