# tests/dialogue/test_socratic.py
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic import Anthropic

from socratese.dialogue.prompt import SYSTEM_PROMPT
from socratese.dialogue.socratic import (
    DEFAULT_MODEL,
    RELEVANCE_THRESHOLD,
    Session,
    get_client,
)
from socratese.retrieval.models import RetrievedChunk


def make_chunk(
    note_title: str = "Transformer Architecture",
    content: str = "A high score means the model uses more of the value vector.",
    distance: float = 0.7,
) -> RetrievedChunk:
    return RetrievedChunk(
        note_path=Path(f"notes/{note_title}.md"),
        note_title=note_title,
        heading="",
        content=content,
        distance=distance,
    )


class FakeMessages:
    """Stands in for client.messages — records every call, returns numbered replies."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        # snapshot: the session passes its live message list by reference,
        # and a real client serialises immediately rather than aliasing it
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        text = f"question {len(self.calls)}?"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    def __init__(self) -> None:
        self.messages = FakeMessages()


def session_with(
    chunks: list[RetrievedChunk], topic: str = "attention"
) -> tuple[Session, FakeClient]:
    fake = FakeClient()
    return Session(topic, chunks, client=cast(Anthropic, fake)), fake


# --- grounding ----------------------------------------------------------------


def test_chunks_are_filtered_by_threshold_at_construction():
    near, far = make_chunk("Near", distance=0.7), make_chunk("Far", distance=1.4)

    session, _ = session_with([near, far])

    assert [c.note_title for c in session.chunks] == ["Near"]


def test_a_chunk_exactly_at_the_threshold_is_kept():
    """Pins `<=` as inclusive, matching the single-shot path."""
    session, _ = session_with([make_chunk(distance=RELEVANCE_THRESHOLD)])

    assert session.has_grounding


def test_has_grounding_is_false_when_every_chunk_is_too_distant():
    session, _ = session_with([make_chunk(distance=RELEVANCE_THRESHOLD + 0.1)])

    assert session.has_grounding is False


def test_has_grounding_is_false_for_no_chunks_at_all():
    session, _ = session_with([])

    assert session.has_grounding is False


def test_checking_grounding_does_not_build_a_client(monkeypatch: pytest.MonkeyPatch):
    """Being told your vault has nothing on a topic must not require credentials.

    The client is lazy precisely so this path works with no API key set.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    session = Session("attention", [make_chunk(distance=1.4)])

    assert session.has_grounding is False  # would raise ValueError if eager


def test_dropped_chunks_never_reach_the_prompt():
    near = make_chunk("Near", content="kept body", distance=0.7)
    far = make_chunk("Far", content="dropped body", distance=1.4)
    session, fake = session_with([near, far])

    session.opening_question()

    sent = str(fake.messages.calls[0]["messages"][0]["content"])
    assert "kept body" in sent
    assert "dropped body" not in sent


# --- conversation state -------------------------------------------------------


def test_opening_question_seeds_history_with_the_excerpts():
    session, _ = session_with([make_chunk(content="Q dot K scores the match.")])

    session.opening_question()

    assert session.messages[0]["role"] == "user"
    assert "Q dot K scores the match." in str(session.messages[0]["content"])


def test_the_models_own_question_is_recorded_as_an_assistant_turn():
    """Without this the model cannot see what it already asked, and rule 9
    ("never repeat a question") has nothing to work from."""
    session, _ = session_with([make_chunk()])

    question = session.opening_question()

    assert session.messages[-1] == {"role": "assistant", "content": question}


def test_history_alternates_user_and_assistant_across_turns():
    session, _ = session_with([make_chunk()])

    session.opening_question()
    session.answer("my first answer")
    session.answer("my second answer")

    assert [m["role"] for m in session.messages] == [
        "user", "assistant", "user", "assistant", "user", "assistant"
    ]


def test_each_turn_resends_the_whole_conversation():
    """The Messages API is stateless — a turn that sent only the latest reply
    would strip the grounding and every prior question."""
    session, fake = session_with([make_chunk()])

    session.opening_question()
    session.answer("an answer")

    assert len(fake.messages.calls[0]["messages"]) == 1
    assert len(fake.messages.calls[1]["messages"]) == 3


