# tests/tui/test_vault_picker.py
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typing import cast

from textual.pilot import Pilot
from textual.widgets import Input, SelectionList

from socratese import config
from socratese.tui.app import SocrateseApp
from socratese.tui.vault_picker import VaultPicker
from socratese.vault.models import Vault

pytestmark = pytest.mark.asyncio


@pytest.fixture
def three_vaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    now = datetime.now(timezone.utc)
    config.save_vaults([
        Vault(name="work", path=tmp_path / "work", last_indexed=now),
        Vault(name="personal", path=tmp_path / "personal", last_indexed=now),
        Vault(name="fresh", path=tmp_path / "fresh", last_indexed=None),
    ])


async def open_picker(app: SocrateseApp, pilot: Pilot[None]) -> SelectionList[str]:
    app.query_one("#entry", Input).value = "/vaults"
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()
    assert isinstance(app.screen, VaultPicker)
    return cast(SelectionList[str], app.screen.query_one("#picker-list", SelectionList))


async def test_bare_vaults_opens_the_picker(three_vaults: None):
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await open_picker(app, pilot)

        assert isinstance(app.screen, VaultPicker)


async def test_every_tracked_vault_is_listed(three_vaults: None):
    """Un-indexed ones included: the picker is where you notice you never
    indexed something."""
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        picker = await open_picker(app, pilot)

        assert picker.option_count == 3


async def test_an_unindexed_vault_cannot_be_ticked(three_vaults: None):
    """Selecting it would scope a session to a vault with no chunks, which
    finds nothing and looks like a bug."""
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        picker = await open_picker(app, pilot)

        assert picker.get_option("fresh").disabled
        assert not picker.get_option("work").disabled


async def test_space_toggles_and_enter_confirms(three_vaults: None):
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await open_picker(app, pilot)

        await pilot.press("space")          # work
        await pilot.press("down", "space")  # personal
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, VaultPicker)
        assert sorted(app.selected_vaults) == ["personal", "work"]


async def test_escape_cancels_without_touching_the_selection(three_vaults: None):
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        app.selected_vaults = ["work"]
        await open_picker(app, pilot)

        await pilot.press("down", "space")  # tick personal, then bail
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, VaultPicker)
        assert app.selected_vaults == ["work"]


async def test_the_current_selection_is_pre_ticked(three_vaults: None):
    """Reopening the picker should show what is already chosen, not a blank
    slate that silently resets it on confirm."""
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        app.selected_vaults = ["personal"]
        picker = await open_picker(app, pilot)

        assert list(picker.selected) == ["personal"]


async def test_confirming_with_nothing_ticked_means_all_vaults(three_vaults: None):
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        app.selected_vaults = ["work"]
        await open_picker(app, pilot)

        await pilot.press("space")   # untick work
        await pilot.press("enter")
        await pilot.pause()

        assert app.selected_vaults == []
        from textual.widgets import Static

        assert "all indexed vaults" in "\n".join(
            str(w.content) for w in app.query_one("#log").query(Static)
        )


async def test_the_typed_form_still_works(three_vaults: None):
    """/vaults work personal is the shortcut for people who know the names."""
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        app.query_one("#entry", Input).value = "/vaults work personal"
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, VaultPicker)
        assert app.selected_vaults == ["work", "personal"]


async def test_no_vaults_tracked_does_not_open_an_empty_picker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    config.save_vaults([])
    app = SocrateseApp()
    async with app.run_test(size=(100, 30)) as pilot:
        app.query_one("#entry", Input).value = "/vaults"
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, VaultPicker)
