"""Dedicated test suite for tone and length tuning behavior.

Validates that the three tone settings (balanced, concise, detailed) produce
observably different prompt instructions via ``build_system_prompt()``, that
tone composes correctly with the language setting, and that all prompt outputs
match their golden snapshots.
"""

from __future__ import annotations

from pathlib import Path

from lychee.config import LycheeConfig
from lychee.prompt import _TONE_INSTRUCTIONS, build_system_prompt

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Unit tests — _TONE_INSTRUCTIONS dictionary
# ---------------------------------------------------------------------------


class TestToneInstructionEntries:
    """Unit tests verifying the shape and content of _TONE_INSTRUCTIONS."""

    def test_tone_instructions_balanced_empty(self) -> None:
        """The 'balanced' entry is an empty string (no extra instructions)."""
        assert _TONE_INSTRUCTIONS["balanced"] == ""

    def test_tone_instructions_concise_nonempty(self) -> None:
        """The 'concise' entry is a non-empty string with instructions."""
        value = _TONE_INSTRUCTIONS["concise"]
        assert isinstance(value, str)
        assert len(value) > 0

    def test_tone_instructions_detailed_nonempty(self) -> None:
        """The 'detailed' entry is a non-empty string with instructions."""
        value = _TONE_INSTRUCTIONS["detailed"]
        assert isinstance(value, str)
        assert len(value) > 0

    def test_tone_instructions_all_keys_present(self) -> None:
        """All three tone values have entries in the mapping."""
        assert set(_TONE_INSTRUCTIONS.keys()) == {"balanced", "concise", "detailed"}


# ---------------------------------------------------------------------------
# Unit tests — system prompt tone sections
# ---------------------------------------------------------------------------


