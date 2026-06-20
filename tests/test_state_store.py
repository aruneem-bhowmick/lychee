"""Tests for lychee.state_store — durable PR review and installation state."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

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


# ---------------------------------------------------------------------------
# System tests — persistence and concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_store_survives_reopen(tmp_path: object) -> None:
    """Data persists across close/reopen with a file-backed DSN."""  # P5-R4
    from pathlib import Path

    db_path = Path(str(tmp_path)) / "state.db"
    dsn = str(db_path)

    store1 = SqliteStateStore(dsn=dsn)
    await store1.initialize()
    await store1.upsert_review(_make_review(repo="persist/me", pr=7, sha="aaa"))
    await store1.close()

    store2 = SqliteStateStore(dsn=dsn)
    await store2.initialize()
    got = await store2.get_review("persist/me", 7)
    await store2.close()

    assert got is not None
    assert got.last_reviewed_sha == "aaa"


@pytest.mark.asyncio()
async def test_concurrent_upserts(store: SqliteStateStore) -> None:
    """Concurrent upserts via asyncio.gather do not corrupt data."""  # P5-R4
    tasks = [
        store.upsert_review(_make_review(repo="concurrent/repo", pr=i, sha=f"sha-{i}"))
        for i in range(1, 11)
    ]
    await asyncio.gather(*tasks)

    reviews = await store.list_reviews(repo_full_name="concurrent/repo")
    assert len(reviews) == 10


# ---------------------------------------------------------------------------
# Acceptance tests — restart survival and dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_accept_state_survives_restarts(tmp_path: object) -> None:
    """State is recoverable after a simulated server restart."""  # P5-R4
    from pathlib import Path

    db_path = Path(str(tmp_path)) / "restart.db"
    dsn = str(db_path)

    store = SqliteStateStore(dsn=dsn)
    await store.initialize()
    await store.upsert_review(_make_review(repo="restart/test", pr=1, sha="original"))
    await store.upsert_installation(_make_installation(inst=42, login="restarter"))
    await store.close()

    # "restart" — new store instance against same file
    store = SqliteStateStore(dsn=dsn)
    await store.initialize()
    review = await store.get_review("restart/test", 1)
    inst = await store.get_installation(42)
    await store.close()

    assert review is not None
    assert review.last_reviewed_sha == "original"
    assert inst is not None
    assert inst.account_login == "restarter"


@pytest.mark.asyncio()
async def test_accept_dedup_intact(tmp_path: object) -> None:
    """SHA preserved after simulated restart enables dedup check."""  # P5-R4
    from pathlib import Path

    db_path = Path(str(tmp_path)) / "dedup.db"
    dsn = str(db_path)

    store = SqliteStateStore(dsn=dsn)
    await store.initialize()
    await store.upsert_review(_make_review(repo="dedup/repo", pr=1, sha="sha-first"))
    await store.close()

    # Simulate restart
    store = SqliteStateStore(dsn=dsn)
    await store.initialize()
    review = await store.get_review("dedup/repo", 1)
    await store.close()

    assert review is not None
    assert review.last_reviewed_sha == "sha-first"


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_state_store_module_imports() -> None:
    """All public names are importable from lychee.state_store."""  # P5-R4
    from lychee import state_store as mod

    assert hasattr(mod, "ReviewState")
    assert hasattr(mod, "InstallationState")
    assert hasattr(mod, "StateStore")
    assert hasattr(mod, "SqliteStateStore")
    assert hasattr(mod, "create_state_store")


# ---------------------------------------------------------------------------
# Sanity tests
# ---------------------------------------------------------------------------


def test_sqlite_store_is_state_store() -> None:
    """SqliteStateStore is a subclass of StateStore."""  # P5-R4
    assert issubclass(SqliteStateStore, StateStore)


@pytest.mark.asyncio()
async def test_store_close_is_safe() -> None:
    """Closing an already-closed store does not raise."""  # P5-R4
    store = SqliteStateStore(dsn=":memory:")
    await store.initialize()
    await store.close()
    await store.close()  # second close — should not raise


# ---------------------------------------------------------------------------
# Regression tests — round-trip snapshot
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("repo", "pr", "sha", "status"),
    [
        ("snap/alpha", 1, "aaa111", "pending"),
        ("snap/beta", 42, "bbb222", "completed"),
    ],
    ids=["alpha-pending", "beta-completed"],
)
@pytest.mark.asyncio()
async def test_review_state_round_trip_snapshot(
    store: SqliteStateStore,
    repo: str,
    pr: int,
    sha: str,
    status: str,
) -> None:
    """Parametrized fixture: exact field equality after DB round-trip."""  # P5-R4
    review = _make_review(repo=repo, pr=pr, sha=sha, status=status)
    await store.upsert_review(review)

    got = await store.get_review(repo, pr)
    assert got is not None
    assert got.repo_full_name == repo
    assert got.pr_number == pr
    assert got.last_reviewed_sha == sha
    assert got.review_status == status
    assert got.created_at == _NOW
    assert got.updated_at == _NOW


# ---------------------------------------------------------------------------
# Regression tests — schema creation SQL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_schema_creation_sql() -> None:
    """CREATE TABLE statements match expected schema."""  # P5-R4
    from lychee.state_store import _CREATE_INSTALLATIONS_TABLE, _CREATE_REVIEWS_TABLE

    assert "repo_full_name" in _CREATE_REVIEWS_TABLE
    assert "pr_number" in _CREATE_REVIEWS_TABLE
    assert "PRIMARY KEY (repo_full_name, pr_number)" in _CREATE_REVIEWS_TABLE
    assert "last_reviewed_sha" in _CREATE_REVIEWS_TABLE
    assert "review_status" in _CREATE_REVIEWS_TABLE
    assert "comment_id" in _CREATE_REVIEWS_TABLE
    assert "created_at" in _CREATE_REVIEWS_TABLE
    assert "updated_at" in _CREATE_REVIEWS_TABLE

    assert "installation_id INTEGER PRIMARY KEY" in _CREATE_INSTALLATIONS_TABLE
    assert "account_login" in _CREATE_INSTALLATIONS_TABLE
    assert "repos_count" in _CREATE_INSTALLATIONS_TABLE
    assert "last_event_at" in _CREATE_INSTALLATIONS_TABLE
    assert "created_at" in _CREATE_INSTALLATIONS_TABLE
