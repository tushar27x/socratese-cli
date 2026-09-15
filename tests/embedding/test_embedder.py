# tests/embedding/test_embedder.py
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from openai import OpenAI

from socratese.chunking.models import Chunk
from socratese.embedding.embedder import (
    BATCH_SIZE,
    embed_chunks,
    embed_text,
    get_client,
)


def make_chunk(content: str) -> Chunk:
    return Chunk(
        note_path=Path("fake/note.md"),
        note_title="note",
        heading="",
        content=content,
    )


class FakeEmbeddings:
    """Stands in for client.embeddings — records the call, returns fake vectors."""

    def __init__(self):
        self.last_call: dict[str, Any] = {}
        self.call_count = 0

    def create(self, model: str, input: list[str]):
        self.last_call = {"model": model, "input": input}
        self.call_count += 1
        # one fake vector per input text, so we can check ordering
        data = [SimpleNamespace(embedding=[float(i)] * 3) for i in range(len(input))]
        return SimpleNamespace(data=data)


class FakeClient:
    def __init__(self):
        self.embeddings = FakeEmbeddings()


def test_embed_chunks_empty_list_returns_empty_without_calling_client():
    client = FakeClient()

    result = embed_chunks([], client=cast(OpenAI, client))

    assert result == []
    assert client.embeddings.call_count == 0  # never called


def test_embed_chunks_returns_one_vector_per_chunk_in_order():
    client = FakeClient()
    chunks = [make_chunk("first"), make_chunk("second"), make_chunk("third")]

    result = embed_chunks(chunks, client=cast(OpenAI, client))

    assert result == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]


def test_embed_chunks_sends_chunk_content_as_input_texts():
    client = FakeClient()
    chunks = [make_chunk("alpha"), make_chunk("beta")]

    embed_chunks(chunks, client=cast(OpenAI, client))

    assert client.embeddings.last_call["input"] == ["alpha", "beta"]


def test_embed_chunks_uses_configured_model():
    client = FakeClient()

    embed_chunks([make_chunk("text")], client=cast(OpenAI, client))

    assert client.embeddings.last_call["model"] == "text-embedding-3-small"


def test_embed_text_sends_the_text_as_a_single_input():
    client = FakeClient()

    embed_text("what is a vector database?", client=cast(OpenAI, client))

    assert client.embeddings.last_call["input"] == ["what is a vector database?"]


def test_embed_text_returns_one_flat_vector():
    client = FakeClient()

    result = embed_text("query", client=cast(OpenAI, client))

    # embed_chunks returns list[list[float]]; embed_text must unwrap to list[float],
    # since that is what the vector store's query() expects.
    assert result == [0.0, 0.0, 0.0]


def test_embed_text_uses_configured_model():
    client = FakeClient()

    embed_text("query", client=cast(OpenAI, client))

    assert client.embeddings.last_call["model"] == "text-embedding-3-small"


def test_get_client_raises_when_api_key_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_client()


def test_get_client_returns_client_when_api_key_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-testing")

    client = get_client()

    assert client.api_key == "fake-key-for-testing"


# --- batching -----------------------------------------------------------------


class CountingEmbeddings:
    """Records every request, so batch boundaries are observable."""

    def __init__(self) -> None:
        self.batches: list[int] = []

    def create(self, model: str, input: list[str]):
        self.batches.append(len(input))
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[float(i)] * 3) for i in range(len(input))]
        )


class CountingClient:
    def __init__(self) -> None:
        self.embeddings = CountingEmbeddings()


def test_a_large_vault_is_split_into_batches():
    """One request for a whole vault works until it does not — a big vault can
    exceed the request limit, and one failure would cost every chunk."""
    client = CountingClient()
    chunks = [make_chunk(f"chunk {i}") for i in range(BATCH_SIZE * 2 + 5)]

    embed_chunks(chunks, client=cast(OpenAI, client))

    assert client.embeddings.batches == [BATCH_SIZE, BATCH_SIZE, 5]


def test_batching_preserves_order():
    """Embeddings are matched to chunks by position downstream, so a reordered
    batch would silently attach every vector to the wrong note."""
    client = CountingClient()
    chunks = [make_chunk(f"chunk {i}") for i in range(BATCH_SIZE + 3)]

    result = embed_chunks(chunks, client=cast(OpenAI, client))

    assert len(result) == len(chunks)
    assert result[0] == [0.0, 0.0, 0.0]
    assert result[BATCH_SIZE] == [0.0, 0.0, 0.0]  # first of the second batch


def test_progress_is_reported_after_each_batch():
    client = CountingClient()
    chunks = [make_chunk(f"chunk {i}") for i in range(BATCH_SIZE * 2)]
    seen: list[tuple[int, int]] = []

    embed_chunks(chunks, client=cast(OpenAI, client), on_progress=lambda d, t: seen.append((d, t)))

    assert seen == [(BATCH_SIZE, BATCH_SIZE * 2), (BATCH_SIZE * 2, BATCH_SIZE * 2)]


def test_a_small_vault_is_a_single_request():
    client = CountingClient()

    embed_chunks([make_chunk("only one")], client=cast(OpenAI, client))

    assert client.embeddings.batches == [1]
