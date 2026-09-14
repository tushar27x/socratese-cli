# tests/vectorstore/test_store.py
from chromadb.api.models.Collection import Collection
from pathlib import Path

import chromadb
import pytest

from socratese.chunking.models import Chunk
from socratese.vectorstore.store import add_chunks, chunk_id, query


@pytest.fixture
def collection(tmp_path: Path):
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


def test_add_chunks_empty_list_does_not_call_collection(collection: Collection):
    add_chunks([], [], vault="testvault", collection=collection)

    assert collection.count() == 0


def test_add_chunks_stores_documents_and_metadata(collection: Collection):
    chunks = [
        make_chunk("notes/a.md", "Intro", "First chunk content"),
        make_chunk("notes/b.md", "Body", "Second chunk content"),
    ]
    embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    add_chunks(chunks, embeddings, vault="testvault", collection=collection)

    assert collection.count() == 2
    stored = collection.get(ids=[chunk_id(chunks[0])])
    assert stored["documents"] is not None and stored["metadatas"] is not None
    assert stored["documents"][0] == "First chunk content"
    assert stored["metadatas"][0] == {
        "note_path": "notes/a.md",
        "note_title": "a",
        "heading": "Intro",
        "vault": "testvault",
    }


def test_add_chunks_upserts_rather_than_duplicates(collection: Collection):
    chunk = make_chunk("notes/a.md", "Intro", "original content")

    add_chunks([chunk], [[0.1, 0.2, 0.3]], vault="testvault", collection=collection)
    updated_chunk = make_chunk("notes/a.md", "Intro", "updated content")
    add_chunks([updated_chunk], [[0.9, 0.9, 0.9]], vault="testvault", collection=collection)

    assert collection.count() == 1
    stored = collection.get(ids=[chunk_id(chunk)])
    assert stored["documents"] is not None
    assert stored["documents"][0] == "updated content"


def test_query_returns_nearest_chunk_first(collection: Collection):
    near = make_chunk("notes/near.md", "", "close match")
    far = make_chunk("notes/far.md", "", "distant match")
    add_chunks([near, far], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], vault="testvault", collection=collection)

    results = query([1.0, 0.0, 0.0], n_results=2, collection=collection)

    assert results[0]["content"] == "close match"
    assert results[0]["note_title"] == "near"
    assert len(results) == 2


def test_query_respects_n_results(collection: Collection):
    chunks = [make_chunk(f"notes/{i}.md", "", f"content {i}") for i in range(5)]
    embeddings = [[float(i), 0.0, 0.0] for i in range(5)]
    add_chunks(chunks, embeddings, vault="testvault", collection=collection)

    results = query([0.0, 0.0, 0.0], n_results=2, collection=collection)

    assert len(results) == 2


def test_chunks_record_which_vault_they_came_from(collection: Collection):
    """Without this the store cannot tell two vaults apart, and selecting
    which vaults a session draws on is impossible."""
    add_chunks(
        [make_chunk("notes/a.md", "", "content")],
        [[1.0, 0.0, 0.0]],
        vault="work",
        collection=collection,
    )

    stored = collection.get()
    assert stored["metadatas"] is not None
    assert stored["metadatas"][0]["vault"] == "work"


def test_query_can_be_restricted_to_one_vault(collection: Collection):
    add_chunks(
        [make_chunk("work/a.md", "", "work content")],
        [[1.0, 0.0, 0.0]],
        vault="work",
        collection=collection,
    )
    add_chunks(
        [make_chunk("personal/b.md", "", "personal content")],
        [[1.0, 0.0, 0.0]],
        vault="personal",
        collection=collection,
    )

    results = query([1.0, 0.0, 0.0], vaults=["work"], collection=collection)

    assert [r["content"] for r in results] == ["work content"]


def test_query_can_span_several_vaults(collection: Collection):
    for name in ("work", "personal", "archive"):
        add_chunks(
            [make_chunk(f"{name}/a.md", "", f"{name} content")],
            [[1.0, 0.0, 0.0]],
            vault=name,
            collection=collection,
        )

    results = query([1.0, 0.0, 0.0], vaults=["work", "archive"], collection=collection)

    assert {r["content"] for r in results} == {"work content", "archive content"}


def test_query_without_a_filter_searches_every_vault(collection: Collection):
    for name in ("work", "personal"):
        add_chunks(
            [make_chunk(f"{name}/a.md", "", f"{name} content")],
            [[1.0, 0.0, 0.0]],
            vault=name,
            collection=collection,
        )

    results = query([1.0, 0.0, 0.0], collection=collection)

    assert len(results) == 2


def test_filtering_happens_inside_the_store_not_after(collection: Collection):
    """Asking for 2 results from one vault must return 2 from that vault, not
    whatever survives filtering a global top-2."""
    for i in range(5):
        add_chunks(
            [make_chunk(f"other/{i}.md", "", f"other {i}")],
            [[1.0, 0.0, 0.0]],
            vault="other",
            collection=collection,
        )
    for i in range(3):
        add_chunks(
            [make_chunk(f"wanted/{i}.md", "", f"wanted {i}")],
            [[0.9, 0.1, 0.0]],
            vault="wanted",
            collection=collection,
        )

    results = query([1.0, 0.0, 0.0], n_results=2, vaults=["wanted"], collection=collection)

    assert len(results) == 2
    assert all(r["vault"] == "wanted" for r in results)
