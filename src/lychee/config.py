"""Configuration loading and validation for Lychee."""

from pathlib import Path

import pydantic


class LycheeConfig(pydantic.BaseModel):
    """Typed configuration object parsed from .lychee.yml."""

    ...


def load_config(path: Path | None = None) -> LycheeConfig:
    """Load and validate .lychee.yml from the given path or the current directory."""
    raise NotImplementedError("load_config not implemented")
