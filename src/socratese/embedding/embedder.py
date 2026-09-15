from __future__ import annotations
import os
from collections.abc import Callable

from openai import OpenAI

from socratese.chunking.models import Chunk
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

#: Chunks per embedding request. Sending a whole vault in one call works until
#: it does not — a large vault can exceed the request limit, and a failure
#: costs every chunk rather than one batch. Batching also makes real progress
#: reportable instead of a single opaque wait.
BATCH_SIZE = 128

def get_client() -> OpenAI:
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")
    return OpenAI(api_key=openai_api_key)

def embed_text(text: str, client: OpenAI | None = None) -> list[float]:
    """Embed a single free-text string (e.g. a search query)."""
    client = client or get_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text]
    )
    return response.data[0].embedding


def embed_chunks(
    chunks: list[Chunk],
    client: OpenAI | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    """Embed every chunk, in batches, preserving input order.

    `on_progress` is called with (embedded so far, total) after each batch, so
    a caller can show real progress rather than a spinner that cannot move.
    """
    if not chunks:
        return []

    client = client or get_client()
    embeddings: list[list[float]] = []

    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start : start + BATCH_SIZE]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[chunk.content for chunk in batch],
        )
        embeddings.extend(item.embedding for item in response.data)
        if on_progress:
            on_progress(len(embeddings), len(chunks))

    return embeddings

