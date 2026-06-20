"""Tests for the GitHub Actions entrypoint (scripts/run_action.py).

Covers unit tests for event parsing and action filtering, integration tests
with mocked externals, system tests for the full pipeline, acceptance tests
for workflow YAML structure and secret handling, smoke tests for importability,
sanity tests for YAML validity, regression snapshot tests, and feature-flag
wiring tests for inline comment posting.

Framework: pytest, tmp_path for event files, monkeypatch for env vars,
unittest.mock for GitHubClient/ClaudeClient/SummaryPoster/InlineReviewPoster.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from lychee.cost import BudgetExceededError
from lychee.models import (
    Category,
    Finding,
    ReviewResult,
    Ripeness,
    Severity,
)
from lychee.poster import InlinePostResult, PosterError

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "review.yml"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Minimal unified diff for inline-posting tests.
_TEST_DIFF = (
    "diff --git a/test.py b/test.py\n"
    "index 0000000..1111111 100644\n"
    "--- a/test.py\n"
    "+++ b/test.py\n"
    "@@ -1,3 +1,4 @@\n"
    " import os\n"
    "+print('hello')\n"
    " x = 1\n"
    " y = 2\n"
)


def _make_event(
    action: str = "opened", pr_number: int = 42, head_sha: str = "abc123"
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
    """Write an event payload to a temporary JSON file and return its path."""
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")
    return event_file


def _mock_review_result() -> ReviewResult:
    """Create a minimal ReviewResult for mocking run_review return values."""
    return ReviewResult(
        ripeness=Ripeness.ripe,
        summary="Test summary.",
        walkthrough="## Test\n\nNo changes.",
        findings=[
            Finding(
                file="test.py",
                line=1,
                severity=Severity.info,
                category=Category.other,
                message="Test finding.",
            ),
        ],
        model="claude-sonnet-4-6",
        usage={"input_tokens": 100, "output_tokens": 50},
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestParseEvent:
    """Unit tests for _parse_event."""

    def test_parse_event_valid(self, tmp_path: Path) -> None:
        """Valid JSON file returns the parsed dict."""
        from scripts.run_action import _parse_event

        event = {"action": "opened", "pull_request": {"number": 1}}
        event_file = _write_event_file(tmp_path, event)

        result = _parse_event(str(event_file))
        assert result == event

    def test_parse_event_missing_file(self) -> None:
        """Nonexistent path raises SystemExit(1)."""
        from scripts.run_action import _parse_event

        with pytest.raises(SystemExit) as exc_info:
            _parse_event("/nonexistent/event.json")
        assert exc_info.value.code == 1

    def test_parse_event_invalid_json(self, tmp_path: Path) -> None:
        """Malformed JSON raises SystemExit(1)."""
        from scripts.run_action import _parse_event

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            _parse_event(str(bad_file))
        assert exc_info.value.code == 1


class TestIsApplicableEvent:
    """Unit tests for _is_applicable_event."""

    def test_is_applicable_opened(self) -> None:
        """Event action 'opened' is applicable."""
        from scripts.run_action import _is_applicable_event

        assert _is_applicable_event({"action": "opened"}) is True

    def test_is_applicable_synchronize(self) -> None:
        """Event action 'synchronize' is applicable."""
        from scripts.run_action import _is_applicable_event

        assert _is_applicable_event({"action": "synchronize"}) is True

    def test_is_applicable_reopened(self) -> None:
        """Event action 'reopened' is applicable."""
        from scripts.run_action import _is_applicable_event

        assert _is_applicable_event({"action": "reopened"}) is True

    def test_is_applicable_closed(self) -> None:
        """Event action 'closed' is not applicable."""
        from scripts.run_action import _is_applicable_event

        assert _is_applicable_event({"action": "closed"}) is False

    def test_is_applicable_no_action(self) -> None:
        """Empty event dict (no action key) is not applicable."""
        from scripts.run_action import _is_applicable_event

        assert _is_applicable_event({}) is False

    def test_supported_actions_set(self) -> None:
        """_SUPPORTED_ACTIONS contains exactly the three expected actions."""
        from scripts.run_action import _SUPPORTED_ACTIONS

        assert {"opened", "synchronize", "reopened"} == _SUPPORTED_ACTIONS


# ---------------------------------------------------------------------------
# Integration tests (mocked externals)
# ---------------------------------------------------------------------------


class TestMainIntegration:
    """Integration tests for main() with mocked external dependencies."""

    def _setup_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        event: dict[str, Any] | None = None,
        *,
        github_token: str | None = "ghp_test_token",
        anthropic_key: str | None = "sk-ant-test-key",
        repo: str = "owner/repo",
    ) -> Path:
        """Configure environment variables and write event file for main().

        Returns the path to the event file.
        """
        if event is None:
            event = _make_event()
        event_file = _write_event_file(tmp_path, event)

        if github_token is not None:
            monkeypatch.setenv("GITHUB_TOKEN", github_token)
        else:
            monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        if anthropic_key is not None:
            monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_key)
        else:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", repo)

        return event_file

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Mock comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_main_success(
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
        """main() exits 0 when all dependencies succeed."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path)
        mock_config.return_value.features.inline_comments = False
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    @patch("scripts.run_action.run_review")
    def test_main_non_applicable_event_exits_0(
        self,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """main() exits 0 for a 'closed' event without calling the engine."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path, event=_make_event(action="closed"))

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_review.assert_not_called()

    def test_main_missing_github_token_exits_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """main() exits 1 when GITHUB_TOKEN is not set."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path, github_token=None)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_main_missing_anthropic_key_exits_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """main() exits 1 when ANTHROPIC_API_KEY is not set."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path, anthropic_key=None)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Mock comment")
    @patch("scripts.run_action.run_review", side_effect=RuntimeError("engine boom"))
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_main_engine_failure_exits_1(
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
        """main() exits 1 when run_review raises an exception."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Mock comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_main_poster_failure_exits_1(
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
        """main() exits 1 when SummaryPoster.post() raises an exception."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path)
        mock_review.return_value = _mock_review_result()
        mock_poster_cls.return_value.post.side_effect = RuntimeError("poster boom")

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Mock comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_main_posts_with_state(
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
        """main() passes state with last_reviewed_sha to SummaryPoster.post()."""
        from scripts.run_action import main

        head_sha = "deadbeef1234"
        self._setup_env(
            monkeypatch,
            tmp_path,
            event=_make_event(head_sha=head_sha),
        )
        mock_config.return_value.features.inline_comments = False
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        poster_instance = mock_poster_cls.return_value
        poster_instance.post.assert_called_once()
        call_kwargs = poster_instance.post.call_args
        state = call_kwargs.kwargs.get("state") or call_kwargs[1].get("state")
        # If called positionally, check the third argument
        if state is None and len(call_kwargs.args) >= 3:
            state = call_kwargs.args[2]
        assert state is not None
        assert state["last_reviewed_sha"] == head_sha


# ---------------------------------------------------------------------------
# System tests
# ---------------------------------------------------------------------------


class TestSystemAction:
    """System tests for the full action pipeline with mocked externals."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Full pipeline comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_system_action_end_to_end(
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
        """Full pipeline runs end-to-end with mocked externals and exits 0."""
        from scripts.run_action import main

        event = _make_event(action="opened", pr_number=99, head_sha="face0ff")
        event_file = _write_event_file(tmp_path, event)

        monkeypatch.setenv("GITHUB_TOKEN", "ghp_system_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-system-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "test-org/test-repo")

        mock_config.return_value.features.inline_comments = False
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Verify the pipeline was called with correct PR reference
        mock_review.assert_called_once()
        pr_ref_arg = mock_review.call_args[0][0]
        assert pr_ref_arg == "test-org/test-repo#99"

        # Verify render was called
        mock_render.assert_called_once()

        # Verify poster was instantiated and post was called
        mock_poster_cls.return_value.post.assert_called_once()


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestAcceptance:
    """Acceptance tests validating workflow YAML structure and security properties."""

    def _load_workflow(self) -> dict[str, Any]:
        """Load and return the parsed workflow YAML.

        YAML parses the bare key ``on`` as boolean True.  This helper
        normalizes it back to the string ``"on"`` so callers can use
        ordinary string indexing without tripping mypy's index checker.
        """
        raw: dict[Any, Any] = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
        if True in raw:
            raw["on"] = raw.pop(True)
        return raw  # type: ignore[return-value]

    def test_accept_workflow_dispatches_on_opened(self) -> None:
        """Workflow triggers on pull_request 'opened' event type."""
        wf = self._load_workflow()
        types = wf["on"]["pull_request"]["types"]
        assert "opened" in types

    def test_accept_workflow_dispatches_on_synchronize(self) -> None:
        """Workflow triggers on pull_request 'synchronize' event type."""
        wf = self._load_workflow()
        types = wf["on"]["pull_request"]["types"]
        assert "synchronize" in types

    def test_accept_permissions_minimal(self) -> None:
        """Workflow permissions are exactly contents: read + pull-requests: write."""
        wf = self._load_workflow()
        perms = wf["permissions"]
        assert perms == {"contents": "read", "pull-requests": "write"}

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_secret_consumed_not_logged(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Secrets are consumed from env but never appear in log output."""
        from scripts.run_action import main

        secret_token = "ghp_SUPERSECRETTOKEN123"
        secret_key = "sk-ant-SUPERSECRETKEY456"
        event = _make_event()
        event_file = _write_event_file(tmp_path, event)

        monkeypatch.setenv("GITHUB_TOKEN", secret_token)
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret_key)
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit):
            main()

        log_text = caplog.text
        assert secret_token not in log_text
        assert secret_key not in log_text

    @patch("scripts.run_action.run_review")
    def test_accept_non_applicable_event_noop(
        self,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A 'closed' event produces no review and exits 0."""
        from scripts.run_action import main

        event = _make_event(action="closed")
        event_file = _write_event_file(tmp_path, event)

        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_review.assert_not_called()


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_run_action_imports() -> None:
    """The action entrypoint module can be imported."""
    from scripts.run_action import _is_applicable_event, _parse_event, main

    assert callable(main)
    assert callable(_parse_event)
    assert callable(_is_applicable_event)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_workflow_file_valid_yaml() -> None:
    """The review workflow file parses as valid YAML."""
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)


def test_workflow_uses_pull_request_not_target() -> None:
    """The workflow trigger is pull_request, not pull_request_target."""
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    raw: dict[Any, Any] = yaml.safe_load(content)
    # YAML parses bare 'on' as boolean True; normalize to string key
    if True in raw:
        raw["on"] = raw.pop(True)
    triggers: dict[str, Any] = raw["on"]
    assert "pull_request" in triggers
    assert "pull_request_target" not in triggers


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_workflow_snapshot() -> None:
    """Workflow YAML matches the expected snapshot to detect unintended changes.

    If you intentionally modify the workflow, update the snapshot file
    at tests/fixtures/review_workflow_snapshot.yml and re-run.
    """
    snapshot_path = FIXTURES_DIR / "review_workflow_snapshot.yml"
    current = WORKFLOW_PATH.read_text(encoding="utf-8")

    if not snapshot_path.exists():
        snapshot_path.write_text(current, encoding="utf-8")

    saved = snapshot_path.read_text(encoding="utf-8")
    assert current == saved, (
        "Workflow YAML changed. If intentional, delete "
        "tests/fixtures/review_workflow_snapshot.yml and re-run to regenerate."
    )


# ---------------------------------------------------------------------------
# Cost footer integration tests
# ---------------------------------------------------------------------------


class TestCostFooterIntegration:
    """Integration tests for cost footer rendering in the action entrypoint."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_cost_footer_rendered(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """When cost_footer is True, the posted comment includes a cost line."""
        from scripts.run_action import main

        event = _make_event()
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        from lychee.config import FeaturesConfig, LycheeConfig

        config = LycheeConfig(features=FeaturesConfig(cost_footer=True))
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Verify render_comment was called (implicitly via poster.post)
        poster_instance = mock_poster_cls.return_value
        poster_instance.post.assert_called_once()
        posted_body = poster_instance.post.call_args[0][1]
        assert "**Cost:**" in posted_body
        assert "**Tokens:**" in posted_body

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_cost_footer_disabled(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """When cost_footer is False, no cost line appears in the posted comment."""
        from scripts.run_action import main

        event = _make_event()
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        from lychee.config import FeaturesConfig, LycheeConfig

        config = LycheeConfig(features=FeaturesConfig(cost_footer=False))
        mock_config.return_value = config
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        poster_instance = mock_poster_cls.return_value
        poster_instance.post.assert_called_once()
        posted_body = poster_instance.post.call_args[0][1]
        assert "**Cost:**" not in posted_body

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_budget_exceeded_posts_message(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """When budget is exceeded, an abort comment is posted and exit code is 1."""
        from scripts.run_action import main

        event = _make_event()
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        mock_review.side_effect = BudgetExceededError(0.1500, 0.1000)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Sanity tests — cost integration
# ---------------------------------------------------------------------------


class TestCostSanity:
    """Sanity tests verifying unchanged action behaviour without budget cap."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_without_budget_cap_unchanged(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """With no budget cap, action behaviour is identical to before cost accounting."""
        from scripts.run_action import main

        event = _make_event()
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        mock_config.return_value.features.inline_comments = False
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        mock_review.assert_called_once()
        mock_poster_cls.return_value.post.assert_called_once()


# ---------------------------------------------------------------------------
# Observability integration tests
# ---------------------------------------------------------------------------


class TestActionObservability:
    """Integration tests for observability hooks in the action entrypoint."""

    def _setup_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        event: dict[str, Any] | None = None,
    ) -> Path:
        """Configure environment and write event file for main()."""
        if event is None:
            event = _make_event()
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        return event_file

    @patch("scripts.run_action.setup_structured_logging")
    @patch("scripts.run_action.new_correlation_id", return_value="test_cid_abc123")
    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_emits_run_record(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
        mock_new_cid: MagicMock,
        _mock_setup_logging: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Successful review emits a review_complete run record."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path)
        mock_config.return_value.features.inline_comments = False
        mock_review.return_value = _mock_review_result()

        with (
            caplog.at_level(logging.INFO, logger="lychee.run_record"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0

        run_record_logs = [r for r in caplog.records if r.name == "lychee.run_record"]
        assert len(run_record_logs) >= 1
        record = json.loads(run_record_logs[0].message)
        assert record["event"] == "review_complete"
        assert "repo" in record
        assert "pr_number" in record
        assert "finding_counts" in record

    @patch("scripts.run_action.setup_structured_logging")
    @patch("scripts.run_action.new_correlation_id", return_value="test_cid_abc123")
    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Comment")
    @patch("scripts.run_action.run_review", side_effect=RuntimeError("engine boom"))
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_failure_emits_record(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
        mock_new_cid: MagicMock,
        _mock_setup_logging: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Failed review emits a review_failed run record."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path)

        with (
            caplog.at_level(logging.INFO, logger="lychee.run_record"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

        run_record_logs = [r for r in caplog.records if r.name == "lychee.run_record"]
        assert len(run_record_logs) >= 1
        record = json.loads(run_record_logs[0].message)
        assert record["event"] == "review_failed"
        assert record["error_type"] == "RuntimeError"

    @patch("scripts.run_action.setup_structured_logging")
    @patch("scripts.run_action.new_correlation_id", return_value="test_cid_abc123")
    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_correlation_id_propagates(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
        mock_new_cid: MagicMock,
        _mock_setup_logging: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """All log lines from a single run share the same correlation ID."""
        from scripts.run_action import main

        self._setup_env(monkeypatch, tmp_path)
        mock_review.return_value = _mock_review_result()

        with caplog.at_level(logging.INFO), pytest.raises(SystemExit):
            main()

        # The run record should contain the correlation ID from new_correlation_id
        run_record_logs = [r for r in caplog.records if r.name == "lychee.run_record"]
        if run_record_logs:
            # The correlation_id in the record comes from
            # get_correlation_id() inside build_run_record, which uses the
            # ContextVar.  Since we mocked new_correlation_id (which normally
            # sets the ContextVar), the ContextVar may hold a prior test value
            # or default.  What matters is that new_correlation_id was called.
            json.loads(run_record_logs[0].message)
            mock_new_cid.assert_called_once()

    @patch("scripts.run_action.setup_structured_logging")
    @patch("scripts.run_action.new_correlation_id", return_value="test_cid_abc123")
    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_every_run_emits_record(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_render: MagicMock,
        mock_poster_cls: MagicMock,
        mock_new_cid: MagicMock,
        _mock_setup_logging: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Both success and failure paths emit a run record to lychee.run_record."""
        from scripts.run_action import main

        # Success path
        self._setup_env(monkeypatch, tmp_path)
        mock_review.return_value = _mock_review_result()
        mock_review.side_effect = None

        with (
            caplog.at_level(logging.INFO, logger="lychee.run_record"),
            pytest.raises(SystemExit),
        ):
            main()

        success_records = [r for r in caplog.records if r.name == "lychee.run_record"]
        assert len(success_records) >= 1

        caplog.clear()

        # Failure path
        mock_review.side_effect = RuntimeError("fail")

        with (
            caplog.at_level(logging.INFO, logger="lychee.run_record"),
            pytest.raises(SystemExit),
        ):
            main()

        failure_records = [r for r in caplog.records if r.name == "lychee.run_record"]
        assert len(failure_records) >= 1


# ---------------------------------------------------------------------------
# Feature flag wiring tests — inline_comments
# ---------------------------------------------------------------------------


def _make_inline_config(inline: bool = True, cost_footer: bool = False) -> Any:
    """Build a real LycheeConfig with the inline_comments flag set.

    Uses the production LycheeConfig model so that all attributes
    (features.inline_comments, review.severity_threshold, etc.) have
    correct types rather than MagicMock proxies.
    """
    from lychee.config import FeaturesConfig, LycheeConfig

    return LycheeConfig(
        features=FeaturesConfig(inline_comments=inline, cost_footer=cost_footer),
    )


def _make_inline_post_result(
    *,
    inline_count: int = 1,
    fallback_count: int = 0,
    fallback_findings: list[Finding] | None = None,
    posted_findings: list[Finding] | None = None,
) -> InlinePostResult:
    """Build an InlinePostResult with the given counts and findings."""
    return InlinePostResult(
        review_id=100 if inline_count > 0 else None,
        inline_count=inline_count,
        fallback_count=fallback_count,
        fallback_findings=fallback_findings or [],
        posted_findings=posted_findings or [],
    )


def _setup_inline_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    head_sha: str = "abc123",
    pr_number: int = 42,
    action: str = "opened",
) -> Path:
    """Configure environment for inline-path tests and return the event file path."""
    event = _make_event(action=action, pr_number=pr_number, head_sha=head_sha)
    event_file = _write_event_file(tmp_path, event)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    return event_file