class TestSystemPromptToneSections:
    """Unit tests verifying tone sections appear (or not) in the system prompt."""

    def test_system_prompt_balanced_no_tone_section(self) -> None:
        """With tone='balanced', the system prompt has no Tone section header."""
        config = LycheeConfig()
        output = build_system_prompt(config)
        assert "## Tone" not in output

    def test_system_prompt_concise_has_tone_section(self) -> None:
        """With tone='concise', the system prompt contains concise instructions."""
        config = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        assert "## Tone" in output
        assert _TONE_INSTRUCTIONS["concise"] in output

    def test_system_prompt_detailed_has_tone_section(self) -> None:
        """With tone='detailed', the system prompt contains detailed instructions."""
        config = LycheeConfig(review={"tone": "detailed"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        assert "## Tone" in output
        assert _TONE_INSTRUCTIONS["detailed"] in output

    def test_system_prompt_concise_mentions_brevity(self) -> None:
        """The concise prompt contains keywords indicating brevity."""
        config = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        output = build_system_prompt(config).lower()
        brevity_keywords = {"concise", "brief", "short"}
        assert any(
            kw in output for kw in brevity_keywords
        ), f"Expected one of {brevity_keywords} in concise prompt"

    def test_system_prompt_detailed_mentions_thoroughness(self) -> None:
        """The detailed prompt contains keywords indicating thoroughness."""
        config = LycheeConfig(review={"tone": "detailed"})  # type: ignore[arg-type]
        output = build_system_prompt(config).lower()
        thorough_keywords = {"thorough", "detailed", "extensive"}
        assert any(
            kw in output for kw in thorough_keywords
        ), f"Expected one of {thorough_keywords} in detailed prompt"

    def test_tone_and_language_compose(self) -> None:
        """Tone='concise' + language='es' produces both sections in the prompt."""
        config = LycheeConfig(
            review={"tone": "concise", "language": "es"}  # type: ignore[arg-type]
        )
        output = build_system_prompt(config)
        assert "## Tone" in output
        assert _TONE_INSTRUCTIONS["concise"] in output
        assert "## Language" in output
        assert "in es" in output


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestAcceptanceTone:
    """Acceptance tests verifying that tone settings produce distinct prompts."""

    def test_accept_concise_vs_detailed_differ(self) -> None:
        """The system prompts for concise and detailed are structurally different."""
        config_concise = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        config_detailed = LycheeConfig(review={"tone": "detailed"})  # type: ignore[arg-type]
        prompt_concise = build_system_prompt(config_concise)
        prompt_detailed = build_system_prompt(config_detailed)
        assert prompt_concise != prompt_detailed

    def test_accept_concise_differs_from_balanced(self) -> None:
        """The concise prompt differs from the balanced (default) prompt."""
        config_balanced = LycheeConfig()
        config_concise = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        assert build_system_prompt(config_balanced) != build_system_prompt(config_concise)

    def test_accept_detailed_differs_from_balanced(self) -> None:
        """The detailed prompt differs from the balanced (default) prompt."""
        config_balanced = LycheeConfig()
        config_detailed = LycheeConfig(review={"tone": "detailed"})  # type: ignore[arg-type]
        assert build_system_prompt(config_balanced) != build_system_prompt(config_detailed)

    def test_accept_tone_propagates_to_prompt(self) -> None:
        """Tone values propagate through config to build_system_prompt output."""
        for tone_value in ("concise", "detailed"):
            config = LycheeConfig(review={"tone": tone_value})  # type: ignore[arg-type]
            output = build_system_prompt(config)
            assert (
                _TONE_INSTRUCTIONS[tone_value] in output
            ), f"Expected tone={tone_value} instructions in prompt"


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


class TestSanityTone:
    """Sanity tests verifying no regressions from tone changes."""

    def test_balanced_prompt_unchanged(self) -> None:
        """The balanced system prompt matches the baseline golden snapshot."""
        config = LycheeConfig()
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot, (
            "Balanced system prompt changed unexpectedly. "
            "Tone changes should not alter the default prompt."
        )


# ---------------------------------------------------------------------------
# Regression tests — golden snapshots
# ---------------------------------------------------------------------------


class TestRegressionSnapshots:
    """Golden snapshot tests locking the prompt output for each tone."""

    def test_system_prompt_snapshot_balanced(self) -> None:
        """Golden snapshot of the full system prompt with tone='balanced'."""
        config = LycheeConfig()
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot, (
            "Balanced prompt snapshot drifted. If intentional, regenerate "
            "tests/fixtures/system_prompt_snapshot.txt."
        )

    def test_system_prompt_snapshot_concise(self) -> None:
        """Golden snapshot of the full system prompt with tone='concise'."""
        config = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_concise_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot, (
            "Concise prompt snapshot drifted. If intentional, regenerate "
            "tests/fixtures/system_prompt_concise_snapshot.txt."
        )

    def test_system_prompt_snapshot_detailed(self) -> None:
        """Golden snapshot of the full system prompt with tone='detailed'."""
        config = LycheeConfig(review={"tone": "detailed"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_detailed_snapshot.txt").read_text(
            encoding="utf-8"
        )
        assert output == snapshot, (
            "Detailed prompt snapshot drifted. If intentional, regenerate "
            "tests/fixtures/system_prompt_detailed_snapshot.txt."
        )


# ---------------------------------------------------------------------------
# UI (prompt surface) snapshot tests
# ---------------------------------------------------------------------------


class TestUIPromptSnapshots:
    """Snapshot tests treating the prompt as a designed UI surface per tone."""

    def test_ui_prompt_balanced_snapshot(self) -> None:
        """Snapshot the balanced (default) system prompt surface."""
        config = LycheeConfig()
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot

    def test_ui_prompt_concise_snapshot(self) -> None:
        """Snapshot the concise system prompt sections."""
        config = LycheeConfig(review={"tone": "concise"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_concise_snapshot.txt").read_text(encoding="utf-8")
        assert output == snapshot

    def test_ui_prompt_detailed_snapshot(self) -> None:
        """Snapshot the detailed system prompt sections."""
        config = LycheeConfig(review={"tone": "detailed"})  # type: ignore[arg-type]
        output = build_system_prompt(config)
        snapshot = (FIXTURES_DIR / "system_prompt_detailed_snapshot.txt").read_text(
            encoding="utf-8"
        )
        assert output == snapshot
