from __future__ import annotations

import os

import anthropic
import openai
import typer
from rich.console import Console
from rich.panel import Panel

from socratese.config import load_vaults
from socratese.dialogue.socratic import DEFAULT_MODEL, Session
from socratese.history.recorder import recording
from socratese.retrieval.retriever import retrieve


console = Console()

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
        console.print(f"[yellow]Your notes have nothing on '{topic}' yet. [/yellow]")
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

        history.question(question)
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

            history.answer(reply)

            try:
                with console.status("Thinking..."):
                    question = session.answer(reply)
            except anthropic.APIError as e:
                console.print(f"[red]Error:[/red] The question request failed: {e}")
                break

            history.question(question)

    console.print("\n[dim]Session ended.[/dim]")

    if sources:
        console.print("\n[dim]Grounded in:[/dim]")
        for c in session.chunks:
            label = f"{c.note_title} — {c.heading}" if c.heading else c.note_title
            console.print(f"  [dim]{c.distance:.3f}  {label}[/dim]")
