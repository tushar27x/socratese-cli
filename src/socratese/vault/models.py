from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Vault:
    name: str
    path: Path
    last_indexed: datetime | None = None
    
    def to_toml_dict(self) -> dict:
        data = {
            "name": self.name,
            "path": str(self.path),
        }
        if self.last_indexed:
            data["last_indexed"] = self.last_indexed.isoformat()
        return data

    @classmethod
    def from_toml_dict(cls, data: dict) -> "Vault":
        last_indexed = data.get("last_indexed")
        return cls(
            name = data["name"],
            path = Path(data["path"]),
            last_indexed = datetime.fromisoformat(last_indexed) if last_indexed else None,
        )