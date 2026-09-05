from datetime import datetime
from pathlib import Path

from socratese.vault.discovery import find_vaults

def test_find_vault_at_top_level(tmp_path):
    vault_dir = tmp_path / "myvault"
    (vault_dir / ".obsidian").mkdir(parents=True)
    assert find_vaults(tmp_path) == [vault_dir]

def test_find_vault_in_subdirectory(tmp_path):
    vault_dir = tmp_path / "myvault"
    (vault_dir / ".obsidian").mkdir(parents=True)
    (vault_dir / "sub").mkdir(parents=True)
    assert find_vaults(tmp_path) == [vault_dir]

def test_skips_skip_dirs(tmp_path):
    (tmp_path / "node_modules" / ".obsidian").mkdir(parents=True)
    assert find_vaults(tmp_path) == []

def test_respect_max_depth(tmp_path):
    deep = tmp_path
    for i in range(10):
        deep = deep / f"level{i}"
    (deep / ".obsidian").mkdir(parents=True)
    assert find_vaults(tmp_path, max_depth=3) == []