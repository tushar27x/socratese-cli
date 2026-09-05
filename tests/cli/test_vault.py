from typer.testing import CliRunner

from socratese import config
from socratese.cli.vault import app as vault_app
from socratese.vault.models import Vault

runner = CliRunner()

def test_list_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    result = runner.invoke(vault_app, ["list"])
    assert result.exit_code == 0
    assert "No vaults indexed" in result.output

def test_list_shows_tracked_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    vault_dir = tmp_path / "myvault"
    (vault_dir / ".obsidian").mkdir(parents=True)
    config.save_vaults([Vault(name="myvault", path=vault_dir)])

    result = runner.invoke(vault_app, ["list"])
    assert result.exit_code == 0
    assert "myvault" in result.output


def test_add_success(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    vault_dir = tmp_path / "myvault"
    (vault_dir / ".obsidian").mkdir(parents=True)

    result = runner.invoke(vault_app, ["add", str(vault_dir)])

    assert result.exit_code == 0
    assert "Success" in result.output
    saved = config.load_vaults()
    assert len(saved) == 1
    assert saved[0].name == "myvault"
    assert saved[0].path == vault_dir


def test_add_duplicate_path_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    vault_dir = tmp_path / "myvault"
    (vault_dir / ".obsidian").mkdir(parents=True)
    config.save_vaults([Vault(name="myvault", path=vault_dir)])

    result = runner.invoke(vault_app, ["add", str(vault_dir)])

    assert result.exit_code == 1
    assert "already indexed" in result.output


def test_add_duplicate_name_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    existing = tmp_path / "existing" / "myvault"
    (existing / ".obsidian").mkdir(parents=True)
    config.save_vaults([Vault(name="myvault", path=existing)])

    other = tmp_path / "other" / "myvault"
    (other / ".obsidian").mkdir(parents=True)

    result = runner.invoke(vault_app, ["add", str(other)])

    assert result.exit_code == 1
    assert "already indexed" in result.output


def test_add_invalid_path_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    not_a_vault = tmp_path / "not_a_vault"
    not_a_vault.mkdir()

    result = runner.invoke(vault_app, ["add", str(not_a_vault)])

    assert result.exit_code == 1
    assert "not a valid Obsidian vault" in result.output


def test_remove_success(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    vault_dir = tmp_path / "myvault"
    (vault_dir / ".obsidian").mkdir(parents=True)
    config.save_vaults([Vault(name="myvault", path=vault_dir)])

    result = runner.invoke(vault_app, ["remove", "myvault"])

    assert result.exit_code == 0
    assert "removed" in result.output
    assert config.load_vaults() == []


def test_remove_nonexistent_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")

    result = runner.invoke(vault_app, ["remove", "ghost"])

    assert result.exit_code == 1
    assert "ghost" in result.output


def test_remove_only_removes_matching_name(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    keep_dir = tmp_path / "keep"
    (keep_dir / ".obsidian").mkdir(parents=True)
    gone_dir = tmp_path / "gone"
    (gone_dir / ".obsidian").mkdir(parents=True)
    config.save_vaults(
        [
            Vault(name="keep", path=keep_dir),
            Vault(name="gone", path=gone_dir),
        ]
    )

    result = runner.invoke(vault_app, ["remove", "gone"])

    assert result.exit_code == 0
    remaining = config.load_vaults()
    assert len(remaining) == 1
    assert remaining[0].name == "keep"


def test_rescan_no_change_when_all_valid(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    vault_dir = tmp_path / "myvault"
    (vault_dir / ".obsidian").mkdir(parents=True)
    config.save_vaults([Vault(name="myvault", path=vault_dir)])

    result = runner.invoke(vault_app, ["rescan"])

    assert result.exit_code == 0
    assert "All vaults are valid" in result.output
    assert config.load_vaults() == [Vault(name="myvault", path=vault_dir)]


def test_rescan_drops_stale_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    gone_dir = tmp_path / "gone"  # never created on disk
    config.save_vaults([Vault(name="gone", path=gone_dir)])

    result = runner.invoke(vault_app, ["rescan"])

    assert result.exit_code == 0
    assert "no longer valid" in result.output
    assert "1 vault(s) removed" in result.output
    assert config.load_vaults() == []


def test_rescan_keeps_valid_drops_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    keep_dir = tmp_path / "keep"
    (keep_dir / ".obsidian").mkdir(parents=True)
    gone_dir = tmp_path / "gone"
    config.save_vaults(
        [
            Vault(name="keep", path=keep_dir),
            Vault(name="gone", path=gone_dir),
        ]
    )

    result = runner.invoke(vault_app, ["rescan"])

    assert result.exit_code == 0
    remaining = config.load_vaults()
    assert len(remaining) == 1
    assert remaining[0].name == "keep"


def test_rescan_with_no_tracked_vaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")

    result = runner.invoke(vault_app, ["rescan"])

    assert result.exit_code == 0
    assert "All vaults are valid" in result.output
    assert config.load_vaults() == []