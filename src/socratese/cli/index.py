from __future__ import annotations
from collections.abc import Callable
from datetime import datetime, timezone
import typer
import openai
from rich.console import Console
from rich.progress import Progress

from socratese.chunking.chunker import chunk_notes
from socratese.config import load_vaults, save_vaults
from socratese.embedding.embedder import embed_chunks
from socratese.ingest.parser import parse_vault
from socratese.vault.discovery import VAULT_MARKER
from socratese.vault.models import Vault
from socratese.vectorstore.store import add_chunks

console = Console(soft_wrap=True)

def index_vault(
    vault: Vault, on_progress: Callable[[str, int, int], None] | None = None
) -> int:
    """Parse, chunk, embed and store one vault. Returns the chunk count.

    `on_progress(stage, done, total)` lets a caller render progress without
    this function knowing what a console or a terminal app looks like.
    """
    if not (vault.path / VAULT_MARKER).is_dir():
        console.print(
            f"[red]Error:[/red] Vault '{vault.name}' at {vault.path} is not valid, skipping."
        )
        return 0

    def report(stage: str, done: int = 0, total: int = 0) -> None:
        if on_progress:
            on_progress(stage, done, total)

    report("parsing")
    notes = list(parse_vault(vault.path))
    report("chunking", len(notes), len(notes))
    chunks = chunk_notes(notes)

    if not chunks:
        console.print(f"[yellow]Warning:[/yellow] Vault '{vault.name}' has no content to index.")
        return 0

    with Progress(console=console) as progress:
        task = progress.add_task(f"Embedding '{vault.name}'...", total=len(chunks))

        def advance(done: int, total: int) -> None:
            progress.update(task, completed=done)
            report("embedding", done, total)

        embeddings = embed_chunks(chunks, on_progress=advance)

    report("storing", len(chunks), len(chunks))
    add_chunks(chunks, embeddings, vault.name)
    vault.last_indexed = datetime.now(timezone.utc)

    console.print(
        f"[green]Success:[/green] Indexed '{vault.name}': {len(notes)} notes, {len(chunks)} chunks."
    )
    return len(chunks)

def index(
        vault_name: str = typer.Argument(
            ..., help="Name of the vault to index, or 'all' to index every tracked vault"
        )
) -> None:
    """Parse, chunk, embed and store a vault's notes."""
    vaults = load_vaults()
    if not vaults:
        console.print("No vaults indexed. Run [bold]socratese vault add[/bold] first.")
        raise typer.Exit(code=1)

    if vault_name == "all":
        targets = vaults
    else:
        targets = [v for v in vaults if v.name == vault_name]
        if not targets:
            console.print(f"[red]Error:[/red] No vault named '{vault_name}' is indexed.")
            raise typer.Exit(code=1)

    try:
        for vault in targets:
            index_vault(vault)
    except openai.APIError as e:
        console.print(f"[red]Error:[/red] Embedding request failed: {e}")
        console.print("[yellow]Stopping.[/yellow] Progress from any vaults indexed before this point was saved.")
        raise typer.Exit(code=1)
    finally:
        save_vaults(vaults)
