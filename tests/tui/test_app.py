# tests/tui/test_app.py
from datetime import datetime, timezone
from pathlib import Path

import pytest
from textual.widgets import Input, RichLog

from socratese import config, tutor
from socratese.retrieval.models import RetrievedChunk
from socratese.tui.app import SocrateseApp
from socratese.vault.models import Vault

pytestmark = pytest.mark.asyncio


def make_chunk(distance: float = 0.7) -> RetrievedChunk:
    return RetrievedChunk(
        note_path=Path("/vault/Redis.md"),
        note_title="Redis Persistence",
        heading="RDB",
        content="Redis forks to snapshot.",
        distance=distance,
        vault="work",
    )


class FakeSession:
    def __init__(self, topic: str, chunks: list[RetrievedChunk], client: object = None) -> None:
        self.topic = topic
        self.chunks = [c for c in chunks if c.distance <= 1.2]
        self.messages: list[dict[str, str]] = []
        self.replies: list[str] = []

    @property
    def has_grounding(self) -> bool:
        return bool(self.chunks)

    def opening_question(self) -> str:
        return "Q1?"

    def answer(self, response: str) -> str:
        self.replies.append(response)
        return f"Q{len(self.replies) + 1}?"


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(config, "get_config_path", lambda: tmp_path / "config.toml")
    config.save_vaults([
        Vault(name="work", path=tmp_path / "work", last_indexed=datetime.now(timezone.utc)),
        Vault(name="fresh", path=tmp_path / "fresh", last_indexed=None),
    ])

    def fake_retrieve(
        query: str, n_results: int = 5, vaults: list[str] | None = None
    ) -> list[RetrievedChunk]:
        return [make_chunk()]

    monkeypatch.setattr(tutor, "retrieve", fake_retrieve)
    monkeypatch.setattr(tutor, "Session", FakeSession)
    monkeypatch.setattr("socratese.history.store.get_db_path", lambda: tmp_path / "sessions.db")
    return tmp_path


def written(app: SocrateseApp) -> str:
    """Everything the conversation pane has shown, as plain text."""
    log = app.query_one("#log", RichLog)
    return "\n".join(str(line) for line in log.lines)


async def submit(pilot: object, app: SocrateseApp, text: str) -> None:
    app.query_one("#entry", Input).value = text
    await pilot.press("enter")  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]


async def test_it_opens_showing_the_banner_and_vaults(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        assert "Socratese" in written(pilot.app)  # type: ignore[arg-type]
        assert "work" in written(pilot.app)  # type: ignore[arg-type]


async def test_help_lists_every_command(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/help")  # type: ignore[arg-type]

        for name in ("/ask", "/resume", "/vaults", "/index", "/quit"):
            assert name in written(app)  # type: ignore[arg-type]


async def test_an_unknown_command_suggests_a_real_one(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/resum")  # type: ignore[arg-type]

        assert "/resume" in written(app)  # type: ignore[arg-type]


async def test_ask_starts_a_session_and_shows_the_question(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/ask redis persistence")  # type: ignore[arg-type]
        await pilot.pause()

        assert "Q1?" in written(app)  # type: ignore[arg-type]
        assert app.session is not None  # type: ignore[attr-defined]


async def test_plain_text_answers_the_current_question(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/ask redis")  # type: ignore[arg-type]
        await pilot.pause()

        await submit(pilot, app, "the parent keeps serving")  # type: ignore[arg-type]
        await pilot.pause()

        assert "Q2?" in written(app)  # type: ignore[arg-type]


async def test_answering_with_no_session_says_so(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "an answer to nothing")  # type: ignore[arg-type]
        await pilot.pause()

        assert "No session running" in written(app)  # type: ignore[arg-type]


async def test_ask_without_a_topic_is_refused(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/ask")  # type: ignore[arg-type]

        assert "Give me a topic" in written(app)  # type: ignore[arg-type]


async def test_vaults_can_be_narrowed_for_the_next_session(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/vaults work")  # type: ignore[arg-type]

        assert app.selected_vaults == ["work"]  # type: ignore[attr-defined]


async def test_an_unindexed_vault_cannot_be_selected(wired: Path):
    """Selecting it would scope a session to a vault with no chunks."""
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/vaults fresh")  # type: ignore[arg-type]

        assert "Not indexed" in written(app)  # type: ignore[arg-type]
        assert app.selected_vaults == []  # type: ignore[attr-defined]


async def test_end_closes_the_session_without_quitting(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/ask redis")  # type: ignore[arg-type]
        await pilot.pause()

        await submit(pilot, app, "/end")  # type: ignore[arg-type]

        assert app.session is None  # type: ignore[attr-defined]
        assert app.is_running


async def test_a_second_ask_while_running_is_refused(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/ask redis")  # type: ignore[arg-type]
        await pilot.pause()

        await submit(pilot, app, "/ask something else")  # type: ignore[arg-type]

        assert "already running" in written(app)  # type: ignore[arg-type]


async def test_sources_are_shown_only_on_request(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/ask redis")  # type: ignore[arg-type]
        await pilot.pause()
        assert "Redis Persistence" not in written(app)  # type: ignore[arg-type]

        await submit(pilot, app, "/sources")  # type: ignore[arg-type]

        assert "Redis Persistence" in written(app)  # type: ignore[arg-type]


async def test_the_input_is_cleared_after_submitting(wired: Path):
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app
        await submit(pilot, app, "/help")  # type: ignore[arg-type]

        assert app.query_one("#entry", Input).value == ""


async def test_the_input_is_never_clipped_at_any_terminal_size(wired: Path):
    """The input's round border needs three rows. A docked Footer competing
    for them silently cut off the bottom edge."""
    for size in [(100, 24), (80, 15), (60, 10)]:
        async with SocrateseApp().run_test(size=size) as pilot:
            app = pilot.app
            entry = app.query_one("#entry")
            log = app.query_one("#log")

            assert entry.region.height == 3
            assert entry.region.y + entry.region.height <= size[1]
            assert log.region.y + log.region.height <= entry.region.y


async def test_the_terminal_background_shows_through(wired: Path):
    """A solid fill would paint over the user's terminal background and any
    wallpaper behind it."""
    async with SocrateseApp().run_test() as pilot:
        app = pilot.app

        assert app.screen.styles.background.a == 0
        assert app.query_one("#log").styles.background.a == 0
        assert app.query_one("#entry").styles.background.a == 0


async def test_it_uses_the_terminals_own_ansi_palette(wired: Path):
    """So the app inherits whatever theme the user has, rather than imposing
    Textual's."""
    async with SocrateseApp().run_test() as pilot:
        assert pilot.app.ansi_color is True
