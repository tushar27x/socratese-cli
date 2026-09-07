from __future__ import annotations

import re

from pathlib import Path
import frontmatter
from socratese.ingest.models import Note

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)[^\]]*\]\]")

def parse_note(path: Path):
    post = frontmatter.load(path)
    wikilinks = WIKILINK_RE.findall(post.content)
    return Note(
        path=path,
        title=path.stem,
        frontmatter=dict(post.metadata),
        wikilinks=wikilinks,
        content=post.content
    )

def parse_vault(vault_path: Path):
    for md_path in vault_path.rglob("*.md"):
        yield parse_note(md_path)
