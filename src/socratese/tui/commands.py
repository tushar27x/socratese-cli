"""Parsing and describing the slash commands the app accepts.

Kept apart from the app so the command table can be tested, and rendered in
`/help`, without starting a terminal application.
"""
from __future__ import annotations

from dataclasses import dataclass

from textual.suggester import Suggester


@dataclass(frozen=True)
class Command:
    name: str
    usage: str
    summary: str


COMMANDS: tuple[Command, ...] = (
    Command("ask", "/ask <topic>", "Be questioned about a topic"),
    Command("resume", "/resume [id]", "List past sessions, or continue one"),
    Command("vaults", "/vaults [name ...]", "Pick which vaults sessions search"),
    Command("add", "/add <path>", "Track a new Obsidian vault"),
    Command("index", "/index <name|all>", "Index a vault's notes"),
    Command("sources", "/sources", "Reveal which notes the current session drew on"),
    Command("end", "/end", "End the current session without quitting"),
    Command("help", "/help", "Show this list"),
    Command("quit", "/quit", "Leave"),
)

BY_NAME = {command.name: command for command in COMMANDS}


@dataclass(frozen=True)
class Parsed:
    """A line of input, classified.

    `name` is empty for ordinary text, which is an answer to the current
    question rather than an instruction.
    """

    name: str
    args: list[str]
    text: str

    @property
    def is_command(self) -> bool:
        return bool(self.name)

    @property
    def rest(self) -> str:
        """Arguments rejoined — what a topic or path needs, unlike argv."""
        return " ".join(self.args)


def parse(line: str) -> Parsed:
    """Classify a line of input. Only a leading slash makes it a command.

    A topic can contain a slash ("tcp/ip"), so anything not *starting* with one
    is treated as prose.
    """
    stripped = line.strip()
    if not stripped.startswith("/"):
        return Parsed(name="", args=[], text=stripped)

    head, _, tail = stripped[1:].partition(" ")
    return Parsed(name=head.lower(), args=tail.split() if tail.strip() else [], text=stripped)


def unknown_command_hint(name: str) -> str:
    """Suggest the closest command, so a typo does not need /help to recover."""
    candidates = [c.name for c in COMMANDS if c.name.startswith(name[:2])]
    if candidates:
        return f"Unknown command /{name}. Did you mean /{candidates[0]}?"
    return f"Unknown command /{name}. Type /help to see what is available."


#: What the input offers as you type. Ordered so the most-used commands win a
#: shared prefix — "/a" completes to /ask, not /add.
SUGGESTIONS: tuple[str, ...] = tuple(f"/{command.name}" for command in COMMANDS)


class SlashCommandSuggester(Suggester):
    """Ghost-text completion for /commands, regardless of case.

    Not SuggestFromList: its `case_sensitive=False` does not match a
    differently-cased prefix in the installed Textual (`/A` suggests nothing),
    and `parse` accepts any case, so the suggestion should too.
    """

    def __init__(self, suggestions: tuple[str, ...] = SUGGESTIONS) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self.suggestions = suggestions

    async def get_suggestion(self, value: str) -> str | None:
        # Folded here rather than relying on case_sensitive=False: that only
        # folds on the path through the caching wrapper, so a direct call --
        # including from a test -- would otherwise behave differently from the
        # widget.
        folded = value.casefold()
        if not folded.startswith("/"):
            return None
        return next((s for s in self.suggestions if s.startswith(folded)), None)
