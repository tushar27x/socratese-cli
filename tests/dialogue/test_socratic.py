# tests/dialogue/test_socratic.py
from pathlib import Path
from types import SimpleNamespace

import pytest

from socratese.dialogue.prompt import SYSTEM_PROMPT
from socratese.dialogue.socratic import (
    DEFAULT_MODEL,
    RELEVANCE_THRESHOLD,
    ask_questions,
    get_client,
)
from socratese.retrieval.models import RetrievedChunk

NO_MATCH = "No relevant notes found."


def make_chunk(
    note_title: str = "Redis Persistence",
    content: str = "Redis forks to write a snapshot.",
    distance: float = 0.7,
) -> RetrievedChunk:
    return RetrievedChunk(
        note_path=Path(f"notes/{note_title}.md"),
        note_title=note_title,
        heading="",
        content=content,
        distance=distance,
    )


def text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def thinking_block(thinking: str = "reasoning..."):
    """A non-text block with no `.text` attribute at all — so a filter that
    stopped checking `.type` would raise AttributeError rather than pass."""
    return SimpleNamespace(type="thinking", thinking=thinking)


class FakeMessages:
    """Stands in for client.messages — records each call, returns fixed blocks."""

    def __init__(self, blocks):
        self.blocks = blocks
        self.last_call = None
        self.call_count = 0

    def create(self, **kwargs):
        self.last_call = kwargs
        self.call_count += 1
        return SimpleNamespace(content=self.blocks)


class FakeClient:
    def __init__(self, blocks=None):
        if blocks is None:
            blocks = [text_block("What happens to concurrent writes?")]
        self.messages = FakeMessages(blocks)


# --- the relevance gate -------------------------------------------------------


def test_returns_the_no_match_message_when_every_chunk_is_too_distant():
    client = FakeClient()
    far = [make_chunk(distance=RELEVANCE_THRESHOLD + 0.1)]

    result = ask_questions("vector databases", far, client=client)

    assert result == NO_MATCH


def test_does_not_call_the_api_when_every_chunk_is_too_distant():
    """The gate exists to avoid spending a request on notes we already know are
    irrelevant. Asserting only on the return value would still pass if the
    filter ran after the call."""
    client = FakeClient()
    far = [make_chunk(distance=RELEVANCE_THRESHOLD + 0.1)]

    ask_questions("vector databases", far, client=client)

    assert client.messages.call_count == 0


def test_empty_chunk_list_short_circuits_without_calling_the_api():
    client = FakeClient()

    result = ask_questions("anything", [], client=client)

    assert result == NO_MATCH
    assert client.messages.call_count == 0


def test_a_chunk_exactly_at_the_threshold_is_kept():
    """Pins the boundary as inclusive (`<=`). Flipping to `<` would silently
    drop borderline matches, and no other assertion here would notice."""
    client = FakeClient()

    ask_questions("topic", [make_chunk(distance=RELEVANCE_THRESHOLD)], client=client)

    assert client.messages.call_count == 1


def test_only_chunks_under_the_threshold_reach_the_prompt():
    client = FakeClient()
    chunks = [
        make_chunk(note_title="Near", content="relevant body", distance=0.7),
        make_chunk(note_title="Far", content="irrelevant body", distance=RELEVANCE_THRESHOLD + 0.5),
    ]

    ask_questions("topic", chunks, client=client)

    sent = client.messages.last_call["messages"][0]["content"]
    assert "relevant body" in sent
    assert "irrelevant body" not in sent


# --- the request --------------------------------------------------------------


def test_sends_the_system_prompt_separately_from_the_notes():
    """The system half must stay byte-stable across queries so it can be cached
    later; the per-query notes belong in the user turn."""
    client = FakeClient()

    ask_questions("topic", [make_chunk()], client=client)

    call = client.messages.last_call
    assert call["system"] == SYSTEM_PROMPT
    assert call["messages"] == [{"role": "user", "content": call["messages"][0]["content"]}]
    assert SYSTEM_PROMPT not in call["messages"][0]["content"]


def test_sends_the_topic_and_the_chunk_content_in_the_user_turn():
    client = FakeClient()

    ask_questions("how does redis persist data?", [make_chunk(content="fork and snapshot")], client=client)

    sent = client.messages.last_call["messages"][0]["content"]
    assert "how does redis persist data?" in sent
    assert "fork and snapshot" in sent


def test_uses_the_default_model_when_no_override_is_set(monkeypatch):
    monkeypatch.delenv("DIALOGUE_MODEL", raising=False)
    client = FakeClient()

    ask_questions("topic", [make_chunk()], client=client)

    assert client.messages.last_call["model"] == DEFAULT_MODEL


def test_dialogue_model_env_var_overrides_the_default(monkeypatch):
    """Read inside the function, not at import time — so a value loaded from
    .env after this module is imported still takes effect."""
    monkeypatch.setenv("DIALOGUE_MODEL", "claude-sonnet-5")
    client = FakeClient()

    ask_questions("topic", [make_chunk()], client=client)

    assert client.messages.last_call["model"] == "claude-sonnet-5"


def test_requests_enough_output_tokens_for_a_complete_question(monkeypatch):
    """max_tokens is a ceiling, not a reservation — unused tokens cost nothing,
    and a tight cap would truncate a long question mid-sentence."""
    client = FakeClient()

    ask_questions("topic", [make_chunk()], client=client)

    assert client.messages.last_call["max_tokens"] >= 2048


# --- the response -------------------------------------------------------------


def test_returns_the_text_of_the_response():
    client = FakeClient([text_block("What happens to concurrent writes?")])

    result = ask_questions("topic", [make_chunk()], client=client)

    assert result == "What happens to concurrent writes?"


def test_ignores_non_text_blocks_in_the_response():
    client = FakeClient([thinking_block(), text_block("The question?")])

    result = ask_questions("topic", [make_chunk()], client=client)

    assert result == "The question?"


def test_joins_multiple_text_blocks_in_order():
    client = FakeClient([text_block("First half "), text_block("second half?")])

    result = ask_questions("topic", [make_chunk()], client=client)

    assert result == "First half second half?"


def test_strips_surrounding_whitespace_from_the_question():
    client = FakeClient([text_block("\n  A question?  \n")])

    result = ask_questions("topic", [make_chunk()], client=client)

    assert result == "A question?"


# --- client construction ------------------------------------------------------


def test_get_client_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_client()


def test_get_client_returns_client_when_api_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-testing")

    client = get_client()

    assert client.api_key == "fake-key-for-testing"


def test_ask_questions_does_not_build_a_real_client_when_one_is_injected(monkeypatch):
    """The injection seam must short-circuit get_client entirely — otherwise the
    whole suite would need ANTHROPIC_API_KEY set to run."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = FakeClient()

    result = ask_questions("topic", [make_chunk()], client=client)

    assert result == "What happens to concurrent writes?"
