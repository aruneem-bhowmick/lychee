"""GitHub App authentication: JWT signing and installation token lifecycle.

Generates RS256-signed JWTs from the App's private key, exchanges them for
short-lived installation access tokens via the GitHub API, and caches tokens
in memory with automatic refresh when near expiry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import jwt

from lychee.observability import get_correlation_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_JWT_ALGORITHM = "RS256"
_JWT_EXPIRY_SECONDS = 600  # 10 minutes (GitHub maximum)
_JWT_IAT_BACKDATE_SECONDS = 60  # Clock-skew buffer
_TOKEN_REFRESH_BUFFER_SECONDS = 300  # 5 minutes before expiry
_GITHUB_API_BASE = "https://api.github.com"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InstallationToken:
    """A GitHub App installation access token with expiry."""

    token: str
    expires_at: float  # Unix timestamp
    installation_id: int

    @property
    def is_expired(self) -> bool:
        """Return True if the token is expired or within 5 minutes of expiry."""
        return time.time() >= (self.expires_at - _TOKEN_REFRESH_BUFFER_SECONDS)


class AppAuthError(Exception):
    """Raised when GitHub App authentication fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialise with a descriptive message and optional HTTP status code."""
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Authenticator
# ---------------------------------------------------------------------------


class AppAuthenticator:
    """Manages GitHub App authentication: JWT signing and installation token lifecycle."""

    def __init__(self, app_id: int, private_key_path: str) -> None:
        """Initialize with App ID and path to the PEM private key file.

        Raises:
            FileNotFoundError: If private_key_path does not exist.
            ValueError: If the private key file is empty or unreadable.
        """
        self._app_id = app_id
        key_path = Path(private_key_path)

        if not key_path.exists():
            raise FileNotFoundError(f"GitHub App private key not found: {private_key_path}")

        key_bytes = key_path.read_bytes()
        if not key_bytes.strip():
            raise ValueError(f"GitHub App private key file is empty: {private_key_path}")

        self._private_key = key_bytes
        self._token_cache: dict[str, InstallationToken] = {}

        logger.info(
            "AppAuthenticator initialised for app_id=%d, correlation_id=%s",
            app_id,
            get_correlation_id(),
        )

    def generate_jwt(self, now: float | None = None) -> str:
        """Generate a short-lived JWT for GitHub App authentication.

        The JWT is valid for 10 minutes (GitHub's maximum), with:
        - iss: app_id
        - iat: now - 60 (clock skew buffer)
        - exp: now + 600

        Args:
            now: Current Unix timestamp; defaults to time.time(). Exposed for testing.

        Returns:
            Encoded JWT string.
        """
        if now is None:
            now = time.time()

        payload = {
            "iss": str(self._app_id),
            "iat": int(now) - _JWT_IAT_BACKDATE_SECONDS,
            "exp": int(now) + _JWT_EXPIRY_SECONDS,
        }

        encoded: str = jwt.encode(payload, self._private_key, algorithm=_JWT_ALGORITHM)
        logger.debug(
            "Generated JWT for app_id=%d, correlation_id=%s",
            self._app_id,
            get_correlation_id(),
        )
        return encoded

    async def get_installation_token(self, installation_id: int) -> InstallationToken:
        """Get or refresh an installation access token.

        Returns a cached token if still valid (>5 min from expiry).
        Otherwise, mints a new token via the GitHub API.

        Args:
            installation_id: The GitHub App installation ID.

        Returns:
            A valid InstallationToken.

        Raises:
            AppAuthError: If the token request fails.
        """
        cache_key = self._cache_key(installation_id)
        cached = self._token_cache.get(cache_key)

        if cached is not None and not cached.is_expired:
            logger.debug(
                "Cache hit for installation_id=%d, correlation_id=%s",
                installation_id,
                get_correlation_id(),
            )
            return cached

        logger.info(
            "Cache miss for installation_id=%d, minting new token, correlation_id=%s",
            installation_id,
            get_correlation_id(),
        )
        token = await self._mint_token(installation_id)
        self._token_cache[cache_key] = token
        return token

    def _cache_key(self, installation_id: int) -> str:
        """Return the cache key for an installation."""
        return f"installation:{installation_id}"

    async def _mint_token(self, installation_id: int) -> InstallationToken:
        """Mint a new installation access token via the GitHub API.

        POST /app/installations/{installation_id}/access_tokens
        Authorization: Bearer <jwt>

        Returns:
            A fresh InstallationToken.

        Raises:
            AppAuthError: On HTTP errors or unexpected responses.
        """
        jwt_token = self.generate_jwt()
        url = f"{_GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers)
        except httpx.HTTPError as exc:
            raise AppAuthError(
                f"HTTP error minting installation token for installation_id={installation_id}",
                status_code=None,
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            logger.error(
                "Token mint failed for installation_id=%d, status=%d, correlation_id=%s",
                installation_id,
                response.status_code,
                get_correlation_id(),
            )
            raise AppAuthError(
                f"Failed to mint installation token for installation_id={installation_id}: "
                f"HTTP {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        expires_at_str: str = data["expires_at"]
        expires_at = (
            datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            .replace(tzinfo=UTC)
            .timestamp()
        )

        token = InstallationToken(
            token=data["token"],
            expires_at=expires_at,
            installation_id=installation_id,
        )

        logger.info(
            "Minted installation token for installation_id=%d, "
            "expires_at=%.0f, correlation_id=%s",
            installation_id,
            expires_at,
            get_correlation_id(),
        )
        return token
