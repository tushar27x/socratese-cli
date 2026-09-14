from __future__ import annotations

import os

import anthropic
import openai
import typer
from rich.console import Console
from rich.panel import Panel

from socratese.config import load_vaults
from socratese.dialogue.socratic import DEFAULT_MODEL, Session
from socratese.history.recorder import SessionRecorder, recording, resuming
from socratese.history.store import connect, load_session, recent_sessions
from socratese.retrieval.retriever import retrieve

console = Console()


def _print_sources(session: Session) -> None:
    console.print("\n[dim]Grounded in:[/dim]")
    for chunk in session.chunks:
        label = f"{chunk.note_title} — {chunk.heading}" if chunk.heading else chunk.note_title
        console.print(f"  [dim]{chunk.distance:.3f}  {label}[/dim]")


def _converse(session: Session, history: SessionRecorder, question: str) -> None:
    """Run the question/answer loop until the user stops or the API fails.

    Shared by `ask` and `resume` — the only difference between them is how the
    session and its opening question are obtained.
    """
    console.print("\n[dim]Answer in your own words. Blank line to end.[/dim]")

    while True:
        console.print()
        console.print(Panel(question, border_style="cyan", padding=(1, 2)))

        try:
            reply = console.input("\n[bold cyan]>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not reply:
            break

        history.answer(reply, session.messages)

        try:
            with console.status("Thinking..."):
                question = session.answer(reply)
        except anthropic.APIError as e:
            console.print(f"[red]Error:[/red] The question request failed: {e}")
            break

        history.question(question, session.messages)


def ask(
    topic: str = typer.Argument(..., help="What you want to be questioned about"),
    n_chunks: int = typer.Option(5, "--chunks", "-n", help="how many notes to draw on"),
    sources: bool = typer.Option(
        False, "--sources", "-s", help="Reveal which notes the questions come from"
    ),
) -> None:
    """Be questioned Socratically about your own notes."""
    if not any(v.last_indexed for v in load_vaults()):
        console.print("No vault has been indexed yet. Run [bold]socratese index <vault>[/bold] first.")
        raise typer.Exit(code=1)

    try:
        with console.status("Searching your notes..."):
            chunks = retrieve(topic, n_results=n_chunks)
    except openai.APIError as e:
        console.print(f"[red]Error:[/red] Could not embed your question: {e}")
        raise typer.Exit(code=1)

    session = Session(topic, chunks)
    if not session.has_grounding:
        console.print(f"[yellow]Your notes have nothing on '{topic}' yet.[/yellow]")
        console.print("Nothing was close enough to question you about.")
        raise typer.Exit(code=1)

    model = os.environ.get("DIALOGUE_MODEL", DEFAULT_MODEL)

    with recording(topic, model, session.chunks) as history:
        try:
            with console.status("Finding a question to ask you..."):
                question = session.opening_question()
        except anthropic.AuthenticationError:
            console.print("[red]Error:[/red] ANTHROPIC_API_KEY is missing or invalid. Check your .env file.")
            raise typer.Exit(code=1)
        except anthropic.APIError as e:
            console.print(f"[red]Error:[/red] The question request failed: {e}")
            raise typer.Exit(code=1)

        history.question(question, session.messages)
        _converse(session, history, question)

    console.print("\n[dim]Session ended.[/dim]")

    if sources:
        _print_sources(session)


def resume(
    session_id: int | None = typer.Argument(
        None, help="Which session to resume. Omit to list recent ones."
    ),
    sources: bool = typer.Option(
        False, "--sources", "-s", help="Reveal which notes the questions come from"
    ),
) -> None:
    """Pick up a previous session where you left it."""
    conn = connect()

    if session_id is None:
        sessions = recent_sessions(conn)
        if not sessions:
            console.print("No past sessions yet. Run [bold]socratese ask[/bold] first.")
            raise typer.Exit(code=1)

        console.print("\n[dim]Recent sessions:[/dim]")
        for stored in sessions:
            mark = " " if stored.is_resumable else "*"
            console.print(
                f"  {mark}[bold]{stored.id}[/bold]  {stored.started_at:%Y-%m-%d %H:%M}"
                f"  [dim]{stored.answered_count} answered[/dim]  {stored.topic}"
            )
        if any(not s.is_resumable for s in sessions):
            console.print("\n[dim]* recorded before transcripts were saved; cannot be resumed[/dim]")
        console.print("\nResume one with [bold]socratese resume <id>[/bold].")
        raise typer.Exit()

    record = load_session(conn, session_id)
    if record is None:
        console.print(f"[red]Error:[/red] No session {session_id}. Run [bold]socratese resume[/bold] to list them.")
        raise typer.Exit(code=1)

    if not record.is_resumable:
        console.print(f"[yellow]Session {session_id} has no stored transcript.[/yellow]")
        console.print("It predates transcript storage, so there is nothing to continue from.")
        raise typer.Exit(code=1)

    session = Session.from_messages(record.topic, record.chunks, record.messages)

    console.print(f"\n[dim]Resuming session {record.id}: {record.topic}[/dim]")
    for turn in record.turns:
        if turn.answer:
            console.print(f"  [dim]Q{turn.ordinal}[/dim] {turn.question}")
            console.print(f"  [dim]  >[/dim] {turn.answer}")

    last = record.turns[-1] if record.turns else None
    if last is None:
        console.print("[red]Error:[/red] That session has no recorded questions.")
        raise typer.Exit(code=1)

    with resuming(record.id) as history:
        if last.answer is None:
            question = last.question
        else:
            # the session ended on an answered question, so it needs a new one
            try:
                with console.status("Picking up where you left off..."):
                    question = session.answer(last.answer)
            except anthropic.APIError as e:
                console.print(f"[red]Error:[/red] The question request failed: {e}")
                raise typer.Exit(code=1)
            history.question(question, session.messages)

        _converse(session, history, question)

    console.print("\n[dim]Session ended.[/dim]")

    if sources:
        _print_sources(session)
