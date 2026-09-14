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
from itertools import combinations

from dotenv import load_dotenv

load_dotenv()

from socratese.dialogue.socratic import (  # noqa: E402
    DEFAULT_MODEL,
    RELEVANCE_THRESHOLD,
    Session,
)
from socratese.dialogue.stall import (  # noqa: E402
    content_words,
    is_stalled,
    orbiting_terms,
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
        "3 and 8 — the notes do not contain the answer",
        "how does react.js make use of the virtual DOM?",
        [
            # a real transcript: the notes describe what the virtual DOM is for
            # but never mention diffing two virtual trees, so no answer the user
            # gives can satisfy a question driving at reconciliation
            "It compares changes with the real DOM and only apply changes to the "
            "components where changes are present rather than re-rendering the whole page",
            "for monitoring changes in the specific changes in the DOM tree. it only "
            "updates the components (nodes) which need updating",
            "I don't know.",
            "the change would appear in the virtual DOM first",
            "since virtual DOM is a copy of the original DOM, it can monitor what "
            "changed in the virtual dom and only render the required change",
        ],
    ),
    (
        "gate — nothing in the vault covers this",
        "what is a vector database?",
        ["it stores embeddings so you can do similarity search"],
    ),
]


def report_repetition(questions: list[str], topic: str) -> None:
    """Rule 9 says never repeat a question. Two ways it can break.

    Literal repeats show up as a high-overlap pair. The more interesting
    failure is *orbiting* — the model rewording one unanswered question so no
    pair looks alike. That detection now lives in the app (dialogue/stall.py),
    since the CLI warns the user about it live; this only reports it.
    """
    pairs = [
        (i + 1, j + 1, overlap)
        for (i, a), (j, b) in combinations(list(enumerate(questions)), 2)
        if (union := content_words(a) | content_words(b))
        and (overlap := len(content_words(a) & content_words(b)) / len(union)) > 0.5
    ]
    for i, j, overlap in pairs:
        print(f"  RULE 9 — Q{i} and Q{j} share {overlap:.0%} of their words")

    stalled_at = next(
        (n for n in range(1, len(questions) + 1) if is_stalled(questions[:n], topic)), None
    )
    if stalled_at:
        terms = ", ".join(sorted(orbiting_terms(questions[:stalled_at], topic)))
        print(f"  STALLED from Q{stalled_at} — circling: {terms}")
    elif not pairs:
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
    report_repetition(questions, topic)
    print()


def main(argv: list[str]) -> None:
    wanted = argv[0] if argv else None
    print(f"model: {DEFAULT_MODEL}   threshold: {RELEVANCE_THRESHOLD}\n")

    for label, topic, answers in SCENARIOS:
        if wanted is None or wanted in label:
            run(label, topic, answers)


if __name__ == "__main__":
    main(sys.argv[1:])
