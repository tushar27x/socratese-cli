from __future__ import annotations

import re
import os

from pathlib import Path
import frontmatter
from socratese.ingest.models import Note

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)[^\]]*\]\]")
SKIP_DIRS = {".trash", ".obsidian"}

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
    for dirpath, dirnames, filenames in os.walk(vault_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if filename.endswith(".md") and not filename.endswith(".excalidraw.md"):
                yield parse_note(Path(dirpath)/filename)
