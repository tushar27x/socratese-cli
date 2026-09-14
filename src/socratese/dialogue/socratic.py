import os
from anthropic import Anthropic
from anthropic.types import MessageParam

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
) -> str | None:
    relevant = [c for c in chunks if c.distance <= RELEVANCE_THRESHOLD]

    if not relevant:
        return None

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

class Session:
    """A running conversation about one topic, grounded in one set of chunks.

    Chunks are filtered once, at construction. The grounding stays fixed for
    the life of the session so follow-ups keep referring to the same notes
    instead of drifting toward whatever the last answer happened to mention.
    """

    def __init__(self, topic: str, chunks: list[RetrievedChunk], client: Anthropic | None = None) -> None:
        self.topic = topic
        self.chunks = [c for c in chunks if c.distance <= RELEVANCE_THRESHOLD]
        self._client = client
        self.messages: list[MessageParam] = []

    @property
    def client(self) -> Anthropic:
        if self._client is None:
            self._client = get_client()

        return self._client
    @property
    def has_grounding(self) -> bool:
        return bool(self.chunks)

    def opening_question(self) -> str:
        self.messages.append(
            {"role": "user", "content": build_user_turn(self.topic, self.chunks)}
        )

        return self._next_turn()

    def answer(self, response:str) -> str:
        """Submit the user's answer, get the follow-up question."""
        self.messages.append({"role": "user", "content": response})
        return self._next_turn()

    
    def _next_turn(self) -> str:
        res = self.client.messages.create(
            model=os.environ.get("DIALOGUE_MODEL", DEFAULT_MODEL),
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=self.messages
        )

        text: str = "".join(b.text for b in res.content if b.type == "text").strip()
        self.messages.append({"role": "assistant", "content": text})
        return text
    