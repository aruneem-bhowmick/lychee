"""PR comment poster — upserts the lychee review comment on a pull request."""


class SummaryPoster:
    """Upserts the lychee marker comment on a PR."""

    def __init__(self, github_client: object) -> None:
        """Initialise the poster with a GitHub client."""
        ...

    def post(self, pr_ref: str, comment_body: str) -> None:
        """Create or update the lychee review comment on a PR."""
        raise NotImplementedError("SummaryPoster.post not implemented")
