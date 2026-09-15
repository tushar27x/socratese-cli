# tests/test_tutor.py
from datetime import datetime, timezone
from pathlib import Path

import pytest

from socratese import config, tutor
from socratese.history.models import SessionRecord
from socratese.retrieval.models import RetrievedChunk
from socratese.vault.models import Vault


def make_chunk(distance: float = 0.7, vault: str = "work") -> RetrievedChunk:
    return RetrievedChunk(
        note_path=Path("/vault/Redis.md"),
        note_title="Redis",
        heading="RDB",
        content="body",
        distance=distance,
        vault=vault,
    )


@pytest.fixture
def vaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    config.save_vaults([
        Vault(name="work", path=tmp_path / "work", last_indexed=datetime.now(timezone.utc)),
        Vault(name="personal", path=tmp_path / "personal", last_indexed=datetime.now(timezone.utc)),
        Vault(name="never-indexed", path=tmp_path / "other", last_indexed=None),
    ])


@pytest.fixture
def retrieval(monkeypatch: pytest.MonkeyPatch):
    """Records what the tutor asked retrieval for."""
    calls: list[dict[str, object]] = []

    def spy(query: str, n_results: int = 5, vaults: list[str] | None = None) -> list[RetrievedChunk]:
        calls.append({"query": query, "n_results": n_results, "vaults": vaults})
        return [make_chunk()]

    monkeypatch.setattr(tutor, "retrieve", spy)
    return calls


def test_indexed_vaults_excludes_never_indexed_ones(vaults: None):
    """An un-indexed vault has no chunks, so searching it would silently
    return nothing rather than failing."""
    assert [v.name for v in tutor.indexed_vaults()] == ["work", "personal"]


def test_start_returns_a_session_ready_for_its_first_question(vaults: None, retrieval: list[dict[str, object]]):
    session = tutor.start("redis persistence")

    assert session.topic == "redis persistence"
    assert session.has_grounding
    assert session.messages == []


def test_start_passes_the_topic_and_size_through(vaults: None, retrieval: list[dict[str, object]]):
    tutor.start("redis", n_chunks=9)

    assert retrieval[0]["query"] == "redis"
    assert retrieval[0]["n_results"] == 9


def test_start_forwards_a_vault_filter(vaults: None, retrieval: list[dict[str, object]]):
    tutor.start("redis", vaults=["work"])

    assert retrieval[0]["vaults"] == ["work"]


def test_an_empty_vault_list_means_all_vaults(vaults: None, retrieval: list[dict[str, object]]):
    """An empty filter must become None, not a filter matching nothing."""
    tutor.start("redis", vaults=[])

    assert retrieval[0]["vaults"] is None


def test_no_indexed_vaults_is_refused_before_retrieving(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, retrieval: list[dict[str, object]]
):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    config.save_vaults([Vault(name="v", path=tmp_path, last_indexed=None)])

    with pytest.raises(tutor.NoVaultsIndexed):
        tutor.start("redis")

    assert retrieval == []  # no embedding spent on a doomed search


def test_an_unknown_vault_is_refused_and_names_the_real_ones(
    vaults: None, retrieval: list[dict[str, object]]
):
    with pytest.raises(tutor.UnknownVaults) as caught:
        tutor.start("redis", vaults=["work", "typo"])

    assert caught.value.unknown == ["typo"]
    assert caught.value.known == ["personal", "work"]
    assert retrieval == []


def test_a_vault_that_exists_but_was_never_indexed_is_unknown(
    vaults: None, retrieval: list[dict[str, object]]
):
    """It is in the config but has no chunks — treating it as valid would give
    a session silently grounded in nothing."""
    with pytest.raises(tutor.UnknownVaults):
        tutor.start("redis", vaults=["never-indexed"])


def test_nothing_clearing_the_gate_is_refused(
    monkeypatch: pytest.MonkeyPatch, vaults: None
):
    def nothing_close(
        query: str, n_results: int = 5, vaults: list[str] | None = None
    ) -> list[RetrievedChunk]:
        return [make_chunk(distance=1.4)]

    monkeypatch.setattr(tutor, "retrieve", nothing_close)

    with pytest.raises(tutor.NothingRelevant) as caught:
        tutor.start("vector databases")

    assert caught.value.topic == "vector databases"


def test_every_failure_is_a_tutor_error(vaults: None, retrieval: list[dict[str, object]]):
    """Callers catch the base class to render a message; a failure outside the
    hierarchy would reach the user as a traceback."""
    for error in (tutor.NoVaultsIndexed, tutor.UnknownVaults, tutor.NothingRelevant, tutor.NotResumable):
        assert issubclass(error, tutor.TutorError)


# --- resuming -----------------------------------------------------------------


def test_resume_rebuilds_a_stored_session():
    record = SessionRecord(
        id=1,
        topic="redis",
        model="claude-haiku-4-5",
        started_at=datetime.now(timezone.utc),
        messages=[{"role": "user", "content": "excerpts"}, {"role": "assistant", "content": "Q1?"}],
        chunks=[make_chunk()],
    )

    session = tutor.resume(record)

    assert session.topic == "redis"
    assert len(session.messages) == 2
    assert session.chunks == [make_chunk()]


def test_resuming_a_session_without_a_transcript_is_refused():
    record = SessionRecord(
        id=7, topic="redis", model="m", started_at=datetime.now(timezone.utc), chunks=[make_chunk()]
    )

    with pytest.raises(tutor.NotResumable) as caught:
        tutor.resume(record)

    assert caught.value.session_id == 7
