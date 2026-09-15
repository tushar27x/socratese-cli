from dotenv import load_dotenv
load_dotenv()
import typer
from socratese.cli.vault import app as vault_app
from socratese.cli.index import index
from socratese.cli.ask import ask, resume
app = typer.Typer(name="socratese", invoke_without_command=True)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Be questioned Socratically about your own Obsidian notes."""
    # bare `socratese` opens the terminal app; subcommands stay scriptable
    if ctx.invoked_subcommand is None:
        from socratese.tui.app import run

        run()

app.add_typer(vault_app, name="vault")
app.command("index")(index)
app.command("ask")(ask)
app.command("resume")(resume)

if __name__ == "__main__":
    app()
