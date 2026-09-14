"""Retrieve relevant chunks for a query, across all indexed vaults."""
from __future__ import annotations

from pathlib import Path

from chromadb.api.models.Collection import Collection
from openai import OpenAI

from socratese.embedding.embedder import embed_text
from socratese.retrieval.models import RetrievedChunk
from socratese.vectorstore.store import query as query_store


def retrieve(
    query: str,
    n_results: int = 5,
    vaults: list[str] | None = None,
    client: OpenAI | None = None,
    collection: Collection | None = None,
) -> list[RetrievedChunk]:
    """Embed `query` and return the nearest stored chunks, closest first.

    `vaults` restricts the search by vault name; None searches all of them.
    """
    embedding = embed_text(query, client=client)
    return [
        RetrievedChunk(
            note_path=Path(hit["note_path"]),
            note_title=hit["note_title"],
            heading=hit["heading"],
            content=hit["content"],
            distance=hit["distance"],
            # chunks indexed before vaults were recorded have no vault field
            vault=hit.get("vault", ""),
        )
        for hit in query_store(
            embedding, n_results=n_results, vaults=vaults, collection=collection
        )
    ]
