"""Durable state store for PR review and installation metadata.

Provides an abstract ``StateStore`` interface backed by SQLite (via aiosqlite)
for persisting per-PR review state and per-installation metadata.  The store
complements the comment-embedded state marker used for inline deduplication,
adding server-side persistence for job idempotency, crash recovery, and
cluster management.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from lychee.observability import get_correlation_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ReviewState:
    """Per-PR review state persisted in the durable store."""

    repo_full_name: str
    pr_number: int
    installation_id: int
    last_reviewed_sha: str = ""
    review_status: str = "pending"
    comment_id: int | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class InstallationState:
    """Per-installation metadata persisted in the durable store."""

    installation_id: int
    account_login: str = ""
    repos_count: int = 0
    last_event_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class StateStore(ABC):
    """Abstract interface for a durable state store."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables / prepare the backing store."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by the store."""

    # -- reviews --

    @abstractmethod
    async def get_review(self, repo_full_name: str, pr_number: int) -> ReviewState | None:
        """Return the review state for a PR, or ``None`` if not found."""

    @abstractmethod
    async def upsert_review(self, state: ReviewState) -> None:
        """Insert or update review state (composite key: repo_full_name + pr_number)."""

    @abstractmethod
    async def list_reviews(self, **filters: Any) -> list[ReviewState]:
        """Return reviews matching the given filters.

        Supported filter keys: ``repo_full_name``, ``installation_id``,
        ``review_status``.
        """

    @abstractmethod
    async def delete_review(self, repo_full_name: str, pr_number: int) -> bool:
        """Delete a review.  Return ``True`` if a row was deleted."""

    # -- installations --

    @abstractmethod
    async def get_installation(self, installation_id: int) -> InstallationState | None:
        """Return the installation state, or ``None`` if not found."""

    @abstractmethod
    async def upsert_installation(self, state: InstallationState) -> None:
        """Insert or update installation state (key: installation_id)."""

    @abstractmethod
    async def list_installations(self) -> list[InstallationState]:
        """Return all tracked installations."""

    @abstractmethod
    async def delete_installation(self, installation_id: int) -> bool:
        """Delete an installation.  Return ``True`` if a row was deleted."""


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

_CREATE_REVIEWS_TABLE = """
CREATE TABLE IF NOT EXISTS reviews (
    repo_full_name  TEXT    NOT NULL,
    pr_number       INTEGER NOT NULL,
    installation_id INTEGER NOT NULL,
    last_reviewed_sha TEXT NOT NULL DEFAULT '',
    review_status   TEXT    NOT NULL DEFAULT 'pending',
    comment_id      INTEGER,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (repo_full_name, pr_number)
)
"""

_CREATE_INSTALLATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS installations (
    installation_id INTEGER PRIMARY KEY,
    account_login   TEXT    NOT NULL DEFAULT '',
    repos_count     INTEGER NOT NULL DEFAULT 0,
    last_event_at   TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
)
"""


