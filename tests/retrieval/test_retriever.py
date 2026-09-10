# tests/retrieval/test_retriever.py
from pathlib import Path
from types import SimpleNamespace

import chromadb
import pytest

from socratese.chunking.models import Chunk
from socratese.retrieval.models import RetrievedChunk
from socratese.retrieval.retriever import retrieve
from socratese.vectorstore.store import add_chunks


@pytest.fixture
def collection(tmp_path):
    """A real, isolated Chroma collection backed by a throwaway tmp_path."""
    client = chromadb.PersistentClient(path=str(tmp_path))
    return client.get_or_create_collection("test_retrieval")


class FakeEmbeddings:
    """Stands in for client.embeddings — records the call, returns a fixed vector."""

    def __init__(self, vector: list[float]):
        self.vector = vector
        self.last_call = None

    def create(self, model: str, input: list[str]):
        self.last_call = {"model": model, "input": input}
        return SimpleNamespace(data=[SimpleNamespace(embedding=list(self.vector))])


class FakeClient:
    """Returns a caller-chosen query vector, so tests control which chunk is nearest."""

    def __init__(self, vector: list[float] = [1.0, 0.0, 0.0]):
        self.embeddings = FakeEmbeddings(vector)


def make_chunk(note_path: str, heading: str, content: str) -> Chunk:
    return Chunk(
        note_path=Path(note_path),
        note_title=Path(note_path).stem,
        heading=heading,
        content=content,
    )


def test_retrieve_maps_stored_metadata_onto_retrieved_chunk(collection):
    add_chunks(
        [make_chunk("notes/a.md", "Intro", "alpha content")],
        [[1.0, 0.0, 0.0]],
        collection=collection,
    )

    results = retrieve("query", client=FakeClient(), collection=collection)

    assert len(results) == 1
    hit = results[0]
    assert isinstance(hit, RetrievedChunk)
    assert hit.note_title == "a"
    assert hit.heading == "Intro"
    assert hit.content == "alpha content"


def test_retrieve_restores_note_path_as_a_path_object(collection):
    add_chunks(
        [make_chunk("notes/a.md", "", "content")], [[1.0, 0.0, 0.0]], collection=collection
    )

    results = retrieve("query", client=FakeClient(), collection=collection)

    # Chroma metadata can only hold primitives, so the store writes note_path as a
    # str; the retriever is responsible for turning it back into a Path.
    assert isinstance(results[0].note_path, Path)
    assert results[0].note_path == Path("notes/a.md")


def test_retrieve_returns_nearest_chunk_first(collection):
    near = make_chunk("notes/near.md", "", "close match")
    far = make_chunk("notes/far.md", "", "distant match")
    add_chunks([near, far], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], collection=collection)

    results = retrieve("query", client=FakeClient([1.0, 0.0, 0.0]), collection=collection)

    assert [r.note_title for r in results] == ["near", "far"]
    assert results[0].distance < results[1].distance


def test_retrieve_reports_real_distances_on_chromas_scale(collection):
    """Pins both ends of the scale: identical vectors read 0.0, orthogonal ones 2.0.

    Chroma's default space is squared L2, so lower means closer and the value is
    not a 0-1 similarity. Anchoring both ends here is what makes a distance
    threshold elsewhere in the app interpretable.
    """
    same = make_chunk("notes/same.md", "", "identical vector")
    orthogonal = make_chunk("notes/orthogonal.md", "", "unrelated vector")
    add_chunks(
        [same, orthogonal], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], collection=collection
    )

    results = retrieve("query", client=FakeClient([1.0, 0.0, 0.0]), collection=collection)

    by_title = {r.note_title: r.distance for r in results}
    assert by_title["same"] == pytest.approx(0.0, abs=1e-6)
    assert by_title["orthogonal"] == pytest.approx(2.0, abs=1e-6)


def test_retrieve_embeds_the_query_text_verbatim(collection):
    add_chunks(
        [make_chunk("notes/a.md", "", "content")], [[1.0, 0.0, 0.0]], collection=collection
    )
    client = FakeClient()

    retrieve("what is a vector database?", client=client, collection=collection)

    assert client.embeddings.last_call["input"] == ["what is a vector database?"]


def test_retrieve_respects_n_results(collection):
    chunks = [make_chunk(f"notes/{i}.md", "", f"content {i}") for i in range(5)]
    add_chunks(chunks, [[float(i), 0.0, 0.0] for i in range(5)], collection=collection)

    results = retrieve(
        "query", n_results=2, client=FakeClient([0.0, 0.0, 0.0]), collection=collection
    )

    assert len(results) == 2


def test_retrieve_returns_all_chunks_when_n_results_exceeds_collection_size(collection):
    add_chunks(
        [make_chunk("notes/a.md", "", "only one")], [[1.0, 0.0, 0.0]], collection=collection
    )

    results = retrieve(
        "query", n_results=5, client=FakeClient(), collection=collection
    )

    assert len(results) == 1


def test_retrieve_on_an_empty_collection_returns_no_results(collection):
    results = retrieve("query", client=FakeClient(), collection=collection)

    assert results == []
