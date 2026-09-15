"""A modal for choosing which vaults the next session searches.

`/vaults work personal` typed at the prompt does the same thing; this is for
when you cannot remember the names, or want to see what is indexed first.
"""
from __future__ import annotations

from typing import cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, SelectionList, Static
from textual.widgets.selection_list import Selection

from socratese.vault.models import Vault


class VaultPicker(ModalScreen[list[str] | None]):
    """Dismisses with the chosen names, an empty list for "all", or None on cancel.

    Un-indexed vaults are listed but cannot be ticked: selecting one would scope
    a session to a vault with no chunks, which finds nothing and looks like a
    bug. Listing them at all is deliberate — it is the natural place to notice
    "oh, I never indexed that one".
    """

    DEFAULT_CSS = """
    VaultPicker {
        align: center middle;
        background: transparent;
    }
    #picker {
        width: 64;
        height: auto;
        max-height: 80%;
        border: round ansi_blue;
        padding: 1 2;
        background: ansi_default;
    }
    #picker-title { text-style: bold; margin-bottom: 1; }
    #picker-hint  { color: ansi_bright_black; margin-top: 1; }
    #picker-list  { height: auto; max-height: 12; background: transparent; }
    #picker-buttons { height: 3; margin-top: 1; align-horizontal: right; }
    #picker-buttons Button { margin-left: 1; min-width: 10; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Use selected", priority=True),
    ]

    def __init__(self, vaults: list[Vault], selected: list[str]) -> None:
        super().__init__()
        self._vaults = vaults
        self._selected = set(selected)

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static("Which vaults should sessions search?", id="picker-title")
            yield SelectionList[str](
                *(self._selection(v) for v in self._vaults), id="picker-list"
            )
            yield Static(
                "space toggles · enter confirms · nothing ticked means all indexed vaults",
                id="picker-hint",
            )
            with Horizontal(id="picker-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Use selected", id="confirm", variant="primary")

    def _selection(self, vault: Vault) -> Selection[str]:
        indexed = vault.last_indexed is not None
        state = f"indexed {vault.last_indexed:%Y-%m-%d}" if indexed else "never indexed"
        return Selection(
            f"{vault.name}  [dim]{state}[/dim]",
            vault.name,
            initial_state=vault.name in self._selected,
            id=vault.name,
            disabled=not indexed,
        )

    def on_mount(self) -> None:
        self.query_one("#picker-list", SelectionList).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        # query_one does an isinstance check, and a subscripted generic
        # (SelectionList[str]) raises TypeError there at runtime even though
        # pyright accepts it. Unsubscripted lookup, then narrow the values.
        picker = cast(SelectionList[str], self.query_one("#picker-list", SelectionList))
        self.dismiss(list(picker.selected))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.action_confirm()
        else:
            self.action_cancel()
