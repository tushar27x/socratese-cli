# tests/dialogue/test_prompt.py
from pathlib import Path

from socratese.dialogue.prompt import SYSTEM_PROMPT, build_user_turn, format_chunks
from socratese.retrieval.models import RetrievedChunk


def make_chunk(
    note_title: str = "Redis Persistence",
    heading: str = "RDB Snapshots",
    content: str = "Redis forks to write a point-in-time snapshot.",
    distance: float = 0.7,
) -> RetrievedChunk:
    return RetrievedChunk(
        note_path=Path(f"notes/{note_title}.md"),
        note_title=note_title,
        heading=heading,
        content=content,
        distance=distance,
    )


def test_format_chunks_labels_an_excerpt_with_title_and_heading():
    result = format_chunks([make_chunk(note_title="Redis", heading="RDB")])

    assert '<excerpt source="Redis — RDB">' in result


def test_format_chunks_omits_the_separator_when_the_chunk_has_no_heading():
    """A heading-less chunk (content before the first `#`) must not render a
    dangling em dash — the label is the note title alone."""
    result = format_chunks([make_chunk(note_title="Redis", heading="")])

    assert '<excerpt source="Redis">' in result
    assert "—" not in result


def test_format_chunks_preserves_content_verbatim():
    """Chunk content is raw markdown, including its own `#` headings. The
    excerpt wrapper must not strip, reflow, or re-indent it."""
    body = "## Inner heading\n\n- a bullet\n- another\n\n    indented code"
    result = format_chunks([make_chunk(content=body)])

    assert body in result


def test_format_chunks_separates_excerpts_with_a_blank_line():
    result = format_chunks(
        [make_chunk(note_title="A", content="alpha"), make_chunk(note_title="B", content="beta")]
    )

    assert "</excerpt>\n\n<excerpt" in result
    assert result.count("<excerpt") == 2


def test_format_chunks_of_an_empty_list_is_an_empty_string():
    assert format_chunks([]) == ""


def test_build_user_turn_includes_the_topic_and_the_excerpts():
    result = build_user_turn("how does redis persist data?", [make_chunk(content="alpha")])

    assert "Topic: how does redis persist data?" in result
    assert "alpha" in result


def test_build_user_turn_puts_the_topic_before_the_excerpts():
    """Ordering matters for prompt caching later: stable content first, the
    volatile per-query half after. Pin it so a refactor cannot silently swap them."""
    result = build_user_turn("a topic", [make_chunk()])

    assert result.index("Topic:") < result.index("<excerpt")


def test_system_prompt_carries_the_load_bearing_rules():
    """These four are the failure modes the prompt exists to prevent. Losing one
    to an edit would degrade output quality with no test failure anywhere else."""
    assert "exactly one question" in SYSTEM_PROMPT
    assert "Never state the answer" in SYSTEM_PROMPT
    assert "BAD:" in SYSTEM_PROMPT and "GOOD:" in SYSTEM_PROMPT
    assert "Never answer" in SYSTEM_PROMPT
