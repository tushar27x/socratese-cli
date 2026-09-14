# tests/tui/test_app.py
from datetime import datetime, timezone
from pathlib import Path

import pytest
from textual.containers import VerticalScroll
from textual.pilot import Pilot
from textual.widgets import Input, ProgressBar, Static

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
    """Everything the conversation pane has shown, as plain text.

    Strip.text, not str(strip): the repr is a list of Segments, so a phrase
    spanning two styles never appears literally and assertions pass vacuously.
    """
    log = app.query_one("#log", VerticalScroll)
    return "\n".join(str(w.content) for w in log.query(Static))


async def submit(pilot: Pilot[None], app: SocrateseApp, text: str) -> None:
    app.query_one("#entry", Input).value = text
    await pilot.press("enter")
    await pilot.pause()


async def test_it_opens_showing_the_banner_and_vaults(wired: Path):
    app = SocrateseApp()
    async with app.run_test():
        assert "Socratese" in written(app)
        assert "work" in written(app)


async def test_help_lists_every_command(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/help")

        for name in ("/ask", "/resume", "/vaults", "/index", "/quit"):
            assert name in written(app)


async def test_an_unknown_command_suggests_a_real_one(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/resum")

        assert "/resume" in written(app)


async def test_ask_starts_a_session_and_shows_the_question(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/ask redis persistence")
        await pilot.pause()

        assert "Q1?" in written(app)
        assert app.session is not None  # type: ignore[attr-defined]


async def test_plain_text_answers_the_current_question(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/ask redis")
        await pilot.pause()

        await submit(pilot, app, "the parent keeps serving")
        await pilot.pause()

        assert "Q2?" in written(app)


async def test_answering_with_no_session_says_so(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "an answer to nothing")
        await pilot.pause()

        assert "No session running" in written(app)


async def test_ask_without_a_topic_is_refused(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/ask")

        assert "Give me a topic" in written(app)


async def test_vaults_can_be_narrowed_for_the_next_session(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/vaults work")

        assert app.selected_vaults == ["work"]  # type: ignore[attr-defined]


async def test_an_unindexed_vault_cannot_be_selected(wired: Path):
    """Selecting it would scope a session to a vault with no chunks."""
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/vaults fresh")

        assert "Not indexed" in written(app)
        assert app.selected_vaults == []  # type: ignore[attr-defined]


async def test_end_closes_the_session_without_quitting(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/ask redis")
        await pilot.pause()

        await submit(pilot, app, "/end")

        assert app.session is None  # type: ignore[attr-defined]
        assert app.is_running


async def test_a_second_ask_while_running_is_refused(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/ask redis")
        await pilot.pause()

        await submit(pilot, app, "/ask something else")

        assert "already running" in written(app)


async def test_sources_are_shown_only_on_request(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/ask redis")
        await pilot.pause()
        assert "Redis Persistence" not in written(app)

        await submit(pilot, app, "/sources")

        assert "Redis Persistence" in written(app)


async def test_the_input_is_cleared_after_submitting(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/help")

        assert app.query_one("#entry", Input).value == ""


async def test_the_input_is_never_clipped_at_any_terminal_size(wired: Path):
    """The input's round border needs three rows. A docked Footer competing
    for them silently cut off the bottom edge."""
    for size in [(100, 24), (80, 15), (60, 10)]:
        app = SocrateseApp()
        async with app.run_test(size=size):
            entry = app.query_one("#entry")
            log = app.query_one("#log")

            assert entry.region.height == 3
            assert entry.region.y + entry.region.height <= size[1]
            assert log.region.y + log.region.height <= entry.region.y


async def test_the_terminal_background_shows_through(wired: Path):
    """A solid fill would paint over the user's terminal background and any
    wallpaper behind it."""
    app = SocrateseApp()
    async with app.run_test():

        assert app.screen.styles.background.a == 0
        assert app.query_one("#log").styles.background.a == 0
        assert app.query_one("#entry").styles.background.a == 0


async def test_it_uses_the_terminals_own_ansi_palette(wired: Path):
    """So the app inherits whatever theme the user has, rather than imposing
    Textual's."""
    app = SocrateseApp()
    async with app.run_test():
        assert app.ansi_color is True


async def test_an_answer_is_echoed_into_the_transcript(wired: Path):
    """Without the echo the pane shows only questions, which reads as a list
    of demands rather than a conversation."""
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/ask redis")
        await pilot.pause()

        await submit(pilot, app, "the parent keeps serving writes")
        await pilot.pause()

        transcript = written(app)
        assert "the parent keeps serving writes" in transcript
        assert transcript.index("Q1?") < transcript.index("the parent keeps serving writes")


async def test_the_echo_comes_before_the_next_question(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/ask redis")
        await pilot.pause()
        await submit(pilot, app, "my answer")
        await pilot.pause()

        transcript = written(app)
        assert transcript.index("my answer") < transcript.index("Q2?")


async def test_commands_are_not_echoed_as_answers(wired: Path):
    """A command is an instruction, not part of the conversation; echoing it
    would put '/help' in the middle of a transcript."""
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/help")

        assert "> /help" not in written(app)


async def test_the_input_has_a_suggester_attached(wired: Path):
    app = SocrateseApp()
    async with app.run_test():
        assert app.query_one("#entry", Input).suggester is not None


async def test_slash_commands_are_suggested_as_you_type(wired: Path):
    app = SocrateseApp()
    async with app.run_test():
        suggester = app.query_one("#entry", Input).suggester
        assert suggester is not None

        for typed, expected in [
            ("/a", "/ask"),
            ("/re", "/resume"),
            ("/s", "/sources"),
            ("/v", "/vaults"),
        ]:
            assert await suggester.get_suggestion(typed) == expected


async def test_suggestions_are_case_insensitive(wired: Path):
    app = SocrateseApp()
    async with app.run_test():
        suggester = app.query_one("#entry", Input).suggester
        assert suggester is not None

        assert await suggester.get_suggestion("/AS") == "/ask"


async def test_plain_text_gets_no_suggestion(wired: Path):
    """Answers are prose; ghost-text completions over them would be noise."""
    app = SocrateseApp()
    async with app.run_test():
        suggester = app.query_one("#entry", Input).suggester
        assert suggester is not None

        assert await suggester.get_suggestion("the parent keeps") is None


async def test_every_command_is_offered(wired: Path):
    """A command absent from the list is undiscoverable without /help."""
    from socratese.tui.commands import COMMANDS, SUGGESTIONS

    assert set(SUGGESTIONS) == {f"/{c.name}" for c in COMMANDS}


# --- indexing ------------------------------------------------------------------


async def test_indexing_reports_each_stage_and_drives_the_bar(
    monkeypatch: pytest.MonkeyPatch, wired: Path
):
    """The bar has to be fed real numbers; a spinner that cannot move is what
    this replaced."""
    from socratese.cli import index as index_module

    def fake_index_vault(vault: object, on_progress: object = None) -> int:
        assert on_progress is not None
        on_progress("parsing", 0, 0)  # type: ignore[operator]
        on_progress("chunking", 10, 10)  # type: ignore[operator]
        on_progress("embedding", 0, 400)  # type: ignore[operator]
        on_progress("embedding", 200, 400)  # type: ignore[operator]
        on_progress("embedding", 400, 400)  # type: ignore[operator]
        on_progress("storing", 400, 400)  # type: ignore[operator]
        return 400

    monkeypatch.setattr(index_module, "index_vault", fake_index_vault)

    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/index work")
        await pilot.pause()
        await pilot.pause()

        transcript = written(app)
        assert "Reading notes" in transcript
        assert "Embedding" in transcript
        assert "400 chunks" in transcript


async def test_the_bar_is_hidden_until_indexing_starts(wired: Path):
    app = SocrateseApp()
    async with app.run_test():
        bar = app.query_one("#progress", ProgressBar)

        assert not bar.has_class("running")


async def test_the_bar_is_hidden_again_when_indexing_finishes(
    monkeypatch: pytest.MonkeyPatch, wired: Path
):
    from socratese.cli import index as index_module

    def fake_index_vault(vault: object, on_progress: object = None) -> int:
        on_progress("embedding", 5, 5)  # type: ignore[operator]
        return 5

    monkeypatch.setattr(index_module, "index_vault", fake_index_vault)

    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/index work")
        await pilot.pause()
        await pilot.pause()

        assert not app.query_one("#progress", ProgressBar).has_class("running")


async def test_indexing_an_unknown_vault_says_so(wired: Path):
    app = SocrateseApp()
    async with app.run_test() as pilot:
        await submit(pilot, app, "/index nope")
        await pilot.pause()

        assert "No vault named" in written(app)


# --- wrapping ------------------------------------------------------------------


async def test_text_rewraps_when_the_terminal_narrows(wired: Path):
    """Increasing the terminal's font scale means fewer columns. RichLog wraps
    once at write time, which left earlier lines too wide and cut off; these
    widgets re-wrap themselves."""
    long_line = (
        "In your example, you said MRO would pick between B and C based on "
        "left-to-right order, but what if the method is not implemented in B "
        "or C, and exists only in their shared grandparent A?"
    )
    app = SocrateseApp()
    async with app.run_test(size=(160, 20)) as pilot:
        app.say(long_line)
        await pilot.pause()
        widget = list(app.query_one("#log", VerticalScroll).query(Static))[-1]
        wide = widget.size.height

        await pilot.resize_terminal(70, 20)
        await pilot.pause()
        narrow = widget.size.height

        assert narrow > wide
        assert widget.size.width <= 70


async def test_the_bar_is_visible_while_indexing_runs(wired: Path):
    """Tested directly: the bar's whole job is to be on screen during the wait,
    and asserting only the before/after states misses it never appearing."""
    app = SocrateseApp()
    async with app.run_test() as pilot:
        bar = app.query_one("#progress", ProgressBar)

        app.progress_start("Embedding — work", 400)
        await pilot.pause()
        assert bar.has_class("running")

        app.progress_to(200, 400)
        await pilot.pause()
        assert bar.progress == 200
        assert bar.total == 400

        app.progress_done()
        await pilot.pause()
        assert not bar.has_class("running")
