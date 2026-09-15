"""Starting a tutoring session, independent of how it is presented.

This is the one layer that knows about config, retrieval and dialogue at the
same time. It exists so the CLI and the TUI share the setup sequence — which
vaults count, what to retrieve, whether anything cleared the relevance gate —
instead of each re-implementing it and drifting apart.

It raises rather than prints: the caller owns how a failure is rendered.
"""
from __future__ import annotations

from socratese.config import load_vaults
from socratese.dialogue.socratic import Session
from socratese.history.models import SessionRecord
from socratese.retrieval.retriever import retrieve
from socratese.vault.models import Vault


class TutorError(Exception):
    """Something stopped a session from starting. Message is user-facing."""


class NoVaultsIndexed(TutorError):
    def __init__(self) -> None:
        super().__init__("No vault has been indexed yet.")


class UnknownVaults(TutorError):
    def __init__(self, unknown: list[str], known: list[str]) -> None:
        self.unknown = unknown
        self.known = known
        super().__init__(
            f"No indexed vault named {', '.join(unknown)}. "
            f"Indexed: {', '.join(known) or 'none'}."
        )


class NothingRelevant(TutorError):
    def __init__(self, topic: str) -> None:
        self.topic = topic
        super().__init__(f"Your notes have nothing on '{topic}' yet.")


class NotResumable(TutorError):
    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        super().__init__(
            f"Session {session_id} predates transcript storage, "
            "so there is nothing to continue from."
        )


def indexed_vaults() -> list[Vault]:
    """Vaults that have actually been indexed. Others cannot be searched."""
    return [v for v in load_vaults() if v.last_indexed]


def start(topic: str, n_chunks: int = 5, vaults: list[str] | None = None) -> Session:
    """Retrieve for `topic` and return a session ready for its first question.

    Raises TutorError when the vault set is unusable or nothing is relevant.
    Network errors from the embedding call propagate untouched — the caller
    already has to handle those for the dialogue request anyway.
    """
    available = indexed_vaults()
    if not available:
        raise NoVaultsIndexed

    known = {v.name for v in available}
    unknown = [name for name in (vaults or []) if name not in known]
    if unknown:
        raise UnknownVaults(unknown, sorted(known))

    chunks = retrieve(topic, n_results=n_chunks, vaults=vaults or None)
    session = Session(topic, chunks)
    if not session.has_grounding:
        raise NothingRelevant(topic)

    return session


def resume(record: SessionRecord) -> Session:
    """Rebuild a stored session so it can be continued."""
    if not record.is_resumable:
        raise NotResumable(record.id)
    return Session.from_messages(record.topic, record.chunks, record.messages)
