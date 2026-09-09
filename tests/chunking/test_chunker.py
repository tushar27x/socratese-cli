# tests/chunking/test_chunker.py
from pathlib import Path

from socratese.chunking.chunker import chunk_note, chunk_notes
from socratese.ingest.models import Note


def make_note(content: str, frontmatter: dict | None = None) -> Note:
    return Note(
        path=Path("fake/note.md"),
        title="note",
        frontmatter=frontmatter or {},
        wikilinks=[],
        content=content,
    )


def test_chunk_note_with_no_headings_is_one_chunk():
    note = make_note("Just some plain content, no headings at all.")

    chunks = chunk_note(note)

    assert len(chunks) == 1
    assert chunks[0].heading == ""
    assert chunks[0].content == "Just some plain content, no headings at all."
    assert chunks[0].note_title == "note"


def test_chunk_note_splits_by_heading():
    note = make_note(
        "# First Section\n"
        "Content for the first section.\n"
        "## Second Section\n"
        "Content for the second section.\n"
    )

    chunks = chunk_note(note)

    assert len(chunks) == 2
    assert chunks[0].heading == "First Section"
    assert chunks[0].content == "Content for the first section."
    assert chunks[1].heading == "Second Section"
    assert chunks[1].content == "Content for the second section."


def test_chunk_note_keeps_preamble_before_first_heading():
    note = make_note(
        "Some intro text before any heading.\n"
        "# First Section\n"
        "Section content.\n"
    )

    chunks = chunk_note(note)

    assert len(chunks) == 2
    assert chunks[0].heading == ""
    assert chunks[0].content == "Some intro text before any heading."
    assert chunks[1].heading == "First Section"
    assert chunks[1].content == "Section content."


def test_chunk_note_skips_empty_sections():
    note = make_note(
        "# Empty Section\n"
        "# Section With Content\n"
        "Actual content here.\n"
    )

    chunks = chunk_note(note)

    # The empty section between the two headings should produce no chunk.
    assert len(chunks) == 1
    assert chunks[0].heading == "Section With Content"


def test_chunk_note_carries_frontmatter_onto_every_chunk():
    note = make_note(
        "# Section\nSome content.\n",
        frontmatter={"tags": ["python"]},
    )

    chunks = chunk_note(note)

    assert chunks[0].frontmatter == {"tags": ["python"]}


def test_chunk_note_empty_note_produces_no_chunks():
    note = make_note("")

    chunks = chunk_note(note)

    assert chunks == []

def test_chunk_note_whitespace_only_content_produces_no_chunks():
    note = make_note("   \n\n   ")
    chunks = chunk_note(note)
    assert chunks == []

def test_chunk_notes_flattens_across_multiple_notes():
    note_a = make_note("# A1\nContent A1")
    note_b = make_note("# B1\nContent B1\n# B2\nContent B2")

    chunks = chunk_notes([note_a, note_b])

    assert len(chunks) == 3
    assert [c.heading for c in chunks] == ["A1", "B1", "B2"]
