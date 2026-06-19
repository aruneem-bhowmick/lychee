"""Tests for the @lychee command parser (lychee.commands).

Covers mention detection, command extraction, edge cases (whitespace,
punctuation, multiple mentions, code blocks), enum correctness, help text
completeness, and frozen dataclass immutability.

Framework: pytest
"""

from __future__ import annotations

import dataclasses

import pytest

from lychee.commands import (
    HELP_TEXT,
    Command,
    ParsedCommand,
    ParseResult,
    UnknownCommand,
    is_lychee_mention,
    parse_command,
)

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def test_commands_module_imports() -> None:
    """All public names import cleanly from lychee.commands."""
    from lychee.commands import (  # noqa: F401
        HELP_TEXT,
        Command,
        ParsedCommand,
        UnknownCommand,
        is_lychee_mention,
        parse_command,
    )


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_command_enum_is_str_enum() -> None:
    """Command is a StrEnum and its members are str instances."""
    assert issubclass(Command, str)
    for member in Command:
        assert isinstance(member, str)


def test_parsed_command_is_frozen() -> None:
    """ParsedCommand and UnknownCommand are immutable (frozen dataclasses)."""
    pc = ParsedCommand(command=Command.peel)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pc.command = Command.juice  # type: ignore[misc]

    uc = UnknownCommand(raw_text="bad")
    with pytest.raises(dataclasses.FrozenInstanceError):
        uc.raw_text = "worse"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Unit tests — Command enum
# ---------------------------------------------------------------------------


def test_command_enum_values() -> None:
    """All four members exist with correct string values."""
    assert Command.peel.value == "peel"
    assert Command.juice.value == "juice"
    assert Command.pit.value == "pit"
    assert Command.ripe.value == "ripe?"
    assert len(Command) == 4


# ---------------------------------------------------------------------------
# Unit tests — is_lychee_mention
# ---------------------------------------------------------------------------


def test_is_lychee_mention_true() -> None:
    """@lychee in various positions returns True."""
    assert is_lychee_mention("@lychee peel") is True
    assert is_lychee_mention("please @lychee review") is True
    assert is_lychee_mention("@LYCHEE") is True
    assert is_lychee_mention("  @lychee  ") is True


def test_is_lychee_mention_false() -> None:
    """Text without @lychee returns False."""
    assert is_lychee_mention("just a regular comment") is False
    assert is_lychee_mention("lychee fruit") is False
    assert is_lychee_mention("") is False


def test_is_lychee_mention_partial() -> None:
    """@lychee-bot does not match (word boundary)."""
    assert is_lychee_mention("@lychee-bot hello") is False
    assert is_lychee_mention("@lycheefoo") is False


# ---------------------------------------------------------------------------
# Unit tests — parse_command: valid commands
# ---------------------------------------------------------------------------


def test_parse_valid_peel() -> None:
    """@lychee peel returns ParsedCommand(Command.peel)."""
    result = parse_command("@lychee peel")
    assert result == ParsedCommand(command=Command.peel)


def test_parse_valid_juice() -> None:
    """@lychee juice returns ParsedCommand(Command.juice)."""
    result = parse_command("@lychee juice")
    assert result == ParsedCommand(command=Command.juice)


def test_parse_valid_pit() -> None:
    """@lychee pit returns ParsedCommand(Command.pit)."""
    result = parse_command("@lychee pit")
    assert result == ParsedCommand(command=Command.pit)


def test_parse_valid_ripe() -> None:
    """@lychee ripe? returns ParsedCommand(Command.ripe)."""
    result = parse_command("@lychee ripe?")
    assert result == ParsedCommand(command=Command.ripe)


# ---------------------------------------------------------------------------
# Unit tests — parse_command: case insensitivity
# ---------------------------------------------------------------------------


def test_parse_case_insensitive() -> None:
    """@Lychee Peel, @LYCHEE JUICE, etc. all parse correctly."""
    assert parse_command("@Lychee Peel") == ParsedCommand(command=Command.peel)
    assert parse_command("@LYCHEE JUICE") == ParsedCommand(command=Command.juice)
    assert parse_command("@LyChEe PiT") == ParsedCommand(command=Command.pit)
    assert parse_command("@LYCHEE RIPE?") == ParsedCommand(command=Command.ripe)


# ---------------------------------------------------------------------------
# Unit tests — parse_command: unknown and missing commands
# ---------------------------------------------------------------------------


def test_parse_bare_mention() -> None:
    """@lychee alone returns UnknownCommand(raw_text="")."""
    result = parse_command("@lychee")
    assert result == UnknownCommand(raw_text="")


def test_parse_unknown_command() -> None:
    """@lychee foobar returns UnknownCommand(raw_text="foobar")."""
    result = parse_command("@lychee foobar")
    assert result == UnknownCommand(raw_text="foobar")


def test_parse_no_mention() -> None:
    """A comment without @lychee returns None."""
    result = parse_command("just a regular comment")
    assert result is None


# ---------------------------------------------------------------------------
# Unit tests — parse_command: edge cases
# ---------------------------------------------------------------------------


def test_parse_mention_in_sentence() -> None:
    """hey @lychee peel this please returns ParsedCommand(Command.peel)."""
    result = parse_command("hey @lychee peel this please")
    assert result == ParsedCommand(command=Command.peel)


