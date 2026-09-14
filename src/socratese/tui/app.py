"""The Socratese terminal application.

Runs when `socratese` is invoked with no subcommand. The Typer subcommands
remain for scripting; this is the interactive surface.

Every call that touches the network runs in a thread worker. Textual's event
loop is single-threaded, so an embedding or dialogue request on it would
freeze the interface for the duration — including the spinner meant to show
that something is happening.
"""
from __future__ import annotations

import os
from contextlib import AbstractContextManager

import anthropic
import openai
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, ProgressBar, Static

from socratese import tutor
from socratese.dialogue.socratic import DEFAULT_MODEL, Session
from socratese.dialogue.stall import is_stalled, orbiting_terms
from socratese.history.models import SessionRecord
from socratese.history.recorder import SessionRecorder, recording, resuming
from socratese.history.store import connect, load_session, recent_sessions
from socratese.tui.commands import (
    COMMANDS,
    SlashCommandSuggester,
    parse,
    unknown_command_hint,
)

BANNER = "Socratese — you answer, it asks. /help for commands."


class SocrateseApp(App[None]):
    """A conversation pane and a single input that doubles as a command bar."""


    #: Backgrounds are transparent throughout: a solid fill would paint over
    #: the terminal's background (and any wallpaper behind it), which is the
    #: one thing a terminal app should not take from the user.
    CSS = """
    Screen {
        background: transparent;
        layout: vertical;
    }
    #log {
        height: 1fr;
        background: transparent;
        padding: 0 1;
        scrollbar-size-vertical: 1;
        overflow-x: hidden;
    }
    #log Static {
        background: transparent;
        width: 100%;
    }
    #entry {
        dock: bottom;
        height: 3;
        background: transparent;
        border: round ansi_blue;
        padding: 0 1;
    }
    #entry:focus {
        border: round ansi_bright_blue;
    }
    /* One docked container, so the bar and the input share an allocation
       instead of competing for the bottom rows. Docking both separately put
       the bar on the input's border row, where it was drawn underneath. */
    #bottom {
        dock: bottom;
        height: 3;
        background: transparent;
    }
    /* Explicit heights, not `auto`: with the bar hidden, auto collapsed the
       container to zero and the input floated over the log, letting the
       transcript scroll underneath it. */
    #bottom.indexing {
        height: 4;
    }
    #progress {
        height: 1;
        padding: 0 2;
        background: transparent;
        display: none;
    }
    #progress.running {
        display: block;
    }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self) -> None:
        # ansi_color makes Textual emit the terminal's own 16 ANSI colours
        # instead of its palette, so the app inherits the user's theme rather
        # than imposing one. It is a reactive, so it is set, not overridden.
        super().__init__(ansi_color=True)
        self.session: Session | None = None
        self.history: SessionRecorder | None = None
        self._open_recordings: list[AbstractContextManager[SessionRecorder]] = []
        self.selected_vaults: list[str] = []
        self.asked: list[str] = []
        self.warned_stalled = False

    # --- layout ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        # No Header or Footer: both paint a solid bar, and a docked Footer
        # competes with the input for the bottom rows and clips its border.
        #
        # A scroll of Static widgets rather than a RichLog: RichLog wraps text
        # once, when it is written, and never again. Increasing the terminal's
        # font scale means fewer columns, which left every earlier line too
        # wide and cut off behind a horizontal scrollbar. Static re-wraps
        # itself whenever its width changes.
        yield VerticalScroll(id="log")
        with Vertical(id="bottom"):
            yield ProgressBar(id="progress", show_eta=False)
            yield Input(
                placeholder="Type an answer, or /help",
                id="entry",
                suggester=SlashCommandSuggester(),
            )

    def on_mount(self) -> None:
        self.title = "socratese"
        self.say(f"[bold]{BANNER}[/bold]")
        self.show_vaults()
        self.query_one("#entry", Input).focus()

    # --- output ---------------------------------------------------------

    def say(self, markup: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(markup, markup=True))
        log.scroll_end(animate=False)

    def say_question(self, question: str) -> None:
        self.say("")
        self.say(f"[bold ansi_bright_cyan]{question}[/bold ansi_bright_cyan]")
        self.say("")

    def say_error(self, message: str) -> None:
        self.say(f"[ansi_red]{message}[/ansi_red]")

    def say_answer(self, text: str) -> None:
        """Echo what the user typed.

        Without this the pane shows only questions, which reads as a list of
        demands rather than a conversation — and makes a resumed transcript
        impossible to follow.
        """
        self.say(f"[dim]>[/dim] {text}")

    # --- input ----------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.input.value = ""
        parsed = parse(event.value)

        if not parsed.text:
            return

        if not parsed.is_command:
            self.say_answer(parsed.text)
            self.answer(parsed.text)
            return

        handler = getattr(self, f"cmd_{parsed.name}", None)
        if handler is None:
            self.say_error(unknown_command_hint(parsed.name))
            return
        handler(parsed.rest)

    # --- commands -------------------------------------------------------

    def cmd_help(self, rest: str) -> None:
        self.say("")
        for command in COMMANDS:
            self.say(f"  [bold]{command.usage:<20}[/bold] [dim]{command.summary}[/dim]")

    def cmd_quit(self, rest: str) -> None:
        self.end_session(announce=False)
        self.exit()

    def cmd_vaults(self, rest: str) -> None:
        names = rest.split()
        if not names:
            self.show_vaults()
            return

        known = {v.name for v in tutor.indexed_vaults()}
        unknown = [n for n in names if n not in known]
        if unknown:
            self.say_error(f"Not indexed: {', '.join(unknown)}")
            return

        self.selected_vaults = names
        self.say(f"[ansi_green]Next session will use:[/ansi_green] {', '.join(names)}")

    def cmd_ask(self, rest: str) -> None:
        if not rest:
            self.say_error("Give me a topic: /ask how does redis persist data")
            return
        if self.session is not None:
            self.say_error("A session is already running. /end it first.")
            return
        self.say(f"\n[dim]Searching your notes for '{rest}'...[/dim]")
        self.begin(rest)

    def cmd_resume(self, rest: str) -> None:
        if self.session is not None:
            self.say_error("A session is already running. /end it first.")
            return
        if not rest:
            self.list_sessions()
            return
        if not rest.isdigit():
            self.say_error(f"'{rest}' is not a session id. /resume with no id lists them.")
            return
        self.continue_session(int(rest))

    def cmd_sources(self, rest: str) -> None:
        if self.session is None:
            self.say_error("No session running.")
            return
        self.say("\n[dim]Grounded in:[/dim]")
        for chunk in self.session.chunks:
            label = f"{chunk.note_title} — {chunk.heading}" if chunk.heading else chunk.note_title
            self.say(f"  [dim]{chunk.distance:.3f}  {label}[/dim]")

    def cmd_end(self, rest: str) -> None:
        if self.session is None:
            self.say_error("No session running.")
            return
        self.end_session()

    def cmd_add(self, rest: str) -> None:
        from socratese.cli.vault import VAULT_MARKER
        from socratese.config import load_vaults, save_vaults
        from pathlib import Path
        from socratese.vault.models import Vault

        if not rest:
            self.say_error("Give me a path: /add ~/Documents/MyVault")
            return

        path = Path(rest).expanduser().resolve()
        if not (path / VAULT_MARKER).is_dir():
            self.say_error(f"{path} is not an Obsidian vault (no {VAULT_MARKER}).")
            return

        vaults = load_vaults()
        if any(v.path == path for v in vaults):
            self.say_error(f"{path} is already tracked.")
            return

        vaults.append(Vault(name=path.name, path=path))
        save_vaults(vaults)
        self.say(f"[ansi_green]Added[/ansi_green] {path.name} — /index {path.name} to make it searchable.")

    def cmd_index(self, rest: str) -> None:
        if not rest:
            self.say_error("Name a vault, or 'all': /index learning")
            return
        self.run_index(rest)

    # --- progress ---------------------------------------------------------

    def progress_start(self, label: str, total: int) -> None:
        bar = self.query_one("#progress", ProgressBar)
        bar.update(total=total or None, progress=0)
        bar.add_class("running")
        self.query_one("#bottom").add_class("indexing")
        self.say(f"[dim]{label}[/dim]")

    def progress_to(self, done: int, total: int) -> None:
        self.query_one("#progress", ProgressBar).update(total=total or None, progress=done)

    def progress_done(self) -> None:
        self.query_one("#progress", ProgressBar).remove_class("running")
        self.query_one("#bottom").remove_class("indexing")

    # --- views ----------------------------------------------------------

    def show_vaults(self) -> None:
        from socratese.config import load_vaults

        vaults = load_vaults()
        if not vaults:
            self.say("[ansi_yellow]No vaults tracked.[/ansi_yellow] /add <path> to start.")
            return

        self.say("")
        for vault in vaults:
            if vault.last_indexed:
                state = f"indexed {vault.last_indexed:%Y-%m-%d}"
            else:
                state = "[ansi_yellow]never indexed[/ansi_yellow]"
            chosen = "▸" if vault.name in self.selected_vaults else " "
            self.say(f" {chosen} [bold]{vault.name}[/bold]  [dim]{vault.path}  ({state})[/dim]")

        scope = ", ".join(self.selected_vaults) if self.selected_vaults else "all indexed vaults"
        self.say(f"\n[dim]Sessions will search: {scope}[/dim]")

    def list_sessions(self) -> None:
        conn = connect()
        try:
            sessions = recent_sessions(conn)
        finally:
            conn.close()

        if not sessions:
            self.say("[ansi_yellow]No past sessions.[/ansi_yellow] /ask to start one.")
            return

        self.say("")
        for stored in sessions:
            mark = " " if stored.is_resumable else "*"
            self.say(
                f" {mark}[bold]{stored.id}[/bold]  [dim]{stored.started_at:%Y-%m-%d %H:%M}"
                f"  {stored.answered_count} answered[/dim]  {stored.topic}"
            )
        if any(not s.is_resumable for s in sessions):
            self.say("\n[dim]* predates transcript storage; cannot be resumed[/dim]")
        self.say("[dim]/resume <id> to continue one.[/dim]")

    # --- session lifecycle ----------------------------------------------

    def open_recorder(
        self, manager: AbstractContextManager[SessionRecorder]
    ) -> SessionRecorder:
        """Enter a recording context and keep it open across many turns.

        The CLI can use `with recording(...)`; here the session outlives the
        function that starts it, so the context manager is entered by hand and
        exited in end_session.
        """
        recorder = manager.__enter__()
        self._open_recordings.append(manager)
        return recorder

    def end_session(self, announce: bool = True) -> None:
        while self._open_recordings:
            self._open_recordings.pop().__exit__(None, None, None)

        stalled = self.warned_stalled
        session = self.session
        self.session = None
        self.history = None
        self.asked = []
        self.warned_stalled = False

        if announce:
            self.say("\n[dim]Session ended.[/dim]")
        if stalled and session is not None:
            self.say("[ansi_yellow]Worth re-reading — and possibly filling in:[/ansi_yellow]")
            for chunk in session.chunks:
                label = f"{chunk.note_title} — {chunk.heading}" if chunk.heading else chunk.note_title
                self.say(f"  [dim]{chunk.distance:.3f}  {label}[/dim]")

    def after_question(self, question: str) -> None:
        self.asked.append(question)
        self.say_question(question)

        if not self.warned_stalled and self.session and is_stalled(self.asked, self.session.topic):
            terms = ", ".join(f"'{t}'" for t in sorted(orbiting_terms(self.asked, self.session.topic)))
            self.warned_stalled = True
            self.say(f"[ansi_yellow]These last few questions are all circling {terms}.[/ansi_yellow]")
            self.say("[dim]Your notes may not settle what it is driving at. /end to stop and see them.[/dim]")

    # --- workers ---------------------------------------------------------

    @work(thread=True, exclusive=True)
    def begin(self, topic: str) -> None:
        try:
            session = tutor.start(topic, vaults=self.selected_vaults or None)
        except tutor.TutorError as e:
            self.call_from_thread(self.say_error, str(e))
            return
        except openai.APIError as e:
            self.call_from_thread(self.say_error, f"Could not embed your question: {e}")
            return

        model = os.environ.get("DIALOGUE_MODEL", DEFAULT_MODEL)
        recorder = self.open_recorder(recording(topic, model, session.chunks))

        try:
            question = session.opening_question()
        except anthropic.APIError as e:
            self.call_from_thread(self.say_error, f"The question request failed: {e}")
            self.call_from_thread(self.end_session, False)
            return

        recorder.question(question, session.messages)
        self.session = session
        self.history = recorder
        self.call_from_thread(self.after_question, question)

    @work(thread=True, exclusive=True)
    def answer(self, reply: str) -> None:
        session, history = self.session, self.history
        if session is None or history is None:
            self.call_from_thread(
                self.say_error, "No session running. /ask <topic> to start one."
            )
            return

        history.answer(reply, session.messages)
        try:
            question = session.answer(reply)
        except anthropic.APIError as e:
            self.call_from_thread(self.say_error, f"The question request failed: {e}")
            return

        history.question(question, session.messages)
        self.call_from_thread(self.after_question, question)

    @work(thread=True, exclusive=True)
    def continue_session(self, session_id: int) -> None:
        conn = connect()
        try:
            record: SessionRecord | None = load_session(conn, session_id)
        finally:
            conn.close()

        if record is None:
            self.call_from_thread(self.say_error, f"No session {session_id}.")
            return

        try:
            session = tutor.resume(record)
        except tutor.TutorError as e:
            self.call_from_thread(self.say_error, str(e))
            return

        self.call_from_thread(self.say, f"\n[dim]Resuming {record.id}: {record.topic}[/dim]")
        for turn in record.turns:
            if turn.answer:
                self.call_from_thread(self.say, f"[dim]{turn.question}[/dim]")
                self.call_from_thread(self.say_answer, turn.answer)

        last = record.turns[-1] if record.turns else None
        if last is None:
            self.call_from_thread(self.say_error, "That session has no recorded questions.")
            return

        recorder = self.open_recorder(resuming(record.id))

        if last.answer is None:
            question = last.question
        else:
            try:
                question = session.answer(last.answer)
            except anthropic.APIError as e:
                self.call_from_thread(self.say_error, f"The question request failed: {e}")
                self.call_from_thread(self.end_session, False)
                return
            recorder.question(question, session.messages)

        self.session = session
        self.history = recorder
        self.call_from_thread(self.after_question, question)

    @work(thread=True, exclusive=True)
    def run_index(self, name: str) -> None:
        from socratese.cli.index import index_vault
        from socratese.config import load_vaults, save_vaults

        vaults = load_vaults()
        targets = vaults if name == "all" else [v for v in vaults if v.name == name]
        if not targets:
            self.call_from_thread(self.say_error, f"No vault named '{name}'.")
            return

        STAGES = {
            "parsing": "Reading notes",
            "chunking": "Splitting into chunks",
            "embedding": "Embedding",
            "storing": "Storing",
        }

        try:
            for vault in targets:
                seen: set[str] = set()

                def report(stage: str, done: int, total: int, name: str = vault.name) -> None:
                    if stage not in seen:
                        seen.add(stage)
                        self.call_from_thread(
                            self.progress_start, f"{STAGES[stage]} — {name}", total
                        )
                    elif total:
                        self.call_from_thread(self.progress_to, done, total)

                chunks = index_vault(vault, on_progress=report)
                self.call_from_thread(
                    self.say, f"[ansi_green]Indexed[/ansi_green] {vault.name}: {chunks} chunks."
                )
        except openai.APIError as e:
            self.call_from_thread(self.say_error, f"Embedding failed: {e}")
        finally:
            save_vaults(vaults)
            self.call_from_thread(self.progress_done)


def run() -> None:
    SocrateseApp().run()
