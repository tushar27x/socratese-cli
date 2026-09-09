from dotenv import load_dotenv
import typer
from socratese.cli.vault import app as vault_app
from socratese.cli.index import index
load_dotenv()
app = typer.Typer(name="socratese")

app.add_typer(vault_app, name="vault")
app.command("index")(index)

if __name__ == "__main__":
    app()