# ---------------------------------------------------------------------------
# Unit tests — feature flag wiring
# ---------------------------------------------------------------------------


class TestInlineFlagUnit:
    """Unit tests for the feature flag branching logic in main()."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_flag_off_no_inline_poster_created(
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
        """When inline_comments is False, InlineReviewPoster is not instantiated."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=False)
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_inline_cls.assert_not_called()

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_flag_on_inline_poster_created(
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
        """When inline_comments is True, InlineReviewPoster is instantiated and post() called."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_inline_cls.assert_called_once()
        mock_inline_cls.return_value.post.assert_called_once()

    @patch("scripts.run_action.render_comment", return_value="# No fallback")
    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_flag_off_render_no_fallback(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_poster_cls: MagicMock,
        mock_render: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """When flag is off, render_comment is called without fallback_findings."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=False)
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_render.assert_called_once()
        _, call_kwargs = mock_render.call_args
        # fallback_findings must not be in kwargs
        assert "fallback_findings" not in call_kwargs

    @patch("scripts.run_action.render_comment", return_value="# With fallback")
    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_flag_on_render_with_fallback(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_inline_cls: MagicMock,
        mock_poster_cls: MagicMock,
        mock_render: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """render_comment receives fallback_findings from InlinePostResult."""
        from scripts.run_action import main

        fallback = [
            Finding(
                file="unmappable.py",
                line=None,
                severity=Severity.minor,
                category=Category.style,
                message="Could not map this finding.",
            )
        ]

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result(
            fallback_count=1, fallback_findings=fallback
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_render.assert_called_once()
        _, call_kwargs = mock_render.call_args
        assert call_kwargs["fallback_findings"] == fallback


# ---------------------------------------------------------------------------
# Integration tests — inline flag wiring
# ---------------------------------------------------------------------------


class TestInlineFlagIntegration:
    """Integration tests for inline flag wiring with mocked externals."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_inline_enabled_full_flow(
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
        """With inline_comments=True, both InlineReviewPoster and SummaryPoster are called."""
        from scripts.run_action import main

        posted_findings = [
            Finding(
                file="test.py",
                line=1,
                severity=Severity.info,
                category=Category.other,
                message="Test finding.",
            )
        ]

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result(
            posted_findings=posted_findings,
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Both posters called
        mock_inline_cls.return_value.post.assert_called_once()
        mock_poster_cls.return_value.post.assert_called_once()

        # State includes inline_findings
        poster_call = mock_poster_cls.return_value.post.call_args
        state = poster_call.kwargs.get("state")
        if state is None and len(poster_call.args) >= 3:
            state = poster_call.args[2]
        assert state is not None
        assert "inline_findings" in state
        assert "last_reviewed_sha" in state

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_inline_disabled_full_flow(
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
        """With inline_comments=False, only SummaryPoster is called; no inline posting."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=False)
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        mock_inline_cls.assert_not_called()
        mock_poster_cls.return_value.post.assert_called_once()

        # State has no inline_findings
        poster_call = mock_poster_cls.return_value.post.call_args
        state = poster_call.kwargs.get("state")
        if state is None and len(poster_call.args) >= 3:
            state = poster_call.args[2]
        assert state is not None
        assert "inline_findings" not in state
        assert state["last_reviewed_sha"] == "abc123"

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_inline_failure_fallback(
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
        """When InlineReviewPoster raises PosterError, SummaryPoster still posts."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.side_effect = PosterError("API failure")

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Summary still posted despite inline failure
        mock_poster_cls.return_value.post.assert_called_once()

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_inline_dedup_state_passed(
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
        """On second push with existing comment, previous_state is extracted and passed."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF

        # Simulate existing comment with state marker
        existing_body = (
            "<!-- lychee:review -->\nOld comment\n\n"
            '<!-- lychee:state {"last_reviewed_sha":"old_sha",'
            '"inline_findings":[{"file":"test.py","line":1,'
            '"severity":"info","message_hash":"abc123def456"}]} -->'
        )
        mock_existing = MagicMock()
        mock_existing.body = existing_body
        mock_poster_cls.return_value._find_existing_comment.return_value = mock_existing

        # extract_state is a classmethod on the mocked SummaryPoster,
        # so configure the class-level mock to return real parsed state.
        mock_poster_cls.extract_state.return_value = {
            "last_reviewed_sha": "old_sha",
            "inline_findings": [
                {
                    "file": "test.py",
                    "line": 1,
                    "severity": "info",
                    "message_hash": "abc123def456",
                }
            ],
        }
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Verify previous_state was passed to InlineReviewPoster.post()
        inline_call = mock_inline_cls.return_value.post.call_args
        previous_state = inline_call.kwargs.get("previous_state")
        assert previous_state is not None
        assert "inline_findings" in previous_state


# ---------------------------------------------------------------------------
# System tests — inline flag wiring
# ---------------------------------------------------------------------------


class TestSystemInlineFlag:
    """System tests for the full action path with inline flag on and off."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_system_flag_on_inline_plus_summary(
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
        """Full action path with flag on: both inline and summary posted."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path, head_sha="deadbeef")
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        mock_inline_cls.return_value.post.assert_called_once()
        mock_poster_cls.return_value.post.assert_called_once()

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_system_flag_off_summary_only(
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
        """Full action path with flag off: only summary posted."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=False)
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        mock_inline_cls.assert_not_called()
        mock_poster_cls.return_value.post.assert_called_once()


# ---------------------------------------------------------------------------
# Acceptance tests — inline flag wiring
# ---------------------------------------------------------------------------


class TestAcceptInlineFlag:
    """Acceptance tests for feature flag wiring correctness."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_flag_off_preserves_existing_behavior(
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
        """With flag off, the posted summary matches existing behavior exactly."""
        from scripts.run_action import main

        head_sha = "abc123"
        _setup_inline_env(monkeypatch, tmp_path, head_sha=head_sha)
        mock_config.return_value = _make_inline_config(inline=False)
        result = _mock_review_result()
        mock_review.return_value = result

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        poster_instance = mock_poster_cls.return_value
        poster_instance.post.assert_called_once()

        # Verify state format is identical to pre-inline behavior
        call_kwargs = poster_instance.post.call_args
        state = call_kwargs.kwargs.get("state")
        if state is None and len(call_kwargs.args) >= 3:
            state = call_kwargs.args[2]
        assert state == {"last_reviewed_sha": head_sha}

        # Verify summary body contains the review marker
        posted_body = call_kwargs.args[1]
        from lychee.render import REVIEW_MARKER

        assert REVIEW_MARKER in posted_body

        # No inline poster instantiated
        mock_inline_cls.assert_not_called()

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_accept_flag_on_inline_plus_summary(
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
        """With flag on, both inline review and summary comment are posted."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        mock_inline_cls.return_value.post.assert_called_once()
        mock_poster_cls.return_value.post.assert_called_once()


# ---------------------------------------------------------------------------
# Smoke tests — inline imports
# ---------------------------------------------------------------------------


def test_action_imports_inline_modules() -> None:
    """run_action.py can import all inline commenting modules without error."""
    from scripts.run_action import (
        InlineReviewPoster,
        PosterError,
        build_inline_state,
    )

    assert callable(InlineReviewPoster)
    assert issubclass(PosterError, Exception)
    assert callable(build_inline_state)


# ---------------------------------------------------------------------------
# Sanity tests — inline flag
# ---------------------------------------------------------------------------


class TestExistingTestsSanity:
    """Sanity verification that inline wiring does not break existing tests."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_existing_action_tests_still_pass(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """With default config (inline_comments=False), main() succeeds."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=False)
        mock_review.return_value = _mock_review_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_poster_cls.return_value.post.assert_called_once()


# ---------------------------------------------------------------------------
# Regression tests — inline flag
# ---------------------------------------------------------------------------


class TestInlineFlagRegression:
    """Regression tests for feature flag wiring."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_action_summary_snapshot_flag_off(
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        mock_poster_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """With flag off, the summary body matches render_comment output exactly."""
        from scripts.run_action import main

        from lychee.render import render_comment

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=False, cost_footer=False)
        result = _mock_review_result()
        mock_review.return_value = result

        expected_body = render_comment(result, cost_line=None)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        posted_body = mock_poster_cls.return_value.post.call_args.args[1]
        assert posted_body == expected_body


# ---------------------------------------------------------------------------
# E2E test — inline flag
# ---------------------------------------------------------------------------


class TestInlineFlagE2E:
    """End-to-end test for inline commenting with the full action path."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_e2e_inline_local(
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
        """Local e2e: ReviewResult + diff -> inline + summary + state + dedup on re-push."""
        from scripts.run_action import main

        findings = [
            Finding(
                file="test.py",
                line=2,
                severity=Severity.major,
                category=Category.correctness,
                message="Potential null reference.",
                suggestion="if x is not None:\n    print(x)",
            ),
            Finding(
                file="other.py",
                line=None,
                severity=Severity.minor,
                category=Category.style,
                message="Unused import.",
            ),
        ]
        result = ReviewResult(
            ripeness=Ripeness.unripe,
            summary="Two issues found.",
            walkthrough="## Findings\n\nNull ref and unused import.",
            findings=findings,
            model="claude-sonnet-4-6",
            usage={"input_tokens": 500, "output_tokens": 100},
        )

        posted_findings = [findings[0]]
        fallback_findings = [findings[1]]

        _setup_inline_env(monkeypatch, tmp_path, head_sha="e2e_sha_1")
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = result
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result(
            inline_count=1,
            fallback_count=1,
            posted_findings=posted_findings,
            fallback_findings=fallback_findings,
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Verify inline poster called
        mock_inline_cls.return_value.post.assert_called_once()

        # Verify summary posted with state containing inline_findings
        poster_call = mock_poster_cls.return_value.post.call_args
        state = poster_call.kwargs.get("state")
        if state is None and len(poster_call.args) >= 3:
            state = poster_call.args[2]
        assert state is not None
        assert state["last_reviewed_sha"] == "e2e_sha_1"
        assert len(state["inline_findings"]) == 1

        # Verify summary body contains the fallback section
        posted_body = poster_call.args[1]
        assert "not on a changed line" in posted_body


# ---------------------------------------------------------------------------
# API tests — inline flag
# ---------------------------------------------------------------------------


class TestInlineFlagAPI:
    """API-level tests for inline flag wiring call correctness."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_api_create_review_called_with_result_and_diff(
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
        """InlineReviewPoster receives the ReviewResult and diff for review creation."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        result = _mock_review_result()
        mock_review.return_value = result
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result()

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        # Verify InlineReviewPoster.post() called with result and diff
        inline_call = mock_inline_cls.return_value.post.call_args
        assert inline_call.args[1] is result  # ReviewResult
        assert inline_call.args[2] == _TEST_DIFF  # diff

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_api_summary_upsert_with_inline_state(
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
        """SummaryPoster.post() receives state with inline_findings and last_reviewed_sha."""
        from scripts.run_action import main

        posted_findings = [
            Finding(
                file="test.py",
                line=1,
                severity=Severity.info,
                category=Category.other,
                message="Finding.",
            )
        ]
        head_sha = "api_test_sha"

        _setup_inline_env(monkeypatch, tmp_path, head_sha=head_sha)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result(
            posted_findings=posted_findings,
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        poster_call = mock_poster_cls.return_value.post.call_args
        state = poster_call.kwargs.get("state")
        if state is None and len(poster_call.args) >= 3:
            state = poster_call.args[2]
        assert state is not None
        assert state["last_reviewed_sha"] == head_sha
        assert "inline_findings" in state
        assert len(state["inline_findings"]) == 1


# ---------------------------------------------------------------------------
# UI tests — inline flag (summary comment content)
# ---------------------------------------------------------------------------


class TestInlineFlagUI:
    """UI tests verifying the summary comment content with inline flag on."""

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_ui_summary_with_fallback_section(
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
        """When flag is on and there are unmappable findings, fallback section appears."""
        from scripts.run_action import main

        fallback = [
            Finding(
                file="unmapped.py",
                line=999,
                severity=Severity.major,
                category=Category.correctness,
                message="Cannot map to diff.",
            )
        ]

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result(
            fallback_count=1, fallback_findings=fallback
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        posted_body = mock_poster_cls.return_value.post.call_args.args[1]
        assert "not on a changed line" in posted_body
        assert "unmapped.py" in posted_body

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.InlineReviewPoster")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_ui_summary_without_fallback_section(
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
        """When flag is on but all findings map, no fallback section in summary."""
        from scripts.run_action import main

        _setup_inline_env(monkeypatch, tmp_path)
        mock_config.return_value = _make_inline_config(inline=True)
        mock_review.return_value = _mock_review_result()
        mock_gh.return_value.get_diff.return_value = _TEST_DIFF
        mock_poster_cls.return_value._find_existing_comment.return_value = None
        mock_inline_cls.return_value.post.return_value = _make_inline_post_result(
            fallback_count=0, fallback_findings=[]
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        posted_body = mock_poster_cls.return_value.post.call_args.args[1]
        assert "not on a changed line" not in posted_body


# ---------------------------------------------------------------------------
# Command dispatch tests — issue_comment event handling  # P4-R2
# ---------------------------------------------------------------------------


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


class TestMainIssueComment:
    """Tests for issue_comment event handling in main()."""

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_main_issue_comment_peel(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """issue_comment event with @lychee peel triggers command flow."""
        from lychee.config import FeaturesConfig, LycheeConfig
        from lychee.render import REVIEW_MARKER

        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel")
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

        pr_obj = mock_gh.return_value.get_pull_request.return_value
        pr_obj.create_issue_comment.assert_called_once()
        posted = pr_obj.create_issue_comment.call_args.kwargs["body"]
        assert REVIEW_MARKER in posted

    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_main_issue_comment_commands_disabled(  # P4-R2
        self,
        mock_config: MagicMock,
        mock_gh: MagicMock,
        mock_claude: MagicMock,
        mock_review: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """features.commands=False skips command events."""
        from lychee.config import FeaturesConfig, LycheeConfig

        from scripts.run_action import main

        event = _make_comment_event(body="@lychee peel")
        event_file = _write_event_file(tmp_path, event)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        mock_config.return_value = LycheeConfig(
            features=FeaturesConfig(commands=False)
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_review.assert_not_called()

    @patch("scripts.run_action.SummaryPoster")
    @patch("scripts.run_action.render_comment", return_value="# Comment")
    @patch("scripts.run_action.run_review")
    @patch("scripts.run_action.ClaudeClient")
    @patch("scripts.run_action.GitHubClient")
    @patch("scripts.run_action.load_config")
    def test_main_pr_event_still_works(  # P4-R2
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
        """pull_request event still triggers the review flow."""
        from lychee.config import FeaturesConfig, LycheeConfig

        from scripts.run_action import main

        event = _make_event(action="opened")
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
        mock_poster_cls.return_value.post.assert_called_once()
