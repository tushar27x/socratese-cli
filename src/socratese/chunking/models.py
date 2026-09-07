from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Chunk:
    note_path: Path
    note_title: str
    heading: str
    content: str
    frontmatter: dict = field(default_factory=dict)
