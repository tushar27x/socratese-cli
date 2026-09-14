"""Parsing and describing the slash commands the app accepts.

Kept apart from the app so the command table can be tested, and rendered in
`/help`, without starting a terminal application.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    usage: str
    summary: str


COMMANDS: tuple[Command, ...] = (
    Command("ask", "/ask <topic>", "Be questioned about a topic"),
    Command("resume", "/resume [id]", "List past sessions, or continue one"),
    Command("vaults", "/vaults [name ...]", "Show vaults, or limit the next session to some"),
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
