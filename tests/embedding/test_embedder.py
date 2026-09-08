# tests/embedding/test_embedder.py
from pathlib import Path
from types import SimpleNamespace

import pytest

from socratese.chunking.models import Chunk
from socratese.embedding.embedder import embed_chunks, get_client


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
        self.last_call = None

    def create(self, model: str, input: list[str]):
        self.last_call = {"model": model, "input": input}
        # one fake vector per input text, so we can check ordering
        data = [SimpleNamespace(embedding=[float(i)] * 3) for i in range(len(input))]
        return SimpleNamespace(data=data)


class FakeClient:
    def __init__(self):
        self.embeddings = FakeEmbeddings()


def test_embed_chunks_empty_list_returns_empty_without_calling_client():
    client = FakeClient()

    result = embed_chunks([], client=client)

    assert result == []
    assert client.embeddings.last_call is None  # never called


def test_embed_chunks_returns_one_vector_per_chunk_in_order():
    client = FakeClient()
    chunks = [make_chunk("first"), make_chunk("second"), make_chunk("third")]

    result = embed_chunks(chunks, client=client)

    assert result == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]


def test_embed_chunks_sends_chunk_content_as_input_texts():
    client = FakeClient()
    chunks = [make_chunk("alpha"), make_chunk("beta")]

    embed_chunks(chunks, client=client)

    assert client.embeddings.last_call["input"] == ["alpha", "beta"]


def test_embed_chunks_uses_configured_model():
    client = FakeClient()

    embed_chunks([make_chunk("text")], client=client)

    assert client.embeddings.last_call["model"] == "text-embedding-3-small"


def test_get_client_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_client()


def test_get_client_returns_client_when_api_key_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-testing")

    client = get_client()

    assert client.api_key == "fake-key-for-testing"
