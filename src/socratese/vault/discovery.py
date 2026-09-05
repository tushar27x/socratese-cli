import os
from pathlib import Path
from socratese.vault.models import Vault

SKIP_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".cache",
    ".idea",
}

VAULT_MARKER = '.obsidian'
MAX_DEPTH = 6

def _ignore_scan_error(error: OSError) -> None:
    pass

def find_vaults(root: Path, max_depth: int = MAX_DEPTH) -> list[Path]:
    root = Path(root)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=_ignore_scan_error):
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth > max_depth:
            dirnames[:] = []
            continue
        if VAULT_MARKER in dirnames:
            found.append(Path(dirpath))
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

    return found