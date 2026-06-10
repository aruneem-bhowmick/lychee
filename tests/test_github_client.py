"""Tests for lychee.github_client — PullRequestRef, ChangedFile, and GitHubClient."""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from lychee.github_client import ChangedFile, GitHubClient, PullRequestRef

# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_github_client_imports() -> None:
    """All public names are importable from lychee.github_client."""
    # P1-R1
    from lychee import github_client as mod

    assert hasattr(mod, "PullRequestRef")
    assert hasattr(mod, "ChangedFile")
    assert hasattr(mod, "GitHubClient")


# ---------------------------------------------------------------------------
# Unit tests — PullRequestRef.parse()
# ---------------------------------------------------------------------------


def test_parse_valid_ref() -> None:
    """parse() splits a well-formed 'owner/repo#123' into its components."""
    # P1-R1
    ref = PullRequestRef.parse("octocat/hello-world#42")
    assert ref.owner == "octocat"
    assert ref.repo == "hello-world"
    assert ref.number == 42


def test_parse_ref_with_org_slash() -> None:
    """parse() handles owner/repo where repo has no extra slashes."""
    # P1-R1
    ref = PullRequestRef.parse("my-org/my-repo#1")
    assert ref.owner == "my-org"
    assert ref.repo == "my-repo"
    assert ref.number == 1


def test_parse_ref_full_name() -> None:
    """full_name property returns 'owner/repo'."""
    # P1-R1
    ref = PullRequestRef.parse("owner/repo#10")
    assert ref.full_name == "owner/repo"


@pytest.mark.parametrize(
    "bad_ref",
    [
        "no-hash",
        "owner#123",
        "#123",
        "/repo#123",
        "owner/#123",
        "",
    ],
)
def test_parse_ref_invalid_format(bad_ref: str) -> None:
    """parse() raises ValueError for malformed references."""
    # P1-R1
    with pytest.raises(ValueError, match="Invalid PR reference"):
        PullRequestRef.parse(bad_ref)


def test_parse_ref_non_integer_number() -> None:
    """parse() raises ValueError when the PR number is not an integer."""
    # P1-R1
    with pytest.raises(ValueError, match="must be an integer"):
        PullRequestRef.parse("owner/repo#abc")


def test_parse_ref_negative_number() -> None:
    """parse() raises ValueError when the PR number is negative."""
    # P1-R1
    with pytest.raises(ValueError, match="must be a positive integer"):
        PullRequestRef.parse("owner/repo#-1")


def test_parse_ref_zero_number() -> None:
    """parse() raises ValueError when the PR number is zero."""
    # P1-R1
    with pytest.raises(ValueError, match="must be a positive integer"):
        PullRequestRef.parse("owner/repo#0")


# ---------------------------------------------------------------------------
# Unit tests — ChangedFile dataclass
# ---------------------------------------------------------------------------


def test_changed_file_dataclass_fields() -> None:
    """ChangedFile stores all expected fields."""
    # P1-R1
    f = ChangedFile(
        filename="src/main.py",
        status="modified",
        additions=10,
        deletions=2,
        patch="@@ -1,5 +1,7 @@\n+new line",
        content_at_head="print('hello')\n",
        previous_filename=None,
    )
    assert f.filename == "src/main.py"
    assert f.status == "modified"
    assert f.additions == 10
    assert f.deletions == 2
    assert f.patch is not None
    assert f.content_at_head is not None
    assert f.previous_filename is None


