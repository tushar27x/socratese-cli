from __future__ import annotations
from platformdirs import user_data_dir
import hashlib
import chromadb
from socratese.chunking.models import Chunk

APP_NAME = "socratese"
COLLECTION_NAME = "chunks"

def get_store_path() -> str:
    return user_data_dir(APP_NAME)

def get_collection(client: chromadb.ClientAPI | None = None) -> chromadb.api.models.Collection:
    client = client or chromadb.PersistentClient(path=get_store_path())
    return client.get_or_create_collection(name=COLLECTION_NAME)

def chunk_id(chunk: Chunk) -> str:
    key = f"{chunk.note_path}::{chunk.heading}"
    return hashlib.sha256(key.encode()).hexdigest()

def add_chunks(chunks: list[Chunk], embeddings: list[list[float]], collection = None) -> None:
    if not chunks:
        return

    collection = collection or get_collection()
    collection.upsert(
        ids=[chunk_id(c) for c in chunks],
        embeddings=embeddings,
        documents=[c.content for c in chunks],
        metadatas=[
            {"note_path": str(c.note_path), "note_title": c.note_title, "heading": c.heading}
            for c in chunks
        ],
    )

def query(embedding: list[float], n_results: int = 5, collection=None) -> list[dict]:
    collection = collection or get_collection()
    result = collection.query(query_embeddings=[embedding], n_results=n_results)

    return [
        {"content": doc, "distance": dist, **meta}
        for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])
    ]