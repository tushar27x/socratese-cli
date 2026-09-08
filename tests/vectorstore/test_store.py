# tests/vectorstore/test_store.py
from pathlib import Path

import chromadb
import pytest

from socratese.chunking.models import Chunk
from socratese.vectorstore.store import add_chunks, chunk_id, get_collection, query


@pytest.fixture
def collection(tmp_path):
    """A real, isolated Chroma collection backed by a throwaway tmp_path."""
    client = chromadb.PersistentClient(path=str(tmp_path))
    return client.get_or_create_collection("test_chunks")


def make_chunk(note_path: str, heading: str, content: str) -> Chunk:
    return Chunk(
        note_path=Path(note_path),
        note_title=Path(note_path).stem,
        heading=heading,
        content=content,
    )


def test_chunk_id_is_stable_for_same_note_and_heading():
    chunk_a = make_chunk("notes/a.md", "Intro", "some content")
    chunk_b = make_chunk("notes/a.md", "Intro", "different content, same location")

    assert chunk_id(chunk_a) == chunk_id(chunk_b)


def test_chunk_id_differs_across_headings_in_same_note():
    chunk_a = make_chunk("notes/a.md", "Intro", "content")
    chunk_b = make_chunk("notes/a.md", "Conclusion", "content")

    assert chunk_id(chunk_a) != chunk_id(chunk_b)


def test_add_chunks_empty_list_does_not_call_collection(collection):
    add_chunks([], [], collection=collection)

    assert collection.count() == 0


def test_add_chunks_stores_documents_and_metadata(collection):
    chunks = [
        make_chunk("notes/a.md", "Intro", "First chunk content"),
        make_chunk("notes/b.md", "Body", "Second chunk content"),
    ]
    embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    add_chunks(chunks, embeddings, collection=collection)

    assert collection.count() == 2
    stored = collection.get(ids=[chunk_id(chunks[0])])
    assert stored["documents"][0] == "First chunk content"
    assert stored["metadatas"][0] == {
        "note_path": "notes/a.md",
        "note_title": "a",
        "heading": "Intro",
    }


def test_add_chunks_upserts_rather_than_duplicates(collection):
    chunk = make_chunk("notes/a.md", "Intro", "original content")

    add_chunks([chunk], [[0.1, 0.2, 0.3]], collection=collection)
    updated_chunk = make_chunk("notes/a.md", "Intro", "updated content")
    add_chunks([updated_chunk], [[0.9, 0.9, 0.9]], collection=collection)

    assert collection.count() == 1
    stored = collection.get(ids=[chunk_id(chunk)])
    assert stored["documents"][0] == "updated content"


def test_query_returns_nearest_chunk_first(collection):
    near = make_chunk("notes/near.md", "", "close match")
    far = make_chunk("notes/far.md", "", "distant match")
    add_chunks([near, far], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], collection=collection)

    results = query([1.0, 0.0, 0.0], n_results=2, collection=collection)

    assert results[0]["content"] == "close match"
    assert results[0]["note_title"] == "near"
    assert len(results) == 2


def test_query_respects_n_results(collection):
    chunks = [make_chunk(f"notes/{i}.md", "", f"content {i}") for i in range(5)]
    embeddings = [[float(i), 0.0, 0.0] for i in range(5)]
    add_chunks(chunks, embeddings, collection=collection)

    results = query([0.0, 0.0, 0.0], n_results=2, collection=collection)

    assert len(results) == 2