class SqliteStateStore(StateStore):
    """SQLite-backed durable state store using ``aiosqlite``."""

    def __init__(self, dsn: str) -> None:
        """Initialise with a DSN (file path or ``:memory:``)."""
        self._dsn = dsn
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open the database and create tables if they do not exist.

        Idempotent: safe to call multiple times on the same instance.
        """
        logger.debug(
            "Initialising SqliteStateStore dsn=%s, correlation_id=%s",
            self._dsn,
            get_correlation_id(),
        )
        if self._db is None:
            self._db = await aiosqlite.connect(self._dsn)
        await self._db.execute(_CREATE_REVIEWS_TABLE)
        await self._db.execute(_CREATE_INSTALLATIONS_TABLE)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection.  Idempotent."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.debug(
                "SqliteStateStore closed, correlation_id=%s",
                get_correlation_id(),
            )

    # -- internal helper --

    def _conn(self) -> aiosqlite.Connection:
        """Return the active connection, raising if not initialised."""
        if self._db is None:
            raise RuntimeError("StateStore is not initialised; call initialize() first")
        return self._db

    # -- reviews --

    async def get_review(self, repo_full_name: str, pr_number: int) -> ReviewState | None:
        """Return the review state for a PR, or ``None`` if not found."""
        db = self._conn()
        cursor = await db.execute(
            "SELECT repo_full_name, pr_number, installation_id, last_reviewed_sha, "
            "review_status, comment_id, created_at, updated_at "
            "FROM reviews WHERE repo_full_name = ? AND pr_number = ?",
            (repo_full_name, pr_number),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return ReviewState(
            repo_full_name=row[0],
            pr_number=row[1],
            installation_id=row[2],
            last_reviewed_sha=row[3],
            review_status=row[4],
            comment_id=row[5],
            created_at=row[6],
            updated_at=row[7],
        )

    async def upsert_review(self, state: ReviewState) -> None:
        """Insert or update review state, preserving ``created_at`` on update."""
        db = self._conn()
        await db.execute(
            "INSERT INTO reviews "
            "(repo_full_name, pr_number, installation_id, last_reviewed_sha, "
            "review_status, comment_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(repo_full_name, pr_number) DO UPDATE SET "
            "installation_id = excluded.installation_id, "
            "last_reviewed_sha = excluded.last_reviewed_sha, "
            "review_status = excluded.review_status, "
            "comment_id = excluded.comment_id, "
            "updated_at = excluded.updated_at",
            (
                state.repo_full_name,
                state.pr_number,
                state.installation_id,
                state.last_reviewed_sha,
                state.review_status,
                state.comment_id,
                state.created_at,
                state.updated_at,
            ),
        )
        await db.commit()
        logger.debug(
            "Upserted review repo=%s pr=%d, correlation_id=%s",
            state.repo_full_name,
            state.pr_number,
            get_correlation_id(),
        )

    async def list_reviews(self, **filters: Any) -> list[ReviewState]:
        """Return reviews matching optional filters.

        Supported keys: ``repo_full_name``, ``installation_id``, ``review_status``.
        """
        db = self._conn()
        allowed = {"repo_full_name", "installation_id", "review_status"}
        clauses: list[str] = []
        params: list[Any] = []
        for key, value in filters.items():
            if key not in allowed:
                raise ValueError(f"Unsupported filter key: {key}")
            clauses.append(f"{key} = ?")
            params.append(value)

        sql = (
            "SELECT repo_full_name, pr_number, installation_id, last_reviewed_sha, "
            "review_status, comment_id, created_at, updated_at FROM reviews"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [
            ReviewState(
                repo_full_name=r[0],
                pr_number=r[1],
                installation_id=r[2],
                last_reviewed_sha=r[3],
                review_status=r[4],
                comment_id=r[5],
                created_at=r[6],
                updated_at=r[7],
            )
            for r in rows
        ]

    async def delete_review(self, repo_full_name: str, pr_number: int) -> bool:
        """Delete a review.  Return ``True`` if a row was deleted."""
        db = self._conn()
        cursor = await db.execute(
            "DELETE FROM reviews WHERE repo_full_name = ? AND pr_number = ?",
            (repo_full_name, pr_number),
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        logger.debug(
            "Deleted review repo=%s pr=%d deleted=%s, correlation_id=%s",
            repo_full_name,
            pr_number,
            deleted,
            get_correlation_id(),
        )
        return deleted

    # -- installations --

    async def get_installation(self, installation_id: int) -> InstallationState | None:
        """Return the installation state, or ``None`` if not found."""
        db = self._conn()
        cursor = await db.execute(
            "SELECT installation_id, account_login, repos_count, last_event_at, created_at "
            "FROM installations WHERE installation_id = ?",
            (installation_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return InstallationState(
            installation_id=row[0],
            account_login=row[1],
            repos_count=row[2],
            last_event_at=row[3],
            created_at=row[4],
        )

    async def upsert_installation(self, state: InstallationState) -> None:
        """Insert or update installation state, preserving ``created_at`` on update."""
        db = self._conn()
        await db.execute(
            "INSERT INTO installations "
            "(installation_id, account_login, repos_count, last_event_at, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(installation_id) DO UPDATE SET "
            "account_login = excluded.account_login, "
            "repos_count = excluded.repos_count, "
            "last_event_at = excluded.last_event_at",
            (
                state.installation_id,
                state.account_login,
                state.repos_count,
                state.last_event_at,
                state.created_at,
            ),
        )
        await db.commit()
        logger.debug(
            "Upserted installation id=%d, correlation_id=%s",
            state.installation_id,
            get_correlation_id(),
        )

    async def list_installations(self) -> list[InstallationState]:
        """Return all tracked installations."""
        db = self._conn()
        cursor = await db.execute(
            "SELECT installation_id, account_login, repos_count, last_event_at, created_at "
            "FROM installations"
        )
        rows = await cursor.fetchall()
        return [
            InstallationState(
                installation_id=r[0],
                account_login=r[1],
                repos_count=r[2],
                last_event_at=r[3],
                created_at=r[4],
            )
            for r in rows
        ]

    async def delete_installation(self, installation_id: int) -> bool:
        """Delete an installation.  Return ``True`` if a row was deleted."""
        db = self._conn()
        cursor = await db.execute(
            "DELETE FROM installations WHERE installation_id = ?",
            (installation_id,),
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        logger.debug(
            "Deleted installation id=%d deleted=%s, correlation_id=%s",
            installation_id,
            deleted,
            get_correlation_id(),
        )
        return deleted


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_state_store(backend: str, dsn: str) -> StateStore:
    """Create a state store instance for the given backend.

    Args:
        backend: Store backend identifier (currently only ``"sqlite"``).
        dsn: Data source name (file path or ``:memory:`` for SQLite).

    Returns:
        An uninitialised ``StateStore``; caller must ``await store.initialize()``.

    Raises:
        ValueError: If the backend is not supported.
    """
    if backend == "sqlite":
        return SqliteStateStore(dsn=dsn)
    raise ValueError(f"Unsupported state store backend: {backend!r}")
