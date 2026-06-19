"""Tests for the authorization module (lychee.authorization).

Covers user authorization checks, open-access behavior, case-insensitive
matching, whitespace handling, refusal message formatting, marker validation,
config integration, and security regression tests.

Framework: pytest
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lychee.authorization import (
    REFUSAL_MARKER,
    format_refusal,
    is_authorized,
)
from lychee.config import LycheeConfig, load_config

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def test_authorization_module_imports() -> None:
    """All public names import cleanly from lychee.authorization."""  # P4-R5
    from lychee.authorization import (  # noqa: F401
        REFUSAL_MARKER,
        format_refusal,
        is_authorized,
    )


# ---------------------------------------------------------------------------
# Sanity test
# ---------------------------------------------------------------------------


def test_authorization_config_loads() -> None:
    """LycheeConfig with authorization section loads without error."""  # P4-R5
    config = LycheeConfig(
        authorization={"allowed_users": ["alice", "bob"]}  # type: ignore[arg-type]
    )
    assert config.authorization.allowed_users == ["alice", "bob"]


# ---------------------------------------------------------------------------
# Unit tests — is_authorized
# ---------------------------------------------------------------------------


def test_authorized_user_in_list() -> None:
    """A user present in allowed_users returns True."""  # P4-R5
    config = LycheeConfig(
        authorization={"allowed_users": ["alice", "bob"]}  # type: ignore[arg-type]
    )
    assert is_authorized("alice", config) is True


def test_unauthorized_user_not_in_list() -> None:
    """A user not in allowed_users returns False."""  # P4-R5
    config = LycheeConfig(
        authorization={"allowed_users": ["alice", "bob"]}  # type: ignore[arg-type]
    )
    assert is_authorized("charlie", config) is False


def test_open_access_empty_list() -> None:
    """Empty allowed_users returns True for any user."""  # P4-R5
    config = LycheeConfig()
    assert is_authorized("anyone", config) is True
    assert is_authorized("random-user", config) is True
    assert is_authorized("", config) is True


def test_case_insensitive_match() -> None:
    """'Alice' matches ['alice'] and vice versa."""  # P4-R5
    config = LycheeConfig(authorization={"allowed_users": ["alice"]})  # type: ignore[arg-type]
    assert is_authorized("Alice", config) is True
    assert is_authorized("ALICE", config) is True
    assert is_authorized("aLiCe", config) is True


def test_case_insensitive_config() -> None:
    """allowed_users: ['Alice'] matches user 'alice'."""  # P4-R5
    config = LycheeConfig(authorization={"allowed_users": ["Alice"]})  # type: ignore[arg-type]
    assert is_authorized("alice", config) is True


def test_multiple_allowed_users() -> None:
    """User matches one of several allowed users."""  # P4-R5
    config = LycheeConfig(
        authorization={"allowed_users": ["alice", "bob", "charlie"]}  # type: ignore[arg-type]
    )
    assert is_authorized("bob", config) is True
    assert is_authorized("charlie", config) is True
    assert is_authorized("dave", config) is False


def test_whitespace_in_login_handled() -> None:
    """Leading/trailing whitespace in login does not break the check."""  # P4-R5
    config = LycheeConfig(authorization={"allowed_users": ["alice"]})  # type: ignore[arg-type]
    assert is_authorized("  alice  ", config) is True
    assert is_authorized(" alice", config) is True
    assert is_authorized("alice ", config) is True


# ---------------------------------------------------------------------------
# Unit tests — format_refusal
# ---------------------------------------------------------------------------


def test_format_refusal_contains_username() -> None:
    """Refusal message includes the user's login."""  # P4-R5
    msg = format_refusal("charlie")
    assert "@charlie" in msg


def test_format_refusal_contains_config_hint() -> None:
    """Refusal message mentions .lychee.yml."""  # P4-R5
    msg = format_refusal("charlie")
    assert ".lychee.yml" in msg
    assert "authorization.allowed_users" in msg


def test_format_refusal_contains_marker() -> None:
    """Refusal message includes REFUSAL_MARKER."""  # P4-R5
    msg = format_refusal("charlie")
    assert REFUSAL_MARKER in msg


def test_format_refusal_does_not_contain_allowed_list() -> None:
    """Refusal message does not include the actual allowed-user list."""  # P4-R5
    msg = format_refusal("charlie")
    # The message should not reveal who IS allowed — only that the user isn't
    assert "alice" not in msg.lower()
    assert "bob" not in msg.lower()
    assert "allowed_users" in msg  # config key name is fine
    # Should not contain list-like syntax suggesting names
    assert "[" not in msg
    assert "]" not in msg


