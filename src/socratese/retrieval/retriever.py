"""Retrieve relevant chunks for a query, across all indexed vaults."""
from __future__ import annotations

from pathlib import Path

from socratese.embedding.embedder import embed_text
from socratese.retrieval.models import RetrievedChunk
from socratese.vectorstore.store import query as query_store


def retrieve(
    query: str,
    n_results: int = 5,
    client=None,
    collection=None,
) -> list[RetrievedChunk]:
    """Embed `query` and return the nearest stored chunks, closest first."""
    embedding = embed_text(query, client=client)
    return [
        RetrievedChunk(
            note_path=Path(hit["note_path"]),
            note_title=hit["note_title"],
            heading=hit["heading"],
            content=hit["content"],
            distance=hit["distance"],
        )
        for hit in query_store(embedding, n_results=n_results, collection=collection)
    ]
