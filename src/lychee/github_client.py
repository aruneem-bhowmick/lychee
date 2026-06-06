"""GitHub API client wrapper for PR context retrieval."""


class GitHubClient:
    """Wraps PyGithub for PR context retrieval."""

    def __init__(self, token: str) -> None:
        """Initialise the client with a GitHub personal access token or Actions token."""
        ...
