# tests/cli/test_index.py
import httpx
import openai
from typer.testing import CliRunner

from socratese import config
from socratese.cli import index as index_module
from socratese.cli.main import app
from socratese.vault.models import Vault

runner = CliRunner()


def make_vault(tmp_path, name: str, notes: dict[str, str]) -> Vault:
    """Create a real .obsidian-marked vault dir with the given {filename: content} notes."""
    vault_dir = tmp_path / name
    (vault_dir / ".obsidian").mkdir(parents=True)
    for filename, content in notes.items():
        (vault_dir / filename).write_text(content)
    return Vault(name=name, path=vault_dir)


def fake_embed_chunks(chunks, client=None):
    return [[0.1, 0.2, 0.3] for _ in chunks]


def fake_add_chunks(chunks, embeddings, collection=None):
    pass  # no-op; real storage is store.py's concern, already tested there


def test_index_no_vaults_tracked(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")

    result = runner.invoke(app, ["index", "learning"])

    assert result.exit_code == 1
    assert "No vaults indexed" in result.output


def test_index_vault_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    config.save_vaults([make_vault(tmp_path, "other", {"a.md": "content"})])

    result = runner.invoke(app, ["index", "missing"])

    assert result.exit_code == 1
    assert "No vault named 'missing'" in result.output


def test_index_single_vault_success(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(index_module, "embed_chunks", fake_embed_chunks)
    monkeypatch.setattr(index_module, "add_chunks", fake_add_chunks)
    vault = make_vault(tmp_path, "learning", {"note.md": "# Heading\nSome content."})
    config.save_vaults([vault])

    result = runner.invoke(app, ["index", "learning"])

    assert result.exit_code == 0
    assert "Success" in result.output
    saved = config.load_vaults()
    assert saved[0].last_indexed is not None


def test_index_all_indexes_every_tracked_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(index_module, "embed_chunks", fake_embed_chunks)
    monkeypatch.setattr(index_module, "add_chunks", fake_add_chunks)
    vault_a = make_vault(tmp_path, "vault_a", {"a.md": "# A\nContent A"})
    vault_b = make_vault(tmp_path, "vault_b", {"b.md": "# B\nContent B"})
    config.save_vaults([vault_a, vault_b])

    result = runner.invoke(app, ["index", "all"])

    assert result.exit_code == 0
    saved = config.load_vaults()
    assert all(v.last_indexed is not None for v in saved)


def test_index_skips_invalid_vault_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    stale_dir = tmp_path / "gone"  # never created, no .obsidian
    config.save_vaults([Vault(name="gone", path=stale_dir)])

    result = runner.invoke(app, ["index", "gone"])

    assert result.exit_code == 0
    assert "is not valid, skipping" in result.output
    assert config.load_vaults()[0].last_indexed is None


def test_index_empty_vault_has_no_content(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    vault = make_vault(tmp_path, "empty", {})
    config.save_vaults([vault])

    result = runner.invoke(app, ["index", "empty"])

    assert result.exit_code == 0
    assert "has no content to index" in result.output


def test_index_api_error_stops_and_preserves_prior_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    vault_a = make_vault(tmp_path, "vault_a", {"a.md": "# A\nContent A"})
    vault_b = make_vault(tmp_path, "vault_b", {"b.md": "# B\nContent B"})
    config.save_vaults([vault_a, vault_b])

    call_count = {"n": 0}

    def embed_then_fail(chunks, client=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return fake_embed_chunks(chunks)
        request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
        raise openai.APIError("boom", request=request, body=None)

    monkeypatch.setattr(index_module, "embed_chunks", embed_then_fail)
    monkeypatch.setattr(index_module, "add_chunks", fake_add_chunks)

    result = runner.invoke(app, ["index", "all"])

    assert result.exit_code == 1
    assert "Embedding request failed" in result.output
    saved = {v.name: v for v in config.load_vaults()}
    assert saved["vault_a"].last_indexed is not None  # succeeded before the failure
    assert saved["vault_b"].last_indexed is None  # never got there
