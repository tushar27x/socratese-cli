# tests/ingest/test_parser.py
from pathlib import Path

from socratese.ingest.parser import parse_note, parse_vault


def write_note(dir_: Path, name: str, content: str) -> Path:
    path = dir_ / name
    path.write_text(content)
    return path


def test_parse_note_with_frontmatter_and_wikilinks(tmp_path):
    note_path = write_note(
        tmp_path,
        "test.md",
        """---
tags: [python, learning]
---
See [[Other Note]] and [[Other Note|Display Text]] and [[Heading Note#Section]].
""",
    )

    note = parse_note(note_path)

    assert note.title == "test"
    assert note.frontmatter == {"tags": ["python", "learning"]}
    assert note.wikilinks == ["Other Note", "Other Note", "Heading Note"]
    assert "See [[Other Note]]" in note.content


def test_parse_note_with_no_frontmatter(tmp_path):
    note_path = write_note(tmp_path, "plain.md", "Just a plain note, no links.\n")

    note = parse_note(note_path)

    assert note.title == "plain"
    assert note.frontmatter == {}
    assert note.wikilinks == []
    assert note.content.strip() == "Just a plain note, no links."


def test_parse_note_with_empty_file(tmp_path):
    note_path = write_note(tmp_path, "empty.md", "")

    note = parse_note(note_path)

    assert note.frontmatter == {}
    assert note.wikilinks == []
    assert note.content == ""


def test_parse_vault_finds_all_markdown_files(tmp_path):
    write_note(tmp_path, "a.md", "Note A")
    sub = tmp_path / "subdir"
    sub.mkdir()
    write_note(sub, "b.md", "Note B, links to [[a]].")
    write_note(tmp_path, "not_markdown.txt", "ignore me")

    notes = list(parse_vault(tmp_path))

    titles = {n.title for n in notes}
    assert titles == {"a", "b"}


def test_parse_vault_empty_directory(tmp_path):
    notes = list(parse_vault(tmp_path))
    assert notes == []
