# tests/tui/test_commands.py
from socratese.tui.commands import (
    BY_NAME,
    COMMANDS,
    SlashCommandSuggester,
    parse,
    unknown_command_hint,
)


def test_a_leading_slash_makes_a_command():
    parsed = parse("/ask how does redis persist data")

    assert parsed.is_command
    assert parsed.name == "ask"
    assert parsed.rest == "how does redis persist data"


def test_plain_text_is_an_answer_not_a_command():
    parsed = parse("the parent keeps serving writes")

    assert not parsed.is_command
    assert parsed.text == "the parent keeps serving writes"


def test_a_slash_inside_a_topic_is_not_a_command():
    """Topics contain slashes — tcp/ip, and/or — so only a leading one counts."""
    parsed = parse("it uses tcp/ip under the hood")

    assert not parsed.is_command


def test_command_names_are_case_insensitive():
    assert parse("/HELP").name == "help"


def test_a_command_with_no_arguments_has_empty_rest():
    parsed = parse("/resume")

    assert parsed.name == "resume"
    assert parsed.rest == ""
    assert parsed.args == []


def test_rest_rejoins_arguments_for_topics_and_paths():
    """A topic is prose, not argv — splitting and losing the spaces would
    turn '/ask how does X' into a search for 'how'."""
    assert parse("/ask how does react use the virtual DOM").rest == (
        "how does react use the virtual DOM"
    )


def test_surrounding_whitespace_is_ignored():
    assert parse("   /help   ").name == "help"
    assert parse("   ").text == ""


def test_arguments_split_for_commands_that_take_a_list():
    assert parse("/vaults work personal").args == ["work", "personal"]


def test_every_command_has_a_usage_line_and_summary():
    """/help renders these; a blank one would show an empty row."""
    for command in COMMANDS:
        assert command.usage.startswith(f"/{command.name}")
        assert command.summary


def test_command_names_are_unique():
    assert len(BY_NAME) == len(COMMANDS)


def test_a_typo_suggests_the_closest_command():
    assert "/resume" in unknown_command_hint("resum")
    assert "/ask" in unknown_command_hint("as")


def test_an_unrecognisable_command_points_at_help():
    assert "/help" in unknown_command_hint("zzzz")


# --- suggestions --------------------------------------------------------------


async def test_a_prefix_completes_to_the_first_matching_command():
    suggester = SlashCommandSuggester()

    assert await suggester.get_suggestion("/a") == "/ask"
    assert await suggester.get_suggestion("/re") == "/resume"
    assert await suggester.get_suggestion("/v") == "/vaults"


async def test_suggestions_ignore_case():
    """parse() accepts /ASK, so the suggestion has to as well — otherwise the
    completion vanishes the moment caps lock is on."""
    suggester = SlashCommandSuggester()

    assert await suggester.get_suggestion("/A") == "/ask"
    assert await suggester.get_suggestion("/RESUME") == "/resume"


async def test_prose_is_never_completed():
    """Answers are prose; ghost text over them would be noise."""
    suggester = SlashCommandSuggester()

    assert await suggester.get_suggestion("the parent keeps serving") is None
    assert await suggester.get_suggestion("a") is None


async def test_an_unmatched_command_suggests_nothing():
    assert await SlashCommandSuggester().get_suggestion("/zzz") is None


async def test_a_bare_slash_offers_the_first_command():
    assert await SlashCommandSuggester().get_suggestion("/") == "/ask"


async def test_every_command_is_reachable_by_its_own_name():
    """A command shadowed by an earlier prefix match would be uncompletable."""
    suggester = SlashCommandSuggester()

    for command in COMMANDS:
        assert await suggester.get_suggestion(f"/{command.name}") == f"/{command.name}"


async def test_an_empty_input_suggests_nothing():
    """Every command starts with "/", so an empty prefix matches them all —
    without a guard the box would sit there proposing /ask before you type."""
    assert await SlashCommandSuggester().get_suggestion("") is None
