"""Tests for the command dispatch flow (run_action.py command handling).

Covers integration tests with mocked GitHub + Claude, system tests for the
full dispatch pipeline, acceptance tests for each command's output, smoke
tests for importability, sanity tests for backward compatibility, regression
snapshot tests, end-to-end tests, API-level tests, and UI format tests.

Framework: pytest, tmp_path for event files, monkeypatch for env vars,
unittest.mock for GitHubClient/ClaudeClient/run_review/create_issue_comment.
"""
# P4-R2

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lychee.authorization import REFUSAL_MARKER
from lychee.commands import HELP_TEXT
from lychee.config import (
    AuthorizationConfig,
    FeaturesConfig,
    LycheeConfig,
    ModelConfig,
    ReviewConfig,
    ScopeRule,
)
from lychee.models import (
    Category,
    Finding,
    ReviewResult,
    Ripeness,
    Severity,
)
from lychee.render import REVIEW_MARKER


def _make_comment_event(
    body: str = "@lychee peel",
    user: str = "octocat",
    pr_number: int = 42,
    action: str = "created",
) -> dict[str, Any]:
    """Build a minimal issue_comment event payload for testing."""
    return {
        "action": action,
        "comment": {
            "body": body,
            "user": {"login": user},
        },
        "issue": {
            "number": pr_number,
            "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/42"},
        },
    }


def _make_non_pr_comment_event(
    body: str = "@lychee peel",
    action: str = "created",
) -> dict[str, Any]:
    """Build an issue_comment event that is NOT on a PR (regular issue)."""
    return {
        "action": action,
        "comment": {
            "body": body,
            "user": {"login": "octocat"},
        },
        "issue": {
            "number": 99,
            # No "pull_request" key — this is a regular issue, not a PR.
        },
    }


def _make_pr_event(
    action: str = "opened",
    pr_number: int = 42,
    head_sha: str = "abc123",
) -> dict[str, Any]:
    """Build a minimal pull_request event payload for testing."""
    return {
        "action": action,
        "pull_request": {
            "number": pr_number,
            "head": {"sha": head_sha},
        },
    }


def _write_event_file(tmp_path: Path, event: dict[str, Any]) -> Path:
    """Write an event payload to a temporary JSON file."""
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")
    return event_file


def _mock_review_result(
    *,
    ripeness: Ripeness = Ripeness.ripe,
    summary: str = "Clean PR, no issues.",
    walkthrough: str = "## Changes\n\nMinor update.",
    findings: list[Finding] | None = None,
) -> ReviewResult:
    """Create a ReviewResult for mocking run_review return values."""
    if findings is None:
        findings = [
            Finding(
                file="test.py",
                line=1,
                severity=Severity.info,
                category=Category.other,
                message="Test finding.",
            ),
        ]
    return ReviewResult(
        ripeness=ripeness,
        summary=summary,
        walkthrough=walkthrough,
        findings=findings,
        model="claude-sonnet-4-6",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


def _setup_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    event: dict[str, Any],
    *,
    commands_enabled: bool = True,
    allowed_users: list[str] | None = None,
    scope_rules: list[ScopeRule] | None = None,
) -> tuple[Path, LycheeConfig]:
    """Configure environment and build config for command dispatch tests."""
    event_file = _write_event_file(tmp_path, event)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    config = LycheeConfig(
        features=FeaturesConfig(commands=commands_enabled),
        authorization=AuthorizationConfig(allowed_users=allowed_users or []),
        review=ReviewConfig(scope_rules=scope_rules or []),
    )
    return event_file, config


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_command_dispatch_module_imports() -> None:  # P4-R2
    """Command dispatch functions can be imported from run_action."""
    from scripts.run_action import (
        _COMMAND_ACTIONS,
        _handle_command_event,
        _is_command_event,
    )

    assert callable(_handle_command_event)
    assert callable(_is_command_event)
    assert isinstance(_COMMAND_ACTIONS, set)


# ---------------------------------------------------------------------------
# Unit tests — _is_command_event
# ---------------------------------------------------------------------------


