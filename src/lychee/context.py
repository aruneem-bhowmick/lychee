"""PR review context assembly — fetches and bundles all data needed for a review."""

import pydantic


class ReviewContext(pydantic.BaseModel):
    """All context assembled for a single PR review."""

    ...


def build_context(client: object, pr_ref: str, config: object) -> ReviewContext:
    """Fetch and assemble all PR context needed for a review."""
    ...
