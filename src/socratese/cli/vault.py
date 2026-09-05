"""`socratese vault ...` subcommand group.

Commands to implement per the decisions log (CLAUDE.md section 5):
  vault list
  vault add [PATH]
  vault remove <NAME>
  vault rescan
"""

import typer

app = typer.Typer(help="Manage indexed Obsidian vaults.")
