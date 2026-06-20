"""Tests for lychee.app_auth — JWT generation, installation token lifecycle, and caching."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest

from lychee.app_auth import AppAuthenticator, AppAuthError, InstallationToken

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_APP_ID = 12345


@pytest.fixture()
def rsa_private_key_pem() -> bytes:
    """Generate a fresh RSA private key in PEM format for testing."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())


@pytest.fixture()
def rsa_public_key(rsa_private_key_pem: bytes) -> bytes:
    """Derive the public key from the test private key for JWT verification."""
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_pem_private_key,
    )

    private_key = load_pem_private_key(rsa_private_key_pem, password=None)
    return private_key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)


@pytest.fixture()
def key_file(tmp_path: Path, rsa_private_key_pem: bytes) -> Path:
    """Write the test private key to a temporary PEM file."""
    path = tmp_path / "test-app.pem"
    path.write_bytes(rsa_private_key_pem)
    return path


@pytest.fixture()
def authenticator(key_file: Path) -> AppAuthenticator:
    """An AppAuthenticator initialised with the test key file."""
    return AppAuthenticator(app_id=_TEST_APP_ID, private_key_path=str(key_file))


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


def test_app_auth_module_imports() -> None:
    """All public names are importable from lychee.app_auth."""  # P5-R3

    from lychee import app_auth as mod

    assert hasattr(mod, "AppAuthenticator")
    assert hasattr(mod, "InstallationToken")
    assert hasattr(mod, "AppAuthError")


# ---------------------------------------------------------------------------
# Unit tests — InstallationToken
# ---------------------------------------------------------------------------


def test_installation_token_not_expired() -> None:
    """A token with expires_at 10 minutes from now is not expired."""  # P5-R3

    token = InstallationToken(
        token="ghs_test",
        expires_at=time.time() + 600,
        installation_id=1,
    )
    assert not token.is_expired


def test_installation_token_expired() -> None:
    """A token with expires_at in the past is expired."""  # P5-R3

    token = InstallationToken(
        token="ghs_test",
        expires_at=time.time() - 60,
        installation_id=1,
    )
    assert token.is_expired


def test_installation_token_near_expiry() -> None:
    """A token with expires_at 4 minutes from now is expired (5-minute buffer)."""  # P5-R3

    token = InstallationToken(
        token="ghs_test",
        expires_at=time.time() + 240,  # 4 minutes
        installation_id=1,
    )
    assert token.is_expired


def test_installation_token_frozen() -> None:
    """InstallationToken is immutable."""  # P5-R3

    token = InstallationToken(
        token="ghs_test",
        expires_at=time.time() + 600,
        installation_id=1,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        token.token = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Unit tests — AppAuthenticator initialisation
# ---------------------------------------------------------------------------


def test_authenticator_init_missing_key() -> None:
    """FileNotFoundError raised for nonexistent private key path."""  # P5-R3

    with pytest.raises(FileNotFoundError, match="private key not found"):
        AppAuthenticator(app_id=1, private_key_path="/nonexistent/path.pem")


def test_authenticator_init_empty_key(tmp_path: Path) -> None:
    """ValueError raised for empty key file."""  # P5-R3

    empty_file = tmp_path / "empty.pem"
    empty_file.write_text("")
    with pytest.raises(ValueError, match="empty"):
        AppAuthenticator(app_id=1, private_key_path=str(empty_file))


# ---------------------------------------------------------------------------
# Unit tests — AppAuthError
# ---------------------------------------------------------------------------


def test_app_auth_error_with_status() -> None:
    """AppAuthError stores message and status_code."""  # P5-R3

    err = AppAuthError("token request failed", status_code=401)
    assert str(err) == "token request failed"
    assert err.status_code == 401


def test_app_auth_error_without_status() -> None:
    """AppAuthError with status_code=None."""  # P5-R3

    err = AppAuthError("network error")
    assert str(err) == "network error"
    assert err.status_code is None


# ---------------------------------------------------------------------------
# Unit tests — JWT generation
# ---------------------------------------------------------------------------


def test_generate_jwt_structure(
    authenticator: AppAuthenticator,
    rsa_public_key: bytes,
) -> None:
    """Decode the JWT and assert iss, iat, exp fields are correct."""  # P5-R3

    now = 1700000000.0
    token = authenticator.generate_jwt(now=now)

    decoded = pyjwt.decode(
        token,
        rsa_public_key,
        algorithms=["RS256"],
        options={"verify_exp": False},
    )
    assert decoded["iss"] == str(_TEST_APP_ID)
    assert decoded["iat"] == int(now) - 60
    assert decoded["exp"] == int(now) + 600


def test_generate_jwt_expiry_window(
    authenticator: AppAuthenticator,
    rsa_public_key: bytes,
) -> None:
    """exp - iat equals 660 seconds (600 + 60 backdate)."""  # P5-R3

    now = 1700000000.0
    token = authenticator.generate_jwt(now=now)

    decoded = pyjwt.decode(
        token,
        rsa_public_key,
        algorithms=["RS256"],
        options={"verify_exp": False},
    )
    assert decoded["exp"] - decoded["iat"] == 660


def test_generate_jwt_deterministic(
    authenticator: AppAuthenticator,
) -> None:
    """Same now value produces the same JWT."""  # P5-R3

    now = 1700000000.0
    token1 = authenticator.generate_jwt(now=now)
    token2 = authenticator.generate_jwt(now=now)
    assert token1 == token2


# ---------------------------------------------------------------------------
# Regression tests — JWT payload snapshot
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("app_id", "now", "expected_payload"),
    [
        (
            100,
            1700000000.0,
            {"iss": "100", "iat": 1699999940, "exp": 1700000600},
        ),
        (
            999,
            1600000000.0,
            {"iss": "999", "iat": 1599999940, "exp": 1600000600},
        ),
    ],
    ids=["app-100-epoch-1.7B", "app-999-epoch-1.6B"],
)
def test_jwt_payload_snapshot(
    tmp_path: Path,
    rsa_private_key_pem: bytes,
    rsa_public_key: bytes,
    app_id: int,
    now: float,
    expected_payload: dict[str, int | str],
) -> None:
    """Parametrized fixture with known (app_id, now, expected_payload) tuples."""  # P5-R3

    key_file = tmp_path / "snapshot.pem"
    key_file.write_bytes(rsa_private_key_pem)
    auth = AppAuthenticator(app_id=app_id, private_key_path=str(key_file))
    token = auth.generate_jwt(now=now)

    decoded = pyjwt.decode(
        token,
        rsa_public_key,
        algorithms=["RS256"],
        options={"verify_exp": False},
    )
    assert decoded["iss"] == expected_payload["iss"]
    assert decoded["iat"] == expected_payload["iat"]
    assert decoded["exp"] == expected_payload["exp"]


