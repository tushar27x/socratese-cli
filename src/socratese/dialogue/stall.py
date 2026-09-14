"""Detecting when a conversation has stopped going anywhere.

This lives in code rather than the prompt on purpose. Three attempts were made
to get the model to notice and break out of a stalled line of questioning — a
rule against preamble, a rule against reciting the notes, and an amendment to
rule 8 telling it to stop when the excerpts cannot settle what it is asking.
All three were measured against real transcripts; none changed the behaviour,
and one measurably degraded rule 9.

The pattern: this model follows concrete per-turn rules well ("never answer",
"never confirm") and conditional meta-rules ("notice X, then change mode")
poorly. So the noticing is done here, deterministically, and the intervention
belongs to the caller.
"""
from __future__ import annotations

import re

#: How many consecutive questions must orbit the same terms before a
#: conversation counts as stalled. Four is the smallest window that did not
#: fire on healthy transcripts during evaluation.
STALL_WINDOW = 4

#: Words too common to indicate a shared subject.
STOPWORDS = frozenset({
    "the", "a", "an", "what", "do", "does", "did", "you", "your", "is", "are",
    "was", "were", "that", "this", "it", "its", "to", "of", "in", "and", "for",
    "on", "with", "when", "how", "why", "notes", "note", "about", "at", "as",
    "be", "by", "from", "if", "or", "so", "but", "would", "could", "then",
    "there", "they", "them", "we", "us", "i", "me", "my", "say", "says", "said",
    "look", "back", "asking", "ask", "asked", "actually", "specific", "just",
})


#: Shorter than this and a token is a symbol ("V", "Q") rather than a subject.
#: They match constantly and read as noise in the warning shown to the user.
MIN_TERM_LENGTH = 3


def content_words(text: str) -> set[str]:
    """The words in `text` that carry subject matter."""
    return {
        w
        for w in re.findall(r"[a-z]+", text.lower())
        if w not in STOPWORDS and len(w) >= MIN_TERM_LENGTH
    }


def orbiting_terms(
    questions: list[str], topic: str = "", window: int = STALL_WINDOW
) -> set[str]:
    """Terms shared by the last `window` questions, beyond the topic's own words.

    An empty set means the conversation is still moving. Non-empty means the
    recent questions are rewordings of one another: no pair need look alike,
    which is why simple duplicate detection misses this entirely.

    The topic's words are excluded because every question in a session about
    React mentions React — that is the subject, not evidence of circling.
    """
    if len(questions) < window:
        return set[str]()
    recent = [content_words(q) - content_words(topic) for q in questions[-window:]]
    return recent[0].intersection(*recent[1:])


def is_stalled(questions: list[str], topic: str = "", window: int = STALL_WINDOW) -> bool:
    return bool(orbiting_terms(questions, topic, window))