def test_the_answer_is_sent_verbatim():
    session, fake = session_with([make_chunk()])
    session.opening_question()

    session.answer("softmax turns the scores into weights")

    assert fake.messages.calls[1]["messages"][2] == {
        "role": "user",
        "content": "softmax turns the scores into weights",
    }


def test_grounding_is_not_re_sent_on_every_turn():
    """The excerpts are seeded once. Re-appending them each turn would bloat
    the history and let the model drift onto the newest copy."""
    session, fake = session_with([make_chunk(content="unique body text")])

    session.opening_question()
    session.answer("an answer")

    payload = str(fake.messages.calls[1]["messages"])
    assert payload.count("unique body text") == 1


def test_one_api_call_per_turn():
    session, fake = session_with([make_chunk()])

    session.opening_question()
    session.answer("a")
    session.answer("b")

    assert len(fake.messages.calls) == 3


# --- the request --------------------------------------------------------------


def test_every_turn_sends_the_system_prompt():
    session, fake = session_with([make_chunk()])

    session.opening_question()
    session.answer("an answer")

    assert all(call["system"] == SYSTEM_PROMPT for call in fake.messages.calls)


def test_uses_the_default_model_when_no_override_is_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DIALOGUE_MODEL", raising=False)
    session, fake = session_with([make_chunk()])

    session.opening_question()

    assert fake.messages.calls[0]["model"] == DEFAULT_MODEL


def test_dialogue_model_env_var_overrides_the_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DIALOGUE_MODEL", "claude-opus-5")
    session, fake = session_with([make_chunk()])

    session.opening_question()

    assert fake.messages.calls[0]["model"] == "claude-opus-5"


# --- the response -------------------------------------------------------------


def test_returns_the_text_of_each_reply():
    session, _ = session_with([make_chunk()])

    assert session.opening_question() == "question 1?"
    assert session.answer("a") == "question 2?"


def test_ignores_non_text_blocks():
    """A block with no `.text` attribute at all, so a filter that stopped
    checking `.type` would raise rather than quietly pass."""
    session, fake = session_with([make_chunk()])
    fake.messages.create = lambda **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        content=[
            SimpleNamespace(type="thinking", thinking="..."),
            SimpleNamespace(type="text", text="  the question?  "),
        ]
    )

    assert session.opening_question() == "the question?"


def test_the_system_prompt_is_not_duplicated_into_the_user_turn():
    """System and notes are separate halves. Folding the rules into the user
    turn would make the cached prefix vary with every query."""
    session, fake = session_with([make_chunk()])

    session.opening_question()

    call = fake.messages.calls[0]
    assert call["system"] == SYSTEM_PROMPT
    assert SYSTEM_PROMPT not in str(call["messages"][0]["content"])


def test_the_topic_is_sent_alongside_the_excerpts():
    session, fake = session_with([make_chunk()], topic="how does redis persist data?")

    session.opening_question()

    assert "how does redis persist data?" in str(fake.messages.calls[0]["messages"][0]["content"])


def test_requests_enough_output_tokens_for_a_complete_question():
    """max_tokens is a ceiling, not a reservation — unused tokens cost nothing,
    and a tight cap would truncate a question mid-sentence."""
    session, fake = session_with([make_chunk()])

    session.opening_question()

    assert fake.messages.calls[0]["max_tokens"] >= 2048


def test_joins_multiple_text_blocks_in_order():
    session, fake = session_with([make_chunk()])
    fake.messages.create = lambda **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        content=[
            SimpleNamespace(type="text", text="First half "),
            SimpleNamespace(type="text", text="second half?"),
        ]
    )

    assert session.opening_question() == "First half second half?"


# --- client construction ------------------------------------------------------


def test_get_client_raises_when_api_key_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_client()


def test_get_client_returns_client_when_api_key_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-testing")

    client = get_client()

    assert client.api_key == "fake-key-for-testing"


def test_an_injected_client_is_never_replaced(monkeypatch: pytest.MonkeyPatch):
    """The injection seam must short-circuit get_client entirely, or the whole
    suite would need ANTHROPIC_API_KEY set to run."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    session, fake = session_with([make_chunk()])

    session.opening_question()

    assert session.client is fake  # type: ignore[comparison-overlap]
