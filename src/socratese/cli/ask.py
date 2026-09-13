from __future__ import annotations

import anthropic
import openai
import typer
from rich.console import Console
from rich.panel import Panel

from socratese.config import load_vaults
from socratese.retrieval.retriever import retrieve
from socratese.dialogue.socratic import RELEVANCE_THRESHOLD, ask_questions


console = Console()

def ask(
    topic: str = typer.Argument(..., help="What you want to be questioned about"),
    n_chunks: int = typer.Option(5, "--chunks", "-n", help="how many notes to draw on"),
    sources: bool = typer.Option(
        False, "--sources", "-s", help="Reveal which notes the questions come from"
    ),
) -> None:
    """Be questioned Socratically about you own notes."""
    if not any(v.last_indexed for v in load_vaults()):
        console.print("No vault has been indexed yet. Run [bold]socratese index <vault>[/bold] first.")
        raise typer.Exit(code=1)

    try:
        with console.status("Searching you notes..."):
            chunks = retrieve(topic, n_results=n_chunks)
    except openai.APIError as e:
        console.print(f"[red]Error:[/red] Could not embed your question: {e}")
        raise typer.Exit(code=1)

    try:
        with console.status("Finding a question to ask you..."):
            question = ask_questions(topic=topic, chunks=chunks)
    except anthropic.AuthenticationError as e:
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY is missing or invalid. Check your .env file.")
        raise typer.Exit(code=1)
    except anthropic.APIError as e:
        console.print(f"[red]Error:[/red] The question request failed: {e}")
        raise typer.Exit(code=1)

    if question is None:
        console.print(f"[yellow]Your notes have nothing on '{topic}' yet.[/yellow]")
        console.print("Nothing was close enough to question you about.")
        raise typer.Exit(code=1)

    console.print()
    console.print(Panel(question, border_style="cyan", padding=(1, 2)))

    if sources:
        console.print("\n[dim]Grounded in:[/dim]")
        for c in chunks:
            if c.distance <= RELEVANCE_THRESHOLD:
                label = f"{c.note_title} — {c.heading}" if c.heading else c.note_title
                console.print(f"  [dim]{c.distance:.3f}  {label}[/dim]")