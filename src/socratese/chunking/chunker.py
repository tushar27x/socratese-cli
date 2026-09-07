from __future__ import annotations

import re

from socratese.chunking.models import Chunk
from socratese.ingest.models import Note

HEADING_RE = re.compile(r"^(#+)\s+(.*)$", re.MULTILINE)

def chunk_note(note: Note) -> list[Chunk]:
    matches = list(HEADING_RE.finditer(note.content))

    if not matches:
        return [_make_chunk(note, heading="", body=note.content)]

    chunks = []

    preamble = note.content[:matches[0].start()].strip()
    if preamble:
        chunks.append(_make_chunk(note, heading="", body=preamble))
    for i, match in enumerate(matches):
        heading = match.group(2)
        section_start = match.end()
        section_end = matches[i+1].start() if i+1 < len(matches) else len(note.content)

        body = note.content[section_start:section_end].strip()
        if body:
            chunks.append(_make_chunk(note, heading=heading, body=body))

    return chunks

def _make_chunk(note: Note, heading: str, body: str) -> Chunk:
    return Chunk(
        note_path = note.path,
        note_title = note.title,
        heading = heading,
        content = body,
        frontmatter = dict(note.frontmatter)
    )

def chunk_notes(notes: list[Note]) -> list[Chunk]:
    chunks = []
    for note in notes:
        chunks.extend(chunk_note(note))

    return chunks