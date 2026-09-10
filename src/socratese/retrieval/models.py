from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass
class RetrievedChunk:
    note_path: Path
    note_title: str
    heading: str
    content: str
    distance: float