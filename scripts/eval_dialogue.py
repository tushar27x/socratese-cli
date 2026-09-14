"""Drive scripted conversations through Session so the prompt rules can be
judged without answering by hand.

Not a test and must never live under tests/: it costs real money, hits the
network, and has no assertions — a human reads the transcript and judges it.

    python scripts/eval_dialogue.py          # every scenario
    python scripts/eval_dialogue.py 7        # only scenarios matching "7"
"""
from __future__ import annotations

import re
import sys
import time
from itertools import combinations

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
        "9 over a long session — ten unhelpful answers",
        "how does the attention mechanism work?",
        [
            "it decides what to focus on",
            "the dot product tells you relevance",
            "higher score means more important",
            "not sure",
            "you multiply Q and K",
            "then you use V somehow",
            "i think there is scaling involved",
            "something about dividing by a square root",
            "no idea what comes next",
            "it produces the output vector",
        ],
    ),
    (
        "gate — nothing in the vault covers this",
        "what is a vector database?",
        ["it stores embeddings so you can do similarity search"],
    ),
]


STOPWORDS = {
    "the", "a", "an", "what", "do", "does", "you", "your", "is", "are", "that",
    "this", "it", "to", "of", "in", "and", "for", "on", "with", "when", "how",
    "notes", "about", "at", "as", "be", "by", "from", "if", "or", "so", "but",
}


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOPWORDS}


STALL_WINDOW = 5


def report_repetition(questions: list[str]) -> None:
    """Rule 9 says never repeat a question. Two ways it can break.

    Literal repeats show up as a high-overlap pair. The more interesting
    failure is *orbiting*: the model keeps rewording the same unanswered
    question, so no pair looks alike but a run of consecutive questions all
    share the same few content words. Measured over a sliding window because
    a long session only fails this way near the end.
    """
    pairs = [
        (i + 1, j + 1, overlap)
        for (i, a), (j, b) in combinations(list(enumerate(questions)), 2)
        if (union := _content_words(a) | _content_words(b))
        and (overlap := len(_content_words(a) & _content_words(b)) / len(union)) > 0.5
    ]
    for i, j, overlap in pairs:
        print(f"  RULE 9 — Q{i} and Q{j} share {overlap:.0%} of their words")

    stalled = False
    for lo in range(len(questions) - STALL_WINDOW + 1):
        window = questions[lo : lo + STALL_WINDOW]
        shared = set.intersection(*(_content_words(q) for q in window))
        if shared:
            stalled = True
            terms = ", ".join(sorted(shared))
            print(f"  STALLED — Q{lo + 1}-Q{lo + STALL_WINDOW} all circle: {terms}")

    if not pairs and not stalled:
        print("  rule 9 ok — no repeats, no stalled run")


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
    questions = [session.opening_question()]
    print(f"\n  Q1  {questions[0]}")

    for turn, answer in enumerate(answers, start=2):
        print(f"\n  >   {answer}")
        questions.append(session.answer(answer))
        print(f"\n  Q{turn}  {questions[-1]}")

    elapsed = time.perf_counter() - started
    print(f"\n  [{len(questions)} turns, {elapsed:.1f}s]")
    report_repetition(questions)
    print()


def main(argv: list[str]) -> None:
    wanted = argv[0] if argv else None
    print(f"model: {DEFAULT_MODEL}   threshold: {RELEVANCE_THRESHOLD}\n")

    for label, topic, answers in SCENARIOS:
        if wanted is None or wanted in label:
            run(label, topic, answers)


if __name__ == "__main__":
    main(sys.argv[1:])
