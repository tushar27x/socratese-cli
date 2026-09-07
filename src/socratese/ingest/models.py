from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Note:
    path: Path
    title: str
    frontmatter: dict = field(default_factory=dict)
    wikilinks: list[str] = field(default_factory=list)
    content: str = ""
