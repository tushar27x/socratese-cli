from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

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
    turns: list[Turn] = field(default_factory=list[Turn])
    chunks: list[RetrievedChunk] = field(default_factory=list[RetrievedChunk])

    @property
    def answered_turns(self) -> int:
        return sum(1 for t in self.turns if t.answer)

    @property
    def is_complete(self) -> bool:
        return self.ended_at is not None
