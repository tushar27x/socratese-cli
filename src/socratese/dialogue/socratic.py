import os
from anthropic import Anthropic

from socratese.retrieval.models import RetrievedChunk
from socratese.dialogue.prompt import build_user_turn, SYSTEM_PROMPT

RELEVANCE_THRESHOLD = 1.2
DEFAULT_MODEL = "claude-haiku-4-5"

def get_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY enviornment variable not found.")

    return Anthropic(api_key=api_key)

def ask_questions(
        topic: str,
        chunks: list[RetrievedChunk],
        client: Anthropic | None=None
) -> str:
    relevant = [c for c in chunks if c.distance <= RELEVANCE_THRESHOLD]

    if not relevant:
        return "No relevant notes found."

    client = client or get_client()
    res = client.messages.create(
        model = os.environ.get("DIALOGUE_MODEL", DEFAULT_MODEL),
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_turn(topic, relevant)}]
    )
    return "".join(
        block.text for block in res.content if block.type=="text"
    ).strip()