# ---------------------------------------------------------------------------
# Regression tests — token expiry snapshot
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expires_at_offset", "expected_is_expired"),
    [
        (600, False),  # 10 min from now — not expired
        (-60, True),  # 1 min ago — expired
        (240, True),  # 4 min from now — within 5-min buffer
        (300, True),  # exactly 5 min — on the boundary (>= comparison)
        (301, False),  # just past 5-min buffer — not expired
    ],
    ids=["future-10m", "past-1m", "near-4m", "boundary-5m", "safe-5m1s"],
)
def test_token_expiry_snapshot(
    expires_at_offset: int,
    expected_is_expired: bool,
) -> None:
    """Parametrized fixture with known (expires_at, now, expected_is_expired) tuples."""  # P5-R3

    now = time.time()
    token = InstallationToken(
        token="ghs_snap",
        expires_at=now + expires_at_offset,
        installation_id=42,
    )
    assert token.is_expired is expected_is_expired


# ---------------------------------------------------------------------------
# Integration tests — get_installation_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_get_installation_token_mints(
    authenticator: AppAuthenticator,
) -> None:
    """get_installation_token calls the correct GitHub endpoint with JWT auth."""  # P5-R3

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "token": "ghs_minted_token",
        "expires_at": "2099-01-01T00:00:00Z",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client):
        token = await authenticator.get_installation_token(installation_id=42)

    assert token.token == "ghs_minted_token"
    assert token.installation_id == 42
    assert token.expires_at > 0

    # Verify the correct endpoint was called
    call_args = mock_client.post.call_args
    assert "/app/installations/42/access_tokens" in call_args[0][0]
    headers = call_args[1]["headers"]
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Accept"] == "application/vnd.github+json"


@pytest.mark.asyncio()
async def test_get_installation_token_caches(
    authenticator: AppAuthenticator,
) -> None:
    """Second call with same installation_id returns cached token without HTTP."""  # P5-R3

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "token": "ghs_cached",
        "expires_at": "2099-01-01T00:00:00Z",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client):
        token1 = await authenticator.get_installation_token(installation_id=42)
        token2 = await authenticator.get_installation_token(installation_id=42)

    assert token1.token == token2.token
    # Only one HTTP call should have been made
    assert mock_client.post.call_count == 1


@pytest.mark.asyncio()
async def test_get_installation_token_refreshes_expired(
    authenticator: AppAuthenticator,
) -> None:
    """After manually expiring the cached token, the next call mints a new one."""  # P5-R3

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "token": "ghs_fresh",
        "expires_at": "2099-01-01T00:00:00Z",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Seed the cache with an expired token
    expired_token = InstallationToken(
        token="ghs_expired",
        expires_at=time.time() - 60,
        installation_id=42,
    )
    authenticator._token_cache["installation:42"] = expired_token

    with patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client):
        token = await authenticator.get_installation_token(installation_id=42)

    assert token.token == "ghs_fresh"
    assert mock_client.post.call_count == 1


