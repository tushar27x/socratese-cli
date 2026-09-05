from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from socratese.config import load_vaults, save_vaults
from socratese.vault.discovery import VAULT_MARKER
from socratese.vault.models import Vault

app = typer.Typer(help="Manage indexed Obsidian vaults.")
console = Console(soft_wrap=True)

@app.command("list")
def list_vaults() -> None:
    vaults = load_vaults()
    if not vaults:
        console.print("No vaults indexed. Run [bold]socratese vault add[/bold] to add a vault.")
        return

    table = Table("Name", "Path", "Last Indexed")
    for vault in vaults:
      last_indexed =vault.last_indexed.isoformat() if vault.last_indexed else "Never"
      table.add_row(vault.name, str(vault.path), last_indexed)
    console.print(table)

@app.command("add")
def add_vault(
   path: Path = typer.Argument(
      ..., help="Path to the Obsidian vault (a directory containing a .obsidian)."
   )
) -> None:
  path = path.expanduser().resolve()

  if not (path / VAULT_MARKER).is_dir():
     console.print(f"[red]Error:[/red] {path} is not a valid Obsidian vault (missing {VAULT_MARKER}).")
     raise typer.Exit(code=1)

  vaults = load_vaults()
  if any(v.path == path for v in vaults):
      console.print(f"[yellow]Warning:[/yellow] Vault at {path} is already indexed.")
      raise typer.Exit(code=1)

  name = path.name
  if any(v.name == name for v in vaults):
      console.print(f"[yellow]Warning:[/yellow] A vault named '{name}' is already indexed. Consider renaming the directory.")
      raise typer.Exit(code=1)
  
  vaults.append(Vault(name=name, path=path))
  save_vaults(vaults)
  console.print(f"[green]Success:[/green] Vault '{name}' added at {path}.")

@app.command("remove")
def remove_vault(
   name: str = typer.Argument(..., help="Name of the vault to remove.")
) -> None:
  vaults = load_vaults()
  remaining = [v for v in vaults if v.name != name]

  if len(remaining) == len(vaults):
      console.print(f"[red]Error:[/red] No vault named '{name}' is indexed.")
      raise typer.Exit(code=1)
  save_vaults(remaining)
  console.print(f"[green]Success:[/green] Vault '{name}' removed.")

@app.command("rescan")
def rescan_vaults() -> None:
    vaults = load_vaults()
    still_valid = []
    for vault in vaults:
      if (vault.path /VAULT_MARKER).is_dir():
        still_valid.append(vault)
      else:
        console.print(f"[yellow]Warning:[/yellow] Vault '{vault.name}' at {vault.path} is no longer valid and will be removed.")

    if len(still_valid) != len(vaults):
      save_vaults(still_valid)
      console.print(f"[green]Success:[/green] Rescan complete. {len(vaults) - len(still_valid)} vault(s) removed.")
    else:
      console.print("[green]Success:[/green] Rescan complete. All vaults are valid.")