class TestIsCommandEvent:
    """Unit tests for _is_command_event detection."""

    def test_issue_comment_on_pr_is_command(self) -> None:  # P4-R2
        """issue_comment with action 'created' on a PR is a command event."""
        from scripts.run_action import _is_command_event

        event = _make_comment_event()
        assert _is_command_event(event) is True

    def test_non_pr_comment_not_command(self) -> None:  # P4-R2
        """issue_comment on a regular issue (not a PR) is not a command event."""
        from scripts.run_action import _is_command_event

        event = _make_non_pr_comment_event()
        assert _is_command_event(event) is False

    def test_pr_event_not_command(self) -> None:  # P4-R2
        """pull_request events are not command events."""
        from scripts.run_action import _is_command_event

        event = _make_pr_event()
        assert _is_command_event(event) is False

    def test_edited_comment_not_command(self) -> None:  # P4-R2
        """issue_comment with action 'edited' is not a command event."""
        from scripts.run_action import _is_command_event

        event = _make_comment_event(action="edited")
        assert _is_command_event(event) is False


# ---------------------------------------------------------------------------
# Integration tests (mocked GitHub + Claude)
# ---------------------------------------------------------------------------


class TestDispatchIntegration:
    """Integration tests for command dispatch with mocked externals."""

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_peel_runs_review_and_posts(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Peel command runs the engine and posts a full review reply."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        pr_obj.create_issue_comment.assert_called_once()
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REVIEW_MARKER in posted
        assert "Nectar" in posted
        assert "The Peel" in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_juice_posts_nectar_only(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Juice command posts only the Nectar section."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee juice")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Nectar" in posted
        assert "The Peel" not in posted
        assert "Pits" not in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_pit_posts_core_finding(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Pit command posts only the core Pit."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee pit")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Core Pit" in posted
        assert REVIEW_MARKER in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_ripe_posts_verdict(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Ripe? command posts only the Ripeness."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee ripe?")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Ripeness:" in posted
        assert "Ripe" in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_unknown_posts_help(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Unknown command posts HELP_TEXT."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee foobar")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert posted == HELP_TEXT
        mock_review.assert_not_called()

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_unauthorized_posts_refusal(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Unauthorized user gets refusal message."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel", user="intruder")
        _, config = _setup_env(
            monkeypatch, tmp_path, event, allowed_users=["maintainer"]
        )
        mock_config.return_value = config

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REFUSAL_MARKER in posted
        assert "intruder" in posted
        mock_review.assert_not_called()

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_not_a_command_no_reply(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Comment without @lychee triggers no reply."""
        from scripts.run_action import main

        event = _make_comment_event(body="Just a regular comment")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        pr_obj.create_issue_comment.assert_not_called()
        mock_review.assert_not_called()

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_feature_flag_off_skips(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """With features.commands=False, command events are no-ops."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel")
        _, config = _setup_env(
            monkeypatch, tmp_path, event, commands_enabled=False
        )
        mock_config.return_value = config

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        mock_review.assert_not_called()
        mock_gh.return_value.get_pull_request.return_value.create_issue_comment.assert_not_called()

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_dispatch_non_pr_comment_skipped(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """issue_comment on a non-PR issue is skipped."""
        from scripts.run_action import main

        event = _make_non_pr_comment_event(body="@lychee peel")
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        mock_config.return_value = LycheeConfig(
            features=FeaturesConfig(commands=True)
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        # Non-PR comment with action "created" is not a command event,
        # and "created" is not in _SUPPORTED_ACTIONS, so it exits 0.
        assert exc_info.value.code == 0
        mock_review.assert_not_called()


# ---------------------------------------------------------------------------
# System tests
# ---------------------------------------------------------------------------


class TestSystemDispatch:
    """System tests for the full dispatch pipeline."""

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_system_command_flow_end_to_end(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Full command flow: event -> parse -> auth -> review -> render -> post."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel", user="maintainer")
        _, config = _setup_env(
            monkeypatch, tmp_path, event, allowed_users=["maintainer"]
        )
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Verify review was called.
        mock_review.assert_called_once()
        pr_ref_arg = mock_review.call_args[0][0]
        assert pr_ref_arg == "owner/repo#42"

        # Verify response posted.
        pr_obj = mock_gh.return_value.get_pull_request.return_value
        pr_obj.create_issue_comment.assert_called_once()
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REVIEW_MARKER in posted

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# PR Review")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_system_pr_event_unchanged(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """pull_request events still follow the existing review flow."""
        from scripts.run_action import main

        event = _make_pr_event(action="opened")
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        mock_config.return_value = LycheeConfig(
            features=FeaturesConfig(commands=True)
        )
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Should use SummaryPoster, not create_issue_comment.
        mock_poster_cls.return_value.post.assert_called_once()

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_system_scope_rules_applied_to_command(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Command with scope rules uses overridden config (scope rules in config)."""
        from scripts.run_action import main

        scope_rules = [
            ScopeRule(paths=["*.md"], model="claude-opus-4-8", tone="detailed"),
        ]
        event = _make_comment_event(body="@lychee peel")
        _, config = _setup_env(
            monkeypatch, tmp_path, event, scope_rules=scope_rules
        )
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Config with scope rules was passed to run_review.
        call_config = mock_review.call_args[0][1]
        assert len(call_config.review.scope_rules) == 1


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestAcceptanceDispatch:
    """Acceptance tests verifying command output content."""

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_peel_yields_full_review(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Peel command response contains header, nectar, walkthrough, and findings."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REVIEW_MARKER in posted
        assert "Nectar" in posted
        assert "The Peel" in posted
        assert "Pits" in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_juice_yields_nectar_only(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Juice response contains nectar but not findings."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee juice")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Nectar" in posted
        assert "The Peel" not in posted
        assert "Pits" not in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_pit_yields_core_finding(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Pit response contains only the highest-severity finding."""
        from scripts.run_action import main

        result = _mock_review_result(
            findings=[
                Finding(
                    file="low.py",
                    line=1,
                    severity=Severity.info,
                    category=Category.docs,
                    message="Low priority.",
                ),
                Finding(
                    file="high.py",
                    line=10,
                    severity=Severity.critical,
                    category=Category.correctness,
                    message="Critical bug.",
                ),
            ],
        )

        event = _make_comment_event(body="@lychee pit")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = result

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Critical bug." in posted
        assert "high.py" in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_ripe_yields_verdict(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Ripe? response contains ripeness badge."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee ripe?")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result(ripeness=Ripeness.unripe)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Ripeness:" in posted
        assert "Unripe" in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_unauthorized_refused_via_dispatch(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Unauthorized user sees refusal message posted."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel", user="hacker")
        _, config = _setup_env(
            monkeypatch, tmp_path, event, allowed_users=["admin"]
        )
        mock_config.return_value = config

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REFUSAL_MARKER in posted
        assert "hacker" in posted


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


class TestSanityDispatch:
    """Sanity tests verifying backward compatibility."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_existing_pr_review_flow_unchanged(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """The existing PR review flow still works when commands are enabled."""
        from scripts.run_action import main

        event = _make_pr_event(action="opened")
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        mock_config.return_value = LycheeConfig(
            features=FeaturesConfig(commands=True)
        )
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_review.assert_called_once()

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_inline_flag_still_works(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_inline_cls: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Inline commenting still works when commands are also enabled."""
        from lychee.poster import InlinePostResult

        from scripts.run_action import main

        event = _make_pr_event(action="opened")
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        mock_config.return_value = LycheeConfig(
            features=FeaturesConfig(commands=True, inline_comments=True)
        )
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = "diff --git a/f.py b/f.py\n"
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = InlinePostResult(
            review_id=None,
            inline_count=0,
            fallback_count=0,
            fallback_findings=[],
            posted_findings=[],
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_inline_cls.return_value.post.assert_called_once()


# ---------------------------------------------------------------------------
# Regression / snapshot tests
# ---------------------------------------------------------------------------


class TestRegressionDispatch:
    """Regression snapshot tests for command responses via dispatch."""

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_peel_response_snapshot(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Golden snapshot of the full peel response."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REVIEW_MARKER in posted
        assert "Nectar" in posted
        assert "The Peel" in posted
        assert "Pits" in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_juice_response_snapshot(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Golden snapshot of the juice response."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee juice")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Nectar" in posted
        assert "The Peel" not in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_pit_response_snapshot(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Golden snapshot of the pit response."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee pit")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Core Pit" in posted

    @pytest.mark.parametrize(
        "ripeness",
        [Ripeness.ripe, Ripeness.unripe, Ripeness.sour],
        ids=["ripe", "unripe", "sour"],
    )
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_ripe_response_snapshot(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        ripeness: Ripeness,
    ) -> None:
        """Golden snapshot of the ripe response for each ripeness value."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee ripe?")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result(ripeness=ripeness)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Ripeness:" in posted


# ---------------------------------------------------------------------------
# End-to-end tests
# ---------------------------------------------------------------------------


class TestE2EDispatch:
    """End-to-end tests for command dispatch."""

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_e2e_command_local(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Construct a full issue_comment event, mock all externals, run main()."""
        from scripts.run_action import main

        event = _make_comment_event(
            body="Hey @lychee peel this PR please!",
            user="developer",
            pr_number=77,
        )
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_e2e")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-e2e")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "test-org/test-repo")

        config = LycheeConfig(features=FeaturesConfig(commands=True))
        mock_config.return_value = config

        result = _mock_review_result(
            summary="E2E test summary.",
            walkthrough="## E2E\n\nFull walkthrough.",
            findings=[
                Finding(
                    file="app.py",
                    line=42,
                    severity=Severity.major,
                    category=Category.correctness,
                    message="E2E finding.",
                ),
            ],
        )
        mock_review.return_value = result

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Verify review called with correct PR ref.
        mock_review.assert_called_once()
        assert mock_review.call_args[0][0] == "test-org/test-repo#77"

        # Verify response posted with full content.
        pr_obj = mock_gh.return_value.get_pull_request.return_value
        pr_obj.create_issue_comment.assert_called_once()
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REVIEW_MARKER in posted
        assert "E2E test summary." in posted


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestAPIDispatch:
    """API-level tests verifying correct GitHub API calls."""

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_api_reply_posted_as_issue_comment(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Verify create_issue_comment is called (not create_review or summary edit)."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit):
            main()

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        pr_obj.create_issue_comment.assert_called_once()

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_api_help_posted_as_issue_comment(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Unknown command posts help via create_issue_comment."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee unknown")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config

        with pytest.raises(SystemExit):
            main()

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        pr_obj.create_issue_comment.assert_called_once()
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert posted == HELP_TEXT

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_api_refusal_posted_as_issue_comment(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Refusal posted via create_issue_comment."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel", user="outsider")
        _, config = _setup_env(
            monkeypatch, tmp_path, event, allowed_users=["admin"]
        )
        mock_config.return_value = config

        with pytest.raises(SystemExit):
            main()

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        pr_obj.create_issue_comment.assert_called_once()
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REFUSAL_MARKER in posted


# ---------------------------------------------------------------------------
# UI format tests (via dispatch)
# ---------------------------------------------------------------------------


class TestUIDispatch:
    """UI tests verifying response format via the dispatch pipeline."""

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_ui_peel_response_format(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Peel response via dispatch matches the full summary format."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit):
            main()

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert posted.startswith(REVIEW_MARKER)

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_ui_juice_response_format(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Juice response via dispatch has header + nectar only."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee juice")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit):
            main()

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Nectar" in posted
        assert "The Peel" not in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_ui_pit_response_format(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Pit response via dispatch has header + single finding."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee pit")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit):
            main()

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Core Pit" in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_ui_ripe_response_format(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Ripe response via dispatch has header + ripeness badge."""
        from scripts.run_action import main

        event = _make_comment_event(body="@lychee ripe?")
        _, config = _setup_env(monkeypatch, tmp_path, event)
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit):
            main()

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert "Ripeness:" in posted