@pytest.mark.asyncio()
async def test_get_installation_token_error(
    authenticator: AppAuthenticator,
) -> None:
    """Mock a 401 response; assert AppAuthError raised with status_code."""  # P5-R3

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"message": "Bad credentials"}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(AppAuthError) as exc_info,
    ):
        await authenticator.get_installation_token(installation_id=42)

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# API tests — _mint_token request shape and response parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_mint_token_request_shape(
    authenticator: AppAuthenticator,
) -> None:
    """Assert the HTTP request has correct method, headers, and URL."""  # P5-R3

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "token": "ghs_shape_test",
        "expires_at": "2099-06-15T12:00:00Z",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client):
        await authenticator._mint_token(installation_id=99)

    call_args = mock_client.post.call_args
    url = call_args[0][0]
    headers = call_args[1]["headers"]

    assert url == "https://api.github.com/app/installations/99/access_tokens"
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Accept"] == "application/vnd.github+json"

    # Verify the Authorization header contains a valid JWT
    jwt_token = headers["Authorization"].split(" ", 1)[1]
    decoded = pyjwt.decode(jwt_token, options={"verify_signature": False})
    assert decoded["iss"] == str(_TEST_APP_ID)


@pytest.mark.asyncio()
async def test_mint_token_response_parsing(
    authenticator: AppAuthenticator,
) -> None:
    """Assert a valid GitHub response is parsed into correct InstallationToken fields."""  # P5-R3

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "token": "ghs_parsed",
        "expires_at": "2099-03-15T10:30:00Z",
        "permissions": {"contents": "read", "pull_requests": "write"},
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client):
        token = await authenticator._mint_token(installation_id=77)

    assert token.token == "ghs_parsed"
    assert token.installation_id == 77
    assert token.expires_at > 0


@pytest.mark.asyncio()
async def test_mint_token_error_response(
    authenticator: AppAuthenticator,
) -> None:
    """Assert non-2xx responses raise AppAuthError with the status code."""  # P5-R3

    mock_response = MagicMock()
    mock_response.status_code = 403

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(AppAuthError) as exc_info,
    ):
        await authenticator._mint_token(installation_id=99)

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Acceptance tests — multi-repo auth flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_accept_app_reviews_across_repos(
    authenticator: AppAuthenticator,
) -> None:
    """Create GitHubClient instances for two different installations."""  # P5-R3

    from lychee.github_client import GitHubClient

    responses = {
        50: {
            "token": "ghs_repo_alpha",
            "expires_at": "2099-01-01T00:00:00Z",
        },
        60: {
            "token": "ghs_repo_beta",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }

    async def mock_post(url: str, **kwargs: object) -> MagicMock:
        """Return the appropriate response based on the installation ID in the URL."""
        for inst_id, resp_data in responses.items():
            if str(inst_id) in url:
                resp = MagicMock()
                resp.status_code = 201
                resp.json.return_value = resp_data
                return resp
        raise AssertionError(f"Unexpected URL: {url}")

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client):
        token_alpha = await authenticator.get_installation_token(installation_id=50)
        token_beta = await authenticator.get_installation_token(installation_id=60)

    # Tokens should be different for different installations
    assert token_alpha.token != token_beta.token
    assert token_alpha.installation_id == 50
    assert token_beta.installation_id == 60

    # Both tokens can be used to create GitHubClient instances
    with patch("lychee.github_client.github.Github", side_effect=[MagicMock(), MagicMock()]):
        client_alpha = GitHubClient.from_installation_token(token_alpha.token)
        client_beta = GitHubClient.from_installation_token(token_beta.token)

    assert client_alpha is not client_beta
    assert client_alpha._github is not client_beta._github


@pytest.mark.asyncio()
async def test_accept_installation_token_auth(
    authenticator: AppAuthenticator,
    rsa_public_key: bytes,
) -> None:
    """Verify the auth flow: JWT -> mint -> token -> client creation end-to-end."""  # P5-R3

    from lychee.github_client import GitHubClient

    captured_headers: dict[str, str] = {}

    async def capture_post(url: str, **kwargs: object) -> MagicMock:
        """Capture the request headers for verification."""
        headers = kwargs.get("headers", {})
        assert isinstance(headers, dict)
        captured_headers.update(headers)
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {
            "token": "ghs_e2e",
            "expires_at": "2099-12-31T23:59:59Z",
        }
        return resp

    mock_client = AsyncMock()
    mock_client.post = capture_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("lychee.app_auth.httpx.AsyncClient", return_value=mock_client):
        token = await authenticator.get_installation_token(installation_id=1)

    # Verify the JWT sent in the Authorization header is valid
    jwt_str = captured_headers["Authorization"].split(" ", 1)[1]
    decoded = pyjwt.decode(jwt_str, rsa_public_key, algorithms=["RS256"])
    assert decoded["iss"] == str(_TEST_APP_ID)

    # Verify the token can create a GitHubClient
    with patch("lychee.github_client.github.Github"):
        client = GitHubClient.from_installation_token(token.token)
    assert client is not None