def test_parse_trailing_punctuation() -> None:
    """@lychee peel! strips trailing punctuation and parses as peel."""
    result = parse_command("@lychee peel!")
    assert result == ParsedCommand(command=Command.peel)


def test_parse_ripe_question_mark() -> None:
    """@lychee ripe? correctly handles the ? as part of the command."""
    result = parse_command("@lychee ripe?")
    assert result == ParsedCommand(command=Command.ripe)


def test_parse_multiple_mentions() -> None:
    """@lychee peel and @lychee juice uses the first (peel)."""
    result = parse_command("@lychee peel and @lychee juice")
    assert result == ParsedCommand(command=Command.peel)


def test_parse_whitespace_padding() -> None:
    """Extra leading/trailing/inner whitespace is handled."""
    result = parse_command("  @lychee   pit  ")
    assert result == ParsedCommand(command=Command.pit)


def test_parse_in_code_block() -> None:
    """`@lychee peel` inside backticks still parses (text-based detection)."""
    result = parse_command("`@lychee peel`")
    assert result == ParsedCommand(command=Command.peel)


# ---------------------------------------------------------------------------
# Unit tests — HELP_TEXT
# ---------------------------------------------------------------------------


def test_help_text_contains_all_commands() -> None:
    """HELP_TEXT mentions peel, juice, pit, and ripe?."""
    assert "peel" in HELP_TEXT
    assert "juice" in HELP_TEXT
    assert "pit" in HELP_TEXT
    assert "ripe?" in HELP_TEXT


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_valid_commands_parsed() -> None:
    """Each of the four valid commands parses to the correct ParsedCommand."""
    cases: list[tuple[str, Command]] = [
        ("@lychee peel", Command.peel),
        ("@lychee juice", Command.juice),
        ("@lychee pit", Command.pit),
        ("@lychee ripe?", Command.ripe),
    ]
    for body, expected_cmd in cases:
        result = parse_command(body)
        assert isinstance(result, ParsedCommand)
        assert result.command == expected_cmd


def test_accept_unknown_gets_help() -> None:
    """An unrecognized command returns UnknownCommand, signaling a help reply."""
    result = parse_command("@lychee somethinginvalid")
    assert isinstance(result, UnknownCommand)
    assert result.raw_text == "somethinginvalid"


def test_accept_non_commands_ignored() -> None:
    """Comments without @lychee return None."""
    assert parse_command("nice PR!") is None
    assert parse_command("") is None
    assert parse_command("lychee tastes good") is None


# ---------------------------------------------------------------------------
# Regression — parametrized snapshot of parser behavior
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # Valid commands
        ("@lychee peel", ParsedCommand(command=Command.peel)),
        ("@lychee juice", ParsedCommand(command=Command.juice)),
        ("@lychee pit", ParsedCommand(command=Command.pit)),
        ("@lychee ripe?", ParsedCommand(command=Command.ripe)),
        # Case insensitivity
        ("@Lychee Peel", ParsedCommand(command=Command.peel)),
        ("@LYCHEE JUICE", ParsedCommand(command=Command.juice)),
        # Bare mention
        ("@lychee", UnknownCommand(raw_text="")),
        ("@lychee   ", UnknownCommand(raw_text="")),
        # Unknown commands
        ("@lychee foobar", UnknownCommand(raw_text="foobar")),
        ("@lychee help", UnknownCommand(raw_text="help")),
        # No mention
        ("just a regular comment", None),
        ("", None),
        # Mention in sentence
        ("hey @lychee peel this please", ParsedCommand(command=Command.peel)),
        # Trailing punctuation
        ("@lychee peel!", ParsedCommand(command=Command.peel)),
        ("@lychee pit.", ParsedCommand(command=Command.pit)),
        ("@lychee juice,", ParsedCommand(command=Command.juice)),
        # ripe? preserved
        ("@lychee ripe?", ParsedCommand(command=Command.ripe)),
        # Multiple mentions — first wins
        ("@lychee peel and @lychee juice", ParsedCommand(command=Command.peel)),
        # Whitespace
        ("  @lychee   pit  ", ParsedCommand(command=Command.pit)),
        # Code block
        ("`@lychee peel`", ParsedCommand(command=Command.peel)),
        # Blockquote
        ("> @lychee juice", ParsedCommand(command=Command.juice)),
        # Word boundary — no match
        ("@lychee-bot hello", None),
    ],
    ids=[
        "valid-peel",
        "valid-juice",
        "valid-pit",
        "valid-ripe",
        "case-mixed-peel",
        "case-upper-juice",
        "bare-mention",
        "bare-mention-trailing-spaces",
        "unknown-foobar",
        "unknown-help",
        "no-mention-text",
        "no-mention-empty",
        "mention-in-sentence",
        "trailing-bang",
        "trailing-dot",
        "trailing-comma",
        "ripe-question-mark",
        "multiple-mentions-first-wins",
        "whitespace-padding",
        "code-block",
        "blockquote",
        "word-boundary-no-match",
    ],
)
def test_parse_command_snapshot(body: str, expected: ParseResult) -> None:
    """Parametrized fixture locking parser behavior for all known edge cases."""
    assert parse_command(body) == expected
