from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from anthropic.types import MessageParam

from socratese.retrieval.models import RetrievedChunk


@dataclass
class Turn:
    """One question and the answer it drew. `answer` is None when the user
    quit without replying — abandonment is signal, not missing data."""

    ordinal: int
    question: str
    answer: str | None = None


@dataclass
class SessionRecord:
    """A stored conversation, enough to review or resume it.

    Carries the grounding chunks rather than just their identifiers, so a
    resumed session rebuilds the exact prompt it was originally given even if
    the vault has been re-indexed since.
    """

    id: int
    topic: str
    model: str
    started_at: datetime
    ended_at: datetime | None = None
    #: The conversation exactly as sent to the API, for replay. Empty for
    #: sessions recorded before raw messages were stored.
    messages: list[MessageParam] = field(default_factory=list[MessageParam])
    turns: list[Turn] = field(default_factory=list[Turn])
    #: How many turns the user actually answered. Populated by the store for
    #: both listings and full loads, so it is correct even when `turns` is not
    #: hydrated — computing it from `turns` silently reported 0 for listings.
    answered_count: int = 0
    chunks: list[RetrievedChunk] = field(default_factory=list[RetrievedChunk])

    @property
    def is_resumable(self) -> bool:
        """Older sessions have turns but no raw messages, so cannot be replayed."""
        return bool(self.messages)


    @property
    def is_complete(self) -> bool:
        return self.ended_at is not None
