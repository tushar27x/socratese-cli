# tests/cli/test_ask.py
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from anthropic.types import MessageParam
from typer.testing import CliRunner

from socratese import config
from socratese.cli import ask as ask_module
from socratese.cli.main import app
from socratese.history.store import connect, load_session, recent_sessions
from socratese.retrieval.models import RetrievedChunk
from socratese.vault.models import Vault

runner = CliRunner()


def make_chunk(distance: float = 0.7) -> RetrievedChunk:
    return RetrievedChunk(
        note_path=Path("/vault/Redis.md"),
        note_title="Redis Persistence",
        heading="RDB",
        content="Redis forks to write a point-in-time snapshot.",
        distance=distance,
    )


class FakeSession:
    """Stands in for dialogue.Session — no API calls, scripted questions.

    Maintains a real `messages` list because the CLI snapshots it into history;
    a fake without one would pass the old tests and break the new behaviour.
    """

    def __init__(self, topic: str, chunks: list[RetrievedChunk], client: object = None) -> None:
        self.topic = topic
        self.chunks = [c for c in chunks if c.distance <= 1.2]
        self.messages: list[MessageParam] = []
        self.replies: list[str] = []

    @property
    def has_grounding(self) -> bool:
        return bool(self.chunks)

    def opening_question(self) -> str:
        self.messages.append({"role": "user", "content": "<excerpts>"})
        self.messages.append({"role": "assistant", "content": "Q1?"})
        return "Q1?"

    def answer(self, response: str) -> str:
        self.replies.append(response)
        question = f"Q{len(self.replies) + 1}?"
        self.messages.append({"role": "user", "content": response})
        self.messages.append({"role": "assistant", "content": question})
        return question


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Patch names on cli.ask, which imports them at module load.

    Patching socratese.retrieval.retriever directly would rebind a name that
    ask.py never looks at again — the same trap documented for test_index.py.
    """
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    config.save_vaults([Vault(name="v", path=tmp_path, last_indexed=datetime.now(timezone.utc))])

    def fake_retrieve(topic: str, n_results: int = 5) -> list[RetrievedChunk]:
        return [make_chunk()]

    monkeypatch.setattr(ask_module, "retrieve", fake_retrieve)
    monkeypatch.setattr(ask_module, "Session", FakeSession)

    db = tmp_path / "sessions.db"
    monkeypatch.setattr("socratese.history.store.get_db_path", lambda: db)
    return db


def test_refuses_when_no_vault_has_been_indexed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    config.save_vaults([Vault(name="v", path=tmp_path, last_indexed=None)])

    result = runner.invoke(app, ["ask", "anything"])

    assert result.exit_code == 1
    assert "index" in result.output


def test_refuses_when_nothing_clears_the_relevance_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, wired: Path
):
    def nothing_relevant(topic: str, n_results: int = 5) -> list[RetrievedChunk]:
        return [make_chunk(distance=1.4)]

    monkeypatch.setattr(ask_module, "retrieve", nothing_relevant)

    result = runner.invoke(app, ["ask", "vector databases"])

    assert result.exit_code == 1
    assert "nothing on" in result.output
    assert not wired.exists()  # no session opened, so no database created


def test_a_session_runs_and_is_recorded(wired: Path):
    result = runner.invoke(app, ["ask", "redis"], input="my answer\n\n")

    assert result.exit_code == 0
    assert "Q1?" in result.output

    conn = connect(wired)
    stored = recent_sessions(conn)
    assert len(stored) == 1
    assert stored[0].topic == "redis"
    assert stored[0].is_complete

    record = load_session(conn, stored[0].id)
    assert record is not None
    assert [(t.question, t.answer) for t in record.turns] == [("Q1?", "my answer"), ("Q2?", None)]
    assert record.chunks == [make_chunk()]
    conn.close()


def test_sources_are_hidden_unless_asked_for(wired: Path):
    """Naming the source note mid-session tells you where to look, which
    defeats the recall the tool exists to force."""
    without = runner.invoke(app, ["ask", "redis"], input="\n")
    with_flag = runner.invoke(app, ["ask", "redis", "--sources"], input="\n")

    assert "Grounded in" not in without.output
    assert "Grounded in" in with_flag.output
    assert "Redis Persistence" in with_flag.output


def test_a_broken_history_database_does_not_stop_the_session(
    monkeypatch: pytest.MonkeyPatch, wired: Path
):
    """History is secondary to tutoring — it must never cost a conversation."""
    def boom(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr("socratese.history.recorder.connect", boom)

    result = runner.invoke(app, ["ask", "redis"], input="my answer\n\n")

    assert result.exit_code == 0
    assert "Q1?" in result.output
    assert "Q2?" in result.output


def test_the_raw_conversation_is_stored_for_replay(wired: Path):
    """Turns are the queryable view; raw messages are what resume replays."""
    runner.invoke(app, ["ask", "redis"], input="my answer\n\n")

    conn = connect(wired)
    record = load_session(conn, recent_sessions(conn)[0].id)
    assert record is not None
    assert record.is_resumable
    assert [m["role"] for m in record.messages] == ["user", "assistant", "user", "assistant"]
    assert record.messages[2]["content"] == "my answer"
    conn.close()
