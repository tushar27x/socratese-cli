"""Socratese CLI entrypoint.

Wires together the Typer app and subcommand groups. No command logic
lives here — that goes in the individual command modules.
"""

import typer

app = typer.Typer(name="socratese")

# TODO: app.add_typer(vault_app, name="vault") once vault.py has commands.


if __name__ == "__main__":
    app()
