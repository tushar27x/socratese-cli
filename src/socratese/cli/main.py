import typer
from socratese.cli.vault import app as vault_app

app = typer.Typer(name="socratese")

app.add_typer(vault_app, name="vault")

if __name__ == "__main__":
    app()
