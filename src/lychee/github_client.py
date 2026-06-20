"""GitHub API client wrapper for PR context retrieval."""

from __future__ import annotations

import dataclasses
import fnmatch
import logging
from typing import TYPE_CHECKING

import github
import github.Auth
import httpx

if TYPE_CHECKING:
    from github.PullRequest import PullRequest

_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class PullRequestRef:
    """Parsed reference to a GitHub pull request (e.g. ``owner/repo#42``)."""

    owner: str
    repo: str
    number: int

    @classmethod
    def parse(cls, ref: str) -> PullRequestRef:
        """Parse a string like ``owner/repo#123`` into a PullRequestRef.

        Raises ``ValueError`` with a descriptive message on malformed input.
        """
        if "/" not in ref or "#" not in ref:
            raise ValueError(f"Invalid PR reference '{ref}': expected format 'owner/repo#number'")

        try:
            owner_repo, number_str = ref.rsplit("#", 1)
        except ValueError:
            raise ValueError(
                f"Invalid PR reference '{ref}': expected format 'owner/repo#number'"
            ) from None

        parts = owner_repo.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid PR reference '{ref}': expected format 'owner/repo#number'")

        try:
            number = int(number_str)
        except ValueError:
            raise ValueError(
                f"Invalid PR reference '{ref}': PR number must be an integer, got '{number_str}'"
            ) from None

        if number <= 0:
            raise ValueError(
                f"Invalid PR reference '{ref}': PR number must be a positive integer, got {number}"
            )

        return cls(owner=parts[0], repo=parts[1], number=number)

    @property
    def full_name(self) -> str:
        """Return ``owner/repo``."""
        return f"{self.owner}/{self.repo}"


@dataclasses.dataclass(frozen=True)
class ChangedFile:
    """A single file changed in a pull request."""

    filename: str
    status: str
    additions: int
    deletions: int
    patch: str | None
    content_at_head: str | None
    previous_filename: str | None = None


class GitHubClient:
    """Wraps PyGithub for PR context retrieval."""

    def __init__(self, token: str) -> None:
        """Initialise the client with a GitHub personal access token or Actions token."""
        self._github = github.Github(token)

    @classmethod
    def from_installation_token(cls, token: str) -> GitHubClient:
        """Create a GitHubClient authenticated with an installation access token.

        This factory is used by the GitHub App code path. The resulting client
        has the same API as one created with a personal access token.

        Args:
            token: A GitHub App installation access token.

        Returns:
            A configured GitHubClient instance.
        """
        instance = cls.__new__(cls)
        auth = github.Auth.Token(token)
        instance._github = github.Github(auth=auth)
        return instance

    def get_pull_request(self, ref: PullRequestRef) -> PullRequest:
        """Fetch a PullRequest object from GitHub.

        Args:
            ref: Parsed PR reference.

        Returns:
            A PyGithub PullRequest object.
        """
        repo = self._github.get_repo(ref.full_name)
        return repo.get_pull(ref.number)

    def get_diff(self, ref: PullRequestRef) -> str:
        """Fetch the unified diff for a pull request.

        Uses httpx with the GitHub diff media type to retrieve the raw diff text.
        """
        url = f"https://api.github.com/repos/{ref.full_name}/pulls/{ref.number}"
        token = self._github.requester._Requester__authorizationHeader  # type: ignore[attr-defined]
        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3.diff",
        }
        if token:
            headers["Authorization"] = token
        response = httpx.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def get_changed_files(
        self,
        pr: PullRequest,
        *,
        max_files: int = 50,
        max_file_bytes: int = 102_400,
        ignore_globs: list[str] | None = None,
    ) -> list[ChangedFile]:
        """Collect changed files from a pull request.

        Args:
            pr: PyGithub PullRequest object.
            max_files: Maximum number of files to return.
            max_file_bytes: Skip file content fetch if patch suggests file is larger.
            ignore_globs: Glob patterns for filenames to exclude.

        Returns:
            List of ChangedFile objects.
        """
        globs = ignore_globs or []
        result: list[ChangedFile] = []

        for f in pr.get_files():
            if len(result) >= max_files:
                _logger.debug("Reached max_files limit (%d), stopping.", max_files)
                break

            if any(fnmatch.fnmatch(f.filename, pat) for pat in globs):
                _logger.debug("Skipping ignored file: %s", f.filename)
                continue

            content: str | None = None
            if f.status != "removed":
                content = self.get_file_content(
                    repo_full_name=pr.base.repo.full_name,
                    path=f.filename,
                    ref=pr.head.sha,
                    max_bytes=max_file_bytes,
                )

            result.append(
                ChangedFile(
                    filename=f.filename,
                    status=f.status,
                    additions=f.additions,
                    deletions=f.deletions,
                    patch=f.patch,
                    content_at_head=content,
                    previous_filename=f.previous_filename,
                )
            )

        return result

    def get_file_content(
        self,
        repo_full_name: str,
        path: str,
        ref: str,
        *,
        max_bytes: int = 102_400,
    ) -> str | None:
        """Fetch decoded text content of a file at a given ref.

        Returns None when the file is binary, not found, or exceeds max_bytes.
        """
        try:
            repo = self._github.get_repo(repo_full_name)
            contents = repo.get_contents(path, ref=ref)
        except github.GithubException as exc:
            if exc.status == 404:
                _logger.debug("File not found: %s @ %s", path, ref)
                return None
            raise

        if isinstance(contents, list):
            _logger.debug("Path is a directory, not a file: %s", path)
            return None

        if contents.encoding != "base64":
            _logger.debug("Skipping non-base64 (likely binary) file: %s", path)
            return None

        if contents.size > max_bytes:
            _logger.debug("Skipping oversized file (%d bytes): %s", contents.size, path)
            return None

        try:
            return contents.decoded_content.decode("utf-8")
        except UnicodeDecodeError:
            _logger.debug("Skipping binary (non-UTF-8) file: %s", path)
            return None

    def get_commit_messages(self, pr: PullRequest) -> list[str]:
        """Return commit messages for a PR, oldest first."""
        return [c.commit.message for c in pr.get_commits()]

    def get_conventions_file(
        self,
        repo_full_name: str,
        path: str | None,
        ref: str,
    ) -> str | None:
        """Fetch a conventions/guidelines file from the repo.

        Returns None if path is None or the file is not found.
        """
        if path is None:
            return None
        return self.get_file_content(repo_full_name, path, ref)
