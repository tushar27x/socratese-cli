# tests/tui/test_commands.py
from socratese.tui.commands import BY_NAME, COMMANDS, parse, unknown_command_hint


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
