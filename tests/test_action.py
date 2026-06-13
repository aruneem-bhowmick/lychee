"""Tests for the GitHub Actions entrypoint (scripts/run_action.py).

Covers unit tests for event parsing and action filtering, integration tests
with mocked externals, system tests for the full pipeline, acceptance tests
for workflow YAML structure and secret handling, smoke tests for importability,
sanity tests for YAML validity, and regression snapshot tests.

Framework: pytest, tmp_path for event files, monkeypatch for env vars,
unittest.mock for GitHubClient/ClaudeClient/SummaryPoster.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from lychee.models import (
    Category,
    Finding,
    ReviewResult,
    Ripeness,
    Severity,
)

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "review.yml"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
        mock_poster_cls.assert_called_once()
        mock_poster_cls.return_value.post.assert_called_once()


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestAcceptance:
    """Acceptance tests validating workflow YAML structure and security properties."""

    def _load_workflow(self) -> dict[str, Any]:
        """Load and return the parsed workflow YAML.

        YAML parses the bare key ``on`` as boolean True, so trigger
        configuration lives under ``wf[True]``.
        """
        return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def test_accept_workflow_dispatches_on_opened(self) -> None:
        """Workflow triggers on pull_request 'opened' event type."""
        wf = self._load_workflow()
        # YAML 'on' key is parsed as boolean True
        types = wf[True]["pull_request"]["types"]
        assert "opened" in types

    def test_accept_workflow_dispatches_on_synchronize(self) -> None:
        """Workflow triggers on pull_request 'synchronize' event type."""
        wf = self._load_workflow()
        types = wf[True]["pull_request"]["types"]
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
    parsed = yaml.safe_load(content)
    # YAML 'on' key is parsed as boolean True
    triggers = parsed[True]
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
