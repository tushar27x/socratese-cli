from dotenv import load_dotenv
load_dotenv()
import typer
from socratese.cli.vault import app as vault_app
from socratese.cli.index import index
from socratese.cli.ask import ask, resume
app = typer.Typer(name="socratese")

app.add_typer(vault_app, name="vault")
app.command("index")(index)
app.command("ask")(ask)
app.command("resume")(resume)

if __name__ == "__main__":
    app()
