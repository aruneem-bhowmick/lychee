"""Command parser for @lychee mentions in GitHub issue comments.

Extracts structured commands from comment bodies. The parser is pure logic
with no I/O dependencies — it receives a raw comment string and returns a
typed parse result indicating a valid command, an unknown command (prompting
a help reply), or no mention at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# Compiled pattern for detecting @lychee mentions (case-insensitive).
# Uses a negative lookbehind for word chars and a negative lookahead for word
# chars or hyphens, so "@lychee-bot" and "@lycheefoo" do not match.
_MENTION_PATTERN: re.Pattern[str] = re.compile(r"(?i)(?<!\w)@lychee(?![\w-])")

# Punctuation to strip from the token following @lychee, except '?' which is
# part of the valid command "ripe?".
_TRAILING_PUNCT: re.Pattern[str] = re.compile(r"[^\w?]+$")


class Command(StrEnum):
    """Recognized @lychee commands."""

    peel = "peel"
    juice = "juice"
    pit = "pit"
    ripe = "ripe?"


@dataclass(frozen=True)
class ParsedCommand:
    """A successfully parsed @lychee command."""

    command: Command


@dataclass(frozen=True)
class UnknownCommand:
    """An @lychee mention with an unrecognized command word."""

    raw_text: str  # the token after @lychee


# None means the comment does not mention @lychee at all.
ParseResult = ParsedCommand | UnknownCommand | None

# Set of valid command values for O(1) lookup during parsing.
_COMMAND_VALUES: frozenset[str] = frozenset(c.value for c in Command)


def is_lychee_mention(body: str) -> bool:
    """Return True if the body contains an @lychee mention."""
    return _MENTION_PATTERN.search(body) is not None


def parse_command(body: str) -> ParseResult:
    """Parse an @lychee command from a comment body.

    Returns ParsedCommand if a valid command is found,
    UnknownCommand if @lychee is mentioned with an invalid command,
    or None if the comment does not mention @lychee.
    """
    match = _MENTION_PATTERN.search(body)
    if match is None:
        return None

    # Extract the text after the @lychee mention.
    after = body[match.end() :]
    tokens = after.split()

    if not tokens:
        return UnknownCommand(raw_text="")

    token = tokens[0].lower()
    # Strip trailing punctuation (but preserve '?' for "ripe?").
    token = _TRAILING_PUNCT.sub("", token)

    if token in _COMMAND_VALUES:
        return ParsedCommand(command=Command(token))

    return UnknownCommand(raw_text=token)


HELP_TEXT: str = (
    "Available commands:\n"
    "- `@lychee peel` \u2014 full review (Nectar + Peel + Pits)\n"
    "- `@lychee juice` \u2014 Nectar (summary) only\n"
    "- `@lychee pit` \u2014 core Pit (highest-severity finding)\n"
    "- `@lychee ripe?` \u2014 Ripeness verdict only"
)
"""Help message posted when an unknown command is received."""
