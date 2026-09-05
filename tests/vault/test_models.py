from datetime import datetime
from pathlib import Path

from socratese.vault.models import Vault

def test_to_toml_dict_omits_last_indexed_when_none():
    vault = Vault(name="Test Vault", path=Path("/tmp/foo"))
    assert vault.to_toml_dict() == {"name": "Test Vault", "path": "/tmp/foo"}

def test_to_toml_dict_includes_last_indexed_when_present():
    when = datetime(2024, 1, 1, 12, 0, 0)
    vault = Vault(name="Test Vault", path=Path("/tmp/foo"), last_indexed=when)
    assert vault.to_toml_dict()["last_indexed"] == when.isoformat()
    
def test_from_toml_dict_round_trips():
    original = Vault(name="test", path=Path("/tmp/foo"))
    rebuilt = Vault.from_toml_dict(original.to_toml_dict())
    assert rebuilt == original