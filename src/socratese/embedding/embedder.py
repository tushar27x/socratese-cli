from __future__ import annotations
import os
from openai import OpenAI

from socratese.chunking.models import Chunk
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

def get_client():
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")
    return OpenAI(api_key=openai_api_key)

def embed_chunks(chunks: list[Chunk], client: OpenAI | None = None) -> list[list[float]]:
    if not chunks:
        return []

    client = client or get_client()
    texts = [chunk.content for chunk in chunks]

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts
    )

    return [item.embedding for item in response.data]