def test_changed_file_frozen() -> None:
    """ChangedFile instances are immutable."""
    # P1-R1
    f = ChangedFile(
        filename="a.py",
        status="added",
        additions=1,
        deletions=0,
        patch=None,
        content_at_head=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.filename = "b.py"  # type: ignore[misc]


def test_changed_file_serialization() -> None:
    """ChangedFile can be serialized to a dict via dataclasses.asdict."""
    # P1-R1
    f = ChangedFile(
        filename="test.py",
        status="added",
        additions=5,
        deletions=0,
        patch="+hello",
        content_at_head="hello\n",
        previous_filename=None,
    )
    d = dataclasses.asdict(f)
    assert d["filename"] == "test.py"
    assert d["status"] == "added"
    assert d["content_at_head"] == "hello\n"


# ---------------------------------------------------------------------------
# Sanity tests — GitHubClient instantiation
# ---------------------------------------------------------------------------


def test_github_client_instantiates() -> None:
    """GitHubClient can be instantiated with a token string."""
    # P1-R1
    with patch("lychee.github_client.github.Github"):
        client = GitHubClient(token="fake-token")
        assert client is not None


# ---------------------------------------------------------------------------
# Regression tests — snapshots
# ---------------------------------------------------------------------------


def test_pr_ref_parse_snapshot() -> None:
    """PullRequestRef.parse produces consistent output (regression guard)."""
    # P1-R1
    ref = PullRequestRef.parse("anthropics/claude#999")
    assert ref.owner == "anthropics"
    assert ref.repo == "claude"
    assert ref.number == 999
    assert ref.full_name == "anthropics/claude"


def test_changed_file_serialization_snapshot() -> None:
    """ChangedFile serialization structure is stable (regression guard)."""
    # P1-R1
    f = ChangedFile(
        filename="README.md",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1 +1 @@\n-old\n+new",
        content_at_head="new\n",
        previous_filename=None,
    )
    d = dataclasses.asdict(f)
    expected_keys = {
        "filename",
        "status",
        "additions",
        "deletions",
        "patch",
        "content_at_head",
        "previous_filename",
    }
    assert set(d.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Integration tests — GitHubClient methods (mocked PyGithub)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _mock_github() -> MagicMock:
    """A mock github.Github instance for GitHubClient tests."""
    mock = MagicMock()
    return mock


@pytest.fixture()
def client(_mock_github: MagicMock) -> GitHubClient:
    """A GitHubClient with a mocked internal Github instance."""
    with patch("lychee.github_client.github.Github", return_value=_mock_github):
        c = GitHubClient(token="test-token")
    return c


@pytest.fixture()
def ref() -> PullRequestRef:
    """A standard test PR ref."""
    return PullRequestRef(owner="owner", repo="repo", number=42)


def test_get_pull_request_returns_pr(
    client: GitHubClient,
    _mock_github: MagicMock,
    ref: PullRequestRef,
) -> None:
    """get_pull_request fetches PR via get_repo().get_pull()."""
    # P1-R1
    mock_repo = MagicMock()
    mock_pr = MagicMock()
    _mock_github.get_repo.return_value = mock_repo
    mock_repo.get_pull.return_value = mock_pr

    result = client.get_pull_request(ref)

    _mock_github.get_repo.assert_called_once_with("owner/repo")
    mock_repo.get_pull.assert_called_once_with(42)
    assert result is mock_pr


def test_get_diff_returns_string(
    client: GitHubClient,
    ref: PullRequestRef,
) -> None:
    """get_diff returns a diff string from the GitHub API."""
    # P1-R1
    fake_diff = "diff --git a/x.py b/x.py\n+hello\n"
    with patch("lychee.github_client.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = fake_diff
        mock_get.return_value = mock_response

        result = client.get_diff(ref)

    assert result == fake_diff
    mock_response.raise_for_status.assert_called_once()


def test_github_api_diff_accept_header(
    client: GitHubClient,
    ref: PullRequestRef,
) -> None:
    """get_diff sends the correct Accept header for the diff media type."""
    # P1-R1
    with patch("lychee.github_client.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = ""
        mock_get.return_value = mock_response

        client.get_diff(ref)

    call_kwargs = mock_get.call_args
    headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert headers["Accept"] == "application/vnd.github.v3.diff"


def _make_mock_file(
    filename: str = "src/main.py",
    status: str = "modified",
    additions: int = 5,
    deletions: int = 2,
    patch: str | None = "@@ -1 +1 @@\n+new",
    previous_filename: str | None = None,
) -> MagicMock:
    """Create a mock PyGithub File object."""
    f = MagicMock()
    f.filename = filename
    f.status = status
    f.additions = additions
    f.deletions = deletions
    f.patch = patch
    f.previous_filename = previous_filename
    return f


def test_get_changed_files_respects_max_files(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_changed_files stops collecting after max_files."""
    # P1-R1
    mock_pr = MagicMock()
    mock_pr.base.repo.full_name = "owner/repo"
    mock_pr.head.sha = "abc123"
    mock_pr.get_files.return_value = [_make_mock_file(f"file{i}.py") for i in range(10)]

    with patch.object(client, "get_file_content", return_value="content"):
        result = client.get_changed_files(mock_pr, max_files=3)

    assert len(result) == 3


def test_get_changed_files_skips_ignored_globs(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_changed_files excludes files matching ignore_globs patterns."""
    # P1-R1
    mock_pr = MagicMock()
    mock_pr.base.repo.full_name = "owner/repo"
    mock_pr.head.sha = "abc123"
    mock_pr.get_files.return_value = [
        _make_mock_file("src/main.py"),
        _make_mock_file("package-lock.json"),
        _make_mock_file("yarn.lock"),
    ]

    with patch.object(client, "get_file_content", return_value="content"):
        result = client.get_changed_files(mock_pr, ignore_globs=["*.lock", "package-lock.json"])

    filenames = [f.filename for f in result]
    assert "src/main.py" in filenames
    assert "package-lock.json" not in filenames
    assert "yarn.lock" not in filenames


def test_get_changed_files_skips_deleted(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_changed_files does not fetch content for deleted files."""
    # P1-R1
    mock_pr = MagicMock()
    mock_pr.base.repo.full_name = "owner/repo"
    mock_pr.head.sha = "abc123"
    mock_pr.get_files.return_value = [
        _make_mock_file("deleted.py", status="removed"),
    ]

    with patch.object(client, "get_file_content") as mock_content:
        result = client.get_changed_files(mock_pr)

    assert len(result) == 1
    assert result[0].content_at_head is None
    mock_content.assert_not_called()


def test_get_changed_files_handles_renamed(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_changed_files preserves previous_filename for renamed files."""
    # P1-R1
    mock_pr = MagicMock()
    mock_pr.base.repo.full_name = "owner/repo"
    mock_pr.head.sha = "abc123"
    mock_pr.get_files.return_value = [
        _make_mock_file("new_name.py", status="renamed", previous_filename="old_name.py"),
    ]

    with patch.object(client, "get_file_content", return_value="content"):
        result = client.get_changed_files(mock_pr)

    assert len(result) == 1
    assert result[0].previous_filename == "old_name.py"


def test_get_changed_files_skips_binary(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_changed_files returns None content for binary files."""
    # P1-R1
    mock_pr = MagicMock()
    mock_pr.base.repo.full_name = "owner/repo"
    mock_pr.head.sha = "abc123"
    mock_pr.get_files.return_value = [
        _make_mock_file("image.png", status="added"),
    ]

    with patch.object(client, "get_file_content", return_value=None):
        result = client.get_changed_files(mock_pr)

    assert len(result) == 1
    assert result[0].content_at_head is None


def test_get_changed_files_skips_large_files(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_changed_files passes max_file_bytes to get_file_content."""
    # P1-R1
    mock_pr = MagicMock()
    mock_pr.base.repo.full_name = "owner/repo"
    mock_pr.head.sha = "abc123"
    mock_pr.get_files.return_value = [
        _make_mock_file("big.py"),
    ]

    with patch.object(client, "get_file_content", return_value=None) as mock_content:
        client.get_changed_files(mock_pr, max_file_bytes=1024)

    mock_content.assert_called_once_with(
        repo_full_name="owner/repo",
        path="big.py",
        ref="abc123",
        max_bytes=1024,
    )


def test_get_file_content_success(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_file_content returns decoded UTF-8 text for a base64-encoded file."""
    # P1-R1
    mock_repo = MagicMock()
    _mock_github.get_repo.return_value = mock_repo

    mock_contents = MagicMock()
    mock_contents.encoding = "base64"
    mock_contents.size = 100
    mock_contents.decoded_content = b"hello world\n"
    mock_repo.get_contents.return_value = mock_contents

    result = client.get_file_content("owner/repo", "file.py", "abc123")
    assert result == "hello world\n"


def test_get_file_content_404_returns_none(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_file_content returns None when file is not found (404)."""
    # P1-R1
    import github

    mock_repo = MagicMock()
    _mock_github.get_repo.return_value = mock_repo
    mock_repo.get_contents.side_effect = github.GithubException(
        status=404, data={"message": "Not Found"}, headers={}
    )

    result = client.get_file_content("owner/repo", "missing.py", "abc123")
    assert result is None


def test_get_file_content_binary_returns_none(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_file_content returns None for non-base64 (binary) files."""
    # P1-R1
    mock_repo = MagicMock()
    _mock_github.get_repo.return_value = mock_repo

    mock_contents = MagicMock()
    mock_contents.encoding = "none"
    mock_repo.get_contents.return_value = mock_contents

    result = client.get_file_content("owner/repo", "image.png", "abc123")
    assert result is None


def test_get_file_content_oversized_returns_none(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_file_content returns None when file exceeds max_bytes."""
    # P1-R1
    mock_repo = MagicMock()
    _mock_github.get_repo.return_value = mock_repo

    mock_contents = MagicMock()
    mock_contents.encoding = "base64"
    mock_contents.size = 200_000
    mock_repo.get_contents.return_value = mock_contents

    result = client.get_file_content("owner/repo", "huge.py", "abc123", max_bytes=1024)
    assert result is None


def test_get_file_content_directory_returns_none(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_file_content returns None when path resolves to a directory."""
    # P1-R1
    mock_repo = MagicMock()
    _mock_github.get_repo.return_value = mock_repo
    mock_repo.get_contents.return_value = [MagicMock(), MagicMock()]

    result = client.get_file_content("owner/repo", "src/", "abc123")
    assert result is None


def test_github_api_file_content_ref(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_file_content passes the ref argument to get_contents."""
    # P1-R1
    mock_repo = MagicMock()
    _mock_github.get_repo.return_value = mock_repo

    mock_contents = MagicMock()
    mock_contents.encoding = "base64"
    mock_contents.size = 10
    mock_contents.decoded_content = b"x"
    mock_repo.get_contents.return_value = mock_contents

    client.get_file_content("owner/repo", "file.py", "deadbeef")

    mock_repo.get_contents.assert_called_once_with("file.py", ref="deadbeef")


def test_get_commit_messages_order(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_commit_messages returns messages in order (oldest first)."""
    # P1-R1
    mock_pr = MagicMock()
    commits = []
    for msg in ["first commit", "second commit", "third commit"]:
        c = MagicMock()
        c.commit.message = msg
        commits.append(c)
    mock_pr.get_commits.return_value = commits

    result = client.get_commit_messages(mock_pr)
    assert result == ["first commit", "second commit", "third commit"]


def test_get_conventions_file_found(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_conventions_file returns file content when the file exists."""
    # P1-R1
    with patch.object(client, "get_file_content", return_value="# Conventions\n") as mock:
        result = client.get_conventions_file("owner/repo", "CONVENTIONS.md", "abc123")

    assert result == "# Conventions\n"
    mock.assert_called_once_with("owner/repo", "CONVENTIONS.md", "abc123")


def test_get_conventions_file_not_found(
    client: GitHubClient,
    _mock_github: MagicMock,
) -> None:
    """get_conventions_file returns None when file content is not found."""
    # P1-R1
    with patch.object(client, "get_file_content", return_value=None):
        result = client.get_conventions_file("owner/repo", "CONVENTIONS.md", "abc123")

    assert result is None


def test_get_conventions_file_path_none(
    client: GitHubClient,
) -> None:
    """get_conventions_file returns None when path is None."""
    # P1-R1
    result = client.get_conventions_file("owner/repo", None, "abc123")
    assert result is None
