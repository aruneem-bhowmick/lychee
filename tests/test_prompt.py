"""Unit, acceptance, regression, and snapshot tests for lychee.prompt.

Validates that the prompt builder produces deterministic, well-formed
Anthropic Messages API payloads with the correct persona, rubric,
severity/ripeness definitions, and tool schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lychee.config import LycheeConfig
from lychee.context import ReviewContext
from lychee.models import ReviewResult
from lychee.prompt import (
    build_messages,
    build_system_prompt,
    build_system_prompt_blocks,
    build_user_message,
    get_tools,
)

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_config() -> LycheeConfig:
    """Return a default LycheeConfig for deterministic testing."""
    return LycheeConfig()


@pytest.fixture()
def fixture_context() -> ReviewContext:
    """Deterministic ReviewContext matching the golden user_message_snapshot."""
    return ReviewContext(
        pr_number=42,
        pr_title="Add utility functions",
        pr_body="This PR adds utility functions.",
        pr_author="octocat",
        base_ref="main",
        head_ref="feat/utils",
        head_sha="abc123def456",
        repo_full_name="owner/repo",
        diff="diff --git a/f.py b/f.py\n+hello\n",
        changed_files=[
            {
                "filename": "src/utils.py",
                "status": "added",
                "additions": 10,
                "deletions": 0,
                "patch": "@@ -0,0 +1,10 @@\n+code here",
                "content_at_head": "# utils\ndef helper(): pass\n",
                "previous_filename": None,
            }
        ],
        commit_messages=["Add utility functions"],
        conventions=None,
    )


@pytest.fixture()
def context_empty_commits() -> ReviewContext:
    """ReviewContext with an empty commit_messages list."""
    return ReviewContext(
        pr_number=1,
        pr_title="Empty commits",
        pr_body="No commits.",
        pr_author="bot",
        base_ref="main",
        head_ref="fix/empty",
        head_sha="000000",
        repo_full_name="owner/repo",
        diff="",
        changed_files=[],
        commit_messages=[],
        conventions=None,
    )


@pytest.fixture()
def context_binary_file() -> ReviewContext:
    """ReviewContext with a file whose content_at_head is None."""
    return ReviewContext(
        pr_number=2,
        pr_title="Binary file PR",
        pr_body="Adds a binary file.",
        pr_author="dev",
        base_ref="main",
        head_ref="feat/binary",
        head_sha="aaa111",
        repo_full_name="owner/repo",
        diff="diff --git a/image.png b/image.png\n",
        changed_files=[
            {
                "filename": "image.png",
                "status": "added",
                "additions": 0,
                "deletions": 0,
                "patch": None,
                "content_at_head": None,
                "previous_filename": None,
            }
        ],
        commit_messages=["Add image"],
        conventions=None,
    )


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


class TestSmoke:
    """Verify that all public prompt functions import and are callable."""

    def test_prompt_module_imports(self) -> None:
        """All public functions import cleanly from lychee.prompt."""
        from lychee.prompt import (
            build_messages,
            build_system_prompt,
            build_system_prompt_blocks,
            build_user_message,
            get_tools,
        )

        assert callable(build_messages)
        assert callable(build_system_prompt)
        assert callable(build_system_prompt_blocks)
        assert callable(build_user_message)
        assert callable(get_tools)

    def test_build_system_prompt_blocks_importable(self) -> None:
        """build_system_prompt_blocks is importable and callable."""
        from lychee.prompt import build_system_prompt_blocks

        assert callable(build_system_prompt_blocks)


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


class TestSanity:
    """Basic sanity checks: functions return non-empty results."""

    def test_minimal_prompt_builds(self, default_config: LycheeConfig) -> None:
        """build_system_prompt returns a non-empty string."""
        result = build_system_prompt(default_config)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_minimal_messages_builds(
        self, context_empty_commits: ReviewContext, default_config: LycheeConfig
    ) -> None:
        """build_messages returns a non-empty list for a minimal context."""
        result = build_messages(context_empty_commits, default_config)
        assert isinstance(result, list)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Unit tests — build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    """Unit tests for the system prompt assembly."""

    def test_contains_persona(self, default_config: LycheeConfig) -> None:
        """The system prompt includes the reviewer persona description."""
        output = build_system_prompt(default_config)
        assert "tough shell, sweet flesh" in output

    def test_contains_rubric(self, default_config: LycheeConfig) -> None:
        """The system prompt includes all seven review categories."""
        output = build_system_prompt(default_config)
        for category in [
            "correctness",
            "security",
            "performance",
            "tests",
            "style",
            "docs",
            "other",
        ]:
            assert category in output

    def test_contains_severity_definitions(self, default_config: LycheeConfig) -> None:
        """The system prompt defines all four severity levels."""
        output = build_system_prompt(default_config)
        for severity in ["critical", "major", "minor", "info"]:
            assert f"**{severity}**" in output

    def test_contains_ripeness_definitions(self, default_config: LycheeConfig) -> None:
        """The system prompt defines all three ripeness verdicts."""
        output = build_system_prompt(default_config)
        for ripeness in ["ripe", "unripe", "sour"]:
            assert f"**{ripeness}**" in output

    def test_contains_tool_instruction(self, default_config: LycheeConfig) -> None:
        """The system prompt instructs the model to call submit_review."""
        output = build_system_prompt(default_config)
        assert "submit_review" in output

    def test_with_conventions(self, default_config: LycheeConfig) -> None:
        """Conventions string is included in the system prompt when provided."""
        conventions = "Use 4-space indentation.\nPrefer f-strings."
        output = build_system_prompt(default_config, conventions=conventions)
        assert "Project Conventions" in output
        assert "Use 4-space indentation." in output
        assert "Prefer f-strings." in output

    def test_without_conventions(self, default_config: LycheeConfig) -> None:
        """Conventions section is absent when conventions is None."""
        output = build_system_prompt(default_config, conventions=None)
        assert "Project Conventions" not in output

    def test_empty_conventions_omitted(self, default_config: LycheeConfig) -> None:
        """Conventions section is omitted when conventions is an empty string."""
        output = build_system_prompt(default_config, conventions="")
        assert "Project Conventions" not in output


# ---------------------------------------------------------------------------
# Unit tests — build_system_prompt_blocks
# ---------------------------------------------------------------------------


class TestBuildSystemPromptBlocks:
    """Unit tests for the cacheable system prompt block builder."""

    def test_returns_list(self, default_config: LycheeConfig) -> None:
        """build_system_prompt_blocks returns a list."""
        result = build_system_prompt_blocks(default_config)
        assert isinstance(result, list)

    def test_single_block(self, default_config: LycheeConfig) -> None:
        """The result contains exactly one content block."""
        result = build_system_prompt_blocks(default_config)
        assert len(result) == 1

    def test_block_structure(self, default_config: LycheeConfig) -> None:
        """The block has type, text, and cache_control keys."""
        block = build_system_prompt_blocks(default_config)[0]
        assert block["type"] == "text"
        assert isinstance(block["text"], str)
        assert "cache_control" in block

    def test_cache_control(self, default_config: LycheeConfig) -> None:
        """cache_control is set to ephemeral."""
        block = build_system_prompt_blocks(default_config)[0]
        assert block["cache_control"] == {"type": "ephemeral"}

    def test_text_matches_string(self, default_config: LycheeConfig) -> None:
        """The block text matches the output of build_system_prompt."""
        string_prompt = build_system_prompt(default_config)
        block_prompt = build_system_prompt_blocks(default_config)[0]["text"]
        assert block_prompt == string_prompt

    def test_with_conventions(self, default_config: LycheeConfig) -> None:
        """Conventions are included in block text when provided."""
        conventions = "Use 4-space indentation."
        result = build_system_prompt_blocks(default_config, conventions=conventions)
        assert "Use 4-space indentation." in result[0]["text"]
        assert "Project Conventions" in result[0]["text"]

    def test_without_conventions(self, default_config: LycheeConfig) -> None:
        """Conventions section is absent from block text when None."""
        result = build_system_prompt_blocks(default_config, conventions=None)
        assert "Project Conventions" not in result[0]["text"]

    def test_exact_keys(self, default_config: LycheeConfig) -> None:
        """Each block contains only the expected keys (type, text, cache_control)."""
        block = build_system_prompt_blocks(default_config)[0]
        assert set(block.keys()) == {"type", "text", "cache_control"}

    def test_text_matches_with_conventions(self, default_config: LycheeConfig) -> None:
        """Block text with conventions matches build_system_prompt with conventions."""
        conventions = "Prefer f-strings over format()."
        string_prompt = build_system_prompt(default_config, conventions=conventions)
        block_prompt = build_system_prompt_blocks(default_config, conventions=conventions)[0][
            "text"
        ]
        assert block_prompt == string_prompt


# ---------------------------------------------------------------------------
# Unit tests — build_user_message
# ---------------------------------------------------------------------------


class TestBuildUserMessage:
    """Unit tests for user message construction."""

    def test_contains_title(self, fixture_context: ReviewContext) -> None:
        """The user message includes the PR title."""
        output = build_user_message(fixture_context)
        assert fixture_context.pr_title in output

    def test_contains_author(self, fixture_context: ReviewContext) -> None:
        """The user message includes the PR author."""
        output = build_user_message(fixture_context)
        assert fixture_context.pr_author in output

    def test_contains_diff(self, fixture_context: ReviewContext) -> None:
        """The user message includes the diff in a diff code block."""
        output = build_user_message(fixture_context)
        assert "```diff" in output
        assert "+hello" in output

    def test_contains_commit_messages(self, fixture_context: ReviewContext) -> None:
        """The user message lists the commit messages."""
        output = build_user_message(fixture_context)
        assert "Add utility functions" in output
        assert "1. " in output

    def test_empty_commits(self, context_empty_commits: ReviewContext) -> None:
        """Empty commit list produces a 'no commit messages' placeholder."""
        output = build_user_message(context_empty_commits)
        assert "No commit messages available." in output

    def test_contains_changed_files(self, fixture_context: ReviewContext) -> None:
        """Changed file content appears under a file heading."""
        output = build_user_message(fixture_context)
        assert "### src/utils.py" in output
        assert "def helper(): pass" in output

    def test_empty_files(self, context_empty_commits: ReviewContext) -> None:
        """No changed files produces a 'no changed files' placeholder."""
        output = build_user_message(context_empty_commits)
        assert "No changed files." in output

    def test_binary_file_placeholder(self, context_binary_file: ReviewContext) -> None:
        """A file with None content shows the binary/deleted placeholder."""
        output = build_user_message(context_binary_file)
        assert "### image.png" in output
        assert "*Binary, deleted, or too large to display.*" in output

    def test_contains_base_head_refs(self, fixture_context: ReviewContext) -> None:
        """The user message includes base and head ref information."""
        output = build_user_message(fixture_context)
        assert "main" in output
        assert "feat/utils" in output

    def test_none_pr_body(self) -> None:
        """A None PR body does not produce 'None' in the message."""
        ctx = ReviewContext(
            pr_number=99,
            pr_title="No body",
            pr_body=None,
            pr_author="user",
            base_ref="main",
            head_ref="fix/x",
            head_sha="fff",
            repo_full_name="o/r",
            diff="",
            changed_files=[],
            commit_messages=[],
            conventions=None,
        )
        output = build_user_message(ctx)
        assert "None" not in output


# ---------------------------------------------------------------------------
# Unit tests — build_messages
# ---------------------------------------------------------------------------


class TestBuildMessages:
    """Unit tests for the Messages API message list."""

    def test_returns_user_role(
        self, fixture_context: ReviewContext, default_config: LycheeConfig
    ) -> None:
        """The returned list has one dict with role 'user'."""
        msgs = build_messages(fixture_context, default_config)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert "content" in msgs[0]


# ---------------------------------------------------------------------------
# Unit tests — get_tools
# ---------------------------------------------------------------------------


class TestGetTools:
    """Unit tests for the tool schema accessor."""

    def test_returns_submit_review(self) -> None:
        """The returned list has one tool named submit_review."""
        tools = get_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "submit_review"

    def test_schema_matches_model(self) -> None:
        """get_tools()[0] equals ReviewResult.to_tool_schema()."""
        tools = get_tools()
        assert tools[0] == ReviewResult.to_tool_schema()


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Verify that prompt functions produce identical output on repeated calls."""

    def test_deterministic_system_prompt(self, default_config: LycheeConfig) -> None:
        """Calling build_system_prompt twice with the same inputs produces equal strings."""
        a = build_system_prompt(default_config)
        b = build_system_prompt(default_config)
        assert a == b

    def test_deterministic_system_prompt_blocks(self, default_config: LycheeConfig) -> None:
        """Calling build_system_prompt_blocks twice with the same inputs produces equal lists."""
        a = build_system_prompt_blocks(default_config)
        b = build_system_prompt_blocks(default_config)
        assert a == b

    def test_deterministic_user_message(self, fixture_context: ReviewContext) -> None:
        """Calling build_user_message twice with the same context produces equal strings."""
        a = build_user_message(fixture_context)
        b = build_user_message(fixture_context)
        assert a == b


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestAcceptance:
    """Acceptance criteria: well-formed output, persona present, schema correct."""

    def test_well_formed_messages(
        self, fixture_context: ReviewContext, default_config: LycheeConfig
    ) -> None:
        """Output is a list of dicts with 'role' and 'content' keys."""
        msgs = build_messages(fixture_context, default_config)
        assert isinstance(msgs, list)
        for msg in msgs:
            assert isinstance(msg, dict)
            assert "role" in msg
            assert "content" in msg

    def test_persona_rubric_present(self, default_config: LycheeConfig) -> None:
        """The persona description and review rubric are present in the system prompt."""
        output = build_system_prompt(default_config)
        assert "tough shell, sweet flesh" in output
        assert "Review Rubric" in output

    def test_tool_schema_equals_contract(self) -> None:
        """The tool schema returned by get_tools matches ReviewResult.to_tool_schema()."""
        tools = get_tools()
        expected = ReviewResult.to_tool_schema()
        assert tools == [expected]

    def test_prompt_snapshot_stable(
        self, fixture_context: ReviewContext, default_config: LycheeConfig
    ) -> None:
        """For a fixed context, the user message matches its golden snapshot."""
        output = build_user_message(fixture_context)
        snapshot = (FIXTURES_DIR / "user_message_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot

    def test_repeated_blocks_calls_identical(self, default_config: LycheeConfig) -> None:
        """Repeated calls to build_system_prompt_blocks return identical lists."""
        first = build_system_prompt_blocks(default_config)
        second = build_system_prompt_blocks(default_config)
        assert first == second

    def test_same_config_conventions_sharing(self, default_config: LycheeConfig) -> None:
        """Same config and conventions produce identical blocks across calls."""
        conventions = "Always use type hints."
        a = build_system_prompt_blocks(default_config, conventions=conventions)
        b = build_system_prompt_blocks(default_config, conventions=conventions)
        assert a == b


# ---------------------------------------------------------------------------
# Regression tests — golden snapshots
# ---------------------------------------------------------------------------


class TestGoldenSnapshots:
    """Compare prompt output against committed golden snapshots."""

    def test_system_prompt_golden(self, default_config: LycheeConfig) -> None:
        """build_system_prompt(default_config) matches the golden snapshot exactly."""
        output = build_system_prompt(default_config)
        snapshot = (FIXTURES_DIR / "system_prompt_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot, (
            "System prompt changed. If intentional, regenerate "
            "tests/fixtures/system_prompt_snapshot.txt."
        )

    def test_user_message_golden(self, fixture_context: ReviewContext) -> None:
        """build_user_message(fixture_context) matches the golden snapshot exactly."""
        output = build_user_message(fixture_context)
        snapshot = (FIXTURES_DIR / "user_message_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot, (
            "User message changed. If intentional, regenerate "
            "tests/fixtures/user_message_snapshot.txt."
        )

    def test_system_prompt_blocks_golden(self, default_config: LycheeConfig) -> None:
        """build_system_prompt_blocks(default_config) matches the golden JSON snapshot."""
        output = build_system_prompt_blocks(default_config)
        snapshot = json.loads(
            (FIXTURES_DIR / "system_prompt_blocks_snapshot.json").read_text(encoding="utf-8")
        )
        assert output == snapshot, (
            "System prompt blocks changed. If intentional, regenerate "
            "tests/fixtures/system_prompt_blocks_snapshot.json."
        )

    def test_string_snapshot_unchanged(self, default_config: LycheeConfig) -> None:
        """build_system_prompt still matches its snapshot after blocks were added."""
        output = build_system_prompt(default_config)
        snapshot = (FIXTURES_DIR / "system_prompt_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot


# ---------------------------------------------------------------------------
# UI (prompt surface) snapshot tests
# ---------------------------------------------------------------------------


class TestPromptSurface:
    """Snapshot tests treating the prompt as a designed UI surface."""

    def test_system_prompt_snapshot(self, default_config: LycheeConfig) -> None:
        """Golden snapshot of the system prompt (the review UI surface)."""
        output = build_system_prompt(default_config)
        snapshot = (FIXTURES_DIR / "system_prompt_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot

    def test_user_message_snapshot(self, fixture_context: ReviewContext) -> None:
        """Golden snapshot of the user message for a known context."""
        output = build_user_message(fixture_context)
        snapshot = (FIXTURES_DIR / "user_message_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot


# ---------------------------------------------------------------------------
# Tone and language tests
# ---------------------------------------------------------------------------


class TestToneAndLanguage:
    """Tests for tone and language config-driven prompt sections."""

    def test_build_system_prompt_tone_balanced(self) -> None:
        """Default tone (balanced) produces no '## Tone' section."""
        config = LycheeConfig()
        output = build_system_prompt(config)
        assert "## Tone" not in output

    def test_build_system_prompt_tone_concise(self) -> None:
        """Concise tone appends the concise instruction."""
        config = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        assert "## Tone" in output
        assert "Be concise" in output
        assert "Keep the Nectar under 3 sentences" in output

    def test_build_system_prompt_tone_detailed(self) -> None:
        """Detailed tone appends the detailed instruction."""
        config = LycheeConfig(review={"tone": "detailed"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        assert "## Tone" in output
        assert "Be thorough and detailed" in output
        assert "Walk through each file" in output

    def test_build_system_prompt_language_en(self) -> None:
        """Default language (en) produces no '## Language' section."""
        config = LycheeConfig()
        output = build_system_prompt(config)
        assert "## Language" not in output

    def test_build_system_prompt_language_non_en(self) -> None:
        """Non-English language appends the language instruction."""
        config = LycheeConfig(review={"language": "ja"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        assert "## Language" in output
        assert "in ja" in output

    def test_build_system_prompt_tone_and_language(self) -> None:
        """Both tone and language can be set together."""
        config = LycheeConfig(review={"tone": "concise", "language": "fr"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        assert "## Tone" in output
        assert "Be concise" in output
        assert "## Language" in output
        assert "in fr" in output

    def test_build_system_prompt_blocks_includes_tone(self) -> None:
        """build_system_prompt_blocks reflects tone in the block text."""
        config = LycheeConfig(review={"tone": "detailed"})  # type: ignore[arg-type]
        blocks = build_system_prompt_blocks(config)
        assert "## Tone" in blocks[0]["text"]
        assert "Be thorough and detailed" in blocks[0]["text"]

    def test_accept_tone_reflected(self) -> None:
        """Acceptance: concise config produces concise instruction in prompt."""
        config = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        assert "Omit the walkthrough if the PR is straightforward" in output

    def test_accept_language_reflected(self) -> None:
        """Acceptance: language='ja' produces language instruction."""
        config = LycheeConfig(review={"language": "ja"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        assert "Write your entire review" in output
        assert "in ja" in output

    def test_system_prompt_with_tone_snapshot(self) -> None:
        """Regression: prompt with tone='concise' matches snapshot."""
        config = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_concise_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot, (
            "System prompt with tone=concise changed. If intentional, "
            "regenerate tests/fixtures/system_prompt_concise_snapshot.txt."
        )

    def test_default_config_prompt_unchanged(self) -> None:
        """Sanity: default config output is identical to baseline snapshot."""
        config = LycheeConfig()
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot
