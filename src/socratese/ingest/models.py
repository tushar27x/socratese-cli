from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Note:
    path: Path
    title: str
    frontmatter: dict[str, Any] = field(default_factory=dict[str, Any])
    wikilinks: list[str] = field(default_factory=list[str])
    content: str = ""
