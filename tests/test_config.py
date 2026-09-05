from pathlib import Path

import socratese.config as config
from socratese.vault.models import Vault


def test_load_vaults_returns_empty_list_when_no_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    assert config.load_vaults() == []


def test_save_then_load_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    vaults = [Vault(name="test", path=Path("/tmp/foo"))]
    config.save_vaults(vaults)
    assert config.load_vaults() == vaults