def test_refusal_marker_is_html_comment() -> None:
    """REFUSAL_MARKER is a valid HTML comment."""  # P4-R5
    assert REFUSAL_MARKER.startswith("<!--")
    assert REFUSAL_MARKER.endswith("-->")


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_authorization_with_loaded_config() -> None:
    """Load a .lychee.yml with authorization.allowed_users, then check is_authorized()."""  # P4-R5
    config = load_config(FIXTURES_DIR / "lychee_valid.yml")
    # lychee_valid.yml has allowed_users: [admin-user, bot-user]
    assert is_authorized("admin-user", config) is True
    assert is_authorized("bot-user", config) is True
    assert is_authorized("random-user", config) is False


def test_authorization_with_default_config() -> None:
    """load_config() default has open access."""  # P4-R5
    config = LycheeConfig()
    assert config.authorization.allowed_users == []
    assert is_authorized("anyone", config) is True


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_accept_unauthorized_refused() -> None:
    """An unauthorized user gets is_authorized() == False."""  # P4-R5
    config = LycheeConfig(authorization={"allowed_users": ["maintainer"]})  # type: ignore[arg-type]
    assert is_authorized("intruder", config) is False


def test_accept_permitted_proceeds() -> None:
    """An authorized user gets is_authorized() == True."""  # P4-R5
    config = LycheeConfig(authorization={"allowed_users": ["maintainer"]})  # type: ignore[arg-type]
    assert is_authorized("maintainer", config) is True


def test_accept_open_access_default() -> None:
    """With default config, all users are authorized."""  # P4-R5
    config = LycheeConfig()
    assert is_authorized("anyone", config) is True
    assert is_authorized("someone-else", config) is True


def test_accept_refusal_message_clear() -> None:
    """The refusal message is human-readable and non-hostile."""  # P4-R5
    msg = format_refusal("new-contributor")
    # Should address the user
    assert "@new-contributor" in msg
    # Should explain what happened
    assert "not on the authorized list" in msg
    # Should point to the config
    assert ".lychee.yml" in msg
    # Should not be hostile or accusatory
    hostile_words = ["denied", "forbidden", "rejected", "blocked", "banned", "error"]
    for word in hostile_words:
        assert word not in msg.lower(), f"Refusal contains hostile word: {word}"


# ---------------------------------------------------------------------------
# Regression — parametrized authorization snapshot
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user", "allowed_users", "expected"),
    [
        # Empty list — open access
        ("alice", [], True),
        ("bob", [], True),
        ("", [], True),
        # Single user — match
        ("alice", ["alice"], True),
        # Single user — no match
        ("bob", ["alice"], False),
        # Case variations
        ("Alice", ["alice"], True),
        ("ALICE", ["alice"], True),
        ("alice", ["ALICE"], True),
        ("alice", ["Alice"], True),
        # Multiple users
        ("bob", ["alice", "bob", "charlie"], True),
        ("dave", ["alice", "bob", "charlie"], False),
        # Whitespace
        (" alice ", ["alice"], True),
        ("alice", [" alice "], True),
    ],
    ids=[
        "open-access-alice",
        "open-access-bob",
        "open-access-empty-user",
        "single-match",
        "single-no-match",
        "case-user-capitalized",
        "case-user-upper",
        "case-config-upper",
        "case-config-capitalized",
        "multi-match",
        "multi-no-match",
        "whitespace-user",
        "whitespace-config",
    ],
)
def test_unauthorized_user_snapshot(user: str, allowed_users: list[str], expected: bool) -> None:
    """Parametrized fixture locking authorization behavior for all edge cases."""  # P4-R5
    config = LycheeConfig(authorization={"allowed_users": allowed_users})  # type: ignore[arg-type]
    assert is_authorized(user, config) is expected


# ---------------------------------------------------------------------------
# Regression — refusal message snapshot
# ---------------------------------------------------------------------------


def test_refusal_message_snapshot() -> None:
    """Golden snapshot of the refusal message for a fixed user."""  # P4-R5
    msg = format_refusal("test-user")
    expected = (
        "<!-- lychee:command-refused -->\n"
        "Hi @test-user, you're not on the authorized list for `@lychee` "
        "commands in this repository. A maintainer can add you to "
        "`authorization.allowed_users` in `.lychee.yml`."
    )
    assert msg == expected
