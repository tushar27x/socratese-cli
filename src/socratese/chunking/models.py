from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Chunk:
    note_path: Path
    note_title: str
    heading: str
    content: str
    frontmatter: dict[str, Any] = field(default_factory=dict[str, Any])
