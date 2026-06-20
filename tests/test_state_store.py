"""Tests for lychee.state_store — durable PR review and installation state."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from lychee.state_store import (
    InstallationState,
    ReviewState,
    SqliteStateStore,
    StateStore,
    create_state_store,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = "2024-06-01T12:00:00+00:00"
_LATER = "2024-06-01T13:00:00+00:00"


@pytest_asyncio.fixture()
async def store() -> AsyncIterator[SqliteStateStore]:
    """Yield an initialised in-memory SQLite state store, closed after use."""
    s = SqliteStateStore(dsn=":memory:")
    await s.initialize()
    yield s
    await s.close()


def _make_review(
    *,
    repo: str = "owner/repo",
    pr: int = 1,
    inst: int = 100,
    sha: str = "abc123",
    status: str = "pending",
    comment_id: int | None = None,
    created_at: str = _NOW,
    updated_at: str = _NOW,
) -> ReviewState:
    """Helper to build a ReviewState with sensible defaults."""
    return ReviewState(
        repo_full_name=repo,
        pr_number=pr,
        installation_id=inst,
        last_reviewed_sha=sha,
        review_status=status,
        comment_id=comment_id,
        created_at=created_at,
        updated_at=updated_at,
    )


def _make_installation(
    *,
    inst: int = 100,
    login: str = "octocat",
    repos: int = 5,
    last_event: str = _NOW,
    created_at: str = _NOW,
) -> InstallationState:
    """Helper to build an InstallationState with sensible defaults."""
    return InstallationState(
        installation_id=inst,
        account_login=login,
        repos_count=repos,
        last_event_at=last_event,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Unit tests — ReviewState defaults
# ---------------------------------------------------------------------------


def test_review_state_defaults() -> None:
    """ReviewState provides sensible defaults for optional fields."""  # P5-R4
    state = ReviewState(repo_full_name="o/r", pr_number=1, installation_id=10)
    assert state.last_reviewed_sha == ""
    assert state.review_status == "pending"
    assert state.comment_id is None
    assert state.created_at  # non-empty
    assert state.updated_at  # non-empty


def test_review_state_fields() -> None:
    """All ReviewState fields round-trip correctly."""  # P5-R4
    state = _make_review(
        repo="alpha/beta",
        pr=42,
        inst=200,
        sha="deadbeef",
        status="completed",
        comment_id=999,
        created_at=_NOW,
        updated_at=_LATER,
    )
    assert state.repo_full_name == "alpha/beta"
    assert state.pr_number == 42
    assert state.installation_id == 200
    assert state.last_reviewed_sha == "deadbeef"
    assert state.review_status == "completed"
    assert state.comment_id == 999
    assert state.created_at == _NOW
    assert state.updated_at == _LATER


# ---------------------------------------------------------------------------
# Unit tests — InstallationState defaults
# ---------------------------------------------------------------------------


def test_installation_state_defaults() -> None:
    """InstallationState provides sensible defaults for optional fields."""  # P5-R4
    state = InstallationState(installation_id=10)
    assert state.account_login == ""
    assert state.repos_count == 0
    assert state.last_event_at  # non-empty
    assert state.created_at  # non-empty


# ---------------------------------------------------------------------------
# Unit tests — factory
# ---------------------------------------------------------------------------


def test_create_state_store_sqlite() -> None:
    """Factory returns a SqliteStateStore for 'sqlite' backend."""  # P5-R4
    store = create_state_store("sqlite", ":memory:")
    assert isinstance(store, SqliteStateStore)


def test_create_state_store_unsupported() -> None:
    """Factory raises ValueError for unknown backend."""  # P5-R4
    with pytest.raises(ValueError, match="Unsupported state store backend"):
        create_state_store("postgres", "host=localhost")


# ---------------------------------------------------------------------------
# Integration tests — review CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_upsert_and_get_review(store: SqliteStateStore) -> None:
    """Insert a review then retrieve it by key."""  # P5-R4
    review = _make_review(repo="o/r", pr=1, sha="aaa")
    await store.upsert_review(review)

    got = await store.get_review("o/r", 1)
    assert got is not None
    assert got.repo_full_name == "o/r"
    assert got.pr_number == 1
    assert got.last_reviewed_sha == "aaa"


@pytest.mark.asyncio()
async def test_upsert_review_updates(store: SqliteStateStore) -> None:
    """Upserting again overwrites mutable fields."""  # P5-R4
    await store.upsert_review(_make_review(sha="v1"))
    await store.upsert_review(_make_review(sha="v2", updated_at=_LATER))

    got = await store.get_review("owner/repo", 1)
    assert got is not None
    assert got.last_reviewed_sha == "v2"


@pytest.mark.asyncio()
async def test_upsert_preserves_created_at(store: SqliteStateStore) -> None:
    """created_at is not overwritten on conflict update."""  # P5-R4
    original = _make_review(created_at=_NOW)
    await store.upsert_review(original)

    updated = _make_review(sha="new", created_at=_LATER, updated_at=_LATER)
    await store.upsert_review(updated)

    got = await store.get_review("owner/repo", 1)
    assert got is not None
    assert got.created_at == _NOW  # preserved from first insert


@pytest.mark.asyncio()
async def test_get_review_not_found(store: SqliteStateStore) -> None:
    """get_review returns None for missing key."""  # P5-R4
    got = await store.get_review("no/such", 999)
    assert got is None


@pytest.mark.asyncio()
async def test_list_reviews_all(store: SqliteStateStore) -> None:
    """list_reviews with no filters returns all rows."""  # P5-R4
    await store.upsert_review(_make_review(repo="a/b", pr=1))
    await store.upsert_review(_make_review(repo="c/d", pr=2))

    reviews = await store.list_reviews()
    assert len(reviews) == 2


@pytest.mark.asyncio()
async def test_list_reviews_by_repo(store: SqliteStateStore) -> None:
    """list_reviews filters by repo_full_name."""  # P5-R4
    await store.upsert_review(_make_review(repo="a/b", pr=1))
    await store.upsert_review(_make_review(repo="c/d", pr=2))

    reviews = await store.list_reviews(repo_full_name="a/b")
    assert len(reviews) == 1
    assert reviews[0].repo_full_name == "a/b"


@pytest.mark.asyncio()
async def test_list_reviews_by_installation(store: SqliteStateStore) -> None:
    """list_reviews filters by installation_id."""  # P5-R4
    await store.upsert_review(_make_review(repo="a/b", pr=1, inst=10))
    await store.upsert_review(_make_review(repo="c/d", pr=2, inst=20))

    reviews = await store.list_reviews(installation_id=10)
    assert len(reviews) == 1
    assert reviews[0].installation_id == 10


@pytest.mark.asyncio()
async def test_list_reviews_by_status(store: SqliteStateStore) -> None:
    """list_reviews filters by review_status."""  # P5-R4
    await store.upsert_review(_make_review(repo="a/b", pr=1, status="pending"))
    await store.upsert_review(_make_review(repo="c/d", pr=2, status="completed"))

    reviews = await store.list_reviews(review_status="completed")
    assert len(reviews) == 1
    assert reviews[0].review_status == "completed"


@pytest.mark.asyncio()
async def test_list_reviews_combined_filters(store: SqliteStateStore) -> None:
    """list_reviews with multiple filter criteria."""  # P5-R4
    await store.upsert_review(_make_review(repo="a/b", pr=1, inst=10, status="pending"))
    await store.upsert_review(_make_review(repo="a/b", pr=2, inst=10, status="completed"))
    await store.upsert_review(_make_review(repo="c/d", pr=3, inst=20, status="pending"))

    reviews = await store.list_reviews(repo_full_name="a/b", review_status="pending")
    assert len(reviews) == 1
    assert reviews[0].pr_number == 1


@pytest.mark.asyncio()
async def test_delete_review_exists(store: SqliteStateStore) -> None:
    """delete_review returns True when a row is deleted."""  # P5-R4
    await store.upsert_review(_make_review())
    assert await store.delete_review("owner/repo", 1) is True
    assert await store.get_review("owner/repo", 1) is None


@pytest.mark.asyncio()
async def test_delete_review_not_found(store: SqliteStateStore) -> None:
    """delete_review returns False when nothing matched."""  # P5-R4
    assert await store.delete_review("no/such", 999) is False


# ---------------------------------------------------------------------------
# Integration tests — installation CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_upsert_and_get_installation(store: SqliteStateStore) -> None:
    """Insert an installation then retrieve it by key."""  # P5-R4
    inst = _make_installation(inst=10, login="acme")
    await store.upsert_installation(inst)

    got = await store.get_installation(10)
    assert got is not None
    assert got.installation_id == 10
    assert got.account_login == "acme"


@pytest.mark.asyncio()
async def test_upsert_installation_updates(store: SqliteStateStore) -> None:
    """Upserting again overwrites mutable fields."""  # P5-R4
    await store.upsert_installation(_make_installation(repos=5))
    await store.upsert_installation(_make_installation(repos=10, last_event=_LATER))

    got = await store.get_installation(100)
    assert got is not None
    assert got.repos_count == 10


@pytest.mark.asyncio()
async def test_get_installation_not_found(store: SqliteStateStore) -> None:
    """get_installation returns None for missing key."""  # P5-R4
    got = await store.get_installation(999)
    assert got is None


@pytest.mark.asyncio()
async def test_list_installations(store: SqliteStateStore) -> None:
    """list_installations returns all rows."""  # P5-R4
    await store.upsert_installation(_make_installation(inst=1, login="a"))
    await store.upsert_installation(_make_installation(inst=2, login="b"))

    installs = await store.list_installations()
    assert len(installs) == 2


@pytest.mark.asyncio()
async def test_delete_installation_exists(store: SqliteStateStore) -> None:
    """delete_installation returns True when a row is deleted."""  # P5-R4
    await store.upsert_installation(_make_installation(inst=10))
    assert await store.delete_installation(10) is True
    assert await store.get_installation(10) is None


@pytest.mark.asyncio()
async def test_delete_installation_not_found(store: SqliteStateStore) -> None:
    """delete_installation returns False when nothing matched."""  # P5-R4
    assert await store.delete_installation(999) is False


# ---------------------------------------------------------------------------
# Integration tests — idempotent initialisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_initialize_idempotent(store: SqliteStateStore) -> None:
    """Calling initialize() twice does not fail or lose data."""  # P5-R4
    await store.upsert_review(_make_review())
    await store.initialize()  # second init

    got = await store.get_review("owner/repo", 1)
    assert got is not None
