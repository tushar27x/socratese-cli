from __future__ import annotations
from platformdirs import user_data_dir
import hashlib
from typing import Any, cast
import chromadb
from chromadb.api import ClientAPI
from chromadb.api.types import PyEmbedding, Where
from chromadb.api.models.Collection import Collection
from socratese.chunking.models import Chunk

APP_NAME = "socratese"
COLLECTION_NAME = "chunks"

def get_store_path() -> str:
    return user_data_dir(APP_NAME)

def get_collection(client: ClientAPI | None = None) -> Collection:
    client = client or chromadb.PersistentClient(path=get_store_path())
    return client.get_or_create_collection(name=COLLECTION_NAME)

def chunk_id(chunk: Chunk) -> str:
    key = f"{chunk.note_path}::{chunk.heading}"
    return hashlib.sha256(key.encode()).hexdigest()

def add_chunks(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    vault: str,
    collection: Collection | None = None,
) -> None:
    """Store chunks, tagged with the vault they came from.

    `vault` is a parameter rather than a field on Chunk: which vault a note
    lives in is a storage concern, not part of the note's content, and the
    chunker has no idea about vaults.
    """
    if not chunks:
        return

    collection = collection or get_collection()
    collection.upsert(
        ids=[chunk_id(c) for c in chunks],
        # list is invariant, so list[list[float]] is not a list[PyEmbedding]
        # even though every element satisfies it. Not a real mismatch.
        embeddings=cast(list[PyEmbedding], embeddings),
        documents=[c.content for c in chunks],
        metadatas=[
            {
                "note_path": str(c.note_path),
                "note_title": c.note_title,
                "heading": c.heading,
                "vault": vault,
            }
            for c in chunks
        ],
    )

def query(
    embedding: list[float],
    n_results: int = 5,
    vaults: list[str] | None = None,
    collection: Collection | None = None,
) -> list[dict[str, Any]]:
    """Nearest chunks to `embedding`, optionally restricted to named vaults.

    Filtering happens inside Chroma rather than after the fact, so asking for
    five results from one vault returns five, not however many of a global five
    happened to come from it.
    """
    collection = collection or get_collection()
    where: Where | None = {"vault": {"$in": list(vaults)}} if vaults else None
    result = collection.query(query_embeddings=[embedding], n_results=n_results, where=where)

    # Chroma types these as Optional because `include` can omit them; all three
    # are in the default include, so they are always present here.
    documents, metadatas, distances = result["documents"], result["metadatas"], result["distances"]
    assert documents is not None and metadatas is not None and distances is not None

    return [
        {"content": doc, "distance": dist, **meta}
        for doc, meta, dist in zip(documents[0], metadatas[0], distances[0])
    ]
