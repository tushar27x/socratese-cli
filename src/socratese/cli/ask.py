from __future__ import annotations

import os

import anthropic
import openai
import typer
from rich.console import Console
from rich.panel import Panel

from socratese.config import load_vaults
from socratese.dialogue.socratic import DEFAULT_MODEL, Session
from socratese.dialogue.stall import is_stalled, orbiting_terms
from socratese.history.recorder import SessionRecorder, recording, resuming
from socratese.history.store import connect, load_session, recent_sessions
from socratese.retrieval.retriever import retrieve

console = Console()


def _print_sources(session: Session, stalled: bool = False) -> None:
    if stalled:
        console.print(
            "\n[yellow]Worth re-reading — and possibly filling in:[/yellow]"
        )
    else:
        console.print("\n[dim]Grounded in:[/dim]")
    for chunk in session.chunks:
        label = f"{chunk.note_title} — {chunk.heading}" if chunk.heading else chunk.note_title
        console.print(f"  [dim]{chunk.distance:.3f}  {label}[/dim]")


def _converse(session: Session, history: SessionRecorder, question: str) -> bool:
    """Run the question/answer loop until the user stops or the API fails.

    Shared by `ask` and `resume` — the only difference between them is how the
    session and its opening question are obtained. Returns whether the
    conversation ever stalled, which decides if the notes are revealed at the end.
    """
    console.print("\n[dim]Answer in your own words. Blank line to end.[/dim]")

    asked = [question]
    warned = False

    while True:
        console.print()
        console.print(Panel(question, border_style="cyan", padding=(1, 2)))

        if not warned and is_stalled(asked, session.topic):
            terms = ", ".join(f"'{t}'" for t in sorted(orbiting_terms(asked, session.topic)))
            console.print(
                f"\n[yellow]These last few questions are all circling {terms}.[/yellow]"
            )
            console.print(
                "[dim]That usually means your notes don't settle what it's driving at."
                "\nKeep going if you want, or press enter to stop and see the notes.[/dim]"
            )
            warned = True

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
        asked.append(question)

    return warned


def ask(
    topic: str = typer.Argument(..., help="What you want to be questioned about"),
    n_chunks: int = typer.Option(5, "--chunks", "-n", help="how many notes to draw on"),
    vaults: list[str] = typer.Option(
        [], "--vault", "-v", help="Limit to these vaults. Repeatable; default is all."
    ),
    sources: bool = typer.Option(
        False, "--sources", "-s", help="Reveal which notes the questions come from"
    ),
) -> None:
    """Be questioned Socratically about your own notes."""
    indexed = [v for v in load_vaults() if v.last_indexed]
    if not indexed:
        console.print("No vault has been indexed yet. Run [bold]socratese index <vault>[/bold] first.")
        raise typer.Exit(code=1)

    known = {v.name for v in indexed}
    unknown = [name for name in vaults if name not in known]
    if unknown:
        console.print(f"[red]Error:[/red] No indexed vault named {', '.join(unknown)}.")
        console.print(f"Indexed vaults: {', '.join(sorted(known))}")
        raise typer.Exit(code=1)

    try:
        with console.status("Searching your notes..."):
            chunks = retrieve(topic, n_results=n_chunks, vaults=vaults or None)
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
        stalled = _converse(session, history, question)

    console.print("\n[dim]Session ended.[/dim]")

    if sources or stalled:
        _print_sources(session, stalled=stalled)


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

        stalled = _converse(session, history, question)

    console.print("\n[dim]Session ended.[/dim]")

    if sources or stalled:
        _print_sources(session, stalled=stalled)
