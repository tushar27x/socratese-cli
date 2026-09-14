"""Drive scripted conversations through Session so the prompt rules can be
judged without answering by hand.

Not a test and must never live under tests/: it costs real money, hits the
network, and has no assertions — a human reads the transcript and judges it.

    python scripts/eval_dialogue.py          # every scenario
    python scripts/eval_dialogue.py 7        # only scenarios matching "7"
"""
from __future__ import annotations

import sys
import time

from dotenv import load_dotenv

load_dotenv()

from socratese.dialogue.socratic import (  # noqa: E402
    DEFAULT_MODEL,
    RELEVANCE_THRESHOLD,
    Session,
)
from socratese.retrieval.retriever import retrieve  # noqa: E402

# (rule under test, topic, scripted answers)
SCENARIOS: list[tuple[str, str, list[str]]] = [
    (
        "7 — answer contradicts the notes",
        "how does redis persist data to disk?",
        [
            "RDB appends every write command to the file as it happens, so the "
            "snapshot file is always completely up to date."
        ],
    ),
    (
        "8 — surrender",
        "how does the attention mechanism work?",
        ["no idea"],
    ),
    (
        "6 and 9 — partial answers over several turns",
        "how does the attention mechanism work?",
        [
            "the dot product decides which value matters more",
            "higher dot product means the token is more relevant",
            "you normalise them somehow",
        ],
    ),
    (
        "3 — should stay inside the excerpts",
        "how does mongodb store data?",
        ["it stores documents as BSON in collections"],
    ),
    (
        "gate — nothing in the vault covers this",
        "what is a vector database?",
        ["it stores embeddings so you can do similarity search"],
    ),
]


def run(label: str, topic: str, answers: list[str]) -> None:
    print("=" * 78)
    print(f"RULE   {label}")
    print(f"TOPIC  {topic}\n")

    chunks = retrieve(topic)
    for chunk in chunks:
        gate = "PASS" if chunk.distance <= RELEVANCE_THRESHOLD else "drop"
        heading = chunk.heading or "(no heading)"
        print(f"  {gate}  {chunk.distance:.3f}  {chunk.note_title} — {heading}")

    session = Session(topic, chunks)
    if not session.has_grounding:
        print("\n  -> nothing passed the relevance gate; no session started\n")
        return

    started = time.perf_counter()
    print(f"\n  Q1  {session.opening_question()}")

    for turn, answer in enumerate(answers, start=2):
        print(f"\n  >   {answer}")
        print(f"\n  Q{turn}  {session.answer(answer)}")

    elapsed = time.perf_counter() - started
    print(f"\n  [{len(answers) + 1} turns, {elapsed:.1f}s]\n")


def main(argv: list[str]) -> None:
    wanted = argv[0] if argv else None
    print(f"model: {DEFAULT_MODEL}   threshold: {RELEVANCE_THRESHOLD}\n")

    for label, topic, answers in SCENARIOS:
        if wanted is None or wanted in label:
            run(label, topic, answers)


if __name__ == "__main__":
    main(sys.argv[1:])
